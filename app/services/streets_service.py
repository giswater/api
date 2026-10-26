"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.db.execution import execute_sql
from app.services.context import ServiceContext
from app.services.helpers import accepted_data_response

_STREET_VIEWS = ("ve_streetaxis", "ve_ext_streetaxis", "v_streetaxis", "v_ext_streetaxis")
_ADDRESS_VIEWS = ("ve_address", "ve_ext_address", "v_address", "v_ext_address")
_MUNI_VIEWS = ("ve_municipality", "ve_ext_municipality", "v_municipality", "v_ext_municipality", "ext_municipality")
_ALL_VIEWS = _STREET_VIEWS + _ADDRESS_VIEWS + _MUNI_VIEWS


def _drop_none(row: dict) -> dict:
    return {key: value for key, value in row.items() if value is not None}


def _first_present(present: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((name for name in candidates if name in present), None)


def _sql_col(arc_cols: set[str], name: str, expr: str | None = None) -> str:
    if name not in arc_cols:
        return f"NULL AS {name}"
    return expr or f"arc.{name}"


def _cap_page(rows: list, limit: int) -> tuple[list, bool]:
    """Drop the LIMIT+1 probe row. ``truncated`` is true only when that row existed."""
    if len(rows) > limit:
        return rows[:limit], True
    return rows, False


class StreetsService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def _execute(self, sql_query: str, parameters: tuple | None = None) -> list[dict]:
        return await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            sql_query,
            parameters=parameters,
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )

    async def _relations(self) -> dict[str, str | None]:
        rows = await self._execute(
            "SELECT c.relname AS name FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind IN ('v', 'm', 'r') AND c.relname = ANY(%s)",
            (self.ctx.schema, list(_ALL_VIEWS)),
        )
        present = {row["name"] for row in rows if row.get("name")}
        street = _first_present(present, _STREET_VIEWS)
        if street is None:
            raise HTTPException(status_code=500, detail="No streetaxis view in this schema")
        return {
            "street": street,
            "address": _first_present(present, _ADDRESS_VIEWS),
            "muni": _first_present(present, _MUNI_VIEWS),
        }

    async def list_streets(self, q: str, limit: int) -> dict:
        views = await self._relations()
        muni_join = f"LEFT JOIN {{schema}}.{views['muni']} m ON m.muni_id = s.muni_id" if views["muni"] else ""
        muni_name = "m.name AS muni_name" if views["muni"] else "NULL::text AS muni_name"
        muni_group = ", m.name" if views["muni"] else ""
        muni_filter = " OR COALESCE(m.name, '') ILIKE %s" if views["muni"] else ""
        sql_query = f"""
        SELECT
            s.id::text AS id,
            s.name,
            s.muni_id,
            {muni_name},
            ST_XMin(ST_Extent(s.the_geom))::float8 AS x1,
            ST_YMin(ST_Extent(s.the_geom))::float8 AS y1,
            ST_XMax(ST_Extent(s.the_geom))::float8 AS x2,
            ST_YMax(ST_Extent(s.the_geom))::float8 AS y2
        FROM {{schema}}.{views["street"]} s
        {muni_join}
        WHERE s.name ILIKE %s{muni_filter}
        GROUP BY s.id, s.name, s.muni_id{muni_group}
        ORDER BY s.name, s.id
        LIMIT %s
        """
        pattern = f"%{q}%"
        params: list = [pattern]
        if views["muni"]:
            params.append(pattern)
        params.append(limit + 1)
        streets = [_drop_none(dict(row)) for row in await self._execute(sql_query, tuple(params))]
        streets, truncated = _cap_page(streets, limit)
        return await accepted_data_response(
            self.ctx,
            "Fetched streets successfully",
            {"streets": streets, "count": len(streets), "truncated": truncated},
        )

    async def list_street_arcs(
        self,
        street_id: str,
        house_number: str | None,
        buffer_meters: float,
        limit: int,
    ) -> dict:
        views = await self._relations()
        street_rows = await self._street_row(views, street_id)
        if not street_rows:
            raise LookupError(f"Street '{street_id}' not found")
        street = _drop_none(dict(street_rows[0]))
        arc_cols = await self._arc_columns()
        sql_query, params = self._arcs_sql(views, arc_cols, street_id, house_number, buffer_meters, limit + 1)
        arcs = [_drop_none(dict(row)) for row in await self._execute(sql_query, params)]
        arcs, truncated = _cap_page(arcs, limit)
        return await accepted_data_response(
            self.ctx,
            "Fetched street arcs successfully",
            {"street": street, "arcs": arcs, "count": len(arcs), "truncated": truncated},
        )

    async def _street_row(self, views: dict[str, str | None], street_id: str) -> list[dict]:
        muni_join = f"LEFT JOIN {{schema}}.{views['muni']} m ON m.muni_id = s.muni_id" if views["muni"] else ""
        muni_name = "m.name AS muni_name" if views["muni"] else "NULL::text AS muni_name"
        muni_group = ", m.name" if views["muni"] else ""
        sql_query = f"""
        SELECT
            s.id::text AS id,
            s.name,
            s.muni_id,
            {muni_name},
            ST_XMin(ST_Extent(s.the_geom))::float8 AS x1,
            ST_YMin(ST_Extent(s.the_geom))::float8 AS y1,
            ST_XMax(ST_Extent(s.the_geom))::float8 AS x2,
            ST_YMax(ST_Extent(s.the_geom))::float8 AS y2
        FROM {{schema}}.{views["street"]} s
        {muni_join}
        WHERE s.id::text = %s
        GROUP BY s.id, s.name, s.muni_id{muni_group}
        """
        return await self._execute(sql_query, (street_id,))

    async def _arc_columns(self) -> set[str]:
        rows = await self._execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 've_arc'",
            (self.ctx.schema,),
        )
        return {row["column_name"] for row in rows if row.get("column_name")}

    def _arcs_sql(
        self,
        views: dict[str, str | None],
        arc_cols: set[str],
        street_id: str,
        house_number: str | None,
        buffer_meters: float,
        limit: int,
    ) -> tuple[str, tuple]:
        addr_join = ""
        distance_select = "NULL::float8 AS distance_m"
        order_distance = ""
        extra: list = []
        if house_number and views["address"]:
            addr_join = f"""
            LEFT JOIN LATERAL (
                SELECT a.the_geom
                FROM {{schema}}.{views["address"]} a
                WHERE a.streetaxis_id::text = %s AND a.postnumber::text = %s
                ORDER BY a.id
                LIMIT 1
            ) addr ON TRUE
            """
            distance_select = "ST_Distance(ST_Centroid(arc.the_geom), addr.the_geom)::float8 AS distance_m"
            order_distance = "addr.the_geom IS NULL, ST_Distance(ST_Centroid(arc.the_geom), addr.the_geom),"
            extra = [street_id, house_number]
        sql_query = f"""
        WITH street AS (
            SELECT
                s.id,
                ST_LineMerge(ST_Union(s.the_geom)) AS geom
            FROM {{schema}}.{views["street"]} s
            WHERE s.id::text = %s
            GROUP BY s.id
        )
        SELECT
            arc.arc_id,
            {_sql_col(arc_cols, "code")},
            {_sql_col(arc_cols, "sys_type")},
            {_sql_col(arc_cols, "state")},
            ST_X(ST_Centroid(arc.the_geom))::float8 AS x,
            ST_Y(ST_Centroid(arc.the_geom))::float8 AS y,
            {_sql_col(arc_cols, "arc_type")},
            {_sql_col(arc_cols, "cat_dnom")},
            {_sql_col(arc_cols, "cat_matcat_id")},
            {_sql_col(arc_cols, "node_1")},
            {_sql_col(arc_cols, "node_2")},
            {_sql_col(arc_cols, "gis_length", "arc.gis_length::float8 AS gis_length")},
            CASE
                WHEN arc.streetaxis_id::text = street.id::text
                     AND %s > 0 AND ST_DWithin(arc.the_geom, street.geom, %s) THEN 'both'
                WHEN arc.streetaxis_id::text = street.id::text THEN 'attribute'
                ELSE 'spatial'
            END AS match,
            {distance_select}
        FROM street
        JOIN {{schema}}.ve_arc arc ON (
            arc.streetaxis_id::text = street.id::text
            OR (%s > 0 AND ST_DWithin(arc.the_geom, street.geom, %s))
        )
        {addr_join}
        ORDER BY
            {order_distance}
            CASE
                WHEN GeometryType(street.geom) IN ('LINESTRING', 'LINESTRINGZ')
                THEN ST_LineLocatePoint(street.geom, ST_ClosestPoint(street.geom, ST_Centroid(arc.the_geom)))
            END,
            arc.arc_id
        LIMIT %s
        """
        buf = buffer_meters
        return sql_query, (street_id, buf, buf, buf, buf, *extra, limit)
