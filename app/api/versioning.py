"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from starlette.routing import BaseRoute

from app.api.deps import PLUGIN_BY_ENDPOINT, require_feature
from app.api.v1.endpoints import auth
from app.tenancy.registry import Tenant

# Filled by include_routers. Endpoint callables are shared across versions.
FEATURE_BY_ENDPOINT: dict[Callable[..., Any], str] = {}

# Endpoints only meaningful when the tenant uses Keycloak.
KEYCLOAK_ONLY_ENDPOINTS = frozenset({auth.token})


def include_routers(app: FastAPI, routers: list[tuple[APIRouter, str | None]]) -> None:
    """Include routers. A flag of None means the router is always mounted."""
    for router, flag in routers:
        if flag is None:
            app.include_router(router)
            continue
        for route in router.routes:
            endpoint = getattr(route, "endpoint", None)
            if callable(endpoint):
                FEATURE_BY_ENDPOINT[endpoint] = flag
        app.include_router(router, dependencies=[Depends(require_feature(flag))])


def tenant_openapi_routes(app: FastAPI, tenant: Tenant) -> list[BaseRoute]:
    """Routes to expose in OpenAPI for this tenant (feature + plugin toggles)."""
    out: list[BaseRoute] = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if not callable(endpoint):
            out.append(route)
            continue
        if endpoint in KEYCLOAK_ONLY_ENDPOINTS and tenant.settings.auth_mode != "keycloak":
            continue
        plugin_id = PLUGIN_BY_ENDPOINT.get(endpoint)
        if plugin_id is not None:
            if tenant.settings.plugin_enabled(plugin_id):
                out.append(route)
            continue
        flag = FEATURE_BY_ENDPOINT.get(endpoint)
        if flag is None or getattr(tenant.settings, flag, False):
            out.append(route)
    return out
