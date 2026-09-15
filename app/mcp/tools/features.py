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
from app.mcp.registry import DEFAULT_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import feature_rows, one_row, page_total, shape_feature, unwrap
from app.schemas.features.feature_models import FeatureType

_FEATURE_PATH = {
    "node": "nodes",
    "arc": "arcs",
    "link": "links",
    "connec": "connecs",
    "gully": "gullies",
}

_SHARED_FILTERS = frozenset(
    {
        "expl_id",
        "sector_id",
        "dma_id",
        "presszone_id",
        "dqa_id",
        "state",
        "sys_type",
        "code",
    }
)
_TYPE_FILTERS = {
    "node": frozenset({"node_type", "nodecat_id"}),
    "arc": frozenset({"arc_type", "arccat_id", "cat_matcat_id", "cat_dnom"}),
    "link": frozenset({"link_type"}),
    "connec": frozenset({"connec_type", "connecat_id", "customer_code"}),
    "gully": frozenset({"gully_type", "gratecat_id"}),
}

_FEATURE_TABLES = {
    "ve_node": "node",
    "ve_arc": "arc",
    "ve_connec": "connec",
    "ve_gully": "gully",
    "ve_link": "link",
}


def _drop_none(values: dict) -> dict:
    return {k: v for k, v in values.items() if v is not None}


def _reject_type_filters(feature_type: FeatureType, filters: dict) -> None:
    allowed = _SHARED_FILTERS | _TYPE_FILTERS[feature_type]
    extra = sorted(name for name, value in filters.items() if value is not None and name not in allowed)
    if extra:
        raise ToolError(f"{', '.join(extra)} not valid for feature_type={feature_type}")


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
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DEFAULT_LIMIT,
    fields: Annotated[
        Literal["id", "summary", "full"],
        Field(description="id = identifiers only; summary = 6–8 locator fields (default); full = compact row"),
    ] = "summary",
    count_only: Annotated[bool, Field(description="Return the exact match count without rows")] = False,
) -> dict:
    """Find network features by typed filters and optional bbox.

    Returns identifiers, coordinates and counts — not a full attribute dump.
    Use ``get_feature`` for one row's attributes. ``fields``: id | summary (default) | full.
    Shared filters (dma_id, sector_id, expl_id) are echoed once at the top level.
    """
    limit = clamp_limit(limit)
    typed = {
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
    }
    _reject_type_filters(feature_type, typed)
    bbox_vals = (x1, y1, x2, y2)
    if any(v is not None for v in bbox_vals) and any(v is None for v in bbox_vals):
        raise ToolError("Bbox requires all of x1, y1, x2, y2 (project CRS)")
    path = f"/features/{_FEATURE_PATH[feature_type]}"
    params = _drop_none({**typed, "orderBy": order_by, "orderType": order_type, "limit": limit})
    if None not in bbox_vals:
        params["coordinates"] = json.dumps({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    echoed = _drop_none({"dma_id": dma_id, "sector_id": sector_id, "expl_id": expl_id})

    async def _total() -> int:
        return page_total(await api.get(path, schema=schema, params={**params, "limit": 1}))

    if count_only:
        total = await _total()
        return {"items": [], "count": total, "total": total, "truncated": False, "filters": echoed}
    shaped = feature_rows(await api.get(path, schema=schema, params=params), limit=limit)
    items = [shape_feature(item, feature_type, fields) for item in shaped["items"]]
    total = await _total() if shaped["truncated"] else len(items)
    return {
        "items": items,
        "count": len(items),
        "truncated": shaped["truncated"],
        "total": total,
        "filters": echoed,
    }


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
async def search(
    api: TenantApi,
    schema: SchemaName,
    text: Annotated[str, Field(description="Free-text search string")],
    limit: Annotated[int, Field(description="Max hits to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """Free-text search across whatever the project configured as searchable.

    Hits may be network features, addresses, mincuts, workcats, or other entities.
    ``feature_type`` is set only for ``ve_node`` / ``ve_arc`` / ``ve_connec`` /
    ``ve_gully`` / ``ve_link`` rows; only those can be passed to ``get_feature``.
    """
    limit = clamp_limit(limit)
    raw = await api.get("/basic/getsearch", schema=schema, params={"searchText": text})
    data = unwrap(raw)
    items = []
    for section in data.get("searchResults") or []:
        table = section.get("tableName")
        feature_type = _FEATURE_TABLES.get(table) if isinstance(table, str) else None
        for value in section.get("values") or []:
            items.append(
                {
                    "section": section.get("section") or section.get("alias"),
                    "table": table,
                    "feature_type": feature_type,
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
    zoom_ratio: Annotated[
        float,
        Field(
            description=(
                "Snapping radius in CRS units. Determines which feature wins: "
                "Connec/Gully/Node > Link/Arc > Polygons. Default 1000."
            )
        ),
    ] = 1000,
) -> dict:
    """Identify the network feature at project-CRS coordinates (not WGS84 lat/lon).

    Resolves id and type at the click, then returns the same compact row as
    ``get_feature``. ``zoom_ratio`` is a snapping radius (default 1000).
    """
    raw = await api.get(
        "/basic/getinfofromcoordinates",
        schema=schema,
        params={"xcoord": x, "ycoord": y, "epsg": epsg, "zoomRatio": zoom_ratio},
    )
    body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
    feature = body.get("feature") or {}
    feature_id = feature.get("id")
    raw_type = feature.get("featureType") or feature.get("childType")
    feature_type = str(raw_type).lower() if raw_type else None
    header = {"feature_id": feature_id, "feature_type": feature_type, "table": feature.get("tableName")}
    if not feature_id or feature_type not in _FEATURE_PATH:
        return header
    row = one_row(await api.get(f"/features/{_FEATURE_PATH[feature_type]}/{feature_id}", schema=schema))
    return {**header, **row}
