"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio

import pytest
from psycopg import sql

from app.tenancy import state
from tests.helpers import assert_ready, api


@pytest.mark.ws
def test_get_mincuts(client, default_params):
    assert_ready(client)

    response = client.get(api("/om/mincuts"), params=default_params)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "body" in data


@pytest.mark.ud
@pytest.mark.parametrize(
    ("initial_node_id", "final_node_id", "expected_status", "expected_api_status"),
    [
        (35, 38, 200, "Accepted"),
        (36, 37, 500, "Failed"),
    ],
)
def test_create_profile(
    client, default_params, initial_node_id: int, final_node_id: int, expected_status: int, expected_api_status: str
):
    assert_ready(client)

    payload = {
        "initial_node_id": initial_node_id,
        "final_node_id": final_node_id,
        "links_distance": 1,
        "scale_eh": 1000,
        "scale_ev": 1000,
    }

    response = client.post(api("/om/profiles"), params=default_params, json=payload)

    assert response.status_code == expected_status
    data = response.json()
    assert data["status"] == expected_api_status
    if expected_status == 200:
        assert "body" in data


@pytest.mark.ud
@pytest.mark.parametrize(
    ("direction", "node_id"),
    [
        ("upstream", 35),
        ("downstream", 35),
    ],
)
def test_flow_success(client, default_params, direction: str, node_id: int):
    assert_ready(client)

    payload = {"direction": direction, "node_id": node_id}
    response = client.post(api("/om/flow"), params=default_params, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "body" in data


@pytest.mark.ud
def test_flow_fails_without_node_or_coordinates(client, default_params):
    assert_ready(client)

    response = client.post(api("/om/flow"), params=default_params, json={"direction": "upstream"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Either node ID or coordinates must be provided"


@pytest.mark.ud
def test_flow_fails_with_invalid_direction(client, default_params):
    assert_ready(client)

    response = client.post(api("/om/flow"), params=default_params, json={"direction": "sideways", "node_id": 35})

    assert response.status_code == 422
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# Mincut lifecycle helpers
# ---------------------------------------------------------------------------

_MINCUT_COORDINATES = {
    "xcoord": 419487.25,
    "ycoord": 4576484.26,
    "epsg": 25831,
    "zoomRatio": 1000,
}


def _ensure_current_user_in_cat_users(schema: str) -> None:
    """om_mincut.assigned_to FK → cat_users(id); seed current_user before create."""
    assert state.registry is not None, "Tenant registry not initialized"
    tenant = state.registry.get("test")
    assert tenant is not None, "Tenant 'test' not loaded"

    async def _run() -> None:
        async with tenant.db_manager.get_db() as conn:
            assert conn is not None, "Postgres not available"
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL(
                        "INSERT INTO {}.cat_users (id, name) "
                        "VALUES (current_user, current_user) "
                        "ON CONFLICT (id) DO NOTHING"
                    ).format(sql.Identifier(schema))
                )
            await conn.commit()

    asyncio.run(_run())


def _create_mincut(client, default_params) -> int:
    """Create a mincut and return its ID."""
    _ensure_current_user_in_cat_users(default_params["schema"])
    payload = {
        "coordinates": _MINCUT_COORDINATES,
        "plan": {
            "mincut_type": "Real",
            "anl_cause": "Accidental",
            "anl_descript": "Test mincut",
        },
        "use_psectors": False,
    }
    response = client.post(api("/om/mincuts"), params=default_params, json=payload)
    assert response.status_code == 200, f"Failed to create mincut: {response.text}"
    data = response.json()
    assert data["status"] == "Accepted"
    # Extract the mincut_id from the response
    mincut_id = data["body"]["data"]["mincutId"]
    return mincut_id


def _delete_mincut(client, default_params, mincut_id: int):
    """Delete a mincut (cleanup helper)."""
    response = client.delete(api(f"/om/mincuts/{mincut_id}"), params=default_params)
    assert response.status_code == 200, f"Failed to delete mincut {mincut_id}: {response.text}"


# ---------------------------------------------------------------------------
# Mincut lifecycle test
# ---------------------------------------------------------------------------


@pytest.mark.ws
@pytest.mark.destructive
def test_mincut_lifecycle(client, default_params):
    """Full lifecycle: create -> get dialog -> update -> get valves -> start -> end -> delete."""
    assert_ready(client)

    # 1. Create
    mincut_id = _create_mincut(client, default_params)

    # 2. Get dialog
    response = client.get(api(f"/om/mincuts/{mincut_id}"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "body" in data

    # 3. Update
    update_payload = {
        "plan": {"anl_descript": "Updated test mincut"},
        "use_psectors": False,
    }
    response = client.patch(api(f"/om/mincuts/{mincut_id}"), params=default_params, json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"

    # 4. Get valves
    response = client.get(api(f"/om/mincuts/{mincut_id}/valves"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"

    # 5. Start
    start_payload = {"use_psectors": False}
    response = client.post(api(f"/om/mincuts/{mincut_id}/start"), params=default_params, json=start_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"

    # 6. End
    end_payload = {"shutoff_required": True, "use_psectors": False}
    response = client.post(api(f"/om/mincuts/{mincut_id}/end"), params=default_params, json=end_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"


@pytest.mark.ws
@pytest.mark.destructive
def test_mincut_cancel(client, default_params):
    """Create a mincut, cancel it, then delete it."""
    assert_ready(client)

    mincut_id = _create_mincut(client, default_params)
    response = client.post(api(f"/om/mincuts/{mincut_id}/cancel"), params=default_params)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"


@pytest.mark.ws
@pytest.mark.destructive
def test_valve_toggle_unaccess(client, default_params):
    """Create a mincut, get valves, toggle unaccess on the first valve found."""
    assert_ready(client)

    mincut_id = _create_mincut(client, default_params)
    try:
        # Get valves to find a valve_id
        response = client.get(api(f"/om/mincuts/{mincut_id}/valves"), params=default_params)
        assert response.status_code == 200
        data = response.json()
        features = data.get("body", {}).get("data", {}).get("features", [])
        if not features:
            pytest.skip("No valves found for this mincut, cannot test toggle-unaccess")

        valve_id = features[0]["node_id"]
        toggle_payload = {"use_psectors": False}
        response = client.post(
            api(f"/om/mincuts/{mincut_id}/valves/{valve_id}/toggle-unaccess"),
            params=default_params,
            json=toggle_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Accepted"
    finally:
        _delete_mincut(client, default_params, mincut_id)


@pytest.mark.ws
@pytest.mark.destructive
def test_valve_toggle_status(client, default_params):
    """Create a mincut, get valves, toggle status on the first valve found."""
    assert_ready(client)

    mincut_id = _create_mincut(client, default_params)
    try:
        # Get valves to find a valve_id
        response = client.get(api(f"/om/mincuts/{mincut_id}/valves"), params=default_params)
        assert response.status_code == 200
        data = response.json()
        features = data.get("body", {}).get("data", {}).get("features", [])
        if not features:
            pytest.skip("No valves found for this mincut, cannot test toggle-status")

        valve_id = features[0]["node_id"]
        toggle_payload = {"use_psectors": False}
        response = client.post(
            api(f"/om/mincuts/{mincut_id}/valves/{valve_id}/toggle-status"),
            params=default_params,
            json=toggle_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Accepted"
    finally:
        _delete_mincut(client, default_params, mincut_id)


# ---------------------------------------------------------------------------
# Water Balance
# ---------------------------------------------------------------------------


@pytest.mark.ws
def test_get_waterbalance(client, default_params):
    assert_ready(client)

    response = client.get(api("/om/waterbalance"), params=default_params)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted"
    assert "body" in data
