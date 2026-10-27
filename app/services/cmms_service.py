"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.db.execution import execute_sql
from app.schemas.cmms.cmms_models import AttachmentUpdate, AttachmentUpload, VisitCreate, VisitUpdate
from app.services import cmms_media
from app.services.context import ServiceContext
from app.services.helpers import accepted_data_response

# Writes go to the singleton cmms schema. Reads are limited to rows in
# {schema}.v_cmms_visit and {schema}.v_cmms_attachment.
_CHUNK = 1024 * 1024
_CMMS_VIEWS = ("v_cmms_visit", "v_cmms_attachment")
_VISIT_SCOPE = "v.id IN (SELECT id FROM {schema}.v_cmms_visit)"
_ATTACHMENT_SCOPE = "a.id IN (SELECT id FROM {schema}.v_cmms_attachment)"

_VISIT_COLUMNS = {
    "extVisitId": ("ext_visit_id", ""),
    "type": ("type", ""),
    "status": ("status", ""),
    "title": ("title", ""),
    "description": ("description", ""),
    "startDate": ("start_date", "::timestamptz"),
    "endDate": ("end_date", "::timestamptz"),
    "properties": ("properties", "::jsonb"),
}
_ATTACHMENT_COLUMNS = {
    "name": ("name", ""),
    "code": ("code", ""),
    "description": ("description", ""),
    "attachmentType": ("attachment_type", ""),
    "properties": ("properties", "::jsonb"),
    "coordinates": ("coordinates", "::jsonb"),
}
# No braces: execute_sql runs the query through sql.SQL.format.
_ATTACHMENT_JSON = """jsonb_build_object(
    'id', a.id, 'name', a.name, 'code', a.code, 'description', a.description,
    'content_type', a.content_type, 'path', a.path, 'thumbnail_path', a.thumbnail_path,
    'size', a.size, 'attachment_type', a.attachment_type, 'properties', a.properties,
    'coordinates', a.coordinates, 'uploaded_by', a.uploaded_by, 'uploaded_at', a.uploaded_at,
    'metadata', a.metadata,
    'sys_codes', COALESCE((
        SELECT jsonb_agg(axf.sys_code ORDER BY axf.id)
        FROM cmms.attachment_x_feature axf WHERE axf.attachment_id = a.id
    ), jsonb_build_array()),
    'visit_ids', COALESCE((
        SELECT jsonb_agg(axv.visit_id ORDER BY axv.id)
        FROM cmms.attachment_x_visit axv WHERE axv.attachment_id = a.id
    ), jsonb_build_array())
)"""

_VISIT_JSON = """jsonb_build_object(
    'id', v.id, 'ext_visit_id', v.ext_visit_id, 'type', v.type, 'status', v.status,
    'title', v.title, 'description', v.description, 'start_date', v.start_date,
    'end_date', v.end_date, 'properties', v.properties, 'created_at', v.created_at,
    'created_by', v.created_by, 'updated_at', v.updated_at, 'updated_by', v.updated_by,
    'sys_codes', COALESCE((
        SELECT jsonb_agg(vx.sys_code ORDER BY vx.id)
        FROM cmms.visit_x_feature vx WHERE vx.visit_id = v.id
    ), jsonb_build_array())
)"""

_INSERT_VISIT = """
WITH v AS (
    INSERT INTO cmms.visit (
        id, ext_visit_id, type, status, title, description,
        start_date, end_date, properties, created_by, updated_by
    ) VALUES (
        %s::uuid, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s::jsonb, %s, %s
    )
    RETURNING id
),
vf AS (
    INSERT INTO cmms.visit_x_feature (visit_id, sys_code)
    SELECT v.id, s.sys_code FROM v CROSS JOIN unnest(%s::text[]) AS s(sys_code)
    RETURNING sys_code
)
SELECT id FROM v
"""

_INSERT_ATTACHMENT = """
WITH a AS (
    INSERT INTO cmms.attachment (
        id, name, code, description, content_type, path, thumbnail_path, size,
        attachment_type, properties, coordinates, uploaded_by, metadata
    ) VALUES (
        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb
    )
    RETURNING id
),
ax AS (
    INSERT INTO cmms.attachment_x_visit (visit_id, attachment_id)
    SELECT %s::uuid, a.id FROM a WHERE %s::uuid IS NOT NULL
),
af AS (
    INSERT INTO cmms.attachment_x_feature (sys_code, attachment_id)
    SELECT s.sys_code, a.id FROM a CROSS JOIN unnest(%s::text[]) AS s(sys_code)
)
SELECT id FROM a
"""


def _json(value) -> str | None:
    return None if value is None else json.dumps(value)


def _clean_codes(codes: list[str] | None) -> list[str]:
    seen: list[str] = []
    for code in codes or []:
        text = str(code).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _assignments(data: dict, columns: dict[str, tuple[str, str]]) -> tuple[str, list]:
    parts: list[str] = []
    params: list = []
    for key, (column, cast) in columns.items():
        if key not in data:
            continue
        value = data[key]
        if cast == "::jsonb" and value is not None:
            value = json.dumps(value)
        parts.append(f"{column} = %s{cast}")
        params.append(value)
    return ", ".join(parts), params


def _split_total(rows: list[dict], key: str) -> tuple[list, int]:
    if not rows:
        return [], 0
    total = int(rows[0].get("total_count") or 0)
    return [row[key] for row in rows], total


class CmmsService:
    def __init__(self, ctx: ServiceContext, *, storage_dir: Path, max_upload_bytes: int):
        self.ctx = ctx.with_logger(__name__)
        self.storage_dir = Path(storage_dir)
        self.max_upload_bytes = max_upload_bytes

    async def _require_cmms_views(self) -> None:
        rows = await self._sql(
            "SELECT c.relname AS name FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = 'v' AND c.relname = ANY(%s)",
            (self.ctx.schema, list(_CMMS_VIEWS)),
        )
        present = {row["name"] for row in rows if row.get("name")}
        if not set(_CMMS_VIEWS).issubset(present):
            schema = self.ctx.schema
            raise HTTPException(status_code=404, detail=f"CMMS is not integrated for schema '{schema}'")

    async def _sql(self, query: str, parameters: tuple | None = None) -> list[dict]:
        # schema= validates the tenant project schema and fills {schema}.
        return await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            query,
            parameters=parameters,
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )

    def _remove_dir(self, attachment_id: str) -> None:
        root = (self.storage_dir / self.ctx.tenant_id).resolve()
        path = (root / attachment_id).resolve()
        if path.is_relative_to(root):
            shutil.rmtree(path, ignore_errors=True)

    def _relative(self, path: Path) -> str:
        root = self.storage_dir.resolve()
        full = path.resolve()
        if not full.is_relative_to(root):
            raise HTTPException(status_code=500, detail="Stored file escaped the CMMS storage directory")
        return full.relative_to(root).as_posix()

    def _resolve_stored(self, relative: str) -> Path:
        root = self.storage_dir.resolve()
        full = (root / relative).resolve()
        if not full.is_relative_to(root) or not full.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return full

    async def _store_one(self, upload: AttachmentUpload) -> dict:
        attachment_id = str(uuid4())
        filename = _safe_name(upload.file.filename)
        directory = self.storage_dir / self.ctx.tenant_id / attachment_id
        directory.mkdir(parents=True, exist_ok=True)
        try:
            dest = directory / filename
            size = await _write_upload(upload.file, dest, self.max_upload_bytes)
            content_type = cmms_media.resolve_content_type(filename, upload.file.content_type)
            processed = await run_in_threadpool(cmms_media.process_upload, dest, content_type)
        except Exception:
            self._remove_dir(attachment_id)
            raise
        coordinates = processed["coordinates"]
        if upload.lat is not None and upload.lon is not None:
            coordinates = {"lat": upload.lat, "lon": upload.lon, "alt": upload.alt}
        return {
            "id": attachment_id,
            "name": upload.name or processed["path"].name,
            "code": upload.code,
            "description": upload.description,
            "content_type": processed["content_type"],
            "path": self._relative(processed["path"]),
            "thumbnail_path": self._relative(processed["thumbnail_path"]) if processed["thumbnail_path"] else None,
            "size": processed["size"] or size,
            "attachment_type": upload.attachmentType,
            "properties": {},
            "coordinates": coordinates,
            "uploaded_by": self.ctx.user_id,
            "metadata": processed["metadata"] or {},
        }

    async def create_visit(self, visit: VisitCreate) -> dict:
        data = visit.model_dump(mode="json")
        visit_id = str(uuid4())
        await self._sql(
            _INSERT_VISIT,
            (
                visit_id,
                data.get("extVisitId"),
                data["type"],
                data["status"],
                data.get("title"),
                data.get("description"),
                data.get("startDate"),
                data.get("endDate"),
                json.dumps(data.get("properties") or {}),
                self.ctx.user_id,
                self.ctx.user_id,
                _clean_codes(data["sysCodes"]),
            ),
        )
        return await self.get_visit(UUID(visit_id))

    async def list_visits(
        self,
        *,
        sys_code: str | None = None,
        visit_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict:
        await self._require_cmms_views()
        clauses = [_VISIT_SCOPE]
        params: list = []
        if sys_code:
            clauses.append("v.id IN (SELECT visit_id FROM cmms.visit_x_feature WHERE sys_code = %s)")
            params.append(sys_code)
        if visit_type:
            clauses.append("v.type = %s")
            params.append(visit_type)
        if status:
            clauses.append("v.status = %s")
            params.append(status)
        params.append(limit)
        query = f"""
            SELECT {_VISIT_JSON} AS visit, count(*) OVER () AS total_count
            FROM cmms.visit v
            WHERE {" AND ".join(clauses)}
            ORDER BY v.created_at DESC
            LIMIT %s
        """
        visits, total = _split_total(await self._sql(query, tuple(params)), "visit")
        return await accepted_data_response(self.ctx, "Fetched visits successfully", {"visits": visits, "count": total})

    async def get_visit(self, visit_id: UUID, *, scoped: bool = False) -> dict:
        if scoped:
            await self._require_cmms_views()
        visit = await self._require_visit(visit_id, scoped=scoped)
        return await accepted_data_response(self.ctx, "Fetched visit successfully", {"visits": [visit]})

    async def update_visit(self, visit_id: UUID, visit: VisitUpdate) -> dict:
        data = visit.model_dump(mode="json", exclude_unset=True)
        codes = _clean_codes(data.pop("sysCodes")) if "sysCodes" in data else None
        if not data and codes is None:
            return await self.get_visit(visit_id)
        await self._update_visit_row(visit_id, data, codes)
        return await self.get_visit(visit_id)

    async def _update_visit_row(self, visit_id: UUID, data: dict, codes: list[str] | None) -> None:
        sets, params = _assignments(data, _VISIT_COLUMNS)
        sets = f"updated_by = %s, {sets}" if sets else "updated_by = %s"
        params = [self.ctx.user_id, *params, str(visit_id)]
        if codes is None:
            query = f"UPDATE cmms.visit SET {sets} WHERE id = %s::uuid RETURNING id"
        else:
            params.extend([str(visit_id), codes])
            query = f"""
                WITH upd AS (
                    UPDATE cmms.visit SET {sets} WHERE id = %s::uuid RETURNING id
                ),
                del AS (
                    DELETE FROM cmms.visit_x_feature WHERE visit_id = %s::uuid RETURNING id
                ),
                ins AS (
                    INSERT INTO cmms.visit_x_feature (visit_id, sys_code)
                    SELECT upd.id, s.sys_code FROM upd CROSS JOIN unnest(%s::text[]) AS s(sys_code)
                    RETURNING sys_code
                )
                SELECT id FROM upd
            """
        rows = await self._sql(query, tuple(params))
        if not rows:
            raise HTTPException(status_code=404, detail=f"Visit '{visit_id}' not found")

    async def delete_visit(self, visit_id: UUID) -> dict:
        visit = await self._delete_row("visit", _VISIT_JSON, "v", visit_id, "Visit")
        return await accepted_data_response(self.ctx, "Deleted visit successfully", {"visits": [visit]})

    async def list_attachments(
        self,
        *,
        sys_code: str | None = None,
        visit_id: UUID | None = None,
        limit: int = 100,
    ) -> dict:
        await self._require_cmms_views()
        clauses = [_ATTACHMENT_SCOPE]
        params: list = []
        if sys_code:
            clauses.append(
                """a.id IN (
                    SELECT attachment_id FROM cmms.attachment_x_feature WHERE sys_code = %s
                    UNION
                    SELECT axv.attachment_id FROM cmms.attachment_x_visit axv
                    JOIN cmms.visit_x_feature vx ON vx.visit_id = axv.visit_id
                    WHERE vx.sys_code = %s
                )"""
            )
            params.extend([sys_code, sys_code])
        if visit_id is not None:
            clauses.append("a.id IN (SELECT attachment_id FROM cmms.attachment_x_visit WHERE visit_id = %s::uuid)")
            params.append(str(visit_id))
        params.append(limit)
        query = f"""
            SELECT {_ATTACHMENT_JSON} AS attachment, count(*) OVER () AS total_count
            FROM cmms.attachment a
            WHERE {" AND ".join(clauses)}
            ORDER BY a.uploaded_at DESC
            LIMIT %s
        """
        items, total = _split_total(await self._sql(query, tuple(params)), "attachment")
        return await accepted_data_response(
            self.ctx, "Fetched attachments successfully", {"attachments": items, "count": total}
        )

    async def get_attachment(self, attachment_id: UUID, *, scoped: bool = False) -> dict:
        if scoped:
            await self._require_cmms_views()
        attachment = await self._require_attachment(attachment_id, scoped=scoped)
        return await accepted_data_response(self.ctx, "Fetched attachment successfully", {"attachments": [attachment]})

    async def add_attachment(self, upload: AttachmentUpload, *, visit_id: UUID | None = None) -> dict:
        if visit_id is not None:
            await self._require_visit(visit_id)
        stored = await self._store_one(upload)
        visit = str(visit_id) if visit_id else None
        try:
            await self._sql(
                _INSERT_ATTACHMENT,
                (
                    stored["id"],
                    stored["name"],
                    stored["code"],
                    stored["description"],
                    stored["content_type"],
                    stored["path"],
                    stored["thumbnail_path"],
                    stored["size"],
                    stored["attachment_type"],
                    _json(stored["properties"]),
                    _json(stored["coordinates"]),
                    stored["uploaded_by"],
                    _json(stored["metadata"]),
                    visit,
                    visit,
                    _clean_codes(upload.sysCodes),
                ),
            )
        except Exception:
            self._remove_dir(stored["id"])
            raise
        return await self.get_attachment(UUID(stored["id"]))

    async def update_attachment(self, attachment_id: UUID, attachment: AttachmentUpdate) -> dict:
        data = attachment.model_dump(mode="json", exclude_unset=True)
        codes = _clean_codes(data.pop("sysCodes")) if "sysCodes" in data else None
        if not data and codes is None:
            return await self.get_attachment(attachment_id)
        if data:
            await self._update_attachment_row(attachment_id, data)
        if codes is not None:
            await self._replace_attachment_codes(attachment_id, codes)
        return await self.get_attachment(attachment_id)

    async def delete_attachment(self, attachment_id: UUID) -> dict:
        attachment = await self._delete_row("attachment", _ATTACHMENT_JSON, "a", attachment_id, "Attachment")
        self._remove_dir(str(attachment_id))
        return await accepted_data_response(self.ctx, "Deleted attachment successfully", {"attachments": [attachment]})

    async def get_file(self, attachment_id: UUID, *, visit_id: UUID | None = None, thumbnail: bool = False):
        await self._require_cmms_views()
        rows = await self._sql(
            f"""
            SELECT path, thumbnail_path, content_type, name
            FROM cmms.attachment a
            WHERE a.id = %s::uuid
              AND {_ATTACHMENT_SCOPE}
              AND (
                %s::uuid IS NULL
                OR EXISTS (
                    SELECT 1 FROM cmms.attachment_x_visit x
                    WHERE x.attachment_id = a.id AND x.visit_id = %s::uuid
                )
              )
            """,
            (str(attachment_id), str(visit_id) if visit_id else None, str(visit_id) if visit_id else None),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' not found")
        row = rows[0]
        if thumbnail:
            if not row.get("thumbnail_path"):
                raise HTTPException(status_code=404, detail="No thumbnail")
            return self._resolve_stored(row["thumbnail_path"]), "image/jpeg", "thumb.jpg"
        return self._resolve_stored(row["path"]), row.get("content_type"), row.get("name")

    async def _delete_row(self, table: str, row_json: str, alias: str, row_id: UUID, label: str) -> dict:
        # Snapshot first: a RETURNING subquery would miss links removed by ON DELETE CASCADE.
        rows = await self._sql(
            f"""
            WITH src AS (
                SELECT {row_json} AS item
                FROM cmms.{table} {alias}
                WHERE {alias}.id = %s::uuid
            ),
            gone AS (
                DELETE FROM cmms.{table} WHERE id = %s::uuid RETURNING id
            )
            SELECT src.item AS item FROM src WHERE EXISTS (SELECT 1 FROM gone)
            """,
            (str(row_id), str(row_id)),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"{label} '{row_id}' not found")
        return rows[0]["item"]

    async def _require_visit(self, visit_id: UUID, *, scoped: bool = False) -> dict:
        scope = f" AND {_VISIT_SCOPE}" if scoped else ""
        rows = await self._sql(
            f"SELECT {_VISIT_JSON} AS visit FROM cmms.visit v WHERE v.id = %s::uuid{scope}",
            (str(visit_id),),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Visit '{visit_id}' not found")
        return rows[0]["visit"]

    async def _require_attachment(self, attachment_id: UUID, *, scoped: bool = False) -> dict:
        scope = f" AND {_ATTACHMENT_SCOPE}" if scoped else ""
        rows = await self._sql(
            f"SELECT {_ATTACHMENT_JSON} AS attachment FROM cmms.attachment a WHERE a.id = %s::uuid{scope}",
            (str(attachment_id),),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' not found")
        return rows[0]["attachment"]

    async def _update_attachment_row(self, attachment_id: UUID, data: dict) -> None:
        sets, params = _assignments(data, _ATTACHMENT_COLUMNS)
        params.append(str(attachment_id))
        rows = await self._sql(
            f"UPDATE cmms.attachment SET {sets} WHERE id = %s::uuid RETURNING id",
            tuple(params),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' not found")

    async def _replace_attachment_codes(self, attachment_id: UUID, codes: list[str]) -> None:
        rows = await self._sql(
            """
            WITH found AS (
                SELECT id FROM cmms.attachment WHERE id = %s::uuid
            ),
            del AS (
                DELETE FROM cmms.attachment_x_feature
                WHERE attachment_id = (SELECT id FROM found)
                RETURNING id
            ),
            ins AS (
                INSERT INTO cmms.attachment_x_feature (sys_code, attachment_id)
                SELECT s.sys_code, found.id FROM found CROSS JOIN unnest(%s::text[]) AS s(sys_code)
                RETURNING sys_code
            )
            SELECT id FROM found
            """,
            (str(attachment_id), codes),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' not found")


def _safe_name(filename: str | None) -> str:
    name = Path(filename or "file").name
    if name in ("", ".", ".."):
        return "file"
    return name


async def _write_upload(upload: UploadFile, dest: Path, limit: int) -> int:
    size = 0
    try:
        with dest.open("wb") as handle:
            while chunk := await upload.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    mb = limit // (1024 * 1024)
                    raise HTTPException(status_code=413, detail=f"File exceeds the {mb}MB upload limit")
                handle.write(chunk)
    finally:
        await upload.close()
    return size
