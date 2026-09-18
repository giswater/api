"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated, Any, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DEFAULT_LIMIT, DENSE_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import list_rows, unwrap
from app.schemas.epa.dscenario_models import DscenarioObjectType, DscenarioType


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
    """List objects of one type inside a dscenario (pipe, junction, demand, …)."""
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
    # POST /epa/dscenarios is response_model=dict and may skip the Giswater envelope.
    return unwrap(raw) if isinstance(raw.get("body"), dict) else raw


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
    return unwrap(await api.post(f"/epa/dscenarios/{dscenario_id}/select", schema=schema, json={}))


@tool(feature="api_epa", destructive=True)
async def delete_dscenario(
    api: TenantApi,
    schema: SchemaName,
    dscenario_id: Annotated[int, Field(description="Dscenario id")],
) -> dict:
    """Permanently delete an EPA dscenario."""
    return unwrap(await api.delete(f"/epa/dscenarios/{dscenario_id}", schema=schema))


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
    The id column (and object_id) depends on object_type: connec=connec_id;
    controls/demand/rules=id; frpump/frshortpipe/frvalve=element_id;
    inlet/junction/pump/pump_additional/reservoir/shortpipe/tank/valve=node_id;
    pipe/virtualpump/virtualvalve=arc_id; pattern/pattern_value=pattern_id.
    """
    base = f"/epa/dscenarios/{dscenario_id}/{object_type}"
    if action == "insert":
        if not objects:
            raise ToolError("insert requires objects")
        return unwrap(await api.post(base, schema=schema, json=objects))
    if action == "upsert":
        if not objects:
            raise ToolError("upsert requires objects")
        return unwrap(await api.put(base, schema=schema, json=objects))
    if action == "update":
        if object_id is None or data is None:
            raise ToolError("update requires object_id and data")
        return unwrap(await api.patch(f"{base}/{object_id}", schema=schema, json=data))
    if object_id is None:
        raise ToolError("delete requires object_id")
    return unwrap(await api.delete(f"{base}/{object_id}", schema=schema))
