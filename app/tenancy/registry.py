"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi_keycloak import FastAPIKeycloak

from ..core.config import TenantSettings, global_settings, load_tenant_settings
from ..db.manager import DatabaseManager
from ..auth.keycloak import build_idp

TENANT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_IDS = {"www", "api", "admin", "static", "traefik", "localhost"}

logger = logging.getLogger(__name__)
_IGNORED_TENANT_FILENAMES = frozenset({"example.env", "sample.env", "template.env"})


def validate_tenant_id(tid: str) -> None:
    if not isinstance(tid, str) or not TENANT_ID_RE.match(tid):
        raise ValueError(f"Invalid tenant id '{tid}'")
    if tid in RESERVED_IDS:
        raise ValueError(f"Reserved tenant id '{tid}'")


@dataclass
class Tenant:
    id: str
    settings: TenantSettings
    db_manager: DatabaseManager
    idp: Optional[FastAPIKeycloak]
    api_logger: logging.Logger
    api_log_date: str
    log_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def ensure_logger_fresh(self) -> None:
        """Refresh the per-tenant file logger when the day rolls over."""
        today = date.today().strftime("%Y%m%d")
        if self.api_log_date == today:
            return
        async with self.log_lock:
            if self.api_log_date == today:
                return
            from ..utils.log_setup import create_log

            self.api_logger = create_log("api", _tenant_log_dir(self.id))
            self.api_log_date = today


def _tenant_log_dir(tid: str) -> str:
    return os.path.join(global_settings.log_dir, tid)


def _build_tenant_logger(tid: str) -> tuple[logging.Logger, str]:
    from ..utils.log_setup import create_log

    today = date.today().strftime("%Y%m%d")
    return create_log("api", _tenant_log_dir(tid)), today


def _atomic_write_env(path: Path, contents: str) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1000)}")
    tmp.write_text(contents, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    s = str(value)
    if any(c in s for c in (" ", "\t", "#", '"', "'")):
        s = '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def serialize_tenant_settings(settings: TenantSettings) -> str:
    """Produce a `.env` body for a TenantSettings (atomic-write friendly)."""
    fields = (
        ("API_BASIC", settings.api_basic),
        ("API_PROFILE", settings.api_profile),
        ("API_FLOW", settings.api_flow),
        ("API_MINCUT", settings.api_mincut),
        ("API_WATER_BALANCE", settings.api_water_balance),
        ("API_MAPZONES", settings.api_mapzones),
        ("API_ROUTING", settings.api_routing),
        ("API_CRM", settings.api_crm),
        ("API_EPA", settings.api_epa),
        ("API_FEATURES", settings.api_features),
        ("DB_HOST", settings.db_host),
        ("DB_PORT", settings.db_port),
        ("DB_NAME", settings.db_name),
        ("DB_USER", settings.db_user),
        ("DB_PASSWORD", settings.db_password),
        ("DB_SCHEMA", settings.db_schema),
        ("DATABASE_URL", settings.database_url),
        ("DB_POOL_MIN_SIZE", settings.db_pool_min_size),
        ("DB_POOL_MAX_SIZE", settings.db_pool_max_size),
        ("DB_POOL_TIMEOUT", settings.db_pool_timeout),
        ("DB_POOL_MAX_WAITING", settings.db_pool_max_waiting),
        ("DB_POOL_MAX_IDLE", settings.db_pool_max_idle),
        ("DB_CONNECT_TIMEOUT", settings.db_connect_timeout),
        ("AUTH_MODE", settings.auth_mode),
        ("AUTH_BASIC_BOOTSTRAP_USER", settings.auth_basic_bootstrap_user),
        ("AUTH_BASIC_BOOTSTRAP_PASSWORD", settings.auth_basic_bootstrap_password),
        # DEPRECATED #22: stop writing KEYCLOAK_ENABLED on admin serialize; remove in 2.0.0
        ("KEYCLOAK_ENABLED", settings.keycloak_enabled),
        ("KEYCLOAK_URL", settings.keycloak_url),
        ("KEYCLOAK_REALM", settings.keycloak_realm),
        ("KEYCLOAK_CLIENT_ID", settings.keycloak_client_id),
        ("KEYCLOAK_CLIENT_SECRET", settings.keycloak_client_secret),
        ("KEYCLOAK_ADMIN_CLIENT_ID", settings.keycloak_admin_client_id),
        ("KEYCLOAK_ADMIN_CLIENT_SECRET", settings.keycloak_admin_client_secret),
        ("KEYCLOAK_CALLBACK_URI", settings.keycloak_callback_uri),
    )
    lines = [f"{key}={_format_value(value)}" for key, value in fields if value is not None]
    return "\n".join(lines) + "\n"


class TenantRegistry:
    """Owns per-tenant resources: pool, idp, file logger.

    Mutating methods take `_lock` for the entire op; reads are lock-free."""

    def __init__(self, tenants_dir: Path):
        self.dir = tenants_dir
        self._tenants: dict[str, Tenant] = {}
        self._lock = asyncio.Lock()

    def get(self, tid: str) -> Tenant | None:
        return self._tenants.get(tid)

    def is_empty(self) -> bool:
        return not self._tenants

    def ids(self) -> list[str]:
        return sorted(self._tenants.keys())

    def all(self) -> list[Tenant]:
        return [self._tenants[tid] for tid in self.ids()]

    @staticmethod
    def _is_template_env_file(path: Path) -> bool:
        return path.name.lower() in _IGNORED_TENANT_FILENAMES

    def _tenant_files(self) -> list[Path]:
        return sorted(p for p in self.dir.glob("*.env") if p.is_file() and not self._is_template_env_file(p))

    async def load_all(self) -> dict:
        """Eager-load every `.env` in `tenants_dir` in parallel."""
        if not self.dir.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
        files = self._tenant_files()

        async def build(path: Path):
            tid = path.stem
            try:
                validate_tenant_id(tid)
                tenant = await self._build_tenant(tid, load_tenant_settings(path))
                return (tid, tenant, None)
            except Exception as exc:
                return (tid, None, exc)

        results = await asyncio.gather(*(build(p) for p in files))
        loaded: list[str] = []
        errors: list[dict] = []
        for tid, tenant, err in results:
            if tenant is not None:
                self._tenants[tid] = tenant
                loaded.append(tid)
            else:
                errors.append({"id": tid, "error": str(err)})
                logger.error("Failed to load tenant '%s': %s", tid, err)
        return {"loaded": loaded, "errors": errors}

    async def _build_tenant(self, tid: str, settings: TenantSettings) -> Tenant:
        settings.validate()
        db = DatabaseManager(settings, tid)
        try:
            await asyncio.wait_for(db.init_conn_pool(), timeout=max(settings.db_connect_timeout, 5.0))
        except Exception as exc:
            logger.warning("[%s] pool init failed; tenant kept, will retry on demand: %s", tid, exc)
        if db.connection_pool is not None:
            try:
                from ..db.migrate import ensure_tenant_database

                await asyncio.wait_for(
                    ensure_tenant_database(db, settings),
                    timeout=max(settings.db_connect_timeout, global_settings.db_migrate_timeout),
                )
            except Exception as exc:
                logger.warning("[%s] tenant database init failed: %s", tid, exc)
        idp = build_idp(settings)
        api_logger, api_log_date = _build_tenant_logger(tid)
        return Tenant(
            id=tid,
            settings=settings,
            db_manager=db,
            idp=idp,
            api_logger=api_logger,
            api_log_date=api_log_date,
        )

    async def reload_one(self, tid: str) -> Tenant:
        async with self._lock:
            validate_tenant_id(tid)
            path = self.dir / f"{tid}.env"
            if not path.exists():
                raise FileNotFoundError(f"Tenant file not found: {path}")
            new = await self._build_tenant(tid, load_tenant_settings(path))
            old = self._tenants.get(tid)
            self._tenants[tid] = new
            if old is not None:
                await self._safe_close(old)
            return new

    async def reload(self) -> dict:
        async with self._lock:
            if not self.dir.exists():
                self.dir.mkdir(parents=True, exist_ok=True)
            files = {p.stem: p for p in self._tenant_files()}
            existing = set(self._tenants.keys())
            wanted = set(files.keys())

            added: list[str] = []
            reloaded: list[str] = []
            removed: list[str] = []
            errors: list[dict] = []

            for tid in sorted(wanted - existing):
                try:
                    validate_tenant_id(tid)
                    tenant = await self._build_tenant(tid, load_tenant_settings(files[tid]))
                    self._tenants[tid] = tenant
                    added.append(tid)
                except Exception as exc:
                    errors.append({"id": tid, "error": str(exc)})

            for tid in sorted(wanted & existing):
                try:
                    validate_tenant_id(tid)
                    new = await self._build_tenant(tid, load_tenant_settings(files[tid]))
                    old = self._tenants[tid]
                    self._tenants[tid] = new
                    await self._safe_close(old)
                    reloaded.append(tid)
                except Exception as exc:
                    errors.append({"id": tid, "error": str(exc)})

            for tid in sorted(existing - wanted):
                old = self._tenants.pop(tid, None)
                if old is not None:
                    await self._safe_close(old)
                    removed.append(tid)

            return {"added": added, "reloaded": reloaded, "removed": removed, "errors": errors}

    async def create(self, tid: str, settings: TenantSettings) -> Tenant:
        async with self._lock:
            validate_tenant_id(tid)
            if tid in self._tenants:
                raise ValueError(f"Tenant '{tid}' already exists")
            path = self.dir / f"{tid}.env"
            if path.exists():
                raise ValueError(f"Tenant file already exists: {path}")
            self.dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_env(path, serialize_tenant_settings(settings))
            try:
                tenant = await self._build_tenant(tid, settings)
            except Exception:
                # Roll back the file write so the registry stays consistent.
                if path.exists():
                    path.unlink()
                raise
            self._tenants[tid] = tenant
            return tenant

    async def update(self, tid: str, settings: TenantSettings) -> Tenant:
        async with self._lock:
            validate_tenant_id(tid)
            if tid not in self._tenants:
                raise KeyError(f"Tenant '{tid}' not found")
            path = self.dir / f"{tid}.env"
            _atomic_write_env(path, serialize_tenant_settings(settings))
            new = await self._build_tenant(tid, settings)
            old = self._tenants[tid]
            self._tenants[tid] = new
            await self._safe_close(old)
            return new

    async def delete(self, tid: str) -> None:
        async with self._lock:
            if tid not in self._tenants:
                raise KeyError(f"Tenant '{tid}' not found")
            tenant = self._tenants[tid]
            await self._safe_close(tenant)
            path = self.dir / f"{tid}.env"
            if global_settings.admin_archive_on_delete and path.exists():
                archive = self.dir / "_archive"
                archive.mkdir(parents=True, exist_ok=True)
                os.replace(path, archive / f"{tid}-{int(time.time())}.env")
            elif path.exists():
                path.unlink()
            self._tenants.pop(tid, None)

    async def close_all(self) -> None:
        async with self._lock:
            for tid, tenant in list(self._tenants.items()):
                try:
                    await tenant.db_manager.close()
                except Exception as exc:
                    logger.warning("[%s] close failed: %s", tid, exc)
            self._tenants.clear()

    @staticmethod
    async def _safe_close(tenant: Tenant) -> None:
        try:
            await tenant.db_manager.close()
        except Exception as exc:
            logger.warning("[%s] close failed: %s", tenant.id, exc)
