"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from app.db.schema import GWAPI_SCHEMA, JOBS_TABLE
from app.jobs.repository import JobRepository
from app.schemas.jobs import JobCreateResponse, JobResultResponse, JobStatusResponse


def test_jobs_imports_use_schema_constants():
    """Job repository must resolve against app.db.schema (not deleted bootstrap)."""
    assert GWAPI_SCHEMA == "gwapi"
    assert JOBS_TABLE == "jobs"
    assert JobRepository is not None
    assert JobStatusResponse is not None
    assert JobCreateResponse is not None
    assert JobResultResponse is not None
