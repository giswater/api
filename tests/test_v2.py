"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.constants import TENANT_PREFIX_V2
from app.schemas.om.mincut_models import (
    GetMincutResponse,
    GetMincutsResponse,
    MincutState,
    OmMincut,
    OmMincutValve,
)
from tests.helpers import api_v2, assert_ready
from tests.test_om import _create_mincut, _delete_mincut

_GEOM_COLUMNS = ("anl_the_geom", "exec_the_geom", "polygon_the_geom")
_CHILD_COLLECTIONS = ("arcs", "valves", "nodes", "connecs", "hydrometers")
_CHILD_GEOM_COLLECTIONS = ("arcs", "valves", "nodes", "connecs")


def _assert_bbox(bbox) -> None:
    assert bbox is not None
    assert set(bbox) == {"x1", "y1", "x2", "y2"}
    assert bbox["x1"] <= bbox["x2"]
    assert bbox["y1"] <= bbox["y2"]
    assert -180 <= bbox["x1"] <= 180
    assert -180 <= bbox["x2"] <= 180
    assert -90 <= bbox["y1"] <= 90
    assert -90 <= bbox["y2"] <= 90


def _assert_geojson_or_none(value) -> None:
    if value is None:
        return
    assert isinstance(value, dict)
    assert "type" in value
    assert "coordinates" in value


def test_om_mincut_rejects_unknown_columns():
    with pytest.raises(ValidationError):
        OmMincut.model_validate({"id": 1, "not_a_column": True})


def test_om_mincut_state_roundtrip():
    row = OmMincut.model_validate({"id": 1, "mincut_state": 0, "mincut_class": 1})
    assert row.mincut_state == MincutState.PLANIFIED
    dumped = row.model_dump(mode="json", exclude_unset=True)
    assert dumped["mincut_state"] == 0
    assert dumped["mincut_class"] == 1
    assert "anl_the_geom" not in dumped


def test_v2_mincut_responses_use_flat_body():
    envelope = {
        "status": "Accepted",
        "message": {"level": 3, "text": "ok"},
        "version": {"api": "1.7.0", "db": "4.16.0"},
    }
    GetMincutsResponse.model_validate({**envelope, "body": {"mincuts": [{"id": 1}]}})
    GetMincutResponse.model_validate(
        {
            **envelope,
            "body": {
                "mincut": {"id": 1},
                "arcs": [],
                "valves": [],
                "nodes": [],
                "connecs": [],
                "hydrometers": [],
                "conflicts": [],
            },
        }
    )
    with pytest.raises(ValidationError):
        GetMincutsResponse.model_validate(
            {
                **envelope,
                "body": {"form": {}, "feature": {}, "data": {"mincuts": [{"id": 1}]}},
            }
        )


def test_om_mincut_valve_parses_flags():
    valve = OmMincutValve.model_validate({"id": 1, "node_id": 99, "proposed": True, "unaccess": False})
    assert valve.node_id == 99
    assert valve.proposed is True
    assert valve.unaccess is False
    dumped = valve.model_dump(mode="json", exclude_unset=True)
    assert "the_geom" not in dumped


def test_v2_health_and_openapi_include_mincuts(client: TestClient):
    health = client.get(api_v2("/health"))
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    openapi = client.get(f"{TENANT_PREFIX_V2}/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/om/mincuts" in paths
    assert "/om/mincuts/{mincut_id}" in paths
    assert "/basic/getlist" not in paths
    list_params = {p["name"] for p in paths["/om/mincuts"]["get"].get("parameters", [])}
    assert "includeGeometry" in list_params
    detail_params = {p["name"] for p in paths["/om/mincuts/{mincut_id}"]["get"].get("parameters", [])}
    assert "includeGeometry" in detail_params

    schemas = openapi.json()["components"]["schemas"]
    assert "mincuts" in schemas["GetMincutsData"]["properties"]
    assert "form" not in schemas["GetMincutsData"]["properties"]
    assert "data" not in schemas["GetMincutsData"]["properties"]
    assert "mincut" in schemas["GetMincutData"]["properties"]
    assert "form" not in schemas["GetMincutData"]["properties"]
    assert "data" not in schemas["GetMincutData"]["properties"]
    assert schemas["GetMincutsResponse"]["properties"]["body"]["$ref"].endswith("/GetMincutsData")
    assert schemas["GetMincutResponse"]["properties"]["body"]["$ref"].endswith("/GetMincutData")


@pytest.mark.ws
def test_v2_get_mincuts(client: TestClient, default_params):
    assert_ready(client)

    response = client.get(api_v2("/om/mincuts"), params=default_params)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    mincuts = data["body"]["mincuts"]
    assert isinstance(mincuts, list)
    for row in mincuts:
        for col in _GEOM_COLUMNS:
            assert col not in row


@pytest.mark.ws
def test_v2_get_mincuts_include_geometry(client: TestClient, default_params):
    assert_ready(client)

    params = {**default_params, "includeGeometry": "true"}
    response = client.get(api_v2("/om/mincuts"), params=params)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    mincuts = data["body"]["mincuts"]
    assert isinstance(mincuts, list)
    for row in mincuts:
        for col in _GEOM_COLUMNS:
            assert col in row
            geom = row[col]
            _assert_geojson_or_none(geom)


@pytest.mark.ws
@pytest.mark.destructive
def test_v2_get_mincut(client: TestClient, default_params):
    assert_ready(client)
    mincut_id = _create_mincut(client, default_params)
    try:
        response = client.get(api_v2(f"/om/mincuts/{mincut_id}"), params=default_params)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Accepted"
        payload = data["body"]
        assert payload["mincut"]["id"] == mincut_id
        for col in _GEOM_COLUMNS:
            assert col not in payload["mincut"]
        for name in _CHILD_COLLECTIONS:
            assert isinstance(payload[name], list)
            for row in payload[name]:
                assert "result_id" not in row
                assert "the_geom" not in row
        assert isinstance(payload["conflicts"], list)
        for sibling_id in payload["conflicts"]:
            assert isinstance(sibling_id, int)
            assert sibling_id != mincut_id
        _assert_bbox(payload["bbox"])
    finally:
        _delete_mincut(client, default_params, mincut_id)


@pytest.mark.ws
@pytest.mark.destructive
def test_v2_get_mincut_include_geometry(client: TestClient, default_params):
    assert_ready(client)
    mincut_id = _create_mincut(client, default_params)
    try:
        params = {**default_params, "includeGeometry": "true"}
        response = client.get(api_v2(f"/om/mincuts/{mincut_id}"), params=params)

        assert response.status_code == 200
        payload = response.json()["body"]
        assert payload["mincut"]["id"] == mincut_id
        for col in _GEOM_COLUMNS:
            assert col in payload["mincut"]
            _assert_geojson_or_none(payload["mincut"][col])
        for name in _CHILD_GEOM_COLLECTIONS:
            for row in payload[name]:
                assert "the_geom" in row
                _assert_geojson_or_none(row["the_geom"])
        for row in payload["hydrometers"]:
            assert "the_geom" not in row
        _assert_bbox(payload["bbox"])
    finally:
        _delete_mincut(client, default_params, mincut_id)


@pytest.mark.ws
def test_v2_get_mincut_not_found(client: TestClient, default_params):
    assert_ready(client)

    response = client.get(api_v2("/om/mincuts/2147483647"), params=default_params)

    assert response.status_code == 404
    assert "2147483647" in response.json()["detail"]
