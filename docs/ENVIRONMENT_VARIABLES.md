# Environment variables

This document is the **reference** for all configuration keys. For a **copy-paste template** of current defaults, use [`.env.example`](../.env.example) (process-wide) and [`config/tenants/example.env`](../config/tenants/example.env) (per tenant).

| Where | File | Loaded by |
| ----- | ---- | --------- |
| Process (global) | `.env` at project root | `load_dotenv()` in [`app/config.py`](../app/config.py) |
| Per tenant | `config/tenants/<tenant_id>.env` | `dotenv_values()` only (does not pollute `os.environ`) |

Boolean env vars accept: `true`, `t`, `yes`, `y`, `1`, `on` (case-insensitive). Empty or unset uses the **default** shown below.

---

## Process-wide (`.env`)

These apply to the whole Python process: routing, logging, admin API, platform Keycloak, and (when using the production Docker image) Gunicorn.

### Deployment modes

Two supported production modes (mutually exclusive):

- **DNS multi-tenant** (default): set `BASE_DOMAIN=example.com`, leave `SINGLE_TENANT_ID` empty. Each tenant lives on `<tenant>.example.com`; admin lives on the apex `example.com`. Requires real DNS.
- **Single tenant** (IP-only or single host): set `SINGLE_TENANT_ID=<id>` (e.g. `main`). All `${API_ROOT}/v1/*` requests resolve to that tenant and `${API_ROOT}/admin/*` is reachable on the same host. `BASE_DOMAIN` is ignored for routing. No DNS required.

`DEV_ALLOW_TENANT_HEADER` is **not** a deployment mode; it is a local/dev convenience and must stay `false` in production.

### Routing

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `BASE_DOMAIN` | `bgeo360.com` | Apex domain (DNS multi-tenant mode only): the bare host (`BASE_DOMAIN`) serves `${API_ROOT}/admin/*`; `tenant.BASE_DOMAIN` serves `${API_ROOT}/v1/*`. Tenant id is the leftmost DNS label (subdomain). Ignored when `SINGLE_TENANT_ID` is set. |
| `SINGLE_TENANT_ID` | _(empty)_ | Enable single-tenant routing for IP-only or single-host deployments. When set (e.g. `main`), every `${API_ROOT}/v1/*` request resolves to this tenant regardless of `Host`, and `${API_ROOT}/admin/*` is reachable on the same host. The value must satisfy the tenant id rules and must not be one of the reserved ids. When unset, the app uses DNS-based multi-tenant routing via `BASE_DOMAIN`. |
| `TENANTS_DIR` | `config/tenants` | Directory containing one `\<id\>.env` per tenant. Files named `example.env`, `sample.env`, `template.env` are ignored for discovery. |
| `API_ROOT` | `/giswater` | Public URL root for every API surface. Tenant API is `${API_ROOT}/v1`, admin `${API_ROOT}/admin`, global liveness `${API_ROOT}/health`, static assets `${API_ROOT}/static`. Accepts `giswater`, `/giswater`, or `/giswater/` (all normalized). Must not be `/`, contain `//`, whitespace, `?`, `#`, or `..`. Set `/gw-api` to keep legacy URLs. Process-wide; change requires restart. |

### Logging

Request logging writes JSON lines to rotating files under `LOG_DIR`, and optionally inserts sampled rows into the tenant database API log table.

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `LOG_LEVEL` | `INFO` | Root logging level for handlers created via `create_log` (e.g. `DEBUG`, `INFO`, `WARNING`). |
| `LOG_DIR` | `logs` | Base directory for API log files (`\<LOG_DIR\>/\<tenant_or_global\>/\<YYYYMMDD\>/`). |
| `LOG_ROTATE_DAYS` | `14` | Number of rotated daily log files to retain. |
| `LOG_DB_ENABLED` | `true` | When `true`, eligible tenant requests may insert rows into the tenant DB API log schema (subject to sample rate). |
| `LOG_DB_SAMPLE_RATE` | `1.0` | Fraction (0–1) of tenant-scoped requests that pass random sampling for **DB** log inserts. `1.0` means every eligible request is considered (typical for QGIS plugin traffic). `0` turns off DB sampling together with `LOG_DB_ENABLED` logic; prefer `LOG_DB_ENABLED=false` to disable DB logging entirely. Lower the rate if the log table becomes a bottleneck. |
| `LOG_HTTP_BODY_CAPTURE` | `true` | When `true`, request/response **payload text** is included for failed requests (`4xx`/`5xx`) with redaction and truncation. Binary/multipart payloads are skipped. When `false`, only metadata (sizes, timing, allowlisted headers, etc.) is logged. |
| `LOG_DB_MAX_BODY_BYTES` | `2048` | Max bytes stored per request/response body when capture is on. `0` uses an internal safe cap (same as 2048-style limit). |
| `LOG_DB_RESPONSE_MAX_BYTES` | `8192` | Max bytes stored in `gwapi.db_logs.response_json` (raw DB function output captured by `execute_procedure`). Separate from `LOG_DB_MAX_BODY_BYTES` because DB payloads are typically much larger than HTTP form bodies. `0` (or negative) disables truncation (full payload stored). |

### Database migrations (`gwapi` schema)

The API owns the `gwapi` schema (basic-auth tables plus audit logs). Its layout is managed by Alembic; see [Database migrations](DATABASE_MIGRATIONS.md).

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DB_AUTO_MIGRATE` | `true` | When `true`, `alembic upgrade head` runs per tenant on load (creating/relocating the `gwapi` schema). Set `false` to defer schema changes to a controlled window and apply them with `giswater-api db upgrade`. The API keeps serving against the legacy `log` schema until the upgrade runs. |
| `DB_MIGRATE_TIMEOUT` | `30` | Seconds allowed for the per-tenant migration during startup. |

### Giswater DB compatibility (readiness)

Used only when evaluating tenant **`GET ${API_ROOT}/v1/ready`** (after the database is reachable).

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `GISWATER_DB_VERSION_CHECK` | `false` | When `true`, readiness compares `{DB_SCHEMA}.sys_version.giswater` to `GISWATER_DB_MIN_VERSION`. Returns **503** if missing or below minimum. |
| `GISWATER_DB_MIN_VERSION` | `4.8.0` | Minimum Giswater DB version string for the check (parsed as dotted numeric components). Align with [README compatibility](../README.md#compatibility). |

### Rate limiting

Applied by dependencies on selected routes (see [`app/utils/utils.py`](../app/utils/utils.py) `create_rate_limiter`).

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `RATE_LIMIT_DEFAULT_MAX_REQUESTS` | `30` | Max requests per client IP per window for default-scoped limiters. |
| `RATE_LIMIT_DEFAULT_WINDOW_SECONDS` | `60` | Sliding window length in seconds. Set `max_requests` or `window_seconds` ≤ `0` in code contexts that honor those knobs to disable (see usages). |

### Admin API (`${API_ROOT}/admin/*`)

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `ADMIN_USER` | `admin` | HTTP Basic user for admin routes. Legacy alias: `LOG_ADMIN_USER`. |
| `ADMIN_PASSWORD` | _(empty)_ | HTTP Basic password; leave unset only in trusted dev environments. Legacy alias: `LOG_ADMIN_PASSWORD`. |
| `ADMIN_RELOAD_ENABLED` | `true` | When `false`, directory-wide tenant reload is refused (gate for `POST /admin/tenants/reload`). |
| `ADMIN_WRITE_ENABLED` | `true` | When `false`, tenant create/update/delete and single-tenant reload mutations are refused. |
| `ADMIN_ARCHIVE_ON_DELETE` | `true` | When `true`, deleting a tenant moves its `.env` to `TENANTS_DIR/_archive/` instead of unlinking. |

### Development

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DEV_ALLOW_TENANT_HEADER` | `false` | When `true`, non-apex hosts may send `X-Tenant-ID` to pick a tenant without DNS-based host matching. **Local/dev only**: never enable in production — use `SINGLE_TENANT_ID` for IP-only single-tenant deployments or DNS routing for multi-tenant. Ignored when `SINGLE_TENANT_ID` is set. |

### Platform Keycloak (admin Bearer auth)

Separate from **per-tenant** Keycloak. Used to validate **`Authorization: Bearer`** on `${API_ROOT}/admin/*` when enabled. Required realm role: **`platform-admin`**. HTTP Basic (`ADMIN_*`) can still be used in parallel.

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `PLATFORM_KEYCLOAK_ENABLED` | `false` | Master switch for JWT validation against the platform IdP. |
| `PLATFORM_KEYCLOAK_URL` | _(empty)_ | Keycloak base URL. |
| `PLATFORM_KEYCLOAK_REALM` | _(empty)_ | Realm name. |
| `PLATFORM_KEYCLOAK_CLIENT_ID` | _(empty)_ | Client id used for API/resource validation context. |
| `PLATFORM_KEYCLOAK_CLIENT_SECRET` | _(empty)_ | Client secret when required by your deployment. |

---

## Gunicorn (production Docker image only)

The [`Dockerfile`](../Dockerfile) starts **`gunicorn -c gunicorn.conf.py`**. These variables are read in [`gunicorn.conf.py`](../gunicorn.conf.py). They are **ignored** when you run **`uvicorn --reload`** locally.

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `GUNICORN_BIND` | `0.0.0.0:8000` | `host:port` passed to Gunicorn `bind`. |
| `WEB_CONCURRENCY` | _(auto)_ | Worker count. If unset or invalid, uses `min(2 × CPU + 1, 8)` with at least **1** worker. |
| `GUNICORN_TIMEOUT` | `120` | Worker silent timeout (seconds) before kill/restart. |
| `GUNICORN_GRACEFUL_TIMEOUT` | `30` | Seconds to finish requests after reload/SIGTERM. |
| `GUNICORN_KEEPALIVE` | `5` | HTTP keep-alive seconds. |
| `GUNICORN_MAX_REQUESTS` | `2000` | Restart worker after this many requests (mitigate leaks). |
| `GUNICORN_MAX_REQUESTS_JITTER` | `200` | Random jitter added to `max_requests`. |
| `GUNICORN_ACCESSLOG` | `-` | Access log destination (`-` = stdout). |
| `GUNICORN_ERRORLOG` | `-` | Error log destination (`-` = stderr). |
| `GUNICORN_LOG_LEVEL` | `info` | Gunicorn’s own log level. |
| `GUNICORN_CAPTURE_OUTPUT` | `true` | When true, forward worker stdout/stderr into Gunicorn error log. |

---

## Per-tenant environment files

One file per tenant: `config/tenants/<tenant_id>.env`. The filename stem is the tenant id and must match the subdomain (`acme` → `https://acme.<BASE_DOMAIN>${API_ROOT}/v1/...`).

**Template with inline comments:** [`config/tenants/example.env`](../config/tenants/example.env).

### API feature toggles

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `API_BASIC` | `false` | Basic GIS/feature endpoints module. |
| `API_PROFILE` | `false` | Profile / trace tools module. |
| `API_FLOW` | `false` | Flow analysis endpoints. |
| `API_MINCUT` | `false` | Mincut operations. |
| `API_WATER_BALANCE` | `false` | Water balance endpoints. |
| `API_MAPZONES` | `false` | Mapzones (DMA, sector, etc.). |
| `API_ROUTING` | `false` | External routing (Valhalla) integration. |
| `API_CRM` | `false` | CRM / hydrometer-style endpoints. |
| `API_EPA` | `false` | EPA / dscenario endpoints. |

### Database

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DB_HOST` | `localhost` | Postgres host. |
| `DB_PORT` | `5432` | Postgres port. |
| `DB_NAME` | `postgres` | Database name. |
| `DB_USER` | `postgres` | Database user. |
| `DB_PASSWORD` | `postgres` | Database password. |
| `DB_SCHEMA` | `public` | Giswater schema for this tenant (functions, `sys_version`, etc.). |
| `DATABASE_URL` | _(optional)_ | If set, overrides individual `DB_*` components for the pool URL (see [`DatabaseManager`](../app/database.py)). |

### Connection pool (per tenant)

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DB_POOL_MIN_SIZE` | `1` | Pool minimum connections. |
| `DB_POOL_MAX_SIZE` | `10` | Pool maximum connections. Total DB load ≈ **tenants × `DB_POOL_MAX_SIZE`**. |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a connection from the pool. |
| `DB_POOL_MAX_WAITING` | `0` | Max queued waiters (psycopg pool). |
| `DB_POOL_MAX_IDLE` | `300` | Seconds before idle connections may be dropped. |
| `DB_CONNECT_TIMEOUT` | `5` | Seconds for initial pool open / connectivity checks. |

### Tenant API authentication

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `AUTH_MODE` | `none` | `none`, `basic`, or `keycloak`. Primary auth mode for `${API_ROOT}/v1/*`. |
| `AUTH_BASIC_BOOTSTRAP_USER` | _(empty)_ | When `AUTH_MODE=basic`, optional first user if `gwapi.users` is empty. |
| `AUTH_BASIC_BOOTSTRAP_PASSWORD` | _(empty)_ | Password for bootstrap user. |

### Keycloak (tenant API)

When **`AUTH_MODE=keycloak`**, tenant routes expect a valid Bearer JWT for that realm. When `none`, anonymous access is allowed for that tenant (still subject to feature toggles).

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `KEYCLOAK_ENABLED` | `false` | **Deprecated** (2.0.0). Shim: `true` → `AUTH_MODE=keycloak`. Prefer `AUTH_MODE`. |
| `KEYCLOAK_URL` | _(required if enabled)_ | Keycloak base URL. |
| `KEYCLOAK_REALM` | _(required if enabled)_ | Realm. |
| `KEYCLOAK_CLIENT_ID` | _(required if enabled)_ | Client id. |
| `KEYCLOAK_CLIENT_SECRET` | _(required if enabled)_ | Client secret. |
| `KEYCLOAK_ADMIN_CLIENT_ID` | _(required if enabled)_ | Admin client (service account / mgmt). |
| `KEYCLOAK_ADMIN_CLIENT_SECRET` | _(required if enabled)_ | Admin client secret. |
| `KEYCLOAK_CALLBACK_URI` | _(required if enabled)_ | Callback URI registered in Keycloak for this client setup. |

**Keycloak client checklist** (for the client named in `KEYCLOAK_CLIENT_ID`, required for Swagger OAuth and the token proxy):

1. *Standard flow* ON — authorization-code button in Swagger UI.
2. *Direct access grants* ON — username/password button in Swagger UI.
3. *Valid redirect URIs* includes `https://<tenant>.<BASE_DOMAIN>${API_ROOT}/v1/docs/oauth2-redirect` (in addition to `KEYCLOAK_CALLBACK_URI` if used elsewhere).
4. An **Audience** protocol mapper with *Included Client Audience* = the same client (`KEYCLOAK_CLIENT_ID`) and *Add to access token* ON. Without it, `verify_token` rejects every token with `401 Invalid token` because Keycloak does not add the client to `aud` automatically.
5. LDAP users authenticate through the realm's LDAP federation provider. The Direct Grant Flow must not force OTP, and the user must have no pending required actions (otherwise use the authorization-code flow).
6. The API issues `SET ROLE <preferred_username>` on DB calls; each user needs a matching PostgreSQL role.

**Local IdP:** `docker compose --profile keycloak up -d keycloak` starts a preconfigured Keycloak on `http://auth.localhost:8080` (realm/client/user ready for Swagger). See [docker/keycloak/README.md](../docker/keycloak/README.md).

---

## See also

- [`.env.example`](../.env.example) — copy-paste root defaults
- [API request examples](API_REQUESTS.md) — curl/httpx for `none` / `basic` / `keycloak` + admin
- [Deployment checklist](DEPLOYMENT_CHECKLIST.md)
- [README – Configuration](../README.md#configuration)
- [README – Compatibility](../README.md#compatibility)
