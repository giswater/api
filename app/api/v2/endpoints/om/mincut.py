"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi import APIRouter, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.om.mincut_models import GetMincutsResponse
from app.services.om.mincut_service import MincutService

router = APIRouter(prefix="/om", tags=["OM - Mincut"])


@router.get(
    "/mincuts",
    description=(
        "Returns a list of mincuts from om_mincut. "
        "Geometry columns are omitted by default; pass includeGeometry=true to receive them as GeoJSON (EPSG:4326)."
    ),
    response_model=GetMincutsResponse,
    response_model_exclude_unset=True,
)
async def get_mincuts(
    commons: CommonsDep,
    include_geometry: bool = Query(
        False,
        alias="includeGeometry",
        description="Include anl_the_geom, exec_the_geom, and polygon_the_geom as GeoJSON (EPSG:4326)",
    ),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).get_mincuts_v2(include_geometry=include_geometry)
