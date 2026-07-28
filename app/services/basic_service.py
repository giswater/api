"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Literal, Optional

from pydantic import ValidationError

from app.core.exceptions import InvalidParametersError
from app.schemas.common import CoordinatesModel, ExtentModel, FilterFieldModel, PageInfoModel
from app.services.context import ServiceContext
from app.services.procedure import empty_procedure_response, run_procedure, run_procedure_raw
from app.utils.body import create_body_dict


class BasicService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def get_feature_changes(
        self,
        feature_type: Literal["FEATURE", "ARC", "NODE", "CONNEC", "GULLY", "ELEMENT"],
        action: Literal["INSERT", "UPDATE"],
        last_feeding: date,
    ) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            feature={"feature_type": feature_type},
            extras={"action": action, "lastFeeding": last_feeding.strftime("%Y-%m-%d")},
            cur_user=self.ctx.user_id,
        )
        result = await run_procedure_raw(self.ctx, "gw_fct_featurechanges", body)
        if not result:
            return empty_procedure_response(self.ctx, message="No feature changes found", body={"feature": []})
        return result

    async def get_info_from_coordinates(self, coordinates: CoordinatesModel) -> dict:
        coordinates_dict = coordinates.model_dump()
        body = create_body_dict(
            device=self.ctx.device,
            form={"editable": "False"},
            feature={},
            extras={
                "activeLayer": "ve_node",
                "visibleLayers": [
                    "ve_cat_feature_node",
                    "ve_cat_feature_arc",
                    "ve_cat_feature_connec",
                    "ve_cat_feature_gully",
                    "ve_cat_feature_link",
                    "ve_cat_feature_element",
                    "cat_node",
                    "cat_arc",
                    "cat_connec",
                    "cat_gully",
                    "cat_link",
                    "cat_element",
                    "cat_material",
                    "ve_node",
                    "ve_man_frelem",
                    "ve_arc",
                    "ve_connec",
                    "ve_gully",
                    "ve_link",
                    "ve_pol_node",
                    "ve_pol_connec",
                    "ve_pol_gully",
                    "ve_dimensions",
                    "v_ext_municipality",
                    "v_ext_plot",
                    "v_ext_streetaxis",
                    "cat_feature",
                    "sys_feature_type",
                    "v_value_relation",
                ],
                "coordinates": coordinates_dict,
            },
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getinfofromcoordinates", body)

    async def get_features_from_polygon(
        self,
        feature_type: Literal["ARC", "NODE", "CONNEC", "GULLY", "ALL"],
        polygon_geom: str,
    ) -> dict:
        parameters = {"featureType": feature_type, "polygonGeom": polygon_geom}
        body = create_body_dict(
            device=self.ctx.device,
            form={},
            feature={},
            extras={"parameters": parameters},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getfeaturesfrompolygon", body)

    async def get_selectors(
        self,
        selector_type: Literal["selector_basic", "selector_mincut", "selector_netscenario"],
        filter_text: str,
        current_tab: Optional[str],
    ) -> dict:
        body = create_body_dict(
            device=self.ctx.device,
            form={"currentTab": current_tab},
            feature={},
            extras={"selectorType": selector_type, "filterText": filter_text},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getselectors", body)

    async def get_search(self, search_text: str) -> dict:
        parameters = {"searchText": search_text}
        body = create_body_dict(
            device=self.ctx.device,
            form={},
            feature={},
            extras={"parameters": parameters},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getsearch", body)

    async def get_arc_audit_values(self, start_date: date, end_date: date) -> dict:
        parameters = {"startDate": start_date.strftime("%Y-%m-%d"), "endDate": end_date.strftime("%Y-%m-%d")}
        body = create_body_dict(
            device=self.ctx.device,
            form={},
            feature={},
            extras={"parameters": parameters},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getarcauditvalues", body)

    def _parse_list_query_params(
        self,
        coordinates: Optional[str] = None,
        page_info: Optional[str] = None,
        filter_fields: Optional[str] = None,
    ) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
        try:
            coordinates_data = None
            if coordinates:
                coords_obj = ExtentModel(**json.loads(coordinates))
                coordinates_data = coords_obj.model_dump(mode="json", exclude_unset=True)

            page_info_data = None
            if page_info:
                page_obj = PageInfoModel(**json.loads(page_info))
                page_info_data = page_obj.model_dump(mode="json", exclude_unset=True)

            filter_fields_data = None
            if filter_fields:
                filter_fields_raw = json.loads(filter_fields)
                filter_fields_data = {
                    k: FilterFieldModel(**v).model_dump(mode="json", exclude_unset=True)
                    for k, v in filter_fields_raw.items()
                }
        except ValidationError as exc:
            raise InvalidParametersError(str(exc)) from exc

        return coordinates_data, page_info_data, filter_fields_data

    async def get_list(
        self,
        table_name: str,
        coordinates: Optional[str] = None,
        page_info: Optional[str] = None,
        filter_fields: Optional[str] = None,
    ) -> dict:
        coordinates_data, page_info_data, filter_fields_data = self._parse_list_query_params(
            coordinates, page_info, filter_fields
        )

        data = {"tableName": table_name}
        if coordinates:
            data["canvasExtend"] = coordinates_data

        body = create_body_dict(
            extras=data,
            filter_fields=filter_fields_data if filter_fields_data else {},
            page_info=page_info_data if page_info_data else {},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getlist", body)

    async def get_features(
        self,
        table_name: str,
        coordinates: Optional[str] = None,
        page_info: Optional[str] = None,
        filter_fields: Optional[str] = None,
        output_format: Literal["geojson"] = "geojson",
    ) -> dict:
        coordinates_data, page_info_data, filter_fields_data = self._parse_list_query_params(
            coordinates, page_info, filter_fields
        )

        data = {"tableName": table_name, "outputFormat": output_format}
        if coordinates:
            data["canvasExtend"] = coordinates_data

        body = create_body_dict(
            device=self.ctx.device,
            lang=self.ctx.lang,
            extras=data,
            filter_fields=filter_fields_data if filter_fields_data else {},
            page_info=page_info_data if page_info_data else {},
            cur_user=self.ctx.user_id,
        )
        return await run_procedure(self.ctx, "gw_fct_getfeatures", body)
