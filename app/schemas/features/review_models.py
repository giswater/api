"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import BaseAPIResponse
from app.schemas.features.feature_models import FeatureType


class _V2Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewStatus(IntEnum):
    PENDING = 0
    ACCEPTED = 1
    REJECTED = 2


class ReviewCreate(_V2Model):
    """Changeset for one feature. gw_fct_core_feature_edit_request_create stores it as pending."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    table_name: FeatureType = Field(..., alias="tableName", description="node, arc, connec, link, or gully")
    table_id: int = Field(..., alias="tableId", description="Feature id", examples=[1001])
    annotation: Optional[str] = Field(None, description="Note from the person proposing the change")
    changes: Dict[str, Any] = Field(..., description="Proposed column values. Must not be empty.")


class ReviewDecision(_V2Model):
    """Accept or reject a pending review."""

    annotation: Optional[str] = Field(None, description="Reviewer note")
    changes: Optional[Dict[str, Any]] = Field(
        None,
        description="Values to write on accept. Omit to apply the stored proposal. Ignored on reject.",
    )


class ReviewListItem(_V2Model):
    """One row from gw_fct_core_feature_edit_request_get_list."""

    id: int
    table_name: str
    table_id: int
    feature_code: Optional[str] = None
    feature_type: Optional[str] = None
    expl_id: Optional[int] = None
    field_user: Optional[str] = None
    field_date: Optional[datetime] = None
    field_annotation: Optional[str] = None
    field_changes: Optional[Dict[str, Any]] = None
    review_changes: Optional[Dict[str, Any]] = None
    review_user: Optional[str] = None
    review_date: Optional[datetime] = None
    review_annotation: Optional[str] = None
    status: ReviewStatus
    status_name: Optional[str] = None


class ListReviewsData(_V2Model):
    reviews: List[ReviewListItem] = Field(default_factory=list)


class ListReviewsResponse(BaseAPIResponse[ListReviewsData]):
    """Response for GET /features/reviews."""

    pass


class CreateReviewData(_V2Model):
    id: int = Field(..., description="Id from gw_fct_core_feature_edit_request_create")


class CreateReviewResponse(BaseAPIResponse[CreateReviewData]):
    """Response for POST /features/reviews."""

    pass


class Review(ReviewListItem):
    """One row from gw_fct_core_feature_edit_request_get."""

    child_layer: Optional[str] = None
    current_values: Optional[Dict[str, Optional[str]]] = Field(
        None,
        description="Live text value for each key in field_changes. Null when the feature has no value.",
    )


class GetReviewResponse(BaseAPIResponse[Review]):
    """Response for GET /features/reviews/{review_id}."""

    pass


class ReviewResult(_V2Model):
    id: int
    status: ReviewStatus


class ReviewResultResponse(BaseAPIResponse[ReviewResult]):
    """Response for accept and reject."""

    pass
