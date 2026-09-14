"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

from app.mcp.client import TenantApi
from app.mcp.registry import SchemaName, tool
from app.mcp.shaping import compact_row, unwrap


class HydrometerItem(BaseModel):
    """One hydrometer row. ``code`` is required; extra CRM fields are allowed."""

    model_config = ConfigDict(extra="allow")

    code: str = Field(..., description="Hydrometer code")


@tool(feature="api_crm", read_only=True)
async def list_hydrometers(
    api: TenantApi,
    schema: SchemaName,
    code: Annotated[str | None, Field(description="Filter by hydrometer code")] = None,
    connec_id: Annotated[int | None, Field(description="Filter by connec id")] = None,
    dma_id: Annotated[int | None, Field(description="Filter by DMA id")] = None,
    limit: Annotated[int, Field(description="Max rows requested from the API (1–500)")] = 100,
    compact: Annotated[bool, Field(description="Drop nulls and QGIS style fields")] = True,
) -> dict:
    """List hydrometers, optionally filtered by code, connec_id or dma_id."""
    limit = min(max(limit, 1), 500)
    params = {
        k: v for k, v in {"code": code, "connecId": connec_id, "dmaId": dma_id, "limit": limit}.items() if v is not None
    }
    raw = await api.get("/crm/hydrometers", schema=schema, params=params)
    data = unwrap(raw)
    items = list(data.get("hydrometers") or [])
    if compact:
        items = [compact_row(item) for item in items]
    count = data.get("count", len(items))
    truncated = isinstance(count, int) and count > len(items)
    return {"items": items, "count": count, "truncated": truncated}


@tool(feature="api_crm", destructive=True)
async def manage_hydrometers(
    api: TenantApi,
    schema: SchemaName,
    action: Annotated[Literal["create", "update", "delete"], Field(description="create / update / delete")],
    hydrometers: Annotated[list[HydrometerItem], Field(description="Rows; each must include code")],
) -> dict:
    """Create, update or delete hydrometers.

    Each item needs ``code``. create/update send the row fields; delete uses ``code`` only.
    Full-table replace is not available.
    """
    if not hydrometers:
        raise ToolError("hydrometers must be a non-empty list")
    payload = []
    for item in hydrometers:
        if isinstance(item, HydrometerItem):
            payload.append(item.model_dump(exclude_none=True))
        elif isinstance(item, dict):
            payload.append(item)
        else:
            payload.append(item.model_dump(exclude_none=True))
    if action == "create":
        raw = await api.post("/crm/hydrometers", schema=schema, json=payload)
    elif action == "update":
        raw = await api.patch("/crm/hydrometers", schema=schema, json=payload)
    else:
        codes = [str(item.code) for item in hydrometers if item.code is not None]
        if not codes:
            raise ToolError("delete requires hydrometer code(s)")
        if len(codes) == 1:
            raw = await api.delete(f"/crm/hydrometers/{codes[0]}", schema=schema)
        else:
            raw = await api.delete("/crm/hydrometers", schema=schema, json=codes)
    return unwrap(raw)
