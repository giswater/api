"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest

from tests.helpers import api, assert_ready

_MATCH = {"attribute", "spatial", "both"}
_PROBE_Q = ("ca", "er", "an", "al", "el", "de", "la", "sa", "ra", "ma", "ri", "to")


def _streets_payload(response):
    return ((response.json().get("body") or {}).get("data") or {}).get("streets") or []


def _sample_street(client, default_params) -> dict:
    for q in _PROBE_Q:
        response = client.get(api("/streets"), params={**default_params, "q": q, "limit": 5})
        if response.status_code != 200:
            continue
        streets = _streets_payload(response)
        if streets:
            return streets[0]
    pytest.skip("no streets in sample")


def test_list_streets_requires_q(client, default_params):
    assert_ready(client)
    response = client.get(api("/streets"), params=default_params)
    assert response.status_code == 422


def test_list_streets_rejects_short_q(client, default_params):
    assert_ready(client)
    response = client.get(api("/streets"), params={**default_params, "q": "a"})
    assert response.status_code == 422


def test_list_streets_finds_sample(client, default_params):
    assert_ready(client)
    street = _sample_street(client, default_params)
    assert street.get("id")
    token = (street.get("name") or street["id"])[:2]
    if len(token) < 2:
        token = street["id"][:2]
    response = client.get(api("/streets"), params={**default_params, "q": token, "limit": 50})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    streets = _streets_payload(response)
    assert any(row.get("id") == street["id"] for row in streets)


def test_list_street_arcs(client, default_params):
    assert_ready(client)
    street = _sample_street(client, default_params)
    response = client.get(api(f"/streets/{street['id']}/arcs"), params={**default_params, "limit": 50})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    payload = (data.get("body") or {}).get("data") or {}
    assert payload.get("street", {}).get("id") == street["id"]
    arcs = payload.get("arcs") or []
    for arc in arcs:
        assert arc.get("match") in _MATCH
        assert "arc_id" in arc
        assert "distance_m" not in arc


def test_list_street_arcs_unknown_house_number(client, default_params):
    assert_ready(client)
    street = _sample_street(client, default_params)
    base = client.get(api(f"/streets/{street['id']}/arcs"), params={**default_params, "limit": 50})
    ranked = client.get(
        api(f"/streets/{street['id']}/arcs"),
        params={**default_params, "houseNumber": "999999", "limit": 50},
    )
    assert ranked.status_code == 200
    base_arcs = ((base.json().get("body") or {}).get("data") or {}).get("arcs") or []
    ranked_data = (ranked.json().get("body") or {}).get("data") or {}
    ranked_arcs = ranked_data.get("arcs") or []
    assert {a.get("arc_id") for a in ranked_arcs} == {a.get("arc_id") for a in base_arcs}
    assert all("distance_m" not in a for a in ranked_arcs)


def _assert_exact_page(fetch, full_count: int):
    """``fetch(limit)`` returns ``body.data``. A page of size ``full_count`` is not truncated."""
    if full_count >= 500:
        pytest.skip("match set hits the 500 cap; cannot prove an exact page")
    exact = fetch(full_count)
    assert exact["truncated"] is False
    assert exact["count"] == full_count
    if full_count < 2:
        return
    short = fetch(full_count - 1)
    assert short["truncated"] is True
    assert short["count"] == full_count - 1


def test_list_streets_exact_page_is_not_truncated(client, default_params):
    assert_ready(client)
    street = _sample_street(client, default_params)
    token = street.get("name") or ""
    if len(token) < 2:
        token = street["id"][:2]

    def fetch(limit: int) -> dict:
        response = client.get(api("/streets"), params={**default_params, "q": token, "limit": limit})
        assert response.status_code == 200, response.text
        return (response.json().get("body") or {}).get("data") or {}

    wide = fetch(500)
    _assert_exact_page(fetch, wide["count"])


def test_list_street_arcs_exact_page_is_not_truncated(client, default_params):
    assert_ready(client)
    street = _sample_street(client, default_params)

    def fetch(limit: int) -> dict:
        response = client.get(api(f"/streets/{street['id']}/arcs"), params={**default_params, "limit": limit})
        assert response.status_code == 200, response.text
        return (response.json().get("body") or {}).get("data") or {}

    wide = fetch(500)
    if not wide.get("arcs"):
        pytest.skip("street has no arcs")
    _assert_exact_page(fetch, wide["count"])


def test_list_street_arcs_unknown_id(client, default_params):
    assert_ready(client)
    response = client.get(api("/streets/__missing__/arcs"), params=default_params)
    assert response.status_code == 404
