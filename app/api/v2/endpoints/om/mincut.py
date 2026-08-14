"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi import APIRouter, Path, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.om.mincut_models import GetMincutResponse, GetMincutsResponse
from app.services.om.mincut_service import MincutService

router = APIRouter(prefix="/om", tags=["OM - Mincut"])

_INCLUDE_GEOMETRY_DESCRIPTION = (
    "Include geometry columns as GeoJSON (EPSG:4326). "
    "On the mincut row: anl_the_geom, exec_the_geom, polygon_the_geom. "
    "On arcs, valves, nodes, and connecs: the_geom."
)


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


@router.get(
    "/mincuts/{mincut_id}",
    description=(
        "Returns one mincut from om_mincut plus its related arcs, valves, nodes, connecs, "
        "hydrometers, conflict sibling ids, and a 4326 bounding box. "
        "Geometry columns are omitted by default; pass includeGeometry=true to receive them as GeoJSON (EPSG:4326)."
    ),
    response_model=GetMincutResponse,
    response_model_exclude_unset=True,
)
async def get_mincut(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to fetch", examples=[1]),
    include_geometry: bool = Query(
        False,
        alias="includeGeometry",
        description=_INCLUDE_GEOMETRY_DESCRIPTION,
    ),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).get_mincut_v2(mincut_id, include_geometry=include_geometry)
