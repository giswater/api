"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..common import BaseAPIResponse, Body, Data, PageInfoReturnModel

FeatureType = Literal["node", "arc", "link", "connec", "gully"]

FEATURE_TYPE_PARAM: Dict[FeatureType, str] = {
    "node": "NODE",
    "arc": "ARC",
    "link": "LINK",
    "connec": "CONNEC",
    "gully": "GULLY",
}

FEATURE_ID_MAP: Dict[FeatureType, str] = {
    "node": "node_id",
    "arc": "arc_id",
    "link": "link_id",
    "connec": "connec_id",
    "gully": "gully_id",
}


def get_feature_type_param(feature_type: FeatureType) -> str:
    return FEATURE_TYPE_PARAM[feature_type]


def get_feature_table(feature_type: FeatureType) -> str:
    return f"ve_{feature_type}"


def get_feature_id_column(feature_type: FeatureType) -> str:
    return FEATURE_ID_MAP[feature_type]


class FeatureFilters(BaseModel):
    """Shared filter fields present on all feature views."""

    model_config = ConfigDict(extra="forbid")

    expl_id: Optional[int] = Field(None, description="Exploitation id")
    macroexpl_id: Optional[int] = Field(None, description="Macroexploitation id")
    sector_id: Optional[int] = Field(None, description="Sector id")
    macrosector_id: Optional[int] = Field(None, description="Macrosector id")
    dma_id: Optional[int] = Field(None, description="DMA id")
    macrodma_id: Optional[int] = Field(None, description="Macro DMA id")
    presszone_id: Optional[str] = Field(None, description="Pressure zone id")
    dqa_id: Optional[int] = Field(None, description="DQA id")
    state: Optional[int] = Field(None, description="Feature state")
    sys_type: Optional[List[str]] = Field(
        None, description="System type / feature class group (e.g. VALVE, PIPE, JUNCTION)"
    )
    code: Optional[str] = Field(None, description="Feature code")

    def to_filter_fields(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for key, value in self.model_dump(exclude_none=True).items():
            if isinstance(value, list):
                out[key] = {"value": value, "filterSign": "IN"}
            else:
                out[key] = {"value": value, "filterSign": "="}
        return out


class NodeFilters(FeatureFilters):
    node_type: Optional[List[str]] = Field(None, description="Node type (cat_feature.id subtype)")
    nodecat_id: Optional[List[str]] = Field(None, description="Node catalog id")


class ArcFilters(FeatureFilters):
    arc_type: Optional[List[str]] = Field(None, description="Arc type")
    arccat_id: Optional[List[str]] = Field(None, description="Arc catalog id")
    cat_matcat_id: Optional[str] = Field(None, description="Material catalog id")
    cat_dnom: Optional[str] = Field(None, description="Nominal diameter")


class ConnecFilters(FeatureFilters):
    connec_type: Optional[List[str]] = Field(None, description="Connec type")
    connecat_id: Optional[List[str]] = Field(None, description="Connec catalog id")
    customer_code: Optional[str] = Field(None, description="Customer code")


class GullyFilters(FeatureFilters):
    gully_type: Optional[List[str]] = Field(None, description="Gully type")
    gratecat_id: Optional[List[str]] = Field(None, description="Grate catalog id")


class LinkFilters(FeatureFilters):
    link_type: Optional[List[str]] = Field(None, description="Link type")


class GetFeatureResponse(BaseAPIResponse[Body[Data]]):
    """Response model for a single feature form (gw_fct_getinfofromid)."""

    pass


class GetFeatureFieldsData(Data):
    """Single feature row (gw_fct_getfeatures, outputFormat=list, filtered by id)."""

    feature: Optional[Dict[str, Any]] = Field(None, description="Feature row")


class GetFeatureFieldsBody(Body[GetFeatureFieldsData]):
    form: Optional[Dict] = Field(default_factory=dict, description="Form")
    feature: Optional[Dict] = Field(default_factory=dict, description="Feature")


class GetFeatureFieldsResponse(BaseAPIResponse[GetFeatureFieldsBody]):
    """Response model for a single feature row (gw_fct_getfeatures, outputFormat=list)."""

    pass


class GetFeatureGeoJsonData(Data):
    """Single GeoJSON Feature."""

    type: Optional[Literal["Feature"]] = Field(None, description="GeoJSON type")
    geometry: Optional[Dict[str, Any]] = Field(None, description="GeoJSON geometry")
    properties: Optional[Dict[str, Any]] = Field(None, description="Feature attributes")


class GetFeatureGeoJsonBody(Body[GetFeatureGeoJsonData]):
    form: Optional[Dict] = Field(default_factory=dict, description="Form")
    feature: Optional[Dict] = Field(default_factory=dict, description="Feature")


class GetFeatureGeoJsonResponse(BaseAPIResponse[GetFeatureGeoJsonBody]):
    """Response model for a single feature as GeoJSON (gw_fct_getfeatures, outputFormat=geojson)."""

    pass


class GetFeaturesData(Data):
    """List payload returned by gw_fct_getfeatures with outputFormat=list."""

    features: Optional[List[Dict[str, Any]]] = Field(None, description="Feature rows")
    pageInfo: Optional[PageInfoReturnModel] = Field(None, description="Pagination information")


class GetFeaturesBody(Body[GetFeaturesData]):
    form: Optional[Dict] = Field(default_factory=dict, description="Form")
    feature: Optional[Dict] = Field(default_factory=dict, description="Feature")


class GetFeaturesResponse(BaseAPIResponse[GetFeaturesBody]):
    """Response model for feature lists (gw_fct_getfeatures, outputFormat=list)."""

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
