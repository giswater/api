"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Optional

from fastapi import APIRouter, Path, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.streets.street_models import ListStreetArcsResponse, ListStreetsResponse
from app.services.streets_service import StreetsService

router = APIRouter(tags=["Streets"])


@router.get(
    "/streets",
    description="Search street axes by name (and municipality name). Caller picks an id when the query is ambiguous.",
    response_model=ListStreetsResponse,
    response_model_exclude_unset=True,
)
async def list_streets(
    commons: CommonsDep,
    q: str = Query(..., min_length=2, description="Street or municipality name substring"),
    limit: int = Query(50, ge=1, le=500, description="Maximum streets to return"),
):
    ctx = get_service_context(commons)
    return await StreetsService(ctx).list_streets(q, limit)


@router.get(
    "/streets/{street_id}/arcs",
    description=(
        "Arcs on a street by streetaxis_id and/or proximity to the street geometry. "
        "Optional houseNumber ranks by distance to that address."
    ),
    response_model=ListStreetArcsResponse,
    response_model_exclude_unset=True,
)
async def list_street_arcs(
    commons: CommonsDep,
    street_id: str = Path(..., description="Street axis id (ext_streetaxis.id)", examples=["1-10220C"]),
    house_number: Optional[str] = Query(None, alias="houseNumber", description="Address number on this street"),
    buffer_meters: float = Query(
        10, alias="bufferMeters", ge=0, le=1000, description="Spatial buffer in CRS units. 0 = attribute-only."
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum arcs to return"),
):
    ctx = get_service_context(commons)
    return await StreetsService(ctx).list_street_arcs(street_id, house_number, buffer_meters, limit)
