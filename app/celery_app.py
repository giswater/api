"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config import global_settings

logger = logging.getLogger(__name__)

JOBS_QUEUE = "giswater.jobs"

celery_app = Celery("giswater")
celery_app.conf.update(
    broker_url=global_settings.celery_broker_url,
    result_backend=None,
    task_default_queue=JOBS_QUEUE,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "reconcile-stale-jobs": {
            "task": "giswater.reconcile_stale_jobs",
            "schedule": 300.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"], related_name="jobs")
celery_app.autodiscover_tasks(["app.tasks"], related_name="maintenance")


@worker_process_init.connect
def _on_worker_process_init(**_kwargs) -> None:
    from app.tasks.runtime import init_worker

    init_worker()


@worker_process_shutdown.connect
def _on_worker_process_shutdown(**_kwargs) -> None:
    from app.tasks.runtime import shutdown_worker

    shutdown_worker()
