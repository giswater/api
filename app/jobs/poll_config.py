"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from app.jobs.models import JobRecord, JobStatus

JOB_POLL_CONFIG: dict[str, dict[str, int]] = {"go2epa": {"created": 3000, "running": 2000}}

DEFAULT_POLL_MS: dict[str, int] = {"created": 5000, "running": 3000}


def poll_interval_ms_for_job(job: JobRecord) -> int | None:
    """Return suggested client poll interval, or None when polling should stop."""
    if job.status in (JobStatus.FINISHED, JobStatus.FAILED):
        return None
    type_config = JOB_POLL_CONFIG.get(job.type, {})
    status_key = job.status.value
    if status_key in type_config:
        return type_config[status_key]
    return DEFAULT_POLL_MS.get(status_key)
