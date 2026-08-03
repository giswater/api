"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.jobs.context import JobContext


class BaseJob(ABC):
    """Each job type subclasses this and implements run() + repair()."""

    job_type: ClassVar[str]
    requires_auth: ClassVar[bool] = False
    # Max seconds in ``running`` before reconcile marks the job failed. ``None`` uses
    # ``JOBS_STALE_AFTER_SECONDS``. Set to ``0`` to disable stale reconciliation.
    max_running_seconds: ClassVar[int | None] = None

    @abstractmethod
    async def run(self, ctx: JobContext, payload: dict[str, Any], side_effects: dict[str, Any]) -> dict[str, Any]:
        """Execute job logic. May mutate side_effects for repair(). Returns result dict."""

    @abstractmethod
    async def repair(self, ctx: JobContext, payload: dict[str, Any], side_effects: dict[str, Any]) -> None:
        """Revert partial changes after failure or worker restart."""
