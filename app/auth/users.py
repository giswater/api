"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import bcrypt
from psycopg import sql
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from ..core.config import TenantSettings
from .constants import MIN_PASSWORD_LENGTH
from .schemas import ApiUser
from ..db.schema import GWAPI_ROLES_TABLE, GWAPI_SCHEMA, GWAPI_USER_ROLES_TABLE, GWAPI_USERS_TABLE

logger = logging.getLogger(__name__)


class GwapiUserError(ValueError):
    pass


@dataclass(frozen=True)
class GwapiUserRecord:
    id: int
    username: str
    db_role: str
    enabled: bool
    roles: frozenset[str]
    created_at: datetime
    updated_at: datetime


def _hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise GwapiUserError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _record_to_api_user(record: GwapiUserRecord) -> ApiUser:
    return ApiUser(
        sub=str(record.id),
        preferred_username=record.username,
        auth_method="basic",
        roles=record.roles,
        db_role=record.db_role,
    )


async def validate_db_role(db_manager, role_name: str) -> bool:
    async with db_manager.get_db() as conn:
        if conn is None:
            return False
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
            row = await cursor.fetchone()
            return row is not None


async def list_roles(db_manager) -> list[dict[str, str]]:
    async with db_manager.get_db() as conn:
        if conn is None:
            return []
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL("SELECT name, description FROM {}.{} ORDER BY name").format(
                    sql.Identifier(GWAPI_SCHEMA),
                    sql.Identifier(GWAPI_ROLES_TABLE),
                )
            )
            rows = await cursor.fetchall()
            return [{"name": row["name"], "description": row.get("description")} for row in rows]


async def _load_roles_for_user(conn, user_id: int) -> frozenset[str]:
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            sql.SQL("SELECT role_name FROM {}.{} WHERE user_id = %s").format(
                sql.Identifier(GWAPI_SCHEMA),
                sql.Identifier(GWAPI_USER_ROLES_TABLE),
            ),
            (user_id,),
        )
        rows = await cursor.fetchall()
        return frozenset(row["role_name"] for row in rows)


async def _row_to_record(conn, row: dict[str, Any]) -> GwapiUserRecord:
    roles = await _load_roles_for_user(conn, row["id"])
    return GwapiUserRecord(
        id=row["id"],
        username=row["username"],
        db_role=row["db_role"],
        enabled=row["enabled"],
        roles=roles,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_users(db_manager) -> list[GwapiUserRecord]:
    async with db_manager.get_db() as conn:
        if conn is None:
            return []
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL(
                    "SELECT id, username, db_role, enabled, created_at, updated_at FROM {}.{} ORDER BY username"
                ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(GWAPI_USERS_TABLE))
            )
            rows = await cursor.fetchall()
            return [await _row_to_record(conn, row) for row in rows]


async def get_user(db_manager, username: str) -> GwapiUserRecord | None:
    async with db_manager.get_db() as conn:
        if conn is None:
            return None
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL(
                    "SELECT id, username, db_role, enabled, created_at, updated_at FROM {}.{} WHERE username = %s"
                ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(GWAPI_USERS_TABLE)),
                (username,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return await _row_to_record(conn, row)


async def verify_credentials(db_manager, username: str, password: str) -> ApiUser | None:
    async with db_manager.get_db() as conn:
        if conn is None:
            return None
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL(
                    "SELECT id, username, password_hash, db_role, enabled, created_at, updated_at FROM {}.{} "
                    "WHERE username = %s"
                ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(GWAPI_USERS_TABLE)),
                (username,),
            )
            row = await cursor.fetchone()
            if row is None or not row["enabled"]:
                return None
            if not _check_password(password, row["password_hash"]):
                return None
            record = await _row_to_record(conn, row)
            return _record_to_api_user(record)


async def create_user(
    db_manager,
    *,
    username: str,
    password: str,
    db_role: str | None,
    roles: list[str],
    enabled: bool = True,
) -> GwapiUserRecord:
    effective_db_role = db_role or username
    if not await validate_db_role(db_manager, effective_db_role):
        raise GwapiUserError(f"PostgreSQL role '{effective_db_role}' does not exist")
    password_hash = _hash_password(password)
    async with db_manager.get_db() as conn:
        if conn is None:
            raise GwapiUserError("Database unavailable")
        try:
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.{} (username, password_hash, db_role, enabled)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, username, db_role, enabled, created_at, updated_at
                        """
                    ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(GWAPI_USERS_TABLE)),
                    (username, password_hash, effective_db_role, enabled),
                )
                row = await cursor.fetchone()
                user_id = row["id"]
                for role_name in roles:
                    await cursor.execute(
                        sql.SQL("INSERT INTO {}.{} (user_id, role_name) VALUES (%s, %s) ON CONFLICT DO NOTHING").format(
                            sql.Identifier(GWAPI_SCHEMA), sql.Identifier(GWAPI_USER_ROLES_TABLE)
                        ),
                        (user_id, role_name),
                    )
            await conn.commit()
        except UniqueViolation as exc:
            await conn.rollback()
            raise GwapiUserError(f"User '{username}' already exists") from exc
        except Exception:
            await conn.rollback()
            raise
    record = await get_user(db_manager, username)
    if record is None:
        raise GwapiUserError("Failed to create user")
    return record


async def update_user(
    db_manager,
    username: str,
    *,
    password: str | None = None,
    db_role: str | None = None,
    roles: list[str] | None = None,
    enabled: bool | None = None,
) -> GwapiUserRecord:
    existing = await get_user(db_manager, username)
    if existing is None:
        raise GwapiUserError(f"User '{username}' not found")

    new_db_role = db_role if db_role is not None else existing.db_role
    if not await validate_db_role(db_manager, new_db_role):
        raise GwapiUserError(f"PostgreSQL role '{new_db_role}' does not exist")

    async with db_manager.get_db() as conn:
        if conn is None:
            raise GwapiUserError("Database unavailable")
        try:
            async with conn.cursor() as cursor:
                sets = ["updated_at = now()", "db_role = %s"]
                params: list[Any] = [new_db_role]
                if enabled is not None:
                    sets.append("enabled = %s")
                    params.append(enabled)
                if password is not None:
                    sets.append("password_hash = %s")
                    params.append(_hash_password(password))
                params.append(username)
                await cursor.execute(
                    sql.SQL("UPDATE {}.{} SET {} WHERE username = %s").format(
                        sql.Identifier(GWAPI_SCHEMA),
                        sql.Identifier(GWAPI_USERS_TABLE),
                        sql.SQL(", ").join(sql.SQL(part) for part in sets),
                    ),
                    params,
                )
                if roles is not None:
                    await cursor.execute(
                        sql.SQL("DELETE FROM {}.{} WHERE user_id = %s").format(
                            sql.Identifier(GWAPI_SCHEMA),
                            sql.Identifier(GWAPI_USER_ROLES_TABLE),
                        ),
                        (existing.id,),
                    )
                    for role_name in roles:
                        await cursor.execute(
                            sql.SQL(
                                "INSERT INTO {}.{} (user_id, role_name) VALUES (%s, %s) ON CONFLICT DO NOTHING"
                            ).format(sql.Identifier(GWAPI_SCHEMA), sql.Identifier(GWAPI_USER_ROLES_TABLE)),
                            (existing.id, role_name),
                        )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    record = await get_user(db_manager, username)
    if record is None:
        raise GwapiUserError("Failed to update user")
    return record


async def delete_user(db_manager, username: str) -> None:
    async with db_manager.get_db() as conn:
        if conn is None:
            raise GwapiUserError("Database unavailable")
        async with conn.cursor() as cursor:
            await cursor.execute(
                sql.SQL("DELETE FROM {}.{} WHERE username = %s").format(
                    sql.Identifier(GWAPI_SCHEMA),
                    sql.Identifier(GWAPI_USERS_TABLE),
                ),
                (username,),
            )
            if cursor.rowcount == 0:
                raise GwapiUserError(f"User '{username}' not found")
        await conn.commit()


async def maybe_bootstrap_user(db_manager, settings: TenantSettings) -> None:
    username = settings.auth_basic_bootstrap_user
    password = settings.auth_basic_bootstrap_password
    if not username or not password:
        return
    users = await list_users(db_manager)
    if users:
        return
    try:
        await create_user(
            db_manager,
            username=username,
            password=password,
            db_role=username,
            roles=["basic"],
            enabled=True,
        )
        logger.info("Bootstrapped basic auth user '%s'", username)
    except GwapiUserError as exc:
        logger.warning("Basic auth bootstrap failed for '%s': %s", username, exc)
