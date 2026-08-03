"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.celery_app import celery_app
from app.jobs.context import job_context_from_tenant
from app.jobs.exceptions import WorkerAuthError
from app.jobs.models import TERMINAL_STATUSES
from app.jobs.progress import JobProgressReporter
from app.jobs.registry import get_job_class
from app.jobs.repository import JobRepository
from app.jobs.worker_auth import get_worker_token
from app.tasks.runtime import get_tenant, run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="giswater.execute_job", bind=True, max_retries=0)
def execute_job(self, tenant_id: str, job_id: str) -> None:  # noqa: ARG001
    run_async(_execute_job_async(tenant_id, job_id))


async def _execute_job_async(tenant_id: str, job_id: str) -> None:
    tenant = await get_tenant(tenant_id)
    repo = JobRepository(tenant.db_manager)
    job_uuid = UUID(job_id)

    record = await repo.get_job(job_uuid, tenant_id)
    if record is None:
        logger.warning("[%s] execute_job: job %s not found", tenant_id, job_id)
        return
    if record.status in TERMINAL_STATUSES:
        logger.info("[%s] execute_job: job %s already terminal (%s)", tenant_id, job_id, record.status.value)
        return

    record = await repo.mark_running(job_uuid)
    if record is None:
        logger.info("[%s] execute_job: job %s not in 'created' state, skipping", tenant_id, job_id)
        return

    try:
        job_impl = get_job_class(record.type)()
        progress = JobProgressReporter(repo, job_uuid, record.type)
        ctx = await _build_context(tenant, repo, job_uuid, job_impl, progress)
        if ctx is None:
            return
    except Exception as exc:
        error_text = str(exc) or exc.__class__.__name__
        logger.exception(
            "[%s] execute_job: job %s failed before handler (%s): %s",
            tenant_id,
            job_uuid,
            record.type,
            error_text,
        )
        await repo.fail_job(job_uuid, error_text)
        return

    await _run_handler(repo, job_uuid, record, job_impl, ctx, progress)


async def _build_context(tenant, repo: JobRepository, job_uuid, job_impl, progress):
    bearer_token = None
    if job_impl.requires_auth:
        try:
            bearer_token = await get_worker_token(tenant)
        except WorkerAuthError as exc:
            logger.error("[%s] worker token unavailable for job %s: %s", tenant.id, job_uuid, exc)
            await repo.fail_job(job_uuid, str(exc))
            return None
    try:
        return job_context_from_tenant(
            tenant,
            bearer_token=bearer_token,
            logger=tenant.api_logger,
            progress=progress,
        )
    except ValueError as exc:
        await repo.fail_job(job_uuid, str(exc))
        return None


async def _run_handler(repo: JobRepository, job_uuid, record, job_impl, ctx, progress) -> None:
    side_effects = dict(record.side_effects or {})
    try:
        result = await job_impl.run(ctx, record.payload, side_effects)
        if side_effects:
            await repo.update_side_effects(job_uuid, side_effects)
        await progress.set_percentage(100.0, force=True)
        await repo.finish_job(job_uuid, result)
        logger.info("job %s finished (%s)", job_uuid, record.type)
    except Exception as exc:
        error_text = str(exc) or exc.__class__.__name__
        logger.exception("job %s failed (%s): %s", job_uuid, record.type, error_text)
        if side_effects:
            try:
                await repo.update_side_effects(job_uuid, side_effects)
            except Exception:
                logger.exception("failed to persist side_effects for job %s", job_uuid)
        try:
            await job_impl.repair(ctx, record.payload, side_effects)
        except Exception:
            logger.exception("repair failed for job %s", job_uuid)
        await repo.fail_job(job_uuid, error_text)
