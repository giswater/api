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
from app.db.execution import execute_sql
from app.schemas.common import CoordinatesModel
from app.schemas.om.mincut_models import (
    MINCUT_CAUSE_VALUES,
    GetMincutData,
    GetMincutsData,
    MincutExecParams,
    MincutFilterFieldsModel,
    MincutPlanParams,
    MincutValveFilterFieldsModel,
)
from app.services.basic_service import BasicService
from app.services.context import ServiceContext
from app.services.helpers import accepted_v2_response
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict

_OM_MINCUT_GEOM_COLUMNS = ("anl_the_geom", "exec_the_geom", "polygon_the_geom")


def _init_sql(table: str) -> str:
    return f"""
        (SELECT CASE
            WHEN g IS NULL THEN NULL
            ELSE jsonb_build_object('x', ST_X(g), 'y', ST_Y(g))
         END
         FROM (SELECT ST_Transform({table}.anl_the_geom, 4326) AS g) p)
    """


def _bbox_sql(table: str) -> str:
    return f"""
        (SELECT CASE
            WHEN e IS NULL THEN NULL
            ELSE jsonb_build_object(
                'x1', ST_XMin(e),
                'y1', ST_YMin(e),
                'x2', ST_XMax(e),
                'y2', ST_YMax(e)
            )
         END
         FROM (
            SELECT ST_Extent(ST_Transform(g, 4326)) AS e
            FROM (
                SELECT a.the_geom AS g FROM {{schema}}.om_mincut_arc a WHERE a.result_id = {table}.id
                UNION ALL
                SELECT v.the_geom FROM {{schema}}.om_mincut_valve v WHERE v.result_id = {table}.id
                UNION ALL
                SELECT {table}.anl_the_geom
                UNION ALL
                SELECT {table}.exec_the_geom
                UNION ALL
                SELECT {table}.polygon_the_geom
            ) geoms
            WHERE g IS NOT NULL
         ) extent)
    """


def _mincut_json(table: str) -> str:
    geoms = ", ".join(
        f"'{col}', ST_AsGeoJSON(ST_Transform({table}.{col}, 4326))::jsonb" for col in _OM_MINCUT_GEOM_COLUMNS
    )
    return f"""
        (to_jsonb({table}) - %s::text[])
        || CASE WHEN params.include_geometry THEN jsonb_build_object({geoms})
           ELSE jsonb_build_object() END
        || jsonb_build_object(
            'init', {_init_sql(table)},
            'bbox', {_bbox_sql(table)}
        )
    """


def _child_agg(table: str, order_by: str) -> str:
    return f"""
        (SELECT COALESCE(jsonb_agg(
            (to_jsonb(t) - 'result_id' - 'the_geom')
            || CASE WHEN params.include_geometry THEN jsonb_build_object(
                'the_geom', ST_AsGeoJSON(ST_Transform(t.the_geom, 4326))::jsonb
            ) ELSE jsonb_build_object() END
            ORDER BY t.{order_by}
        ), '[]'::jsonb)
         FROM {{schema}}.{table} t
         WHERE t.result_id = m.id)
    """


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

    async def get_mincuts_v2(self, include_geometry: bool = False) -> dict:
        sql = f"""
            WITH params AS (SELECT %s::boolean AS include_geometry)
            SELECT {_mincut_json("m")} AS mincut
            FROM {{schema}}.om_mincut m
            CROSS JOIN params
        """
        rows = await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            sql,
            parameters=(include_geometry, list(_OM_MINCUT_GEOM_COLUMNS)),
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )
        payload = GetMincutsData.model_validate({"mincuts": [row["mincut"] for row in rows]})
        return await accepted_v2_response(
            self.ctx,
            "Fetched mincuts successfully",
            payload.model_dump(mode="json", exclude_unset=True),
        )

    async def get_mincut_v2(self, mincut_id: int, include_geometry: bool = False) -> dict:
        sql = f"""
            WITH params AS (SELECT %s::boolean AS include_geometry)
            SELECT
                {_mincut_json("m")} AS mincut,
                {_child_agg("om_mincut_arc", "arc_id")} AS arcs,
                {_child_agg("om_mincut_valve", "node_id")} AS valves,
                {_child_agg("om_mincut_node", "node_id")} AS nodes,
                {_child_agg("om_mincut_connec", "connec_id")} AS connecs,
                (SELECT COALESCE(jsonb_agg(to_jsonb(h) - 'result_id' ORDER BY h.id), '[]'::jsonb)
                 FROM {{schema}}.om_mincut_hydrometer h WHERE h.result_id = m.id) AS hydrometers,
                (SELECT COALESCE(
                    jsonb_agg(omc.mincut_id) FILTER (WHERE omc.mincut_id <> m.id),
                    '[]'::jsonb)
                 FROM {{schema}}.om_mincut_conflict omc
                 WHERE omc.id = (
                    SELECT id FROM {{schema}}.om_mincut_conflict WHERE mincut_id = m.id LIMIT 1
                 )) AS conflicts
            FROM {{schema}}.om_mincut m
            CROSS JOIN params
            WHERE m.id = %s
        """
        rows = await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            sql,
            parameters=(include_geometry, list(_OM_MINCUT_GEOM_COLUMNS), mincut_id),
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )
        if not rows:
            raise LookupError(f"Mincut {mincut_id} not found")
        row = rows[0]
        payload = GetMincutData.model_validate(
            {
                "mincut": row["mincut"],
                "arcs": row["arcs"] or [],
                "valves": row["valves"] or [],
                "nodes": row["nodes"] or [],
                "connecs": row["connecs"] or [],
                "hydrometers": row["hydrometers"] or [],
                "conflicts": row["conflicts"] or [],
            }
        )
        return await accepted_v2_response(
            self.ctx,
            "Fetched mincut successfully",
            payload.model_dump(mode="json", exclude_unset=True),
        )

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
