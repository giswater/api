"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.jobs.models import JobStatus


class JobStatusResponse(BaseModel):
    job_id: UUID
    type: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    progress_percentage: float = 0.0
    current_step: str | None = None
    step_label: str | None = None
    step_current: int = 0
    step_total: int = 0
    message: str | None = None
    poll_interval_ms: int | None = None


class JobCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    poll_interval_ms: int | None = None


class JobResultResponse(BaseModel):
    job_id: UUID
    type: str
    status: JobStatus
    result: dict[str, Any] = Field(default_factory=dict)
