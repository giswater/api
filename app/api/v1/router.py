"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, basic, cmms, crm, features, jobs, streets, system
from app.api.v1.endpoints.epa import dscenario
from app.api.v1.endpoints.om import flow, mincut, profile, waterbalance
from app.api.v1.endpoints.om.mapzones import dma, dqa, omunit, omzone, presszone, sector
from app.api.v1.endpoints.routing import routing

# None means the router is always mounted (not behind an API_* toggle).
ROUTERS: list[tuple[APIRouter, str | None]] = [
    (basic.router, "api_basic"),
    (streets.router, "api_basic"),
    (features.router, "api_features"),
    (profile.router, "api_profile"),
    (flow.router, "api_flow"),
    (mincut.router, "api_mincut"),
    (waterbalance.router, "api_water_balance"),
    (routing.router, "api_routing"),
    (crm.router, "api_crm"),
    (cmms.router, "api_cmms"),
    (dscenario.router, "api_epa"),
    (dma.router, "api_mapzones"),
    (sector.router, "api_mapzones"),
    (presszone.router, "api_mapzones"),
    (dqa.router, "api_mapzones"),
    (omzone.router, "api_mapzones"),
    (omunit.router, "api_mapzones"),
    (system.router, None),
    (jobs.router, None),
    (auth.router, None),
]
