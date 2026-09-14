"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from app.mcp.client import TenantApi
from app.mcp.registry import tool
from app.mcp.shaping import fc_summary, list_rows, unwrap

MincutState = Literal[0, 1, 2, 3, 4, 5]

_FC_KEYS = {
    "init": ("mincutInit", None),
    "proposed_valve": ("mincutProposedValve", "node_id"),
    "unaccess_valve": ("mincutUnaccessValve", "node_id"),
    "changestatus_valve": ("mincutChangestatusValve", "node_id"),
    "not_proposed_valve": ("mincutNotProposedValve", "node_id"),
    "node": ("mincutNode", "node_id"),
    "connec": ("mincutConnec", "connec_id"),
    "arc": ("mincutArc", "arc_id"),
}


def _filter_fields(**fields: Any) -> dict | None:
    payload = {}
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = {"value": value, "filterSign": "="}
    if not payload:
        return None
    return {"filterFields": json.dumps(payload)}


def _summarise_mincut(data: dict, include_geometry: bool) -> dict:
    geom = data.get("geometry") or {}
    bbox = None
    if isinstance(geom, dict):
        box = geom.get("bbox") or {}
        if box:
            bbox = [box.get("x1"), box.get("y1"), box.get("x2"), box.get("y2")]
        elif "x" in geom and "y" in geom:
            bbox = [geom.get("x"), geom.get("y"), geom.get("x"), geom.get("y")]
    categories = {name: fc_summary(data.get(key), id_key) for name, (key, id_key) in _FC_KEYS.items()}
    result = {
        "mincut_id": data.get("mincutId"),
        "state": data.get("mincutState"),
        "bbox": bbox,
        "categories": categories,
    }
    info = data.get("info")
    if info:
        result["info"] = info
    if include_geometry:
        result["geometry"] = {name: data.get(key) for name, (key, _) in _FC_KEYS.items()}
    return result


@tool(feature="api_mincut", read_only=True)
async def list_mincuts(
    api: TenantApi,
    schema: str,
    state: MincutState | None = None,
    exploitation: int | None = None,
    limit: int = 50,
) -> dict:
    """List mincuts, most recent first. State: 0 planified, 1 in progress, 2 finished, 3 canceled, 4 on planning, 5 conflict."""
    limit = min(max(limit, 1), 500)
    raw = await api.get(
        "/om/mincuts",
        schema=schema,
        params=_filter_fields(mincut_state=state, expl_id=exploitation),
    )
    return list_rows(raw, limit=limit)


@tool(feature="api_mincut", read_only=True)
async def get_mincut(api: TenantApi, schema: str, mincut_id: int, include_geometry: bool = False) -> dict:
    """Mincut summary: state, bbox, and counts/ids per valve category and affected features."""
    raw = await api.get(f"/om/mincuts/{mincut_id}", schema=schema)
    return _summarise_mincut(unwrap(raw), include_geometry)


@tool(feature="api_mincut", read_only=True)
async def list_mincut_valves(api: TenantApi, schema: str, mincut_id: int, limit: int = 50) -> dict:
    """Valves associated with a mincut."""
    limit = min(max(limit, 1), 500)
    raw = await api.get(f"/om/mincuts/{mincut_id}/valves", schema=schema)
    return list_rows(raw, limit=limit)


@tool(feature="api_mincut", idempotent=False)
async def create_mincut(
    api: TenantApi,
    schema: str,
    x: float,
    y: float,
    epsg: int,
    mincut_type: Literal["Demo", "Test", "Real"] = "Demo",
    anl_cause: Literal["Accidental", "Planified"] = "Accidental",
    anl_descript: str | None = None,
) -> dict:
    """Create an unplanned mincut at project-CRS coordinates (not WGS84). Not idempotent — retrying creates a duplicate."""
    body = {
        "coordinates": {"xcoord": x, "ycoord": y, "epsg": epsg, "zoomRatio": 1000},
        "plan": {
            "mincut_type": mincut_type,
            "anl_cause": anl_cause,
            "anl_descript": anl_descript,
        },
        "use_psectors": False,
    }
    raw = await api.post("/om/mincuts", schema=schema, json=body)
    return _summarise_mincut(unwrap(raw), include_geometry=False)


@tool(feature="api_mincut")
async def update_mincut(
    api: TenantApi,
    schema: str,
    mincut_id: int,
    mincut_type: Literal["Demo", "Test", "Real"] | None = None,
    anl_descript: str | None = None,
    exec_descript: str | None = None,
) -> dict:
    """Update plan or execution fields of an existing mincut."""
    body: dict[str, Any] = {"use_psectors": False}
    plan = {k: v for k, v in {"mincut_type": mincut_type, "anl_descript": anl_descript}.items() if v is not None}
    exec_ = {k: v for k, v in {"exec_descript": exec_descript}.items() if v is not None}
    if plan:
        body["plan"] = plan
    if exec_:
        body["exec"] = exec_
    raw = await api.patch(f"/om/mincuts/{mincut_id}", schema=schema, json=body)
    return unwrap(raw)


@tool(feature="api_mincut", idempotent=False)
async def set_mincut_valve(
    api: TenantApi,
    schema: str,
    mincut_id: int,
    valve_id: int,
    change: Literal["status", "unaccess"],
) -> dict:
    """Toggle a mincut valve. This is a TOGGLE, not a setter: calling twice restores the original state. Do not retry after a timeout."""
    path = f"/om/mincuts/{mincut_id}/valves/{valve_id}/toggle-{change}"
    raw = await api.post(path, schema=schema, json={"use_psectors": False})
    return unwrap(raw)


@tool(feature="api_mincut", destructive=True)
async def set_mincut_state(
    api: TenantApi,
    schema: str,
    mincut_id: int,
    action: Literal["start", "end", "cancel"],
    shutoff_required: bool = True,
) -> dict:
    """Change mincut lifecycle. Starting a mincut interrupts water supply to customers."""
    path = f"/om/mincuts/{mincut_id}/{action}"
    body: dict[str, Any] = {}
    if action == "end":
        body["shutoff_required"] = shutoff_required
    raw = await api.post(path, schema=schema, json=body or None)
    return unwrap(raw)


@tool(feature="api_mincut", destructive=True)
async def delete_mincut(api: TenantApi, schema: str, mincut_id: int) -> dict:
    """Permanently delete a mincut record."""
    return unwrap(await api.delete(f"/om/mincuts/{mincut_id}", schema=schema))
