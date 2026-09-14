"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Any, Literal

from fastmcp.exceptions import ToolError

from app.mcp.client import TenantApi
from app.mcp.registry import tool
from app.mcp.shaping import unwrap


@tool(feature="api_crm", read_only=True)
async def list_hydrometers(
    api: TenantApi,
    schema: str,
    code: str | None = None,
    connec_id: int | None = None,
    dma_id: int | None = None,
    limit: int = 100,
) -> dict:
    """List hydrometers, optionally filtered by code, connec_id or dma_id."""
    limit = min(max(limit, 1), 500)
    params = {
        k: v for k, v in {"code": code, "connecId": connec_id, "dmaId": dma_id, "limit": limit}.items() if v is not None
    }
    raw = await api.get("/crm/hydrometers", schema=schema, params=params)
    data = unwrap(raw)
    items = list(data.get("hydrometers") or [])
    return {"items": items[:limit], "count": data.get("count", len(items)), "truncated": len(items) > limit}


@tool(feature="api_crm", destructive=True)
async def manage_hydrometers(
    api: TenantApi,
    schema: str,
    action: Literal["create", "update", "delete"],
    hydrometers: list[dict[str, Any]],
) -> dict:
    """Create, update or delete hydrometers. Each item needs ``code``. Full-table replace is not available."""
    if not hydrometers:
        raise ToolError("hydrometers must be a non-empty list")
    if action == "create":
        raw = await api.post("/crm/hydrometers", schema=schema, json=hydrometers)
    elif action == "update":
        raw = await api.patch("/crm/hydrometers", schema=schema, json=hydrometers)
    else:
        codes = [str(item.get("code")) for item in hydrometers if item.get("code") is not None]
        if not codes:
            raise ToolError("delete requires hydrometer code(s)")
        if len(codes) == 1:
            raw = await api.delete(f"/crm/hydrometers/{codes[0]}", schema=schema)
        else:
            raw = await api.delete("/crm/hydrometers", schema=schema, json=codes)
    return unwrap(raw)
