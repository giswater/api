"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import logging
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from dotenv import dotenv_values, load_dotenv

logger = logging.getLogger(__name__)
AuthMode = Literal["none", "basic", "keycloak"]
AUTH_MODES = frozenset({"none", "basic", "keycloak"})

# Tracks 2.0.0 cleanup: grep `DEPRECATED #22` (github.com/Giswater/giswater-api/issues/22).
DEPRECATED_KEYCLOAK_ENABLED_ISSUE = "22"

# Mirror of `app.tenancy.registry.TENANT_ID_RE` / `RESERVED_IDS` (kept here to avoid a
# circular import: `app.tenancy.registry` imports from this module).
_TENANT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_RESERVED_TENANT_IDS = {"www", "api", "admin", "static", "traefik", "localhost"}


def _to_bool(value, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("true", "t", "yes", "y", "1", "on")


def _to_int(value, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_api_root(value: str | None, default: str = "/giswater") -> str:
    """Normalize and validate the public API root prefix (e.g. ``/giswater``).

    Accepts ``giswater``, ``/giswater``, ``/giswater/``. Rejects empty roots
    (``/``), embedded ``//``, whitespace, query/fragment markers, and path
    traversal. The result always starts with ``/`` and has no trailing slash.
    """
    raw = (value or "").strip()
    if not raw:
        return default
    candidate = raw if raw.startswith("/") else f"/{raw}"
    candidate = candidate.rstrip("/")
    if not candidate or candidate == "/":
        raise ValueError(f"API_ROOT must be a non-empty path, got {value!r}")
    forbidden = ("//", "?", "#", " ", "\t", "\n")
    if any(token in candidate for token in forbidden):
        raise ValueError(f"API_ROOT contains forbidden characters: {value!r}")
    if ".." in candidate.split("/"):
        raise ValueError(f"API_ROOT must not contain path traversal: {value!r}")
    return candidate


def _normalize_single_tenant_id(value: str | None) -> str | None:
    """Validate `SINGLE_TENANT_ID`. Empty/unset → ``None`` (DNS multi-tenant mode)."""
    raw = (value or "").strip()
    if not raw:
        return None
    if not _TENANT_ID_RE.match(raw):
        raise ValueError(f"SINGLE_TENANT_ID must match tenant id rules, got {value!r}")
    if raw in _RESERVED_TENANT_IDS:
        raise ValueError(f"SINGLE_TENANT_ID is reserved: {value!r}")
    return raw


@dataclass(frozen=True)
class GlobalSettings:
    """Process-wide configuration. One instance lives in `global_settings`."""

    # Routing
    base_domain: str = "bgeo360.com"
    tenants_dir: str = "config/tenants"
    # Public URL root prefix for all API surfaces (e.g. "/giswater" → "/giswater/v1", "/giswater/admin").
    api_root: str = "/giswater"

    # Logging
    log_dir: str = "logs"
    log_level: str = "INFO"
    log_rotate_days: int = 14
    log_db_enabled: bool = True
    log_db_sample_rate: float = 1.0
    # When True, request/response bodies appear in file + DB logs (truncated per LOG_DB_MAX_BODY_BYTES).
    log_http_body_capture: bool = True
    # Max bytes stored per body when capture is enabled; 0 means use safe default (2048).
    log_db_max_body_bytes: int = 2048
    # Max bytes stored for `gwapi.db_logs.response_json` (raw DB function output).
    # DB responses can be much larger than HTTP form bodies, so this is a separate knob.
    # 0 (or negative) disables truncation (full payload stored).
    log_db_response_max_bytes: int = 8192

    # Rate limiting
    rate_limit_default_max_requests: int = 30
    rate_limit_default_window_seconds: int = 60

    # Admin
    admin_user: str = "admin"
    admin_password: str | None = None
    admin_reload_enabled: bool = True
    admin_write_enabled: bool = True
    admin_archive_on_delete: bool = True

    # Single-tenant routing (IP-only or single-host deployments). When set,
    # all `${API_ROOT}/v1/*` requests resolve to this tenant regardless of Host,
    # and `${API_ROOT}/admin/*` is reachable on the same host. When unset, the
    # app uses DNS-based multi-tenant routing via `BASE_DOMAIN`.
    single_tenant_id: str | None = None

    # Dev
    dev_allow_tenant_header: bool = False

    # Platform Keycloak (separate from per-tenant Keycloak)
    platform_keycloak_enabled: bool = False
    platform_keycloak_url: str | None = None
    platform_keycloak_realm: str | None = None
    platform_keycloak_client_id: str | None = None
    platform_keycloak_client_secret: str | None = None

    # DB compatibility (optional readiness gate; see GISWATER_DB_* env vars)
    giswater_db_version_check: bool = False
    giswater_db_min_version: str = "4.17.0"

    # Alembic migrations for the API-owned `gwapi` schema.
    # When True, `alembic upgrade head` runs per tenant on load. Set False to
    # defer schema changes to a controlled window (`giswater-api db upgrade`).
    db_auto_migrate: bool = True
    db_migrate_timeout: float = 30.0

    # Legacy aliases (kept for the duration of the multi-tenant migration).
    @property
    def log_admin_user(self) -> str:
        return self.admin_user

    @property
    def log_admin_password(self) -> str | None:
        return self.admin_password


@dataclass(frozen=True)
class TenantSettings:
    """Per-tenant configuration loaded from `config/tenants/<id>.env`."""

    # API toggles
    api_basic: bool = False
    api_profile: bool = False
    api_flow: bool = False
    api_mincut: bool = False
    api_water_balance: bool = False
    api_mapzones: bool = False
    api_routing: bool = False
    api_crm: bool = False
    api_epa: bool = False
    api_features: bool = False

    # Database
    db_host: str = "localhost"
    db_port: str = "5432"
    db_name: str = "postgres"
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_schema: str = "public"
    database_url: str | None = None
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_timeout: float = 30.0
    db_pool_max_waiting: int = 0
    db_pool_max_idle: float = 300.0
    db_connect_timeout: float = 5.0

    # Tenant API authentication
    auth_mode: AuthMode = "none"
    auth_basic_bootstrap_user: str | None = None
    auth_basic_bootstrap_password: str | None = None

    # Keycloak (required when auth_mode == "keycloak")
    keycloak_url: str | None = None
    keycloak_realm: str | None = None
    keycloak_client_id: str | None = None
    keycloak_client_secret: str | None = None
    keycloak_admin_client_id: str | None = None
    keycloak_admin_client_secret: str | None = None
    keycloak_callback_uri: str | None = None

    @property
    def keycloak_enabled(self) -> bool:
        return self.auth_mode == "keycloak"

    def validate(self) -> None:
        if self.auth_mode == "keycloak":
            missing = [
                name
                for name, value in (
                    ("KEYCLOAK_URL", self.keycloak_url),
                    ("KEYCLOAK_REALM", self.keycloak_realm),
                    ("KEYCLOAK_CLIENT_ID", self.keycloak_client_id),
                    ("KEYCLOAK_CLIENT_SECRET", self.keycloak_client_secret),
                    ("KEYCLOAK_ADMIN_CLIENT_ID", self.keycloak_admin_client_id),
                    ("KEYCLOAK_ADMIN_CLIENT_SECRET", self.keycloak_admin_client_secret),
                    ("KEYCLOAK_CALLBACK_URI", self.keycloak_callback_uri),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"Keycloak configuration is incomplete: {', '.join(missing)}")
        if self.auth_mode not in AUTH_MODES:
            raise ValueError(f"Invalid AUTH_MODE '{self.auth_mode}'")


def _resolve_auth_mode(env: Mapping[str, str | None]) -> AuthMode:
    auth_mode_raw = (env.get("AUTH_MODE") or "").strip().lower()
    if auth_mode_raw in AUTH_MODES:
        return auth_mode_raw  # type: ignore[return-value]

    # DEPRECATED #22: entire block below (KEYCLOAK_ENABLED env fallback); remove in 2.0.0
    if env.get("AUTH_MODE") is None and env.get("KEYCLOAK_ENABLED") is not None:
        warnings.warn(
            "KEYCLOAK_ENABLED is deprecated; set AUTH_MODE=keycloak|basic|none. "
            f"Removal in giswater-api 2.0.0 (#{DEPRECATED_KEYCLOAK_ENABLED_ISSUE}).",
            DeprecationWarning,
            stacklevel=3,
        )
        logger.info(
            "KEYCLOAK_ENABLED is deprecated; set AUTH_MODE explicitly. Removal in giswater-api 2.0.0 (#%s).",
            DEPRECATED_KEYCLOAK_ENABLED_ISSUE,
        )
    if _to_bool(env.get("KEYCLOAK_ENABLED"), False):
        return "keycloak"
    # END DEPRECATED #22

    return "none"


def _build_global(env: Mapping[str, str | None]) -> GlobalSettings:
    return GlobalSettings(
        base_domain=(env.get("BASE_DOMAIN") or "bgeo360.com"),
        tenants_dir=(env.get("TENANTS_DIR") or "config/tenants"),
        api_root=_normalize_api_root(env.get("API_ROOT")),
        log_dir=(env.get("LOG_DIR") or "logs"),
        log_level=(env.get("LOG_LEVEL") or "INFO"),
        log_rotate_days=_to_int(env.get("LOG_ROTATE_DAYS"), 14),
        log_db_enabled=_to_bool(env.get("LOG_DB_ENABLED"), True),
        log_db_sample_rate=_to_float(env.get("LOG_DB_SAMPLE_RATE"), 1.0),
        log_http_body_capture=_to_bool(env.get("LOG_HTTP_BODY_CAPTURE"), True),
        log_db_max_body_bytes=_to_int(env.get("LOG_DB_MAX_BODY_BYTES"), 2048),
        log_db_response_max_bytes=_to_int(env.get("LOG_DB_RESPONSE_MAX_BYTES"), 8192),
        rate_limit_default_max_requests=_to_int(env.get("RATE_LIMIT_DEFAULT_MAX_REQUESTS"), 30),
        rate_limit_default_window_seconds=_to_int(env.get("RATE_LIMIT_DEFAULT_WINDOW_SECONDS"), 60),
        admin_user=(env.get("ADMIN_USER") or env.get("LOG_ADMIN_USER") or "admin"),
        admin_password=(env.get("ADMIN_PASSWORD") or env.get("LOG_ADMIN_PASSWORD") or None),
        admin_reload_enabled=_to_bool(env.get("ADMIN_RELOAD_ENABLED"), True),
        admin_write_enabled=_to_bool(env.get("ADMIN_WRITE_ENABLED"), True),
        admin_archive_on_delete=_to_bool(env.get("ADMIN_ARCHIVE_ON_DELETE"), True),
        single_tenant_id=_normalize_single_tenant_id(env.get("SINGLE_TENANT_ID")),
        dev_allow_tenant_header=_to_bool(env.get("DEV_ALLOW_TENANT_HEADER"), False),
        platform_keycloak_enabled=_to_bool(env.get("PLATFORM_KEYCLOAK_ENABLED"), False),
        platform_keycloak_url=env.get("PLATFORM_KEYCLOAK_URL") or None,
        platform_keycloak_realm=env.get("PLATFORM_KEYCLOAK_REALM") or None,
        platform_keycloak_client_id=env.get("PLATFORM_KEYCLOAK_CLIENT_ID") or None,
        platform_keycloak_client_secret=env.get("PLATFORM_KEYCLOAK_CLIENT_SECRET") or None,
        giswater_db_version_check=_to_bool(env.get("GISWATER_DB_VERSION_CHECK"), False),
        giswater_db_min_version=(env.get("GISWATER_DB_MIN_VERSION") or "4.17.0"),
        db_auto_migrate=_to_bool(env.get("DB_AUTO_MIGRATE"), True),
        db_migrate_timeout=_to_float(env.get("DB_MIGRATE_TIMEOUT"), 30.0),
    )


def _build_tenant(env: Mapping[str, str | None]) -> TenantSettings:
    return TenantSettings(
        api_basic=_to_bool(env.get("API_BASIC"), False),
        api_profile=_to_bool(env.get("API_PROFILE"), False),
        api_flow=_to_bool(env.get("API_FLOW"), False),
        api_mincut=_to_bool(env.get("API_MINCUT"), False),
        api_water_balance=_to_bool(env.get("API_WATER_BALANCE"), False),
        api_mapzones=_to_bool(env.get("API_MAPZONES"), False),
        api_routing=_to_bool(env.get("API_ROUTING"), False),
        api_crm=_to_bool(env.get("API_CRM"), False),
        api_epa=_to_bool(env.get("API_EPA"), False),
        api_features=_to_bool(env.get("API_FEATURES"), False),
        db_host=(env.get("DB_HOST") or "localhost"),
        db_port=(env.get("DB_PORT") or "5432"),
        db_name=(env.get("DB_NAME") or "postgres"),
        db_user=(env.get("DB_USER") or "postgres"),
        db_password=(env.get("DB_PASSWORD") or "postgres"),
        db_schema=(env.get("DB_SCHEMA") or "public"),
        database_url=env.get("DATABASE_URL") or None,
        db_pool_min_size=_to_int(env.get("DB_POOL_MIN_SIZE"), 1),
        db_pool_max_size=_to_int(env.get("DB_POOL_MAX_SIZE"), 10),
        db_pool_timeout=_to_float(env.get("DB_POOL_TIMEOUT"), 30.0),
        db_pool_max_waiting=_to_int(env.get("DB_POOL_MAX_WAITING"), 0),
        db_pool_max_idle=_to_float(env.get("DB_POOL_MAX_IDLE"), 300.0),
        db_connect_timeout=_to_float(env.get("DB_CONNECT_TIMEOUT"), 5.0),
        auth_mode=_resolve_auth_mode(env),
        auth_basic_bootstrap_user=env.get("AUTH_BASIC_BOOTSTRAP_USER") or None,
        auth_basic_bootstrap_password=env.get("AUTH_BASIC_BOOTSTRAP_PASSWORD") or None,
        keycloak_url=env.get("KEYCLOAK_URL") or None,
        keycloak_realm=env.get("KEYCLOAK_REALM") or None,
        keycloak_client_id=env.get("KEYCLOAK_CLIENT_ID") or None,
        keycloak_client_secret=env.get("KEYCLOAK_CLIENT_SECRET") or None,
        keycloak_admin_client_id=env.get("KEYCLOAK_ADMIN_CLIENT_ID") or None,
        keycloak_admin_client_secret=env.get("KEYCLOAK_ADMIN_CLIENT_SECRET") or None,
        keycloak_callback_uri=env.get("KEYCLOAK_CALLBACK_URI") or None,
    )


def load_global_settings() -> GlobalSettings:
    """Load global settings. The single place that touches process env."""
    load_dotenv()
    return _build_global(os.environ)


def load_tenant_settings(path: Path) -> TenantSettings:
    """Load a tenant from a `.env` file without mutating `os.environ`."""
    return _build_tenant(dotenv_values(path))


global_settings = load_global_settings()
