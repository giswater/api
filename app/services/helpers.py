"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging

from app.db.version import get_db_version
from app.services.context import ServiceContext


async def accepted_data_response(ctx: ServiceContext, message: str, data: dict) -> dict:
    log = ctx.logger or logging.getLogger(__name__)
    db_version = await get_db_version(log, ctx.db_manager, schema=ctx.schema)
    return {
        "status": "Accepted",
        "message": {"level": 3, "text": message},
        "version": {"api": ctx.api_version, "db": db_version},
        "body": {"form": {}, "feature": {}, "data": data},
    }


async def accepted_v2_response(ctx: ServiceContext, message: str, body: dict) -> dict:
    """Accepted envelope with the payload as `body` (no form/feature/data wrap)."""
    log = ctx.logger or logging.getLogger(__name__)
    db_version = await get_db_version(log, ctx.db_manager, schema=ctx.schema)
    return {
        "status": "Accepted",
        "message": {"level": 3, "text": message},
        "version": {"api": ctx.api_version, "db": db_version},
        "body": body,
    }
