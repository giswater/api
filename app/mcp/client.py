"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from starlette.types import ASGIApp

from app.core.config import global_settings
from app.core.constants import TENANT_PREFIX
from app.mcp.registry import CURRENT_MCP_TOOL
from app.mcp.shaping import failed_text
from app.tenancy.registry import Tenant

_FORWARD = ("authorization", "x-device", "x-lang")


class TenantApi:
    """In-process loopback client into the parent app for one tenant."""

    def __init__(self, tenant: Tenant, root_app: ASGIApp):
        self.tenant_id = tenant.id
        host = f"{tenant.id}.{global_settings.base_domain}" if global_settings.base_domain else "mcp.internal"
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=root_app),
            base_url=f"http://{host}{TENANT_PREFIX}",
            event_hooks={"request": [self._forward]},
            timeout=global_settings.mcp_timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _forward(self, request: httpx.Request) -> None:
        try:
            inbound = get_http_request()
        except Exception:
            inbound = None
        if inbound is None:
            return
        inbound_tenant = getattr(inbound.state, "tenant", None)
        if inbound_tenant is None or inbound_tenant.id != self.tenant_id:
            raise RuntimeError("MCP tenant mismatch")
        for header in _FORWARD:
            value = inbound.headers.get(header)
            if value:
                request.headers[header] = value
        request.headers.pop("cookie", None)
        tool_name = CURRENT_MCP_TOOL.get()
        if tool_name:
            request.headers["x-mcp-tool"] = tool_name

    def _params(self, schema: str | None, params: dict | None) -> dict:
        out = dict(params or {})
        if schema is not None:
            out.setdefault("schema", schema)
        return out

    async def _valid_schema_names(self) -> list[str]:
        try:
            resp = await self._client.get("/schemas")
            data = resp.json()
            return [item["schema"] for item in data.get("schemas") or [] if item.get("schema")]
        except Exception:
            return []

    async def _raise_http(self, resp: httpx.Response) -> None:
        try:
            payload = resp.json()
        except Exception:
            payload = {"detail": resp.text}
        text = _http_error_text(payload)
        if resp.status_code == 404 and "schema" in text.lower():
            names = await self._valid_schema_names()
            listed = ", ".join(names) if names else "(none found)"
            raise ToolError(f"Unknown or missing schema. Valid schemas: {listed}")
        raise ToolError(f"HTTP {resp.status_code}: {text}")

    async def _send(self, method: str, path: str, *, schema: str | None, params=None, json=None) -> dict:
        resp = await self._client.request(method, path, params=self._params(schema, params), json=json)
        if resp.status_code >= 400:
            await self._raise_http(resp)
        try:
            data = resp.json()
        except Exception as exc:
            raise ToolError(f"Non-JSON response from {path}") from exc
        if isinstance(data, dict) and data.get("status") == "Failed":
            raise ToolError(failed_text(data) or "API request failed")
        return data if isinstance(data, dict) else {"result": data}

    async def get(self, path: str, *, schema: str | None, params: dict | None = None) -> dict:
        return await self._send("GET", path, schema=schema, params=params)

    async def post(self, path: str, *, schema: str | None, json: Any = None, params: dict | None = None) -> dict:
        return await self._send("POST", path, schema=schema, params=params, json=json)

    async def patch(self, path: str, *, schema: str | None, json: Any = None, params: dict | None = None) -> dict:
        return await self._send("PATCH", path, schema=schema, params=params, json=json)

    async def put(self, path: str, *, schema: str | None, json: Any = None, params: dict | None = None) -> dict:
        return await self._send("PUT", path, schema=schema, params=params, json=json)

    async def delete(self, path: str, *, schema: str | None, json: Any = None, params: dict | None = None) -> dict:
        return await self._send("DELETE", path, schema=schema, params=params, json=json)


def _http_error_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return failed_text(detail) or str(detail)
    if detail is not None:
        return str(detail)
    return failed_text(payload) or str(payload)
