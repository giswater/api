"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ..common import BaseAPIResponse, Body


class Street(BaseModel):
    id: str = Field(..., description="Street axis id (ext_streetaxis.id)")
    name: Optional[str] = Field(None, description="Street name")
    muni_id: Optional[int] = Field(None, description="Municipality id")
    muni_name: Optional[str] = Field(None, description="Municipality name")
    x1: Optional[float] = Field(None, description="Bbox min x")
    y1: Optional[float] = Field(None, description="Bbox min y")
    x2: Optional[float] = Field(None, description="Bbox max x")
    y2: Optional[float] = Field(None, description="Bbox max y")


class StreetArc(BaseModel):
    arc_id: int | str = Field(..., description="Arc id")
    code: Optional[str] = Field(None, description="Feature code")
    sys_type: Optional[str] = Field(None, description="System type")
    state: Optional[int] = Field(None, description="Feature state")
    x: Optional[float] = Field(None, description="Centroid x in project CRS")
    y: Optional[float] = Field(None, description="Centroid y in project CRS")
    arc_type: Optional[str] = Field(None, description="Arc type")
    cat_dnom: Optional[str] = Field(None, description="Nominal diameter")
    cat_matcat_id: Optional[str] = Field(None, description="Material catalog id")
    node_1: Optional[int | str] = Field(None, description="Start node id")
    node_2: Optional[int | str] = Field(None, description="End node id")
    gis_length: Optional[float] = Field(None, description="GIS length")
    match: Literal["attribute", "spatial", "both"] = Field(..., description="How the arc matched the street")
    distance_m: Optional[float] = Field(None, description="Distance to houseNumber point, when resolved")


class ListStreetsData(BaseModel):
    streets: List[Street] = Field(default_factory=list, description="Matching streets")
    count: int = Field(..., description="Number of streets returned")


class ListStreetsBody(Body[ListStreetsData]):
    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class ListStreetsResponse(BaseAPIResponse[ListStreetsBody]):
    pass


class ListStreetArcsData(BaseModel):
    street: Street = Field(..., description="Street row")
    arcs: List[StreetArc] = Field(default_factory=list, description="Candidate arcs")
    count: int = Field(..., description="Number of arcs returned")


class ListStreetArcsBody(Body[ListStreetArcsData]):
    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class ListStreetArcsResponse(BaseAPIResponse[ListStreetArcsBody]):
    pass
