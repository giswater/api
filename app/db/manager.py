"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from psycopg_pool import AsyncConnectionPool
import psycopg
from fastapi import HTTPException

from ..core.config import TenantSettings
from ..core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Per-tenant async Postgres connection pool."""

    def __init__(self, settings: TenantSettings, tenant_id: str):
        self.tenant_id = tenant_id
        self.settings = settings
        self.connection_pool = None

        self.host = settings.db_host
        self.port = settings.db_port
        self.dbname = settings.db_name
        self.user = settings.db_user
        self.password = settings.db_password
        self.default_schema = settings.db_schema

        if settings.database_url:
            self.database_url = settings.database_url
        else:
            self.database_url = (
                f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/"
                f"{self.dbname}?application_name=giswater-api"
            )

    def _log_prefix(self) -> str:
        return f"[{self.tenant_id}]"

    @staticmethod
    async def _reset_pooled_connection(conn):
        """Drop session-level SET ROLE before the connection goes back into the pool."""
        await conn.execute("RESET ROLE")

    async def init_conn_pool(self):
        """Initialize the async connection pool."""
        try:
            self.connection_pool = AsyncConnectionPool(
                self.database_url,
                min_size=self.settings.db_pool_min_size,
                max_size=self.settings.db_pool_max_size,
                timeout=self.settings.db_pool_timeout,
                max_waiting=self.settings.db_pool_max_waiting,
                max_idle=self.settings.db_pool_max_idle,
                reset=self._reset_pooled_connection,
                open=False,
            )
            await asyncio.wait_for(self.connection_pool.open(), timeout=self.settings.db_connect_timeout)
            logger.info("%s Initialized connection pool for %s", self._log_prefix(), self.dbname)
        except asyncio.TimeoutError:
            logger.warning("%s Timed out initializing connection pool for %s", self._log_prefix(), self.dbname)
            self.connection_pool = None
        except Exception:
            logger.exception("%s Failed to initialize connection pool for %s", self._log_prefix(), self.dbname)
            self.connection_pool = None

    @asynccontextmanager
    async def get_db(self):
        """
        Get a database connection from the pool.

        Yields:
            psycopg connection or None if connection fails

        Only connection *acquisition* is retried. Errors raised by the caller after
        the connection is yielded propagate unchanged (no pool recreate / re-yield).
        """
        max_tries = 3
        retry_delay_seconds = 2

        async with AsyncExitStack() as stack:
            for n_try in range(max_tries):
                if self.connection_pool is None:
                    await self.init_conn_pool()
                    if self.connection_pool is None:
                        if n_try < max_tries - 1:
                            await asyncio.sleep(retry_delay_seconds)
                        continue

                try:
                    conn = await stack.enter_async_context(self.connection_pool.connection())
                    break
                except (psycopg.Error, OSError, asyncio.TimeoutError) as e:
                    logger.warning(
                        "%s Failed to acquire database connection (attempt %s/%s): %s",
                        self._log_prefix(),
                        n_try + 1,
                        max_tries,
                        e,
                    )
                    # Pool may be stale after DB restarts/outages; force recreation.
                    try:
                        if self.connection_pool is not None:
                            await self.connection_pool.close()
                    except OSError:
                        logger.debug("%s Error closing stale pool", self._log_prefix(), exc_info=True)
                    self.connection_pool = None
                    if n_try < max_tries - 1:
                        await asyncio.sleep(retry_delay_seconds)
            else:
                yield None
                return

            yield conn

    async def validate_schema(self, schema: str) -> bool:
        """Validate if a schema exists in the database."""
        async with self.get_db() as conn:
            if conn is None:
                raise DatabaseUnavailableError()
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", (schema,)
                    )
                    return await cursor.fetchone() is not None
            except psycopg.Error as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

    async def is_db_available(self, timeout_seconds: float = 2.0) -> bool:
        """Fast one-shot availability check used by health endpoints."""
        if self.connection_pool is None:
            try:
                await asyncio.wait_for(self.init_conn_pool(), timeout=timeout_seconds)
            except (asyncio.TimeoutError, OSError, psycopg.Error):
                return False
            if self.connection_pool is None:
                return False

        try:
            async with self.connection_pool.connection(timeout=timeout_seconds) as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    await cursor.fetchone()
            return True
        except (psycopg.Error, OSError, asyncio.TimeoutError):
            return False

    async def healthcheck(self) -> bool:
        """Alias for `is_db_available` used by tenant-scoped /ready."""
        return await self.is_db_available()

    async def close(self):
        """Close the connection pool."""
        if self.connection_pool:
            await self.connection_pool.close()
            logger.info("%s Closed connection pool for %s", self._log_prefix(), self.dbname)
            self.connection_pool = None
