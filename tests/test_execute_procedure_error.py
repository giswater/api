"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import psycopg

from app.db.execution import execute_procedure

_ROLE_ERROR = 'permission denied to set role "qwc2_bgeo"'


def _conn_with_cursor(cursor):
    conn = MagicMock()
    # as_string() quotes identifiers itself when connection is unset.
    conn.connection = None
    conn.rollback = AsyncMock()
    conn.commit = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = cursor
    conn.cursor.return_value = cm
    return conn


def _db_manager():
    mgr = MagicMock()
    mgr.default_schema = "ws"
    mgr.validate_schema = AsyncMock(return_value=True)
    return mgr


def _call(conn):
    return execute_procedure(
        logging.getLogger("test"),
        _db_manager(),
        "gw_fct_getinfofromid",
        schema="ws",
        user="client",
        db_role="qwc2_bgeo",
        api_version="1.10.0",
        conn=conn,
    )


def test_set_role_error_version_is_api_only():
    async def _run():
        cursor = AsyncMock()
        cursor.execute.side_effect = psycopg.Error(_ROLE_ERROR)
        result = await _call(_conn_with_cursor(cursor))
        assert result["status"] == "Failed"
        assert result["message"] == {"level": 3, "text": _ROLE_ERROR}
        assert result["version"] == {"api": "1.10.0"}
        assert result["body"] == {}

    asyncio.run(_run())


def test_success_payload_stamps_db_version():
    async def _run():
        cursor = AsyncMock()
        cursor.fetchone.return_value = ({"status": "Accepted", "version": "4.8.1", "body": {}},)
        result = await _call(_conn_with_cursor(cursor))
        assert result["status"] == "Accepted"
        assert result["version"] == {"db": "4.8.1", "api": "1.10.0"}
        assert result["body"] == {}

    asyncio.run(_run())
