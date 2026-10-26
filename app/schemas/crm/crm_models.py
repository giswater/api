"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date
from ..common import BaseAPIResponse, Body


# Input models


class HydrometerBase(BaseModel):
    """Base hydrometer model with all fields"""

    code: str = Field(..., description="Hydrometer code (from CRM)")
    hydroNumber: Optional[str] = Field(None, description="Hydrometer number")
    customerCode: Optional[str] = Field(
        None, description="Connec customer code (maps to feature_customer_code on write)"
    )
    # DEPRECATED: prefer customerCode. Looked up to ve_connec.customer_code; not a function key.
    connecId: Optional[int] = Field(None, deprecated="Prefer customerCode.")
    link: Optional[str] = Field(None, description="URL link to CRM software")
    stateId: Optional[int] = Field(None, description="State ID (catalog)")
    catalogId: Optional[int] = Field(None, description="Catalog ID")
    categoryId: Optional[int] = Field(None, description="Category ID (catalog)")
    priorityId: Optional[int] = Field(None, description="Priority ID (catalog)")
    exploitation: Optional[int] = Field(None, description="Exploitation ID")
    startDate: Optional[date] = Field(None, description="Start date")
    endDate: Optional[date] = Field(None, description="End date")
    updateDate: Optional[date] = Field(None, description="Update date")
    shutdownDate: Optional[date] = Field(None, description="Shutdown date")


class HydrometerCreate(HydrometerBase):
    """Model for creating hydrometers - code is required"""

    pass


class HydrometerUpdate(HydrometerBase):
    """Model for updating hydrometers - all fields optional except code"""

    pass


# Response models


class HydrometerData(BaseModel):
    """Data returned from hydrometer operations"""

    hydrometers: Optional[List[Dict[str, Any]]] = Field(None, description="List of hydrometers affected")
    count: Optional[int] = Field(None, description="Number of hydrometers affected")


class HydrometerBody(Body[HydrometerData]):
    """Body for hydrometer response"""

    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class HydrometerResponse(BaseAPIResponse[HydrometerBody]):
    """Response model for hydrometer operations"""

    pass
