"""Service-account auth for background jobs.

Jobs act as a Keycloak service account instead of persisting the end user's
bearer token. ``client_credentials`` uses ``WORKER_KEYCLOAK_CLIENT_ID`` /
``WORKER_KEYCLOAK_CLIENT_SECRET`` when set, otherwise the tenant API client.
Outbound calls that require that token keep the service-account token.

Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
import threading
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
_cache_lock = threading.Lock()


def worker_client_credentials(settings) -> tuple[str | None, str | None]:
    """Worker client id/secret, falling back to the tenant API client."""
    worker_id = getattr(settings, "worker_keycloak_client_id", None)
    worker_secret = getattr(settings, "worker_keycloak_client_secret", None)
    if worker_id and worker_secret:
        return worker_id, worker_secret
    return settings.keycloak_client_id, settings.keycloak_client_secret


def worker_token_configured(tenant) -> bool:
    """True when the tenant can request a service-account token."""
    s = tenant.settings
    client_id, client_secret = worker_client_credentials(s)
    return bool(s.keycloak_url and s.keycloak_realm and client_id and client_secret)


def _token_endpoint(tenant) -> str:
    base = tenant.settings.keycloak_url.rstrip("/")
    realm = tenant.settings.keycloak_realm
    return f"{base}/realms/{realm}/protocol/openid-connect/token"


def _cache_key(tenant) -> str:
    s = tenant.settings
    client_id, _secret = worker_client_credentials(s)
    return f"{tenant.id}:{s.keycloak_realm}:{client_id}"


async def get_worker_token(tenant, *, force_refresh: bool = False) -> str:
    """Cached ``client_credentials`` token for the worker client."""
    if not worker_token_configured(tenant):
        raise WorkerAuthError(
            f"Tenant '{tenant.id}' has no Keycloak client configured "
            "(WORKER_KEYCLOAK_CLIENT_ID / WORKER_KEYCLOAK_CLIENT_SECRET or KEYCLOAK_CLIENT_ID / KEYCLOAK_CLIENT_SECRET)"
        )

    key = _cache_key(tenant)
    if not force_refresh:
        cached = _read_cached(key)
        if cached is not None:
            return cached

    token, expires_in = await _request_token(tenant)
    _store(key, token, expires_in)
    return token


def service_account_token_source(tenant):
    """Callable that returns a fresh service-account token for ``tenant``.

    Downstream clients call this before every request. ``force_refresh=True``
    skips the cache (used after a downstream 401).
    """

    async def token(*, force_refresh: bool = False) -> str:
        return await get_worker_token(tenant, force_refresh=force_refresh)

    return token


def _read_cached(key: str) -> str | None:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached.expires_at > now:
            return cached.access_token
    return None


def _store(key: str, token: str, expires_in: float) -> None:
    expires_at = time.monotonic() + max(0.0, expires_in - _EXPIRY_SKEW_SECONDS)
    with _cache_lock:
        _cache[key] = _CachedToken(access_token=token, expires_at=expires_at)


async def _request_token(tenant) -> tuple[str, float]:
    client_id, client_secret = worker_client_credentials(tenant.settings)
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
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


def reset_cache() -> None:
    """Clear cached tokens (used by tests and on tenant reload)."""
    with _cache_lock:
        _cache.clear()
