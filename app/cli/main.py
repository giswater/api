"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import click

from app.cli.bootstrap import (
    build_tenant_context,
    emit_json,
    get_registry,
    resolve_tenant,
    run_service,
    tenants_dir_from_ctx,
)
from app.db.migrate import get_current_revision, history, run_alembic_upgrade
from app.schemas.crm.crm_models import HydrometerCreate
from app.services.admin.tenant_service import TenantService
from app.services.admin.user_service import GwapiUserService
from app.services.crm_service import CrmService
from app.services.system_service import SystemService


@click.group()
@click.option("--tenants-dir", type=click.Path(exists=True, file_okay=False), default=None, help="Tenants config dir")
@click.pass_context
def main(ctx: click.Context, tenants_dir: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["tenants_dir"] = tenants_dir


@main.group()
def admin() -> None:
    """Platform admin operations."""


@admin.group("tenants")
def admin_tenants() -> None:
    """Manage tenants."""


@admin_tenants.command("list")
@click.pass_context
def admin_tenants_list(ctx: click.Context) -> None:
    async def _run():
        registry = await get_registry(tenants_dir_from_ctx(ctx.obj))
        return [t.model_dump(by_alias=True) for t in TenantService(registry).list_tenants()]

    emit_json(run_service(_run))


@admin_tenants.command("get")
@click.argument("tenant_id")
@click.pass_context
def admin_tenants_get(ctx: click.Context, tenant_id: str) -> None:
    async def _run():
        registry = await get_registry(tenants_dir_from_ctx(ctx.obj))
        return TenantService(registry).get_tenant(tenant_id).model_dump(by_alias=True)

    emit_json(run_service(_run))


@admin.group("users")
def admin_users() -> None:
    """Manage tenant users (basic auth tenants)."""


@admin_users.command("list")
@click.option("--tenant", required=True, help="Tenant id")
@click.pass_context
def admin_users_list(ctx: click.Context, tenant: str) -> None:
    async def _run():
        registry = await get_registry(tenants_dir_from_ctx(ctx.obj))
        users = await GwapiUserService(registry).list_users(tenant)
        return [u.model_dump() for u in users]

    emit_json(run_service(_run))


@admin_users.command("create")
@click.option("--tenant", required=True)
@click.option("--username", required=True)
@click.option("--password", required=True)
@click.option("--db-role", default=None)
@click.option("--role", "roles", multiple=True, default=["basic"])
@click.option("--enabled/--disabled", default=True)
@click.pass_context
def admin_users_create(
    ctx: click.Context,
    tenant: str,
    username: str,
    password: str,
    db_role: str | None,
    roles: tuple[str, ...],
    enabled: bool,
) -> None:
    async def _run():
        registry = await get_registry(tenants_dir_from_ctx(ctx.obj))
        user = await GwapiUserService(registry).create_user(
            tenant,
            username=username,
            password=password,
            db_role=db_role,
            roles=list(roles),
            enabled=enabled,
        )
        return user.model_dump()

    emit_json(run_service(_run))


@main.group("db")
def db_group() -> None:
    """Database migrations for the API-owned `gwapi` schema."""


async def _db_targets(ctx: click.Context, tenant: str | None, all_tenants: bool):
    registry = await get_registry(tenants_dir_from_ctx(ctx.obj))
    if all_tenants:
        return registry.all()
    if not tenant:
        raise click.UsageError("Provide --tenant <id> or --all")
    return [await resolve_tenant(tenant, tenants_dir_from_ctx(ctx.obj))]


@db_group.command("upgrade")
@click.option("--tenant", default=None, help="Tenant id")
@click.option("--all", "all_tenants", is_flag=True, help="Upgrade every loaded tenant")
@click.pass_context
def db_upgrade(ctx: click.Context, tenant: str | None, all_tenants: bool) -> None:
    """Run `alembic upgrade head` against one or all tenants."""

    async def _run():
        results = []
        for t in await _db_targets(ctx, tenant, all_tenants):
            await run_alembic_upgrade(t.db_manager)
            revision = await get_current_revision(t.db_manager.database_url)
            results.append({"tenant": t.id, "revision": revision})
        return results

    emit_json(run_service(_run))


@db_group.command("current")
@click.option("--tenant", default=None, help="Tenant id")
@click.option("--all", "all_tenants", is_flag=True, help="Report every loaded tenant")
@click.pass_context
def db_current(ctx: click.Context, tenant: str | None, all_tenants: bool) -> None:
    """Show the applied Alembic revision per tenant."""

    async def _run():
        results = []
        for t in await _db_targets(ctx, tenant, all_tenants):
            revision = await get_current_revision(t.db_manager.database_url)
            results.append({"tenant": t.id, "revision": revision})
        return results

    emit_json(run_service(_run))


@db_group.command("history")
def db_history() -> None:
    """List available migration revisions (newest first)."""
    emit_json(history())


@main.group()
@click.option("--tenant", required=True, help="Tenant id")
@click.option("--schema", required=True, help="Database schema")
@click.option("--user", default=None, help="Current user for SET ROLE / gw_fct payloads")
@click.option("--db-role", default=None, help="PostgreSQL role for SET ROLE")
@click.option("--device", default=5, show_default=True, type=int)
@click.option("--lang", default="es_ES", show_default=True)
@click.pass_context
def tenant(
    ctx: click.Context,
    tenant: str,
    schema: str,
    user: str | None,
    db_role: str | None,
    device: int,
    lang: str,
) -> None:
    ctx.obj["tenant_id"] = tenant
    ctx.obj["schema"] = schema
    ctx.obj["user"] = user
    ctx.obj["db_role"] = db_role
    ctx.obj["device"] = device
    ctx.obj["lang"] = lang


async def _tenant_context(ctx: click.Context):
    t = await resolve_tenant(ctx.obj["tenant_id"], tenants_dir_from_ctx(ctx.obj))
    return build_tenant_context(
        t,
        schema=ctx.obj["schema"],
        user=ctx.obj.get("user"),
        db_role=ctx.obj.get("db_role"),
        device=ctx.obj["device"],
        lang=ctx.obj["lang"],
    )


@tenant.command("ready")
@click.pass_context
def tenant_ready(ctx: click.Context) -> None:
    async def _run():
        t = await resolve_tenant(ctx.obj["tenant_id"], tenants_dir_from_ctx(ctx.obj))
        return await SystemService(t).ready()

    result = run_service(_run)
    code = 0 if result.get("status") == "ready" else 1
    emit_json(result, exit_code=code)


@tenant.group("crm")
def tenant_crm() -> None:
    """CRM operations for the selected tenant."""


@tenant_crm.command("insert-hydrometer")
@click.option("--code", required=True)
@click.option("--hydro-number", required=True)
@click.pass_context
def tenant_crm_insert_hydrometer(ctx: click.Context, code: str, hydro_number: str) -> None:
    async def _run():
        svc_ctx = await _tenant_context(ctx)
        payload = HydrometerCreate(code=code, hydroNumber=hydro_number)
        return await CrmService(svc_ctx).insert_hydrometers([payload])

    emit_json(run_service(_run))


if __name__ == "__main__":
    main()
