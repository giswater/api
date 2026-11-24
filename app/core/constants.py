"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

# API surface prefixes (part of the public contract; computed once at import time
# from ``global_settings.api_root``). Override with the ``API_ROOT`` env var; changes
# require a process restart.
from .config import global_settings

API_ROOT = global_settings.api_root
API_VERSIONS = ("v1", "v2")
UNRELEASED_API_VERSIONS = frozenset({"v2"})
TENANT_PREFIXES = {version: f"{API_ROOT}/{version}" for version in API_VERSIONS}
ADMIN_PREFIX = f"{API_ROOT}/admin"
GLOBAL_HEALTH_PATH = f"{API_ROOT}/health"
STATIC_PREFIX = f"{API_ROOT}/static"
