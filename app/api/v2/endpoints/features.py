"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Path, Query

from app.api.deps import CommonsDep, get_service_context
from app.schemas.features.review_models import (
    CreateReviewResponse,
    GetReviewResponse,
    ListReviewsResponse,
    ReviewCreate,
    ReviewDecision,
    ReviewResultResponse,
)
from app.services.review_service import ReviewService

router = APIRouter(prefix="/features", tags=["Features"])

_REVIEW_ID = Path(..., title="Review id", description="feature_edit_request id", examples=[1])


@router.get(
    "/reviews",
    description="Lists rows from gw_fct_core_feature_edit_request_get_list. status defaults to 0 (pending).",
    response_model=ListReviewsResponse,
    response_model_exclude_unset=True,
)
async def list_reviews(
    commons: CommonsDep,
    status: int = Query(0, description="0 pending, 1 accepted, 2 rejected"),
    table_name: Optional[str] = Query(None, alias="tableName"),
    field_user: Optional[str] = Query(None, alias="fieldUser", description="Matched with ILIKE"),
    date_from: Optional[date] = Query(None, alias="dateFrom"),
    date_to: Optional[date] = Query(None, alias="dateTo"),
    limit: int = Query(100, ge=1, le=5000),
):
    ctx = get_service_context(commons)
    return await ReviewService(ctx).list_reviews(
        status=status,
        table_name=table_name,
        field_user=field_user,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.post(
    "/reviews",
    description="Creates a pending review through gw_fct_core_feature_edit_request_create.",
    response_model=CreateReviewResponse,
    response_model_exclude_unset=True,
)
async def create_review(commons: CommonsDep, payload: ReviewCreate):
    ctx = get_service_context(commons)
    return await ReviewService(ctx).create_review(payload)


@router.get(
    "/reviews/{review_id}",
    description=(
        "Returns one review from gw_fct_core_feature_edit_request_get, "
        "including field_changes and current_values."
    ),
    response_model=GetReviewResponse,
    response_model_exclude_unset=True,
)
async def get_review(commons: CommonsDep, review_id: int = _REVIEW_ID):
    ctx = get_service_context(commons)
    return await ReviewService(ctx).get_review(review_id)


@router.post(
    "/reviews/{review_id}/accept",
    description="Accepts a pending review through gw_fct_core_feature_edit_request_accept.",
    response_model=ReviewResultResponse,
    response_model_exclude_unset=True,
)
async def accept_review(
    commons: CommonsDep,
    review_id: int = _REVIEW_ID,
    payload: ReviewDecision = Body(default_factory=ReviewDecision),
):
    ctx = get_service_context(commons)
    return await ReviewService(ctx).accept_review(review_id, payload)


@router.post(
    "/reviews/{review_id}/reject",
    description="Rejects a pending review through gw_fct_core_feature_edit_request_reject.",
    response_model=ReviewResultResponse,
    response_model_exclude_unset=True,
)
async def reject_review(
    commons: CommonsDep,
    review_id: int = _REVIEW_ID,
    payload: ReviewDecision = Body(default_factory=ReviewDecision),
):
    ctx = get_service_context(commons)
    return await ReviewService(ctx).reject_review(review_id, payload)
