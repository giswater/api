# Plugins Directory

Place one folder per plugin. Each plugin is loaded at startup on the tenant API surface (`${API_ROOT}/v1`).

## Contract

Every plugin folder must expose:

```python
def register_plugin(app: FastAPI, plugin_id: str) -> None:
    ...
```

`plugin_id` is the folder name (valid Python identifier, e.g. `my_plugin`, not `my-plugin`). It is the same value used in the tenant allowlist.

## Enable per tenant

In `config/tenants/<id>.env`:

```env
ENABLED_PLUGINS=my_plugin,another_plugin
```

Register routers with `register_plugin_router` from `app.api.deps`:

```python
from app.api.deps import register_plugin_router

def register_plugin(app: FastAPI, plugin_id: str) -> None:
    register_plugin_router(app, my_router, plugin_id)
```

## Recommended layout

```
plugins/<name>/
├── __init__.py          # exports register_plugin
├── plugin.py            # router registration
├── config.py            # plugin-specific settings
├── dependencies.py      # FastAPI dependencies
├── routers/             # HTTP layer
├── services/            # business logic, external integrations
├── models/              # Pydantic models
└── README.md
```

## Reference plugin: `gw_api_plus`

See [`gw_api_plus/README.md`](gw_api_plus/README.md) for S3 storage setup, tenant flags, and test commands.

## External example

[giswater-api-example-plugin](https://github.com/Giswater/giswater-api-example-plugin)

## Background jobs

Plugins may register Celery job handlers via `register_plugin_jobs()` in `__init__.py`:

```python
from app.jobs import BaseJob, register_job

@register_job
class MyJob(BaseJob):
    job_type = "my_plugin.my_job"
    max_running_seconds = 600  # reconcile fails after 10 min; omit for JOBS_STALE_AFTER_SECONDS

    async def run(self, ctx, payload, side_effects):
        ...

    async def repair(self, ctx, payload, side_effects):
        ...

def register_plugin_jobs() -> None:
    # import side effect registers MyJob via @register_job
    ...
```

Long-running jobs (e.g. EPANET simulations) should set a generous `max_running_seconds` (e.g. `86400` for 24 h) or `0` to disable stale reconciliation entirely.
