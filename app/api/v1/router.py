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
from app.api.v1.endpoints import basic, crm, features, system
from app.api.v1.endpoints.epa import dscenario
from app.api.v1.endpoints.om import flow, mincut, profile, waterbalance
from app.api.v1.endpoints.om.mapzones import dma, dqa, omunit, omzone, presszone, sector
from app.api.v1.endpoints.routing import routing
from app.tenancy.registry import Tenant

# Tuple list: `APIRouter` is not hashable in Python 3.13+ (cannot use as dict keys).
ROUTER_FEATURES: list[tuple[APIRouter, str]] = [
    (basic.router, "api_basic"),
    (features.router, "api_features"),
    (profile.router, "api_profile"),
    (flow.router, "api_flow"),
    (mincut.router, "api_mincut"),
    (waterbalance.router, "api_water_balance"),
    (routing.router, "api_routing"),
    (crm.router, "api_crm"),
    (dscenario.router, "api_epa"),
    (dma.router, "api_mapzones"),
    (sector.router, "api_mapzones"),
    (presszone.router, "api_mapzones"),
    (dqa.router, "api_mapzones"),
    (omzone.router, "api_mapzones"),
    (omunit.router, "api_mapzones"),
]

# Map endpoint callables to feature flag — used for per-tenant OpenAPI filtering.
FEATURE_BY_ENDPOINT: dict[Callable[..., Any], str] = {}
for _rtr, _flag in ROUTER_FEATURES:
    for _route in _rtr.routes:
        ep = getattr(_route, "endpoint", None)
        if callable(ep):
            FEATURE_BY_ENDPOINT[ep] = _flag


def register_v1(tenant_app: FastAPI) -> None:
    """Include all v1 routers on the tenant app, feature-gated, plus the system router."""
    for router, flag in ROUTER_FEATURES:
        tenant_app.include_router(router, dependencies=[Depends(require_feature(flag))])
    tenant_app.include_router(system.router)


def tenant_openapi_routes(tenant_app: FastAPI, tenant: Tenant) -> list[BaseRoute]:
    """Routes to expose in OpenAPI for this tenant (feature toggles)."""
    out: list[BaseRoute] = []
    for route in tenant_app.routes:
        ep = getattr(route, "endpoint", None)
        flag = FEATURE_BY_ENDPOINT.get(ep) if callable(ep) else None
        if flag is None or getattr(tenant.settings, flag, False):
            out.append(route)
    return out
