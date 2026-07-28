"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from ..common import BaseAPIResponse, Body, Data, PageInfoReturnModel

FeatureType = Literal["node", "arc", "link", "connec", "gully"]

FEATURE_TABLE_MAP: Dict[FeatureType, str] = {
    "node": "ve_node",
    "arc": "ve_arc",
    "link": "ve_link",
    "connec": "ve_connec",
    "gully": "ve_gully",
}

FEATURE_ID_MAP: Dict[FeatureType, str] = {
    "node": "node_id",
    "arc": "arc_id",
    "link": "link_id",
    "connec": "connec_id",
    "gully": "gully_id",
}


def get_feature_table(feature_type: FeatureType) -> str:
    return FEATURE_TABLE_MAP[feature_type]


def get_feature_id_column(feature_type: FeatureType) -> str:
    return FEATURE_ID_MAP[feature_type]


class GetFeatureResponse(BaseAPIResponse[Body[Data]]):
    """Response model for a single feature form (gw_fct_getinfofromid)."""

    pass


class GetFeaturesGeoJsonData(Data):
    """GeoJSON feature collection returned by gw_fct_getfeatures."""

    type: Optional[Literal["FeatureCollection"]] = Field(None, description="GeoJSON type")
    features: Optional[List[Dict[str, Any]]] = Field(None, description="GeoJSON features")
    pageInfo: Optional[PageInfoReturnModel] = Field(None, description="Pagination information")


class GetFeaturesGeoJsonBody(Body[GetFeaturesGeoJsonData]):
    form: Optional[Dict] = Field(default_factory=dict, description="Form")
    feature: Optional[Dict] = Field(default_factory=dict, description="Feature")


class GetFeaturesGeoJsonResponse(BaseAPIResponse[GetFeaturesGeoJsonBody]):
    """Response model for feature geometries as GeoJSON (gw_fct_getfeatures)."""

    pass
