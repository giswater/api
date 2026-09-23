"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from app.mcp.client import TenantApi
from app.mcp.registry import tool


@tool(read_only=True)
async def list_schemas(api: TenantApi) -> dict:
    """List Giswater project schemas on this tenant.

    Call this first (no arguments). Each schema is one project: water supply (WS)
    or urban drainage (UD), with its ``epsg``. Pick the schema that matches the
    user's intent; if it is ambiguous, ask the user. Never guess. Pass the chosen
    schema name to every other tool.
    """
    return await api.get("/schemas", schema=None)
