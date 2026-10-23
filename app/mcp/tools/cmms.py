"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated, Any

from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DENSE_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import compact_row, drop_geometry, list_payload, unwrap


def _kept(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value is not None}


def _first(data: dict, key: str) -> dict:
    rows = data.get(key) or []
    row = rows[0] if isinstance(rows, list) and rows else {}
    return compact_row(drop_geometry(row))


@tool(feature="api_cmms", read_only=True)
async def list_visits(
    api: TenantApi,
    schema: SchemaName,
    sys_code: Annotated[str | None, Field(description="Filter by feature sys_code")] = None,
    visit_type: Annotated[str | None, Field(description="Filter by visit type")] = None,
    status: Annotated[str | None, Field(description="Filter by visit status")] = None,
    limit: Annotated[int, Field(description="Max rows (1–500)")] = DENSE_LIMIT,
) -> dict:
    """List CMMS visits. Each item includes its sys_codes. count is the page size; total is the match count."""
    limit = clamp_limit(limit)
    params = _kept({"sysCode": sys_code, "type": visit_type, "status": status, "limit": limit})
    data = unwrap(await api.get("/cmms/visits", schema=schema, params=params))
    total = data.get("count")
    return list_payload(list(data.get("visits") or []), limit=limit, total=total if isinstance(total, int) else None)


@tool(feature="api_cmms", read_only=True)
async def get_visit(
    api: TenantApi,
    schema: SchemaName,
    visit_id: Annotated[str, Field(description="Visit UUID")],
) -> dict:
    """Get one CMMS visit and its sys_codes. List its files with list_attachments(visit_id=...)."""
    data = unwrap(await api.get(f"/cmms/visits/{visit_id}", schema=schema))
    return _first(data, "visits")


@tool(feature="api_cmms", read_only=True)
async def list_attachments(
    api: TenantApi,
    schema: SchemaName,
    sys_code: Annotated[str | None, Field(description="Feature sys_code, direct or via a visit")] = None,
    visit_id: Annotated[str | None, Field(description="Visit UUID")] = None,
    limit: Annotated[int, Field(description="Max rows (1–500)")] = DENSE_LIMIT,
) -> dict:
    """List CMMS attachments. thumbnail_path is null when the file has no generated thumbnail."""
    limit = clamp_limit(limit)
    params = _kept({"sysCode": sys_code, "visitId": visit_id, "limit": limit})
    data = unwrap(await api.get("/cmms/attachments", schema=schema, params=params))
    total = data.get("count")
    return list_payload(
        list(data.get("attachments") or []),
        limit=limit,
        total=total if isinstance(total, int) else None,
    )


@tool(feature="api_cmms", read_only=True)
async def get_attachment(
    api: TenantApi,
    schema: SchemaName,
    attachment_id: Annotated[str, Field(description="Attachment UUID")],
) -> dict:
    """Get one CMMS attachment. Metadata only; file bytes are not returned."""
    data = unwrap(await api.get(f"/cmms/attachments/{attachment_id}", schema=schema))
    return _first(data, "attachments")


@tool(feature="api_cmms")
async def create_visit(
    api: TenantApi,
    schema: SchemaName,
    visit_type: Annotated[str, Field(description="Visit type")],
    status: Annotated[str, Field(description="Visit status")],
    sys_codes: Annotated[list[str] | None, Field(description="Feature sys_code values")] = None,
    ext_visit_id: Annotated[str | None, Field(description="External visit id")] = None,
    title: Annotated[str | None, Field(description="Title")] = None,
    description: Annotated[str | None, Field(description="Description")] = None,
    start_date: Annotated[str | None, Field(description="Start, ISO-8601")] = None,
    end_date: Annotated[str | None, Field(description="End, ISO-8601")] = None,
    properties: Annotated[dict[str, Any] | None, Field(description="Free-form properties")] = None,
) -> dict:
    """Create a CMMS visit. Does not upload files; attach those through the REST API."""
    payload = _kept(
        {
            "type": visit_type,
            "status": status,
            "sysCodes": sys_codes,
            "extVisitId": ext_visit_id,
            "title": title,
            "description": description,
            "startDate": start_date,
            "endDate": end_date,
            "properties": properties,
        }
    )
    data = unwrap(await api.post("/cmms/visits", schema=schema, json=payload))
    return _first(data, "visits")


@tool(feature="api_cmms")
async def update_visit(
    api: TenantApi,
    schema: SchemaName,
    visit_id: Annotated[str, Field(description="Visit UUID")],
    visit_type: Annotated[str | None, Field(description="Visit type")] = None,
    status: Annotated[str | None, Field(description="Visit status")] = None,
    sys_codes: Annotated[list[str] | None, Field(description="Replace feature links")] = None,
    ext_visit_id: Annotated[str | None, Field(description="External visit id")] = None,
    title: Annotated[str | None, Field(description="Title")] = None,
    description: Annotated[str | None, Field(description="Description")] = None,
    start_date: Annotated[str | None, Field(description="Start, ISO-8601")] = None,
    end_date: Annotated[str | None, Field(description="End, ISO-8601")] = None,
    properties: Annotated[dict[str, Any] | None, Field(description="Free-form properties")] = None,
) -> dict:
    """Update a CMMS visit. Only fields you set are changed. sys_codes replaces the feature links."""
    payload = _kept(
        {
            "type": visit_type,
            "status": status,
            "sysCodes": sys_codes,
            "extVisitId": ext_visit_id,
            "title": title,
            "description": description,
            "startDate": start_date,
            "endDate": end_date,
            "properties": properties,
        }
    )
    data = unwrap(await api.patch(f"/cmms/visits/{visit_id}", schema=schema, json=payload))
    return _first(data, "visits")


@tool(feature="api_cmms", destructive=True)
async def delete_visit(
    api: TenantApi,
    schema: SchemaName,
    visit_id: Annotated[str, Field(description="Visit UUID")],
) -> dict:
    """Delete a CMMS visit and its feature links. Attachments are kept."""
    data = unwrap(await api.delete(f"/cmms/visits/{visit_id}", schema=schema))
    return _first(data, "visits")
