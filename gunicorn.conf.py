"""
Gunicorn config for production ASGI (FastAPI via UvicornWorker).

Override worker count with WEB_CONCURRENCY (integer); otherwise uses min(2 * CPUs + 1, 8).
"""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

try:
    workers = max(1, int(os.environ.get("WEB_CONCURRENCY", "")))
except ValueError:
    cpu = multiprocessing.cpu_count() or 1
    workers = max(1, min(2 * cpu + 1, 8))

worker_class = "uvicorn.workers.UvicornWorker"
# Trust X-Forwarded-* from the Docker bridge. The app is only published on 127.0.0.1.
forwarded_allow_ips = "*"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "200"))

accesslog = os.environ.get("GUNICORN_ACCESSLOG", "-")
errorlog = os.environ.get("GUNICORN_ERRORLOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = os.environ.get("GUNICORN_CAPTURE_OUTPUT", "true").lower() in ("1", "true", "yes", "on")
