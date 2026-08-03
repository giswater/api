"""Tests for the Celery job execution task (_execute_job_async)."""

import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.jobs.exceptions import UnknownJobTypeError
from app.jobs.models import JobRecord, JobStatus
from app.tasks import jobs as jobs_task


def _record(*, status: JobStatus, job_type: str = "test_job") -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        id=uuid4(),
        type=job_type,
        status=status,
        tenant_id="test",
        schema_name="public",
        payload={"key": "value"},
        result=None,
        error=None,
        side_effects={},
        progress={},
        created_at=now,
        started_at=now if status != JobStatus.CREATED else None,
        finished_at=None,
        created_by=None,
        user_name=None,
    )


def _make_job_class(*, fail: bool = False):
    class _FakeJobClass:
        requires_auth = False
        _fail = fail
        ran = False
        repaired = False

        async def run(self, ctx, payload, side_effects):
            type(self).ran = True
            if type(self)._fail:
                raise RuntimeError("boom")
            return {"ok": True}

        async def repair(self, ctx, payload, side_effects):
            type(self).repaired = True

    return _FakeJobClass


def _wire(monkeypatch, *, record, mark_running_result, job_cls):
    tenant = SimpleNamespace(id="test", db_manager=object(), api_logger=logging.getLogger("test"))
    monkeypatch.setattr(jobs_task, "get_tenant", AsyncMock(return_value=tenant))

    repo = MagicMock()
    repo.get_job = AsyncMock(return_value=record)
    repo.mark_running = AsyncMock(return_value=mark_running_result)
    repo.finish_job = AsyncMock()
    repo.fail_job = AsyncMock()
    repo.update_side_effects = AsyncMock()
    repo.update_progress = AsyncMock()
    monkeypatch.setattr(jobs_task, "JobRepository", lambda *_a, **_k: repo)

    monkeypatch.setattr(jobs_task, "get_job_class", lambda _t: job_cls)
    monkeypatch.setattr(jobs_task, "job_context_from_tenant", lambda *_a, **_k: object())
    monkeypatch.setattr(jobs_task, "get_worker_token", AsyncMock(return_value="tok"))
    return repo


def test_execute_skips_when_job_not_found(monkeypatch):
    repo = _wire(monkeypatch, record=None, mark_running_result=None, job_cls=_make_job_class())
    asyncio.run(jobs_task._execute_job_async("test", str(uuid4())))
    repo.mark_running.assert_not_awaited()


def test_execute_skips_when_already_terminal(monkeypatch):
    record = _record(status=JobStatus.FINISHED)
    repo = _wire(monkeypatch, record=record, mark_running_result=None, job_cls=_make_job_class())
    asyncio.run(jobs_task._execute_job_async("test", str(record.id)))
    repo.mark_running.assert_not_awaited()


def test_execute_skips_when_claim_fails(monkeypatch):
    record = _record(status=JobStatus.CREATED)
    job_cls = _make_job_class()
    repo = _wire(monkeypatch, record=record, mark_running_result=None, job_cls=job_cls)
    asyncio.run(jobs_task._execute_job_async("test", str(record.id)))
    assert job_cls.ran is False
    repo.finish_job.assert_not_awaited()
    repo.fail_job.assert_not_awaited()


def test_execute_success_finishes_job(monkeypatch):
    record = _record(status=JobStatus.CREATED)
    running = _record(status=JobStatus.RUNNING, job_type=record.type)
    job_cls = _make_job_class()
    repo = _wire(monkeypatch, record=record, mark_running_result=running, job_cls=job_cls)
    asyncio.run(jobs_task._execute_job_async("test", str(record.id)))
    assert job_cls.ran is True
    repo.finish_job.assert_awaited_once()
    args = repo.finish_job.await_args.args
    assert args[1] == {"ok": True}
    repo.fail_job.assert_not_awaited()


def test_execute_failure_repairs_and_fails(monkeypatch):
    record = _record(status=JobStatus.CREATED)
    running = _record(status=JobStatus.RUNNING, job_type=record.type)
    job_cls = _make_job_class(fail=True)
    repo = _wire(monkeypatch, record=record, mark_running_result=running, job_cls=job_cls)
    asyncio.run(jobs_task._execute_job_async("test", str(record.id)))
    assert job_cls.repaired is True
    repo.fail_job.assert_awaited_once()
    repo.finish_job.assert_not_awaited()


def test_execute_unknown_job_type_fails_instead_of_staying_running(monkeypatch):
    record = _record(status=JobStatus.CREATED, job_type="missing.job")
    running = _record(status=JobStatus.RUNNING, job_type=record.type)
    repo = _wire(monkeypatch, record=record, mark_running_result=running, job_cls=_make_job_class())
    monkeypatch.setattr(
        jobs_task,
        "get_job_class",
        lambda _job_type: (_ for _ in ()).throw(
            UnknownJobTypeError("No handler registered for job type 'missing.job'")
        ),
    )
    asyncio.run(jobs_task._execute_job_async("test", str(record.id)))
    repo.fail_job.assert_awaited_once_with(record.id, "No handler registered for job type 'missing.job'")
    repo.finish_job.assert_not_awaited()
