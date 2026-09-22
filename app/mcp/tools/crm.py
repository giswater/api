"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Annotated

from pydantic import Field

from app.mcp.client import TenantApi
from app.mcp.registry import DENSE_LIMIT, SchemaName, clamp_limit, tool
from app.mcp.shaping import list_payload, unwrap


@tool(feature="api_crm", read_only=True)
async def list_hydrometers(
    api: TenantApi,
    schema: SchemaName,
    code: Annotated[str | None, Field(description="Filter by hydrometer code")] = None,
    connec_id: Annotated[int | None, Field(description="Filter by connec id")] = None,
    dma_id: Annotated[int | None, Field(description="Filter by DMA id")] = None,
    mincut_id: Annotated[int | None, Field(description="Filter by mincut id (affected hydrometers)")] = None,
    customer_code: Annotated[str | None, Field(description="Filter by connec customer code")] = None,
    limit: Annotated[int, Field(description="Max rows requested from the API (1–500)")] = DENSE_LIMIT,
) -> dict:
    """List hydrometers, optionally filtered by code, connec_id, dma_id, mincut_id or customer_code.

    ``count`` is the page size; ``total`` is the match count. Hydrometers whose
    customer code does not join a connec have ``dma_id`` null and are invisible
    to a ``dma_id`` filter — per-DMA totals will not sum to the unfiltered total.
    Present on both WS and UD sample schemas (UD rows may carry ``is_waterbal``).
    """
    limit = clamp_limit(limit)
    params = {
        k: v
        for k, v in {
            "code": code,
            "connecId": connec_id,
            "dmaId": dma_id,
            "mincutId": mincut_id,
            "customerCode": customer_code,
            "limit": limit,
        }.items()
        if v is not None
    }
    data = unwrap(await api.get("/crm/hydrometers", schema=schema, params=params))
    items = list(data.get("hydrometers") or [])
    rest_total = data.get("count")
    total = rest_total if isinstance(rest_total, int) else None
    return list_payload(items, limit=limit, total=total)
