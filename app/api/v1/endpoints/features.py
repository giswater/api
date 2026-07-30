"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Any, Callable, Literal, Optional, Type, TypeVar

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from app.api.deps import CommonsDep, get_service_context
from app.schemas.features.feature_models import (
    ArcFilters,
    ConnecFilters,
    FeatureFilters,
    GetFeatureResponse,
    GetFeaturesGeoJsonResponse,
    GetFeaturesResponse,
    GullyFilters,
    LinkFilters,
    NodeFilters,
)
from app.services.features_service import FeaturesService

router = APIRouter(prefix="/features", tags=["Features"])

_LIMIT = Query(100, ge=1, le=5000, title="Limit", description="Maximum number of features to return")
_COORDINATES = Query(
    None,
    title="Coordinates",
    description="JSON string of map extent (ExtentModel: x1, y1, x2, y2)",
)
_ORDER_TYPE = Query(None, alias="orderType", title="Order type", description="ASC or DESC")

_RESERVED_QUERY_KEYS = frozenset({"schema", "coordinates", "orderBy", "orderType", "limit"})

NodeOrderBy = Literal["node_id", "code", "sys_type", "node_type", "nodecat_id", "dma_id", "sector_id", "state"]
ArcOrderBy = Literal["arc_id", "code", "sys_type", "arc_type", "arccat_id", "dma_id", "sector_id", "state"]
LinkOrderBy = Literal["link_id", "code", "sys_type", "link_type", "dma_id", "sector_id", "state"]
ConnecOrderBy = Literal["connec_id", "code", "sys_type", "connec_type", "connecat_id", "dma_id", "sector_id", "state"]
GullyOrderBy = Literal["gully_id", "code", "sys_type", "gully_type", "gratecat_id", "dma_id", "sector_id", "state"]

F = TypeVar("F", bound=FeatureFilters)


def _reject_unknown_filters(request: Request, model_cls: Type[FeatureFilters]) -> None:
    allowed = set(model_cls.model_fields) | _RESERVED_QUERY_KEYS
    unknown = sorted({key for key in request.query_params.keys() if key not in allowed})
    if not unknown:
        return
    raise RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": ["query", key],
                "msg": "Extra inputs are not permitted",
                "input": request.query_params.get(key),
            }
            for key in unknown
        ]
    )


def make_filters_dependency(model_cls: Type[F]) -> Callable[..., F]:
    """Build a Depends callable whose signature exposes model fields for OpenAPI.

    FastAPI only expands a Pydantic query model when it is the sole query param.
    CommonsDep always injects ``schema``, so filters must be a Depends instead.
    """

    parameters: list[inspect.Parameter] = [
        inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request)
    ]
    for name, field in model_cls.model_fields.items():
        default = field.default
        if default is PydanticUndefined:
            default = None
        query_default = Query(default, description=field.description)
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=query_default,
                annotation=field.annotation,
            )
        )

    async def _dependency(request: Request, **kwargs: Any) -> F:
        _reject_unknown_filters(request, model_cls)
        try:
            return model_cls.model_validate(kwargs)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

    _dependency.__signature__ = inspect.Signature(parameters, return_annotation=model_cls)  # type: ignore[attr-defined]
    _dependency.__annotations__ = {p.name: p.annotation for p in parameters} | {"return": model_cls}
    return _dependency


NodeFiltersDep = Annotated[NodeFilters, Depends(make_filters_dependency(NodeFilters))]
ArcFiltersDep = Annotated[ArcFilters, Depends(make_filters_dependency(ArcFilters))]
LinkFiltersDep = Annotated[LinkFilters, Depends(make_filters_dependency(LinkFilters))]
ConnecFiltersDep = Annotated[ConnecFilters, Depends(make_filters_dependency(ConnecFilters))]
GullyFiltersDep = Annotated[GullyFilters, Depends(make_filters_dependency(GullyFilters))]


@router.get(
    "/nodes",
    description=(
        "Returns a filtered collection of nodes from ve_node. "
        "Use sys_type for feature-class groups (e.g. VALVE) and node_type for subtypes "
        "(e.g. CHECK_VALVE). Mapzone filters such as dma_id and sector_id are supported."
    ),
    response_model=GetFeaturesResponse,
    response_model_exclude_unset=True,
)
async def get_nodes(
    commons: CommonsDep,
    filters: NodeFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[NodeOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features(
        "node", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/nodes/geojson",
    description=("Returns nodes as a GeoJSON FeatureCollection, with the same filters as GET /features/nodes."),
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_nodes_geojson(
    commons: CommonsDep,
    filters: NodeFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[NodeOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features_geojson(
        "node", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/nodes/{node_id}",
    description="Returns the form/info payload for a single node (gw_fct_getinfofromid).",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_node(
    commons: CommonsDep,
    node_id: str = Path(..., title="Node id", description="The unique identifier of the node", examples=["1001"]),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("node", node_id)


@router.get(
    "/arcs",
    description=(
        "Returns a filtered collection of arcs from ve_arc. "
        "Filter by mapzones (dma_id, sector_id, …), sys_type, arc_type, or catalog fields."
    ),
    response_model=GetFeaturesResponse,
    response_model_exclude_unset=True,
)
async def get_arcs(
    commons: CommonsDep,
    filters: ArcFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[ArcOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features(
        "arc", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/arcs/geojson",
    description=("Returns arcs as a GeoJSON FeatureCollection, with the same filters as GET /features/arcs."),
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_arcs_geojson(
    commons: CommonsDep,
    filters: ArcFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[ArcOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features_geojson(
        "arc", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/arcs/{arc_id}",
    description="Returns the form/info payload for a single arc (gw_fct_getinfofromid).",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_arc(
    commons: CommonsDep,
    arc_id: str = Path(..., title="Arc id", description="The unique identifier of the arc", examples=["2001"]),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("arc", arc_id)


@router.get(
    "/links",
    description=("Returns a filtered collection of links from ve_link. Filter by mapzones, sys_type, or link_type."),
    response_model=GetFeaturesResponse,
    response_model_exclude_unset=True,
)
async def get_links(
    commons: CommonsDep,
    filters: LinkFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[LinkOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features(
        "link", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/links/geojson",
    description=("Returns links as a GeoJSON FeatureCollection, with the same filters as GET /features/links."),
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_links_geojson(
    commons: CommonsDep,
    filters: LinkFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[LinkOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features_geojson(
        "link", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/links/{link_id}",
    description="Returns the form/info payload for a single link (gw_fct_getinfofromid).",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_link(
    commons: CommonsDep,
    link_id: str = Path(..., title="Link id", description="The unique identifier of the link", examples=["3001"]),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("link", link_id)


@router.get(
    "/connecs",
    description=(
        "Returns a filtered collection of connecs from ve_connec. "
        "Filter by mapzones (dma_id, sector_id, …), sys_type, connec_type, or customer_code."
    ),
    response_model=GetFeaturesResponse,
    response_model_exclude_unset=True,
)
async def get_connecs(
    commons: CommonsDep,
    filters: ConnecFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[ConnecOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features(
        "connec", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/connecs/geojson",
    description=("Returns connecs as a GeoJSON FeatureCollection, with the same filters as GET /features/connecs."),
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_connecs_geojson(
    commons: CommonsDep,
    filters: ConnecFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[ConnecOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features_geojson(
        "connec", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/connecs/{connec_id}",
    description="Returns the form/info payload for a single connec (gw_fct_getinfofromid).",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_connec(
    commons: CommonsDep,
    connec_id: str = Path(..., title="Connec id", description="The unique identifier of the connec", examples=["4001"]),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("connec", connec_id)


@router.get(
    "/gullies",
    description=(
        "Returns a filtered collection of gullies from ve_gully. "
        "UD (urban drainage) schemas only — ve_gully does not exist on water-supply (WS) schemas. "
        "Filter by mapzones, sys_type, gully_type, or gratecat_id."
    ),
    response_model=GetFeaturesResponse,
    response_model_exclude_unset=True,
)
async def get_gullies(
    commons: CommonsDep,
    filters: GullyFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[GullyOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features(
        "gully", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/gullies/geojson",
    description=(
        "Returns gullies as a GeoJSON FeatureCollection, with the same filters as GET /features/gullies. "
        "UD schemas only."
    ),
    response_model=GetFeaturesGeoJsonResponse,
    response_model_exclude_unset=True,
)
async def get_gullies_geojson(
    commons: CommonsDep,
    filters: GullyFiltersDep,
    coordinates: Optional[str] = _COORDINATES,
    order_by: Optional[GullyOrderBy] = Query(None, alias="orderBy", title="Order by"),
    order_type: Optional[Literal["ASC", "DESC"]] = _ORDER_TYPE,
    limit: int = _LIMIT,
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).list_features_geojson(
        "gully", filters, coordinates=coordinates, order_by=order_by, order_type=order_type, limit=limit
    )


@router.get(
    "/gullies/{gully_id}",
    description="Returns the form/info payload for a single gully (gw_fct_getinfofromid). UD schemas only.",
    response_model=GetFeatureResponse,
    response_model_exclude_unset=True,
)
async def get_gully(
    commons: CommonsDep,
    gully_id: str = Path(..., title="Gully id", description="The unique identifier of the gully", examples=["5001"]),
):
    ctx = get_service_context(commons)
    return await FeaturesService(ctx).get_feature("gully", gully_id)
