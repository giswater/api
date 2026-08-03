"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class JobStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    FAILED = "failed"
    FINISHED = "finished"


TERMINAL_STATUSES = frozenset({JobStatus.FAILED, JobStatus.FINISHED})


@dataclass(frozen=True)
class JobRecord:
    id: UUID
    type: str
    status: JobStatus
    tenant_id: str
    schema_name: str | None
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    side_effects: dict[str, Any]
    progress: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_by: str | None
    user_name: str | None
