"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

# Backward-compat tests for KEYCLOAK_ENABLED → AUTH_MODE shim.
# DEPRECATED #22: delete the legacy tests below when releasing 2.0.0 (grep DEPRECATED #22).

import warnings


from app.core.config import _build_tenant, _resolve_auth_mode
from app.auth.schemas import ApiUser
from app.db.context import DB_IDENTITY_CTX, DbIdentity, _resolve_db_identity


def test_resolve_auth_mode_explicit_none():
    assert _resolve_auth_mode({"AUTH_MODE": "none"}) == "none"


def test_resolve_auth_mode_explicit_basic():
    assert _resolve_auth_mode({"AUTH_MODE": "basic"}) == "basic"


# DEPRECATED #22: remove in 2.0.0
def test_resolve_auth_mode_keycloak_enabled_legacy():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert _resolve_auth_mode({"KEYCLOAK_ENABLED": "true"}) == "keycloak"
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_resolve_auth_mode_default_none():
    assert _resolve_auth_mode({}) == "none"


# DEPRECATED #22: remove in 2.0.0
def test_build_tenant_auth_mode_from_keycloak_enabled():
    settings = _build_tenant({"KEYCLOAK_ENABLED": "true", "KEYCLOAK_URL": "https://auth.example.com"})
    assert settings.auth_mode == "keycloak"
    assert settings.keycloak_enabled is True


def test_api_user_roles():
    user = ApiUser(
        sub="1",
        preferred_username="alice",
        auth_method="basic",
        roles=frozenset({"basic", "edit"}),
        db_role="postgres",
    )
    assert user.has_role("edit")
    assert user.has_any_role(["om", "edit"])
    assert not user.has_role("system")


def test_api_user_anonymous():
    user = ApiUser.anonymous()
    assert user.is_anonymous
    assert not user.roles


def test_resolve_db_identity_without_context():
    assert _resolve_db_identity() is None
    assert _resolve_db_identity("alice") == "alice"
    assert _resolve_db_identity("alice", "postgres") == "postgres"


def test_resolve_db_identity_from_context():
    token = DB_IDENTITY_CTX.set(DbIdentity(username="alice", db_role="postgres"))
    try:
        assert _resolve_db_identity() == "postgres"
        assert _resolve_db_identity("anonymous") == "postgres"
        assert _resolve_db_identity("bob") == "bob"
        assert _resolve_db_identity("alice") == "postgres"
        assert _resolve_db_identity("alice", "other") == "other"
    finally:
        DB_IDENTITY_CTX.reset(token)
