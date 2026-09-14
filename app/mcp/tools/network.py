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
from app.mcp.registry import SchemaName, tool
from app.mcp.shaping import drop_keys, fc_summary, unwrap


@tool(feature="api_flow", read_only=True)
async def trace_flow(
    api: TenantApi,
    schema: SchemaName,
    direction: Annotated[Literal["upstream", "downstream"], Field(description="Trace direction")],
    node_id: Annotated[int | None, Field(description="Start node id (alternative to x/y/epsg)")] = None,
    x: Annotated[float | None, Field(description="X in project CRS if node_id is omitted")] = None,
    y: Annotated[float | None, Field(description="Y in project CRS if node_id is omitted")] = None,
    epsg: Annotated[int | None, Field(description="Project EPSG if using x/y (not 4326)")] = None,
    include_geometry: Annotated[bool, Field(description="Include GeoJSON point/line collections")] = False,
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
    schema: SchemaName,
    start_node_id: Annotated[int, Field(description="Start node id")],
    end_node_id: Annotated[int, Field(description="End node id")],
    intermediate_node_ids: Annotated[list[int] | None, Field(description="Optional nodes along the path")] = None,
    include_geometry: Annotated[bool, Field(description="Include GeoJSON point/line/polygon")] = False,
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
