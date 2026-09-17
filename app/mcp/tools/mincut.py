"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DEFAULT_LIMIT, SchemaName, clamp_limit, tool
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


@tool(feature="api_mincut", read_only=True, project_types={"WS"})
async def list_mincuts(
    api: TenantApi,
    schema: SchemaName,
    state: Annotated[
        MincutState | None,
        Field(description="0 planified, 1 in progress, 2 finished, 3 canceled, 4 on planning, 5 conflict"),
    ] = None,
    exploitation: Annotated[int | None, Field(description="Exploitation id")] = None,
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """List mincuts. State: 0 planified, 1 in progress, 2 finished, 3 canceled, 4 on planning, 5 conflict."""
    limit = clamp_limit(limit)
    raw = await api.get(
        "/om/mincuts",
        schema=schema,
        params=_filter_fields(mincut_state=state, expl_id=exploitation),
    )
    return list_rows(raw, limit=limit)


@tool(feature="api_mincut", read_only=True, project_types={"WS"})
async def get_mincut(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    include_geometry: Annotated[bool, Field(description="Include GeoJSON FeatureCollections")] = False,
) -> dict:
    """Mincut summary: state, bbox, and counts/ids per valve category and affected features."""
    raw = await api.get(f"/om/mincuts/{mincut_id}", schema=schema)
    return _summarise_mincut(unwrap(raw), include_geometry)


@tool(feature="api_mincut", read_only=True, project_types={"WS"})
async def list_mincut_valves(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """Valves associated with a mincut."""
    limit = clamp_limit(limit)
    raw = await api.get(f"/om/mincuts/{mincut_id}/valves", schema=schema)
    return list_rows(raw, limit=limit)


@tool(feature="api_mincut", project_types={"WS"})
async def create_mincut(
    api: TenantApi,
    schema: SchemaName,
    x: Annotated[float | None, Field(description="X coordinate in the project CRS (not WGS84)")] = None,
    y: Annotated[float | None, Field(description="Y coordinate in the project CRS (not WGS84)")] = None,
    arc_id: Annotated[
        int | None, Field(description="Arc id from list_street_arcs. Mutually exclusive with x/y.")
    ] = None,
    epsg: Annotated[int | None, Field(description="Project EPSG; omit to use the schema EPSG")] = None,
    mincut_type: Annotated[Literal["Demo", "Test", "Real"], Field(description="Mincut type")] = "Demo",
    anl_cause: Annotated[Literal["Accidental", "Planified"], Field(description="Cause")] = "Accidental",
    anl_descript: Annotated[str | None, Field(description="Optional description")] = None,
    zoom_ratio: Annotated[
        float,
        Field(
            description=(
                "Snapping radius in CRS units when using x/y. Determines which feature wins: "
                "Connec/Gully/Node > Link/Arc > Polygons. Default 1000."
            )
        ),
    ] = 1000,
) -> dict:
    """Create an unplanned mincut from an arc_id or project-CRS coordinates. Not idempotent — retrying creates a duplicate."""
    has_arc = arc_id is not None
    has_any_xy = x is not None or y is not None
    if has_arc and has_any_xy:
        raise ToolError("Provide arc_id or both x and y, not both")
    if not has_arc and not (x is not None and y is not None):
        raise ToolError("Provide arc_id or both x and y")
    plan = {"mincut_type": mincut_type, "anl_cause": anl_cause, "anl_descript": anl_descript}
    if has_arc:
        body = {"arcId": arc_id, "plan": plan, "use_psectors": False}
    else:
        epsg = await api.resolve_epsg(schema, epsg)
        body = {
            "coordinates": {"xcoord": x, "ycoord": y, "epsg": epsg, "zoomRatio": zoom_ratio},
            "plan": plan,
            "use_psectors": False,
        }
    raw = await api.post("/om/mincuts", schema=schema, json=body)
    return _summarise_mincut(unwrap(raw), include_geometry=False)


@tool(feature="api_mincut", project_types={"WS"})
async def update_mincut(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    mincut_type: Annotated[Literal["Demo", "Test", "Real"] | None, Field(description="Mincut type")] = None,
    anl_descript: Annotated[str | None, Field(description="Plan description")] = None,
    exec_descript: Annotated[str | None, Field(description="Execution description")] = None,
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
    return _summarise_mincut(unwrap(raw), include_geometry=False)


@tool(feature="api_mincut", project_types={"WS"})
async def toggle_mincut_valve(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    valve_id: Annotated[int, Field(description="Valve node id")],
    change: Annotated[Literal["status", "unaccess"], Field(description="Toggle status or unaccess")],
) -> dict:
    """Toggle a mincut valve. This is a TOGGLE, not a setter: calling twice restores the original state. Do not retry after a timeout."""
    path = f"/om/mincuts/{mincut_id}/valves/{valve_id}/toggle-{change}"
    raw = await api.post(path, schema=schema, json={"use_psectors": False})
    return _summarise_mincut(unwrap(raw), include_geometry=False)


@tool(feature="api_mincut", destructive=True, project_types={"WS"})
async def set_mincut_state(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    action: Annotated[Literal["start", "end", "cancel"], Field(description="Lifecycle action")],
    shutoff_required: Annotated[bool, Field(description="Required when action is end")] = True,
) -> dict:
    """Change mincut lifecycle. Starting a mincut interrupts water supply to customers."""
    path = f"/om/mincuts/{mincut_id}/{action}"
    body: dict[str, Any] = {}
    if action == "end":
        body["shutoff_required"] = shutoff_required
    raw = await api.post(path, schema=schema, json=body or None)
    return _summarise_mincut(unwrap(raw), include_geometry=False)


@tool(feature="api_mincut", destructive=True, project_types={"WS"})
async def delete_mincut(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
) -> dict:
    """Permanently delete a mincut record."""
    return _summarise_mincut(
        unwrap(await api.delete(f"/om/mincuts/{mincut_id}", schema=schema)), include_geometry=False
    )
