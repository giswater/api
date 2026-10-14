"""Tests for job poll interval hints."""

from datetime import datetime, timezone
from uuid import uuid4

from app.jobs.models import JobRecord, JobStatus
from app.jobs.poll_config import poll_interval_ms_for_job


def _record(*, status: JobStatus, job_type: str = "go2epa") -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        id=uuid4(),
        type=job_type,
        status=status,
        tenant_id="test",
        schema_name="public",
        payload={},
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


def test_poll_interval_none_when_cancelled():
    assert poll_interval_ms_for_job(_record(status=JobStatus.CANCELLED)) is None


def test_poll_interval_for_cancelling_matches_running():
    assert poll_interval_ms_for_job(_record(status=JobStatus.CANCELLING)) == 2000
