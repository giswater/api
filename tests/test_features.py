"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from dataclasses import replace

import pytest
from tests.helpers import api, assert_ready


def _db_version(client, default_params) -> str | None:
    response = client.get(api("/features/nodes"), params={**default_params, "limit": 1})
    if response.status_code == 200:
        version = response.json().get("version") or {}
        return version.get("db")
    body = response.json()
    version = body.get("version")
    if isinstance(version, dict):
        return version.get("db")
    if isinstance(version, str):
        return version
    return None


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _require_getfeatures_refactor(client, default_params) -> None:
    """gw_fct_getfeatures featureType/outputFormat ships in Giswater DB 4.17.0+."""
    assert_ready(client)
    version = _db_version(client, default_params)
    if version is None:
        pytest.skip("Could not determine Giswater DB version")
    if _version_tuple(version) < (4, 17, 0):
        pytest.skip(f"Requires Giswater DB >= 4.17.0 for gw_fct_getfeatures refactor (got {version})")


@pytest.mark.parametrize(
    "path",
    [
        "/features/nodes",
        "/features/arcs",
        "/features/links",
        "/features/connecs",
    ],
)
def test_list_features(client, default_params, path):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api(path), params={**default_params, "limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "body" in data
    assert "data" in data["body"]
    assert "features" in data["body"]["data"]


@pytest.mark.parametrize(
    "path",
    [
        "/features/nodes/geojson",
        "/features/arcs/geojson",
        "/features/links/geojson",
        "/features/connecs/geojson",
    ],
)
def test_list_features_geojson(client, default_params, path):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api(path), params={**default_params, "limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    body_data = data["body"]["data"]
    assert body_data.get("type") == "FeatureCollection"
    assert "features" in body_data


def test_nodes_geojson_not_swallowed_by_node_id(client, default_params):
    """Route order: /nodes/geojson must not match /nodes/{node_id}."""
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/nodes/geojson"), params={**default_params, "limit": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert data["body"]["data"].get("type") == "FeatureCollection"


def test_arcs_filter_by_dma_id(client, default_params):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/arcs"), params={**default_params, "dma_id": 2, "limit": 50})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    features = data["body"]["data"].get("features") or []
    for feature in features:
        assert feature.get("dma_id") == 2


def test_connecs_filter_by_sector_id(client, default_params):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/connecs"), params={**default_params, "sector_id": 5, "limit": 50})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    features = data["body"]["data"].get("features") or []
    for feature in features:
        assert feature.get("sector_id") == 5


def test_nodes_filter_by_sys_type_valve(client, default_params):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/nodes"), params={**default_params, "sys_type": "VALVE", "limit": 50})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    features = data["body"]["data"].get("features") or []
    for feature in features:
        assert feature.get("sys_type") == "VALVE"


def test_unknown_filter_returns_422(client, default_params):
    assert_ready(client)

    response = client.get(api("/features/nodes"), params={**default_params, "nodetype": "VALVE", "limit": 10})

    assert response.status_code == 422


def test_limit_is_honoured(client, default_params):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/arcs"), params={**default_params, "limit": 3})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    features = data["body"]["data"].get("features") or []
    assert len(features) <= 3


def test_get_feature_by_id(client, default_params):
    _require_getfeatures_refactor(client, default_params)

    listing = client.get(api("/features/nodes"), params={**default_params, "limit": 1})
    assert listing.status_code == 200
    features = listing.json().get("body", {}).get("data", {}).get("features") or []
    if not features:
        pytest.skip("No nodes available to fetch by id")

    node_id = features[0].get("node_id")
    assert node_id is not None
    list_keys = set(features[0].keys())

    response = client.get(api(f"/features/nodes/{node_id}"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    feature = data["body"]["data"]["feature"]
    assert feature["node_id"] == node_id
    assert set(feature.keys()) == list_keys


@pytest.mark.parametrize(
    ("list_path", "id_field"),
    [
        ("/features/nodes", "node_id"),
        ("/features/arcs", "arc_id"),
        ("/features/links", "link_id"),
        ("/features/connecs", "connec_id"),
    ],
)
def test_get_feature_fields_by_id(client, default_params, list_path, id_field):
    _require_getfeatures_refactor(client, default_params)

    listing = client.get(api(list_path), params={**default_params, "limit": 1})
    assert listing.status_code == 200
    features = listing.json().get("body", {}).get("data", {}).get("features") or []
    if not features:
        pytest.skip(f"No features available at {list_path}")

    feature_id = features[0][id_field]
    list_keys = set(features[0].keys())
    base_path = list_path.rstrip("/")

    response = client.get(api(f"{base_path}/{feature_id}"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    feature = data["body"]["data"]["feature"]
    assert feature[id_field] == feature_id
    assert set(feature.keys()) == list_keys


@pytest.mark.parametrize(
    ("list_path", "id_field"),
    [
        ("/features/nodes", "node_id"),
        ("/features/arcs", "arc_id"),
        ("/features/links", "link_id"),
        ("/features/connecs", "connec_id"),
    ],
)
def test_get_feature_form_by_id(client, default_params, list_path, id_field):
    _require_getfeatures_refactor(client, default_params)

    listing = client.get(api(list_path), params={**default_params, "limit": 1})
    assert listing.status_code == 200
    features = listing.json().get("body", {}).get("data", {}).get("features") or []
    if not features:
        pytest.skip(f"No features available at {list_path}")

    feature_id = features[0][id_field]
    base_path = list_path.rstrip("/")

    response = client.get(api(f"{base_path}/{feature_id}/form"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "fields" in data["body"]["data"]


@pytest.mark.parametrize(
    ("list_path", "id_field"),
    [
        ("/features/nodes", "node_id"),
        ("/features/arcs", "arc_id"),
        ("/features/links", "link_id"),
        ("/features/connecs", "connec_id"),
    ],
)
def test_get_feature_geojson_by_id(client, default_params, list_path, id_field):
    _require_getfeatures_refactor(client, default_params)

    listing = client.get(api(list_path), params={**default_params, "limit": 1})
    assert listing.status_code == 200
    features = listing.json().get("body", {}).get("data", {}).get("features") or []
    if not features:
        pytest.skip(f"No features available at {list_path}")

    feature_id = features[0][id_field]
    base_path = list_path.rstrip("/")

    response = client.get(api(f"{base_path}/{feature_id}/geojson"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    body_data = data["body"]["data"]
    assert body_data["type"] == "Feature"
    assert body_data["geometry"] is not None
    assert body_data["properties"][id_field] == feature_id


def test_get_feature_by_id_not_found(client, default_params):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/arcs/__nope__"), params=default_params)
    assert response.status_code == 404
    assert "detail" in response.json()


def test_arcs_geojson_not_swallowed_by_arc_id(client, default_params):
    """Route order: /arcs/geojson must not match /arcs/{arc_id}."""
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api("/features/arcs/geojson"), params={**default_params, "limit": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert data["body"]["data"].get("type") == "FeatureCollection"


def test_features_disabled_returns_404(client, default_params):
    assert_ready(client)

    from app.tenancy import state

    assert state.registry is not None
    tenant = state.registry.get("test")
    assert tenant is not None
    original = tenant.settings
    tenant.settings = replace(original, api_features=False)
    try:
        response = client.get(api("/features/nodes"), params={**default_params, "limit": 1})
        assert response.status_code == 404
        assert response.json()["detail"] == "Feature disabled"
    finally:
        tenant.settings = original


@pytest.mark.ud
@pytest.mark.parametrize(
    "path",
    [
        "/features/gullies",
        "/features/gullies/geojson",
    ],
)
def test_list_gullies_ud(client, default_params, path):
    _require_getfeatures_refactor(client, default_params)

    response = client.get(api(path), params={**default_params, "limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "body" in data
