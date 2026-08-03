"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import TenantUserDep
from app.jobs.exceptions import JobNotFoundError
from app.jobs.service import JobService
from app.schemas.jobs import JobResultResponse, JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _retry_after_header(poll_interval_ms: int | None) -> dict[str, str]:
    if poll_interval_ms is None:
        return {}
    seconds = max(1, poll_interval_ms // 1000)
    return {"Retry-After": str(seconds)}


@router.get("/{job_id}", summary="Get job status", response_model=JobStatusResponse)
async def get_job_status(job_id: UUID, commons: TenantUserDep, response: Response):
    tenant = commons["tenant"]
    try:
        status_response = await JobService(tenant).get_job_status(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    for key, value in _retry_after_header(status_response.poll_interval_ms).items():
        response.headers[key] = value

    return status_response


@router.get("/{job_id}/result", summary="Get job result", response_model=JobResultResponse)
async def get_job_result(job_id: UUID, commons: TenantUserDep):
    tenant = commons["tenant"]
    try:
        result_response = await JobService(tenant).get_job_result(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return result_response
