"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.db.execution import execute_sql
from app.schemas.crm.crm_models import HydrometerCreate, HydrometerUpdate
from app.services.context import ServiceContext
from app.services.helpers import accepted_data_response
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict

# REST camelCase → keys gw_fct_set_hydrometers actually reads.
_REST_TO_FCT = {
    "code": "code",
    "hydroNumber": "hydro_number",
    "customerCode": "feature_customer_code",
    "link": "link",
    "stateId": "state_id",
    "catalogId": "catalog_id",
    "categoryId": "category_id",
    "priorityId": "priority_id",
    "exploitation": "exploitation",
    "startDate": "start_date",
    "endDate": "end_date",
    "updateDate": "update_date",
    "shutdownDate": "shutdown_date",
}


def _split_total_count(rows: list[dict]) -> tuple[list[dict], int]:
    if not rows:
        return [], 0
    total = int(rows[0].get("total_count") or 0)
    out = []
    for row in rows:
        item = dict(row)
        item.pop("total_count", None)
        out.append(item)
    return out, total


class CrmService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def _sql(self, query: str, parameters: tuple | None = None) -> list[dict]:
        return await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            query,
            parameters=parameters,
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )

    async def _customer_code_for_connec(self, connec_id: int) -> str:
        rows = await self._sql(
            "SELECT customer_code FROM {schema}.ve_connec WHERE connec_id = %s LIMIT 1",
            (connec_id,),
        )
        code = rows[0].get("customer_code") if rows else None
        if not code:
            raise HTTPException(
                status_code=400,
                detail=f"connecId {connec_id} has no customer_code on ve_connec",
            )
        return str(code)

    async def _to_fct_hydrometer(self, row: dict) -> dict:
        mapped = {fct_key: row[rest] for rest, fct_key in _REST_TO_FCT.items() if rest in row}
        if "feature_customer_code" not in mapped and "connecId" in row:
            mapped["feature_customer_code"] = await self._customer_code_for_connec(int(row["connecId"]))
        return mapped

    async def _set_hydrometers(self, action: str, hydrometers_data: list[dict]) -> dict:
        mapped = [await self._to_fct_hydrometer(row) for row in hydrometers_data]
        body = create_body_dict(
            device=self.ctx.device,
            extras={"action": action, "hydrometers": mapped},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_set_hydrometers", body)

    async def list_hydrometers(
        self,
        *,
        code: str | None = None,
        connec_id: int | None = None,
        dma_id: int | None = None,
        mincut_id: int | None = None,
        customer_code: str | None = None,
        limit: int = 100,
    ) -> dict:
        clauses = ["TRUE"]
        params: list = []
        if code:
            clauses.append("h.code = %s")
            params.append(code)
        if connec_id is not None:
            clauses.append("c.connec_id = %s")
            params.append(connec_id)
        if dma_id is not None:
            clauses.append("c.dma_id = %s")
            params.append(dma_id)
        if customer_code:
            clauses.append("h.feature_customer_code = %s")
            params.append(customer_code)
        if mincut_id is not None:
            clauses.append(
                "h.hydrometer_id IN (SELECT hydrometer_id FROM {schema}.om_mincut_hydrometer WHERE result_id = %s)"
            )
            params.append(mincut_id)
        where = " AND ".join(clauses)
        # Link is v_hydrometer.feature_customer_code → ve_connec.customer_code.
        # vf_hydrometer is a selector/state-filtered view; do not use it here.
        query = (
            "SELECT h.*, c.connec_id, c.dma_id, "
            "COALESCE(c.customer_code, h.feature_customer_code) AS customer_code, "
            "count(*) OVER () AS total_count "
            "FROM {schema}.v_hydrometer h "
            "LEFT JOIN {schema}.ve_connec c ON c.customer_code::text = h.feature_customer_code::text "
            f"WHERE {where} LIMIT {int(limit)}"
        )
        rows, total = _split_total_count(await self._sql(query, tuple(params) if params else None))
        return await accepted_data_response(
            self.ctx,
            "Fetched hydrometers successfully",
            {"hydrometers": rows, "count": total},
        )

    async def insert_hydrometers(self, hydrometers: list[HydrometerCreate]) -> dict:
        hydrometers_data = [h.model_dump(mode="json", exclude_unset=True) for h in hydrometers]
        return await self._set_hydrometers("INSERT", hydrometers_data)

    async def update_hydrometer(self, code: str, hydrometer: HydrometerUpdate) -> dict:
        hydrometer_dict = hydrometer.model_dump(mode="json", exclude_unset=True)
        hydrometer_dict["code"] = code
        return await self._set_hydrometers("UPDATE", [hydrometer_dict])

    async def update_hydrometers_bulk(self, hydrometers: list[HydrometerUpdate]) -> dict:
        hydrometers_data = [h.model_dump(mode="json", exclude_unset=True) for h in hydrometers]
        return await self._set_hydrometers("UPDATE", hydrometers_data)

    async def delete_hydrometer(self, code: str) -> dict:
        return await self._set_hydrometers("DELETE", [{"code": code}])

    async def delete_hydrometers_bulk(self, codes: list[str]) -> dict:
        hydrometers_data = [{"code": code} for code in codes]
        return await self._set_hydrometers("DELETE", hydrometers_data)

    async def replace_all_hydrometers(self, hydrometers: list[HydrometerCreate]) -> dict:
        hydrometers_data = [h.model_dump(mode="json", exclude_unset=True) for h in hydrometers]
        return await self._set_hydrometers("REPLACE", hydrometers_data)
