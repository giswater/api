"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import List, Optional, Union

from fastapi import APIRouter, Body, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.crm.crm_models import HydrometerCreate, HydrometerResponse, HydrometerUpdate
from app.services.crm_service import CrmService

router = APIRouter(prefix="/crm", tags=["CRM"])


@router.get(
    "/hydrometers",
    description="List hydrometers. Filter by code, connecId, and/or dmaId.",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def list_hydrometers(
    commons: CommonsDep,
    code: Optional[str] = Query(None, description="Hydrometer code"),
    connec_id: Optional[int] = Query(None, alias="connecId", description="Linked connec id"),
    dma_id: Optional[int] = Query(None, alias="dmaId", description="DMA id"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum rows to return"),
):
    ctx = get_service_context(commons)
    return await CrmService(ctx).list_hydrometers(code=code, connec_id=connec_id, dma_id=dma_id, limit=limit)


@router.post(
    "/hydrometers",
    description="Insert hydrometers (single or bulk)",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def insert_hydrometers(
    commons: CommonsDep,
    hydrometers: Union[HydrometerCreate, List[HydrometerCreate]] = Body(
        ..., title="Hydrometers", description="Single hydrometer or list of hydrometers to insert"
    ),
):
    """Insert one or multiple hydrometers"""
    ctx = get_service_context(commons)
    hydrometers_list = hydrometers if isinstance(hydrometers, list) else [hydrometers]
    return await CrmService(ctx).insert_hydrometers(hydrometers_list)


@router.patch(
    "/hydrometers/{code}",
    description="Update a single hydrometer by code",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def update_hydrometer(
    commons: CommonsDep,
    code: str,
    hydrometer: HydrometerUpdate = Body(
        ..., title="Hydrometer", description="Hydrometer data to update (partial data allowed)"
    ),
):
    """Update a single hydrometer identified by code"""
    ctx = get_service_context(commons)
    return await CrmService(ctx).update_hydrometer(code, hydrometer)


@router.patch(
    "/hydrometers",
    description="Update multiple hydrometers in bulk",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def update_hydrometers_bulk(
    commons: CommonsDep,
    hydrometers: List[HydrometerUpdate] = Body(
        ..., title="Hydrometers", description="List of hydrometers to update (partial data allowed)"
    ),
):
    """Update multiple hydrometers. Each must include 'code' as identifier"""
    ctx = get_service_context(commons)
    return await CrmService(ctx).update_hydrometers_bulk(hydrometers)


@router.delete(
    "/hydrometers/{code}",
    description="Delete a single hydrometer by code",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def delete_hydrometer(commons: CommonsDep, code: str):
    """Delete a single hydrometer identified by code"""
    ctx = get_service_context(commons)
    return await CrmService(ctx).delete_hydrometer(code)


@router.delete(
    "/hydrometers",
    description="Delete multiple hydrometers in bulk",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def delete_hydrometers_bulk(
    commons: CommonsDep,
    codes: List[str] = Body(..., title="Codes", description="List of hydrometer codes to delete"),
):
    """Delete multiple hydrometers by their codes"""
    ctx = get_service_context(commons)
    return await CrmService(ctx).delete_hydrometers_bulk(codes)


@router.put(
    "/hydrometers",
    description="Replace all hydrometers. Deletes all existing hydrometers and inserts the provided ones.",
    response_model=HydrometerResponse,
    response_model_exclude_unset=True,
)
async def replace_all_hydrometers(
    commons: CommonsDep,
    hydrometers: List[HydrometerCreate] = Body(
        ...,
        title="Hydrometers",
        description="Complete list of hydrometers to replace existing ones (can be empty array)",
    ),
):
    """
    Full sync mode: Replace all hydrometers with the provided list.
    This will DELETE all existing hydrometers and INSERT only the ones provided.
    Works consistently whether there are 0 or 1000+ existing hydrometers.
    """
    ctx = get_service_context(commons)
    return await CrmService(ctx).replace_all_hydrometers(hydrometers)
