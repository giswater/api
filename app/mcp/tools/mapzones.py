"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Any, Literal

from app.mcp.client import TenantApi
from app.mcp.registry import tool
from app.mcp.shaping import unwrap

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
async def list_mapzones(api: TenantApi, schema: str, zone_type: ZoneType) -> dict:
    """List mapzones of one type (dma, sector, presszone, dqa, omzone, …). Geometry is omitted."""
    raw = await api.get(_ZONE_PATH[zone_type], schema=schema)
    data = unwrap(raw)
    items = _drop_geometry(_first_list(data))
    return {"zone_type": zone_type, "items": items, "count": len(items)}


@tool(feature="api_mapzones", read_only=True)
async def get_dma_contents(
    api: TenantApi,
    schema: str,
    dma_id: int,
    content: Literal["hydrometers", "connecs", "parameters"],
    limit: int = 100,
) -> dict:
    """DMA contents: hydrometers, connecs (curated columns), or parameters."""
    limit = min(max(limit, 1), 500)
    raw = await api.get(f"/om/dmas/{dma_id}/{content}", schema=schema)
    data = unwrap(raw)
    items = _first_list(data)
    if content == "connecs":
        trimmed = []
        for item in items:
            if isinstance(item, dict):
                trimmed.append({k: v for k, v in item.items() if k in _CONNEC_KEEP})
            else:
                trimmed.append(item)
        items = trimmed
    truncated = len(items) > limit
    items = items[:limit]
    return {"dma_id": dma_id, "content": content, "items": items, "count": len(items), "truncated": truncated}


@tool(feature="api_water_balance", read_only=True)
async def get_water_balance(api: TenantApi, schema: str, dma_ids: list[int] | None = None) -> dict:
    """DMA water-balance numbers. Geometry (node/DMA/line GeoJSON) is stripped."""
    params = {"dma_id": dma_ids} if dma_ids else None
    raw = await api.get("/om/waterbalance", schema=schema, params=params)
    data = unwrap(raw)
    items = []
    for row in data.get("waterbalance") or []:
        node = row.get("node") or {}
        dma = row.get("dma") or {}
        items.append(
            {
                "node_id": row.get("node_id"),
                "dma_id": row.get("dma_id"),
                "flow_sign": row.get("flow_sign"),
                "node_type": node.get("node_type"),
                "dma_stylesheet": dma.get("dma_stylesheet"),
            }
        )
    return {"items": items, "count": len(items)}
