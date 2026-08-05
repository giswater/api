"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from pydantic import BaseModel, Field, field_validator
from pydantic_geojson import FeatureCollectionModel
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime

from ..common import (
    BaseAPIResponse,
    Body,
    Data,
    Geometry,
    Info,
    FilterFieldModel,
    GwField,
)

# region Value mappings

MINCUT_CAUSE_VALUES = {"Accidental": 1, "Planified": 2}

# endregion

# region Input parameters


class MincutPlanParams(BaseModel):
    mincut_type: Literal["Demo", "Test", "Real"] = Field(
        "Demo", title="Mincut Type", description="Type of the mincut", examples=["Demo"]
    )
    anl_cause: Literal["Accidental", "Planified"] = Field(
        "Accidental", title="Analysis Cause", description="Cause of the analysis", examples=["Accidental"]
    )
    anl_descript: Optional[str] = Field(
        None, title="Analysis Description", description="Description of the analysis", examples=["Test mincut"]
    )
    forecast_start: Optional[datetime] = Field(
        None, title="Forecast Start", description="Start of the forecast", examples=["2025-05-15T14:30"]
    )
    forecast_end: Optional[datetime] = Field(
        None, title="Forecast End", description="End of the forecast", examples=["2025-05-16T15:40"]
    )
    received_date: Optional[datetime] = Field(
        None, title="Received Date", description="Date of the received", examples=["2025-05-13T12:00"]
    )


class MincutExecParams(BaseModel):
    exec_start: Optional[datetime] = Field(
        None, title="Execution Start", description="Start date of the mincut", examples=["2025-05-15T14:30"]
    )
    exec_end: Optional[datetime] = Field(
        None, title="Execution End", description="End date of the mincut", examples=["2025-05-16T15:40"]
    )
    exec_descript: Optional[str] = Field(
        None,
        title="Execution Description",
        description="Description of the execution",
        examples=["Test mincut execution"],
    )
    exec_user: Optional[str] = Field(
        None, title="Execution User", description="User who is doing the action", examples=["bgeo"]
    )
    exec_from_plot: Optional[float] = Field(
        None, title="Distance", description="Distance of the mincut", examples=[1.5]
    )
    exec_depth: Optional[float] = Field(None, title="Depth", description="Depth of the mincut", examples=[0.8])
    exec_appropiate: Optional[bool] = Field(
        None, title="Appropriate", description="Appropriate of the mincut", examples=[True]
    )


# endregion

# region Response models

# region Mincut create response models


class MincutCreateData(Data):
    """Mincut create data"""

    mincutId: int = Field(..., description="Mincut id", examples=[1])
    mincutState: int = Field(
        ...,
        description=(
            "Mincut state (0: Planified, 1: In Progress, 2: Finished, 3: Canceled, 4: On Planning, 5: Conflict)"
        ),
        examples=[1],
        ge=0,
        le=5,
    )
    info: Optional[Info] = Field(None, description="Information about the process")
    mincutInit: Optional[FeatureCollectionModel] = Field(None, description="Mincut initial point")
    mincutProposedValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut proposed valve")
    mincutUnaccessValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut unaccessible valve")
    mincutChangestatusValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut change-status valve"
    )
    mincutNotProposedValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut not proposed / do-not-operate valve"
    )
    mincutNode: Optional[FeatureCollectionModel] = Field(None, description="Mincut node")
    mincutConnec: Optional[FeatureCollectionModel] = Field(None, description="Mincut connecs")
    mincutArc: Optional[FeatureCollectionModel] = Field(None, description="Mincut arcs")
    geometry: Optional[Geometry] = Field(None, description="Extent of the mincut")


class MincutCreateBody(Body[MincutCreateData]):
    """Body for mincut create response"""

    pass


class MincutCreateResponse(BaseAPIResponse[MincutCreateBody]):
    """Response model for mincut create"""

    pass


# endregion


# region Mincut dialog response models


class MincutDialogData(Data):
    """Mincut dialog data"""

    mincutId: int = Field(..., description="Mincut id", examples=[1])
    mincutState: int = Field(
        ...,
        description=(
            "Mincut state (0: Planified, 1: In Progress, 2: Finished, 3: Canceled, 4: On Planning, 5: Conflict)"
        ),
        examples=[1],
        ge=0,
        le=5,
    )
    info: Optional[Info] = Field(None, description="Information about the process")
    mincutInit: Optional[FeatureCollectionModel] = Field(None, description="Mincut initial point")
    mincutProposedValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut proposed valve")
    mincutUnaccessValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut unaccessible valve")
    mincutChangestatusValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut change-status valve"
    )
    mincutNotProposedValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut not proposed / do-not-operate valve"
    )
    mincutNode: Optional[FeatureCollectionModel] = Field(None, description="Mincut node")
    mincutConnec: Optional[FeatureCollectionModel] = Field(None, description="Mincut connecs")
    mincutArc: Optional[FeatureCollectionModel] = Field(None, description="Mincut arcs")
    geometry: Optional[Geometry] = Field(None, description="Extent of the mincut")


class MincutDialogBody(Body[MincutDialogData]):
    """Body for mincut create response"""

    pass


class MincutDialogResponse(BaseAPIResponse[MincutDialogBody]):
    """Response model for mincut create"""

    pass


# endregion


# region Mincut update response models


class MincutUpdateData(Data):
    """Mincut update data"""

    mincutId: int = Field(..., description="Mincut id", examples=[1])
    mincutState: int = Field(
        ...,
        description=(
            "Mincut state (0: Planified, 1: In Progress, 2: Finished, 3: Canceled, 4: On Planning, 5: Conflict)"
        ),
        examples=[1],
        ge=0,
        le=5,
    )
    info: Optional[Info] = Field(None, description="Information about the process")
    mincutInit: Optional[FeatureCollectionModel] = Field(None, description="Mincut initial point")
    mincutProposedValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut proposed valve")
    mincutUnaccessValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut unaccessible valve")
    mincutChangestatusValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut change-status valve"
    )
    mincutNotProposedValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut not proposed / do-not-operate valve"
    )
    mincutNode: Optional[FeatureCollectionModel] = Field(None, description="Mincut node")
    mincutConnec: Optional[FeatureCollectionModel] = Field(None, description="Mincut connecs")
    mincutArc: Optional[FeatureCollectionModel] = Field(None, description="Mincut arcs")
    geometry: Optional[Geometry] = Field(None, description="Extent of the mincut")


class MincutUpdateBody(Body[MincutUpdateData]):
    """Body for mincut update response"""

    pass


class MincutUpdateResponse(BaseAPIResponse[MincutUpdateBody]):
    """Response model for mincut update"""

    pass


# endregion


# region Mincut toggle valve unaccess response models


class MincutToggleValveUnaccessData(Data):
    """Mincut toggle valve unaccess data"""

    # NOTE: fields are inherited from Data
    info: Optional[Info] = Field(None, description="Info of the data")
    mincutId: int = Field(..., description="Mincut id", examples=[1])
    mincutState: int = Field(..., description="Mincut state", examples=[1])
    mincutInit: FeatureCollectionModel = Field(..., description="Mincut initial point")
    mincutProposedValve: FeatureCollectionModel = Field(..., description="Mincut proposed valve")
    mincutUnaccessValve: FeatureCollectionModel = Field(..., description="Mincut unaccessible valve")
    mincutChangestatusValve: FeatureCollectionModel = Field(..., description="Mincut change-status valve")
    mincutNotProposedValve: FeatureCollectionModel = Field(
        ..., description="Mincut not proposed / do-not-operate valve"
    )
    mincutNode: FeatureCollectionModel = Field(..., description="Mincut node")
    mincutConnec: FeatureCollectionModel = Field(..., description="Mincut connecs")
    mincutArc: FeatureCollectionModel = Field(..., description="Mincut arcs")
    tiled: bool = Field(..., description="Tiled", examples=[True])
    geometry: Geometry = Field(..., description="Extent of the mincut")


class MincutToggleValveUnaccessBody(Body[MincutToggleValveUnaccessData]):
    """Body for mincut toggle valve unaccess response"""

    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class MincutToggleValveUnaccessResponse(BaseAPIResponse[MincutToggleValveUnaccessBody]):
    """Response model for mincut toggle valve unaccess"""

    pass


# endregion


# region Mincut toggle valve status response models


class MincutToggleValveStatusData(Data):
    """Mincut toggle valve status data"""

    # NOTE: fields are inherited from Data
    info: Optional[Info] = Field(None, description="Info of the data")
    mincutId: int = Field(..., description="Mincut id", examples=[1])
    mincutState: int = Field(..., description="Mincut state", examples=[1])
    mincutInit: FeatureCollectionModel = Field(..., description="Mincut initial point")
    mincutProposedValve: FeatureCollectionModel = Field(..., description="Mincut proposed valve")
    mincutUnaccessValve: FeatureCollectionModel = Field(..., description="Mincut unaccessible valve")
    mincutChangestatusValve: FeatureCollectionModel = Field(..., description="Mincut change-status valve")
    mincutNotProposedValve: FeatureCollectionModel = Field(
        ..., description="Mincut not proposed / do-not-operate valve"
    )
    mincutNode: FeatureCollectionModel = Field(..., description="Mincut node")
    mincutConnec: FeatureCollectionModel = Field(..., description="Mincut connecs")
    mincutArc: FeatureCollectionModel = Field(..., description="Mincut arcs")
    tiled: bool = Field(..., description="Tiled", examples=[True])
    geometry: Geometry = Field(..., description="Extent of the mincut")


class MincutToggleValveStatusBody(Body[MincutToggleValveStatusData]):
    """Body for mincut toggle valve status response"""

    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class MincutToggleValveStatusResponse(BaseAPIResponse[MincutToggleValveStatusBody]):
    """Response model for mincut toggle valve status"""

    pass


# endregion


# region Mincut start response models


class MincutStartData(Data):
    """Mincut start data"""

    mincutId: int = Field(..., description="Mincut id", examples=[1])
    # mincutInit: FeatureCollectionModel = Field(..., description="Mincut initial point")
    # valve: FeatureCollectionModel = Field(..., description="Valve")
    # mincutNode: FeatureCollectionModel = Field(..., description="Mincut node")
    # mincutConnec: FeatureCollectionModel = Field(..., description="Mincut connecs")
    # mincutArc: FeatureCollectionModel = Field(..., description="Mincut arcs")


class MincutStartBody(Body[MincutStartData]):
    """Body for mincut start response"""

    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class MincutStartResponse(BaseAPIResponse[MincutStartBody]):
    """Response model for mincut start"""

    pass


# region Mincut end response models


class MincutEndData(Data):
    """Mincut end data"""

    info: dict[str, list[dict[str, Any]]] = Field(..., description="Info")
    geometry: Optional[Geometry] = Field(None, description="Geometry")
    mincutId: Optional[int] = Field(None, description="Mincut id")
    fields: Optional[List[GwField]] = Field(None, description="Fields")
    mincutState: Optional[int] = Field(None, description="Mincut state")
    mincutInit: Optional[FeatureCollectionModel] = Field(None, description="Mincut initial")
    mincutProposedValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut proposed valve")
    mincutUnaccessValve: Optional[FeatureCollectionModel] = Field(None, description="Mincut unaccessible valve")
    mincutChangestatusValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut change-status valve"
    )
    mincutNotProposedValve: Optional[FeatureCollectionModel] = Field(
        None, description="Mincut not proposed / do-not-operate valve"
    )
    mincutNode: Optional[FeatureCollectionModel] = Field(None, description="Mincut node")
    mincutConnec: Optional[FeatureCollectionModel] = Field(None, description="Mincut connecs")
    mincutArc: Optional[FeatureCollectionModel] = Field(None, description="Mincut arcs")


class MincutEndManager(BaseModel):
    """Mincut end manager"""

    style: dict[str, dict[str, Any]] = Field(..., description="Style configuration for point, line, and polygon")


class MincutEndLayerManager(BaseModel):
    """Mincut end layer manager"""

    visible: List[dict[str, Any]] = Field(..., description="Visible")


class MincutEndBody(Body[MincutEndData]):
    """Body for mincut end response"""

    overlapStatus: Optional[str] = Field(None, description="Overlap status")
    returnManager: Optional[MincutEndManager] = Field(None, description="Return manager")
    layerManager: Optional[MincutEndLayerManager] = Field(None, description="Layer manager")


class MincutEndResponse(BaseAPIResponse[MincutEndBody]):
    """Response model for mincut end"""

    pass


# endregion


# region Mincut cancel response models


class MincutCancelResponse(BaseAPIResponse[Dict]):
    """Response model for mincut cancel"""

    pass


# endregion


# region Mincut delete response models


class MincutDeleteResponse(BaseAPIResponse[Dict]):
    """Response model for mincut delete"""

    pass


# endregion

# endregion


# endregion


MINCUT_VALID_FIELDS = frozenset(
    ["id", "work_order", "state", "mincut_type", "exploitation", "streetaxis", "forecast_start", "forecast_end"]
)


class MincutFilterFieldsModel(BaseModel):
    """Mincut filter fields response"""

    data: Optional[Dict[str, FilterFieldModel]] = Field(None, description="Data")

    @field_validator("data")
    @classmethod
    def validate_keys(cls, v):
        for key in v.keys():
            parts = [p.strip() for p in key.split(", ")]
            if not all(p in MINCUT_VALID_FIELDS for p in parts):
                raise ValueError(f"Invalid key: '{key}'")
        return v


MINCUT_VALVE_VALID_FIELDS = frozenset(
    ["result_id", "work_order", "node_id", "closed", "broken", "unaccess", "proposed", "to_arc"]
)


class MincutValveFilterFieldsModel(BaseModel):
    """Mincut valve filter fields response"""

    data: Optional[Dict[str, FilterFieldModel]] = Field(None, description="Data")

    @field_validator("data")
    @classmethod
    def validate_keys(cls, v):
        for key in v.keys():
            parts = [p.strip() for p in key.split(", ")]
            if not all(p in MINCUT_VALVE_VALID_FIELDS for p in parts):
                raise ValueError(f"Invalid key: '{key}'")
        return v
