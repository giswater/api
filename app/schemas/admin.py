"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..core.config import TenantSettings
from ..tenancy.registry import Tenant

AuthMode = Literal["none", "basic", "keycloak"]

_REDACTED = "***"


class DbSettingsIn(BaseModel):
    host: str = "localhost"
    port: str = "5432"
    name: str = "postgres"
    user: str = "postgres"
    password: Optional[str] = None
    schema_: str = Field(default="public", alias="schema")
    database_url: Optional[str] = None
    pool_min_size: int = 1
    pool_max_size: int = 10
    pool_timeout: float = 30.0
    pool_max_waiting: int = 0
    pool_max_idle: float = 300.0
    connect_timeout: float = 5.0

    model_config = {"populate_by_name": True}


class DbSettingsOut(BaseModel):
    host: str
    port: str
    name: str
    user: str
    password: Optional[str] = None  # always _REDACTED or null
    schema_: str = Field(alias="schema")
    database_url: Optional[str] = None
    pool_min_size: int
    pool_max_size: int
    pool_timeout: float
    pool_max_waiting: int
    pool_max_idle: float
    connect_timeout: float

    model_config = {"populate_by_name": True}


class KeycloakSettingsIn(BaseModel):
    enabled: bool = False  # DEPRECATED #22: use auth.mode; remove in 2.0.0
    url: Optional[str] = None
    realm: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    admin_client_id: Optional[str] = None
    admin_client_secret: Optional[str] = None
    callback_uri: Optional[str] = None


class KeycloakSettingsOut(BaseModel):
    enabled: bool  # DEPRECATED #22: use auth.mode; remove in 2.0.0
    url: Optional[str] = None
    realm: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None  # _REDACTED or null
    admin_client_id: Optional[str] = None
    admin_client_secret: Optional[str] = None  # _REDACTED or null
    callback_uri: Optional[str] = None


class AuthSettingsIn(BaseModel):
    mode: AuthMode = "none"
    bootstrap_user: Optional[str] = Field(default=None, alias="bootstrapUser")
    bootstrap_password: Optional[str] = Field(default=None, alias="bootstrapPassword")
    keycloak: Optional[KeycloakSettingsIn] = None

    model_config = {"populate_by_name": True}


class AuthSettingsOut(BaseModel):
    mode: AuthMode
    bootstrap_user: Optional[str] = Field(default=None, alias="bootstrapUser")
    bootstrap_password: Optional[str] = None  # _REDACTED or null
    keycloak: Optional[KeycloakSettingsOut] = None

    model_config = {"populate_by_name": True}


class TenantIn(BaseModel):
    api: dict[str, bool] = Field(default_factory=dict)
    db: DbSettingsIn
    auth: Optional[AuthSettingsIn] = None
    keycloak: Optional[KeycloakSettingsIn] = None  # DEPRECATED #22: use auth.keycloak


class TenantCreateIn(TenantIn):
    id: str


class PoolStatus(BaseModel):
    size: Optional[int] = None
    in_use: Optional[int] = None
    healthy: bool = False


class TenantOut(BaseModel):
    id: str
    api: dict[str, bool]
    db: DbSettingsOut
    auth: AuthSettingsOut
    keycloak: Optional[KeycloakSettingsOut] = None  # DEPRECATED #22: use auth.keycloak
    pool: PoolStatus

    @classmethod
    def from_tenant(cls, tenant: Tenant) -> "TenantOut":
        s = tenant.settings
        api = {
            "basic": s.api_basic,
            "profile": s.api_profile,
            "flow": s.api_flow,
            "mincut": s.api_mincut,
            "water_balance": s.api_water_balance,
            "mapzones": s.api_mapzones,
            "routing": s.api_routing,
            "crm": s.api_crm,
            "epa": s.api_epa,
            "features": s.api_features,
        }
        db = DbSettingsOut(
            host=s.db_host,
            port=s.db_port,
            name=s.db_name,
            user=s.db_user,
            password=_REDACTED if s.db_password else None,
            schema=s.db_schema,
            database_url=_REDACTED if s.database_url else None,
            pool_min_size=s.db_pool_min_size,
            pool_max_size=s.db_pool_max_size,
            pool_timeout=s.db_pool_timeout,
            pool_max_waiting=s.db_pool_max_waiting,
            pool_max_idle=s.db_pool_max_idle,
            connect_timeout=s.db_connect_timeout,
        )
        keycloak_out: Optional[KeycloakSettingsOut] = None
        if s.auth_mode == "keycloak" or any(
            (
                s.keycloak_url,
                s.keycloak_realm,
                s.keycloak_client_id,
                s.keycloak_admin_client_id,
                s.keycloak_callback_uri,
            )
        ):
            keycloak_out = KeycloakSettingsOut(
                enabled=s.keycloak_enabled,
                url=s.keycloak_url,
                realm=s.keycloak_realm,
                client_id=s.keycloak_client_id,
                client_secret=_REDACTED if s.keycloak_client_secret else None,
                admin_client_id=s.keycloak_admin_client_id,
                admin_client_secret=_REDACTED if s.keycloak_admin_client_secret else None,
                callback_uri=s.keycloak_callback_uri,
            )
        auth = AuthSettingsOut(
            mode=s.auth_mode,
            bootstrapUser=s.auth_basic_bootstrap_user,
            bootstrap_password=_REDACTED if s.auth_basic_bootstrap_password else None,
            keycloak=keycloak_out if s.auth_mode == "keycloak" else None,
        )
        pool = tenant.db_manager.connection_pool
        pool_status = PoolStatus(
            size=getattr(pool, "max_size", None) if pool is not None else None,
            in_use=None,
            healthy=pool is not None,
        )
        return cls(
            id=tenant.id,
            api=api,
            db=db,
            auth=auth,
            keycloak=keycloak_out,  # DEPRECATED #22: duplicate of auth.keycloak; remove in 2.0.0
            pool=pool_status,
        )


def build_tenant_settings_from_input(
    payload: TenantIn,
    *,
    existing: Optional[TenantSettings] = None,
) -> TenantSettings:
    """Convert a TenantIn payload into a TenantSettings.

    When `existing` is provided, secrets that come back as `None` keep the
    previous value (so PUT clients don't have to resend the password)."""
    api = payload.api or {}

    def _api(name: str) -> bool:
        if name in api:
            return bool(api[name])
        return bool(getattr(existing, f"api_{name}", False)) if existing else False

    db = payload.db
    auth = payload.auth
    # DEPRECATED #22: payload.keycloak fallback; remove in 2.0.0
    kc = auth.keycloak if auth and auth.keycloak else payload.keycloak

    def _kept(new, old):
        return new if new is not None else old

    if auth is not None:
        auth_mode = auth.mode
    elif kc and kc.enabled:
        auth_mode = "keycloak"  # DEPRECATED #22: legacy keycloak.enabled; remove in 2.0.0
    elif existing is not None:
        auth_mode = existing.auth_mode
    else:
        auth_mode = "none"

    bootstrap_user = auth.bootstrap_user if auth else None
    bootstrap_password = auth.bootstrap_password if auth else None
    if existing is not None:
        bootstrap_user = _kept(bootstrap_user, existing.auth_basic_bootstrap_user)
        bootstrap_password = _kept(bootstrap_password, existing.auth_basic_bootstrap_password)

    return TenantSettings(
        api_basic=_api("basic"),
        api_profile=_api("profile"),
        api_flow=_api("flow"),
        api_mincut=_api("mincut"),
        api_water_balance=_api("water_balance"),
        api_mapzones=_api("mapzones"),
        api_routing=_api("routing"),
        api_crm=_api("crm"),
        api_epa=_api("epa"),
        api_features=_api("features"),
        db_host=db.host,
        db_port=db.port,
        db_name=db.name,
        db_user=db.user,
        db_password=_kept(db.password, existing.db_password if existing else None) or "postgres",
        db_schema=db.schema_,
        database_url=_kept(db.database_url, existing.database_url if existing else None),
        db_pool_min_size=db.pool_min_size,
        db_pool_max_size=db.pool_max_size,
        db_pool_timeout=db.pool_timeout,
        db_pool_max_waiting=db.pool_max_waiting,
        db_pool_max_idle=db.pool_max_idle,
        db_connect_timeout=db.connect_timeout,
        auth_mode=auth_mode,
        auth_basic_bootstrap_user=bootstrap_user,
        auth_basic_bootstrap_password=bootstrap_password,
        keycloak_url=kc.url if kc else None,
        keycloak_realm=kc.realm if kc else None,
        keycloak_client_id=kc.client_id if kc else None,
        keycloak_client_secret=(
            _kept(kc.client_secret, existing.keycloak_client_secret if existing else None) if kc else None
        ),
        keycloak_admin_client_id=kc.admin_client_id if kc else None,
        keycloak_admin_client_secret=(
            _kept(kc.admin_client_secret, existing.keycloak_admin_client_secret if existing else None) if kc else None
        ),
        keycloak_callback_uri=kc.callback_uri if kc else None,
    )
