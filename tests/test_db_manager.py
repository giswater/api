"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from psycopg import OperationalError

from app.core.config import TenantSettings
from app.db.manager import DatabaseManager


def _manager() -> DatabaseManager:
    return DatabaseManager(TenantSettings(), "main")


def _live_db_manager(tenant_id: str) -> DatabaseManager:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "gw_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    url = (
        f"postgresql://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
        f"@{db_host}:{db_port}/{quote(db_name, safe='')}"
        "?application_name=giswater-api&sslmode=disable"
    )
    return DatabaseManager(
        TenantSettings(
            database_url=url,
            db_pool_min_size=1,
            db_pool_max_size=1,
            db_connect_timeout=5.0,
        ),
        tenant_id,
    )


def test_reset_pooled_connection_runs_reset_role():
    async def _run():
        conn = AsyncMock()
        await DatabaseManager._reset_pooled_connection(conn)
        conn.execute.assert_awaited_once_with("RESET ROLE")
        conn.commit.assert_awaited_once_with()

    asyncio.run(_run())


def test_init_conn_pool_registers_reset_callback():
    async def _run():
        mgr = _manager()
        fake_pool = MagicMock()
        fake_pool.open = AsyncMock()

        with patch("app.db.manager.AsyncConnectionPool", return_value=fake_pool) as pool_cls:
            await mgr.init_conn_pool()

        assert mgr.connection_pool is fake_pool
        kwargs = pool_cls.call_args.kwargs
        assert kwargs["reset"] is DatabaseManager._reset_pooled_connection

    asyncio.run(_run())


def test_get_db_does_not_retry_when_body_raises_psycopg_error():
    """Regression: errors after yield must propagate, not become 'athrow' / acquire retries."""

    async def _run():
        mgr = _manager()
        conn = object()
        checkouts = 0

        @asynccontextmanager
        async def fake_connection():
            nonlocal checkouts
            checkouts += 1
            yield conn

        pool = MagicMock()
        pool.connection = fake_connection
        pool.close = AsyncMock()
        mgr.connection_pool = pool

        with pytest.raises(OperationalError, match="permiso denegado"):
            async with mgr.get_db() as acquired:
                assert acquired is conn
                raise OperationalError("permiso denegado al esquema gwapi")

        assert checkouts == 1
        pool.close.assert_not_awaited()
        assert mgr.connection_pool is pool

    asyncio.run(_run())


def test_get_db_retries_acquire_failures_then_yields_none():
    async def _run():
        mgr = _manager()
        attempts = 0

        @asynccontextmanager
        async def failing_connection():
            nonlocal attempts
            attempts += 1
            raise OperationalError("connection refused")
            yield  # pragma: no cover

        pool = MagicMock()
        pool.connection = failing_connection
        pool.close = AsyncMock()
        mgr.connection_pool = pool

        with (
            patch.object(mgr, "init_conn_pool", new=AsyncMock()) as init_pool,
            patch("app.db.manager.asyncio.sleep", new=AsyncMock()) as sleep,
        ):

            async def _noop_init():
                mgr.connection_pool = pool

            init_pool.side_effect = _noop_init

            async with mgr.get_db() as acquired:
                assert acquired is None

        assert attempts == 3
        assert sleep.await_count == 2

    asyncio.run(_run())


def test_pool_reset_clears_set_role_between_checkouts():
    """SET ROLE must not leak across pool checkouts (basic-auth vs procedure role)."""
    role = f"gwapi_reset_{uuid.uuid4().hex[:8]}"
    tid = f"pool-reset-{uuid.uuid4().hex[:8]}"

    async def _run():
        db = _live_db_manager(tid)
        try:
            async with db.get_db() as conn:
                assert conn is not None, "Postgres not available"
                async with conn.cursor() as cur:
                    await cur.execute(f"CREATE ROLE {role} NOLOGIN")
                    await cur.execute(f"SET ROLE {role}")
                    await cur.execute("SELECT current_user, session_user")
                    current, session = await cur.fetchone()
                await conn.commit()
            assert current == role
            assert session != role

            async with db.get_db() as conn:
                assert conn is not None
                async with conn.cursor() as cur:
                    await cur.execute("SELECT current_user, session_user")
                    current, session = await cur.fetchone()
            assert current == session
        finally:
            try:
                async with db.get_db() as conn:
                    if conn is not None:
                        async with conn.cursor() as cur:
                            await cur.execute("RESET ROLE")
                            await cur.execute(f"DROP ROLE IF EXISTS {role}")
                        await conn.commit()
            finally:
                await db.close()

    asyncio.run(_run())
