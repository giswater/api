"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.exception_handlers import register_exception_handlers
from .api.admin.router import register_admin
from .api.v1.router import register_v1, tenant_openapi_routes
from .auth import verify_admin
from .core.config import global_settings
from .core.constants import ADMIN_PREFIX, GLOBAL_HEALTH_PATH, STATIC_PREFIX, TENANT_PREFIX
from .middleware.request_logging import request_logging_middleware
from .schemas.common import GwErrorResponse
from .tenancy import state
from .tenancy.host_middleware import host_middleware
from .tenancy.registry import Tenant, TenantRegistry
from .utils.log_setup import create_log
from .utils.plugins import load_plugins
from .jobs.types import load_job_types

TITLE = "Giswater API"
VERSION = pkg_version("giswater-api")
DESCRIPTION = "API for interacting with a Giswater database."
logger = logging.getLogger(__name__)


def _register_health_route(app: FastAPI, path: str = "/health") -> None:
    @app.get(path, include_in_schema=False)
    async def health():
        """Liveness probe: process is up."""
        return {"status": "ok"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tenants_dir = Path(global_settings.tenants_dir).resolve()
    registry = TenantRegistry(tenants_dir)
    summary = await registry.load_all()
    if registry.is_empty():
        listing = sorted(p.name for p in tenants_dir.iterdir()) if tenants_dir.exists() else "<missing>"
        logger.warning(
            "No tenants loaded at startup (admin can create tenants). tenants_dir=%s cwd=%s entries=%s errors=%s",
            tenants_dir,
            os.getcwd(),
            listing,
            summary.get("errors"),
        )
    elif summary.get("errors"):
        logger.warning("Tenant load errors: %s", summary["errors"])
    if not registry.is_empty():
        logger.info("Loaded tenants from %s: %s", tenants_dir, registry.ids())

    load_job_types()

    state.registry = registry
    state.global_logger = create_log("api", os.path.join(global_settings.log_dir, "_global"))

    try:
        yield
    finally:
        await registry.close_all()
        state.registry = None
        state.global_logger = None


parent = FastAPI(
    version=VERSION,
    title=TITLE,
    description=DESCRIPTION,
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
    lifespan=lifespan,
    responses={
        500: {"model": GwErrorResponse, "description": "Database function error"},
        503: {"model": GwErrorResponse, "description": "Database unavailable"},
    },
)

tenant_app = FastAPI(
    version=VERSION,
    title=TITLE,
    description=DESCRIPTION,
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
    responses={
        500: {"model": GwErrorResponse, "description": "Database function error"},
        503: {"model": GwErrorResponse, "description": "Database unavailable"},
    },
)

register_v1(tenant_app)


@tenant_app.get("/", summary="Service status")
async def tenant_root():
    return {
        "status": "Accepted",
        "message": f"{TITLE} is running.",
        "version": VERSION,
        "description": DESCRIPTION,
    }


@tenant_app.get("/openapi.json", include_in_schema=False)
async def tenant_openapi_json(request: Request):
    tenant: Tenant = request.state.tenant
    routes = tenant_openapi_routes(tenant_app, tenant)
    root_path = request.scope.get("root_path") or TENANT_PREFIX
    schema = get_openapi(
        title=TITLE,
        version=VERSION,
        description=DESCRIPTION,
        routes=routes,
        servers=[{"url": root_path}],
    )
    return JSONResponse(schema)


@tenant_app.get("/docs", include_in_schema=False)
async def tenant_docs():
    return get_swagger_ui_html(
        openapi_url=f"{TENANT_PREFIX}/openapi.json",
        title=f"{TITLE} - docs",
    )


@tenant_app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("app", "static", "favicon.ico")
    return FileResponse(favicon_path)


admin_app = FastAPI(
    title=f"{TITLE} - Admin",
    version=VERSION,
    description="Platform admin API",
    docs_url="/docs",
    openapi_url="/openapi.json",
    dependencies=[Depends(verify_admin)],
    responses={
        500: {"model": GwErrorResponse, "description": "Database function error"},
        503: {"model": GwErrorResponse, "description": "Database unavailable"},
    },
)
register_admin(admin_app)

parent.mount(ADMIN_PREFIX, admin_app)
parent.mount(TENANT_PREFIX, tenant_app)
parent.mount(STATIC_PREFIX, StaticFiles(directory="app/static"), name="static")

_register_health_route(parent, GLOBAL_HEALTH_PATH)
for _app in (tenant_app, admin_app):
    _register_health_route(_app)


# Middleware order: Starlette runs LIFO — register host_middleware first so it runs inner.
parent.middleware("http")(host_middleware)
parent.middleware("http")(request_logging_middleware)

for _app in (parent, tenant_app, admin_app):
    register_exception_handlers(_app)

load_plugins(tenant_app)

app = parent
