"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from app.core.config import global_settings
from app.jobs.exceptions import UnknownJobTypeError
from app.jobs.registry import get_job_class


def stale_after_seconds_for(job_type: str) -> int | None:
    """Return max running seconds before reconcile fails the job, or ``None`` to skip."""
    try:
        limit = getattr(get_job_class(job_type), "max_running_seconds", None)
    except UnknownJobTypeError:
        return global_settings.jobs_stale_after_seconds
    if limit is None:
        return global_settings.jobs_stale_after_seconds
    if limit <= 0:
        return None
    return limit
