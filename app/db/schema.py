"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Single API-owned schema: basic-auth tables + audit log tables + jobs.
GWAPI_SCHEMA = "gwapi"

# DEPRECATED #28: pre-1.6.0 deployments kept audit logs in the `log` schema.
# The resolver below keeps reading/writing it until Alembic relocates the
# tables into `gwapi`. Remove in 2.0.0 (grep `DEPRECATED #28`).
LEGACY_LOG_SCHEMA = "log"

# Auth tables
GWAPI_USERS_TABLE = "users"
GWAPI_ROLES_TABLE = "roles"
GWAPI_USER_ROLES_TABLE = "user_roles"

# Background jobs table
JOBS_TABLE = "jobs"

# Audit log tables (current names in `gwapi`)
HTTP_LOG_TABLE = "http_logs"
DB_LOG_TABLE = "db_logs"

# Legacy table names (still used in the `log` schema until migration succeeds)
LEGACY_HTTP_LOG_TABLE = "gw_api_logs"
LEGACY_DB_LOG_TABLE = "gw_api_logs_db"


@dataclass(frozen=True)
class LogTargets:
    """Schema + table names for HTTP and DB audit logs."""

    schema: str
    http_table: str
    db_table: str


# Per-tenant cache of resolved log targets. Cleared after a successful migration
# so the next request picks up `gwapi` (see migrate.run_alembic_upgrade).
_log_targets_cache: dict[str, LogTargets] = {}


def invalidate_log_schema_cache(tenant_id: str | None = None) -> None:
    if tenant_id is None:
        _log_targets_cache.clear()
    else:
        _log_targets_cache.pop(tenant_id, None)


async def table_exists(conn, schema: str, table: str) -> bool:
    async with conn.cursor() as cursor:
        await cursor.execute(
            "SELECT to_regclass(%s) IS NOT NULL",
            (f"{schema}.{table}",),
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def _detect_log_targets(db_manager) -> LogTargets | None:
    """Detect where audit log tables live for this tenant.

    Returns None when the database is unreachable so the caller can avoid
    caching a transient default.
    """
    async with db_manager.get_db() as conn:
        if conn is None:
            return None
        if await table_exists(conn, GWAPI_SCHEMA, HTTP_LOG_TABLE):
            return LogTargets(GWAPI_SCHEMA, HTTP_LOG_TABLE, DB_LOG_TABLE)
        if await table_exists(conn, LEGACY_LOG_SCHEMA, LEGACY_HTTP_LOG_TABLE):
            logger.warning(
                "[%s] DEPRECATED #28: audit logs still in the 'log' schema; run "
                "'giswater-api db upgrade' to relocate them to 'gwapi'. Removal in 2.0.0.",
                db_manager.tenant_id,
            )
            return LogTargets(LEGACY_LOG_SCHEMA, LEGACY_HTTP_LOG_TABLE, LEGACY_DB_LOG_TABLE)
    # Neither exists yet (e.g. fresh DB before migration); target gwapi.
    return LogTargets(GWAPI_SCHEMA, HTTP_LOG_TABLE, DB_LOG_TABLE)


async def resolve_log_targets(db_manager) -> LogTargets:
    """Resolve schema and table names for audit log reads/writes.

    Prefers `gwapi.http_logs` / `gwapi.db_logs`; falls back to the legacy
    `log.gw_api_logs*` names until migration has moved and renamed the tables.
    Result is cached per tenant.
    """
    tenant_id = db_manager.tenant_id
    cached = _log_targets_cache.get(tenant_id)
    if cached is not None:
        return cached
    targets = await _detect_log_targets(db_manager)
    if targets is None:
        # DB transiently unavailable; do not cache the optimistic default.
        return LogTargets(GWAPI_SCHEMA, HTTP_LOG_TABLE, DB_LOG_TABLE)
    _log_targets_cache[tenant_id] = targets
    return targets


async def resolve_log_schema(db_manager) -> str:
    """Return the schema for audit log reads/writes (legacy fallback aware)."""
    return (await resolve_log_targets(db_manager)).schema
