"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated

from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DEFAULT_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import list_payload, unwrap


def _listed(rows: list, limit: int, truncated: bool | None, extra: dict | None = None) -> dict:
    if isinstance(truncated, bool):
        return list_payload(rows, limit=limit, truncated=truncated, extra=extra)
    return list_payload(rows, limit=limit, extra=extra)


@tool(feature="api_basic", read_only=True)
async def list_streets(
    api: TenantApi,
    schema: SchemaName,
    q: Annotated[str, Field(description="Street or municipality name substring (min 2 characters)")],
    limit: Annotated[int, Field(description="Max streets to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """Search street axes by name. Ambiguous queries return multiple streets; pick an id for list_street_arcs.

    Example: list_streets("Salvador Espriu") → list_street_arcs("1-10220C") → create_mincut(arc_id=132).
    """
    limit = clamp_limit(limit)
    data = unwrap(await api.get("/streets", schema=schema, params={"q": q, "limit": limit}))
    return _listed(list(data.get("streets") or []), limit, data.get("truncated"))


@tool(feature="api_basic", read_only=True)
async def list_street_arcs(
    api: TenantApi,
    schema: SchemaName,
    street_id: Annotated[str, Field(description="Street axis id from list_streets (ext_streetaxis.id)")],
    house_number: Annotated[str | None, Field(description="Address number; ranks arcs by distance when found")] = None,
    buffer_meters: Annotated[
        float, Field(description="Spatial buffer in CRS units. 0 = attribute-only. Default 10.")
    ] = 10,
    limit: Annotated[int, Field(description="Max arcs to return (1–500)")] = DEFAULT_LIMIT,
) -> dict:
    """Arcs on a street by streetaxis_id and/or proximity. Caller picks an arc_id for create_mincut."""
    limit = clamp_limit(limit)
    params: dict = {"limit": limit, "bufferMeters": buffer_meters}
    if house_number is not None:
        params["houseNumber"] = house_number
    data = unwrap(await api.get(f"/streets/{street_id}/arcs", schema=schema, params=params))
    extra = {"street": data["street"]} if data.get("street") else None
    return _listed(list(data.get("arcs") or []), limit, data.get("truncated"), extra)
