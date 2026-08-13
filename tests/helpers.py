"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi.testclient import TestClient

from app.core.constants import GLOBAL_HEALTH_PATH, TENANT_PREFIX_V1, TENANT_PREFIX_V2


def api(path: str) -> str:
    """Build path under the tenant API prefix (mounted at `${API_ROOT}/v1`, default `/giswater/v1`)."""
    if not path.startswith("/"):
        path = "/" + path
    return TENANT_PREFIX_V1 + path


def api_v2(path: str) -> str:
    """Build path under the v2 tenant API prefix (mounted at `${API_ROOT}/v2`, default `/giswater/v2`)."""
    if not path.startswith("/"):
        path = "/" + path
    return TENANT_PREFIX_V2 + path


def assert_ready(client: TestClient) -> None:
    health_r = client.get(GLOBAL_HEALTH_PATH)
    assert health_r.status_code == 200, health_r.text
    health = health_r.json()
    assert health.get("status") == "ok", f"Health check failed: {health}"
    ready_r = client.get(api("/ready"))
    assert ready_r.status_code == 200, ready_r.text
    ready = ready_r.json()
    assert ready.get("status") == "ready", f"Ready check failed: {ready}"
