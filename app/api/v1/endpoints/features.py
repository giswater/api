"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Optional

from fastapi import APIRouter, Path, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.basic.basic_models import GetListResponse
from app.schemas.features.feature_models import GetFeatureResponse, GetFeaturesGeoJsonResponse
from app.services.features_service import FeaturesService

router = APIRouter(prefix="/features", tags=["Features"])


@router.get(
    "/nodes",
    description="Get nodes",
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_nodes(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features("node", coordinates, page_info, filter_fields)


@router.get(
    "/nodes/geojson",
    description="Get nodes as GeoJSON",
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_nodes_geojson(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features_geojson("node", coordinates, page_info, filter_fields)


@router.get(
    "/nodes/{node_id}",
    description="Get a single node form",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_node(
    commons: CommonsDep,
    node_id: str = Path(..., description="Node id"),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("node", node_id)


@router.get(
    "/arcs",
    description="Get arcs",
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_arcs(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features("arc", coordinates, page_info, filter_fields)


@router.get(
    "/arcs/geojson",
    description="Get arcs as GeoJSON",
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_arcs_geojson(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features_geojson("arc", coordinates, page_info, filter_fields)


@router.get(
    "/arcs/{arc_id}",
    description="Get a single arc form",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_arc(
    commons: CommonsDep,
    arc_id: str = Path(..., description="Arc id"),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("arc", arc_id)


@router.get(
    "/links",
    description="Get links",
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_links(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features("link", coordinates, page_info, filter_fields)


@router.get(
    "/links/geojson",
    description="Get links as GeoJSON",
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_links_geojson(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features_geojson("link", coordinates, page_info, filter_fields)


@router.get(
    "/links/{link_id}",
    description="Get a single link form",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_link(
    commons: CommonsDep,
    link_id: str = Path(..., description="Link id"),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("link", link_id)


@router.get(
    "/connecs",
    description="Get connecs",
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_connecs(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features("connec", coordinates, page_info, filter_fields)


@router.get(
    "/connecs/geojson",
    description="Get connecs as GeoJSON",
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_connecs_geojson(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features_geojson("connec", coordinates, page_info, filter_fields)


@router.get(
    "/connecs/{connec_id}",
    description="Get a single connec form",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_connec(
    commons: CommonsDep,
    connec_id: str = Path(..., description="Connec id"),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("connec", connec_id)


@router.get(
    "/gullys",
    description="Get gullys",
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_gullys(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features("gully", coordinates, page_info, filter_fields)


@router.get(
    "/gullys/geojson",
    description="Get gullys as GeoJSON",
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_gullys_geojson(
    commons: CommonsDep,
    coordinates: Optional[str] = Query(None, description="JSON string of coordinates (ExtentModel)"),
    page_info: Optional[str] = Query(None, alias="pageInfo", description="JSON string of page info (PageInfoModel)"),
    filter_fields: Optional[str] = Query(
        None, alias="filterFields", description="JSON string of filter fields (Dict[str, FilterFieldModel])"
    ),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_features_geojson("gully", coordinates, page_info, filter_fields)


@router.get(
    "/gullys/{gully_id}",
    description="Get a single gully form",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_gully(
    commons: CommonsDep,
    gully_id: str = Path(..., description="Gully id"),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("gully", gully_id)
