"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.jobs.exceptions import WorkerAuthError

logger = logging.getLogger(__name__)

CONNECTION_ERRORS = (httpx.ConnectError, httpx.TimeoutException, OSError, ConnectionError)

_EXPIRY_SKEW_SECONDS = 30.0
_REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class _CachedToken:
    access_token: str
    expires_at: float


_cache: dict[str, _CachedToken] = {}
_locks: dict[str, asyncio.Lock] = {}


def worker_token_configured(tenant) -> bool:
    s = tenant.settings
    return bool(s.keycloak_url and s.keycloak_realm and s.worker_keycloak_client_id and s.worker_keycloak_client_secret)


def _token_endpoint(tenant) -> str:
    base = tenant.settings.keycloak_url.rstrip("/")
    realm = tenant.settings.keycloak_realm
    return f"{base}/realms/{realm}/protocol/openid-connect/token"


def _cache_key(tenant) -> str:
    s = tenant.settings
    return f"{tenant.id}:{s.keycloak_realm}:{s.worker_keycloak_client_id}"


async def get_worker_token(tenant, *, force_refresh: bool = False) -> str:
    if not worker_token_configured(tenant):
        raise WorkerAuthError(
            f"Tenant '{tenant.id}' has no worker service account configured "
            "(WORKER_KEYCLOAK_CLIENT_ID / WORKER_KEYCLOAK_CLIENT_SECRET)"
        )

    key = _cache_key(tenant)
    now = time.monotonic()
    if not force_refresh:
        cached = _cache.get(key)
        if cached is not None and cached.expires_at > now:
            return cached.access_token

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _cache.get(key)
        if not force_refresh and cached is not None and cached.expires_at > now:
            return cached.access_token

        token, expires_in = await _request_token(tenant)
        expires_at = time.monotonic() + max(0.0, expires_in - _EXPIRY_SKEW_SECONDS)
        _cache[key] = _CachedToken(access_token=token, expires_at=expires_at)
        return token


async def _request_token(tenant) -> tuple[str, float]:
    s = tenant.settings
    data = {
        "grant_type": "client_credentials",
        "client_id": s.worker_keycloak_client_id,
        "client_secret": s.worker_keycloak_client_secret,
    }
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(_token_endpoint(tenant), data=data)
    except CONNECTION_ERRORS as exc:
        raise WorkerAuthError(f"Keycloak unreachable for tenant '{tenant.id}': {exc}") from exc

    if resp.status_code != 200:
        raise WorkerAuthError(f"Keycloak token request failed for tenant '{tenant.id}' (status {resp.status_code})")

    body = resp.json()
    token = body.get("access_token")
    if not token:
        raise WorkerAuthError(f"Keycloak response missing access_token for tenant '{tenant.id}'")
    expires_in = float(body.get("expires_in", 0) or 0)
    return token, expires_in


async def ensure_worker_token_available(tenant) -> None:
    await get_worker_token(tenant)


def reset_cache() -> None:
    _cache.clear()
    _locks.clear()
