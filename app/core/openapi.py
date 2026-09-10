"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import logging

from app.tenancy.registry import Tenant

logger = logging.getLogger(__name__)

SCOPES = {"openid": "OpenID Connect", "profile": "User profile", "email": "User email"}
_SCOPE_NAMES = list(SCOPES.keys())
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})


def _tenant_security_requirements(auth_mode: str) -> list[dict[str, list[str]]]:
    if auth_mode == "none":
        return []
    if auth_mode == "basic":
        return [{"tenantBasic": []}]
    if auth_mode == "keycloak":
        return [
            {"keycloakPassword": _SCOPE_NAMES},
            {"keycloakAuthCode": _SCOPE_NAMES},
        ]
    return [{"tenantBasic": []}]


def _rewrite_operation_security(security: list[dict], replacement: list[dict[str, list[str]]]) -> list[dict]:
    out: list[dict] = []
    for requirement in security:
        if "tenantBasic" in requirement:
            out.extend(replacement)
        else:
            out.append(requirement)
    return out


def _keycloak_security_schemes(tenant: Tenant, root_path: str) -> dict[str, dict]:
    settings = tenant.settings
    if not (settings.keycloak_url and settings.keycloak_realm):
        logger.warning(
            "Tenant '%s' has AUTH_MODE=keycloak but Keycloak URL/realm is incomplete; skipping OAuth2 schemes",
            tenant.id,
        )
        return {}

    base = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect"
    token_url = f"{root_path}/auth/token"
    return {
        "keycloakPassword": {
            "type": "oauth2",
            "description": "Keycloak Direct Access Grant. Username/password of a realm or LDAP user.",
            "flows": {
                "password": {
                    "tokenUrl": token_url,
                    "refreshUrl": token_url,
                    "scopes": SCOPES,
                }
            },
        },
        "keycloakAuthCode": {
            "type": "oauth2",
            "description": (
                "Redirects to the Keycloak login page. Use this if your account has pending required actions or OTP."
            ),
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": f"{base}/auth",
                    "tokenUrl": token_url,
                    "refreshUrl": token_url,
                    "scopes": SCOPES,
                }
            },
        },
    }


def apply_tenant_security(schema: dict, tenant: Tenant, root_path: str) -> dict:
    """Rewrite OpenAPI security schemes and requirements for the tenant's auth mode."""
    auth_mode = tenant.settings.auth_mode
    replacement = _tenant_security_requirements(auth_mode)

    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            security = operation.get("security")
            if not isinstance(security, list):
                continue
            rewritten = _rewrite_operation_security(security, replacement)
            if rewritten:
                operation["security"] = rewritten
            else:
                operation.pop("security", None)

    components = schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})

    if auth_mode != "basic":
        schemes.pop("tenantBasic", None)

    if auth_mode == "keycloak":
        schemes.update(_keycloak_security_schemes(tenant, root_path))

    return schema
