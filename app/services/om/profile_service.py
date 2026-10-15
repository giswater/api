"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

from typing import List, Optional

from app.services.context import ServiceContext
from app.services.procedure import run_procedure
from app.utils.body import create_body_dict


class ProfileService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx.with_logger(__name__)

    async def create_profile(
        self,
        initial_node_id: int,
        final_node_id: int,
        middle_features: Optional[List[int]],
        links_distance: int,
        scale_eh: int,
        scale_ev: int,
    ) -> dict:
        extras = {
            "initNode": initial_node_id,
            "endNode": final_node_id,
            "midFeatures": middle_features,
            "linksDistance": links_distance,
            "scale": {"eh": scale_eh, "ev": scale_ev},
        }
        body = create_body_dict(device=self.ctx.device, extras=extras, cur_user=self.ctx.user_id)
        return await run_procedure(self.ctx, "gw_fct_getprofilevalues", body)
