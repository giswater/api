"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from starlette.types import ASGIApp

from fastmcp import FastMCP

from app.mcp.client import TenantApi
from app.mcp.tools import REGISTRY
from app.tenancy.registry import Tenant

_INSTRUCTIONS = (
    "Call list_schemas first (no arguments). It returns each project's schema name, "
    "type (WS or UD), giswater version, and epsg. Every other tool requires a `schema` "
    "argument. Pick the schema matching the user's intent; if it is ambiguous, ask the "
    "user which schema to use. Never guess. Coordinates are in the project CRS (pass "
    "`epsg` from list_schemas), not WGS84 lat/lon."
)


def build_tenant_mcp(tenant: Tenant, root_app: ASGIApp) -> FastMCP:
    api = TenantApi(tenant, root_app)
    mcp = FastMCP(name=f"Giswater API ({tenant.id})", instructions=_INSTRUCTIONS)
    for spec in REGISTRY:
        if spec.feature is None or getattr(tenant.settings, spec.feature, False):
            mcp.tool(spec.bind(api), name=spec.fn.__name__, annotations=spec.annotations)
    mcp._gw_api = api  # closed by TenantMcp.aclose
    return mcp
