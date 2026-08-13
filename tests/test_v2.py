"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.constants import TENANT_PREFIX_V2
from tests.helpers import api_v2, assert_ready

_GEOM_COLUMNS = ("anl_the_geom", "exec_the_geom", "polygon_the_geom")


def test_v2_health_and_openapi_include_mincuts(client: TestClient):
    health = client.get(api_v2("/health"))
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    openapi = client.get(f"{TENANT_PREFIX_V2}/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/om/mincuts" in paths
    assert "/basic/getlist" not in paths
    params = {p["name"] for p in paths["/om/mincuts"]["get"].get("parameters", [])}
    assert "includeGeometry" in params


@pytest.mark.ws
def test_v2_get_mincuts(client: TestClient, default_params):
    assert_ready(client)

    response = client.get(api_v2("/om/mincuts"), params=default_params)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    mincuts = data["body"]["data"]["mincuts"]
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
    mincuts = data["body"]["data"]["mincuts"]
    assert isinstance(mincuts, list)
    for row in mincuts:
        for col in _GEOM_COLUMNS:
            assert col in row
            geom = row[col]
            if geom is not None:
                assert isinstance(geom, dict)
                assert "type" in geom
                assert "coordinates" in geom
