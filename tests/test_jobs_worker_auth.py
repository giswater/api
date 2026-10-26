"""Tests for the service-account token helper."""

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
        keycloak_client_id="giswater-api",
        keycloak_client_secret="secret",
    )
    for key, value in overrides.items():
        setattr(settings, key, value)
    return SimpleNamespace(id="test", settings=settings)


def setup_function() -> None:
    worker_auth.reset_cache()


def test_worker_token_configured_true_when_all_present():
    assert worker_auth.worker_token_configured(_tenant()) is True


def test_worker_token_configured_false_when_missing_secret():
    assert worker_auth.worker_token_configured(_tenant(keycloak_client_secret=None)) is False


def test_get_worker_token_raises_when_not_configured():
    tenant = _tenant(keycloak_client_id=None)
    with pytest.raises(WorkerAuthError, match="KEYCLOAK_CLIENT"):
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


def test_service_account_token_source_refreshes_on_demand(monkeypatch):
    request = AsyncMock(side_effect=[("tok-1", 3600.0), ("tok-2", 3600.0)])
    monkeypatch.setattr(worker_auth, "_request_token", request)
    tenant = _tenant()
    source = worker_auth.service_account_token_source(tenant)

    async def _run():
        first = await source()
        cached = await source()
        refreshed = await source(force_refresh=True)
        return first, cached, refreshed

    first, cached, refreshed = asyncio.run(_run())
    assert (first, cached, refreshed) == ("tok-1", "tok-1", "tok-2")
    assert request.await_count == 2


def test_request_token_uses_client_credentials(monkeypatch):
    captured: dict = {}

    class _Response:
        status_code = 200

        def json(self):
            return {"access_token": "tok-cc", "expires_in": 60}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, data):
            captured["url"] = url
            captured["data"] = data
            return _Response()

    monkeypatch.setattr(worker_auth.httpx, "AsyncClient", _Client)
    token = asyncio.run(worker_auth.get_worker_token(_tenant()))

    assert token == "tok-cc"
    assert captured["url"] == "http://kc/realms/realm/protocol/openid-connect/token"
    assert captured["data"] == {
        "grant_type": "client_credentials",
        "client_id": "giswater-api",
        "client_secret": "secret",
    }


def test_request_token_prefers_worker_client(monkeypatch):
    captured: dict = {}

    class _Response:
        status_code = 200

        def json(self):
            return {"access_token": "tok-worker", "expires_in": 60}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, data):
            captured["data"] = data
            return _Response()

    monkeypatch.setattr(worker_auth.httpx, "AsyncClient", _Client)
    tenant = _tenant(worker_keycloak_client_id="giswater-worker", worker_keycloak_client_secret="wsecret")
    token = asyncio.run(worker_auth.get_worker_token(tenant))

    assert token == "tok-worker"
    assert captured["data"]["client_id"] == "giswater-worker"
