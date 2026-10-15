"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import functools
import inspect
from contextvars import ContextVar
from dataclasses import dataclass, fields
from typing import Annotated, Any, Callable

from pydantic import Field

from app.core.config import TenantSettings

CURRENT_MCP_TOOL: ContextVar[str | None] = ContextVar("current_mcp_tool", default=None)

REGISTRY: list[ToolSpec] = []

DEFAULT_LIMIT = 50
DENSE_LIMIT = 100
MAX_LIMIT = 500

_TENANT_SETTING_FIELDS = {f.name for f in fields(TenantSettings)}

SchemaName = Annotated[
    str,
    Field(description="Giswater project schema. Call list_schemas first; never guess."),
]


def clamp_limit(limit: int) -> int:
    return min(max(limit, 1), MAX_LIMIT)


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., Any]
    feature: str | None
    annotations: dict[str, bool]
    project_types: frozenset[str] | None = None

    def bind(self, api: Any) -> Callable[..., Any]:
        """Bind ``api`` as the first argument and hide it from the MCP schema."""
        sig = inspect.signature(self.fn)
        params = list(sig.parameters.values())[1:]
        new_sig = sig.replace(parameters=params)

        @functools.wraps(self.fn)
        async def bound(*args: Any, **kwargs: Any) -> Any:
            token = CURRENT_MCP_TOOL.set(self.fn.__name__)
            try:
                return await self.fn(api, *args, **kwargs)
            finally:
                CURRENT_MCP_TOOL.reset(token)

        bound.__signature__ = new_sig  # type: ignore[attr-defined]
        anns = dict(getattr(bound, "__annotations__", {}))
        anns.pop("api", None)
        bound.__annotations__ = anns
        return bound


def spec_by_name(name: str | None) -> ToolSpec | None:
    if not name:
        return None
    return next((spec for spec in REGISTRY if spec.fn.__name__ == name), None)


def tool(
    *,
    feature: str | None = None,
    read_only: bool = False,
    destructive: bool = False,
    idempotent: bool | None = None,
    project_types: set[str] | frozenset[str] | None = None,
):
    """Register a curated MCP tool. ``feature`` is a TenantSettings ``api_*`` flag.

    Defaults match the MCP spec: writes are not idempotent; reads are.
    ``openWorldHint`` is always true (tools hit a live Giswater DB).
    ``project_types`` restricts the tool to WS and/or UD schemas (enforced at call time).
    """

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        if feature is not None and feature not in _TENANT_SETTING_FIELDS:
            raise ValueError(f"Unknown tenant feature flag {feature!r} on {fn.__name__}")
        types = frozenset(t.upper() for t in project_types) if project_types else None
        if types:
            restriction = f"Restricted to {'/'.join(sorted(types))} schemas."
            doc = (fn.__doc__ or "").rstrip()
            fn.__doc__ = f"{doc}\n\n{restriction}" if doc else restriction
        REGISTRY.append(
            ToolSpec(
                fn,
                feature,
                {
                    "readOnlyHint": read_only,
                    "destructiveHint": destructive,
                    "idempotentHint": read_only if idempotent is None else idempotent,
                    "openWorldHint": True,
                },
                types,
            )
        )
        return fn

    return deco
