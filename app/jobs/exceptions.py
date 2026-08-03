"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""


class JobError(Exception):
    """Base class for job-related errors."""


class JobNotFoundError(JobError):
    """Raised when a job row does not exist for the given id/tenant."""


class UnknownJobTypeError(JobError):
    """Raised when no registered handler exists for a job type."""


class WorkerAuthError(JobError):
    """Raised when the worker service account cannot obtain a token."""
