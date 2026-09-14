"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from app.mcp.registry import REGISTRY
from app.mcp.tools import crm, discovery, epa, features, mapzones, mincut, network  # noqa: F401

__all__ = ["REGISTRY"]
