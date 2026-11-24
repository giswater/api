"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, jobs, system
from app.api.v2.endpoints import features
from app.api.v2.endpoints.om import mincut

# None means the router is always mounted (not behind an API_* toggle).
# system, auth and jobs are the v1 routers until one of them needs its own contract.
ROUTERS: list[tuple[APIRouter, str | None]] = [
    (mincut.router, "api_mincut"),
    (features.router, "api_features"),
    (system.router, None),
    (auth.router, None),
    (jobs.router, None),
]
