"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated, Any, Literal

from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import SchemaName, tool
from app.mcp.shaping import compact_row, feature_rows, unwrap

ZoneType = Literal[
    "dma",
    "macrodma",
    "sector",
    "macrosector",
    "presszone",
    "dqa",
    "macrodqa",
    "omzone",
    "macroomzone",
    "omunit",
]

_ZONE_PATH: dict[ZoneType, str] = {
    "dma": "/om/dmas",
    "macrodma": "/om/macrodmas",
    "sector": "/om/sectors",
    "macrosector": "/om/macrosectors",
    "presszone": "/om/presszones",
    "dqa": "/om/dqas",
    "macrodqa": "/om/macrodqas",
    "omzone": "/om/omzones",
    "macroomzone": "/om/macroomzones",
    "omunit": "/om/omunits",
}

_CONNEC_KEEP = {
    "connec_id",
    "code",
    "customer_code",
    "sys_type",
    "connec_type",
    "dma_id",
    "sector_id",
    "state",
    "expl_id",
    "cat_dnom",
}


def _first_list(data: dict) -> list:
    for value in data.values():
        if isinstance(value, list):
            return value
    return []


def _drop_geometry(items: list[Any]) -> list[Any]:
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append({k: v for k, v in item.items() if k.lower() not in {"geometry", "the_geom", "thegeom"}})
        else:
            out.append(item)
    return out


@tool(feature="api_mapzones", read_only=True)
async def list_mapzones(
    api: TenantApi,
    schema: SchemaName,
    zone_type: Annotated[ZoneType, Field(description="Mapzone class (dma, sector, presszone, dqa, omzone, …)")],
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = 50,
) -> dict:
    """List mapzones of one type (dma, sector, presszone, dqa, omzone, …). Geometry is omitted."""
    limit = min(max(limit, 1), 500)
    raw = await api.get(_ZONE_PATH[zone_type], schema=schema)
    data = unwrap(raw)
    items = _drop_geometry(_first_list(data))
    truncated = len(items) > limit
    items = items[:limit]
    return {"zone_type": zone_type, "items": items, "count": len(items), "truncated": truncated}


@tool(feature="api_mapzones", read_only=True)
async def get_dma_contents(
    api: TenantApi,
    schema: SchemaName,
    dma_id: Annotated[int, Field(description="DMA id")],
    content: Annotated[Literal["hydrometers", "connecs"], Field(description="hydrometers or connecs")],
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = 100,
) -> dict:
    """DMA contents: hydrometers or connecs (curated columns)."""
    limit = min(max(limit, 1), 500)
    if content == "connecs":
        raw = await api.get("/features/connecs", schema=schema, params={"dma_id": dma_id, "limit": limit})
        shaped = feature_rows(raw, limit=limit)
        items = []
        for item in shaped["items"]:
            if isinstance(item, dict):
                items.append({k: v for k, v in item.items() if k in _CONNEC_KEEP})
            else:
                items.append(item)
        return {
            "dma_id": dma_id,
            "content": content,
            "items": items,
            "count": len(items),
            "truncated": shaped["truncated"],
        }
    raw = await api.get(f"/om/dmas/{dma_id}/hydrometers", schema=schema)
    data = unwrap(raw)
    items = _first_list(data)
    truncated = len(items) > limit
    items = items[:limit]
    return {"dma_id": dma_id, "content": content, "items": items, "count": len(items), "truncated": truncated}


@tool(feature="api_water_balance", read_only=True)
async def get_water_balance(
    api: TenantApi,
    schema: SchemaName,
    dma_ids: Annotated[list[int] | None, Field(description="Optional DMA ids to filter")] = None,
) -> dict:
    """DMA boundary flow signs (in/out). Geometry is stripped; not volumetric KPIs."""
    params = {"dma_id": dma_ids} if dma_ids else None
    raw = await api.get("/om/waterbalance", schema=schema, params=params)
    data = unwrap(raw)
    items = []
    for row in data.get("waterbalance") or []:
        node = row.get("node") or {}
        items.append(
            compact_row(
                {
                    "node_id": row.get("node_id"),
                    "dma_id": row.get("dma_id"),
                    "flow_sign": row.get("flow_sign"),
                    "node_type": node.get("node_type"),
                }
            )
        )
    return {"items": items, "count": len(items)}
