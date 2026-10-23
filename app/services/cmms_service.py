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
from app.schemas.cmms.cmms_models import AttachmentMeta, AttachmentUpdate, VisitCreate, VisitUpdate
from app.services import cmms_media
from app.services.context import ServiceContext
from app.services.helpers import accepted_data_response

# cmms is one schema per database, not the tenant project schema.
_CHUNK = 1024 * 1024

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
_RECORD_KEYS = (
    "id",
    "name",
    "code",
    "description",
    "content_type",
    "path",
    "thumbnail_path",
    "size",
    "attachment_type",
    "properties",
    "coordinates",
    "uploaded_by",
    "metadata",
)

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

_ATTACH_CTES = """
a AS (
    INSERT INTO cmms.attachment (
        id, name, code, description, content_type, path, thumbnail_path, size,
        attachment_type, properties, coordinates, uploaded_by, metadata
    )
    SELECT id, name, code, description, content_type, path, thumbnail_path, size,
        attachment_type, properties, coordinates, uploaded_by, metadata
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        id uuid, name text, code text, description text, content_type text, path text,
        thumbnail_path text, size bigint, attachment_type text, properties jsonb,
        coordinates jsonb, uploaded_by text, metadata jsonb
    )
    RETURNING id, name, code, description, content_type, path, thumbnail_path, size,
        attachment_type, properties, coordinates, uploaded_by, uploaded_at, metadata
),
ax AS (
    INSERT INTO cmms.attachment_x_visit (visit_id, attachment_id)
    SELECT %s::uuid, a.id FROM a WHERE %s::uuid IS NOT NULL
),
af AS (
    INSERT INTO cmms.attachment_x_feature (sys_code, attachment_id)
    SELECT s.sys_code, a.id FROM a CROSS JOIN unnest(%s::text[]) AS s(sys_code)
)
"""

_INSERT_VISIT = f"""
WITH v AS (
    INSERT INTO cmms.visit (
        id, ext_visit_id, type, status, title, description,
        start_date, end_date, properties, created_by, updated_by
    ) VALUES (
        %s::uuid, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s::jsonb, %s, %s
    )
    RETURNING id, ext_visit_id, type, status, title, description, start_date, end_date,
        properties, created_at, created_by, updated_at, updated_by
),
vf AS (
    INSERT INTO cmms.visit_x_feature (visit_id, sys_code)
    SELECT %s::uuid, s.sys_code FROM unnest(%s::text[]) AS s(sys_code)
    RETURNING sys_code
),
{_ATTACH_CTES}
SELECT to_jsonb(v) AS visit,
    COALESCE((SELECT jsonb_agg(vf.sys_code ORDER BY vf.sys_code) FROM vf), jsonb_build_array()) AS sys_codes,
    COALESCE((SELECT jsonb_agg(to_jsonb(a)) FROM a), jsonb_build_array()) AS attachments
FROM v
"""

_INSERT_ATTACHMENTS = f"""
WITH {_ATTACH_CTES}
SELECT COALESCE((SELECT jsonb_agg(to_jsonb(a)) FROM a), jsonb_build_array()) AS attachments
"""


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

    async def _sql(self, query: str, parameters: tuple | None = None) -> list[dict]:
        # schema= validates the tenant project schema. cmms itself is hardcoded.
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

    async def _store_files(self, files: list[UploadFile] | None, meta: AttachmentMeta | None) -> list[dict]:
        created: list[str] = []
        try:
            return [await self._store_one(upload, meta, created) for upload in (files or [])]
        except Exception:
            for attachment_id in created:
                self._remove_dir(attachment_id)
            raise

    async def _store_one(self, upload: UploadFile, meta: AttachmentMeta | None, created: list[str]) -> dict:
        attachment_id = str(uuid4())
        filename = _safe_name(upload.filename)
        directory = self.storage_dir / self.ctx.tenant_id / attachment_id
        directory.mkdir(parents=True, exist_ok=True)
        created.append(attachment_id)
        dest = directory / filename
        size = await _write_upload(upload, dest, self.max_upload_bytes)
        content_type = cmms_media.resolve_content_type(filename, upload.content_type)
        processed = await run_in_threadpool(cmms_media.process_upload, dest, content_type)
        coordinates = processed["coordinates"]
        if meta is not None and meta.coordinates is not None:
            coordinates = meta.coordinates
        return {
            "id": attachment_id,
            "name": processed["path"].name,
            "code": None,
            "description": meta.description if meta else None,
            "content_type": processed["content_type"],
            "path": self._relative(processed["path"]),
            "thumbnail_path": self._relative(processed["thumbnail_path"]) if processed["thumbnail_path"] else None,
            "size": processed["size"] or size,
            "attachment_type": meta.attachmentType if meta else None,
            "properties": meta.properties if meta else {},
            "coordinates": coordinates,
            "uploaded_by": self.ctx.user_id,
            "metadata": processed["metadata"] or {},
        }

    def _attach_params(self, records: list[dict], visit_id: str | None, sys_codes: list[str]) -> tuple:
        payload = [{key: row[key] for key in _RECORD_KEYS} for row in records]
        return (json.dumps(payload), visit_id, visit_id, sys_codes)

    async def create_visit(self, visit: VisitCreate, files: list[UploadFile] | None = None) -> dict:
        data = visit.model_dump(mode="json")
        visit_id = str(uuid4())
        codes = _clean_codes(data["sysCodes"])
        stored = await self._store_files(files, None)
        params = (
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
            visit_id,
            codes,
            *self._attach_params(stored, visit_id, []),
        )
        try:
            rows = await self._sql(_INSERT_VISIT, params)
        except Exception:
            for item in stored:
                self._remove_dir(item["id"])
            raise
        body = rows[0]
        created = body["visit"]
        created["sys_codes"] = body["sys_codes"]
        created["attachments"] = _stamp(body["attachments"], visit_id=created["id"], sys_codes=[])
        return await accepted_data_response(self.ctx, "Created visit successfully", {"visits": [created]})

    async def list_visits(
        self,
        *,
        sys_code: str | None = None,
        visit_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict:
        clauses = ["TRUE"]
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

    async def get_visit(self, visit_id: UUID) -> dict:
        visit = await self._require_visit(visit_id)
        visit["attachments"] = await self._attachments_for_visit(visit_id)
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
        rows = await self._sql("DELETE FROM cmms.visit WHERE id = %s::uuid RETURNING id", (str(visit_id),))
        if not rows:
            raise HTTPException(status_code=404, detail=f"Visit '{visit_id}' not found")
        return await accepted_data_response(self.ctx, "Deleted visit successfully", {"visits": [{"id": str(visit_id)}]})

    async def list_attachments(
        self,
        *,
        sys_code: str | None = None,
        visit_id: UUID | None = None,
        limit: int = 100,
    ) -> dict:
        clauses = ["TRUE"]
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

    async def get_attachment(self, attachment_id: UUID) -> dict:
        attachment = await self._require_attachment(attachment_id)
        return await accepted_data_response(self.ctx, "Fetched attachment successfully", {"attachments": [attachment]})

    async def add_attachments(
        self,
        files: list[UploadFile] | None,
        *,
        visit_id: UUID | None = None,
        meta: AttachmentMeta | None = None,
    ) -> dict:
        if visit_id is not None:
            await self._require_visit(visit_id)
        stored = await self._store_files(files, meta)
        if not stored:
            raise HTTPException(status_code=400, detail="No files uploaded")
        codes = _clean_codes(meta.sysCodes) if meta else []
        visit = str(visit_id) if visit_id else None
        try:
            rows = await self._sql(_INSERT_ATTACHMENTS, self._attach_params(stored, visit, codes))
        except Exception:
            for item in stored:
                self._remove_dir(item["id"])
            raise
        attachments = _stamp(rows[0]["attachments"], visit_id=visit, sys_codes=codes)
        return await accepted_data_response(self.ctx, "Uploaded attachments successfully", {"attachments": attachments})

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
        rows = await self._sql(
            "DELETE FROM cmms.attachment WHERE id = %s::uuid RETURNING id",
            (str(attachment_id),),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' not found")
        self._remove_dir(str(attachment_id))
        return await accepted_data_response(
            self.ctx, "Deleted attachment successfully", {"attachments": [{"id": str(attachment_id)}]}
        )

    async def get_file(self, attachment_id: UUID, *, visit_id: UUID | None = None, thumbnail: bool = False):
        rows = await self._sql(
            """
            SELECT path, thumbnail_path, content_type, name
            FROM cmms.attachment a
            WHERE a.id = %s::uuid
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

    async def _require_visit(self, visit_id: UUID) -> dict:
        rows = await self._sql(
            f"SELECT {_VISIT_JSON} AS visit FROM cmms.visit v WHERE v.id = %s::uuid", (str(visit_id),)
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Visit '{visit_id}' not found")
        return rows[0]["visit"]

    async def _require_attachment(self, attachment_id: UUID) -> dict:
        rows = await self._sql(
            f"SELECT {_ATTACHMENT_JSON} AS attachment FROM cmms.attachment a WHERE a.id = %s::uuid",
            (str(attachment_id),),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' not found")
        return rows[0]["attachment"]

    async def _attachments_for_visit(self, visit_id: UUID) -> list:
        rows = await self._sql(
            f"""
            SELECT COALESCE(jsonb_agg({_ATTACHMENT_JSON} ORDER BY a.uploaded_at), jsonb_build_array()) AS attachments
            FROM cmms.attachment a
            JOIN cmms.attachment_x_visit x ON x.attachment_id = a.id
            WHERE x.visit_id = %s::uuid
            """,
            (str(visit_id),),
        )
        return rows[0]["attachments"] if rows else []

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


def _stamp(attachments, *, visit_id: str | None, sys_codes: list[str]) -> list:
    stamped = []
    for item in attachments or []:
        row = dict(item)
        row["sys_codes"] = list(sys_codes)
        row["visit_ids"] = [visit_id] if visit_id else []
        stamped.append(row)
    return stamped
