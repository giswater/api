# Production deployment checklist (v1.0+)

Use with [deploy/install.sh](../deploy/install.sh) (recommended), [deploy/.env.prod.example](../deploy/.env.prod.example), [Environment variables](ENVIRONMENT_VARIABLES.md), and [README.md](../README.md#deployment-notes).

## Before go-live

- [ ] **Install**: run [deploy/install.sh](../deploy/install.sh) or copy [deploy/](../deploy/) templates to `/opt/giswater-api` manually.
- [ ] **TLS** terminates at reverse proxy; certificates valid and auto-renewed.
- [ ] **Routing mode** picked: either DNS multi-tenant (`BASE_DOMAIN` set, `SINGLE_TENANT_ID` empty) or single-tenant (`SINGLE_TENANT_ID=<id>`, no DNS required). `DEV_ALLOW_TENANT_HEADER` stays `false` in production.
- [ ] **DNS multi-tenant only**: `proxy_set_header Host $host;` (tenant id is the left label of the Host); apex `BASE_DOMAIN` → `${API_ROOT}/admin/*`; `*.BASE_DOMAIN` → `${API_ROOT}/v1/*` (default `API_ROOT=/giswater`).
- [ ] **Single-tenant only**: `SINGLE_TENANT_ID` matches an existing `config/tenants/<id>.env`; admin and tenant API both reachable on the same host/IP under `${API_ROOT}/admin/*` and `${API_ROOT}/v1/*`.
- [ ] **Secrets**: `ADMIN_PASSWORD` set; Keycloak secrets not in git; DB password least-privilege.
- [ ] **Postgres / Giswater DB**: version matches [compatibility table](../README.md#compatibility) for this API release; backup/restore tested.
- [ ] **Pool budget**: `N_tenants × DB_POOL_MAX_SIZE` within Postgres `max_connections`.
- [ ] **Logging**: `LOG_DB_SAMPLE_RATE=1.0` for full API request audit; lower if the DB log table becomes hot. Use `LOG_HTTP_BODY_CAPTURE=false` only when you must avoid storing payload text; otherwise bodies are truncated via `LOG_DB_MAX_BODY_BYTES`.
- [ ] **Readiness**: `GISWATER_DB_VERSION_CHECK=true` in prod if you want `/ready` to enforce min Giswater DB; set `GISWATER_DB_MIN_VERSION` to the floor you want.
- [ ] **Gunicorn**: `WEB_CONCURRENCY` set for CPU/RAM; container `start_period` allows pool + DB connect.
- [ ] **Probes**: liveness `GET ${API_ROOT}/health`; readiness per tenant `GET ${API_ROOT}/v1/ready` (503 if DB or version check fails).

## Rollout / rollback

- [ ] Tag image / artifact with app version; keep previous image for quick rollback.
- [ ] **gwapi schema migrations** (see [DATABASE_MIGRATIONS.md](DATABASE_MIGRATIONS.md)):
    - [ ] Back up tenant DBs and note whether a `log` schema exists (`\dn log` in psql).
    - [ ] Choose rollout: default auto-migrate (`DB_AUTO_MIGRATE=true`, runs on startup) or controlled window (`DB_AUTO_MIGRATE=false` + `giswater-api db upgrade --all`).
    - [ ] Post-deploy verify: `giswater-api db current --tenant <id>` and spot-check the admin log endpoints.
    - [ ] Rollback note: if a schema move already completed, rolling back the image alone is insufficient — run `alembic downgrade` or restore from backup first.
- [ ] After deploy: [scripts/smoke_test.sh](../scripts/smoke_test.sh) or `pytest` operability test in CI.

## Ongoing

- [ ] **Log retention** and disk for `LOG_DIR` + API log table growth.
- [ ] **Credential rotation** for DB, admin, Keycloak on a defined schedule.
- [ ] **Upgrade path**: read `CHANGELOG.md` and matching Giswater DB release notes before bumping.
