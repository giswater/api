"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.constants import TENANT_PREFIX
from app.main import app

_BUSINESS_PATH = "/basic/getlist"
_LOGS_PATH = "/logs"


def _read_test_env_template() -> list[str]:
    tenants_dir = Path(os.environ["TENANTS_DIR"])
    return [line for line in (tenants_dir / "test.env").read_text().splitlines() if not line.startswith("AUTH_MODE=")]


def _write_tenant_env(tenant_id: str, auth_mode: str) -> None:
    lines = _read_test_env_template()
    lines.append(f"AUTH_MODE={auth_mode}")
    if auth_mode == "keycloak":
        lines.extend(
            [
                "KEYCLOAK_URL=https://auth.example.com",
                "KEYCLOAK_REALM=acme",
                "KEYCLOAK_CLIENT_ID=giswater-api",
                "KEYCLOAK_CLIENT_SECRET=secret",
                "KEYCLOAK_ADMIN_CLIENT_ID=giswater-api-admin",
                "KEYCLOAK_ADMIN_CLIENT_SECRET=admin-secret",
                "KEYCLOAK_CALLBACK_URI=https://example.com/callback",
            ]
        )
    tenants_dir = Path(os.environ["TENANTS_DIR"])
    (tenants_dir / f"{tenant_id}.env").write_text("\n".join(lines) + "\n")


def _remove_tenant(tenant_id: str) -> None:
    path = Path(os.environ["TENANTS_DIR"]) / f"{tenant_id}.env"
    if path.exists():
        path.unlink()


def _fetch_openapi(client: TestClient, host: str) -> dict:
    response = client.get(f"{TENANT_PREFIX}/openapi.json", headers={"Host": host})
    assert response.status_code == 200
    return response.json()


def _operation_security(schema: dict, path: str, method: str = "get") -> list[dict] | None:
    return schema["paths"][path][method].get("security")


@pytest.fixture
def openapi_client(default_headers: dict[str, str]):
    with TestClient(app, headers=default_headers) as client:
        yield client


@pytest.fixture
def basic_openapi_client(default_headers: dict[str, str]):
    _write_tenant_env("basic", "basic")
    with TestClient(app, headers=default_headers) as client:
        yield client
    _remove_tenant("basic")


@pytest.fixture
def keycloak_openapi_client(default_headers: dict[str, str]):
    _write_tenant_env("kc", "keycloak")
    with TestClient(app, headers=default_headers) as client:
        yield client
    _remove_tenant("kc")


def test_openapi_none_mode_has_admin_basic_only(openapi_client: TestClient):
    schema = _fetch_openapi(openapi_client, "test.bgeo360.com")
    schemes = schema["components"]["securitySchemes"]

    assert "tenantBasic" not in schemes
    assert schemes["adminBasic"]["scheme"] == "basic"
    assert _operation_security(schema, _BUSINESS_PATH) is None
    assert _operation_security(schema, _LOGS_PATH) == [{"adminBasic": []}]
    assert "/auth/token" not in schema["paths"]


def test_openapi_basic_mode(basic_openapi_client: TestClient):
    schema = _fetch_openapi(basic_openapi_client, "basic.bgeo360.com")
    schemes = schema["components"]["securitySchemes"]

    assert schemes["tenantBasic"] == {"type": "http", "scheme": "basic"}
    assert schemes["adminBasic"]["scheme"] == "basic"
    assert _operation_security(schema, _BUSINESS_PATH) == [{"tenantBasic": []}]
    assert _operation_security(schema, _LOGS_PATH) == [{"adminBasic": []}]
    assert "/auth/token" not in schema["paths"]


def test_openapi_keycloak_mode(keycloak_openapi_client: TestClient):
    schema = _fetch_openapi(keycloak_openapi_client, "kc.bgeo360.com")
    schemes = schema["components"]["securitySchemes"]
    token_path = "/auth/token"

    assert "keycloakPassword" in schemes
    assert "keycloakAuthCode" in schemes
    assert "tenantBasic" not in schemes

    password_flow = schemes["keycloakPassword"]["flows"]["password"]
    auth_code_flow = schemes["keycloakAuthCode"]["flows"]["authorizationCode"]
    assert password_flow["tokenUrl"] == f"{TENANT_PREFIX}/auth/token"
    assert auth_code_flow["tokenUrl"] == f"{TENANT_PREFIX}/auth/token"
    assert auth_code_flow["authorizationUrl"].endswith("/realms/acme/protocol/openid-connect/auth")

    business_security = _operation_security(schema, _BUSINESS_PATH)
    assert {"keycloakPassword": ["openid", "profile", "email"]} in business_security
    assert {"keycloakAuthCode": ["openid", "profile", "email"]} in business_security
    assert _operation_security(schema, _LOGS_PATH) == [{"adminBasic": []}]
    assert token_path in schema["paths"]
