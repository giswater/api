"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from app.db.execution import execute_sql
from app.services.context import ServiceContext
from app.services.helpers import accepted_data_response


class WaterbalanceService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def get_waterbalance(self, dma_id: list[int] | None = None) -> dict:
        sql = """
    WITH sel_expl AS (
            SELECT selector_expl.expl_id
            FROM {schema}.selector_expl
            WHERE selector_expl.cur_user = CURRENT_USER
        )
        SELECT
            w.node_id,
            w.mapzone_id AS dma_id,
            w.flow_sign,
            json_build_object(
                'node_id', w.node_id,
                'node_type', cn.node_type,
                'node_geometry', jsonb_build_object(
                    'type', 'FeatureCollection',
                    'features', jsonb_build_array(
                        jsonb_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(st_transform(n.the_geom, 4326))::jsonb,
                            'properties', jsonb_build_object()
                        )
                    )
                )
            ) AS node,
            json_build_object(
                'dma_id', d.dma_id,
                'dma_stylesheet', d.stylesheet::json ->> 'featureColor'::text,
                'dma_geometry', jsonb_build_object(
                    'type', 'FeatureCollection',
                    'features', jsonb_build_array(
                        jsonb_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(st_transform(d.the_geom, 4326))::jsonb,
                            'properties', jsonb_build_object()
                        )
                    )
                )
            ) AS dma,
            jsonb_build_object(
                'type', 'FeatureCollection',
                'features', jsonb_build_array(
                    jsonb_build_object(
                        'type', 'Feature',
                        'geometry',
                        ST_AsGeoJSON(
                            st_transform(
                                st_makeline(n.the_geom, st_centroid(d.the_geom)), 4326
                            )
                        )::jsonb,
                        'properties', jsonb_build_object()
                    )
                )
            ) AS line
        FROM {schema}.ve_dma d
        JOIN {schema}.mapzone_graph w ON w.mapzone_id = d.dma_id
        JOIN {schema}.node n ON w.node_id = n.node_id
        JOIN {schema}.cat_node cn ON cn.id = n.nodecat_id
        WHERE EXISTS (
            SELECT 1
            FROM sel_expl
            WHERE sel_expl.expl_id = ANY (d.expl_id)
        )
        AND w.mapzone_type = 'DMA'
        AND d.dma_id > 0
        AND n.the_geom IS NOT NULL
        AND d.the_geom IS NOT NULL
    """
        parameters = None
        if dma_id:
            sql += " AND d.dma_id = ANY(%s)"
            parameters = (dma_id,)
        waterbalance = await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            sql,
            parameters=parameters,
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )
        return await accepted_data_response(
            self.ctx, "Fetched waterbalance successfully", {"waterbalance": waterbalance}
        )
