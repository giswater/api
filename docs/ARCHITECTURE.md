# Architecture

This service is a multi-tenant FastAPI application. Business logic lives in the
Giswater database (`gw_fct_*` functions); the **service layer** marshals requests
to those functions, while the HTTP and CLI layers stay thin wrappers around the
same services. The layout follows the
[FastAPI "Bigger Applications"](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
conventions and the [full-stack template](https://github.com/fastapi/full-stack-fastapi-template)
(`schemas/` = Pydantic; there is no SQLAlchemy `models/` layer).

## Package map

```
app/
  main.py                 # lifespan, the three FastAPI sub-apps, mounts, middleware + handler registration
  api/                    # HTTP layer (uses absolute `from app...` imports)
    deps.py               # CommonsDep, get_service_context, get_schema, require_feature
    exception_handlers.py # register_exception_handlers
    v1/
      router.py           # ROUTER_FEATURES wiring + per-tenant OpenAPI filter
      endpoints/          # thin route handlers; delegate to services/
    admin/
      router.py           # aggregates the admin sub-app routers
      tenants.py          # tenant lifecycle endpoints
      users.py            # gwapi user CRUD endpoints
  services/               # HTTP-agnostic business logic (shared by API + CLI)
    context.py            # ServiceContext, service_context_from_commons
    procedure.py          # run_procedure, ensure_procedure_accepted helpers
    admin/                # tenant_service, user_service
    basic_service.py      # basic GIS endpoints
    features_service.py   # feature collections (nodes/arcs/links/connecs/gullies)
    crm_service.py        # hydrometer CRUD
    om/                   # flow, profile, mincut, dma, mapzones, waterbalance
    epa/                  # dscenario_service
    routing_service.py
    system_service.py
  cli/                    # Click CLI (`giswater-api` console script)
    bootstrap.py          # tenant registry bootstrap, run_service helper
    main.py               # command groups (admin, tenant)
  core/                   # LEAF: no intra-app imports
    config.py             # GlobalSettings / TenantSettings, AUTH_MODES, deprecation constants
    constants.py          # API_ROOT, TENANT_PREFIX, ADMIN_PREFIX, STATIC_PREFIX, GLOBAL_HEALTH_PATH
    exceptions.py         # ProcedureError, DatabaseUnavailableError, InvalidParametersError
  auth/
    __init__.py           # re-exports get_current_user, verify_admin, require_role, ApiUser
    session.py            # token verification, get_current_user, require_role, verify_admin
    keycloak.py           # per-tenant Keycloak IDP builder
    users.py              # basic-auth verification + gwapi user store/bootstrap
    schemas.py            # ApiUser + gwapi user DTOs (Pydantic)
    constants.py          # MIN_PASSWORD_LENGTH
  db/
    manager.py            # DatabaseManager (connection pool, schema validation)
    context.py            # DbIdentity, DB_IDENTITY_CTX, REQUEST_ID_CTX, identity resolution
    execution.py          # execute_procedure, execute_sql*
    version.py            # get_db_version (DB query)
    log_store.py          # insert_api_log, insert_api_db_log
    schema.py             # gwapi schema/table constants + resolve_log_targets (legacy log fallback)
    partitions.py         # monthly partition DDL (runtime-managed)
    migrate.py            # Alembic runner + ensure_tenant_database orchestrator
  tenancy/
    registry.py           # Tenant + TenantRegistry
    state.py              # process-global registry / global_logger
    host_middleware.py    # Host header -> tenant resolution
  middleware/
    request_logging.py    # HTTP request logging middleware
  schemas/                # Pydantic request/response models (basic/ crm/ om/ routing/ epa/, admin.py, common.py)
  utils/                  # dependency-light helpers (no DB imports)
    body.py               # create_body_dict, create_api_response, handle_procedure_result
    version.py            # pure version string comparison
    rate_limit.py         # create_rate_limiter
    plugins.py            # load_plugins
    log_setup.py          # create_log, remove_handlers
    routing.py            # Valhalla routing helpers
  static/                 # favicon, logs UI assets
```

## Dependency direction

```
core  <-  everything            (core imports nothing from app)
db / auth / tenancy / schemas / utils  <-  api / middleware / main
```

Rules that keep this acyclic:

- **`core` is a leaf.** It must not import from any other `app.*` package. This is
  why `AUTH_MODES` and `DEPRECATED_KEYCLOAK_ENABLED_ISSUE` live in `core/config.py`
  rather than under `auth/` (a `core.config -> auth -> core.config` cycle otherwise).
- **`db/__init__.py` is empty** (no eager imports), so importing a `db` submodule
  never drags in the whole package.
- The only `db -> auth` edge (bootstrapping the first gwapi user) is a
  **function-local import** inside `ensure_tenant_database` (`db/migrate.py`),
  not a module-level one.
- The `api/` layer uses **absolute imports** (`from app.schemas... import ...`);
  shared layers (`core`, `auth`, `db`, `tenancy`, `utils`, `middleware`) use
  relative imports among themselves.

## Code locations

| Concern | Location |
| --- | --- |
| Tenant HTTP endpoints | `app/api/v1/endpoints/` — handlers call `app/services/`; registered in `app/api/v1/router.py` `ROUTER_FEATURES` |
| Admin HTTP endpoints | `app/api/admin/` with logic in `app/services/admin/`; aggregated in `app/api/admin/router.py` |
| CLI commands | `app/cli/main.py` — invokes the same services as the HTTP routes |
| Request/response models | `app/schemas/<domain>/` or `schemas/common.py` for shared models |
| FastAPI dependencies | `app/api/deps.py` |
| Service-layer exceptions | `app/core/exceptions.py`; HTTP mapping in `app/api/exception_handlers.py` |
| Procedure/body execution | `app/services/procedure.py`, `app/utils/body.py` |
| DB function calls / raw SQL | `app/db/execution.py` |
| Schema migrations (`gwapi`) | `alembic/` (revisions) + `app/db/migrate.py` (runner); see [DATABASE_MIGRATIONS.md](DATABASE_MIGRATIONS.md) |
| Configuration / env vars | `app/core/config.py` (+ `docs/ENVIRONMENT_VARIABLES.md`) |
| Auth modes / roles | `app/auth/` |
| Pure helpers (no DB) | `app/utils/` |

## Error handling

Route handlers call services and let exceptions propagate to `exception_handlers.py`. FastAPI handles request-parameter validation (e.g. `Query`).

| Exception | HTTP | Response body |
| --- | --- | --- |
| `ProcedureError` | 500 | Giswater JSON (`status`, `message`, `version`, `body`) |
| `DatabaseUnavailableError` | 503 | Giswater unavailable payload |
| `InvalidParametersError` | 422 | `{"detail": "..."}` |
| `ValueError` | 400 | `{"detail": "..."}` |
| `LookupError` | 404 | `{"detail": "..."}` |
| `GwapiUserError` | 400/404 | `{"detail": "..."}` |
| `TenantServiceError` | varies | `{"detail": "..."}` |
| `RuntimeError` (routing) | 502/500 | `{"detail": "..."}` |

Handlers live in [`app/api/exception_handlers.py`](app/api/exception_handlers.py) and are registered via `register_exception_handlers()` in `main.py`.

## Request lifecycle (tenant API)

1. `host_middleware` resolves the `Host` header to a `Tenant` and stores it on `request.state`.
2. `request_logging` assigns a request id and records the HTTP log entry.
3. `api/deps.py` builds `CommonsDep` and `get_service_context()`.
4. The route calls a service method.
5. Uncaught service exceptions are mapped by `exception_handlers.py`; successful calls return the service dict as JSON.

## Versioning

See [VERSIONING.md](VERSIONING.md).
