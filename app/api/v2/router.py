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

from app.api.deps import require_feature
from app.api.v1.endpoints import auth, system
from app.api.v2.endpoints.om import mincut
from app.tenancy.registry import Tenant

# Tuple list: `APIRouter` is not hashable in Python 3.13+ (cannot use as dict keys).
ROUTER_FEATURES: list[tuple[APIRouter, str]] = [
    (mincut.router, "api_mincut"),
]

# Map endpoint callables to feature flag — used for per-tenant OpenAPI filtering.
FEATURE_BY_ENDPOINT: dict[Callable[..., Any], str] = {}
for _rtr, _flag in ROUTER_FEATURES:
    for _route in _rtr.routes:
        ep = getattr(_route, "endpoint", None)
        if callable(ep):
            FEATURE_BY_ENDPOINT[ep] = _flag

# Endpoints only meaningful when the tenant uses Keycloak.
KEYCLOAK_ONLY_ENDPOINTS = frozenset({auth.token})


def register_v2(tenant_app: FastAPI) -> None:
    """Include v2 routers on the tenant app, feature-gated, plus shared system/auth routers."""
    for router, flag in ROUTER_FEATURES:
        tenant_app.include_router(router, dependencies=[Depends(require_feature(flag))])
    tenant_app.include_router(system.router)
    tenant_app.include_router(auth.router)


def tenant_openapi_routes(tenant_app: FastAPI, tenant: Tenant) -> list[BaseRoute]:
    """Routes to expose in OpenAPI for this tenant (feature toggles)."""
    out: list[BaseRoute] = []
    for route in tenant_app.routes:
        ep = getattr(route, "endpoint", None)
        flag = FEATURE_BY_ENDPOINT.get(ep) if callable(ep) else None
        if ep in KEYCLOAK_ONLY_ENDPOINTS and tenant.settings.auth_mode != "keycloak":
            continue
        if flag is None or getattr(tenant.settings, flag, False):
            out.append(route)
    return out
