"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import SchemaName, tool
from app.mcp.shaping import feature_rows, fields_to_dict, one_row, unwrap
from app.schemas.features.feature_models import FeatureType

_FEATURE_PATH = {
    "node": "nodes",
    "arc": "arcs",
    "link": "links",
    "connec": "connecs",
    "gully": "gullies",
}

_LIMIT = 50

_SECTION_KEYS = ("gully", "connec", "link", "arc", "node")


def _drop_none(values: dict) -> dict:
    return {k: v for k, v in values.items() if v is not None}


def _map_search_section(section: str | None) -> str | None:
    if not section:
        return None
    lowered = section.lower()
    for key in _SECTION_KEYS:
        if key in lowered:
            return key
    return section


@tool(feature="api_features", read_only=True)
async def find_features(
    api: TenantApi,
    schema: SchemaName,
    feature_type: Annotated[FeatureType, Field(description="Feature class: node, arc, link, connec, or gully")],
    expl_id: Annotated[int | None, Field(description="Exploitation id")] = None,
    sector_id: Annotated[int | None, Field(description="Sector id")] = None,
    dma_id: Annotated[int | None, Field(description="DMA id")] = None,
    presszone_id: Annotated[str | None, Field(description="Pressure zone id")] = None,
    dqa_id: Annotated[int | None, Field(description="DQA id")] = None,
    state: Annotated[int | None, Field(description="Feature state (0 obsolete, 1 operative, 2 planified)")] = None,
    sys_type: Annotated[list[str] | None, Field(description="System types, e.g. VALVE, JUNCTION")] = None,
    code: Annotated[str | None, Field(description="Feature code")] = None,
    node_type: Annotated[list[str] | None, Field(description="Node type catalog values")] = None,
    nodecat_id: Annotated[list[str] | None, Field(description="Node catalog ids")] = None,
    arc_type: Annotated[list[str] | None, Field(description="Arc type catalog values")] = None,
    arccat_id: Annotated[list[str] | None, Field(description="Arc catalog ids")] = None,
    cat_matcat_id: Annotated[str | None, Field(description="Material catalog id")] = None,
    cat_dnom: Annotated[str | None, Field(description="Nominal diameter catalog value")] = None,
    connec_type: Annotated[list[str] | None, Field(description="Connec type catalog values")] = None,
    connecat_id: Annotated[list[str] | None, Field(description="Connec catalog ids")] = None,
    customer_code: Annotated[str | None, Field(description="Customer code (connecs)")] = None,
    gully_type: Annotated[list[str] | None, Field(description="Gully type catalog values (UD)")] = None,
    gratecat_id: Annotated[list[str] | None, Field(description="Grate catalog ids (UD)")] = None,
    link_type: Annotated[list[str] | None, Field(description="Link type catalog values")] = None,
    x1: Annotated[float | None, Field(description="Bbox min X in project CRS")] = None,
    y1: Annotated[float | None, Field(description="Bbox min Y in project CRS")] = None,
    x2: Annotated[float | None, Field(description="Bbox max X in project CRS")] = None,
    y2: Annotated[float | None, Field(description="Bbox max Y in project CRS")] = None,
    order_by: Annotated[str | None, Field(description="Column to sort by")] = None,
    order_type: Annotated[Literal["ASC", "DESC"] | None, Field(description="Sort direction")] = None,
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = _LIMIT,
    compact: Annotated[bool, Field(description="Drop nulls and QGIS style fields")] = True,
) -> dict:
    """Find network features (nodes, arcs, links, connecs, gullies).

    Use typed filters (sys_type, dma_id, state, code, …) and an optional bbox
    in the project CRS (x1,y1,x2,y2). Default limit 50, max 500.
    """
    limit = min(max(limit, 1), 500)
    bbox_vals = (x1, y1, x2, y2)
    if any(v is not None for v in bbox_vals) and any(v is None for v in bbox_vals):
        raise ToolError("Bbox requires all of x1, y1, x2, y2 (project CRS)")
    path = f"/features/{_FEATURE_PATH[feature_type]}"
    params = _drop_none(
        {
            "expl_id": expl_id,
            "sector_id": sector_id,
            "dma_id": dma_id,
            "presszone_id": presszone_id,
            "dqa_id": dqa_id,
            "state": state,
            "sys_type": sys_type,
            "code": code,
            "node_type": node_type,
            "nodecat_id": nodecat_id,
            "arc_type": arc_type,
            "arccat_id": arccat_id,
            "cat_matcat_id": cat_matcat_id,
            "cat_dnom": cat_dnom,
            "connec_type": connec_type,
            "connecat_id": connecat_id,
            "customer_code": customer_code,
            "gully_type": gully_type,
            "gratecat_id": gratecat_id,
            "link_type": link_type,
            "orderBy": order_by,
            "orderType": order_type,
            "limit": limit,
        }
    )
    if None not in bbox_vals:
        params["coordinates"] = json.dumps({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    raw = await api.get(path, schema=schema, params=params)
    return feature_rows(raw, limit=limit, compact=compact)


@tool(feature="api_features", read_only=True)
async def get_feature(
    api: TenantApi,
    schema: SchemaName,
    feature_type: Annotated[FeatureType, Field(description="Feature class: node, arc, link, connec, or gully")],
    feature_id: Annotated[str, Field(description="Feature id")],
    compact: Annotated[bool, Field(description="Drop nulls and QGIS style fields")] = True,
) -> dict:
    """Get one feature row by type and id (plain attributes, not a QGIS form)."""
    path = f"/features/{_FEATURE_PATH[feature_type]}/{feature_id}"
    return one_row(await api.get(path, schema=schema), compact=compact)


@tool(feature="api_basic", read_only=True)
async def search_features(
    api: TenantApi,
    schema: SchemaName,
    text: Annotated[str, Field(description="Free-text search string")],
    limit: Annotated[int, Field(description="Max hits to return (1–500)")] = _LIMIT,
) -> dict:
    """Free-text search across features. Returns flattened hits (section, table, id, label)."""
    limit = min(max(limit, 1), 500)
    raw = await api.get("/basic/getsearch", schema=schema, params={"searchText": text})
    data = unwrap(raw)
    items = []
    for section in data.get("searchResults") or []:
        mapped = _map_search_section(section.get("section") or section.get("alias"))
        for value in section.get("values") or []:
            items.append(
                {
                    "section": mapped,
                    "table": section.get("tableName"),
                    "id": value.get("value") or value.get("key"),
                    "label": value.get("displayName") or value.get("value"),
                }
            )
    truncated = len(items) > limit
    items = items[:limit]
    return {"items": items, "count": len(items), "truncated": truncated}


@tool(feature="api_basic", read_only=True)
async def get_feature_at_point(
    api: TenantApi,
    schema: SchemaName,
    x: Annotated[float, Field(description="X coordinate in the project CRS (not WGS84)")],
    y: Annotated[float, Field(description="Y coordinate in the project CRS (not WGS84)")],
    epsg: Annotated[int, Field(description="Project EPSG from list_schemas (not 4326)")],
    zoom_ratio: Annotated[float, Field(description="Map zoom ratio passed to the info function")] = 1000,
) -> dict:
    """Identify the network feature at project-CRS coordinates (not WGS84 lat/lon)."""
    raw = await api.get(
        "/basic/getinfofromcoordinates",
        schema=schema,
        params={"xcoord": x, "ycoord": y, "epsg": epsg, "zoomRatio": zoom_ratio},
    )
    data = unwrap(raw)
    body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
    feature = body.get("feature") or {}
    return {
        "feature_id": feature.get("id"),
        "feature_type": feature.get("featureType") or feature.get("childType"),
        "table": feature.get("tableName"),
        "fields": fields_to_dict(data.get("fields"), skip_hidden=True, drop_nulls=True),
    }
