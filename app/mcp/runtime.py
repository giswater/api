"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.session import _basic, get_current_user
from app.core.config import global_settings
from app.mcp.server import build_tenant_mcp
from app.tenancy.registry import Tenant

logger = logging.getLogger(__name__)

_root_app: ASGIApp | None = None


def configure(*, root_app: ASGIApp) -> None:
    global _root_app
    _root_app = root_app


class TenantMcp:
    def __init__(self, app: ASGIApp, api: Any | None = None):
        self.app = app
        self.api = api
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        ready = asyncio.Event()
        self._task = asyncio.create_task(self._run(ready))

        def _on_done(task: asyncio.Task) -> None:
            if not ready.is_set():
                ready.set()

        self._task.add_done_callback(_on_done)
        await ready.wait()
        if self._task.done() and not self._task.cancelled():
            exc = self._task.exception()
            if exc is not None:
                raise exc

    async def _run(self, ready: asyncio.Event) -> None:
        # FastMCP's session manager uses an anyio task group that must be entered
        # and exited in the same task. Do not fold this into an AsyncExitStack on
        # the caller — the lifespan context has to live on this dedicated task.
        lifespan = getattr(self.app, "router", None)
        ctx = getattr(lifespan, "lifespan_context", None) if lifespan is not None else None
        if ctx is None:
            ctx = getattr(self.app, "lifespan", None)
        if ctx is None:
            ready.set()
            await self._stop.wait()
            return
        async with ctx(self.app):
            ready.set()
            await self._stop.wait()

    async def aclose(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except Exception as exc:
                logger.warning("MCP lifespan task failed: %s", exc)
            self._task = None
        if self.api is not None:
            try:
                await self.api.aclose()
            except Exception as exc:
                logger.warning("MCP httpx client close failed: %s", exc)
            self.api = None


async def get_or_create(tenant: Tenant | None) -> TenantMcp | None:
    if tenant is None or not global_settings.mcp_enabled or not tenant.settings.api_mcp:
        return None
    if tenant.mcp is not None:
        return tenant.mcp
    if _root_app is None:
        logger.error("MCP runtime not configured")
        return None
    async with tenant.mcp_lock:
        if tenant.mcp is not None:
            return tenant.mcp
        mcp, api = build_tenant_mcp(tenant, _root_app)
        http_app = mcp.http_app(path="/", stateless_http=True)
        entry = TenantMcp(http_app, api=api)
        try:
            await entry.start()
        except Exception:
            await entry.aclose()
            raise
        tenant.mcp = entry
        return entry


class _ASGIPassthrough(Response):
    """Starlette Response that forwards the request to an ASGI app at ``/``."""

    def __init__(self, app: ASGIApp):
        super().__init__(content=b"")
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app({**scope, "path": "/", "raw_path": b"/"}, receive, send)


async def _authenticate(scope: Scope) -> JSONResponse | None:
    req = Request(scope)
    try:
        await get_current_user(req, await _basic(req))
    except HTTPException as exc:
        headers = dict(exc.headers) if exc.headers else None
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
    return None


async def _resolve_mcp(scope: Scope) -> TenantMcp | JSONResponse:
    tenant = (scope.get("state") or {}).get("tenant")
    entry = await get_or_create(tenant) if tenant else None
    if entry is None:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    denied = await _authenticate(scope)
    if denied is not None:
        return denied
    return entry


async def mcp_dispatch(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1000})
        return
    resolved = await _resolve_mcp(scope)
    if isinstance(resolved, JSONResponse):
        await resolved(scope, receive, send)
        return
    await resolved.app({**scope, "path": "/", "raw_path": b"/"}, receive, send)


async def mcp_http_endpoint(request: Request):
    """FastAPI route handler for ``/mcp`` without a trailing slash."""
    resolved = await _resolve_mcp(request.scope)
    if isinstance(resolved, JSONResponse):
        return resolved
    return _ASGIPassthrough(resolved.app)
