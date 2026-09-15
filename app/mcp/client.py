"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from starlette.types import ASGIApp

from app.core.config import global_settings
from app.core.constants import TENANT_PREFIX
from app.mcp.registry import CURRENT_MCP_TOOL, ToolSpec, spec_by_name
from app.mcp.shaping import failed_text
from app.tenancy.registry import Tenant
from app.utils.version import db_version_at_least

_FORWARD = ("authorization", "x-device", "x-lang")
_SCHEMA_TTL = 300.0


def refuse_incompatible(meta: dict, spec: ToolSpec | None) -> None:
    """Raise ToolError if the schema version or project type cannot run this tool."""
    schema = meta.get("schema") or "unknown"
    giswater = meta.get("giswater")
    min_v = global_settings.giswater_db_min_version
    version = str(giswater) if giswater is not None else None
    if not db_version_at_least(version, min_v):
        raise ToolError(f"Schema {schema} is Giswater {giswater or 'unknown'}; MCP requires {min_v} or later.")
    if spec is None or not spec.project_types:
        return
    project_type = (meta.get("project_type") or "").upper()
    if project_type not in spec.project_types:
        allowed = "/".join(sorted(spec.project_types))
        raise ToolError(f"{spec.fn.__name__} is {allowed}-only; schema {schema} is {project_type or 'unknown'}.")


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
        self._schema_cache: list[dict] | None = None
        self._schema_cache_at: float = 0.0

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

    async def _schemas(self, *, refresh: bool = False) -> list[dict]:
        now = time.monotonic()
        if not refresh and self._schema_cache is not None and (now - self._schema_cache_at) < _SCHEMA_TTL:
            return self._schema_cache
        resp = await self._client.get("/schemas")
        data = resp.json()
        self._schema_cache = list(data.get("schemas") or [])
        self._schema_cache_at = now
        return self._schema_cache

    async def schema_meta(self, schema: str) -> dict:
        schemas = await self._schemas()
        for item in schemas:
            if item.get("schema") == schema:
                return item
        schemas = await self._schemas(refresh=True)
        for item in schemas:
            if item.get("schema") == schema:
                return item
        names = [item["schema"] for item in schemas if item.get("schema")]
        listed = ", ".join(names) if names else "(none found)"
        raise ToolError(f"Unknown or missing schema. Valid schemas: {listed}")

    async def resolve_epsg(self, schema: str, epsg: int | None) -> int:
        project = (await self.schema_meta(schema)).get("epsg")
        if project is None:
            raise ToolError(f"Schema {schema} has no epsg")
        project = int(project)
        if epsg is None:
            return project
        if int(epsg) != project:
            raise ToolError(
                f"epsg {epsg} does not match schema {schema} ({project}). Reproject coordinates to the project CRS first."
            )
        return project

    async def _valid_schema_names(self) -> list[str]:
        try:
            return [item["schema"] for item in await self._schemas() if item.get("schema")]
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

    async def _preflight(self, schema: str) -> None:
        refuse_incompatible(await self.schema_meta(schema), spec_by_name(CURRENT_MCP_TOOL.get()))

    async def _send(self, method: str, path: str, *, schema: str | None, params=None, json=None) -> dict:
        if schema is not None:
            await self._preflight(schema)
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
