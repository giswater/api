# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`/features` endpoints**: typed filters for nodes/arcs/links/connecs/gullies (list + GeoJSON collection + by-id fields, form, and GeoJSON Feature), gated by `API_FEATURES`.

### Changed

- **`GISWATER_DB_MIN_VERSION`** default raised to **4.17.0** (refactored `gw_fct_getfeatures` with `featureType` / `outputFormat`). Compatibility table: **1.7.x → Giswater DB ≥ 4.17.0**.

### Deprecated

- **`GET /om/dmas/{dma_id}/connecs`**: prefer `GET /features/connecs?dma_id={dma_id}`.

## [1.6.0] - 2026-06-22

### Added

- **Alembic-managed `gwapi` schema** (`alembic/`, `app/db/migrate.py`): the API-owned schema (basic-auth tables + audit logs) is now versioned with plain-SQL migrations instead of runtime DDL. psycopg remains the runtime driver; SQLAlchemy is only the engine Alembic needs. New CLI: `giswater-api db upgrade|current|history`. See [`docs/DATABASE_MIGRATIONS.md`](docs/DATABASE_MIGRATIONS.md).
- **`DB_AUTO_MIGRATE`** (default `true`, no `.env` change required) and **`DB_MIGRATE_TIMEOUT`** (default `30`): control whether `alembic upgrade head` runs per tenant on startup or is deferred to a manual `giswater-api db upgrade` in a maintenance window.
- **Legacy `log` schema compatibility resolver** (`app/db/schema.py` `resolve_log_targets`): audit reads/writes target `gwapi.http_logs` / `gwapi.db_logs` once migrated and transparently fall back to legacy `log.gw_api_logs*` table names until then (`DEPRECATED #28`; removed in 2.0.0).
- Migration integration tests (`tests/test_db_migrations.py`) and CLI `db` smoke tests.

### Changed

- **`app/db/`** — `schema.py` (constants + schema resolver), `partitions.py` (runtime partition DDL), and `migrate.py` (Alembic runner) added; runtime DDL bootstrap (`bootstrap/{log,gwapi}.py`) removed in favor of Alembic.
- **API-owned audit log tables moved from the `log` schema to `gwapi`** (`gwapi.http_logs`, `gwapi.db_logs`; renamed from legacy `gw_api_logs` / `gw_api_logs_db`). On upgrade, the tables and their rows are relocated automatically; 1.6.0 keeps reading/writing `log.gw_api_logs*` until the migration runs, so there is no HTTP/API contract change. `gwapi` is now the single API-owned schema (auth + audit logs).

### Deprecated

- **`log` schema** for API audit tables (`DEPRECATED #28`; removal in **2.0.0**). After upgrading, move any external SQL/reporting that reads `log.gw_api_logs*` to `gwapi.http_logs` / `gwapi.db_logs`.

### Removed

- Runtime DDL bootstrap modules (`app/db/bootstrap/`); schema creation is now handled by Alembic.

### Migration notes

- **1.5.0 -> 1.6.0 with unchanged `.env`:** restart only. Auto-migrate relocates the audit tables into `gwapi`; tenants keep working.
- **Controlled window:** set `DB_AUTO_MIGRATE=false`, deploy, then run `giswater-api db upgrade --all`. The API serves against `log.*` until the upgrade completes.
- Rolling back the image alone is insufficient once a schema move has completed — run `alembic downgrade` or restore from backup first.

## [1.5.0] - 2026-06-19

### Added

- **Service layer** (`app/services/`): business logic extracted from FastAPI routes into HTTP-agnostic services (`ServiceContext`, domain services for basic/CRM/OM/EPA/routing/system/admin). HTTP handlers and the CLI share the same code path.
- **`giswater-api` CLI** (`app/cli/`, Click): console script entry point after `pip install -e .`. Commands:
  - `admin tenants list|get` — platform tenant registry
  - `admin users list|create` — gwapi user management (basic-auth tenants)
  - `tenant --tenant … --schema … ready` — tenant readiness probe (exit code 1 when not ready)
  - `tenant … crm insert-hydrometer` — example tenant-scoped CRM operation
  - Global `--tenants-dir` overrides `TENANTS_DIR` outside the FastAPI lifespan
- **`app/api/exception_handlers.py`**: centralized mapping of service-layer exceptions to HTTP responses (replaces per-route error handling).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (package map, dependency rules, where to add code) and [`docs/VERSIONING.md`](docs/VERSIONING.md) (API/DB versioning policy).
- CLI smoke test (`tests/test_cli_smoke.py`).

### Changed

- **FastAPI-aligned internal layout** (no HTTP path, env var, or behavior changes). `app/` is now split into standard subpackages:
  - `app/api/` — `deps.py` (was `dependencies.py`), `v1/` (`router.py` wiring + `endpoints/` tenant routers), and `admin/` (`tenants.py`, `users.py`, `router.py`).
  - `app/core/` — `config.py`, `constants.py`, `exceptions.py` (dependency-free leaf). `AUTH_MODES` / `DEPRECATED_KEYCLOAK_ENABLED_ISSUE` now live in `core/config.py`, fixing a latent `config`<=>`auth` import cycle.
  - `app/auth/` — `session.py` (was `auth.py`), `keycloak.py`, `users.py` (was `gwapi_users.py`), `schemas.py` (`ApiUser` + gwapi user DTOs), `constants.py`.
  - `app/db/` — `manager.py` (was `database.py`), `context.py`, `execution.py`, `version.py`, `log_store.py`, and `bootstrap/{log,gwapi}.py` (the old `app/schemas.py` DDL).
  - `app/tenancy/` — `registry.py` (was `tenant.py`), `state.py`, `host_middleware.py`.
  - `app/middleware/request_logging.py` (was `app/logging.py`, no longer shadows stdlib `logging`).
  - `app/schemas/` now holds all Pydantic request/response models (was `app/models/`).
  - `app/utils/` slimmed into focused modules: `body.py`, `version.py` (merges `giswater_version.py`), `rate_limit.py`, `plugins.py`, `log_setup.py`, `routing.py`.
- All v1 and admin route handlers are now thin wrappers: `CommonsDep` → `get_service_context()` → service method → JSON response.
- OpenAPI `description` metadata added or improved across admin, system, and tenant endpoints.
- README updated with CLI usage examples and the new package layout.

### Fixed

- Service-layer exceptions are re-raised after handling so FastAPI's registered exception handlers produce the correct HTTP status and body (instead of being swallowed or mapped inline in routes).

### Removed

- `app/api/http_errors.py` (superseded by `exception_handlers.py`).

## [1.4.0] - 2026-06-12

### Added

- Per-tenant **`AUTH_MODE`** (`none` | `basic` | `keycloak`) for tenant API authentication.
- **`basic`** mode: HTTP Basic auth backed by the `gwapi` schema (`gwapi.users`, roles, user CRUD via admin API).
- Unified **`ApiUser`** identity with **`require_role()`** FastAPI dependency.
- [`app/schemas.py`](app/schemas.py) centralizes DDL bootstrap for `log` and `gwapi` schemas.
- Install script for production deployment (single-tenant)

### Deprecated

- **`KEYCLOAK_ENABLED`** per-tenant env var (shim maps to `AUTH_MODE`; removal in **2.0.0**, `# DEPRECATED #22`).
- Admin API top-level **`keycloak`** block (use **`auth.mode`** + **`auth.keycloak`**).

## [1.3.2] - 2026-06-08

### Fixed

- Sector and expl ID fields are lists of integers

## [1.3.1] - 2026-05-28

### Fixed

- Skip DB logging for tenant health probes (`${API_ROOT}/v1/health`), matching global and admin health.

## [1.3.0] - 2026-05-19

### Added

- **`LOG_DB_RESPONSE_MAX_BYTES`** (default `8192`): truncate the raw DB function payload stored in `log.gw_api_logs_db.response_json` (captured by `execute_procedure`). Prevents huge JSON responses from bloating the API DB log table. Set to `0` to disable truncation. Independent from `LOG_DB_MAX_BODY_BYTES`, which only caps HTTP request/response bodies in `log.gw_api_logs`.

## [1.2.0] - 2026-05-19

### Added

- **Single-tenant routing mode** (`SINGLE_TENANT_ID`): when set, all `${API_ROOT}/v1/*` requests resolve to that tenant regardless of `Host`, and `${API_ROOT}/admin/*` is reachable on the same host/IP. Enables IP-only or single-host production deployments without DNS or fake `Host` headers. `BASE_DOMAIN` is ignored for routing in this mode. When unset, DNS-based multi-tenant routing via `BASE_DOMAIN` is unchanged.

### Changed

- **Configurable API root**: all surfaces now live under a single env-driven prefix (`API_ROOT`, default `/giswater`). Tenant API at `${API_ROOT}/v1`, admin at `${API_ROOT}/admin`, global health at `${API_ROOT}/health`, static at `${API_ROOT}/static`. Set `API_ROOT=/gw-api` to keep legacy v1.1 URLs.
- Log viewer (`/logs/ui`) now resolves its static asset URLs from `STATIC_PREFIX` instead of hardcoded `/gw-api/static`.
- `deploy/nginx.conf.example`, `scripts/smoke_test.sh`, and `docker-compose.yml` healthcheck updated to use `${API_ROOT}` (default `/giswater`).
- Public URLs moved from `/gw-api/...` to `/giswater/...` by default. Deployments that need the old paths must set `API_ROOT=/gw-api`; clients, Keycloak callbacks, probes, and any hardcoded URLs must be updated accordingly.

## [1.1.0] - 2026-05-11

### Changed

- Serve everything under `/gw-api`.

## [1.0.0] - 2026-05-07

### Added

- **Production runtime**: `gunicorn` + `uvicorn.workers.UvicornWorker` with `gunicorn.conf.py` (workers from `WEB_CONCURRENCY`, timeouts, max-requests).
- **Logging defaults**: `LOG_HTTP_BODY_CAPTURE` default **on** (bodies truncated via `LOG_DB_MAX_BODY_BYTES`); `LOG_DB_SAMPLE_RATE` default **1.0** for full request audit; response buffering only when capture enabled.
- **DB compatibility gate**: `GISWATER_DB_VERSION_CHECK` / `GISWATER_DB_MIN_VERSION` integrated into tenant `GET /gw-api/v1/ready`.
- **Golden prod env**: `.env.prod.example`; deployment checklist `docs/DEPLOYMENT_CHECKLIST.md`.
- **Post-deploy smoke**: `scripts/smoke_test.sh`; pytest operability smoke (`tests/test_operability.py`).
- **Version parsing helper**: `app/giswater_version.py`.

### Changed

- **Dockerfile** CMD uses Gunicorn instead of bare `uvicorn`.
- **Hot paths**: narrower `psycopg.Error` handling in DB/SQL utilities and admin log queries; routing/Valhalla helpers avoid bare `except`.
- **Documentation**: README deployment, compatibility table for 1.x, logging and probe guidance.

### Security

- Payload retention is truncated and skippable: set `LOG_HTTP_BODY_CAPTURE=false` for metadata-only, or lower `LOG_DB_SAMPLE_RATE` if the DB log table is under pressure.

### Removed

- Runtime `print(...)` usage in favor of structured logging.

## [0.9.0] - 2026-04-08

### Added

- Multi-tenant support (host-based routing, tenant registry, admin API).
- Keycloak admin client id.
- Execute upsert on utils and new upsert endpoint for dscenario objects.

## [0.8.3] - 2026-03-26

### Added

- Github workflow to publish on Docker Hub

### Security

- Bumped `requests` version

## [0.8.2] - 2026-03-25

### Changed

- Dscenario object_id management & various fixes
- App icon

## [0.8.1] - 2026-03-24

### Security

- Bumped dependencies versions

## [0.8.0] - 2026-03-17

### Added

- Scripts to do releases
- pyproject.toml file
- EPA Dscenario endpoints

### Changed

- Profile validation model: node_id/arc_id are integers

## [0.7.0] - 2026-02-10

### Added

- DMA connecs endpoints
- Waterbalance endpoint
- Tests
- Database logging + endpoint to see them

### Changed

- DMA endpoints prefix

### Removed

- Hydraulic engine endpoints

## [0.6.0] - 2026-01-29

### Added

- Toggle valve status endpoint
- Get mincut valves endpoint
- Get mincut dialog endpoint
- Get features from polygon endpoint
- Profile endpoint
- Flow endpoint
- Get arc audit values endpoint

### Changed

- Valve unaccess endpoint
- Message level allowed values
- Linter (ruff)
- Configuration to .env file

## [0.5.0] - 2025-12-11

### Added

- This CHANGELOG file.
- Keycloak authorization support.
- `X-Device` and `X-Lang` headers.
- Functionality on mincut endpoints (start, end, cancel, delete)
- New endpoint: getlist.
- Exception handler class & function.

### Changed

- CI files and workflows.
- Hydrometer models.
- Mincut endpoints to be RESTful.
- Mincut models to be Pydantic objects.
- Mincut parameters & return models following gw_fct_setmincut refactor.
- Group common dependencies.

### Removed

- Deprecated code.
- Unused imports.

## [0.4.0] - 2025-11-05

### Added

- Option to fetch all feature types in getfeaturechanges.
- CRM endpoints and models (6 new endpoints).

### Changed

- Models for getfeaturechanges.
- Type of connecId to int.

## [0.3.4] - 2025-07-10

### Added

- DMA models.
- Fetch DMAs from database.
- Hydrometer models.

### Fixed

- Send parameters properly in getsearch endpoint.

## [0.3.3] - 2025-07-09

### Added

- Support for circular routes.

### Changed

- Start following [SemVer](https://semver.org) properly.
- Geometry field type in GetSelectorsData model.

### Fixed

- getsearch endpoint.
- Procedure call to gw_fct_getfeatures.

## [0.3.2] - 2025-06-27

### Added

- Call to gw_fct_getsearch.

### Changed

- GetFeatureChanges models to include node and connec features.

## [0.3.1] - 2025-06-26

### Added

- Maneuvers support for routing endpoints.

### Changed

- GetFeatureChanges response.

## [0.3.0] - 2025-06-19

### Added

- Routing endpoints.
- Search endpoint.

### Changed

- Group routers by Giswater toolbars.

## [0.2.0] - 2025-06-16

### Added

- Basic endpoint code structure for Features, Hydraulic engine, Mincut
  & Water balance.
- Docker configuration file.
- Plugin support.
- Basic test with pytest.
- Basic CI workflow.

[unreleased]: https://github.com/Giswater/giswater-api/compare/v1.6.0...main
[1.6.0]: https://github.com/Giswater/giswater-api/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/Giswater/giswater-api/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/Giswater/giswater-api/compare/v1.3.2...v1.4.0
[1.3.2]: https://github.com/Giswater/giswater-api/compare/v1.3.1...v1.3.2
[1.3.0]: https://github.com/Giswater/giswater-api/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Giswater/giswater-api/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Giswater/giswater-api/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Giswater/giswater-api/compare/v0.9.0...v1.0.0
[0.9.0]: https://github.com/Giswater/giswater-api/compare/v0.8.3...v0.9.0
[0.8.3]: https://github.com/Giswater/giswater-api/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/giswater/giswater-api/compare/v0.8.1...0.8.2
[0.8.1]: https://github.com/giswater/giswater-api/compare/v0.8.0...0.8.1
[0.8.0]: https://github.com/giswater/giswater-api/compare/v0.7.0...0.8.0
[0.7.0]: https://github.com/giswater/giswater-api/compare/v0.6.0...0.7.0
[0.6.0]: https://github.com/giswater/giswater-api/compare/v0.5.0...0.6.0
[0.5.0]: https://github.com/giswater/giswater-api/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/giswater/giswater-api/compare/v0.3.4...v0.4.0
[0.3.4]: https://github.com/giswater/giswater-api/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/giswater/giswater-api/compare/mv0.3.2...v0.3.3
[0.3.2]: https://github.com/giswater/giswater-api/compare/mv0.3.1...mv0.3.2
[0.3.1]: https://github.com/giswater/giswater-api/compare/mv0.3.0...mv0.3.1
[0.3.0]: https://github.com/giswater/giswater-api/compare/mv0.2.0...mv0.3.0
[0.2.0]: https://github.com/giswater/giswater-api/releases/tag/mv0.2.0
