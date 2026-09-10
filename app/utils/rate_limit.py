"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

_rate_limit_state: dict[tuple[str, str], deque[float]] = defaultdict(deque)
# threading.Lock: module-level asyncio.Lock breaks across TestClient event loops.
_rate_limit_lock = threading.Lock()


def create_rate_limiter(
    *,
    max_requests: int,
    window_seconds: int,
    scope: str,
) -> Callable[[Any], Awaitable[None]]:
    """
    Create a reusable per-IP rate-limit dependency for FastAPI endpoints.

    Use in routes as: dependencies=[Depends(create_rate_limiter(...))]
    """

    async def rate_limit_dependency(request: Request) -> None:
        if max_requests <= 0 or window_seconds <= 0:
            return

        now = time.monotonic()
        client_ip = request.client.host if request.client else "unknown"
        bucket_key = (scope, client_ip)

        with _rate_limit_lock:
            hits = _rate_limit_state[bucket_key]
            cutoff = now - window_seconds

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= max_requests:
                retry_after = max(1, int(hits[0] + window_seconds - now))
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: max {max_requests} requests per {window_seconds} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            hits.append(now)

    return rate_limit_dependency
