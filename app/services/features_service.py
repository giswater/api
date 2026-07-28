"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from typing import Optional

from app.schemas.features.feature_models import (
    FeatureType,
    get_feature_id_column,
    get_feature_table,
)
from app.services.basic_service import BasicService
from app.services.context import ServiceContext
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict


class FeaturesService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)
        self._basic = BasicService(self.ctx)

    async def get_features(
        self,
        feature_type: FeatureType,
        coordinates: Optional[str] = None,
        page_info: Optional[str] = None,
        filter_fields: Optional[str] = None,
    ) -> dict:
        return await self._basic.get_list(
            get_feature_table(feature_type),
            coordinates=coordinates,
            page_info=page_info,
            filter_fields=filter_fields,
        )

    async def get_feature(self, feature_type: FeatureType, feature_id: str) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            lang=self.ctx.lang,
            feature={
                "tableName": get_feature_table(feature_type),
                "id": feature_id,
                "idName": get_feature_id_column(feature_type),
            },
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getinfofromid", body)

    async def get_features_geojson(
        self,
        feature_type: FeatureType,
        coordinates: Optional[str] = None,
        page_info: Optional[str] = None,
        filter_fields: Optional[str] = None,
    ) -> dict:
        return await self._basic.get_features(
            get_feature_table(feature_type),
            coordinates=coordinates,
            page_info=page_info,
            filter_fields=filter_fields,
        )
