"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import ValidationError

from app.core.exceptions import InvalidParametersError
from app.schemas.common import ExtentModel
from app.schemas.features.feature_models import (
    FeatureFilters,
    FeatureType,
    get_feature_id_column,
    get_feature_table,
    get_feature_type_param,
)
from app.services.context import ServiceContext
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict

# gw_fct_getfeatures only applies LIMIT when device != 4 (QGIS Desktop).
_FEATURES_DEVICE_FALLBACK = 5
_DEFAULT_LIMIT = 500


class FeaturesService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    def _effective_device(self) -> int:
        return self.ctx.device if self.ctx.device != 4 else _FEATURES_DEVICE_FALLBACK

    def _parse_coordinates(self, coordinates: Optional[str]) -> Optional[dict]:
        if not coordinates:
            return None
        try:
            return ExtentModel(**json.loads(coordinates)).model_dump(mode="json", exclude_unset=True)
        except (ValidationError, json.JSONDecodeError, TypeError) as exc:
            raise InvalidParametersError(str(exc)) from exc

    async def _list_features(
        self,
        feature_type: FeatureType,
        output_format: Literal["list", "geojson"],
        filters: FeatureFilters,
        coordinates: Optional[str] = None,
        order_by: Optional[str] = None,
        order_type: Optional[Literal["ASC", "DESC"]] = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict:
        coordinates_data = self._parse_coordinates(coordinates)
        filter_fields = filters.to_filter_fields()

        page_info: dict = {"limit": limit}
        if order_by:
            page_info["orderBy"] = order_by
            page_info["orderType"] = order_type or "ASC"

        extras: dict = {
            "featureType": get_feature_type_param(feature_type),
            "outputFormat": output_format,
        }
        if coordinates_data is not None:
            extras["canvasExtend"] = coordinates_data

        body = create_body_dict(
            device=self._effective_device(),
            lang=self.ctx.lang,
            extras=extras,
            filter_fields=filter_fields,
            page_info=page_info,
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getfeatures", body)

    async def list_features(
        self,
        feature_type: FeatureType,
        filters: FeatureFilters,
        coordinates: Optional[str] = None,
        order_by: Optional[str] = None,
        order_type: Optional[Literal["ASC", "DESC"]] = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict:
        return await self._list_features(
            feature_type,
            "list",
            filters,
            coordinates=coordinates,
            order_by=order_by,
            order_type=order_type,
            limit=limit,
        )

    async def list_features_geojson(
        self,
        feature_type: FeatureType,
        filters: FeatureFilters,
        coordinates: Optional[str] = None,
        order_by: Optional[str] = None,
        order_type: Optional[Literal["ASC", "DESC"]] = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict:
        return await self._list_features(
            feature_type,
            "geojson",
            filters,
            coordinates=coordinates,
            order_by=order_by,
            order_type=order_type,
            limit=limit,
        )

    async def _get_feature_by_id(
        self,
        feature_type: FeatureType,
        feature_id: str,
        output_format: Literal["list", "geojson"],
    ) -> tuple[dict, dict]:
        body = create_body_dict(
            device=self._effective_device(),
            lang=self.ctx.lang,
            extras={
                "featureType": get_feature_type_param(feature_type),
                "outputFormat": output_format,
            },
            filter_fields={get_feature_id_column(feature_type): {"value": [feature_id], "filterSign": "IN"}},
            page_info={"limit": 1},
            cur_user=self.ctx.user_id,
        )
        result = await run_procedure(self.ctx, "gw_fct_getfeatures", body)
        features = ((result.get("body") or {}).get("data") or {}).get("features") or []
        if not features:
            raise LookupError(f"{feature_type} '{feature_id}' not found")
        return result, features[0]

    async def get_feature_fields(self, feature_type: FeatureType, feature_id: str) -> dict:
        result, feature = await self._get_feature_by_id(feature_type, feature_id, "list")
        result["body"]["data"] = {"feature": feature}
        return result

    async def get_feature_geojson(self, feature_type: FeatureType, feature_id: str) -> dict:
        result, feature = await self._get_feature_by_id(feature_type, feature_id, "geojson")
        result["body"]["data"] = feature
        return result

    async def get_feature_form(self, feature_type: FeatureType, feature_id: str) -> dict:
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
