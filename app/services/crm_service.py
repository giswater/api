"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from fastapi import HTTPException
from psycopg import sql
from psycopg.rows import dict_row

from app.core.exceptions import DatabaseUnavailableError
from app.db.execution import execute_sql_select
from app.schemas.crm.crm_models import HydrometerCreate, HydrometerUpdate
from app.services.context import ServiceContext
from app.services.helpers import accepted_data_response
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict


class CrmService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def _set_hydrometers(self, action: str, hydrometers_data: list[dict]) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            extras={"action": action, "hydrometers": hydrometers_data},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_set_hydrometers", body)

    async def list_hydrometers(
        self,
        *,
        code: str | None = None,
        connec_id: int | None = None,
        dma_id: int | None = None,
        limit: int = 100,
    ) -> dict:
        if connec_id is None and dma_id is None:
            clauses: list[str] = []
            params: list = []
            if code:
                clauses.append("code = %s")
                params.append(code)
            where = " AND ".join(clauses) if clauses else "TRUE"
            where = f"{where} LIMIT {int(limit)}"
            rows = await execute_sql_select(
                self.ctx.logger,
                self.ctx.db_manager,
                table_name="v_hydrometer",
                columns=None,
                where_clause=where,
                parameters=tuple(params) if params else None,
                schema=self.ctx.schema,
                user=self.ctx.user_id,
                db_role=self.ctx.db_role,
            )
        else:
            rows = await self._list_hydrometers_joined(code=code, connec_id=connec_id, dma_id=dma_id, limit=limit)
        return await accepted_data_response(
            self.ctx,
            "Fetched hydrometers successfully",
            {"hydrometers": rows, "count": len(rows)},
        )

    async def _list_hydrometers_joined(
        self,
        *,
        code: str | None,
        connec_id: int | None,
        dma_id: int | None,
        limit: int,
    ) -> list[dict]:
        schema_name = self.ctx.schema
        clauses = ["TRUE"]
        params: list = []
        if code:
            clauses.append("h.code = %s")
            params.append(code)
        if connec_id is not None:
            clauses.append("f.feature_id = %s")
            params.append(connec_id)
        if dma_id is not None:
            clauses.append("c.dma_id = %s")
            params.append(dma_id)
        query = sql.SQL(
            "SELECT h.* FROM {schema}.v_hydrometer h "
            "LEFT JOIN {schema}.vf_hydrometer f ON f.hydrometer_id = h.hydrometer_id "
            "LEFT JOIN {schema}.ve_connec c ON c.connec_id = f.feature_id "
            "WHERE {where} LIMIT {limit}"
        ).format(
            schema=sql.Identifier(schema_name),
            where=sql.SQL(" AND ").join(sql.SQL(c) for c in clauses),
            limit=sql.Literal(int(limit)),
        )
        async with self.ctx.db_manager.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            try:
                async with conn.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(query, tuple(params))
                    return await cursor.fetchall()
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

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
