"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import re
from typing import Annotated, Any, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DEFAULT_LIMIT, DENSE_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import as_int, compact_row, list_rows, unwrap
from app.schemas.epa.dscenario_models import DscenarioObjectType, DscenarioType

_COLUMN_ERROR = re.compile(r'column "([^"]+)" of relation "(?:[^"]+\.)?ve_inp_dscenario_([^"]+)"')

_WRITE_KEYS = (
    "connec=connec_id; controls/rules=id; demand=feature_id+feature_type (not node_id; "
    "id is the serial); frpump/frshortpipe/frvalve=element_id; "
    "inlet/junction/pump/pump_additional/reservoir/shortpipe/tank/valve=node_id; "
    "pipe/virtualpump/virtualvalve=arc_id; pattern/pattern_value=pattern_id."
)


def _shape_dscenario(data: dict, *, name: str | None = None, dscenario_type: str | None = None) -> dict:
    ds_id = as_int(data.get("dscenario_id"))
    out: dict[str, Any] = {}
    if ds_id is not None:
        out["dscenario_id"] = ds_id
    for key in ("name", "descript", "dscenario_type", "type"):
        if data.get(key) is not None:
            out[key] = data[key]
    if "name" not in out and name is not None:
        out["name"] = name
    if "dscenario_type" not in out and "type" not in out and dscenario_type is not None:
        out["dscenario_type"] = dscenario_type
    return compact_row(out) if out else compact_row(data)


def _rewrite_dscenario_error(exc: ToolError) -> ToolError:
    text = str(exc)
    found = _COLUMN_ERROR.search(text)
    if not found:
        return exc
    column, object_type = found.group(1), found.group(2)
    return ToolError(f"Unknown column {column!r} for object_type={object_type!r}. Write keys: {_WRITE_KEYS}")


async def _dscenario_request(call, path: str, schema: str, payload: Any) -> dict:
    try:
        raw = await call(path, schema=schema, json=payload)
    except ToolError as exc:
        raise _rewrite_dscenario_error(exc) from exc
    return compact_row(unwrap(raw))


@tool(feature="api_epa", read_only=True)
async def list_dscenarios(
    api: TenantApi,
    schema: SchemaName,
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """List EPA dscenarios."""
    return list_rows(await api.get("/epa/dscenarios", schema=schema), limit=clamp_limit(limit))


@tool(feature="api_epa", read_only=True)
async def list_dscenario_objects(
    api: TenantApi,
    schema: SchemaName,
    dscenario_id: Annotated[int, Field(description="Dscenario id")],
    object_type: Annotated[DscenarioObjectType, Field(description="Object class inside the dscenario")],
    limit: Annotated[int, Field(description="Max rows to return (1–500)")] = DENSE_LIMIT,
) -> dict:
    """List objects of one type inside a dscenario (pipe, junction, demand, …). Geometry is omitted."""
    raw = await api.get(f"/epa/dscenarios/{dscenario_id}/{object_type}", schema=schema)
    return list_rows(raw, limit=clamp_limit(limit))


@tool(feature="api_epa")
async def create_dscenario(
    api: TenantApi,
    schema: SchemaName,
    name: Annotated[str, Field(description="Dscenario name")],
    dscenario_type: Annotated[DscenarioType, Field(description="DEMAND, VALVE, PIPE, …")],
    descript: Annotated[str | None, Field(description="Optional description")] = None,
    expl: Annotated[int, Field(description="Exploitation id")] = 0,
    active: Annotated[bool, Field(description="Active flag")] = True,
) -> dict:
    """Create an EPA dscenario. Not idempotent — retrying creates a duplicate."""
    raw = await api.post(
        "/epa/dscenarios",
        schema=schema,
        json={"name": name, "type": dscenario_type, "descript": descript, "expl": expl, "active": active},
    )
    data = unwrap(raw) if isinstance(raw.get("body"), dict) else raw
    return _shape_dscenario(data if isinstance(data, dict) else {}, name=name, dscenario_type=dscenario_type)


@tool(feature="api_epa")
async def select_dscenario(
    api: TenantApi,
    schema: SchemaName,
    dscenario_id: Annotated[int, Field(description="Dscenario id")],
) -> dict:
    """Set the current user's selected dscenario (session selector, not a row update).

    Writes ``selector_inp_dscenario`` for ``CURRENT_USER``. If the MCP DB role is
    the same as a QGIS session, this clobbers that user's selected dscenario.
    """
    data = unwrap(await api.post(f"/epa/dscenarios/{dscenario_id}/select", schema=schema, json={}))
    items = data.get("items") or data.get("fields") or []
    row = items[0] if items and isinstance(items[0], dict) else data
    selected = as_int(row.get("dscenario_id")) if isinstance(row, dict) else None
    return compact_row(
        {
            "dscenario_id": selected if selected is not None else dscenario_id,
            "cur_user": row.get("cur_user") if isinstance(row, dict) else None,
        }
    )


@tool(feature="api_epa", destructive=True)
async def delete_dscenario(
    api: TenantApi,
    schema: SchemaName,
    dscenario_id: Annotated[int, Field(description="Dscenario id")],
) -> dict:
    """Permanently delete an EPA dscenario."""
    await api.delete(f"/epa/dscenarios/{dscenario_id}", schema=schema)
    return {"dscenario_id": dscenario_id, "deleted": True}


@tool(feature="api_epa", destructive=True)
async def manage_dscenario_objects(
    api: TenantApi,
    schema: SchemaName,
    action: Annotated[
        Literal["insert", "update", "delete", "upsert"], Field(description="insert / update / upsert / delete")
    ],
    dscenario_id: Annotated[int, Field(description="Dscenario id")],
    object_type: Annotated[DscenarioObjectType, Field(description="Object class inside the dscenario")],
    objects: Annotated[list[dict[str, Any]] | None, Field(description="Required for insert and upsert")] = None,
    object_id: Annotated[str | None, Field(description="Required for update and delete")] = None,
    data: Annotated[dict[str, Any] | None, Field(description="Required for update (fields to patch)")] = None,
) -> dict:
    """Insert, update, upsert or delete objects inside a dscenario.

    insert/upsert require objects. update requires object_id and data. delete requires object_id.
    """
    base = f"/epa/dscenarios/{dscenario_id}/{object_type}"
    if action in {"insert", "upsert"}:
        if not objects:
            raise ToolError(f"{action} requires objects")
        method = api.post if action == "insert" else api.put
        return await _dscenario_request(method, base, schema, objects)
    if action == "update":
        if object_id is None or data is None:
            raise ToolError("update requires object_id and data")
        return await _dscenario_request(api.patch, f"{base}/{object_id}", schema, data)
    if object_id is None:
        raise ToolError("delete requires object_id")
    return await _dscenario_request(api.delete, f"{base}/{object_id}", schema, None)


manage_dscenario_objects.__doc__ = (
    f"{manage_dscenario_objects.__doc__.rstrip()}\n"
    f"Write keys (and URL object_id) depend on object_type: {_WRITE_KEYS}\n"
)
