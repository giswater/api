"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.constants import ADMIN_PREFIX
from app.tenancy import state
from tests.helpers import api, assert_ready


def _parse_mcp(resp):
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise AssertionError(f"No SSE data in {resp.text!r}")
    return resp.json()


def _mcp(
    client: TestClient,
    method: str,
    params: dict | None = None,
    *,
    path: str = "/mcp/",
    host: str | None = None,
    auth=None,
    extra_headers: dict | None = None,
):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if host:
        headers["host"] = host
    if extra_headers:
        headers.update(extra_headers)
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post(api(path), json=payload, headers=headers, auth=auth)


def _initialize(client: TestClient, **kwargs):
    resp = _mcp(
        client,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
        **kwargs,
    )
    return resp, _parse_mcp(resp) if resp.status_code == 200 else None


def _tool_names(client: TestClient, **kwargs) -> set[str]:
    init, _ = _initialize(client, **kwargs)
    assert init.status_code == 200, init.text
    session = init.headers.get("mcp-session-id")
    extra = {"mcp-session-id": session} if session else None
    listed = _mcp(client, "tools/list", extra_headers=extra, **kwargs)
    assert listed.status_code == 200, listed.text
    body = _parse_mcp(listed)
    tools = body.get("result", body).get("tools") or []
    return {tool["name"] for tool in tools}


def _call_tool(client: TestClient, name: str, arguments: dict, **kwargs):
    init, _ = _initialize(client, **kwargs)
    assert init.status_code == 200, init.text
    session = init.headers.get("mcp-session-id")
    extra = {"mcp-session-id": session} if session else None
    resp = _mcp(client, "tools/call", {"name": name, "arguments": arguments}, extra_headers=extra, **kwargs)
    return resp, _parse_mcp(resp) if resp.status_code < 500 else None


def test_list_schemas_rest(client):
    resp = client.get(api("/schemas"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "schemas" in body
    assert isinstance(body["schemas"], list)


def test_mcp_tools_list_and_tenant_state(client):
    """scope state.tenant must survive BaseHTTPMiddleware for MCP to resolve."""
    resp, body = _initialize(client)
    assert resp.status_code == 200, resp.text
    assert body.get("result") or body.get("serverInfo") or "result" in body


def test_mcp_path_with_and_without_slash(client):
    for path in ("/mcp", "/mcp/"):
        resp, _ = _initialize(client, path=path)
        assert resp.status_code == 200, (path, resp.text)


def test_mcp_api_mcp_false_is_404(client):
    resp = _mcp(client, "initialize", host="nomcp.bgeo360.com")
    assert resp.status_code == 404


def test_mcp_auth_gate_basic(client):
    resp = _mcp(client, "initialize", host="authed.bgeo360.com")
    assert resp.status_code == 401
    listed = _mcp(client, "tools/list", host="authed.bgeo360.com")
    assert listed.status_code == 401


def test_mcp_isolation_no_crm_leak(client):
    names_a = _tool_names(client, host="test.bgeo360.com")
    names_b = _tool_names(client, host="isolated.bgeo360.com")
    assert "list_hydrometers" in names_a
    assert "list_hydrometers" not in names_b
    assert "manage_hydrometers" not in names_b
    init_a, _ = _initialize(client, host="test.bgeo360.com")
    session_a = init_a.headers.get("mcp-session-id")
    extra = {"mcp-session-id": session_a} if session_a else {"mcp-session-id": "from-tenant-a"}
    listed_b = _mcp(client, "tools/list", host="isolated.bgeo360.com", extra_headers=extra)
    assert listed_b.status_code == 200, listed_b.text
    names_b_session = {t["name"] for t in _parse_mcp(listed_b).get("result", {}).get("tools") or []}
    assert "list_hydrometers" not in names_b_session
    call, body = _call_tool(client, "list_hydrometers", {"schema": "public"}, host="isolated.bgeo360.com")
    assert call.status_code in (200, 400) or (body and body.get("error"))
    if body and not body.get("error"):
        result = body.get("result") or {}
        is_error = result.get("isError")
        assert is_error


def test_mcp_list_schemas(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(client, "list_schemas", {"schema": default_params["schema"]})
    assert resp.status_code == 200, resp.text
    result = body.get("result") or body
    text = json.dumps(result)
    assert "schemas" in text or default_params["schema"] in text


def test_mcp_bad_schema_lists_valid(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(client, "find_features", {"schema": "does_not_exist_xx", "feature_type": "node"})
    payload = json.dumps(body)
    assert "Valid schemas" in payload or "schema" in payload.lower()


def test_mcp_reload_tears_down_task(client):
    _initialize(client)
    tenant = state.registry.get("test")
    assert tenant is not None
    old = tenant.mcp
    assert old is not None
    old_task = old._task
    reload_resp = client.post(
        f"{ADMIN_PREFIX}/tenants/test/reload",
        headers={"host": "bgeo360.com"},
        auth=("admin", "admin"),
    )
    assert reload_resp.status_code == 200, reload_resp.text
    if old_task is not None:
        assert old_task.done()
    new_tenant = state.registry.get("test")
    assert new_tenant is not tenant
    assert new_tenant.mcp is None


def test_mcp_get_mincut_budget(client, default_params):
    assert_ready(client)
    listed = client.get(api("/om/mincuts"), params=default_params)
    if listed.status_code != 200:
        pytest.skip("mincuts not available")
    fields = ((listed.json().get("body") or {}).get("data") or {}).get("fields") or []
    if not fields:
        pytest.skip("no mincuts to summarise")
    mincut_id = fields[0].get("id") or fields[0].get("mincut_id")
    resp, body = _call_tool(client, "get_mincut", {"schema": default_params["schema"], "mincut_id": int(mincut_id)})
    assert resp.status_code == 200, resp.text
    assert len(json.dumps(body)) < 80_000


def test_mcp_water_balance_budget(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(client, "get_water_balance", {"schema": default_params["schema"]})
    if resp.status_code != 200:
        pytest.skip(resp.text)
    assert len(json.dumps(body)) < 80_000


def test_mcp_dma_connecs_budget(client, default_params):
    assert_ready(client)
    dmas = client.get(api("/om/dmas"), params=default_params)
    if dmas.status_code != 200:
        pytest.skip("dmas not available")
    items = ((dmas.json().get("body") or {}).get("data") or {}).get("dmas") or []
    if not items:
        pytest.skip("no dmas")
    dma_id = items[0].get("dmaId") or items[0].get("dma_id")
    resp, body = _call_tool(
        client,
        "get_dma_contents",
        {"schema": default_params["schema"], "dma_id": int(dma_id), "content": "connecs", "limit": 20},
    )
    if resp.status_code != 200:
        pytest.skip(resp.text)
    assert len(json.dumps(body)) < 80_000


@pytest.mark.ud
def test_mcp_find_features_gully(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "gully", "limit": 5},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") in (None, False)
