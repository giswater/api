"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import json
from datetime import datetime
from typing import Any, Dict, Literal

from fastapi import HTTPException

from ..core.exceptions import ProcedureError
from ..schemas.common import APIResponse


def create_body_dict(
    project_epsg=None,
    client_extras=None,
    form=None,
    feature=None,
    filter_fields=None,
    page_info=None,
    extras=None,
    cur_user: str | None = "anonymous",
    device: int = 4,
    lang: str = "es_ES",
) -> str:
    """
    Create request body dictionary for database functions.

    Args:
        project_epsg: Project EPSG code
        client_extras: Extra client parameters
        form: Form data
        feature: Feature data
        filter_fields: Filter fields
        extras: Extra data
        cur_user: Current user (from JWT or config)
        device: Device identifier (from X-Device header)

    Returns:
        Formatted JSON string
    """
    info_type = 1
    if cur_user == "anonymous":
        cur_user = None

    client_extras, form, feature, filter_fields, page_info, extras = _manage_body_params(
        client_extras, form, feature, filter_fields, page_info, extras
    )

    client = {"device": device, "lang": lang, "cur_user": cur_user, **client_extras}
    if info_type is not None:
        client["infoType"] = info_type
    if project_epsg is not None:
        client["epsg"] = project_epsg

    def json_default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    json_str = json.dumps(
        {
            "client": client,
            "form": form,
            "feature": feature,
            # pageInfo must be JSON null when unused: DB functions such as
            # gw_fct_getfeatures treat any non-null pageInfo as "paginated mode"
            # and skip their legacy camelCase projection.
            "data": {"filterFields": filter_fields, "pageInfo": page_info or None, **extras},
        },
        default=json_default,
    )
    return json_str


def _manage_body_params(client_extras, form, feature, filter_fields, page_info, extras):
    if client_extras is None:
        client_extras = {}
    if form is None:
        form = {}
    if feature is None:
        feature = {}
    if filter_fields is None:
        filter_fields = {}
    if page_info is None:
        page_info = {}
    if extras is None:
        extras = {}
    return client_extras, form, feature, filter_fields, page_info, extras


def create_api_response(
    message: str, status: Literal["Accepted", "Failed"], result: Dict[str, Any] | Any | None = None
) -> APIResponse:
    """
    Creates a standardized API response.

    Args:
        message: Response message
        status: Response status ("Accepted" or "Failed")
        result: Optional result data to include in the response

    Returns:
        APIResponse containing the standardized response
    """
    return APIResponse(message=message, status=status, result=result)


def ensure_procedure_accepted(result: dict | None) -> dict:
    """
    Validate procedure result and raise ProcedureError on failure.

    Raises:
        ProcedureError: If result is None or status is not "Accepted"
    """
    if not result:
        raise ProcedureError(
            {
                "status": "Failed",
                "message": {"level": 2, "text": "Database returned null"},
                "body": {},
            }
        )
    if result.get("status") != "Accepted":
        raise ProcedureError(result)
    return result


def handle_procedure_result(result: dict | None) -> dict:
    """
    Validate procedure result and raise appropriate exception on error.

    Args:
        result: Result from execute_procedure

    Returns:
        The result dict if valid

    Raises:
        HTTPException: If result is None
        ProcedureError: If result status is not "Accepted"
    """
    try:
        return ensure_procedure_accepted(result)
    except ProcedureError as exc:
        if exc.result.get("message", {}).get("text") == "Database returned null":
            raise HTTPException(status_code=500, detail="Database returned null") from exc
        raise
