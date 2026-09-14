"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

_ID_KEYS = ("node_id", "arc_id", "connec_id", "gully_id", "link_id", "valve_id", "id")
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
    """Return ``body.data`` from a Giswater envelope; raise on Failed."""
    if not isinstance(resp, dict):
        raise ToolError("Unexpected response from API")
    if resp.get("status") == "Failed":
        raise ToolError(failed_text(resp) or "API request failed")
    body = resp.get("body") or {}
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


def _truncate(items: list, limit: int) -> tuple[list, bool]:
    if limit is None or limit < 0 or len(items) <= limit:
        return items, False
    return items[:limit], True


def _drop_compact_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _DROP_EXACT:
        return True
    return lowered.endswith(_DROP_SUFFIXES)


def compact_row(obj: Any, *, compact: bool = True) -> Any:
    """Drop nulls and QGIS chrome (``*_style``, ``svg``, ``legend``, …)."""
    if not compact:
        return obj
    if isinstance(obj, list):
        return [compact_row(item, compact=True) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out: dict[str, Any] = {}
    for key, value in obj.items():
        if value is None or _drop_compact_key(str(key)):
            continue
        out[key] = compact_row(value, compact=True) if isinstance(value, (dict, list)) else value
    return out


def feature_rows(resp: dict, limit: int, *, compact: bool = True) -> dict:
    """Shape ``/features/*`` list payloads (``data.features``)."""
    data = unwrap(resp)
    items = list(data.get("features") or [])
    page = data.get("pageInfo") or {}
    sliced, truncated = _truncate(items, limit)
    if compact:
        sliced = [compact_row(item) for item in sliced]
    return {"items": sliced, "count": len(sliced), "truncated": truncated, "pageInfo": page or None}


def list_rows(resp: dict, limit: int) -> dict:
    """Shape getlist-backed payloads (``data.fields``)."""
    data = unwrap(resp)
    items = list(data.get("fields") or [])
    sliced, truncated = _truncate(items, limit)
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


def drop_keys(obj: Any, *keys: str) -> Any:
    """Return a shallow copy of ``obj`` without ``keys`` (dicts only)."""
    if not isinstance(obj, dict):
        return obj
    drop = set(keys)
    return {k: v for k, v in obj.items() if k not in drop}
