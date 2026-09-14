"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest
from fastmcp.exceptions import ToolError

from app.mcp.shaping import (
    compact_row,
    drop_keys,
    failed_text,
    fc_summary,
    feature_rows,
    fields_to_dict,
    list_rows,
    one_row,
    unwrap,
)


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


def test_unwrap_failed_message_text():
    with pytest.raises(ToolError, match="downstream missing"):
        unwrap({"status": "Failed", "message": {"level": 3, "text": "downstream missing"}, "body": {}})


def test_failed_text_from_detail_envelope():
    from app.mcp.client import _http_error_text

    text = _http_error_text(
        {"status": "Failed", "message": {"level": 3, "text": "function does not exist"}, "body": {}}
    )
    assert text == "function does not exist"
    wrapped = _http_error_text({"detail": {"status": "Failed", "message": {"text": "function does not exist"}}})
    assert wrapped == "function does not exist"


def test_compact_row_drops_nulls_and_styles():
    row = compact_row(
        {
            "node_id": 1,
            "label": None,
            "dma_style": "179,205,227",
            "sector_visibility": None,
            "svg": "x",
            "sys_type": "VALVE",
            "coordinates": {"x": 1.0, "y": 2.0, "epsg": 25831},
        }
    )
    assert row == {"node_id": 1, "sys_type": "VALVE", "coordinates": {"x": 1.0, "y": 2.0, "epsg": 25831}}


def test_fields_to_dict_skip_hidden_drop_nulls():
    fields = [
        {"columnname": "node_id", "value": 35, "hidden": False},
        {"columnname": "secret", "value": "x", "hidden": True},
        {"columnname": "empty", "value": None, "hidden": False},
    ]
    assert fields_to_dict(fields, skip_hidden=True, drop_nulls=True) == {"node_id": 35}


def test_feature_rows_compact_false_keeps_style():
    resp = {
        "status": "Accepted",
        "body": {"data": {"features": [{"id": 1, "dma_style": "1,2,3", "label": None}]}},
    }
    raw = feature_rows(resp, limit=10, compact=False)
    assert raw["items"][0]["dma_style"] == "1,2,3"
    compact = feature_rows(resp, limit=10, compact=True)
    assert "dma_style" not in compact["items"][0]
    assert "label" not in compact["items"][0]


def test_drop_keys():
    assert drop_keys({"a": 1, "stylesheet": {}, "b": 2}, "stylesheet") == {"a": 1, "b": 2}


def test_failed_text_prefers_msgerr():
    assert failed_text({"MSGERR": "a", "message": {"text": "b"}}) == "a"
