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
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import AgentScalarConfig, get_scalar_api_reference

from .api.exception_handlers import register_exception_handlers
from .api.admin.router import register_admin
from .api.v1 import router as v1_router
from .api.v2 import router as v2_router
from .api.versioning import include_routers, tenant_openapi_routes
from .auth import verify_admin
from .core.config import global_settings
from .core.constants import (
    ADMIN_PREFIX,
    API_VERSIONS,
    GLOBAL_HEALTH_PATH,
    STATIC_PREFIX,
    TENANT_PREFIXES,
    UNRELEASED_API_VERSIONS,
)
from .core.openapi import apply_tenant_security, scalar_authentication
from .middleware.request_logging import request_logging_middleware
from .schemas.common import GwErrorResponse
from .tenancy import state
from .tenancy.host_middleware import host_middleware
from .tenancy.registry import Tenant, TenantRegistry
from .utils.log_setup import create_log
from .utils.plugins import load_plugins
from .jobs.types import load_job_types
from .mcp import runtime as mcp_runtime

TITLE = "Giswater API"
VERSION = pkg_version("giswater-api")
DESCRIPTION = "API for interacting with a Giswater database."
SCALAR_JS_URL = "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.77.0"
logger = logging.getLogger(__name__)

_TENANT_RESPONSES = {
    500: {"model": GwErrorResponse, "description": "Database function error"},
    503: {"model": GwErrorResponse, "description": "Database unavailable"},
}


def _docs_html(openapi_url: str, title: str, authentication: dict | None = None):
    return get_scalar_api_reference(
        openapi_url=openapi_url,
        title=title,
        scalar_js_url=SCALAR_JS_URL,
        scalar_favicon_url=f"{STATIC_PREFIX}/favicon.ico",
        authentication=authentication,
        persist_auth=True,
        telemetry=False,
        agent=AgentScalarConfig(disabled=True),
    )


def _register_health_route(app: FastAPI, path: str = "/health") -> None:
    @app.get(path, include_in_schema=False)
    async def health():
        """Liveness probe: process is up."""
        return {"status": "ok"}


def _version_copy(version: str) -> tuple[str, str]:
    title = f"{TITLE} {version}"
    description = DESCRIPTION
    if version in UNRELEASED_API_VERSIONS:
        title += " (unreleased)"
        description = f"{DESCRIPTION} This version is unreleased and may change without notice."
    return title, description


def _create_tenant_app(version: str) -> FastAPI:
    title, description = _version_copy(version)
    return FastAPI(
        version=VERSION,
        title=title,
        description=description,
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
        responses=_TENANT_RESPONSES,
    )


def _register_tenant_meta_routes(app: FastAPI, version: str) -> None:
    prefix = TENANT_PREFIXES[version]
    title, description = _version_copy(version)

    @app.get("/", summary="Service status")
    async def tenant_root():
        return {
            "status": "Accepted",
            "message": f"{TITLE} is running.",
            "version": VERSION,
            "description": DESCRIPTION,
        }

    @app.get("/openapi.json", include_in_schema=False)
    async def tenant_openapi_json(request: Request):
        tenant: Tenant = request.state.tenant
        routes = tenant_openapi_routes(app, tenant)
        root_path = request.scope.get("root_path") or prefix
        schema = get_openapi(
            title=title,
            version=VERSION,
            description=description,
            routes=routes,
            servers=[{"url": root_path}],
        )
        schema = apply_tenant_security(schema, tenant, root_path)
        return JSONResponse(schema)

    @app.get("/docs", include_in_schema=False)
    async def tenant_docs(request: Request):
        return _docs_html(
            f"{prefix}/openapi.json",
            f"{title} - docs",
            scalar_authentication(request.state.tenant, str(request.url_for("tenant_docs_oauth2_redirect"))),
        )

    # DEPRECATED #44: landing page for the Swagger-era Keycloak redirect URI; remove in 2.0.0
    @app.get("/docs/oauth2-redirect", include_in_schema=False)
    async def tenant_docs_oauth2_redirect():
        return HTMLResponse("<!doctype html>")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        favicon_path = os.path.join("app", "static", "favicon.ico")
        return FileResponse(favicon_path)


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
    responses=_TENANT_RESPONSES,
)

admin_app = FastAPI(
    title=f"{TITLE} - Admin",
    version=VERSION,
    description="Platform admin API",
    docs_url=None,
    openapi_url="/openapi.json",
    dependencies=[Depends(verify_admin)],
    responses={
        500: {"model": GwErrorResponse, "description": "Database function error"},
        503: {"model": GwErrorResponse, "description": "Database unavailable"},
    },
)
register_admin(admin_app)


async def admin_docs(_request: Request):
    return _docs_html(f"{ADMIN_PREFIX}/openapi.json", f"{TITLE} - Admin")


# Plain route, same as FastAPI's built-in docs: stays outside verify_admin.
admin_app.add_route("/docs", admin_docs, include_in_schema=False)

VERSION_ROUTERS = {"v1": v1_router.ROUTERS, "v2": v2_router.ROUTERS}

tenant_apps: dict[str, FastAPI] = {}
for _version in API_VERSIONS:
    _tenant_app = _create_tenant_app(_version)
    include_routers(_tenant_app, VERSION_ROUTERS[_version])
    _register_tenant_meta_routes(_tenant_app, _version)
    tenant_apps[_version] = _tenant_app
    parent.mount(TENANT_PREFIXES[_version], _tenant_app)

parent.mount(ADMIN_PREFIX, admin_app)
parent.mount(STATIC_PREFIX, StaticFiles(directory="app/static"), name="static")

_register_health_route(parent, GLOBAL_HEALTH_PATH)
_register_health_route(admin_app)
for _tenant_app in tenant_apps.values():
    _register_health_route(_tenant_app)


# Middleware order: Starlette runs LIFO — register host_middleware first so it runs inner.
parent.middleware("http")(host_middleware)
parent.middleware("http")(request_logging_middleware)

register_exception_handlers(parent)
register_exception_handlers(admin_app)
for _tenant_app in tenant_apps.values():
    register_exception_handlers(_tenant_app)

load_plugins(tenant_apps["v1"])

mcp_runtime.configure(root_app=parent)
tenant_apps["v1"].add_api_route(
    "/mcp",
    mcp_runtime.mcp_http_endpoint,
    methods=["GET", "POST", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
tenant_apps["v1"].mount("/mcp", mcp_runtime.mcp_dispatch)

app = parent
