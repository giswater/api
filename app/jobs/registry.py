"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from typing import Type

from app.jobs.base import BaseJob
from app.jobs.exceptions import UnknownJobTypeError

_REGISTRY: dict[str, Type[BaseJob]] = {}


def register_job(job_cls: Type[BaseJob]) -> Type[BaseJob]:
    """Register a job subclass. Use as decorator or call directly."""
    if not job_cls.job_type:
        raise ValueError(f"{job_cls.__name__} must define job_type")
    _REGISTRY[job_cls.job_type] = job_cls
    return job_cls


def get_job_class(job_type: str) -> Type[BaseJob]:
    try:
        return _REGISTRY[job_type]
    except KeyError as exc:
        raise UnknownJobTypeError(f"No handler registered for job type '{job_type}'") from exc


def registered_job_types() -> list[str]:
    return sorted(_REGISTRY.keys())
