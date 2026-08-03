"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, TypeVar

from app.core.config import global_settings
from app.tenancy.registry import Tenant, TenantRegistry

logger = logging.getLogger(__name__)

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_registry: TenantRegistry | None = None


def init_worker() -> None:
    global _loop, _registry

    from app.jobs.types import load_job_types

    load_job_types()

    if _loop is None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

    registry = TenantRegistry(Path(global_settings.tenants_dir).resolve())
    summary = _loop.run_until_complete(registry.load_all())
    _registry = registry
    logger.info("Celery worker loaded tenants: %s (errors=%s)", registry.ids(), summary.get("errors"))


def shutdown_worker() -> None:
    global _loop, _registry
    if _registry is not None and _loop is not None:
        try:
            _loop.run_until_complete(_registry.close_all())
        except Exception:
            logger.exception("Error closing tenant registry on worker shutdown")
    if _loop is not None:
        try:
            _loop.close()
        except Exception:
            logger.exception("Error closing worker event loop")
    _loop = None
    _registry = None


def run_async(coro: Awaitable[T]) -> T:
    if _loop is not None:
        return _loop.run_until_complete(coro)
    return asyncio.run(coro)  # type: ignore[arg-type]


def get_registry() -> TenantRegistry:
    if _registry is None:
        raise RuntimeError("Tenant registry not initialized in this worker process")
    return _registry


async def get_tenant(tenant_id: str) -> Tenant:
    registry = get_registry()
    tenant = registry.get(tenant_id)
    if tenant is None:
        try:
            tenant = await registry.reload_one(tenant_id)
        except Exception as exc:
            raise RuntimeError(f"Tenant '{tenant_id}' not available in worker: {exc}") from exc
    return tenant


def iter_tenants() -> list[Any]:
    return get_registry().all()
