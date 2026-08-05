"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import logging
import secrets
import time
from typing import Annotated, Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi_keycloak import FastAPIKeycloak

from ..core.config import global_settings
from .users import verify_credentials
from .schemas import ApiUser

logger = logging.getLogger(__name__)

_basic = HTTPBasic(auto_error=False, scheme_name="tenantBasic")
_admin_basic = HTTPBasic(auto_error=False, scheme_name="adminBasic")

# JWKS cache for the platform realm (separate from tenant idps which cache their own).
_PLATFORM_JWKS_TTL = 3600.0
_platform_jwks_cache: dict[str, tuple[float, dict]] = {}
_platform_jwks_lock = asyncio.Lock()


def _roles_from_jwt_payload(payload: dict, client_id: str | None) -> frozenset[str]:
    roles: set[str] = set()
    realm_roles = (payload.get("realm_access") or {}).get("roles") or []
    roles.update(realm_roles)
    if client_id:
        resource = (payload.get("resource_access") or {}).get(client_id) or {}
        roles.update(resource.get("roles") or [])
    return frozenset(roles)


def verify_token(token: str, idp: FastAPIKeycloak) -> ApiUser:
    """Decode a tenant-issued JWT against the tenant's Keycloak public key."""
    try:
        payload = jwt.decode(
            token,
            idp.public_key,
            algorithms=["RS256"],
            audience=idp.client_id,
        )
    except jwt.PyJWTError as exc:
        logger.warning("Tenant token rejected: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    username = payload.get("preferred_username") or payload.get("sub") or "unknown"
    return ApiUser(
        sub=str(payload.get("sub") or username),
        preferred_username=str(username),
        auth_method="keycloak",
        roles=_roles_from_jwt_payload(payload, idp.client_id),
        db_role=str(username),
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(_basic),
) -> ApiUser:
    """Resolve the authenticated tenant API user."""
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        return ApiUser.anonymous()

    auth_mode = tenant.settings.auth_mode
    if auth_mode == "none":
        return ApiUser.anonymous()

    if auth_mode == "keycloak":
        if tenant.idp is None:
            raise HTTPException(status_code=500, detail="Keycloak not configured for tenant")
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = auth.split(" ", 1)[1].strip()
        return verify_token(token, tenant.idp)

    if auth_mode == "basic":
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Missing basic credentials",
                headers={"WWW-Authenticate": 'Basic realm="tenant"'},
            )
        user = await verify_credentials(tenant.db_manager, credentials.username, credentials.password)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": 'Basic realm="tenant"'},
            )
        return user

    raise HTTPException(status_code=500, detail=f"Unsupported auth mode '{auth_mode}'")


# DEPRECATED #22: remove in 2.0.0; use Depends(get_current_user) directly
def get_current_user_dep():
    """Backward-compatible factory; prefer Depends(get_current_user)."""
    return get_current_user


def require_role(*roles: str):
    """403 when the current user lacks any of the given roles (skipped for anonymous users)."""

    async def _check(user: Annotated[ApiUser, Depends(get_current_user)]) -> ApiUser:
        if user.is_anonymous:
            return user
        if not user.has_any_role(roles):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _check


async def _platform_jwks() -> dict:
    """Fetch + cache the platform Keycloak JWKS."""
    if not (global_settings.platform_keycloak_url and global_settings.platform_keycloak_realm):
        raise HTTPException(status_code=500, detail="Platform Keycloak not configured")
    cache_key = f"{global_settings.platform_keycloak_url}/{global_settings.platform_keycloak_realm}"
    now = time.monotonic()
    async with _platform_jwks_lock:
        cached = _platform_jwks_cache.get(cache_key)
        if cached and (now - cached[0]) < _PLATFORM_JWKS_TTL:
            return cached[1]
        url = (
            f"{global_settings.platform_keycloak_url.rstrip('/')}/realms/"
            f"{global_settings.platform_keycloak_realm}/protocol/openid-connect/certs"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            jwks = resp.json()
        _platform_jwks_cache[cache_key] = (now, jwks)
        return jwks


def _jwk_to_pem(jwk: dict) -> str:
    """Convert a single JWK dict to a PEM public key (uses pyjwt helpers)."""
    return jwt.algorithms.RSAAlgorithm.from_jwk(jwk)


async def _verify_platform_token(token: str) -> Optional[str]:
    """Return actor id if `token` is a valid platform JWT with `platform-admin` role."""
    try:
        unverified = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return None
    kid = unverified.get("kid")
    jwks = await _platform_jwks()
    keys = jwks.get("keys", [])
    matched = next((k for k in keys if k.get("kid") == kid), None)
    if matched is None:
        return None
    public_key = _jwk_to_pem(matched)
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[matched.get("alg") or "RS256"],
            audience=global_settings.platform_keycloak_client_id,
            options={"verify_aud": bool(global_settings.platform_keycloak_client_id)},
        )
    except jwt.PyJWTError:
        return None
    realm_roles = (payload.get("realm_access") or {}).get("roles") or []
    resource = (payload.get("resource_access") or {}).get(global_settings.platform_keycloak_client_id or "") or {}
    client_roles = resource.get("roles") or []
    if "platform-admin" not in realm_roles and "platform-admin" not in client_roles:
        return None
    return payload.get("preferred_username") or payload.get("sub") or "platform-admin"


async def verify_admin(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(_admin_basic),
) -> str:
    """Authorize an admin caller via HTTP Basic and/or platform Keycloak.

    Either credential grants access; both are checked. Returns actor identifier."""
    actor: Optional[str] = None

    if credentials is not None and global_settings.admin_password:
        ok_user = secrets.compare_digest(credentials.username, global_settings.admin_user)
        ok_pass = secrets.compare_digest(credentials.password, global_settings.admin_password)
        if ok_user and ok_pass:
            actor = credentials.username

    if actor is None:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer ") and global_settings.platform_keycloak_enabled:
            token = auth.split(" ", 1)[1].strip()
            actor = await _verify_platform_token(token)

    if actor is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": 'Basic, Bearer realm="platform"'},
        )

    request.state.user = actor
    return actor
