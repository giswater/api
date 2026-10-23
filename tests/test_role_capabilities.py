"""Capability role names and require_capability('epa')."""

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.schemas import ApiUser
from app.auth.session import get_current_user, require_capability
from app.core.config import TenantSettings, _build_tenant, normalize_role_names
from app.schemas.admin import DbSettingsIn, TenantIn, TenantOut, build_tenant_settings_from_input
from app.tenancy.registry import serialize_tenant_settings


def test_normalize_and_build_tenant_role_epa():
    assert normalize_role_names(None, default="epa") == "epa"
    assert normalize_role_names(" , ", default="epa") == "epa"
    assert normalize_role_names(" epa-role , epa ", default="epa") == "epa-role,epa"
    settings = _build_tenant({"ROLE_EPA": "epa-role"})
    assert settings.role_names("epa") == frozenset({"epa-role"})
    assert _build_tenant({}).role_names("epa") == frozenset({"epa"})


def test_unknown_capability_raises():
    try:
        TenantSettings().role_names("run_model")
    except KeyError as exc:
        assert exc.args == ("run_model",)
    else:
        raise AssertionError("expected KeyError")


def _user(*roles: str, anonymous: bool = False) -> ApiUser:
    if anonymous:
        return ApiUser.anonymous()
    return ApiUser(
        sub="user",
        preferred_username="user",
        auth_method="keycloak",
        roles=frozenset(roles),
    )


def _client(user: ApiUser, *, capability: str = "epa", settings: TenantSettings | None = None, tenant=True):
    app = FastAPI()

    @app.middleware("http")
    async def _tenant(request, call_next):
        if tenant:
            request.state.tenant = SimpleNamespace(settings=settings or TenantSettings())
        return await call_next(request)

    @app.post("/epa", dependencies=[Depends(require_capability(capability))])
    async def epa():
        return {"ok": True}

    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_epa_forbidden_without_role():
    response = _client(_user()).post("/epa")
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


def test_epa_allowed_with_default_role():
    assert _client(_user("epa")).post("/epa").status_code == 200


def test_epa_uses_renamed_role():
    settings = TenantSettings(role_epa="epa-role,legacy")
    assert _client(_user("epa"), settings=settings).post("/epa").status_code == 403
    assert _client(_user("legacy"), settings=settings).post("/epa").status_code == 200


def test_epa_skipped_for_anonymous():
    assert _client(_user(anonymous=True)).post("/epa").status_code == 200


def test_unknown_capability_fails_closed():
    assert _client(_user("epa"), capability="nope").post("/epa").status_code == 500


def test_admin_round_trip_role_epa():
    payload = TenantIn(db=DbSettingsIn(password="secret"), roles={"epa": " epa-role "})
    created = build_tenant_settings_from_input(payload)
    assert created.role_epa == "epa-role"

    kept = build_tenant_settings_from_input(TenantIn(db=DbSettingsIn(password="secret")), existing=created)
    assert kept.role_epa == "epa-role"

    reset = build_tenant_settings_from_input(
        TenantIn(db=DbSettingsIn(password="secret"), roles={"epa": ""}),
        existing=created,
    )
    assert reset.role_epa == "epa"
    assert "ROLE_EPA=epa-role" in serialize_tenant_settings(created)

    tenant = SimpleNamespace(id="acme", settings=created, db_manager=SimpleNamespace(connection_pool=None))
    assert TenantOut.from_tenant(tenant).roles == {"epa": "epa-role"}  # type: ignore[arg-type]
