"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.jobs.exceptions import JobNotFoundError
from app.jobs.models import JobRecord, JobStatus, TERMINAL_STATUSES
from app.jobs.poll_config import poll_interval_ms_for_job
from app.jobs.progress import poll_interval_ms_for_progress
from app.jobs.repository import JobRepository
from app.schemas.jobs import JobCreateResponse, JobResultResponse, JobStatusResponse
from app.tenancy.registry import Tenant

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, tenant: Tenant):
        self._tenant = tenant
        self._repo = JobRepository(tenant.db_manager)

    async def create_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
        user_name: str | None = None,
    ) -> JobCreateResponse:
        record = await self._repo.create_job(
            job_type=job_type,
            tenant_id=self._tenant.id,
            payload=payload,
            schema_name=self._tenant.settings.db_schema,
            user_name=user_name,
        )
        await self._enqueue(record.id, job_type)
        return JobCreateResponse(
            job_id=record.id,
            status=record.status,
            poll_interval_ms=poll_interval_ms_for_job(record),
        )

    async def _enqueue(self, job_id: UUID, job_type: str) -> None:
        from app.tasks.jobs import execute_job

        try:
            await asyncio.to_thread(
                execute_job.apply_async,
                kwargs={"tenant_id": self._tenant.id, "job_id": str(job_id)},
                task_id=str(job_id),
            )
        except Exception as exc:
            logger.exception("[%s] failed to enqueue job %s (%s)", self._tenant.id, job_id, job_type)
            await self._repo.fail_job(job_id, f"enqueue failed: {exc}")
            raise RuntimeError(f"Failed to enqueue job: {exc}") from exc

    async def get_job_status(self, job_id: UUID) -> JobStatusResponse:
        record = await self._require_job(job_id)
        return self.build_status_response(record)

    async def get_job_result(self, job_id: UUID) -> JobResultResponse:
        record = await self._require_job(job_id)
        if record.status != JobStatus.FINISHED:
            raise JobNotFoundError(f"Job {job_id} result not available (status={record.status.value})")
        return JobResultResponse(
            job_id=record.id,
            type=record.type,
            status=record.status,
            result=record.result or {},
        )

    async def _require_job(self, job_id: UUID) -> JobRecord:
        record = await self._repo.get_job(job_id, self._tenant.id)
        if record is None:
            raise JobNotFoundError(f"Job {job_id} not found")
        return record

    @staticmethod
    def build_status_response(record: JobRecord) -> JobStatusResponse:
        progress = record.progress or {}
        poll = poll_interval_ms_for_progress(record.type, progress, record.status.value)
        if poll is None:
            poll = poll_interval_ms_for_job(record)

        return JobStatusResponse(
            job_id=record.id,
            type=record.type,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            error=record.error,
            progress_percentage=float(progress.get("percentage", 0.0)),
            current_step=progress.get("current_step"),
            step_label=progress.get("step_label"),
            step_current=int(progress.get("step_current", 0)),
            step_total=int(progress.get("step_total", 0)),
            message=progress.get("message"),
            poll_interval_ms=poll,
        )

    @staticmethod
    def is_terminal(status: JobStatus) -> bool:
        return status in TERMINAL_STATUSES
