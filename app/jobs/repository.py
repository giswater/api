"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.core.exceptions import DatabaseUnavailableError
from app.db.schema import GWAPI_SCHEMA, JOBS_TABLE
from app.jobs.models import JobRecord, JobStatus


def _row_to_record(row: dict[str, Any]) -> JobRecord:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    result = row.get("result")
    if isinstance(result, str):
        result = json.loads(result)
    side_effects = row.get("side_effects") or {}
    if isinstance(side_effects, str):
        side_effects = json.loads(side_effects)
    progress = row.get("progress") or {}
    if isinstance(progress, str):
        progress = json.loads(progress)
    return JobRecord(
        id=row["id"],
        type=row["type"],
        status=JobStatus(row["status"]),
        tenant_id=row["tenant_id"],
        schema_name=row.get("schema_name"),
        payload=payload,
        result=result,
        error=row.get("error"),
        side_effects=side_effects,
        progress=progress,
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        created_by=row.get("created_by"),
        user_name=row.get("user_name"),
    )


class JobRepository:
    def __init__(self, db_manager):
        self._db = db_manager

    async def create_job(
        self,
        *,
        job_type: str,
        tenant_id: str,
        payload: dict[str, Any],
        schema_name: str | None = None,
        user_name: str | None = None,
    ) -> JobRecord:
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.{} (
                            type, status, tenant_id, schema_name, payload, user_name, created_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_USER)
                        RETURNING *
                        """
                    ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)),
                    (
                        job_type,
                        JobStatus.CREATED.value,
                        tenant_id,
                        schema_name,
                        Json(payload),
                        user_name,
                    ),
                )
                row = await cursor.fetchone()
            await conn.commit()
        if row is None:
            raise RuntimeError("Failed to create job")
        return _row_to_record(row)

    async def get_job(self, job_id: UUID, tenant_id: str) -> JobRecord | None:
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    sql.SQL("SELECT * FROM {}.{} WHERE id = %s AND tenant_id = %s").format(
                        sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)
                    ),
                    (job_id, tenant_id),
                )
                row = await cursor.fetchone()
            await conn.commit()
        return _row_to_record(row) if row else None

    async def mark_running(self, job_id: UUID) -> JobRecord | None:
        """Transition a job to running and stamp started_at. Returns the updated row.

        Only flips jobs still in 'created' so a redelivered Celery task does not
        re-run a job that already started or finished.
        """
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    sql.SQL(
                        """
                        UPDATE {}.{}
                        SET status = %s, started_at = now()
                        WHERE id = %s AND status = %s
                        RETURNING *
                        """
                    ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)),
                    (JobStatus.RUNNING.value, job_id, JobStatus.CREATED.value),
                )
                row = await cursor.fetchone()
            await conn.commit()
        return _row_to_record(row) if row else None

    async def finish_job(self, job_id: UUID, result: dict[str, Any]) -> None:
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    sql.SQL(
                        """
                        UPDATE {}.{}
                        SET status = %s, result = %s, finished_at = now(), error = NULL
                        WHERE id = %s
                        """
                    ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)),
                    (JobStatus.FINISHED.value, Json(result), job_id),
                )
            await conn.commit()

    async def fail_job(self, job_id: UUID, error: str) -> None:
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    sql.SQL(
                        """
                        UPDATE {}.{}
                        SET status = %s, error = %s, finished_at = now()
                        WHERE id = %s
                        """
                    ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)),
                    (JobStatus.FAILED.value, error, job_id),
                )
            await conn.commit()

    async def update_side_effects(self, job_id: UUID, side_effects: dict[str, Any]) -> None:
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    sql.SQL("UPDATE {}.{} SET side_effects = %s WHERE id = %s").format(
                        sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)
                    ),
                    (Json(side_effects), job_id),
                )
            await conn.commit()

    async def update_progress(self, job_id: UUID, progress: dict[str, Any]) -> None:
        async with self._db.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    sql.SQL("UPDATE {}.{} SET progress = %s WHERE id = %s").format(
                        sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)
                    ),
                    (Json(progress), job_id),
                )
            await conn.commit()

    async def list_running_jobs(self, tenant_id: str) -> list[JobRecord]:
        async with self._db.get_db() as conn:
            if conn is None:
                return []
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    sql.SQL("SELECT * FROM {}.{} WHERE status = %s AND tenant_id = %s ORDER BY started_at").format(
                        sql.Identifier(GWAPI_SCHEMA), sql.Identifier(JOBS_TABLE)
                    ),
                    (JobStatus.RUNNING.value, tenant_id),
                )
                rows = await cursor.fetchall()
            await conn.commit()
        return [_row_to_record(row) for row in rows]
