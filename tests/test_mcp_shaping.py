"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest
from fastmcp.exceptions import ToolError

from app.mcp.shaping import drop_keys, fc_summary, feature_rows, fields_to_dict, list_rows, one_row, unwrap


def test_unwrap_accepted():
    assert unwrap({"status": "Accepted", "body": {"data": {"a": 1}}}) == {"a": 1}


def test_unwrap_failed_raises():
    with pytest.raises(ToolError, match="boom"):
        unwrap({"status": "Failed", "MSGERR": "boom", "body": {}})


def test_feature_rows_truncates():
    resp = {
        "status": "Accepted",
        "body": {
            "data": {
                "features": [{"id": i} for i in range(5)],
                "pageInfo": {"currentPage": 1, "lastPage": 1},
            }
        },
    }
    shaped = feature_rows(resp, limit=2)
    assert shaped["count"] == 2
    assert shaped["truncated"] is True
    assert shaped["items"][0]["id"] == 0


def test_list_rows():
    resp = {"status": "Accepted", "body": {"data": {"fields": [{"a": 1}, {"a": 2}]}}}
    shaped = list_rows(resp, limit=10)
    assert shaped["count"] == 2
    assert shaped["truncated"] is False


def test_one_row():
    resp = {"status": "Accepted", "body": {"data": {"feature": {"node_id": 35}}}}
    assert one_row(resp)["node_id"] == 35


def test_fields_to_dict():
    assert fields_to_dict([{"columnname": "node_id", "value": 35, "widgettype": "text"}]) == {"node_id": 35}


def test_fc_summary_bbox_and_ids():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                "properties": {"node_id": 10},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
                "properties": {"node_id": 11},
            },
        ],
    }
    summary = fc_summary(fc, "node_id")
    assert summary["count"] == 2
    assert summary["ids"] == [10, 11]
    assert summary["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_drop_keys():
    assert drop_keys({"a": 1, "stylesheet": {}, "b": 2}, "stylesheet") == {"a": 1, "b": 2}
