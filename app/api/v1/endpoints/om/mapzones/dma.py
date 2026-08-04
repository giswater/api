"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi import APIRouter, Path

from app.schemas.om.dma_models import (
    GetDmasResponse,
    GetDmaHydrometersResponse,
    GetDmaParametersResponse,
    GetDmaConnecsResponse,
)
from app.schemas.om.mapzone_models import GetMacrodmasResponse
from app.api.deps import CommonsDep, get_service_context
from app.services.om.dma_service import DmaService

router = APIRouter(prefix="/om", tags=["OM - District Metered Areas"])


@router.get(
    "/dmas",
    description="Returns a collection of DMAs.",
    response_model=GetDmasResponse,
    response_model_exclude_unset=True,
)
async def get_dmas(commons: CommonsDep):
    ctx = get_service_context(commons)
    return await DmaService(ctx).get_dmas()


@router.get(
    "/macrodmas",
    description="Returns a collection of macrodmas.",
    response_model=GetMacrodmasResponse,
    response_model_exclude_unset=True,
)
async def get_macrodmas(commons: CommonsDep):
    ctx = get_service_context(commons)
    return await DmaService(ctx).get_macrodmas()


@router.get(
    "/dmas/{dma_id}/hydrometers",
    description=(
        "Returns a collection of hydrometers within a specific DMA, "
        "providing details on their location, status, and measurement data."
    ),
    response_model=GetDmaHydrometersResponse,
    response_model_exclude_unset=True,
)
async def get_dma_hydrometers(
    commons: CommonsDep,
    dma_id: int = Path(
        ..., title="DMA ID", description="The unique identifier of the DMA for which to fetch hydrometers", examples=[1]
    ),
):
    ctx = get_service_context(commons)
    return await DmaService(ctx).get_dma_hydrometers(dma_id)


@router.get(
    "/dmas/{dma_id}/parameters",
    description=(
        "Retrieves specific parameters within a DMA, excluding geometry. "
        "Provides consumption data, network information, and other key metrics "
        "for performance analysis over a selected period."
    ),
    response_model=GetDmaParametersResponse,
    response_model_exclude_unset=True,
)
async def get_dma_parameters(
    commons: CommonsDep,
    dma_id: int = Path(
        ..., title="DMA ID", description="The unique identifier of the DMA for which to fetch parameters", examples=[1]
    ),
):
    ctx = get_service_context(commons)
    return await DmaService(ctx).get_dma_parameters(dma_id)


@router.get(
    "/dmas/{dma_id}/connecs",
    description=(
        "Deprecated: prefer GET /features/connecs?dma_id={dma_id}. "
        "Returns a collection of connecs within a specific DMA, providing details from ve_connec."
    ),
    deprecated=True,
    response_model=GetDmaConnecsResponse,
    response_model_exclude_unset=True,
)
async def get_dma_connecs(
    commons: CommonsDep,
    dma_id: int = Path(
        ..., title="DMA ID", description="The unique identifier of the DMA for which to fetch connecs", examples=[1]
    ),
):
    ctx = get_service_context(commons)
    return await DmaService(ctx).get_dma_connecs(dma_id)
