"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal

import psycopg
from fastapi import HTTPException
from psycopg import sql
from psycopg.rows import dict_row

from ..core.config import global_settings
from ..core.exceptions import DatabaseUnavailableError
from .context import REQUEST_ID_CTX, _resolve_db_identity
from .log_store import insert_api_db_log

logger = logging.getLogger(__name__)


def create_response(db_result=None, form_xml=None, status=None, message=None):
    """Create and return a json response to send to the client"""

    response = {"status": "Failed", "message": {}, "version": {}, "body": {}}

    if status is not None:
        if status in (True, "Accepted"):
            response["status"] = "Accepted"
            if message:
                response["message"] = {"level": 3, "text": message}
        else:
            response["status"] = "Failed"
            if message:
                response["message"] = {"level": 2, "text": message}

        return response

    if not db_result and not form_xml:
        response["status"] = "Failed"
        response["message"] = {"level": 2, "text": "DB returned null"}
        return response
    elif form_xml:
        response["status"] = "Accepted"

    if db_result:
        response = db_result
    response["form_xml"] = form_xml

    return response


async def _execute_procedure_on_conn(  # noqa: C901
    conn,
    *,
    log,
    db_manager,
    function_name,
    query,
    sql_params: tuple[Any, ...],
    schema_name: str,
    set_role: bool,
    user: str | None,
    db_role: str | None,
    api_version,
    start_time: float,
) -> dict:
    sql_preview = (
        sql.SQL("SELECT {}.{}({})")
        .format(
            sql.Identifier(schema_name),
            sql.Identifier(function_name),
            sql.SQL(", ").join(sql.Literal(p) for p in sql_params),
        )
        .as_string(conn)
    )
    result: dict | Any = {}
    log.debug("execute_procedure SQL: %s", sql_preview)
    identity = _resolve_db_identity(user, db_role)
    db_error = None
    response_msg = ""
    try:
        async with conn.cursor() as cursor:
            if set_role and identity:
                await cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(identity)))
            if sql_params:
                await cursor.execute(query, sql_params)
            else:
                await cursor.execute(query)
            row = await cursor.fetchone()
            result = row[0] if row else None
            await conn.commit()
        response_msg = json.dumps(result)
    except psycopg.Error as e:
        await conn.rollback()
        db_error = str(e)
        db_version = None
        if result and isinstance(result, dict) and "version" in result:
            db_version = result["version"]
        result = {
            "status": "Failed",
            "message": {"level": 3, "text": str(e)},
            "version": {"api": api_version},
            "body": {},
        }
        if db_version:
            result["version"]["db"] = db_version
        response_msg = str(e)
    except Exception as e:
        logger.exception("Non-DB error in execute_procedure")
        await conn.rollback()
        db_error = str(e)
        result = {
            "status": "Failed",
            "message": {"level": 3, "text": str(e)},
            "version": {"api": api_version},
            "body": {},
        }
        response_msg = str(e)

    if not result or (isinstance(result, dict) and result.get("status") == "Failed"):
        log.warning(f"{sql_preview}|||{response_msg}")
    else:
        log.info(f"{sql_preview}|||{response_msg}")

    if result:
        log.debug("execute_procedure response: %s", json.dumps(result, default=str))

    if isinstance(result, dict) and "version" in result:
        result["version"] = {"db": result["version"], "api": api_version}

    if global_settings.log_db_enabled:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        request_id = REQUEST_ID_CTX.get()
        cap = global_settings.log_db_response_max_bytes
        stored_response = response_msg
        if cap > 0 and stored_response is not None and len(stored_response) > cap:
            stored_response = stored_response[:cap] + "...[truncated]"
        db_log_record = {
            "ts": datetime.now(timezone.utc),
            "request_id": request_id,
            "schema_name": schema_name,
            "function_name": function_name,
            "sql_text": sql_preview,
            "response_json": stored_response,
            "duration_ms": duration_ms,
            "status": result.get("status") if isinstance(result, dict) else None,
            "error": db_error,
        }
        asyncio.create_task(insert_api_db_log(db_manager, db_log_record))

    return result


async def execute_procedure(  # noqa: C901
    log,
    db_manager,
    function_name,
    parameters=None,
    set_role=True,
    needs_write=False,
    schema=None,
    user: str | None = "anonymous",
    db_role: str | None = None,
    api_version=None,
    conn=None,
):
    """
    Manage execution of database function.

    Args:
        log: Logger instance
        db_manager: DatabaseManager instance from request.state.tenant.db_manager
        function_name: Name of function to call
        parameters: Parameters for function (json) or (query parameters)
        set_role: Set role in database with the current user
        schema: Database schema to use (defaults to db_manager's default_schema)
        user: Current user (from JWT or config)
        api_version: API version string
        conn: Optional database connection to use

    Returns:
        Response of the function executed (json)
    """

    # Manage schema_name and parameters
    schema_name = schema or db_manager.default_schema
    if schema_name is None:
        log.warning(" Schema is None")
        return create_response(status=False, message="Schema not found")

    # Validate schema exists
    if not await db_manager.validate_schema(schema_name):
        log.warning(f"Schema '{schema_name}' not found")
        return create_response(status=False, message=f"Schema '{schema_name}' not found")

    sql_params: tuple[Any, ...] = ()
    if parameters is not None:
        sql_params = tuple(parameters) if isinstance(parameters, (list, tuple)) else (parameters,)

    query = sql.SQL("SELECT {}.{}({})").format(
        sql.Identifier(schema_name),
        sql.Identifier(function_name),
        sql.SQL(", ").join(sql.Placeholder() for _ in sql_params),
    )

    start_time = time.monotonic()
    kwargs = dict(
        log=log,
        db_manager=db_manager,
        function_name=function_name,
        query=query,
        sql_params=sql_params,
        schema_name=schema_name,
        set_role=set_role,
        user=user,
        db_role=db_role,
        api_version=api_version,
        start_time=start_time,
    )

    if conn is not None:
        return await _execute_procedure_on_conn(conn, **kwargs)

    async with db_manager.get_db() as acquired:
        if acquired is None:
            log.error("No connection to database")
            raise DatabaseUnavailableError()
        return await _execute_procedure_on_conn(acquired, **kwargs)


async def execute_sql_select(
    log,
    db_manager,
    table_name: str,
    columns: list[str] | None = None,
    where_clause: str | None = None,
    parameters: tuple | None = None,
    set_role: bool = True,
    schema: str | None = None,
    user: str | None = "anonymous",
    db_role: str | None = None,
):
    """
    Execute a SELECT query on a table and return rows as dicts.
    """
    schema_name = schema or db_manager.default_schema
    if schema_name is None:
        log.warning("Schema is None")
        raise HTTPException(status_code=500, detail="Schema not found")

    if not await db_manager.validate_schema(schema_name):
        log.warning(f"Schema '{schema_name}' not found")
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")

    if columns:
        column_sql = sql.SQL(", ").join(sql.Identifier(col) for col in columns)
    else:
        column_sql = sql.SQL("*")

    query = sql.SQL("SELECT {} FROM {}.{}").format(column_sql, sql.Identifier(schema_name), sql.Identifier(table_name))
    if where_clause:
        query = sql.SQL("{} WHERE {}").format(query, sql.SQL(where_clause))

    async with db_manager.get_db() as conn:
        if conn is None:
            log.error("No connection to database")
            raise DatabaseUnavailableError()
        try:
            async with conn.cursor(row_factory=dict_row) as cursor:
                identity = _resolve_db_identity(user, db_role)
                if set_role and identity:
                    await cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(identity)))
                if parameters is None:
                    await cursor.execute(query)
                else:
                    await cursor.execute(query, parameters)
                rows = await cursor.fetchall()
            await conn.commit()
        except psycopg.Error as e:
            await conn.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    return rows


async def execute_sql(
    log,
    db_manager,
    sql_query: str,
    parameters: tuple | None = None,
    set_role: bool = True,
    schema: str | None = None,
    user: str | None = "anonymous",
    db_role: str | None = None,
):
    """
    Execute a raw SQL query and return rows as dicts.
    Use {schema} in raw_sql for schema-qualified identifiers.
    """
    schema_name = schema or db_manager.default_schema
    if schema_name is None:
        log.warning("Schema is None")
        raise HTTPException(status_code=500, detail="Schema not found")

    if not await db_manager.validate_schema(schema_name):
        log.warning(f"Schema '{schema_name}' not found")
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")

    try:
        query = sql.SQL(sql_query).format(schema=sql.Identifier(schema_name))  # type: ignore
    except (TypeError, ValueError) as e:
        log.error(f"Failed to create SQL query: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid SQL query or parameters: {e}") from e

    async with db_manager.get_db() as conn:
        if conn is None:
            log.error("No connection to database")
            raise DatabaseUnavailableError()
        try:
            async with conn.cursor(row_factory=dict_row) as cursor:
                identity = _resolve_db_identity(user, db_role)
                if set_role and identity:
                    await cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(identity)))
                if parameters is None:
                    await cursor.execute(query)
                else:
                    await cursor.execute(query, parameters)
                rows = await cursor.fetchall()
            await conn.commit()
        except psycopg.Error as e:
            await conn.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    return rows


async def execute_sql_insert(
    log,
    db_manager,
    table_name: str,
    data: dict,
    set_role: bool = True,
    schema: str | None = None,
    user: str | None = "anonymous",
    db_role: str | None = None,
):
    """
    Execute an INSERT on a table and return inserted rows as dicts.
    """
    schema_name = schema or db_manager.default_schema
    if schema_name is None:
        log.warning("Schema is None")
        raise HTTPException(status_code=500, detail="Schema not found")

    if not await db_manager.validate_schema(schema_name):
        log.warning(f"Schema '{schema_name}' not found")
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")

    if not data:
        raise HTTPException(status_code=400, detail="No data provided for insert")

    columns = [sql.Identifier(col) for col in data.keys()]
    values = list(data.values())
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)

    query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
        sql.SQL(", ").join(columns),
        placeholders,
    )

    async with db_manager.get_db() as conn:
        if conn is None:
            log.error("No connection to database")
            raise DatabaseUnavailableError()
        try:
            async with conn.cursor(row_factory=dict_row) as cursor:
                identity = _resolve_db_identity(user, db_role)
                if set_role and identity:
                    await cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(identity)))
                await cursor.execute(query, tuple(values))
                rows = await cursor.fetchall()
            await conn.commit()
        except psycopg.Error as e:
            await conn.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    return rows


async def execute_sql_update(
    log,
    db_manager,
    table_name: str,
    data: dict,
    where_data: dict,
    set_role: bool = True,
    schema: str | None = None,
    user: str | None = "anonymous",
    db_role: str | None = None,
):
    """
    Execute an UPDATE on a table and return updated rows as dicts.
    """
    schema_name = schema or db_manager.default_schema
    if schema_name is None:
        log.warning("Schema is None")
        raise HTTPException(status_code=500, detail="Schema not found")

    if not await db_manager.validate_schema(schema_name):
        log.warning(f"Schema '{schema_name}' not found")
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")

    if not data:
        raise HTTPException(status_code=400, detail="No data provided for update")
    if not where_data:
        raise HTTPException(status_code=400, detail="No where_data provided for update")

    set_clauses = [sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder()) for col in data.keys()]
    where_clauses = [sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder()) for col in where_data.keys()]

    values = list(data.values()) + list(where_data.values())

    query = sql.SQL("UPDATE {}.{} SET {} WHERE {} RETURNING *").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
        sql.SQL(", ").join(set_clauses),
        sql.SQL(" AND ").join(where_clauses),
    )

    async with db_manager.get_db() as conn:
        if conn is None:
            log.error("No connection to database")
            raise DatabaseUnavailableError()
        try:
            async with conn.cursor(row_factory=dict_row) as cursor:
                identity = _resolve_db_identity(user, db_role)
                if set_role and identity:
                    await cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(identity)))
                await cursor.execute(query, tuple(values))
                rows = await cursor.fetchall()
            await conn.commit()
        except psycopg.Error as e:
            await conn.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    return rows


async def execute_sql_upsert(
    log,
    db_manager,
    table_name: str,
    data: dict,
    where_data: dict,
    set_role: bool = True,
    schema: str | None = None,
    user: str | None = "anonymous",
    db_role: str | None = None,
) -> tuple[list[dict], Literal["inserted", "updated"]]:
    """
    Try UPDATE first; if no row matched, INSERT with where_data + data.
    When data is empty (only key fields provided), checks existence via SELECT instead.
    Returns (rows, "inserted" | "updated").
    """
    if data:
        rows = await execute_sql_update(
            log=log,
            db_manager=db_manager,
            table_name=table_name,
            data=data,
            where_data=where_data,
            set_role=set_role,
            schema=schema,
            user=user,
            db_role=db_role,
        )
        if rows:
            return rows, "updated"
    else:
        where_clause = " AND ".join(f"{col} = %s" for col in where_data)
        rows = await execute_sql_select(
            log=log,
            db_manager=db_manager,
            table_name=table_name,
            where_clause=where_clause,
            parameters=tuple(where_data.values()),
            set_role=set_role,
            schema=schema,
            user=user,
            db_role=db_role,
        )
        if rows:
            return rows, "updated"

    insert_data = {**where_data, **data}
    rows = await execute_sql_insert(
        log=log,
        db_manager=db_manager,
        table_name=table_name,
        data=insert_data,
        set_role=set_role,
        schema=schema,
        user=user,
        db_role=db_role,
    )
    return rows, "inserted"


async def execute_sql_delete(
    log,
    db_manager,
    table_name: str,
    where_data: dict,
    set_role: bool = True,
    schema: str | None = None,
    user: str | None = "anonymous",
    db_role: str | None = None,
) -> bool:
    """
    Execute a DELETE on a table and return True if successful, False otherwise.
    """
    status = False
    schema_name = schema or db_manager.default_schema
    if schema_name is None:
        log.warning("Schema is None")
        raise HTTPException(status_code=500, detail="Schema not found")

    if not await db_manager.validate_schema(schema_name):
        log.warning(f"Schema '{schema_name}' not found")
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")

    if not where_data:
        raise HTTPException(status_code=400, detail="No where_data provided for delete")

    where_clauses = [sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder()) for col in where_data.keys()]
    values = list(where_data.values())

    query = sql.SQL("DELETE FROM {}.{} WHERE {}").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
        sql.SQL(" AND ").join(where_clauses),
    )

    async with db_manager.get_db() as conn:
        if conn is None:
            log.error("No connection to database")
            raise DatabaseUnavailableError()
        try:
            async with conn.cursor(row_factory=dict_row) as cursor:
                rows = await execute_sql_select(
                    log=log,
                    db_manager=db_manager,
                    table_name=table_name,
                    where_clause=sql.SQL(" AND ").join(where_clauses).as_string(conn),
                    parameters=tuple(values),
                    schema=schema_name,
                    user=user,
                    db_role=db_role,
                )
                if not rows:
                    return False

                identity = _resolve_db_identity(user, db_role)
                if set_role and identity:
                    await cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(identity)))
                await cursor.execute(query, tuple(values))
                status = True
            await conn.commit()
        except psycopg.Error as e:
            await conn.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    return status
