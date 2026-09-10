"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import ValidationError

from app.core.exceptions import InvalidParametersError
from app.schemas.common import CoordinatesModel
from app.schemas.om.mincut_models import (
    MINCUT_CAUSE_VALUES,
    MincutExecParams,
    MincutFilterFieldsModel,
    MincutPlanParams,
    MincutValveFilterFieldsModel,
)
from app.services.basic_service import BasicService
from app.services.context import ServiceContext
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict


class MincutService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)
        self._basic = BasicService(self.ctx)

    def _validate_mincut_filter_fields(self, filter_fields: str | None) -> None:
        if not filter_fields:
            return
        try:
            filter_fields_dict = json.loads(filter_fields)
            MincutFilterFieldsModel(data=filter_fields_dict)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InvalidParametersError(f"Invalid filterFields: {exc}") from exc

    def _validate_valve_filter_fields(self, mincut_id: int, filter_fields: str | None) -> None:
        if not filter_fields:
            return
        try:
            filter_fields_dict = json.loads(filter_fields)
            filter_fields_dict["result_id"] = mincut_id
            MincutValveFilterFieldsModel(data=filter_fields_dict)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InvalidParametersError(f"Invalid filterFields: {exc}") from exc

    async def get_mincuts(self, filter_fields: Optional[str] = None) -> dict:
        self._validate_mincut_filter_fields(filter_fields)
        return await self._basic.get_list("tbl_mincut_manager", filter_fields=filter_fields)

    async def get_mincut_dialog(self, mincut_id: int) -> dict:
        body = create_body_dict(device=self.ctx.device, extras={"mincutId": mincut_id}, cur_user=self.ctx.user_id)
        return await run_procedure(self.ctx, "gw_fct_getmincut", body)

    async def create_mincut(
        self,
        coordinates: CoordinatesModel,
        plan: Optional[MincutPlanParams],
        use_psectors: bool,
    ) -> dict:
        coordinates_dict = coordinates.model_dump()
        plan_dict = plan.model_dump(exclude_unset=True) if plan else {}
        if plan_dict.get("anl_cause"):
            plan_dict["anl_cause"] = MINCUT_CAUSE_VALUES.get(plan_dict["anl_cause"])
        extras = {
            "action": "mincutNetwork",
            "usePsectors": use_psectors,
            "coordinates": coordinates_dict,
            "status": "check",
            **plan_dict,
        }
        body = create_body_dict(
            device=self.ctx.device,
            client_extras={"tiled": True},
            extras=extras,
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def update_mincut(
        self,
        mincut_id: int,
        plan: Optional[MincutPlanParams],
        exec: Optional[MincutExecParams],
        use_psectors: bool,
    ) -> dict:
        plan_dict = plan.model_dump(exclude_unset=True) if plan else {}
        exec_dict = exec.model_dump(exclude_unset=True) if exec else {}
        body = create_body_dict(
            device=self.ctx.device,
            feature={"featureType": "", "tableName": "om_mincut", "id": mincut_id},
            extras={
                "action": "mincutAccept",
                "mincutClass": 1,
                "status": "check",
                "mincutId": mincut_id,
                "usePsectors": use_psectors,
                "fields": {**plan_dict, **exec_dict},
            },
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def get_valves(self, mincut_id: int, filter_fields: Optional[str] = None) -> dict:
        self._validate_valve_filter_fields(mincut_id, filter_fields)
        return await self._basic.get_list("v_om_mincut_valve", filter_fields=filter_fields)

    async def valve_unaccess(self, mincut_id: int, valve_id: int, use_psectors: bool) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            client_extras={"tiled": True},
            extras={
                "action": "mincutValveUnaccess",
                "nodeId": valve_id,
                "mincutId": mincut_id,
                "usePsectors": use_psectors,
            },
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def valve_toggle_status(self, mincut_id: int, valve_id: int, use_psectors: bool) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            client_extras={"tiled": True},
            extras={
                "action": "mincutChangeValveStatus",
                "nodeId": valve_id,
                "mincutId": mincut_id,
                "usePsectors": use_psectors,
            },
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def start_mincut(self, mincut_id: int, plan: Optional[MincutPlanParams], use_psectors: bool) -> dict:
        plan_dict = plan.model_dump(exclude_unset=True) if plan else {}
        body = create_body_dict(
            device=self.ctx.device,
            extras={"action": "mincutStart", "usePsectors": use_psectors, "mincutId": mincut_id, **plan_dict},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def end_mincut(
        self,
        mincut_id: int,
        shutoff_required: Optional[bool],
        exec: Optional[MincutExecParams],
        use_psectors: bool,
    ) -> dict:
        exec_dict = exec.model_dump(exclude_unset=True) if exec else {}
        body = create_body_dict(
            device=self.ctx.device,
            extras={
                "action": "mincutEnd",
                "mincutId": mincut_id,
                "shutoffRequired": shutoff_required,
                "usePsectors": use_psectors,
                **exec_dict,
            },
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def cancel_mincut(self, mincut_id: int) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            extras={"action": "mincutCancel", "mincutId": mincut_id},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)

    async def delete_mincut(self, mincut_id: int) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            extras={"action": "mincutDelete", "mincutId": mincut_id},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_setmincut", body)
