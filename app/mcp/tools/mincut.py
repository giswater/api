"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DEFAULT_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import as_int, fc_summary, list_rows, unwrap

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

_STATE_LABELS = {
    "planified": 0,
    "in progress": 1,
    "finished": 2,
    "canceled": 3,
    "cancelled": 3,
    "on planning": 4,
    "conflict": 5,
}

_STAT_PATTERNS: tuple[tuple[str, str, type], ...] = (
    (r"Number of arcs:\s*([\d.]+)", "arcs", int),
    (r"Length of affected network:\s*([\d.]+)", "length_m", float),
    (r"Total water volume:\s*([\d.]+)", "volume_m3", float),
    (r"Number of connecs affected:\s*([\d.]+)", "connecs", int),
    (r"Total of hydrometers affected:\s*([\d.]+)", "hydrometers", int),
)
_CLASS_RE = re.compile(r"Hydrometers classification:\s*(\[.*\])", re.DOTALL)
_ZOOM_RATIO_DESC = (
    "Map zoom ratio passed to Giswater (not a snapping radius in CRS units). "
    "Feature precedence at the click: Connec/Gully/Node > Link/Arc > Polygons. Default 1000."
)


def _filter_fields(**fields: Any) -> dict | None:
    payload = {}
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = {"value": value, "filterSign": "="}
    if not payload:
        return None
    return {"filterFields": json.dumps(payload)}


def _parse_mincut_stats(info: Any) -> dict | None:  # noqa: C901
    values = info.get("values") if isinstance(info, dict) else None
    if not values:
        return None
    messages = [row.get("message") for row in values if isinstance(row, dict)]
    stats: dict[str, Any] = {}
    leftover: list[str] = []
    for message in messages:
        if not isinstance(message, str) or not message.strip():
            continue
        text = message.strip()
        if text in {"MINCUT STATS", "------------------------------"} or set(text) <= {"-"}:
            continue
        matched = False
        for pattern, key, conv in _STAT_PATTERNS:
            found = re.search(pattern, text)
            if not found:
                continue
            try:
                stats[key] = conv(found.group(1))
            except (TypeError, ValueError):
                leftover.append(text)
            matched = True
            break
        if matched:
            continue
        classes = _CLASS_RE.search(text)
        if classes:
            try:
                stats["hydrometer_classes"] = json.loads(classes.group(1))
            except json.JSONDecodeError:
                leftover.append(text)
            continue
        leftover.append(text)
    if leftover:
        stats["messages"] = leftover
    return stats or None


def _summarise_mincut(data: dict, include_geometry: bool) -> dict:
    geom = data.get("geometry") or {}
    bbox = None
    if isinstance(geom, dict):
        box = geom.get("bbox") or {}
        if box:
            bbox = [box.get("x1"), box.get("y1"), box.get("x2"), box.get("y2")]
        elif "x" in geom and "y" in geom:
            bbox = [geom.get("x"), geom.get("y"), geom.get("x"), geom.get("y")]
    categories = {name: fc_summary(data.get(key), id_key, with_bbox=False) for name, (key, id_key) in _FC_KEYS.items()}
    result: dict[str, Any] = {
        "mincut_id": as_int(data.get("mincutId")) if data.get("mincutId") is not None else data.get("mincutId"),
        "state": as_int(data.get("mincutState")) if data.get("mincutState") is not None else data.get("mincutState"),
        "bbox": bbox,
        "categories": categories,
    }
    stats = _parse_mincut_stats(data.get("info"))
    if stats:
        result["stats"] = stats
    if include_geometry:
        result["geometry"] = {name: data.get(key) for name, (key, _) in _FC_KEYS.items()}
    return result


def _fill_empty_summary(summary: dict, mincut_id: int, *, action: str | None = None, state: int | None = None) -> dict:
    if summary.get("mincut_id") is not None:
        return summary
    summary["mincut_id"] = mincut_id
    if action is not None:
        summary["action"] = action
    if state is not None:
        summary["state"] = state
    return summary


def _shape_mincut_list_row(row: dict) -> dict:
    out = dict(row)
    if "mincut_id" not in out and "id" in out:
        out["mincut_id"] = out.pop("id")
    else:
        out.pop("id", None)
    state = out.get("state")
    if isinstance(state, str):
        mapped = _STATE_LABELS.get(state.strip().lower())
        if mapped is not None:
            out["state"] = mapped
    return out


def _rewrite_mincut_error(exc: ToolError) -> ToolError:
    text = str(exc)
    lowered = text.lower()
    if "not on planning" in lowered or "cannot be deleted" in lowered:
        return ToolError(
            "delete_mincut only works while the mincut is on planning (state 4). "
            "Planified or canceled mincuts cannot be deleted."
        )
    return exc


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
    """List mincuts. State is numeric: 0 planified, 1 in progress, 2 finished, 3 canceled, 4 on planning, 5 conflict."""
    limit = clamp_limit(limit)
    raw = await api.get(
        "/om/mincuts",
        schema=schema,
        params=_filter_fields(state=state, expl_id=exploitation),
    )
    shaped = list_rows(raw, limit=limit)
    shaped["items"] = [_shape_mincut_list_row(item) if isinstance(item, dict) else item for item in shaped["items"]]
    return shaped


@tool(feature="api_mincut", read_only=True, project_types={"WS"})
async def get_mincut(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    include_geometry: Annotated[bool, Field(description="Include GeoJSON FeatureCollections")] = False,
) -> dict:
    """Mincut summary: state, project-CRS bbox, ids per valve category, and parsed stats (no GeoJSON)."""
    raw = await api.get(f"/om/mincuts/{mincut_id}", schema=schema)
    return _summarise_mincut(unwrap(raw), include_geometry)


@tool(feature="api_mincut", read_only=True, project_types={"WS"})
async def list_mincut_valves(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """Valves associated with a mincut. Point geometry is returned as x/y, not the_geom."""
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
    zoom_ratio: Annotated[float, Field(description=_ZOOM_RATIO_DESC)] = 1000,
) -> dict:
    """Create an unplanned mincut from an arc_id or project-CRS coordinates. Not idempotent — retrying creates a duplicate.

    Set ``anl_descript`` here. ``update_mincut`` planifies (state 4 → 0); after that the mincut cannot be deleted.
    """
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
    """Accept/planify a mincut (GW mincutAccept): state 4 on-planning → 0 planified.

    After this the mincut can only be cancelled, never deleted. Set ``anl_descript`` on
    ``create_mincut`` if the record should stay disposable.
    """
    body: dict[str, Any] = {"use_psectors": False}
    plan = {k: v for k, v in {"mincut_type": mincut_type, "anl_descript": anl_descript}.items() if v is not None}
    exec_ = {k: v for k, v in {"exec_descript": exec_descript}.items() if v is not None}
    if plan:
        body["plan"] = plan
    if exec_:
        body["exec"] = exec_
    raw = await api.patch(f"/om/mincuts/{mincut_id}", schema=schema, json=body)
    return _fill_empty_summary(_summarise_mincut(unwrap(raw), include_geometry=False), mincut_id, action="update")


@tool(feature="api_mincut", project_types={"WS"})
async def toggle_mincut_valve(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    valve_id: Annotated[int, Field(description="Valve node id")],
    change: Annotated[Literal["status", "unaccess"], Field(description="Toggle status or unaccess")],
) -> dict:
    """Toggle a mincut valve by node_id. This is a TOGGLE, not a setter: calling twice restores the original state.

    Do not retry after a timeout. GW recalculates the mincut (valve row ids are rewritten).
    ``status`` may be a no-op once the mincut is planified (state 0); check ``changestatus``
    via ``list_mincut_valves`` rather than assuming the flag flipped.
    """
    path = f"/om/mincuts/{mincut_id}/valves/{valve_id}/toggle-{change}"
    raw = await api.post(path, schema=schema, json={"use_psectors": False})
    return _fill_empty_summary(
        _summarise_mincut(unwrap(raw), include_geometry=False), mincut_id, action=f"toggle-{change}"
    )


@tool(feature="api_mincut", destructive=True, project_types={"WS"})
async def set_mincut_state(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
    action: Annotated[Literal["start", "end", "cancel"], Field(description="Lifecycle action")],
    shutoff_required: Annotated[bool, Field(description="Required when action is end")] = True,
) -> dict:
    """Change mincut lifecycle. Starting a mincut interrupts water supply to customers.

    ``cancel`` is terminal: the mincut cannot be deleted afterwards.
    """
    path = f"/om/mincuts/{mincut_id}/{action}"
    body: dict[str, Any] = {}
    if action == "end":
        body["shutoff_required"] = shutoff_required
    raw = await api.post(path, schema=schema, json=body or None)
    next_state = {"start": 1, "end": 2, "cancel": 3}.get(action)
    return _fill_empty_summary(
        _summarise_mincut(unwrap(raw), include_geometry=False), mincut_id, action=action, state=next_state
    )


@tool(feature="api_mincut", destructive=True, project_types={"WS"})
async def delete_mincut(
    api: TenantApi,
    schema: SchemaName,
    mincut_id: Annotated[int, Field(description="Mincut id")],
) -> dict:
    """Permanently delete a mincut record. Only works while the mincut is on planning (state 4)."""
    try:
        raw = await api.delete(f"/om/mincuts/{mincut_id}", schema=schema)
    except ToolError as exc:
        raise _rewrite_mincut_error(exc) from exc
    return _fill_empty_summary(_summarise_mincut(unwrap(raw), include_geometry=False), mincut_id, action="delete")
