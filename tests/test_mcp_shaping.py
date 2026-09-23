"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import pytest
from fastmcp.exceptions import ToolError

from app.mcp.shaping import (
    DMA_ALIASES,
    compact_row,
    drop_geometry,
    drop_redundant_coords,
    failed_text,
    fc_summary,
    feature_rows,
    fields_to_dict,
    list_payload,
    list_rows,
    one_row,
    page_total,
    shape_feature,
    unwrap,
)


def test_unwrap_accepted():
    assert unwrap({"status": "Accepted", "body": {"data": {"a": 1}}}) == {"a": 1}


def test_unwrap_failed_is_extracted_elsewhere():
    # Failed envelopes are rejected in TenantApi._send, not unwrap.
    assert unwrap({"status": "Failed", "MSGERR": "boom", "body": {}}) == {}


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


def test_feature_rows_full_page_is_truncated():
    # REST lastPage is floor(total/limit); 27 of 52 valves reports lastPage=1.
    resp = {
        "status": "Accepted",
        "body": {
            "data": {
                "features": [{"id": i} for i in range(27)],
                "pageInfo": {"currentPage": 1, "lastPage": 1},
            }
        },
    }
    shaped = feature_rows(resp, limit=27)
    assert shaped["count"] == 27
    assert shaped["truncated"] is True


def test_feature_rows_short_page_is_not_truncated():
    resp = {
        "status": "Accepted",
        "body": {
            "data": {
                "features": [{"id": 1}, {"id": 2}],
                "pageInfo": {"currentPage": 1, "lastPage": 0},
            }
        },
    }
    shaped = feature_rows(resp, limit=27)
    assert shaped["count"] == 2
    assert shaped["truncated"] is False


def test_list_rows():
    resp = {
        "status": "Accepted",
        "body": {"data": {"fields": [{"a": 1, "stylesheet": {}}, {"a": 2, "label": None}]}},
    }
    shaped = list_rows(resp, limit=10)
    assert shaped["count"] == 2
    assert shaped["truncated"] is False
    assert shaped["total"] == 2
    assert shaped["items"][0] == {"a": 1}
    assert "label" not in shaped["items"][1]


def test_one_row():
    resp = {"status": "Accepted", "body": {"data": {"feature": {"node_id": 35}}}}
    assert one_row(resp)["node_id"] == 35


def test_fields_to_dict():
    assert fields_to_dict([{"columnname": "node_id", "value": 35, "widgettype": "text"}]) == {"node_id": 35}


def test_fc_summary_falls_back_to_feature_id():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                "properties": {"feature_id": 71, "feature_type": "NODE"},
            }
        ],
    }
    summary = fc_summary(fc)
    assert summary["ids"] == [71]


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
    assert failed_text({"status": "Failed", "message": {"level": 3, "text": "downstream missing"}, "body": {}}) == (
        "downstream missing"
    )


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


def test_compact_row_nested_stylesheet():
    geom = compact_row(
        {
            "type": "FeatureCollection",
            "legend": "x",
            "features": [
                {
                    "properties": {"node_id": 1, "stylesheet": {}, "dma_style": "x"},
                    "geometry": {"type": "Point", "coordinates": [1, 2]},
                }
            ],
        }
    )
    assert "legend" not in geom
    assert geom["features"][0]["properties"] == {"node_id": 1}


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


def test_shape_feature_summary_flattens_xy():
    row = {
        "node_id": 1,
        "code": "A",
        "sys_type": "VALVE",
        "state": 1,
        "node_type": "VALVE",
        "dma_id": 2,
        "coordinates": {"x": 1.0, "y": 2.0, "epsg": 25831},
    }
    out = shape_feature(row, "node", "summary")
    assert out == {
        "node_id": 1,
        "code": "A",
        "sys_type": "VALVE",
        "state": 1,
        "node_type": "VALVE",
        "x": 1.0,
        "y": 2.0,
    }


def test_shape_feature_id_only():
    assert shape_feature({"node_id": 1, "code": "A"}, "node", "id") == {"node_id": 1}


def test_page_total_uses_last_page():
    resp = {
        "status": "Accepted",
        "body": {"data": {"features": [{}], "pageInfo": {"currentPage": 1, "lastPage": 52}}},
    }
    assert page_total(resp) == 52


def test_refuse_incompatible_version():
    from app.mcp.client import refuse_incompatible

    with pytest.raises(ToolError, match="4.15"):
        refuse_incompatible({"schema": "old", "giswater": "4.15.0", "project_type": "WS"}, None)


def test_refuse_incompatible_project_type():
    from app.mcp.client import refuse_incompatible
    from app.mcp.registry import ToolSpec

    def list_mincuts():
        pass

    spec = ToolSpec(fn=list_mincuts, feature=None, annotations={}, project_types=frozenset({"WS"}))
    with pytest.raises(ToolError, match="WS-only"):
        refuse_incompatible({"schema": "ud_x", "giswater": "4.17.0", "project_type": "UD"}, spec)


def test_refuse_incompatible_accepts_current():
    from app.mcp.client import refuse_incompatible

    refuse_incompatible({"schema": "ws_x", "giswater": "4.17.0", "project_type": "WS"}, None)


def test_failed_text_prefers_msgerr():
    assert failed_text({"MSGERR": "a", "message": {"text": "b"}}) == "a"


def test_list_payload_total_clears_truncated():
    shaped = list_payload([{"id": 1}], limit=1, total=1)
    assert shaped == {"items": [{"id": 1}], "count": 1, "truncated": False, "total": 1}
    full = list_payload([{"id": i} for i in range(5)], limit=5, total=12)
    assert full["count"] == 5
    assert full["truncated"] is True
    assert full["total"] == 12


def test_list_payload_heuristic_without_total():
    shaped = list_payload([{"id": i} for i in range(5)], limit=5)
    assert "total" not in shaped
    assert shaped["truncated"] is True
    short = list_payload([{"id": 1}], limit=5)
    assert short["truncated"] is False


def test_list_payload_explicit_truncated_overrides_full_page():
    exact = list_payload([{"id": i} for i in range(5)], limit=5, truncated=False)
    assert exact["truncated"] is False
    assert exact["count"] == 5
    assert "total" not in exact
    more = list_payload([{"id": i} for i in range(5)], limit=5, truncated=True)
    assert more["truncated"] is True
    assert "total" not in more


def test_drop_geometry_extracts_point_xy():
    row = drop_geometry(
        {
            "node_id": 1086,
            "the_geom": {
                "crs": {"type": "name", "properties": {"name": "EPSG:25831"}},
                "type": "Point",
                "coordinates": [419133.5, 4576241.1],
            },
        }
    )
    assert "the_geom" not in row
    assert row["x"] == 419133.5
    assert row["y"] == 4576241.1


def test_dma_aliases_in_list_payload():
    shaped = list_payload(
        [{"dmaId": 1, "dmaName": "dma1", "explId": [1], "macroDmaId": 0, "geometry": "POLYGON((0 0))"}],
        limit=10,
        total=1,
        aliases=DMA_ALIASES,
    )
    row = shaped["items"][0]
    assert row["dma_id"] == 1
    assert row["name"] == "dma1"
    assert row["expl_id"] == [1]
    assert row["macrodma_id"] == 0
    assert "geometry" not in row
    assert "dmaId" not in row


def test_drop_redundant_coords():
    row = drop_redundant_coords(
        {
            "node_id": 1,
            "lat": 41.3,
            "long": 2.0,
            "xcoord": 1.0,
            "ycoord": 2.0,
            "coordinates": {"x": 1.0, "y": 2.0, "epsg": 25831},
        }
    )
    assert "lat" not in row
    assert "xcoord" not in row
    assert row["coordinates"]["x"] == 1.0
    assert row["node_id"] == 1


def test_feature_rows_omits_page_info():
    resp = {
        "status": "Accepted",
        "body": {"data": {"features": [{"id": 1}], "pageInfo": {"currentPage": 1, "lastPage": 1}}},
    }
    shaped = feature_rows(resp, limit=10)
    assert "pageInfo" not in shaped
