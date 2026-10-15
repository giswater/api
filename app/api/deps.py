"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request

from app.auth import get_current_user
from app.auth.schemas import ApiUser
from app.services.context import ServiceContext, service_context_from_commons
from app.tenancy.registry import Tenant
from app.db.context import DB_IDENTITY_CTX, DbIdentity


def get_service_context(commons: dict) -> ServiceContext:
    """Build a service context from route dependencies."""
    return service_context_from_commons(commons)


def _get_tenant(request: Request) -> Tenant:
    tenant: Tenant | None = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not specified")
    return tenant


async def get_schema(
    request: Request,
    schema: str = Query(..., description="Database schema name", examples=["public"]),
):
    """Validate that `schema` exists in the current tenant's database."""
    tenant = _get_tenant(request)
    if not await tenant.db_manager.validate_schema(schema):
        raise HTTPException(status_code=404, detail=f"Schema '{schema}' not found")
    return schema


def _db_role_for_user(user: ApiUser) -> str | None:
    if user.is_anonymous:
        return None
    return user.db_role or user.preferred_username


async def common_parameters(
    request: Request,
    current_user: Annotated[ApiUser, Depends(get_current_user)],
    schema: str = Depends(get_schema),
    device: int = Header(
        default=5,
        alias="X-Device",
        description=(
            "Device identifier. Valid values: 1 = Mobile, 2 = Tablet, 3 = Web Desktop, 4 = QGIS Desktop, 5 = QGIS Web"
        ),
        ge=1,
        le=5,
    ),
    lang: Literal["es_ES", "es_CR", "en_US", "pt_BR", "pt_PT", "fr_FR", "ca_ES"] = Header(
        default="es_ES",
        alias="X-Lang",
        description="Language code",
        examples=["es_ES", "es_CR", "en_US", "pt_BR", "pt_PT", "fr_FR", "ca_ES"],
    ),
):
    tenant = _get_tenant(request)
    if current_user.is_anonymous:
        identity = DbIdentity(username=None, db_role=None)
    else:
        identity = DbIdentity(
            username=current_user.preferred_username,
            db_role=_db_role_for_user(current_user),
        )
    DB_IDENTITY_CTX.set(identity)
    return {
        "request": request,
        "user": current_user,
        "user_id": current_user.preferred_username,
        "db_role": identity.db_role,
        "schema": schema,
        "device": device,
        "lang": lang,
        "db_manager": tenant.db_manager,
        "tenant": tenant,
        "api_version": request.app.version,
    }


CommonsDep = Annotated[dict, Depends(common_parameters)]


async def tenant_user_parameters(
    request: Request,
    current_user: Annotated[ApiUser, Depends(get_current_user)],
):
    """Auth + tenant only (no schema / device / lang). Used by job status polls."""
    tenant = _get_tenant(request)
    return {
        "request": request,
        "user": current_user,
        "user_id": current_user.preferred_username,
        "tenant": tenant,
        "db_manager": tenant.db_manager,
        "api_version": request.app.version,
    }


TenantUserDep = Annotated[dict, Depends(tenant_user_parameters)]


def require_feature(flag: str):
    """Router-level dep that 404s when the tenant has the API toggle off."""

    async def _check(request: Request) -> None:
        tenant = _get_tenant(request)
        if not getattr(tenant.settings, flag, False):
            raise HTTPException(status_code=404, detail="Feature disabled")

    return _check


PLUGIN_BY_ENDPOINT: dict[Callable[..., Any], str] = {}


def _track_plugin_router(router: APIRouter, plugin_id: str) -> None:
    for route in router.routes:
        ep = getattr(route, "endpoint", None)
        if callable(ep):
            PLUGIN_BY_ENDPOINT[ep] = plugin_id


def require_plugin(plugin_id: str):
    """Router-level dep that 404s when the plugin is not in ENABLED_PLUGINS."""

    async def _check(request: Request) -> None:
        tenant = _get_tenant(request)
        if not tenant.settings.plugin_enabled(plugin_id):
            raise HTTPException(status_code=404, detail="Feature disabled")

    return _check


def register_plugin_router(app: FastAPI, router: APIRouter, plugin_id: str) -> None:
    """Register a plugin router with tenant allowlist gating and OpenAPI tracking."""
    _track_plugin_router(router, plugin_id)
    app.include_router(router, dependencies=[Depends(require_plugin(plugin_id))])
