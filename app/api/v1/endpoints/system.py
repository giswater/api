"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth import verify_admin
from app.core.config import global_settings
from app.core.constants import STATIC_PREFIX
from app.schemas.common import SchemasResponse
from app.services.system_service import SystemService
from app.utils.rate_limit import create_rate_limiter

_LOGS_UI_PATH = Path("app/static/logs.html")
_LOGS_UI_HTML = _LOGS_UI_PATH.read_text(encoding="utf-8").replace("__STATIC_PREFIX__", STATIC_PREFIX)

router = APIRouter(tags=["System"])

schema_rate_limiter = create_rate_limiter(
    max_requests=global_settings.rate_limit_default_max_requests,
    window_seconds=global_settings.rate_limit_default_window_seconds,
    scope="schemas_endpoint",
)


def _tenant(request: Request):
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not specified")
    return tenant


@router.get("/ready", description="Readiness probe for the resolved tenant.")
async def ready(request: Request):
    tenant = _tenant(request)
    result = await SystemService(tenant).ready()
    if result.get("status") != "ready":
        return JSONResponse(status_code=503, content=result)
    return result


@router.get(
    "/logs", description="Query HTTP request logs for the current tenant.", dependencies=[Depends(verify_admin)]
)
async def get_logs(
    request: Request,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    endpoint: str | None = Query(default=None),
    method: str | None = Query(default=None),
    status: int | None = Query(default=None),
    user: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    return await SystemService(_tenant(request)).get_logs(
        from_=from_,
        to=to,
        endpoint=endpoint,
        method=method,
        status=status,
        user=user,
        request_id=request_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/logs/db",
    description="Return database-level logs linked to a specific API request.",
    dependencies=[Depends(verify_admin)],
)
async def get_db_logs(
    request: Request,
    request_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=500),
):
    return await SystemService(_tenant(request)).get_db_logs(request_id, limit)


@router.get(
    "/logs/ui",
    description="Serve the log viewer UI with the resolved STATIC_PREFIX baked in.",
    include_in_schema=False,
    dependencies=[Depends(verify_admin)],
)
async def logs_ui():
    return HTMLResponse(_LOGS_UI_HTML)


@router.get(
    "/schemas",
    description="List Giswater project schemas on this tenant (those with sys_version).",
    response_model=SchemasResponse,
)
async def list_schemas(request: Request):
    return await SystemService(_tenant(request)).list_schemas()


@router.get(
    "/schemas/{schema}",
    description="Validate that a schema exists in the current tenant's database.",
    dependencies=[Depends(schema_rate_limiter)],
)
async def get_schema_endpoint(request: Request, schema: str):
    return await SystemService(_tenant(request)).validate_schema(schema)
