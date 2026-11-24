"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from app.core.config import global_settings
from app.schemas.admin import TenantCreateIn, TenantIn, TenantOut, build_tenant_settings_from_input
from app.tenancy.registry import RESERVED_IDS, TENANT_ID_RE, Tenant, TenantRegistry, validate_tenant_id


class TenantServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class TenantService:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry

    def require_writes(self) -> None:
        if not global_settings.admin_write_enabled:
            raise TenantServiceError("Tenant writes disabled", status_code=403)

    def require_reload(self) -> None:
        if not global_settings.admin_reload_enabled:
            raise TenantServiceError("Reload disabled", status_code=403)

    def list_tenants(self) -> list[TenantOut]:
        return [TenantOut.from_tenant(t) for t in self.registry.all()]

    def get_tenant(self, tid: str) -> TenantOut:
        tenant = self.registry.get(tid)
        if tenant is None:
            raise TenantServiceError(f"Tenant '{tid}' not found", status_code=404)
        return TenantOut.from_tenant(tenant)

    def _validate_id_or_409(self, tid: str) -> None:
        if not TENANT_ID_RE.match(tid) or tid in RESERVED_IDS:
            raise TenantServiceError(f"Invalid tenant id '{tid}'", status_code=400)
        if self.registry.get(tid) is not None:
            raise TenantServiceError(f"Tenant '{tid}' already exists", status_code=409)

    async def create_tenant(self, payload: TenantCreateIn) -> TenantOut:
        self.require_writes()
        self._validate_id_or_409(payload.id)
        try:
            settings = build_tenant_settings_from_input(payload)
            tenant = await self.registry.create(payload.id, settings)
        except ValueError as exc:
            raise TenantServiceError(str(exc), status_code=400) from exc
        return TenantOut.from_tenant(tenant)

    async def update_tenant(self, tid: str, payload: TenantIn) -> TenantOut:
        self.require_writes()
        existing = self.registry.get(tid)
        if existing is None:
            raise TenantServiceError(f"Tenant '{tid}' not found", status_code=404)
        try:
            settings = build_tenant_settings_from_input(payload, existing=existing.settings)
        except ValueError as exc:
            raise TenantServiceError(str(exc), status_code=400) from exc
        try:
            tenant = await self.registry.update(tid, settings)
        except KeyError as exc:
            raise TenantServiceError(str(exc), status_code=404) from exc
        return TenantOut.from_tenant(tenant)

    async def delete_tenant(self, tid: str) -> None:
        self.require_writes()
        try:
            await self.registry.delete(tid)
        except KeyError as exc:
            raise TenantServiceError(str(exc), status_code=404) from exc

    async def reload_tenant(self, tid: str) -> TenantOut:
        self.require_writes()
        try:
            validate_tenant_id(tid)
        except ValueError as exc:
            raise TenantServiceError(str(exc), status_code=400) from exc
        try:
            tenant = await self.registry.reload_one(tid)
        except FileNotFoundError as exc:
            raise TenantServiceError(str(exc), status_code=404) from exc
        return TenantOut.from_tenant(tenant)

    async def reload_all(self) -> dict:
        self.require_reload()
        return await self.registry.reload()

    def get_tenant_record(self, tid: str) -> Tenant:
        tenant = self.registry.get(tid)
        if tenant is None:
            raise TenantServiceError(f"Tenant '{tid}' not found", status_code=404)
        return tenant
