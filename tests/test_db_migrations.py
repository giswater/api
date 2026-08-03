"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.

Integration tests for the Alembic-managed `gwapi` schema. Require Postgres
(the same gw-db container the rest of the suite uses) and run schema-agnostic,
so they are not tagged with the `ws`/`ud` markers.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import pytest

from app.core.config import TenantSettings
from app.db.log_store import insert_api_log
from app.db.manager import DatabaseManager
from app.db.migrate import get_current_revision, head_revision, run_alembic_upgrade
from app.db.schema import (
    DB_LOG_TABLE,
    GWAPI_SCHEMA,
    HTTP_LOG_TABLE,
    JOBS_TABLE,
    LEGACY_DB_LOG_TABLE,
    LEGACY_HTTP_LOG_TABLE,
    LEGACY_LOG_SCHEMA,
    invalidate_log_schema_cache,
    resolve_log_schema,
    resolve_log_targets,
    table_exists,
)


def _database_url() -> str:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "gw_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    return (
        f"postgresql://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
        f"@{db_host}:{db_port}/{quote(db_name, safe='')}"
        "?application_name=giswater-api&sslmode=disable"
    )


def _db_manager(tenant_id: str) -> DatabaseManager:
    settings = TenantSettings(
        database_url=_database_url(),
        db_schema=os.getenv("DB_SCHEMA", "public"),
        db_pool_min_size=1,
        db_pool_max_size=2,
        db_connect_timeout=5.0,
    )
    return DatabaseManager(settings, tenant_id)


async def _exec(db, statements: list[str]) -> None:
    async with db.get_db() as conn:
        assert conn is not None, "Postgres not available"
        async with conn.cursor() as cur:
            for stmt in statements:
                await cur.execute(stmt)
        await conn.commit()


async def _table_exists(db, schema: str, table: str) -> bool:
    async with db.get_db() as conn:
        assert conn is not None
        return await table_exists(conn, schema, table)


async def _reset_api_objects(db) -> None:
    """Remove API-owned objects without touching unrelated `log` content."""
    await _exec(
        db,
        [
            "DROP SCHEMA IF EXISTS gwapi CASCADE",
            f"DROP TABLE IF EXISTS {LEGACY_LOG_SCHEMA}.{LEGACY_HTTP_LOG_TABLE} CASCADE",
            f"DROP TABLE IF EXISTS {LEGACY_LOG_SCHEMA}.{LEGACY_DB_LOG_TABLE} CASCADE",
        ],
    )


_LEGACY_LOG_DDL = [
    f"CREATE SCHEMA IF NOT EXISTS {LEGACY_LOG_SCHEMA}",
    f"""
    CREATE TABLE IF NOT EXISTS {LEGACY_LOG_SCHEMA}.{LEGACY_HTTP_LOG_TABLE} (
        ts timestamptz NOT NULL,
        id bigserial NOT NULL,
        method text NOT NULL,
        endpoint text NOT NULL,
        status integer NOT NULL,
        duration_ms integer,
        user_name text,
        request_id uuid,
        client_ip inet,
        query_params jsonb,
        body_size integer,
        response_size integer,
        request_headers jsonb,
        request_body text,
        response_headers jsonb,
        response_body text,
        PRIMARY KEY (ts, id)
    ) PARTITION BY RANGE (ts)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {LEGACY_LOG_SCHEMA}.{LEGACY_DB_LOG_TABLE} (
        ts timestamptz NOT NULL,
        id bigserial NOT NULL,
        request_id uuid,
        schema_name text,
        function_name text,
        sql_text text,
        response_json text,
        duration_ms integer,
        status text,
        error text,
        PRIMARY KEY (ts, id)
    ) PARTITION BY RANGE (ts)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {LEGACY_LOG_SCHEMA}.{LEGACY_HTTP_LOG_TABLE}_2026_06
    PARTITION OF {LEGACY_LOG_SCHEMA}.{LEGACY_HTTP_LOG_TABLE}
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
    """,
]


def _run(coro):
    return asyncio.run(coro)


def test_alembic_fresh_install():
    tid = f"mig-fresh-{uuid.uuid4().hex[:8]}"

    async def scenario():
        db = _db_manager(tid)
        try:
            await _reset_api_objects(db)
            invalidate_log_schema_cache(tid)

            await run_alembic_upgrade(db)

            assert await _table_exists(db, GWAPI_SCHEMA, HTTP_LOG_TABLE)
            assert await _table_exists(db, GWAPI_SCHEMA, DB_LOG_TABLE)
            assert await _table_exists(db, GWAPI_SCHEMA, "users")
            assert await _table_exists(db, GWAPI_SCHEMA, JOBS_TABLE)
            assert not await _table_exists(db, LEGACY_LOG_SCHEMA, LEGACY_HTTP_LOG_TABLE)
            assert await get_current_revision(db.database_url) == head_revision()
            targets = await resolve_log_targets(db)
            assert targets.schema == GWAPI_SCHEMA
            assert targets.http_table == HTTP_LOG_TABLE
            assert targets.db_table == DB_LOG_TABLE
        finally:
            await _reset_api_objects(db)
            await db.close()

    _run(scenario())


def test_alembic_relocate_log_schema():
    tid = f"mig-reloc-{uuid.uuid4().hex[:8]}"

    async def scenario():
        db = _db_manager(tid)
        try:
            await _reset_api_objects(db)
            invalidate_log_schema_cache(tid)
            await _exec(db, _LEGACY_LOG_DDL)
            await _exec(
                db,
                [
                    f"INSERT INTO {LEGACY_LOG_SCHEMA}.{LEGACY_HTTP_LOG_TABLE} "
                    "(ts, method, endpoint, status) "
                    "VALUES ('2026-06-15T10:00:00Z', 'GET', '/probe', 200)"
                ],
            )

            await run_alembic_upgrade(db)

            assert await _table_exists(db, GWAPI_SCHEMA, HTTP_LOG_TABLE)
            assert await _table_exists(db, GWAPI_SCHEMA, DB_LOG_TABLE)
            assert await _table_exists(db, GWAPI_SCHEMA, JOBS_TABLE)
            assert not await _table_exists(db, GWAPI_SCHEMA, LEGACY_HTTP_LOG_TABLE)
            assert not await _table_exists(db, LEGACY_LOG_SCHEMA, LEGACY_HTTP_LOG_TABLE)
            assert await _table_exists(db, GWAPI_SCHEMA, f"{HTTP_LOG_TABLE}_2026_06")
            assert not await _table_exists(db, GWAPI_SCHEMA, f"{LEGACY_HTTP_LOG_TABLE}_2026_06")
            async with db.get_db() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(f"SELECT count(*) FROM {GWAPI_SCHEMA}.{HTTP_LOG_TABLE}")
                    (count,) = await cur.fetchone()
            assert count == 1
            assert await resolve_log_schema(db) == GWAPI_SCHEMA
        finally:
            await _reset_api_objects(db)
            await db.close()

    _run(scenario())


def test_log_insert_after_migration():
    tid = f"mig-insert-{uuid.uuid4().hex[:8]}"

    async def scenario():
        db = _db_manager(tid)
        try:
            await _reset_api_objects(db)
            invalidate_log_schema_cache(tid)
            await run_alembic_upgrade(db)

            await insert_api_log(
                db,
                {
                    "ts": datetime.now(timezone.utc),
                    "method": "GET",
                    "endpoint": "/after-migration",
                    "status": 200,
                    "request_id": uuid.uuid4(),
                },
            )

            async with db.get_db() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT count(*) FROM {GWAPI_SCHEMA}.{HTTP_LOG_TABLE} WHERE endpoint = %s",
                        ("/after-migration",),
                    )
                    (count,) = await cur.fetchone()
            assert count == 1
        finally:
            await _reset_api_objects(db)
            await db.close()

    _run(scenario())


def test_legacy_log_schema_without_migrate():
    """With migration deferred, inserts keep working against the legacy schema."""
    tid = f"mig-legacy-{uuid.uuid4().hex[:8]}"

    async def scenario():
        db = _db_manager(tid)
        try:
            await _reset_api_objects(db)
            invalidate_log_schema_cache(tid)
            await _exec(db, _LEGACY_LOG_DDL)

            targets = await resolve_log_targets(db)
            assert targets.schema == LEGACY_LOG_SCHEMA
            assert targets.http_table == LEGACY_HTTP_LOG_TABLE
            assert targets.db_table == LEGACY_DB_LOG_TABLE

            await insert_api_log(
                db,
                {
                    "ts": datetime(2026, 6, 20, tzinfo=timezone.utc),
                    "method": "POST",
                    "endpoint": "/legacy",
                    "status": 201,
                    "request_id": uuid.uuid4(),
                },
            )

            async with db.get_db() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT count(*) FROM {LEGACY_LOG_SCHEMA}.{LEGACY_HTTP_LOG_TABLE} WHERE endpoint = %s",
                        ("/legacy",),
                    )
                    (count,) = await cur.fetchone()
            assert count == 1
        finally:
            await _reset_api_objects(db)
            await db.close()

    _run(scenario())


def test_resolver_switches_after_upgrade():
    tid = f"mig-switch-{uuid.uuid4().hex[:8]}"

    async def scenario():
        db = _db_manager(tid)
        try:
            await _reset_api_objects(db)
            invalidate_log_schema_cache(tid)
            await _exec(db, _LEGACY_LOG_DDL)
            assert await resolve_log_schema(db) == LEGACY_LOG_SCHEMA

            await run_alembic_upgrade(db)

            targets = await resolve_log_targets(db)
            assert targets.schema == GWAPI_SCHEMA
            assert targets.http_table == HTTP_LOG_TABLE
            assert targets.db_table == DB_LOG_TABLE
        finally:
            await _reset_api_objects(db)
            await db.close()

    _run(scenario())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
