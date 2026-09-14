"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Literal

from fastmcp.exceptions import ToolError

from app.mcp.client import TenantApi
from app.mcp.registry import tool
from app.mcp.shaping import drop_keys, fc_summary, unwrap


@tool(feature="api_flow", read_only=True)
async def trace_flow(
    api: TenantApi,
    schema: str,
    direction: Literal["upstream", "downstream"],
    node_id: int | None = None,
    x: float | None = None,
    y: float | None = None,
    epsg: int | None = None,
    include_geometry: bool = False,
) -> dict:
    """Trace flow upstream or downstream from a node id or project-CRS coordinates.

    Coordinates must be in the project EPSG (not WGS84 lat/lon). Provide either
    ``node_id`` or ``x``+``y``+``epsg``.
    """
    body: dict = {"direction": direction}
    if node_id is not None:
        body["node_id"] = node_id
    elif None not in (x, y, epsg):
        body["coordinates"] = {"xcoord": x, "ycoord": y, "epsg": epsg, "zoomRatio": 1000}
    else:
        raise ToolError("Provide node_id, or x + y + epsg (project CRS, not lat/lon)")
    raw = await api.post("/om/flow", schema=schema, json=body)
    data = unwrap(raw)
    point = fc_summary(data.get("point"), "node_id")
    line = fc_summary(data.get("line"), "arc_id")
    result = {
        "init_node": data.get("initPoint"),
        "node_ids": point["ids"],
        "arc_ids": line["ids"],
        "counts": {"nodes": point["count"], "arcs": line["count"]},
    }
    if include_geometry:
        result["point"] = data.get("point")
        result["line"] = data.get("line")
    return result


@tool(feature="api_profile", read_only=True)
async def get_profile(
    api: TenantApi,
    schema: str,
    start_node_id: int,
    end_node_id: int,
    intermediate_node_ids: list[int] | None = None,
    include_geometry: bool = False,
) -> dict:
    """Longitudinal profile between two nodes: node / terrain / arc arrays (no stylesheet)."""
    body = {
        "initial_node_id": start_node_id,
        "final_node_id": end_node_id,
        "middle_features": intermediate_node_ids,
        "links_distance": 1,
        "scale_eh": 1000,
        "scale_ev": 1000,
    }
    raw = await api.post("/om/profiles", schema=schema, json=body)
    data = unwrap(raw)
    result = {
        "node": data.get("node") or [],
        "terrain": data.get("terrain") or [],
        "arc": data.get("arc") or [],
        "extension": data.get("extension"),
        "initpoint": data.get("initpoint"),
    }
    if include_geometry:
        result["point"] = data.get("point")
        result["line"] = data.get("line")
        result["polygon"] = data.get("polygon")
    return drop_keys(result, "stylesheet", "legend", "returnManager")
