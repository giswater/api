"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""


def load_job_types() -> None:
    """Import core job types and register plugin jobs."""
    from app.utils.plugins import register_plugin_jobs

    register_plugin_jobs()
