"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest


def _run_subprocess(script: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: {proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


# Boilerplate env that mirrors tests/conftest.py but with a fixed tenants
# fixture dir. `SINGLE_TENANT_ID` is set per test via the placeholder.
_PRELUDE = """
import os, json
os.environ["SINGLE_TENANT_ID"] = {single!r}
os.environ.setdefault("BASE_DOMAIN", "bgeo360.com")
os.environ.setdefault("TENANTS_DIR", "tests/fixtures/tenants")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")
os.environ.setdefault("LOG_DB_ENABLED", "false")
os.environ.setdefault("GISWATER_DB_VERSION_CHECK", "false")

from fastapi.testclient import TestClient
from app.core.constants import ADMIN_PREFIX, GLOBAL_HEALTH_PATH, TENANT_PREFIX_V1, TENANT_PREFIX_V2
from app.main import app
"""


def test_single_tenant_serves_tenant_routes_by_ip():
    """`/v1` and `/v2` health work on a bare IP host with no DNS and no X-Tenant-ID."""
    script = textwrap.dedent(
        _PRELUDE.format(single="test")
        + """
with TestClient(app, base_url="http://127.0.0.1") as c:
    r_tenant = c.get(f"{TENANT_PREFIX_V1}/health")
    r_tenant_v2 = c.get(f"{TENANT_PREFIX_V2}/health")
    r_global = c.get(GLOBAL_HEALTH_PATH)

print(json.dumps({
    "tenant_health": r_tenant.status_code,
    "tenant_v2_health": r_tenant_v2.status_code,
    "global_health": r_global.status_code,
}))
"""
    )
    data = _run_subprocess(script)
    assert data["tenant_health"] == 200
    assert data["tenant_v2_health"] == 200
    assert data["global_health"] == 200


def test_single_tenant_admin_reachable_by_ip():
    """`/admin/health` works on a bare IP host (no apex `BASE_DOMAIN` required)."""
    script = textwrap.dedent(
        _PRELUDE.format(single="test")
        + """
with TestClient(app, base_url="http://127.0.0.1") as c:
    r = c.get(f"{ADMIN_PREFIX}/health", auth=("admin", "admin"))

print(json.dumps({"admin_health": r.status_code}))
"""
    )
    data = _run_subprocess(script)
    assert data["admin_health"] == 200


def test_single_tenant_ignores_hostile_host_header():
    """A wrong/hostile Host does not change which tenant is used."""
    script = textwrap.dedent(
        _PRELUDE.format(single="test")
        + """
with TestClient(app, base_url="http://attacker.example.com") as c:
    r = c.get(f"{TENANT_PREFIX_V1}/health", headers={"host": "evil.example.com"})

print(json.dumps({"status": r.status_code}))
"""
    )
    data = _run_subprocess(script)
    assert data["status"] == 200


def test_single_tenant_missing_returns_unknown_tenant():
    """If `SINGLE_TENANT_ID` points at a tenant that is not loaded, return 404."""
    script = textwrap.dedent(
        _PRELUDE.format(single="missingtenant")
        + """
with TestClient(app, base_url="http://127.0.0.1") as c:
    r = c.get(f"{TENANT_PREFIX_V1}/health")

print(json.dumps({"status": r.status_code, "detail": r.json().get("detail")}))
"""
    )
    data = _run_subprocess(script)
    assert data["status"] == 404
    assert data["detail"] == "Unknown tenant 'missingtenant'"


def test_single_tenant_dns_mode_unchanged_when_unset():
    """With `SINGLE_TENANT_ID` unset, DNS-based routing behavior is preserved."""
    script = textwrap.dedent(
        _PRELUDE.format(single="")
        + """
with TestClient(app, base_url="http://test.bgeo360.com") as c:
    r_tenant = c.get(f"{TENANT_PREFIX_V1}/health")
    r_apex_tenant = c.get(f"{TENANT_PREFIX_V1}/health", headers={"host": "bgeo360.com"})
    r_admin_subdomain = c.get(
        f"{ADMIN_PREFIX}/health",
        headers={"host": "test.bgeo360.com"},
        auth=("admin", "admin"),
    )
    r_admin_apex = c.get(
        f"{ADMIN_PREFIX}/health",
        headers={"host": "bgeo360.com"},
        auth=("admin", "admin"),
    )

print(json.dumps({
    "tenant_via_subdomain": r_tenant.status_code,
    "tenant_on_apex": r_apex_tenant.status_code,
    "admin_on_subdomain": r_admin_subdomain.status_code,
    "admin_on_apex": r_admin_apex.status_code,
}))
"""
    )
    data = _run_subprocess(script)
    assert data["tenant_via_subdomain"] == 200
    assert data["tenant_on_apex"] == 404
    assert data["admin_on_subdomain"] == 404
    assert data["admin_on_apex"] == 200


@pytest.mark.parametrize("bad", ["api", "admin", "localhost", "FOO", "-bad", "a/b"])
def test_single_tenant_id_invalid_or_reserved_fails_fast(bad):
    """Reserved or malformed `SINGLE_TENANT_ID` values are rejected at config load."""
    script = textwrap.dedent(
        f"""
import os, json, sys
os.environ["SINGLE_TENANT_ID"] = {bad!r}
try:
    from app.core.config import load_global_settings
    load_global_settings()
    print(json.dumps({{"ok": True}}))
except ValueError as exc:
    print(json.dumps({{"ok": False, "error": str(exc)}}))
"""
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: {proc.stderr}"
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["ok"] is False, f"expected rejection for {bad!r}"
