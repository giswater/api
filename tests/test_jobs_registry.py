"""Tests for job type registry."""

from typing import Any

from app.jobs.base import BaseJob
from app.jobs.context import JobContext
from app.jobs.registry import get_job_class, register_job, registered_job_types


@register_job
class _SampleJob(BaseJob):
    job_type = "sample_job"

    async def run(self, ctx: JobContext, payload: dict[str, Any], side_effects: dict[str, Any]) -> dict[str, Any]:
        return {"done": True}

    async def repair(self, ctx: JobContext, payload: dict[str, Any], side_effects: dict[str, Any]) -> None:
        return None


def test_sample_job_is_registered():
    assert "sample_job" in registered_job_types()
    job_cls = get_job_class("sample_job")
    assert job_cls.job_type == "sample_job"
