"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Optional

from fastapi import APIRouter, Body, Path, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.basic.basic_models import GetListResponse
from app.schemas.om.mincut_models import (
    MincutCancelResponse,
    MincutCreateParams,
    MincutCreateResponse,
    MincutDeleteResponse,
    MincutDialogResponse,
    MincutEndParams,
    MincutEndResponse,
    MincutStartParams,
    MincutStartResponse,
    MincutToggleParams,
    MincutToggleValveStatusResponse,
    MincutToggleValveUnaccessResponse,
    MincutUpdateParams,
    MincutUpdateResponse,
)
from app.services.om.mincut_service import MincutService

router = APIRouter(prefix="/om", tags=["OM - Mincut"])


@router.get(
    "/mincuts",
    description="Returns a list of mincuts",
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_mincuts(
    commons: CommonsDep,
    filter_fields: Optional[str] = Query(None, alias="filterFields", description="Filter fields"),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).get_mincuts(filter_fields)


@router.get(
    "/mincuts/{mincut_id}",
    description="Returns the dialog data of a mincut",
    response_model=MincutDialogResponse,
    response_model_exclude_unset=True,
)
async def get_mincut_dialog(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to fetch", examples=[1]),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).get_mincut_dialog(mincut_id)


@router.post(
    "/mincuts",
    description=(
        "Create an unplanned mincut from an arc id or a map click. Provide exactly one of arcId or coordinates."
    ),
    response_model=MincutCreateResponse,
    response_model_exclude_unset=True,
)
async def create_mincut(
    commons: CommonsDep,
    payload: MincutCreateParams,
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).create_mincut(
        coordinates=payload.coordinates,
        arc_id=payload.arcId,
        plan=payload.plan,
        use_psectors=payload.use_psectors,
    )


@router.patch(
    "/mincuts/{mincut_id}",
    description="This action should be used when a mincut is already created and it needs to be updated.",
    response_model=MincutUpdateResponse,
    response_model_exclude_unset=True,
)
async def update_mincut(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to update", examples=[1]),
    payload: MincutUpdateParams = Body(default_factory=MincutUpdateParams),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).update_mincut(mincut_id, payload.plan, payload.exec, payload.use_psectors)


@router.get(
    "/mincuts/{mincut_id}/valves",
    description=("Gets the list of valves associated to a mincut."),
    response_model=GetListResponse,
    response_model_exclude_unset=True,
)
async def get_valves(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut associated to the valve", examples=[1]),
    filter_fields: Optional[str] = Query(None, alias="filterFields", description="Filter fields"),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).get_valves(mincut_id, filter_fields)


@router.post(
    "/mincuts/{mincut_id}/valves/{valve_id}/toggle-unaccess",
    description=(
        "Toggles the unaccess status of a valve associated to a mincut."
        " Also recalculates the mincut with the new status of the valve. "
        'Body is {"use_psectors": false}. A bare boolean is DEPRECATED and still accepted.'
    ),
    response_model=MincutToggleValveUnaccessResponse,
    response_model_exclude_unset=True,
)
async def valve_unaccess(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut associated to the valve", examples=[1]),
    valve_id: int = Path(..., title="Node ID", description="ID of the valve to toggle unaccessible", examples=[1114]),
    payload: MincutToggleParams = Body(default_factory=MincutToggleParams),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).valve_unaccess(mincut_id, valve_id, payload.use_psectors)


@router.post(
    "/mincuts/{mincut_id}/valves/{valve_id}/toggle-status",
    description=(
        "Updates the status of a valve associated to a mincut. "
        'Body is {"use_psectors": false}. A bare boolean is DEPRECATED and still accepted.'
    ),
    response_model=MincutToggleValveStatusResponse,
    response_model_exclude_unset=True,
)
async def valve_toggle_status(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut associated to the valve", examples=[1]),
    valve_id: int = Path(..., title="Valve ID", description="ID of the valve to update", examples=[1114]),
    payload: MincutToggleParams = Body(default_factory=MincutToggleParams),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).valve_toggle_status(mincut_id, valve_id, payload.use_psectors)


@router.post(
    "/mincuts/{mincut_id}/start",
    description=(
        "This action should be used when the mincut is ready to be executed. "
        "The system will start the mincut and the water supply will be interrupted on the affected zone."
    ),
    response_model=MincutStartResponse,
    response_model_exclude_unset=True,
)
async def start_mincut(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to start", examples=[1]),
    payload: MincutStartParams = Body(default_factory=MincutStartParams),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).start_mincut(mincut_id, payload.plan, payload.use_psectors)


@router.post(
    "/mincuts/{mincut_id}/end",
    description=(
        "This action should be used when the mincut has been executed and the water supply is restored. "
        "The system will end the mincut and the affected zone will be restored."
    ),
    response_model=MincutEndResponse,
    response_model_exclude_unset=True,
)
async def end_mincut(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to end", examples=[1]),
    payload: MincutEndParams = Body(default_factory=MincutEndParams),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).end_mincut(mincut_id, payload.shutoff_required, payload.exec, payload.use_psectors)


@router.post(
    "/mincuts/{mincut_id}/cancel",
    description=(
        "Cancels the mincut when the repair is not feasible, "
        "nullifying the planned cut while keeping the issue recorded for future resolution. "
        "This ensures proper outage management and prevents data loss."
    ),
    response_model=MincutCancelResponse,
    response_model_exclude_unset=True,
)
async def cancel_mincut(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to cancel", examples=[1]),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).cancel_mincut(mincut_id)


@router.delete(
    "/mincuts/{mincut_id}",
    description="Deletes the mincut from the system. This action should be used when the mincut is no longer needed.",
    response_model=MincutDeleteResponse,
    response_model_exclude_unset=True,
)
async def delete_mincut(
    commons: CommonsDep,
    mincut_id: int = Path(..., title="Mincut ID", description="ID of the mincut to delete", examples=[1]),
):
    ctx = get_service_context(commons)
    return await MincutService(ctx).delete_mincut(mincut_id)
