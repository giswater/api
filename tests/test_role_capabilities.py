"""Capability role names and require_capability."""

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.schemas import ApiUser
from app.auth.session import get_current_user, require_capability
from app.core.config import CAPABILITIES, TenantSettings, _build_tenant, normalize_role_names
from app.schemas.admin import DbSettingsIn, TenantIn, TenantOut, build_tenant_settings_from_input
from app.tenancy.registry import serialize_tenant_settings


def _default_roles() -> dict[str, str]:
    return {cap.id: cap.default for cap in CAPABILITIES}


def test_normalize_and_build_tenant_roles():
    assert normalize_role_names(None, default="epa") == "epa"
    assert normalize_role_names(" , ", default="epa") == "epa"
    assert normalize_role_names(" epa-role , epa ", default="epa") == "epa-role,epa"
    settings = _build_tenant({"ROLE_EPA": "epa-role", "ROLE_PLAN": "planning"})
    assert settings.role_names("epa") == frozenset({"epa-role"})
    assert settings.role_names("plan") == frozenset({"planning"})
    bare = _build_tenant({})
    for cap in CAPABILITIES:
        assert bare.role_names(cap.id) == frozenset({cap.default})
        assert getattr(bare, cap.field) == cap.default


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


def test_plan_allowed_with_default_role():
    assert _client(_user("plan"), capability="plan").post("/epa").status_code == 200


def test_plan_forbidden_without_role():
    assert _client(_user("epa"), capability="plan").post("/epa").status_code == 403


def test_epa_skipped_for_anonymous():
    assert _client(_user(anonymous=True)).post("/epa").status_code == 200


def test_unknown_capability_fails_closed():
    assert _client(_user("epa"), capability="nope").post("/epa").status_code == 500


def test_admin_round_trip_roles():
    payload = TenantIn(db=DbSettingsIn(password="secret"), roles={"epa": " epa-role ", "plan": "planning"})
    created = build_tenant_settings_from_input(payload)
    assert created.role_epa == "epa-role"
    assert created.role_plan == "planning"
    assert created.role_basic == "basic"

    kept = build_tenant_settings_from_input(TenantIn(db=DbSettingsIn(password="secret")), existing=created)
    assert kept.role_epa == "epa-role"
    assert kept.role_plan == "planning"
    assert kept.role_om == "om"

    reset = build_tenant_settings_from_input(
        TenantIn(db=DbSettingsIn(password="secret"), roles={"epa": ""}),
        existing=created,
    )
    assert reset.role_epa == "epa"
    assert reset.role_plan == "planning"

    ignored = build_tenant_settings_from_input(
        TenantIn(db=DbSettingsIn(password="secret"), roles={"crm": "crm-role"}),
        existing=created,
    )
    assert ignored.role_epa == "epa-role"
    assert ignored.role_plan == "planning"

    body = serialize_tenant_settings(created)
    assert "ROLE_BASIC=basic" in body
    assert "ROLE_EPA=epa-role" in body
    assert "ROLE_PLAN=planning" in body
    assert "ROLE_SYSTEM=system" in body

    tenant = SimpleNamespace(id="acme", settings=created, db_manager=SimpleNamespace(connection_pool=None))
    assert TenantOut.from_tenant(tenant).roles == {  # type: ignore[arg-type]
        **_default_roles(),
        "epa": "epa-role",
        "plan": "planning",
    }
