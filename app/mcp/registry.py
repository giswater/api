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
from dataclasses import dataclass
from typing import Annotated, Any, Callable

from pydantic import Field

CURRENT_MCP_TOOL: ContextVar[str | None] = ContextVar("current_mcp_tool", default=None)

REGISTRY: list[ToolSpec] = []

SchemaName = Annotated[
    str,
    Field(description="Giswater project schema. Call list_schemas first; never guess."),
]


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., Any]
    feature: str | None
    annotations: dict[str, bool]

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
        return bound


def tool(
    *, feature: str | None = None, read_only: bool = False, destructive: bool = False, idempotent: bool | None = None
):
    """Register a curated MCP tool. ``feature`` is a TenantSettings ``api_*`` flag.

    Defaults match the MCP spec: writes are not idempotent; reads are.
    ``openWorldHint`` is always true (tools hit a live Giswater DB).
    """

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
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
            )
        )
        return fn

    return deco
