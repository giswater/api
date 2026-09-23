"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DEFAULT_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import DMA_ALIASES, compact_row, list_payload, unwrap

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

_ZONE_LIST_KEY: dict[ZoneType, str] = {
    "dma": "dmas",
    "macrodma": "macrodmas",
    "sector": "sectors",
    "macrosector": "macrosectors",
    "presszone": "presszones",
    "dqa": "dqas",
    "macrodqa": "macrodqas",
    "omzone": "omzones",
    "macroomzone": "macroomzones",
    "omunit": "omunits",
}

_WS_ONLY_ZONES = frozenset({"dma", "macrodma", "presszone", "dqa", "macrodqa"})


async def _reject_ws_only_zone(api: TenantApi, schema: str, zone_type: ZoneType) -> None:
    if zone_type not in _WS_ONLY_ZONES:
        return
    project_type = ((await api.schema_meta(schema)).get("project_type") or "").upper()
    if project_type != "WS":
        raise ToolError(
            f"list_mapzones(zone_type={zone_type!r}) is WS-only; schema {schema} is {project_type or 'unknown'}."
        )


@tool(feature="api_mapzones", read_only=True)
async def list_mapzones(
    api: TenantApi,
    schema: SchemaName,
    zone_type: Annotated[ZoneType, Field(description="Mapzone class (dma, sector, presszone, dqa, omzone, …)")],
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """List mapzones of one type (dma, sector, presszone, dqa, omzone, …). Geometry is omitted.

    dma / macrodma / presszone / dqa / macrodqa are WS-only.
    """
    limit = clamp_limit(limit)
    await _reject_ws_only_zone(api, schema, zone_type)
    data = unwrap(await api.get(_ZONE_PATH[zone_type], schema=schema))
    items = list(data.get(_ZONE_LIST_KEY[zone_type]) or [])
    aliases = DMA_ALIASES if zone_type == "dma" else None
    extra = {"zone_type": zone_type}
    return list_payload(items, limit=limit, total=len(items), extra=extra, aliases=aliases)


@tool(feature="api_water_balance", read_only=True, project_types={"WS"})
async def list_dma_boundary_nodes(
    api: TenantApi,
    schema: SchemaName,
    dma_ids: Annotated[list[int] | None, Field(description="Optional DMA ids to filter")] = None,
) -> dict:
    """DMA-boundary nodes and flow_sign (in/out). Not NRW or volumetric water balance."""
    params = {"dma_id": dma_ids} if dma_ids else None
    data = unwrap(await api.get("/om/waterbalance", schema=schema, params=params))
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
    return {"items": items, "count": len(items), "total": len(items), "truncated": False}
