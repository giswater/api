"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.

Alembic-driven schema management for the API-owned `gwapi` schema.

Migrations are plain SQL (no ORM models). Alembic is synchronous, so the async
entry points hop to a worker thread. The application uses psycopg for all
runtime queries; SQLAlchemy is only the engine Alembic needs to run.
"""

import asyncio
import logging
import threading
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

from ..core.config import TenantSettings, global_settings
from .partitions import ensure_current_month_partitions
from .schema import invalidate_log_schema_cache, resolve_log_targets

logger = logging.getLogger(__name__)

VERSION_TABLE_SCHEMA = "gwapi"
# Alembic's EnvironmentContext proxy lives in module globals; not safe concurrently.
_alembic_upgrade_lock = threading.Lock()


def _alembic_ini() -> Path:
    """Return the project ``alembic.ini`` (Docker WORKDIR or repo root)."""
    for candidate in (Path.cwd() / "alembic.ini", Path(__file__).resolve().parents[2] / "alembic.ini"):
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"alembic.ini not found (cwd={Path.cwd()})")


def _to_sqlalchemy_url(database_url: str) -> str:
    """Adapt a psycopg connection URL to the SQLAlchemy psycopg3 dialect."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if database_url.startswith(prefix):
            return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://") :]
    return database_url


def build_alembic_config(database_url: str) -> Config:
    cfg = Config(str(_alembic_ini()))
    # ConfigParser treats `%` as interpolation syntax; escape for set/get round-trip.
    url = _to_sqlalchemy_url(database_url).replace("%", "%%")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _sync_upgrade(database_url: str) -> None:
    with _alembic_upgrade_lock:
        command.upgrade(build_alembic_config(database_url), "head")


def _sync_current_revision(database_url: str) -> str | None:
    engine = create_engine(_to_sqlalchemy_url(database_url), poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"version_table_schema": VERSION_TABLE_SCHEMA})
            return ctx.get_current_revision()
    finally:
        engine.dispose()


def head_revision() -> str | None:
    script = ScriptDirectory.from_config(build_alembic_config("postgresql://"))
    return script.get_current_head()


def history() -> list[dict[str, str | None]]:
    script = ScriptDirectory.from_config(build_alembic_config("postgresql://"))
    return [
        {
            "revision": rev.revision,
            "down_revision": rev.down_revision,
            "doc": rev.doc,
        }
        for rev in script.walk_revisions()
    ]


async def run_alembic_upgrade(db_manager) -> None:
    """Run `alembic upgrade head` for a tenant and refresh the schema cache."""
    before = await get_current_revision(db_manager.database_url)
    await asyncio.to_thread(_sync_upgrade, db_manager.database_url)
    invalidate_log_schema_cache(db_manager.tenant_id)
    after = await get_current_revision(db_manager.database_url)
    if before != after:
        logger.info("[%s] migrated gwapi schema %s -> %s", db_manager.tenant_id, before, after)
    else:
        logger.debug("[%s] gwapi schema already at %s", db_manager.tenant_id, after)


async def get_current_revision(database_url: str) -> str | None:
    return await asyncio.to_thread(_sync_current_revision, database_url)


async def ensure_tenant_database(db_manager, settings: TenantSettings) -> None:
    """Bring a tenant DB to the current schema and prepare runtime objects.

    Replaces the old runtime DDL bootstrap. Runs Alembic (unless disabled),
    ensures the current-month log partitions, and bootstraps the first basic-auth
    user. Always runs when the tenant has a DB pool so ``gwapi.jobs`` (and other
    API-owned tables) exist regardless of auth mode or audit logging.
    Migration failures are non-fatal: the legacy schema resolver keeps the
    API serving against `log.*` until the issue is resolved.
    """
    if global_settings.db_auto_migrate:
        try:
            await run_alembic_upgrade(db_manager)
        except Exception as exc:
            logger.warning(
                "[%s] alembic upgrade failed; keeping legacy schema: %r",
                db_manager.tenant_id,
                exc,
                exc_info=True,
            )
    else:
        logger.info(
            "[%s] DB_AUTO_MIGRATE=false; audit logs stay in their current schema until "
            "'giswater-api db upgrade' is run.",
            db_manager.tenant_id,
        )
        await _warn_if_behind(db_manager)

    if global_settings.log_db_enabled:
        targets = await resolve_log_targets(db_manager)
        await ensure_current_month_partitions(db_manager, targets)

    if settings.auth_mode == "basic":
        from ..auth.users import maybe_bootstrap_user

        await maybe_bootstrap_user(db_manager, settings)


async def _warn_if_behind(db_manager) -> None:
    try:
        current = await get_current_revision(db_manager.database_url)
    except Exception:
        return
    if current != head_revision():
        logger.warning(
            "[%s] gwapi schema behind head (at %s); run 'giswater-api db upgrade --tenant %s'.",
            db_manager.tenant_id,
            current,
            db_manager.tenant_id,
        )
