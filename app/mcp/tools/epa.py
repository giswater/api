"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Any, Literal

from fastmcp.exceptions import ToolError

from app.mcp.client import TenantApi
from app.mcp.registry import tool
from app.mcp.shaping import list_rows, unwrap
from app.schemas.epa.dscenario_models import DscenarioObjectType


@tool(feature="api_epa", read_only=True)
async def list_dscenarios(api: TenantApi, schema: str, limit: int = 50) -> dict:
    """List EPA dscenarios."""
    limit = min(max(limit, 1), 500)
    return list_rows(await api.get("/epa/dscenarios", schema=schema), limit=limit)


@tool(feature="api_epa", read_only=True)
async def list_dscenario_objects(
    api: TenantApi,
    schema: str,
    dscenario_id: int,
    object_type: DscenarioObjectType,
    limit: int = 100,
) -> dict:
    """List objects of one type inside a dscenario (pipe, junction, demand, …)."""
    limit = min(max(limit, 1), 500)
    raw = await api.get(f"/epa/dscenarios/{dscenario_id}/{object_type}", schema=schema)
    return list_rows(raw, limit=limit)


@tool(feature="api_epa", destructive=True)
async def manage_dscenario(
    api: TenantApi,
    schema: str,
    action: Literal["create", "select", "delete"],
    dscenario_id: int | None = None,
    name: str | None = None,
    type: str | None = None,
    descript: str | None = None,
    expl: int = 0,
    active: bool = True,
) -> dict:
    """Create, select or delete an EPA dscenario."""
    if action == "create":
        if not name or not type:
            raise ToolError("create requires name and type")
        raw = await api.post(
            "/epa/dscenarios",
            schema=schema,
            json={"name": name, "type": type, "descript": descript, "expl": expl, "active": active},
        )
        return unwrap(raw) if isinstance(raw.get("body"), dict) else raw
    if dscenario_id is None:
        raise ToolError("select/delete require dscenario_id")
    if action == "select":
        return unwrap(await api.post(f"/epa/dscenarios/{dscenario_id}/select", schema=schema, json={}))
    return unwrap(await api.delete(f"/epa/dscenarios/{dscenario_id}", schema=schema))


@tool(feature="api_epa", destructive=True)
async def manage_dscenario_objects(
    api: TenantApi,
    schema: str,
    action: Literal["insert", "update", "delete", "upsert"],
    dscenario_id: int,
    object_type: DscenarioObjectType,
    objects: list[dict[str, Any]] | None = None,
    object_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict:
    """Insert, update, upsert or delete objects inside a dscenario."""
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
