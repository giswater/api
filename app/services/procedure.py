"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging

from app.core.exceptions import DatabaseUnavailableError, ProcedureError
from app.db.execution import execute_procedure
from app.services.context import ServiceContext
from app.utils.body import ensure_procedure_accepted


async def run_procedure(ctx: ServiceContext, function_name: str, body: str, conn=None) -> dict:
    log = ctx.logger or logging.getLogger(__name__)
    result = await execute_procedure(
        log,
        ctx.db_manager,
        function_name,
        body,
        schema=ctx.schema,
        api_version=ctx.api_version,
        user=ctx.user_id,
        db_role=ctx.db_role,
        conn=conn,
    )
    return ensure_procedure_accepted(result)


async def run_procedure_raw(ctx: ServiceContext, function_name: str, body: str, conn=None) -> dict | None:
    """Call a procedure without enforcing Accepted status (e.g. feature changes empty result)."""
    log = ctx.logger or logging.getLogger(__name__)
    return await execute_procedure(
        log,
        ctx.db_manager,
        function_name,
        body,
        schema=ctx.schema,
        api_version=ctx.api_version,
        user=ctx.user_id,
        db_role=ctx.db_role,
        conn=conn,
    )


def empty_procedure_response(ctx: ServiceContext, *, message: str, body: dict | None = None) -> dict:
    return {
        "status": "Failed",
        "message": {"level": 4, "text": message},
        "version": {"api": ctx.api_version},
        "body": body or {},
    }


__all__ = [
    "run_procedure",
    "run_procedure_raw",
    "empty_procedure_response",
    "ProcedureError",
    "DatabaseUnavailableError",
]
