"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import inspect
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


def _tool_data(body):
    result = (body or {}).get("result") or {}
    if result.get("structuredContent"):
        return result["structuredContent"]
    for item in result.get("content") or []:
        text = item.get("text")
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text, "isError": result.get("isError")}
    return result


def test_list_schemas_rest(client):
    resp = client.get(api("/schemas"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "schemas" in body
    assert isinstance(body["schemas"], list)
    for item in body["schemas"]:
        assert "schema" in item
        assert "project_type" in item or item.get("project_type") is None
        assert "giswater" in item or item.get("giswater") is None
        assert "epsg" in item


def test_profile_arc_omunit_optional():
    from app.schemas.om.profile_models import ArcModel

    row = ArcModel(
        arc_id=1,
        descript="{}",
        cat_geom1=0.15,
        length=1.0,
        z1=0,
        z2=0,
        y1=0,
        y2=0,
        elev1=1.0,
        elev2=1.0,
        node_1=1,
        node_2=2,
    )
    assert row.omunit_id is None
    assert (
        ArcModel(
            arc_id=1,
            descript="{}",
            cat_geom1=0.15,
            length=1.0,
            z1=0,
            z2=0,
            y1=0,
            y2=0,
            elev1=1.0,
            elev2=1.0,
            node_1=1,
            node_2=2,
            omunit_id=9,
        ).omunit_id
        == 9
    )


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
    resp, body = _call_tool(client, "list_schemas", {})
    assert resp.status_code == 200, resp.text
    data = _tool_data(body)
    assert "schemas" in data or default_params["schema"] in json.dumps(body)
    if isinstance(data, dict) and data.get("schemas"):
        item = data["schemas"][0]
        assert "schema" in item
        assert "epsg" in item


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


_EXPECTED_TOOLS = {
    "list_schemas",
    "list_hydrometers",
    "manage_hydrometers",
    "list_dscenarios",
    "list_dscenario_objects",
    "manage_dscenario",
    "manage_dscenario_objects",
    "find_features",
    "get_feature",
    "search",
    "get_feature_at_point",
    "list_mapzones",
    "get_dma_contents",
    "get_water_balance",
    "list_mincuts",
    "get_mincut",
    "list_mincut_valves",
    "create_mincut",
    "update_mincut",
    "toggle_mincut_valve",
    "set_mincut_state",
    "delete_mincut",
    "trace_flow",
    "get_profile",
}

_READ_ONLY = {
    "list_schemas",
    "list_hydrometers",
    "list_dscenarios",
    "list_dscenario_objects",
    "find_features",
    "get_feature",
    "search",
    "get_feature_at_point",
    "list_mapzones",
    "get_dma_contents",
    "get_water_balance",
    "list_mincuts",
    "get_mincut",
    "list_mincut_valves",
    "trace_flow",
    "get_profile",
}

_DESTRUCTIVE = {
    "manage_hydrometers",
    "manage_dscenario",
    "manage_dscenario_objects",
    "set_mincut_state",
    "delete_mincut",
}


def test_mcp_tool_inventory_and_annotations(client):
    names = _tool_names(client)
    assert names == _EXPECTED_TOOLS
    from app.mcp.registry import REGISTRY

    by_name = {spec.fn.__name__: spec.annotations for spec in REGISTRY}
    assert set(by_name) == _EXPECTED_TOOLS
    for name in _READ_ONLY:
        assert by_name[name]["readOnlyHint"] is True
        assert by_name[name]["idempotentHint"] is True
        assert by_name[name]["openWorldHint"] is True
    for name, annotations in by_name.items():
        if name not in _READ_ONLY:
            assert annotations["idempotentHint"] is False, name
            assert annotations["readOnlyHint"] is False, name
        if name in _DESTRUCTIVE:
            assert annotations["destructiveHint"] is True, name
        else:
            assert annotations["destructiveHint"] is False, name


def test_mcp_bind_hides_api_from_schema():
    from app.mcp.registry import REGISTRY

    spec = next(s for s in REGISTRY if s.fn.__name__ == "find_features")
    bound = spec.bind(object())
    assert "api" not in bound.__annotations__
    assert "api" not in inspect.signature(bound).parameters
    assert "schema" in inspect.signature(bound).parameters
    assert "feature_type" in inspect.signature(bound).parameters


def test_mcp_find_features_compact(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "limit": 3},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") in (None, False)
    data = _tool_data(body)
    items = data.get("items") or []
    if not items:
        pytest.skip("no nodes")
    row = items[0]
    assert "node_id" in row
    assert not any(key.endswith("_style") or key.endswith("_visibility") for key in row)
    full_resp, full_body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "limit": 1, "fields": "full"},
    )
    assert full_resp.status_code == 200, full_resp.text
    full_items = _tool_data(full_body).get("items") or []
    if full_items:
        assert len(full_items[0]) > len(row)
        assert "node_id" in full_items[0]
        coords = full_items[0].get("coordinates") or {}
        if "x" in row:
            assert row["x"] == coords.get("x") or row["x"] == full_items[0].get("x")


def test_mcp_partial_bbox_errors(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "x1": 1.0},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    assert "x1" in json.dumps(body) or "Bbox" in json.dumps(body)


def test_mcp_find_features_rejects_cross_type_filters(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "arc_type": ["PIPE"]},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    assert "arc_type" in json.dumps(body)


def test_mcp_get_profile(client, default_params):
    assert_ready(client)
    listed, listed_body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "limit": 2},
    )
    if listed.status_code != 200:
        pytest.skip(listed.text)
    items = _tool_data(listed_body).get("items") or []
    ids = [item.get("node_id") for item in items if item.get("node_id") is not None]
    if len(ids) < 2:
        pytest.skip("need two nodes for profile")
    resp, body = _call_tool(
        client,
        "get_profile",
        {
            "schema": default_params["schema"],
            "start_node_id": int(ids[0]),
            "end_node_id": int(ids[1]),
        },
    )
    payload = json.dumps(body)
    assert "omunit_id" not in payload.lower() or "field required" not in payload.lower()
    if resp.status_code != 200:
        pytest.skip(resp.text)
    result = (body or {}).get("result") or {}
    if result.get("isError"):
        pytest.skip(payload)


@pytest.mark.ws
def test_mcp_get_feature_at_point_ws(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "get_feature_at_point",
        {
            "schema": default_params["schema"],
            "x": 419487.25,
            "y": 4576484.26,
            "epsg": 25831,
        },
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") in (None, False)
    data = _tool_data(body)
    assert data.get("feature_id")
    keys = list(data)
    assert not any(k.startswith(("btn_", "tbl_", "hspacer_")) for k in keys)
    assert "fields" not in data


@pytest.mark.ud
def test_mcp_get_feature_at_point_ud(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "get_feature_at_point",
        {
            "schema": default_params["schema"],
            "x": 419433.85,
            "y": 4576570.45,
            "epsg": 25831,
        },
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") in (None, False)
    data = _tool_data(body)
    keys = list(data) if isinstance(data, dict) else []
    assert not any(k.startswith(("btn_", "tbl_", "hspacer_")) for k in keys)


def test_summarise_mincut_drops_feature_collections():
    from app.mcp.tools.mincut import _summarise_mincut

    raw = {
        "mincutId": 1,
        "mincutState": 0,
        "geometry": {"bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}},
        "info": {"descript": "x"},
        "mincutNode": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"node_id": 10},
                    "geometry": {"type": "Point", "coordinates": [1, 2]},
                }
            ],
        },
        "mincutArc": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"arc_id": 20},
                    "geometry": {"type": "LineString", "coordinates": [[1, 2], [3, 4]]},
                }
            ],
        },
    }
    summary = _summarise_mincut(raw, include_geometry=False)
    dumped = json.dumps(summary)
    assert "FeatureCollection" not in dumped
    assert summary["mincut_id"] == 1
    assert summary["categories"]["node"]["ids"] == [10]
    assert summary["categories"]["arc"]["ids"] == [20]
    with_geom = _summarise_mincut(raw, include_geometry=True)
    assert "FeatureCollection" in json.dumps(with_geom)


def test_flow_point_ids_group_by_feature_type():
    from app.mcp.tools.network import _flow_point_ids

    fc = {
        "type": "FeatureCollection",
        "features": [
            {"properties": {"feature_id": 1, "feature_type": "NODE"}},
            {"properties": {"feature_id": 2, "feature_type": "CONNEC"}},
            {"properties": {"feature_id": 3, "feature_type": "GULLY"}},
            {"properties": {"feature_id": 4, "feature_type": "NODE"}},
        ],
    }
    grouped = _flow_point_ids(fc)
    assert grouped["node_ids"] == [1, 4]
    assert grouped["connec_ids"] == [2]
    assert grouped["gully_ids"] == [3]


@pytest.mark.ws
def test_mcp_find_features_truncated(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "sys_type": ["VALVE"], "limit": 27},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") in (None, False)
    data = _tool_data(body)
    items = data.get("items") or []
    if len(items) < 27 and not data.get("truncated"):
        pytest.skip("not enough valves to exercise truncation")
    assert data["truncated"] is True
    assert data["count"] == 27


@pytest.mark.ud
def test_mcp_trace_flow_ids(client, default_params):
    assert_ready(client)
    listed, listed_body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "node", "limit": 1},
    )
    if listed.status_code != 200:
        pytest.skip(listed.text)
    items = _tool_data(listed_body).get("items") or []
    node_id = next((item.get("node_id") for item in items if item.get("node_id") is not None), None)
    if node_id is None:
        pytest.skip("no nodes")
    resp, body = _call_tool(
        client,
        "trace_flow",
        {"schema": default_params["schema"], "direction": "downstream", "node_id": int(node_id)},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    if result.get("isError"):
        pytest.skip(json.dumps(body))
    data = _tool_data(body)
    counts = data.get("counts") or {}
    assert len(data.get("node_ids") or []) == counts.get("nodes", 0)
    assert len(data.get("connec_ids") or []) == counts.get("connecs", 0)
    assert len(data.get("gully_ids") or []) == counts.get("gullies", 0)
    assert len(data.get("arc_ids") or []) == counts.get("arcs", 0)
    assert counts.get("nodes") or counts.get("arcs")


@pytest.mark.ws
def test_mcp_list_hydrometers_truncated(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(client, "list_hydrometers", {"schema": default_params["schema"], "limit": 1})
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    if result.get("isError"):
        pytest.skip(json.dumps(body))
    data = _tool_data(body)
    items = data.get("items") or []
    if not items:
        pytest.skip("no hydrometers")
    assert data["count"] >= len(items)
    if data["count"] == 1:
        pytest.skip("only one hydrometer")
    assert data["truncated"] is True
    assert data["count"] > len(items)


@pytest.mark.ws
def test_mcp_water_balance_dma_ids(client, default_params):
    assert_ready(client)
    listed, listed_body = _call_tool(client, "get_water_balance", {"schema": default_params["schema"]})
    if listed.status_code != 200:
        pytest.skip(listed.text)
    result = (listed_body or {}).get("result") or {}
    if result.get("isError"):
        pytest.skip(json.dumps(listed_body))
    items = _tool_data(listed_body).get("items") or []
    if not items:
        pytest.skip("no waterbalance rows")
    dma_id = items[0].get("dma_id")
    resp, body = _call_tool(
        client,
        "get_water_balance",
        {"schema": default_params["schema"], "dma_ids": [int(dma_id)]},
    )
    assert resp.status_code == 200, resp.text
    call_result = body.get("result") or {}
    assert call_result.get("isError") in (None, False)
    filtered = _tool_data(body).get("items") or []
    assert filtered
    assert all(row.get("dma_id") == dma_id for row in filtered)


def test_mcp_find_features_fields_id_and_count_only(client, default_params):
    assert_ready(client)
    schema = default_params["schema"]
    listed, listed_body = _call_tool(
        client,
        "find_features",
        {"schema": schema, "feature_type": "node", "limit": 3, "expl_id": 1},
    )
    assert listed.status_code == 200, listed.text
    result = listed_body.get("result") or {}
    assert result.get("isError") in (None, False)
    data = _tool_data(listed_body)
    items = data.get("items") or []
    if not items:
        pytest.skip("no nodes")
    assert data.get("filters") == {"expl_id": 1} or data.get("filters", {}).get("expl_id") == 1
    assert "total" in data
    row = items[0]
    assert set(row) <= {
        "node_id",
        "code",
        "sys_type",
        "state",
        "x",
        "y",
        "node_type",
    }
    ids_resp, ids_body = _call_tool(
        client,
        "find_features",
        {"schema": schema, "feature_type": "node", "limit": 3, "fields": "id"},
    )
    assert ids_resp.status_code == 200, ids_resp.text
    id_row = (_tool_data(ids_body).get("items") or [{}])[0]
    assert set(id_row) <= {"node_id"}
    count_resp, count_body = _call_tool(
        client,
        "find_features",
        {"schema": schema, "feature_type": "node", "count_only": True},
    )
    assert count_resp.status_code == 200, count_resp.text
    counted = _tool_data(count_body)
    assert counted.get("items") == []
    assert counted.get("count") == counted.get("total")
    assert isinstance(counted.get("total"), int)


def test_mcp_search_feature_type(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(client, "search", {"schema": default_params["schema"], "text": "1"})
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    if result.get("isError"):
        pytest.skip(json.dumps(body))
    items = _tool_data(body).get("items") or []
    if not items:
        pytest.skip("no search hits")
    known = {"ve_node": "node", "ve_arc": "arc", "ve_connec": "connec", "ve_gully": "gully", "ve_link": "link"}
    for item in items:
        table = item.get("table")
        if table in known:
            assert item.get("feature_type") == known[table]
        else:
            assert item.get("feature_type") is None


def test_mcp_ws_only_tools_declare_restriction():
    from app.mcp.registry import REGISTRY

    spec = next(s for s in REGISTRY if s.fn.__name__ == "list_mincuts")
    assert spec.project_types == frozenset({"WS"})
    assert "Restricted to WS schemas" in (spec.fn.__doc__ or "")
    flow = next(s for s in REGISTRY if s.fn.__name__ == "trace_flow")
    assert flow.project_types == frozenset({"UD"})


@pytest.mark.ws
def test_mcp_gully_rejected_on_ws(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "find_features",
        {"schema": default_params["schema"], "feature_type": "gully", "limit": 1},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    payload = json.dumps(body)
    assert "UD" in payload
    assert "ve_gully" not in payload


@pytest.mark.ws
def test_mcp_trace_flow_rejected_on_ws(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "trace_flow",
        {"schema": default_params["schema"], "direction": "downstream", "node_id": 1},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    payload = json.dumps(body)
    assert "UD" in payload
    assert "does not exist" not in payload


@pytest.mark.ud
def test_mcp_mincut_rejected_on_ud(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(client, "list_mincuts", {"schema": default_params["schema"]})
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    payload = json.dumps(body)
    assert "WS" in payload
    assert "EXECUTE is null" not in payload


@pytest.mark.ud
def test_mcp_presszone_rejected_on_ud(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "list_mapzones",
        {"schema": default_params["schema"], "zone_type": "presszone"},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    payload = json.dumps(body)
    assert "WS" in payload
    assert "does not exist" not in payload


@pytest.mark.ud
def test_mcp_dma_rejected_on_ud(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "list_mapzones",
        {"schema": default_params["schema"], "zone_type": "dma"},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    payload = json.dumps(body)
    assert "WS" in payload
    assert "macrodma_id" not in payload


@pytest.mark.ws
def test_mcp_epsg_mismatch(client, default_params):
    assert_ready(client)
    resp, body = _call_tool(
        client,
        "get_feature_at_point",
        {"schema": default_params["schema"], "x": 419487.25, "y": 4576484.26, "epsg": 4326},
    )
    assert resp.status_code == 200, resp.text
    result = body.get("result") or {}
    assert result.get("isError") is True
    payload = json.dumps(body).lower()
    assert "reproject" in payload or "epsg" in payload
    assert "null" not in payload or "does not match" in payload
