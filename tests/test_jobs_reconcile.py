"""Tests for the stale-job reconciliation Celery Beat task."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.jobs.models import JobRecord, JobStatus
from app.tasks import maintenance


def _running_record(*, age_seconds: int, job_type: str = "test_job") -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        id=uuid4(),
        type=job_type,
        status=JobStatus.RUNNING,
        tenant_id="test",
        schema_name="public",
        payload={"key": "value"},
        result=None,
        error=None,
        side_effects={},
        progress={},
        created_at=now - timedelta(seconds=age_seconds),
        started_at=now - timedelta(seconds=age_seconds),
        finished_at=None,
        created_by=None,
        user_name=None,
    )


class _FakeJob:
    requires_auth = False
    max_running_seconds = None

    async def repair(self, ctx, payload, side_effects):
        return None


def _wire(monkeypatch, *, running, job_cls=_FakeJob):
    tenant = SimpleNamespace(
        id="test",
        db_manager=SimpleNamespace(connection_pool=object()),
        api_logger=logging.getLogger("test"),
    )
    monkeypatch.setattr(maintenance, "iter_tenants", lambda: [tenant])

    repo = MagicMock()
    repo.list_running_jobs = AsyncMock(return_value=running)
    repo.fail_job = AsyncMock()
    monkeypatch.setattr(maintenance, "JobRepository", lambda *_a, **_k: repo)
    monkeypatch.setattr(maintenance, "get_job_class", lambda _t: job_cls)
    monkeypatch.setattr("app.jobs.stale_config.get_job_class", lambda _t: job_cls)
    monkeypatch.setattr(maintenance, "job_context_from_tenant", lambda *_a, **_k: object())
    monkeypatch.setattr(maintenance, "get_worker_token", AsyncMock(return_value="tok"))
    return repo


def test_reconcile_fails_stale_jobs(monkeypatch):
    stale = _running_record(age_seconds=10_000)
    repo = _wire(monkeypatch, running=[stale])
    monkeypatch.setattr(
        "app.jobs.stale_config.global_settings",
        __import__("types").SimpleNamespace(jobs_stale_after_seconds=7200),
    )
    asyncio.run(maintenance._reconcile_async())
    repo.fail_job.assert_awaited_once()
    assert repo.fail_job.await_args.args[0] == stale.id


def test_reconcile_ignores_fresh_jobs(monkeypatch):
    fresh = _running_record(age_seconds=5)
    repo = _wire(monkeypatch, running=[fresh])
    asyncio.run(maintenance._reconcile_async())
    repo.fail_job.assert_not_awaited()


def test_reconcile_uses_per_job_max_running_seconds(monkeypatch):
    stale = _running_record(age_seconds=500, job_type="long_job")

    class _LongJob(_FakeJob):
        max_running_seconds = 300

    repo = _wire(monkeypatch, running=[stale], job_cls=_LongJob)
    asyncio.run(maintenance._reconcile_async())
    repo.fail_job.assert_awaited_once()


def test_reconcile_skips_job_when_max_running_seconds_disabled(monkeypatch):
    stale = _running_record(age_seconds=10_000, job_type="no_reconcile")

    class _NoReconcileJob(_FakeJob):
        max_running_seconds = 0

    repo = _wire(monkeypatch, running=[stale], job_cls=_NoReconcileJob)
    asyncio.run(maintenance._reconcile_async())
    repo.fail_job.assert_not_awaited()
