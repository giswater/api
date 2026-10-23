"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from ..common import BaseAPIResponse, Body


class _Dated(BaseModel):
    @model_validator(mode="after")
    def end_not_before_start(self):
        start = getattr(self, "startDate", None)
        end = getattr(self, "endDate", None)
        if start is not None and end is not None and end < start:
            raise ValueError("endDate must be greater than or equal to startDate")
        return self


class VisitCreate(_Dated):
    """Create a visit. `type` and `status` are required by cmms.visit."""

    type: str = Field(..., description="Visit type")
    status: str = Field(..., description="Visit status")
    extVisitId: Optional[str] = Field(None, description="External visit id")
    title: Optional[str] = Field(None, description="Title")
    description: Optional[str] = Field(None, description="Description")
    startDate: Optional[datetime] = Field(None, description="Start")
    endDate: Optional[datetime] = Field(None, description="End")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Free-form properties")
    sysCodes: List[str] = Field(default_factory=list, description="Feature sys_code values this visit is about")


class VisitUpdate(_Dated):
    """Partial visit update. `sysCodes`, when sent, replaces the visit's feature links."""

    type: Optional[str] = Field(None, description="Visit type")
    status: Optional[str] = Field(None, description="Visit status")
    extVisitId: Optional[str] = Field(None, description="External visit id")
    title: Optional[str] = Field(None, description="Title")
    description: Optional[str] = Field(None, description="Description")
    startDate: Optional[datetime] = Field(None, description="Start")
    endDate: Optional[datetime] = Field(None, description="End")
    properties: Optional[Dict[str, Any]] = Field(None, description="Free-form properties")
    sysCodes: Optional[List[str]] = Field(None, description="Replace feature links with these sys_code values")


class AttachmentMeta(BaseModel):
    """JSON `meta` form field sent with an attachment upload."""

    description: Optional[str] = Field(None, description="Description")
    attachmentType: Optional[str] = Field(None, description="Attachment type")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Free-form properties")
    coordinates: Optional[Dict[str, Any]] = Field(
        None, description="Override EXIF GPS. Used as-is when sent; otherwise GPS is read from the image"
    )
    sysCodes: List[str] = Field(default_factory=list, description="Feature sys_code values to link directly")


class AttachmentUpdate(BaseModel):
    """Partial attachment update. `sysCodes`, when sent, replaces direct feature links."""

    name: Optional[str] = Field(None, description="Display name")
    code: Optional[str] = Field(None, description="Code")
    description: Optional[str] = Field(None, description="Description")
    attachmentType: Optional[str] = Field(None, description="Attachment type")
    properties: Optional[Dict[str, Any]] = Field(None, description="Free-form properties")
    coordinates: Optional[Dict[str, Any]] = Field(None, description="Coordinates")
    sysCodes: Optional[List[str]] = Field(None, description="Replace direct feature links")


class CmmsData(BaseModel):
    visits: Optional[List[Dict[str, Any]]] = Field(None, description="Visits")
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="Attachments")
    count: Optional[int] = Field(None, description="Match count")


class CmmsBody(Body[CmmsData]):
    form: Optional[Dict] = Field(default_factory=dict, description="Form")
    feature: Optional[Dict] = Field(default_factory=dict, description="Feature")


class CmmsResponse(BaseAPIResponse[CmmsBody]):
    pass
