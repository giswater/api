"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Literal

from app.mcp.client import TenantApi
from app.mcp.registry import tool
from app.mcp.shaping import feature_rows, one_row, unwrap
from app.schemas.features.feature_models import FeatureType

_FEATURE_PATH = {
    "node": "nodes",
    "arc": "arcs",
    "link": "links",
    "connec": "connecs",
    "gully": "gullies",
}

_LIMIT = 50


def _drop_none(values: dict) -> dict:
    return {k: v for k, v in values.items() if v is not None}


@tool(feature="api_features", read_only=True)
async def find_features(
    api: TenantApi,
    schema: str,
    feature_type: FeatureType,
    expl_id: int | None = None,
    sector_id: int | None = None,
    dma_id: int | None = None,
    presszone_id: str | None = None,
    dqa_id: int | None = None,
    state: int | None = None,
    sys_type: list[str] | None = None,
    code: str | None = None,
    node_type: list[str] | None = None,
    nodecat_id: list[str] | None = None,
    arc_type: list[str] | None = None,
    arccat_id: list[str] | None = None,
    cat_matcat_id: str | None = None,
    cat_dnom: str | None = None,
    connec_type: list[str] | None = None,
    connecat_id: list[str] | None = None,
    customer_code: str | None = None,
    gully_type: list[str] | None = None,
    gratecat_id: list[str] | None = None,
    link_type: list[str] | None = None,
    x1: float | None = None,
    y1: float | None = None,
    x2: float | None = None,
    y2: float | None = None,
    order_by: str | None = None,
    order_type: Literal["ASC", "DESC"] | None = None,
    limit: int = _LIMIT,
) -> dict:
    """Find network features (nodes, arcs, links, connecs, gullies).

    Use typed filters (sys_type, dma_id, state, code, …) and an optional bbox
    in the project CRS (x1,y1,x2,y2). Default limit 50, max 500.
    """
    limit = min(max(limit, 1), 500)
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
    if None not in (x1, y1, x2, y2):
        params["coordinates"] = json.dumps({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    raw = await api.get(path, schema=schema, params=params)
    return feature_rows(raw, limit=limit)


@tool(feature="api_features", read_only=True)
async def get_feature(api: TenantApi, schema: str, feature_type: FeatureType, feature_id: str) -> dict:
    """Get one feature row by type and id (plain attributes, not a QGIS form)."""
    path = f"/features/{_FEATURE_PATH[feature_type]}/{feature_id}"
    return one_row(await api.get(path, schema=schema))


@tool(feature="api_basic", read_only=True)
async def search_features(api: TenantApi, schema: str, text: str) -> dict:
    """Free-text search across features. Returns flattened hits (section, table, id, label)."""
    raw = await api.get("/basic/getsearch", schema=schema, params={"searchText": text})
    data = unwrap(raw)
    items = []
    for section in data.get("searchResults") or []:
        for value in section.get("values") or []:
            items.append(
                {
                    "section": section.get("section") or section.get("alias"),
                    "table": section.get("tableName"),
                    "id": value.get("value") or value.get("key"),
                    "label": value.get("displayName") or value.get("value"),
                }
            )
    return {"items": items, "count": len(items)}
