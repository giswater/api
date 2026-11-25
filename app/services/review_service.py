"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.core.exceptions import InvalidParametersError
from app.db.execution import execute_sql
from app.schemas.features.review_models import (
    CreateReviewData,
    ListReviewsData,
    Review,
    ReviewCreate,
    ReviewDecision,
    ReviewResult,
    ReviewStatus,
)
from app.services.context import ServiceContext
from app.services.helpers import accepted_v2_response

_LIST_COLUMNS = """
id, table_name, table_id, feature_code, feature_type, expl_id,
field_user, field_date, field_annotation, field_changes, review_changes,
review_user, review_date, review_annotation, status, status_name
"""

_GET_COLUMNS = f"{_LIST_COLUMNS}, child_layer, current_values"


class ReviewService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def _call(self, query: str, parameters: tuple = ()) -> list[dict]:
        return await execute_sql(
            self.ctx.logger,
            self.ctx.db_manager,
            query,
            parameters=parameters or None,
            schema=self.ctx.schema,
            user=self.ctx.user_id,
            db_role=self.ctx.db_role,
        )

    async def _accepted(self, message: str, payload: BaseModel) -> dict:
        return await accepted_v2_response(
            self.ctx,
            message,
            payload.model_dump(mode="json", exclude_unset=True),
        )

    async def create_review(self, payload: ReviewCreate) -> dict:
        if not payload.changes:
            raise InvalidParametersError("changes must not be empty")

        rows = await self._call(
            "SELECT {schema}.gw_fct_core_feature_edit_request_create(%s, %s, %s::jsonb, %s) AS id",
            (payload.table_name, payload.table_id, Jsonb(payload.changes), payload.annotation),
        )
        return await self._accepted("Review created", CreateReviewData.model_validate(rows[0]))

    async def list_reviews(
        self,
        *,
        status: int = 0,
        table_name: Optional[str] = None,
        field_user: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> dict:
        rows = await self._call(
            f"SELECT {_LIST_COLUMNS} FROM {{schema}}.gw_fct_core_feature_edit_request_get_list()"
        )
        matched = [
            row
            for row in rows
            if _matches(row, status, table_name, field_user, date_from, date_to)
        ]
        matched.sort(key=_field_date_key, reverse=True)
        return await self._accepted(
            "Fetched reviews",
            ListReviewsData.model_validate({"reviews": matched[:limit]}),
        )

    async def get_review(self, review_id: int) -> dict:
        rows = await self._call(
            f"SELECT {_GET_COLUMNS} FROM {{schema}}.gw_fct_core_feature_edit_request_get(%s)",
            (review_id,),
        )
        if not rows:
            raise LookupError(f"Review {review_id} not found")
        return await self._accepted("Fetched review", Review.model_validate(rows[0]))

    async def accept_review(self, review_id: int, decision: ReviewDecision) -> dict:
        changes = Jsonb(decision.changes) if decision.changes is not None else None
        await self._call(
            "SELECT {schema}.gw_fct_core_feature_edit_request_accept(%s, %s, %s::jsonb) AS accepted",
            (review_id, decision.annotation, changes),
        )
        return await self._accepted(
            "Review accepted",
            ReviewResult(id=review_id, status=ReviewStatus.ACCEPTED),
        )

    async def reject_review(self, review_id: int, decision: ReviewDecision) -> dict:
        await self._call(
            "SELECT {schema}.gw_fct_core_feature_edit_request_reject(%s, %s) AS rejected",
            (review_id, decision.annotation),
        )
        return await self._accepted(
            "Review rejected",
            ReviewResult(id=review_id, status=ReviewStatus.REJECTED),
        )


def _matches(
    row: dict,
    status: int,
    table_name: Optional[str],
    field_user: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> bool:
    if row.get("status") != status:
        return False
    if table_name and row.get("table_name") != table_name:
        return False
    if field_user and field_user.casefold() not in (row.get("field_user") or "").casefold():
        return False
    field_day = _field_day(row.get("field_date"))
    if date_from is not None and (field_day is None or field_day < date_from):
        return False
    if date_to is not None and (field_day is None or field_day > date_to):
        return False
    return True


def _field_day(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _field_date_key(row: dict) -> float:
    value = row.get("field_date")
    if isinstance(value, datetime):
        return value.timestamp()
    return float("-inf")
