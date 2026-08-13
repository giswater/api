"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import os
import subprocess
import sys
import textwrap

import pytest

from app.core.config import _normalize_api_root
from app.core.constants import ADMIN_PREFIX, API_ROOT, GLOBAL_HEALTH_PATH, STATIC_PREFIX, TENANT_PREFIX_V1, TENANT_PREFIX_V2


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "/giswater"),
        ("", "/giswater"),
        ("   ", "/giswater"),
        ("giswater", "/giswater"),
        ("/giswater", "/giswater"),
        ("/giswater/", "/giswater"),
        ("/gw-api", "/gw-api"),
        ("/Some/Nested/Root", "/Some/Nested/Root"),
    ],
)
def test_normalize_api_root_accepts(raw, expected):
    assert _normalize_api_root(raw) == expected


@pytest.mark.parametrize("bad", ["/", "//", "/foo//bar", "/foo bar", "/foo?x", "/foo#x", "/foo/../bar"])
def test_normalize_api_root_rejects(bad):
    with pytest.raises(ValueError):
        _normalize_api_root(bad)


def test_default_prefixes_are_under_giswater():
    """With no override (conftest does not set API_ROOT), the default is /giswater."""
    assert API_ROOT == "/giswater"
    assert TENANT_PREFIX_V1 == "/giswater/v1"
    assert TENANT_PREFIX_V2 == "/giswater/v2"
    assert ADMIN_PREFIX == "/giswater/admin"
    assert GLOBAL_HEALTH_PATH == "/giswater/health"
    assert STATIC_PREFIX == "/giswater/static"


def test_logs_ui_html_uses_resolved_static_prefix():
    from app.api.v1.endpoints import system

    assert "/giswater/static/css/logs.css" in system._LOGS_UI_HTML
    assert "/giswater/static/js/logs.js" in system._LOGS_UI_HTML
    assert "__STATIC_PREFIX__" not in system._LOGS_UI_HTML


def test_api_root_override_reroutes_app(tmp_path):
    """In a fresh process with API_ROOT=/gw-api, the app exposes legacy URLs."""
    script = textwrap.dedent(
        """
        import os, sys, json
        os.environ["API_ROOT"] = "/gw-api"
        os.environ.setdefault("BASE_DOMAIN", "bgeo360.com")
        os.environ.setdefault("TENANTS_DIR", "tests/fixtures/tenants")
        os.environ.setdefault("ADMIN_USER", "admin")
        os.environ.setdefault("ADMIN_PASSWORD", "admin")
        os.environ.setdefault("LOG_DB_ENABLED", "false")
        os.environ.setdefault("GISWATER_DB_VERSION_CHECK", "false")

        from fastapi.testclient import TestClient
        from app.core.constants import ADMIN_PREFIX, GLOBAL_HEALTH_PATH, TENANT_PREFIX_V1, TENANT_PREFIX_V2
        from app.main import app

        with TestClient(app, base_url="http://test.bgeo360.com") as c:
            r1 = c.get(GLOBAL_HEALTH_PATH)
            r2 = c.get(f"{TENANT_PREFIX_V1}/health")
            r2b = c.get(f"{TENANT_PREFIX_V2}/health")
            r3 = c.get(
                f"{ADMIN_PREFIX}/health",
                headers={"host": "bgeo360.com"},
                auth=("admin", "admin"),
            )
            # Default /giswater should NOT be served when API_ROOT is /gw-api.
            r4 = c.get("/giswater/health")

        out = {
            "tenant_prefix_v1": TENANT_PREFIX_V1,
            "tenant_prefix_v2": TENANT_PREFIX_V2,
            "admin_prefix": ADMIN_PREFIX,
            "health_path": GLOBAL_HEALTH_PATH,
            "global_health": r1.status_code,
            "tenant_health": r2.status_code,
            "tenant_v2_health": r2b.status_code,
            "admin_health": r3.status_code,
            "giswater_health": r4.status_code,
        }
        print(json.dumps(out))
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
    import json

    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["tenant_prefix_v1"] == "/gw-api/v1"
    assert data["tenant_prefix_v2"] == "/gw-api/v2"
    assert data["admin_prefix"] == "/gw-api/admin"
    assert data["health_path"] == "/gw-api/health"
    assert data["global_health"] == 200
    assert data["tenant_health"] == 200
    assert data["tenant_v2_health"] == 200
    assert data["admin_health"] == 200
    assert data["giswater_health"] == 404
