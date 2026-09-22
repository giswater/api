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
_GEOM_KEYS = frozenset({"geometry", "the_geom", "thegeom"})
_REDUNDANT_COORD_KEYS = frozenset({"lat", "long", "xcoord", "ycoord"})
DMA_ALIASES = {
    "dmaId": "dma_id",
    "dmaName": "name",
    "explId": "expl_id",
    "macroDmaId": "macrodma_id",
}


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


def rename_keys(obj: Any, aliases: dict[str, str]) -> Any:
    """Rename top-level keys. Unknown keys are kept."""
    if not isinstance(obj, dict):
        return obj
    return {aliases.get(key, key): value for key, value in obj.items()}


def _point_xy(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    if str(value.get("type") or "").lower() == "point":
        coords = value.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
            return float(coords[0]), float(coords[1])
        return None
    nested = value.get("geometry")
    if isinstance(nested, dict):
        return _point_xy(nested)
    coords = value.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
        return float(coords[0]), float(coords[1])
    return None


def drop_geometry(obj: Any) -> Any:
    """Drop GeoJSON / ``the_geom`` blobs. Point geometries become ``x`` / ``y`` first."""
    if isinstance(obj, list):
        return [drop_geometry(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    xy = None
    out: dict[str, Any] = {}
    for key, value in obj.items():
        if str(key).lower() in _GEOM_KEYS:
            if xy is None:
                xy = _point_xy(value)
            continue
        out[key] = drop_geometry(value) if isinstance(value, (dict, list)) else value
    if xy:
        if out.get("x") is None:
            out["x"] = xy[0]
        if out.get("y") is None:
            out["y"] = xy[1]
    return out


def drop_redundant_coords(row: Any) -> Any:
    """Drop ``lat`` / ``long`` / ``xcoord`` / ``ycoord`` when ``coordinates`` is present."""
    if not isinstance(row, dict):
        return row
    coords = row.get("coordinates")
    if not isinstance(coords, dict):
        return row
    if coords.get("x") is None and coords.get("y") is None:
        return row
    return {key: value for key, value in row.items() if key not in _REDUNDANT_COORD_KEYS}


def list_payload(
    items: list | None,
    *,
    limit: int,
    total: int | None = None,
    extra: dict | None = None,
    compact: bool = True,
    aliases: dict[str, str] | None = None,
) -> dict:
    """Unify list tool envelopes: ``items``, ``count`` (page size), optional ``total``, ``truncated``."""
    rows = list(items or [])
    sliced = rows[:limit]
    truncated = total > len(sliced) if total is not None else len(sliced) >= limit
    shaped: list[Any] = []
    for item in sliced:
        row = rename_keys(item, aliases) if aliases else item
        row = drop_geometry(row)
        if compact:
            row = compact_row(row)
        shaped.append(row)
    out: dict[str, Any] = {"items": shaped, "count": len(shaped), "truncated": truncated}
    if total is not None:
        out["total"] = total
    if extra:
        out.update(extra)
    return out


def feature_rows(resp: dict, limit: int, *, compact: bool = True) -> dict:
    """Shape ``/features/*`` list payloads (``data.features``). Server-limited: no ``total``."""
    items = list(unwrap(resp).get("features") or [])
    return list_payload(items, limit=limit, compact=compact)


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
        return drop_redundant_coords(compact_row(drop_geometry(row)))
    flat = dict(row)
    coords = row.get("coordinates")
    if isinstance(coords, dict):
        if flat.get("x") is None and coords.get("x") is not None:
            flat["x"] = coords["x"]
        if flat.get("y") is None and coords.get("y") is not None:
            flat["y"] = coords["y"]
    compacted = compact_row(drop_geometry(flat))
    keep = SUMMARY_KEEP[feature_type]
    return {k: v for k, v in compacted.items() if k in keep}


def list_rows(resp: dict, limit: int) -> dict:
    """Shape getlist-backed payloads (``data.fields``). REST returns the full list; MCP slices."""
    items = list(unwrap(resp).get("fields") or [])
    return list_payload(items, limit=limit, total=len(items))


def one_row(resp: dict, *, compact: bool = True) -> dict:
    """Shape a single-feature payload (``data.feature``)."""
    data = unwrap(resp)
    feature = data.get("feature")
    row = feature if isinstance(feature, dict) else data
    if compact:
        return drop_redundant_coords(compact_row(drop_geometry(row)))
    return row


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


def as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def fc_summary(fc: dict | None, id_key: str | None = None, *, with_bbox: bool = True) -> dict:
    """Summarise a GeoJSON FeatureCollection to counts, ids and bbox."""
    if not isinstance(fc, dict):
        result: dict[str, Any] = {"count": 0, "ids": []}
        if with_bbox:
            result["bbox"] = None
        return result
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
    result = {"count": len(features), "ids": ids}
    if with_bbox:
        result["bbox"] = [min(xs), min(ys), max(xs), max(ys)] if xs and ys else None
    return result
