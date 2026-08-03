"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.jobs.context import job_context_from_tenant
from app.jobs.stale_config import stale_after_seconds_for
from app.jobs.exceptions import UnknownJobTypeError, WorkerAuthError
from app.jobs.registry import get_job_class
from app.jobs.repository import JobRepository
from app.jobs.worker_auth import get_worker_token
from app.tasks.runtime import iter_tenants, run_async

logger = logging.getLogger(__name__)

STALE_JOB_ERROR = "Job exceeded maximum running time and was reconciled to failed"


@celery_app.task(name="giswater.reconcile_stale_jobs")
def reconcile_stale_jobs() -> None:
    run_async(_reconcile_async())


async def _reconcile_async() -> None:
    now = datetime.now(timezone.utc)
    for tenant in iter_tenants():
        if tenant.db_manager.connection_pool is None:
            continue
        repo = JobRepository(tenant.db_manager)
        try:
            running = await repo.list_running_jobs(tenant.id)
        except Exception:
            logger.exception("[%s] reconcile: failed to list running jobs", tenant.id)
            continue
        for job in running:
            if job.started_at is None:
                continue
            limit = stale_after_seconds_for(job.type)
            if limit is None:
                continue
            cutoff = now - timedelta(seconds=limit)
            if job.started_at > cutoff:
                continue
            logger.warning("[%s] reconcile: job %s is stale, repairing+failing", tenant.id, job.id)
            await _reconcile_one(tenant, repo, job)


async def _reconcile_one(tenant, repo: JobRepository, job) -> None:
    try:
        job_impl = get_job_class(job.type)()
    except UnknownJobTypeError:
        await repo.fail_job(job.id, STALE_JOB_ERROR)
        return

    bearer_token = None
    if job_impl.requires_auth:
        try:
            bearer_token = await get_worker_token(tenant)
        except WorkerAuthError:
            logger.warning("[%s] reconcile: no worker token, skipping repair for job %s", tenant.id, job.id)

    try:
        ctx = job_context_from_tenant(tenant, bearer_token=bearer_token, logger=tenant.api_logger)
        await job_impl.repair(ctx, job.payload, dict(job.side_effects or {}))
    except Exception:
        logger.exception("[%s] reconcile: repair failed for job %s", tenant.id, job.id)
    await repo.fail_job(job.id, STALE_JOB_ERROR)
