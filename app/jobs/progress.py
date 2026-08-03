"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

JOB_STEP_CONFIG: dict[str, dict[str, dict[str, Any]]] = {}


@dataclass
class JobProgressState:
    percentage: float = 0.0
    current_step: str = "init"
    step_label: str = ""
    step_current: int = 0
    step_total: int = 0
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "percentage": round(self.percentage, 1),
            "current_step": self.current_step,
            "step_label": self.step_label,
            "step_current": self.step_current,
            "step_total": self.step_total,
            "message": self.message,
        }


def calculate_percentage(
    job_type: str,
    *,
    current_step: str,
    step_current: int = 0,
    step_total: int = 0,
    completed_steps: set[str] | None = None,
) -> float:
    steps = JOB_STEP_CONFIG.get(job_type, {})
    total_weight = sum(c["weight"] for c in steps.values()) or 100
    completed_weight = 0.0
    completed_steps = completed_steps or set()

    for step_id, cfg in steps.items():
        weight = cfg["weight"]
        if step_id in completed_steps:
            completed_weight += weight
        elif step_id == current_step and step_total > 0:
            ratio = min(1.0, step_current / step_total)
            completed_weight += weight * ratio

    return min(100.0, (completed_weight / total_weight) * 100)


class ProgressRepository(Protocol):
    async def update_progress(self, job_id: UUID, progress: dict[str, Any]) -> None: ...


class JobProgressReporter:
    """Writes progress to the database with throttling."""

    def __init__(
        self,
        repo: ProgressRepository,
        job_id: UUID,
        job_type: str,
        *,
        min_interval_seconds: float = 1.0,
    ):
        self._repo = repo
        self._job_id = job_id
        self._job_type = job_type
        self._min_interval = min_interval_seconds
        self._last_flush = 0.0
        self._completed_steps: set[str] = set()
        self.state = JobProgressState()

    async def set_step(
        self,
        step: str,
        *,
        step_current: int = 0,
        step_total: int = 0,
        message: str | None = None,
        force: bool = False,
    ) -> None:
        cfg = JOB_STEP_CONFIG.get(self._job_type, {}).get(step, {})
        self.state.current_step = step
        self.state.step_label = cfg.get("label", step)
        self.state.step_current = step_current
        self.state.step_total = step_total
        self.state.message = message
        self.state.percentage = calculate_percentage(
            self._job_type,
            current_step=step,
            step_current=step_current,
            step_total=step_total,
            completed_steps=self._completed_steps,
        )
        await self._flush(force=force)

    async def complete_step(self, step: str, *, force: bool = True) -> None:
        self._completed_steps.add(step)
        self.state.percentage = calculate_percentage(
            self._job_type,
            current_step=self.state.current_step,
            step_current=self.state.step_current,
            step_total=self.state.step_total,
            completed_steps=self._completed_steps,
        )
        await self._flush(force=force)

    async def set_percentage(self, percentage: float, *, message: str | None = None, force: bool = False) -> None:
        self.state.percentage = min(100.0, max(0.0, percentage))
        if message is not None:
            self.state.message = message
        await self._flush(force=force)

    async def _flush(self, *, force: bool) -> None:
        now = time.monotonic()
        if not force and (now - self._last_flush) < self._min_interval:
            return
        self._last_flush = now
        await self._repo.update_progress(self._job_id, self.state.to_dict())

    def engine_callback(self, step: str) -> Callable[[int, str], None]:
        """Sync callback for long-running engines; schedules progress on the worker loop."""
        loop = asyncio.get_running_loop()

        def on_progress(engine_pct: int, message: str) -> None:
            asyncio.run_coroutine_threadsafe(
                self.set_step(
                    step,
                    step_current=engine_pct,
                    step_total=100,
                    message=message,
                ),
                loop,
            )

        return on_progress


def poll_interval_ms_for_progress(job_type: str, progress: dict[str, Any] | None, status: str) -> int | None:
    if status in ("finished", "failed"):
        return None
    if not progress:
        return None
    step = progress.get("current_step")
    cfg = JOB_STEP_CONFIG.get(job_type, {}).get(step or "", {})
    return cfg.get("poll_interval_ms")
