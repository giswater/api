"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List

from ..common import (
    BaseAPIResponse,
    Body,
    Data,
    LayeredFeatureCollectionModel,
    ReturnManagerModel,
)


class LegendModel(BaseModel):
    """Legend model"""

    catalog: str = Field(..., description="Catalog")
    vs: str = Field(..., description="VS")
    hs: str = Field(..., description="HS")
    referencePlane: str = Field(..., description="Reference plane")
    dimensions: str = Field(..., description="Dimensions")
    ordinates: str = Field(..., description="Ordinates")
    topelev: str = Field(..., description="Top elev")
    ymax: str = Field(..., description="Y max")
    elev: str = Field(..., description="Elev")
    code: str = Field(..., description="Code")
    distance: str = Field(..., description="Distance")


class TitleTextModel(BaseModel):
    """Title text model"""

    color: str = Field(..., description="Text color")
    weight: str = Field(..., description="Text weight")
    size: int = Field(..., description="Text size")


class TitleStylesheetModel(BaseModel):
    """Title stylesheet model"""

    text: TitleTextModel = Field(..., description="Title text style")


class TerrainStylesheetModel(BaseModel):
    """Terrain stylesheet model"""

    color: str = Field(..., description="Terrain color")
    width: float = Field(..., description="Terrain width")
    style: str = Field(..., description="Terrain line style")


class InfraStyleModel(BaseModel):
    """Infra style model"""

    color: str = Field(..., description="Infra color")
    width: float = Field(..., description="Infra width")
    style: str = Field(..., description="Infra line style")


class InfraStylesheetModel(BaseModel):
    """Infra stylesheet model"""

    real: InfraStyleModel = Field(..., description="Real infra style")
    interpolated: InfraStyleModel = Field(..., description="Interpolated infra style")


class GridBoundaryOrLineModel(BaseModel):
    """Grid boundary or line model"""

    color: str = Field(..., description="Boundary or line color")
    style: str = Field(..., description="Boundary or line style")
    width: float = Field(..., description="Boundary or line width")


class GridTextModel(BaseModel):
    """Grid text model"""

    color: str = Field(..., description="Text color")
    weight: str = Field(..., description="Text weight")


class GridStylesheetModel(BaseModel):
    """Grid stylesheet model"""

    boundary: GridBoundaryOrLineModel = Field(..., description="Boundary style")
    lines: GridBoundaryOrLineModel = Field(..., description="Lines style")
    text: GridTextModel = Field(..., description="Grid text style")


class GuitarLinesModel(BaseModel):
    """Guitar lines model"""

    color: str = Field(..., description="Guitar line color")
    style: str = Field(..., description="Guitar line style")
    width: float = Field(..., description="Guitar line width")


class GuitarTextModel(BaseModel):
    """Guitar text model"""

    color: str = Field(..., description="Guitar text color")
    weight: str = Field(..., description="Guitar text weight")


class GuitarStylesheetModel(BaseModel):
    """Guitar stylesheet model"""

    lines: GuitarLinesModel = Field(..., description="Main lines style")
    auxiliarlines: GuitarLinesModel = Field(..., description="Auxiliary lines style")
    text: GuitarTextModel = Field(..., description="Text style")


class StylesheetModel(BaseModel):
    """Stylesheet model"""

    title: TitleStylesheetModel = Field(..., description="Title")
    terrain: TerrainStylesheetModel = Field(..., description="Terrain")
    infra: InfraStylesheetModel = Field(..., description="Infra")
    grid: GridStylesheetModel = Field(..., description="Grid")
    guitar: GuitarStylesheetModel = Field(..., description="Guitar")


class NodeModel(BaseModel):
    """Node model"""

    node_id: int = Field(..., description="Node identifier")
    surface_type: str = Field(..., description="Type of surface")
    descript: str = Field(..., description="JSON description of the node")
    data_type: str = Field(..., description="Data type (e.g., REAL)")
    cat_geom1: int = Field(..., description="Geometry category 1")
    top_elev: float = Field(..., description="Top elevation")
    elev: float = Field(..., description="Elevation")
    ymax: float = Field(..., description="Maximum Y")
    total_distance: float = Field(..., description="Total distance")


class TerrainModel(BaseModel):
    """Terrain model"""

    rid: int = Field(..., description="Row id")
    top_n1: float = Field(..., description="Top elevation node 1")
    top_n2: Optional[float] = Field(..., description="Top elevation node 2")
    delta_y: Optional[float] = Field(..., description="Delta Y")
    delta_x: Optional[float] = Field(..., description="Delta X")
    total_x: float = Field(..., description="Total X")
    label_n1: str = Field(..., description="Node 1 label")
    surface_type: str = Field(..., description="Surface type")


class ArcModel(BaseModel):
    """Arc model"""

    arc_id: int = Field(..., description="Arc identifier")
    descript: str = Field(..., description="JSON description of the arc")
    cat_geom1: float = Field(..., description="Geometry category 1")
    length: float = Field(..., description="Arc length")
    z1: float = Field(..., description="Z1")
    z2: float = Field(..., description="Z2")
    y1: float = Field(..., description="Y1")
    y2: float = Field(..., description="Y2")
    elev1: float = Field(..., description="Elevation 1")
    elev2: float = Field(..., description="Elevation 2")
    node_1: int = Field(..., description="Node 1")
    node_2: int = Field(..., description="Node 2")
    omunit_id: Optional[int] = Field(None, description="OM unit id")


class StyleValueModel(BaseModel):
    """Style value model"""

    id: str = Field(..., description="Value id")
    color: List[int] = Field(..., description="RGB color")
    legend_id: str = Field(..., description="Legend id")


class PointStyleModel(BaseModel):
    """Point style model"""

    style: str = Field(..., description="Style")
    field: str = Field(..., description="Field")
    transparency: float = Field(..., description="Transparency")
    width: float = Field(..., description="Width")
    values: List[StyleValueModel] = Field(..., description="Style values")


class LineStyleModel(BaseModel):
    """Line style model"""

    style: str = Field(..., description="Style")
    field: str = Field(..., description="Field")
    transparency: float = Field(..., description="Transparency")
    width: float = Field(..., description="Width")
    values: List[StyleValueModel] = Field(..., description="Style values")


class ProfileData(Data):
    """Profile data"""

    legend: LegendModel = Field(..., description="Legend")
    scale: str = Field(..., description="Scale")
    extension: dict = Field(..., description="Extension")
    initpoint: dict = Field(..., description="Initial point")
    stylesheet: StylesheetModel = Field(..., description="Stylesheet")
    node: list[NodeModel] = Field(..., description="Node")
    terrain: list[TerrainModel] = Field(..., description="Terrain")
    arc: list[ArcModel] = Field(..., description="Arc")
    point: Optional[LayeredFeatureCollectionModel | Dict[str, Any]] = Field(None, description="Point")
    line: Optional[LayeredFeatureCollectionModel | Dict[str, Any]] = Field(None, description="Line")
    polygon: Optional[LayeredFeatureCollectionModel | Dict[str, Any]] = Field(None, description="Polygon")

    @field_validator("point", "line", "polygon", mode="before")
    @classmethod
    def validate_geojson_or_empty(cls, value: Any) -> Any:
        if value is None or value == {}:
            return value
        if isinstance(value, LayeredFeatureCollectionModel):
            return value
        if isinstance(value, dict):
            if value.get("type") == "FeatureCollection" and "features" in value:
                return value
        raise ValueError("Expected empty dict or FeatureCollection")


class ProfileBody(Body[ProfileData]):
    """Profile body"""

    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")
    data: Optional[ProfileData] = Field(None, description="Data")
    returnManager: Optional[ReturnManagerModel] = Field(None, description="Return manager")


class ProfileResponse(BaseAPIResponse[ProfileBody]):
    """Profile response"""

    pass
