"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import psycopg
from fastapi import HTTPException
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import global_settings
from app.core.exceptions import DatabaseUnavailableError
from app.db.schema import resolve_log_targets
from app.db.version import get_db_version
from app.services.context import ServiceContext
from app.tenancy.registry import Tenant
from app.utils.version import db_version_at_least


class SystemService:
    def __init__(self, tenant: Tenant, ctx: ServiceContext | None = None):
        self.tenant = tenant
        self.ctx = ctx

    async def ready(self) -> dict:
        log = logging.getLogger(__name__)
        db_ready = await self.tenant.db_manager.is_db_available(timeout_seconds=2.0)
        if not db_ready:
            return {
                "status": "not_ready",
                "tenant": self.tenant.id,
                "checks": {"database": "down"},
            }
        checks: dict = {"database": "up"}
        if global_settings.giswater_db_version_check:
            try:
                gv = await get_db_version(log, self.tenant.db_manager, self.tenant.settings.db_schema)
            except HTTPException as exc:
                return {
                    "status": "not_ready",
                    "tenant": self.tenant.id,
                    "checks": {"database": "up", "giswater_db": "error", "detail": exc.detail},
                }
            if gv is None:
                return {
                    "status": "not_ready",
                    "tenant": self.tenant.id,
                    "checks": {"database": "up", "giswater_db": "unknown"},
                }
            min_v = global_settings.giswater_db_min_version
            if not db_version_at_least(gv, min_v):
                return {
                    "status": "not_ready",
                    "tenant": self.tenant.id,
                    "checks": {
                        "database": "up",
                        "giswater_db": "incompatible",
                        "giswater_db_version": gv,
                        "giswater_db_min_required": min_v,
                    },
                }
            checks["giswater_db"] = gv
        return {"status": "ready", "tenant": self.tenant.id, "checks": checks}

    async def validate_schema(self, schema: str) -> dict:
        if not await self.tenant.db_manager.validate_schema(schema):
            raise LookupError(f"Schema '{schema}' not found")
        return {"status": "Accepted", "message": f"Schema '{schema}' is valid"}

    async def list_schemas(self) -> dict:
        """Return Giswater project schemas (those with sys_version) and their type/version."""
        db_manager = self.tenant.db_manager
        async with db_manager.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            try:
                async with conn.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """
                        SELECT n.nspname
                        FROM pg_namespace n
                        WHERE n.nspname NOT LIKE 'pg\\_%'
                          AND n.nspname <> 'information_schema'
                          AND has_schema_privilege(n.oid, 'USAGE')
                          AND EXISTS (
                              SELECT 1 FROM pg_class c
                              WHERE c.relnamespace = n.oid AND c.relname = 'sys_version'
                          )
                        ORDER BY n.nspname
                        """
                    )
                    names = [row["nspname"] for row in await cursor.fetchall()]
                    items: list[dict] = []
                    for name in names:
                        query = sql.SQL("SELECT * FROM {}.sys_version ORDER BY id DESC LIMIT 1").format(
                            sql.Identifier(name)
                        )
                        await cursor.execute(query)
                        row = await cursor.fetchone()
                        if not row:
                            continue
                        items.append(
                            {
                                "schema": name,
                                "project_type": row.get("project_type") or row.get("project"),
                                "giswater": row.get("giswater"),
                                "epsg": row.get("epsg"),
                            }
                        )
                await conn.commit()
            except psycopg.Error as exc:
                await conn.rollback()
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"schemas": items}

    @staticmethod
    def _manage_where_clauses(where_clauses: list, params: list, from_, to, endpoint, method, status, user):
        if from_:
            where_clauses.append("ts >= %s")
            params.append(from_)
        if to:
            where_clauses.append("ts <= %s")
            params.append(to)
        if endpoint:
            where_clauses.append("endpoint = %s")
            params.append(endpoint)
        if method:
            where_clauses.append("method = %s")
            params.append(method.upper())
        if status is not None:
            where_clauses.append("status = %s")
            params.append(status)
        if user:
            where_clauses.append("user_name = %s")
            params.append(user)

    async def get_logs(
        self,
        *,
        from_: datetime | None = None,
        to: datetime | None = None,
        endpoint: str | None = None,
        method: str | None = None,
        status: int | None = None,
        user: str | None = None,
        request_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        db_manager = self.tenant.db_manager
        where_clauses: list[str] = []
        params: list = []
        self._manage_where_clauses(where_clauses, params, from_, to, endpoint, method, status, user)
        if request_id:
            try:
                params.append(uuid.UUID(request_id))
            except ValueError as exc:
                raise ValueError("Invalid request_id") from exc
            where_clauses.append("request_id = %s")

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        targets = await resolve_log_targets(db_manager)
        query = sql.SQL(
            f"""
        SELECT ts, endpoint, method, status, duration_ms, user_name, request_id,
               client_ip, query_params, body_size, response_size,
               request_headers, request_body, response_headers, response_body,
               EXISTS (
                   SELECT 1 FROM {{schema}}.{{db_table}} d
                   WHERE d.request_id = main.request_id
               ) AS has_db_logs
        FROM {{schema}}.{{table}} main
        {where_sql}
        ORDER BY ts DESC
        LIMIT %s OFFSET %s
        """
        ).format(
            schema=sql.Identifier(targets.schema),
            table=sql.Identifier(targets.http_table),
            db_table=sql.Identifier(targets.db_table),
        )
        params.extend([limit, offset])

        async with db_manager.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            try:
                async with conn.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(query, tuple(params))
                    rows = await cursor.fetchall()
                await conn.commit()
            except psycopg.Error as exc:
                await conn.rollback()
                raise RuntimeError(str(exc)) from exc

        return {"count": len(rows), "items": rows}

    async def get_db_logs(self, request_id: str, limit: int = 50) -> dict:
        db_manager = self.tenant.db_manager
        try:
            rid = uuid.UUID(request_id)
        except ValueError as exc:
            raise ValueError("Invalid request_id") from exc

        targets = await resolve_log_targets(db_manager)
        query = sql.SQL(
            """
        SELECT ts, request_id, schema_name, function_name, sql_text,
               response_json, duration_ms, status, error
        FROM {schema}.{table}
        WHERE request_id = %s
        ORDER BY ts ASC
        LIMIT %s
        """
        ).format(schema=sql.Identifier(targets.schema), table=sql.Identifier(targets.db_table))

        async with db_manager.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            try:
                async with conn.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(query, (rid, limit))
                    rows = await cursor.fetchall()
                await conn.commit()
            except psycopg.Error as exc:
                await conn.rollback()
                raise RuntimeError(str(exc)) from exc

        return {"count": len(rows), "items": rows}
