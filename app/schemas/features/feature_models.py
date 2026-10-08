"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from datetime import date
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


class ValvePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    closed: Optional[bool] = Field(None, description="Valve closed")
    broken: Optional[bool] = Field(None, description="Valve broken")


class ArcPatch(BaseModel):
    """Writable ve_arc columns (gw_trg_edit_arc). Geometry, node_1/node_2 and computed columns are excluded."""

    model_config = ConfigDict(extra="forbid")

    arccat_id: Optional[str] = Field(None, description="Arc catalog id. Sets arc_type from cat_arc when omitted")
    arc_type: Optional[str] = Field(
        None, description="Arc type. Derived from arccat_id; WS uses it only for the catalog check"
    )
    state: Optional[int] = Field(None, description="State. 1->2 adds the arc to the current psector; 0 detaches nodes")
    state_type: Optional[int] = Field(None, description="State type, must belong to state")
    epa_type: Optional[str] = Field(None, description="EPA type. Changing it resets the arc's EPA data")

    expl_id: Optional[int] = Field(None, description="Exploitation id. Also updates the arc's connecs and links")
    sector_id: Optional[int] = Field(None, description="Sector id")
    dma_id: Optional[int] = Field(None, description="DMA id")
    expl_visibility: Optional[List[int]] = Field(None, description="Exploitations the arc is visible in")
    presszone_id: Optional[int] = Field(None, description="Pressure zone id (WS only)")
    dqa_id: Optional[int] = Field(None, description="DQA id (WS only)")
    omzone_id: Optional[int] = Field(None, description="OM zone id (UD only)")
    omunit_id: Optional[int] = Field(None, description="OM unit id (UD only)")
    drainzone_outfall: Optional[List[int]] = Field(None, description="Drainzone outfall node ids (UD only)")
    dwfzone_outfall: Optional[List[int]] = Field(None, description="DWF zone outfall node ids (UD only)")

    code: Optional[str] = Field(None, description="Code. On UD, null is regenerated")
    sys_code: Optional[str] = Field(None, description="System code")
    descript: Optional[str] = Field(None, description="Description")
    annotation: Optional[str] = Field(None, description="Annotation")
    observ: Optional[str] = Field(None, description="Observations")
    comment: Optional[str] = Field(None, description="Comment")
    custom_length: Optional[float] = Field(None, description="Custom length")
    num_value: Optional[float] = Field(None, description="Numeric value")
    link: Optional[str] = Field(None, description="External link")
    datasource: Optional[int] = Field(None, description="Datasource (WS only)")

    soilcat_id: Optional[str] = Field(None, description="Soil catalog id")
    function_type: Optional[str] = Field(None, description="Function type")
    category_type: Optional[str] = Field(None, description="Category type")
    fluid_type: Optional[int | str] = Field(None, description="Fluid type (WS: text, UD: integer)")
    location_type: Optional[str] = Field(None, description="Location type")
    matcat_id: Optional[str] = Field(
        None, description="Material catalog id (UD only; ignored when cat_arc defines one)"
    )

    workcat_id: Optional[str] = Field(None, description="Work catalog id")
    workcat_id_end: Optional[str] = Field(None, description="End work catalog id")
    workcat_id_plan: Optional[str] = Field(None, description="Planned work catalog id")
    builtdate: Optional[date] = Field(None, description="Built date")
    enddate: Optional[date] = Field(None, description="End date")
    ownercat_id: Optional[str] = Field(None, description="Owner catalog id")

    muni_id: Optional[int] = Field(None, description="Municipality id")
    streetaxis_id: Optional[str] = Field(None, description="Street axis id")
    streetaxis2_id: Optional[str] = Field(None, description="Second street axis id")
    postcode: Optional[str] = Field(None, description="Postcode")
    district_id: Optional[int] = Field(None, description="District id")
    postnumber: Optional[int] = Field(None, description="Post number")
    postnumber2: Optional[int] = Field(None, description="Second post number")
    postcomplement: Optional[str] = Field(None, description="Post complement")
    postcomplement2: Optional[str] = Field(None, description="Second post complement")

    verified: Optional[int] = Field(None, description="Verified")
    publish: Optional[bool] = Field(None, description="Published")
    inventory: Optional[bool] = Field(None, description="In inventory")
    om_state: Optional[str] = Field(None, description="OM state")
    conserv_state: Optional[str] = Field(None, description="Conservation state")
    lock_level: Optional[int] = Field(None, description="Lock level")
    is_scadamap: Optional[bool] = Field(None, description="Shown on the SCADA map")
    uncertain: Optional[bool] = Field(None, description="Uncertain (UD only)")

    adate: Optional[str] = Field(None, description="Asset date")
    adescript: Optional[str] = Field(None, description="Asset description")
    asset_id: Optional[str] = Field(None, description="Asset id")
    pavcat_id: Optional[str] = Field(None, description="Pavement catalog id")
    parent_id: Optional[int] = Field(None, description="Parent arc id")
    brand_id: Optional[str] = Field(None, description="Brand id")
    model_id: Optional[str] = Field(None, description="Model id")
    serial_number: Optional[str] = Field(None, description="Serial number")
    dataquality: Optional[int] = Field(None, description="Data quality")
    dataquality_obs: Optional[List[str]] = Field(None, description="Data quality observations")

    label_x: Optional[str] = Field(None, description="Label x")
    label_y: Optional[str] = Field(None, description="Label y")
    label_rotation: Optional[float] = Field(None, description="Label rotation")
    label_quadrant: Optional[str] = Field(None, description="Label quadrant")

    visitability: Optional[int] = Field(None, description="Visitability (UD only)")
    registration_date: Optional[date] = Field(None, description="Registration date (UD only)")
    meandering: Optional[int] = Field(None, description="Meandering (UD only)")
    last_visitdate: Optional[date] = Field(None, description="Last visit date (UD only)")
    negative_offset: Optional[bool] = Field(None, description="Negative offset (UD only)")
    initoverflowpath: Optional[bool] = Field(None, description="Initial overflow path (UD only)")
    y1: Optional[float] = Field(None, description="Upstream depth (UD only)")
    y2: Optional[float] = Field(None, description="Downstream depth (UD only)")
    elev1: Optional[float] = Field(None, description="Upstream elevation (UD only)")
    elev2: Optional[float] = Field(None, description="Downstream elevation (UD only)")
    custom_elev1: Optional[float] = Field(None, description="Custom upstream elevation (UD only)")
    custom_elev2: Optional[float] = Field(None, description="Custom downstream elevation (UD only)")
    inverted_slope: Optional[bool] = Field(None, description="Inverted slope (UD only)")


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
