"""Tests for the worker service-account token helper."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.jobs import worker_auth
from app.jobs.exceptions import WorkerAuthError


def _tenant(**overrides):
    settings = SimpleNamespace(
        keycloak_url="http://kc",
        keycloak_realm="realm",
        worker_keycloak_client_id="giswater-worker",
        worker_keycloak_client_secret="secret",
    )
    for key, value in overrides.items():
        setattr(settings, key, value)
    return SimpleNamespace(id="test", settings=settings)


def setup_function() -> None:
    worker_auth.reset_cache()


def test_worker_token_configured_true_when_all_present():
    assert worker_auth.worker_token_configured(_tenant()) is True


def test_worker_token_configured_false_when_missing_secret():
    assert worker_auth.worker_token_configured(_tenant(worker_keycloak_client_secret=None)) is False


def test_get_worker_token_raises_when_not_configured():
    tenant = _tenant(worker_keycloak_client_id=None)
    with pytest.raises(WorkerAuthError):
        asyncio.run(worker_auth.get_worker_token(tenant))


def test_get_worker_token_caches_until_expiry(monkeypatch):
    request = AsyncMock(return_value=("tok-1", 3600.0))
    monkeypatch.setattr(worker_auth, "_request_token", request)
    tenant = _tenant()

    async def _run():
        first = await worker_auth.get_worker_token(tenant)
        second = await worker_auth.get_worker_token(tenant)
        return first, second

    first, second = asyncio.run(_run())
    assert first == "tok-1"
    assert second == "tok-1"
    request.assert_awaited_once()
