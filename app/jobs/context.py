"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.tenancy.registry import Tenant

if TYPE_CHECKING:
    from app.jobs.progress import JobProgressReporter


@dataclass(frozen=True)
class JobContext:
    tenant: Tenant
    bearer_token: str | None
    logger: logging.Logger
    progress: JobProgressReporter | None = None


def job_context_from_tenant(
    tenant: Tenant,
    *,
    bearer_token: str | None = None,
    logger: logging.Logger | None = None,
    progress: JobProgressReporter | None = None,
) -> JobContext:
    return JobContext(
        tenant=tenant,
        bearer_token=bearer_token,
        logger=logger or tenant.api_logger,
        progress=progress,
    )
