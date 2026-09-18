"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest

from uuid import uuid4

from tests.helpers import assert_ready, api


def _new_hydrometer_code() -> str:
    return f"TEST_CRM_{uuid4().hex[:10]}"


def _hydrometer_payload(code: str) -> dict:
    return {"code": code, "hydroNumber": f"HN-{code}"}


def _insert_hydrometers(client, default_params, payload):
    response = client.post(api("/crm/hydrometers"), params=default_params, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    return data


def test_insert_hydrometer_single(client, default_params):
    assert_ready(client)

    code = _new_hydrometer_code()
    payload = _hydrometer_payload(code)

    response = client.post(api("/crm/hydrometers"), params=default_params, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data


def test_insert_hydrometers_bulk(client, default_params):
    assert_ready(client)

    payload = [_hydrometer_payload(_new_hydrometer_code()) for _ in range(2)]

    response = client.post(api("/crm/hydrometers"), params=default_params, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data


def test_update_hydrometer_single(client, default_params):
    assert_ready(client)

    code = _new_hydrometer_code()
    _insert_hydrometers(client, default_params, _hydrometer_payload(code))

    update_payload = {"code": code, "hydroNumber": f"UPDATED-{code}"}
    response = client.patch(api(f"/crm/hydrometers/{code}"), params=default_params, json=update_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data


def test_update_hydrometers_bulk(client, default_params):
    assert_ready(client)

    codes = [_new_hydrometer_code(), _new_hydrometer_code()]
    payload = [_hydrometer_payload(code) for code in codes]
    _insert_hydrometers(client, default_params, payload)

    update_payload = [
        {"code": codes[0], "hydroNumber": f"UPDATED-{codes[0]}"},
        {"code": codes[1], "hydroNumber": f"UPDATED-{codes[1]}"},
    ]
    response = client.patch(api("/crm/hydrometers"), params=default_params, json=update_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data


def test_delete_hydrometer_single(client, default_params):
    assert_ready(client)

    code = _new_hydrometer_code()
    _insert_hydrometers(client, default_params, _hydrometer_payload(code))

    response = client.delete(api(f"/crm/hydrometers/{code}"), params=default_params)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data


def test_delete_hydrometers_bulk(client, default_params):
    assert_ready(client)

    codes = [_new_hydrometer_code(), _new_hydrometer_code()]
    payload = [_hydrometer_payload(code) for code in codes]
    _insert_hydrometers(client, default_params, payload)

    response = client.request("DELETE", api("/crm/hydrometers"), params=default_params, json=codes)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data


def test_list_hydrometers(client, default_params):
    assert_ready(client)

    code = _new_hydrometer_code()
    _insert_hydrometers(client, default_params, _hydrometer_payload(code))

    response = client.get(api("/crm/hydrometers"), params={**default_params, "code": code})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "Accepted"
    hydrometers = ((data.get("body") or {}).get("data") or {}).get("hydrometers") or []
    assert any(row.get("code") == code for row in hydrometers if isinstance(row, dict))


def _hydrometer_rows(data: dict) -> list[dict]:
    return [
        row for row in (((data.get("body") or {}).get("data") or {}).get("hydrometers") or []) if isinstance(row, dict)
    ]


def _sample_linked_connec(client, default_params) -> dict:
    response = client.get(api("/features/connecs"), params={**default_params, "limit": 50})
    assert response.status_code == 200, response.text
    features = ((response.json().get("body") or {}).get("data") or {}).get("features") or []
    for row in features:
        if isinstance(row, dict) and row.get("connec_id") is not None and row.get("customer_code"):
            return row
    pytest.skip("no connec with customer_code")


def test_list_hydrometers_joined_fields(client, default_params):
    assert_ready(client)

    response = client.get(api("/crm/hydrometers"), params={**default_params, "limit": 1})
    assert response.status_code == 200, response.text
    rows = _hydrometer_rows(response.json())
    if not rows:
        pytest.skip("no hydrometers")
    assert "connec_id" in rows[0]
    assert "dma_id" in rows[0]
    assert "customer_code" in rows[0]


@pytest.mark.ws
def test_list_hydrometers_by_customer_code(client, default_params):
    assert_ready(client)

    listed = client.get(api("/crm/hydrometers"), params={**default_params, "limit": 50})
    assert listed.status_code == 200, listed.text
    customer_code = next(
        (row.get("customer_code") for row in _hydrometer_rows(listed.json()) if row.get("customer_code")),
        None,
    )
    if not customer_code:
        pytest.skip("no hydrometer with customer_code")
    response = client.get(
        api("/crm/hydrometers"),
        params={**default_params, "customerCode": customer_code, "limit": 50},
    )
    assert response.status_code == 200, response.text
    rows = _hydrometer_rows(response.json())
    assert rows
    assert all(row.get("customer_code") == customer_code for row in rows)


@pytest.mark.ws
def test_insert_hydrometer_with_customer_code(client, default_params):
    assert_ready(client)

    connec = _sample_linked_connec(client, default_params)
    code = _new_hydrometer_code()
    payload = {"code": code, "customerCode": connec["customer_code"]}
    try:
        _insert_hydrometers(client, default_params, payload)
        response = client.get(api("/crm/hydrometers"), params={**default_params, "code": code})
        assert response.status_code == 200, response.text
        rows = _hydrometer_rows(response.json())
        assert rows
        assert rows[0].get("customer_code") == connec["customer_code"]
        assert rows[0].get("connec_id") == connec["connec_id"] or str(rows[0].get("connec_id")) == str(
            connec["connec_id"]
        )
    finally:
        client.delete(api(f"/crm/hydrometers/{code}"), params=default_params)


@pytest.mark.ws
def test_insert_hydrometer_with_connec_id(client, default_params):
    assert_ready(client)

    connec = _sample_linked_connec(client, default_params)
    code = _new_hydrometer_code()
    payload = {"code": code, "connecId": connec["connec_id"]}
    try:
        _insert_hydrometers(client, default_params, payload)
        response = client.get(api("/crm/hydrometers"), params={**default_params, "code": code})
        assert response.status_code == 200, response.text
        rows = _hydrometer_rows(response.json())
        assert rows
        assert rows[0].get("customer_code") == connec["customer_code"]
        assert rows[0].get("connec_id") == connec["connec_id"] or str(rows[0].get("connec_id")) == str(
            connec["connec_id"]
        )
    finally:
        client.delete(api(f"/crm/hydrometers/{code}"), params=default_params)


@pytest.mark.ws
@pytest.mark.destructive
def test_list_hydrometers_by_mincut_id(client, default_params):
    assert_ready(client)

    from tests.test_om import _create_mincut, _delete_mincut

    mincut_id = _create_mincut(client, default_params)
    try:
        response = client.get(
            api("/crm/hydrometers"),
            params={**default_params, "mincutId": mincut_id, "limit": 50},
        )
        assert response.status_code == 200, response.text
        rows = _hydrometer_rows(response.json())
        if not rows:
            pytest.skip(f"om_mincut_hydrometer empty for mincut {mincut_id}")
        assert all("code" in row for row in rows)
    finally:
        _delete_mincut(client, default_params, mincut_id)


@pytest.mark.destructive
def test_replace_all_hydrometers(client, default_params):
    assert_ready(client)

    payload = [_hydrometer_payload(_new_hydrometer_code()) for _ in range(2)]
    response = client.put(api("/crm/hydrometers"), params=default_params, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "version" in data
    assert "body" in data
