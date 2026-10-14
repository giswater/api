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
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote

import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus

from app.core.config import TenantSettings
from app.core.exceptions import DatabaseUnavailableError
from app.db.context import DB_IDENTITY_CTX, DbIdentity
from app.db.execution import role_connection
from app.db.manager import DatabaseManager


def _manager_yielding(conn):
    mgr = MagicMock()

    @asynccontextmanager
    async def get_db():
        yield conn

    mgr.get_db = get_db
    return mgr


def _open_conn():
    conn = AsyncMock()
    conn.info = MagicMock()
    conn.info.transaction_status = TransactionStatus.INTRANS
    return conn


def test_role_connection_sets_role_from_context():
    async def _run():
        conn = _open_conn()
        token = DB_IDENTITY_CTX.set(DbIdentity(username="alice", db_role="alice_role"))
        try:
            async with role_connection(_manager_yielding(conn)) as acquired:
                assert acquired is conn
                conn.info.transaction_status = TransactionStatus.IDLE
        finally:
            DB_IDENTITY_CTX.reset(token)

        expected = sql.SQL("SET ROLE {}").format(sql.Identifier("alice_role"))
        assert conn.execute.await_args.args[0] == expected
        conn.rollback.assert_not_awaited()

    asyncio.run(_run())


def test_role_connection_skips_set_role_without_identity():
    async def _run():
        conn = _open_conn()
        token = DB_IDENTITY_CTX.set(None)
        try:
            async with role_connection(_manager_yielding(conn)) as acquired:
                assert acquired is conn
        finally:
            DB_IDENTITY_CTX.reset(token)
        conn.execute.assert_not_awaited()
        conn.rollback.assert_not_awaited()

    asyncio.run(_run())


def test_role_connection_rolls_back_open_transaction_on_error():
    async def _run():
        conn = _open_conn()
        with pytest.raises(RuntimeError, match="boom"):
            async with role_connection(_manager_yielding(conn), user="alice", db_role="alice"):
                raise RuntimeError("boom")
        conn.rollback.assert_awaited_once_with()

    asyncio.run(_run())


def test_role_connection_does_not_roll_back_idle_connection():
    async def _run():
        conn = _open_conn()
        conn.info.transaction_status = TransactionStatus.IDLE
        with pytest.raises(RuntimeError, match="already closed"):
            async with role_connection(_manager_yielding(conn), user="alice"):
                raise RuntimeError("already closed")
        conn.rollback.assert_not_awaited()

    asyncio.run(_run())


def test_role_connection_raises_when_pool_is_down():
    async def _run():
        mgr = MagicMock()

        @asynccontextmanager
        async def get_db():
            yield None

        mgr.get_db = get_db
        with pytest.raises(DatabaseUnavailableError):
            async with role_connection(mgr, user="alice"):
                pass

    asyncio.run(_run())


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


@pytest.mark.skipif(not os.getenv("DB_HOST"), reason="DB_HOST is not set")
def test_role_connection_rollback_clears_role_and_uncommitted_work():
    """A failed body rolls back SET ROLE and statements; the next checkout is the login role."""
    suffix = uuid.uuid4().hex[:8]
    role = f"gwapi_role_{suffix}"
    table = f"gwapi_role_tmp_{suffix}"
    tid = f"role-conn-{suffix}"

    async def _run():
        db = _live_db_manager(tid)
        try:
            async with db.get_db() as conn:
                if conn is None:
                    pytest.skip("Postgres not available")
                async with conn.cursor() as cur:
                    await cur.execute(f"CREATE ROLE {role} NOLOGIN")
                await conn.commit()

            with pytest.raises(RuntimeError, match="boom"):
                async with role_connection(db, user=role, db_role=role) as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT current_user")
                        assert (await cur.fetchone())[0] == role
                        await cur.execute(f"CREATE TABLE {table} (id int)")
                    raise RuntimeError("boom")

            async with db.get_db() as conn:
                assert conn is not None
                async with conn.cursor() as cur:
                    await cur.execute("SELECT current_user, session_user")
                    current, session = await cur.fetchone()
                    await cur.execute("SELECT to_regclass(%s)", (table,))
                    regclass = await cur.fetchone()
            assert current == session
            assert regclass[0] is None
        finally:
            try:
                async with db.get_db() as conn:
                    if conn is not None:
                        async with conn.cursor() as cur:
                            await cur.execute("RESET ROLE")
                            await cur.execute(f"DROP TABLE IF EXISTS {table}")
                            await cur.execute(f"DROP ROLE IF EXISTS {role}")
                        await conn.commit()
            finally:
                await db.close()

    asyncio.run(_run())
