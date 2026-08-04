"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.constants import TENANT_PREFIX
from app.main import app
from app.tenancy import state

TOKEN_URL = f"{TENANT_PREFIX}/auth/token"


def _write_keycloak_tenant() -> None:
    tenants_dir = Path(os.environ["TENANTS_DIR"])
    base_lines = [
        line for line in (tenants_dir / "test.env").read_text().splitlines() if not line.startswith("AUTH_MODE=")
    ]
    base_lines.extend(
        [
            "AUTH_MODE=keycloak",
            "KEYCLOAK_URL=https://auth.example.com",
            "KEYCLOAK_REALM=acme",
            "KEYCLOAK_CLIENT_ID=giswater-api",
            "KEYCLOAK_CLIENT_SECRET=secret",
            "KEYCLOAK_ADMIN_CLIENT_ID=giswater-api-admin",
            "KEYCLOAK_ADMIN_CLIENT_SECRET=admin-secret",
            "KEYCLOAK_CALLBACK_URI=https://example.com/callback",
        ]
    )
    (tenants_dir / "kc.env").write_text("\n".join(base_lines) + "\n")
    assert state.registry is not None
    asyncio.run(state.registry.reload_one("kc"))


def _write_basic_tenant() -> None:
    tenants_dir = Path(os.environ["TENANTS_DIR"])
    base_lines = [
        line for line in (tenants_dir / "test.env").read_text().splitlines() if not line.startswith("AUTH_MODE=")
    ]
    base_lines.append("AUTH_MODE=basic")
    (tenants_dir / "basic.env").write_text("\n".join(base_lines) + "\n")
    assert state.registry is not None
    asyncio.run(state.registry.reload_one("basic"))


def _cleanup_extra_tenants() -> None:
    tenants_dir = Path(os.environ["TENANTS_DIR"])
    for tenant_id in ("kc", "basic"):
        path = tenants_dir / f"{tenant_id}.env"
        if path.exists():
            path.unlink()
    if state.registry is not None:
        asyncio.run(state.registry.reload())


@pytest.fixture
def token_client(default_headers: dict[str, str]):
    _write_keycloak_tenant()
    _write_basic_tenant()
    with TestClient(app, headers=default_headers) as client:
        yield client
    _cleanup_extra_tenants()


class _MockAsyncClient:
    def __init__(self, *, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, data=None, **kwargs):
        return await self._handler(url, data, **kwargs)


@pytest.fixture
def mock_keycloak_token(monkeypatch):
    captured: dict = {}

    async def handler(url: str, data: dict, **_kwargs):
        captured["url"] = url
        captured["data"] = dict(data)
        if data.get("username") == "bad":
            return httpx.Response(401, json={"error": "invalid_grant", "error_description": "Invalid user credentials"})
        return httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "Bearer", "expires_in": 300, "refresh_token": "ref"},
        )

    def factory(**_kwargs):
        return _MockAsyncClient(handler=handler)

    monkeypatch.setattr("app.api.v1.endpoints.auth.httpx.AsyncClient", factory)
    return captured


def test_token_proxy_password_grant_success(token_client: TestClient, mock_keycloak_token):
    response = token_client.post(
        TOKEN_URL,
        headers={"Host": "kc.bgeo360.com"},
        data={
            "grant_type": "password",
            "username": "alice",
            "password": "s3cret",
            "client_id": "ignored",
            "client_secret": "ignored",
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "tok"
    assert mock_keycloak_token["data"]["client_id"] == "giswater-api"
    assert mock_keycloak_token["data"]["client_secret"] == "secret"
    assert mock_keycloak_token["data"]["username"] == "alice"
    assert mock_keycloak_token["data"]["password"] == "s3cret"
    assert "ignored" not in mock_keycloak_token["data"].values()
    assert mock_keycloak_token["url"].endswith("/realms/acme/protocol/openid-connect/token")


def test_token_proxy_invalid_grant_passthrough(token_client: TestClient, mock_keycloak_token):
    response = token_client.post(
        TOKEN_URL,
        headers={"Host": "kc.bgeo360.com"},
        data={"grant_type": "password", "username": "bad", "password": "nope"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_grant"


def test_token_proxy_not_available_for_basic_tenant(token_client: TestClient):
    response = token_client.post(
        TOKEN_URL,
        headers={"Host": "basic.bgeo360.com"},
        data={"grant_type": "password", "username": "alice", "password": "s3cret"},
    )

    assert response.status_code == 404


def test_token_proxy_not_available_for_none_tenant(token_client: TestClient):
    response = token_client.post(
        TOKEN_URL,
        headers={"Host": "test.bgeo360.com"},
        data={"grant_type": "password", "username": "alice", "password": "s3cret"},
    )

    assert response.status_code == 404


def test_token_proxy_missing_username(token_client: TestClient, mock_keycloak_token):
    response = token_client.post(
        TOKEN_URL,
        headers={"Host": "kc.bgeo360.com"},
        data={"grant_type": "password", "password": "s3cret"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
