"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp.exceptions import ToolError

from app.schemas.features.feature_models import FEATURE_ID_MAP

_ID_KEYS = ("node_id", "arc_id", "connec_id", "gully_id", "link_id", "valve_id", "feature_id", "id")
_DROP_EXACT = {"svg", "legend", "stylesheet"}
_DROP_SUFFIXES = ("_style", "_stylesheet", "_visibility")


def failed_text(resp: dict | None) -> str | None:
    """Extract a human error string from a Giswater Failed envelope."""
    if not isinstance(resp, dict):
        return None
    parts: list[Any] = [resp.get("MSGERR"), resp.get("NOSQLERR")]
    msg = resp.get("message")
    if isinstance(msg, dict):
        parts.append(msg.get("text"))
    elif isinstance(msg, str):
        parts.append(msg)
    return next((str(p) for p in parts if p), None)


def unwrap(resp: dict) -> dict:
    """Return ``body.data`` from a Giswater envelope.

    Failed envelopes are rejected in ``TenantApi._send`` before they reach here.
    """
    if not isinstance(resp, dict):
        raise ToolError("Unexpected response from API")
    body = resp.get("body") or {}
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


def _truncate(items: list, limit: int) -> tuple[list, bool]:
    # Client-truncated: REST returned the full list; MCP slices. `>` is exact.
    if len(items) <= limit:
        return items, False
    return items[:limit], True


def _drop_compact_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _DROP_EXACT:
        return True
    return lowered.endswith(_DROP_SUFFIXES)


def compact_row(obj: Any) -> Any:
    """Drop nulls and QGIS chrome (``*_style``, ``svg``, ``legend``, …)."""
    if isinstance(obj, list):
        return [compact_row(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out: dict[str, Any] = {}
    for key, value in obj.items():
        if value is None or _drop_compact_key(str(key)):
            continue
        out[key] = compact_row(value) if isinstance(value, (dict, list)) else value
    return out


def feature_rows(resp: dict, limit: int, *, compact: bool = True) -> dict:
    """Shape ``/features/*`` list payloads (``data.features``)."""
    data = unwrap(resp)
    items = list(data.get("features") or [])
    page = data.get("pageInfo") or {}
    # Server-limited: REST applied LIMIT. lastPage is floor(total/limit), so a
    # full page is the only signal that more rows may exist.
    truncated = len(items) >= limit
    sliced = items[:limit]
    if compact:
        sliced = [compact_row(item) for item in sliced]
    return {"items": sliced, "count": len(sliced), "truncated": truncated, "pageInfo": page or None}


def page_total(resp: dict) -> int:
    """Exact row total. REST ``lastPage`` is ``floor(total / limit)``, so call with ``limit=1``."""
    data = unwrap(resp)
    last = (data.get("pageInfo") or {}).get("lastPage")
    if isinstance(last, int):
        return last
    return len(data.get("features") or [])


_SUMMARY_SHARED = ("code", "sys_type", "state", "x", "y")
SUMMARY_KEEP: dict[str, frozenset[str]] = {
    "node": frozenset((*_SUMMARY_SHARED, FEATURE_ID_MAP["node"], "node_type")),
    "connec": frozenset((*_SUMMARY_SHARED, FEATURE_ID_MAP["connec"], "connec_type", "customer_code")),
    "gully": frozenset((*_SUMMARY_SHARED, FEATURE_ID_MAP["gully"], "gully_type")),
    "link": frozenset(("link_id", "sys_type", "state", "x", "y", "link_type", "feature_id")),
    "arc": frozenset(
        (
            *_SUMMARY_SHARED,
            FEATURE_ID_MAP["arc"],
            "arc_type",
            "cat_dnom",
            "cat_matcat_id",
            "node_1",
            "node_2",
            "gis_length",
        )
    ),
}


def shape_feature(row: dict, feature_type: str, fields: Literal["id", "summary", "full"] = "summary") -> dict:
    """Project a feature row to ``id`` / ``summary`` / ``full``."""
    if not isinstance(row, dict):
        return row
    id_key = FEATURE_ID_MAP[feature_type]
    if fields == "id":
        value = row.get(id_key)
        return {id_key: value} if value is not None else {}
    if fields == "full":
        return compact_row(row)
    flat = dict(row)
    coords = row.get("coordinates")
    if isinstance(coords, dict):
        if flat.get("x") is None and coords.get("x") is not None:
            flat["x"] = coords["x"]
        if flat.get("y") is None and coords.get("y") is not None:
            flat["y"] = coords["y"]
    compacted = compact_row(flat)
    keep = SUMMARY_KEEP[feature_type]
    return {k: v for k, v in compacted.items() if k in keep}


def list_rows(resp: dict, limit: int) -> dict:
    """Shape getlist-backed payloads (``data.fields``)."""
    data = unwrap(resp)
    items = list(data.get("fields") or [])
    sliced, truncated = _truncate(items, limit)
    sliced = [compact_row(item) for item in sliced]
    return {"items": sliced, "count": len(sliced), "truncated": truncated}


def one_row(resp: dict, *, compact: bool = True) -> dict:
    """Shape a single-feature payload (``data.feature``)."""
    data = unwrap(resp)
    feature = data.get("feature")
    row = feature if isinstance(feature, dict) else data
    return compact_row(row) if compact else row


def fields_to_dict(fields: list | None, *, skip_hidden: bool = False, drop_nulls: bool = False) -> dict:
    """Collapse a ``GwField`` list into ``{columnname: value}``."""
    out: dict[str, Any] = {}
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        if skip_hidden and field.get("hidden"):
            continue
        name = field.get("columnname")
        if not name:
            continue
        value = field.get("value")
        if drop_nulls and value is None:
            continue
        out[str(name)] = value
    return out


def _walk_coords(coords: Any, xs: list[float], ys: list[float]) -> None:
    if not isinstance(coords, (list, tuple)) or not coords:
        return
    if isinstance(coords[0], (int, float)):
        xs.append(float(coords[0]))
        if len(coords) > 1 and isinstance(coords[1], (int, float)):
            ys.append(float(coords[1]))
        return
    for item in coords:
        _walk_coords(item, xs, ys)


def fc_summary(fc: dict | None, id_key: str | None = None) -> dict:
    """Summarise a GeoJSON FeatureCollection to counts, ids and bbox."""
    if not isinstance(fc, dict):
        return {"count": 0, "ids": [], "bbox": None}
    features = fc.get("features") or []
    ids: list[Any] = []
    xs: list[float] = []
    ys: list[float] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        if id_key and id_key in props:
            ids.append(props[id_key])
        else:
            for key in _ID_KEYS:
                if key in props:
                    ids.append(props[key])
                    break
        geom = feat.get("geometry") or {}
        _walk_coords(geom.get("coordinates"), xs, ys)
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs and ys else None
    return {"count": len(features), "ids": ids, "bbox": bbox}
