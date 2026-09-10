# Making API requests

Concrete examples for calling the tenant API under each `AUTH_MODE`, plus the platform admin API.

Defaults used below:

| Placeholder | Example | Notes |
| ----------- | ------- | ----- |
| `API_ROOT` | `/giswater` | From process `.env` |
| Tenant host | `test.bgeo360.localhost` | `<tenant>.<BASE_DOMAIN>` |
| Apex host | `bgeo360.localhost` | Admin only (`BASE_DOMAIN`) |
| Schema | `ws_40` | Required query param on most tenant routes |
| Base URL | `http://127.0.0.1:8000` | Compose binds here |

Common tenant headers (applied by `common_parameters` on feature routes):

| Header | Default | Meaning |
| ------ | ------- | ------- |
| `X-Device` | `5` | `1` Mobile … `5` QGIS Web |
| `X-Lang` | `es_ES` | `es_ES`, `es_CR`, `en_US`, `pt_BR`, `pt_PT`, `fr_FR`, `ca_ES` |

Tenant resolution:

- **DNS multi-tenant**: send a real `Host: <tenant>.<BASE_DOMAIN>` (or hit that hostname).
- **Single-tenant**: set `SINGLE_TENANT_ID=<id>`; Host/DNS not required for routing.
- **Local/dev only**: `DEV_ALLOW_TENANT_HEADER=true` + `X-Tenant-ID: <id>` (never in production).

Probes that skip tenant auth (still need a resolved tenant for `/v1/*`):

```bash
curl -sS "http://127.0.0.1:8000/giswater/health"
curl -sS -H "Host: test.bgeo360.localhost" \
  "http://127.0.0.1:8000/giswater/v1/ready"
```

Feature routes (e.g. `/basic/getlist`) enforce the tenant's `AUTH_MODE`.

---

## Tenant API — `AUTH_MODE=none`

Anonymous access. No `Authorization` header.

```bash
curl -sS \
  -H "Host: test.bgeo360.localhost" \
  -H "X-Device: 5" \
  -H "X-Lang: en_US" \
  "http://127.0.0.1:8000/giswater/v1/basic/getlist?schema=ws_40&tableName=ve_arc"
```

Dev with header routing:

```bash
curl -sS \
  -H "X-Tenant-ID: test" \
  -H "X-Device: 5" \
  -H "X-Lang: en_US" \
  "http://127.0.0.1:8000/giswater/v1/basic/getlist?schema=ws_40&tableName=ve_arc"
```

```python
import httpx

r = httpx.get(
    "http://127.0.0.1:8000/giswater/v1/basic/getlist",
    params={"schema": "ws_40", "tableName": "ve_arc"},
    headers={
        "Host": "test.bgeo360.localhost",
        "X-Device": "5",
        "X-Lang": "en_US",
    },
)
r.raise_for_status()
print(r.json())
```

---

## Tenant API — `AUTH_MODE=basic`

HTTP Basic against `gwapi.users` in the tenant DB. Bootstrap the first user with `AUTH_BASIC_BOOTSTRAP_USER` / `AUTH_BASIC_BOOTSTRAP_PASSWORD`, or create users via `${API_ROOT}/admin/tenants/{id}/users`.

```bash
curl -sS \
  -u 'alice:s3cretPass!' \
  -H "Host: test.bgeo360.localhost" \
  -H "X-Device: 5" \
  -H "X-Lang: en_US" \
  "http://127.0.0.1:8000/giswater/v1/basic/getlist?schema=ws_40&tableName=ve_arc"
```

Equivalent explicit header:

```bash
# Authorization: Basic base64(user:pass)
curl -sS \
  -H "Authorization: Basic $(printf '%s' 'alice:s3cretPass!' | base64 -w0)" \
  -H "Host: test.bgeo360.localhost" \
  -H "X-Device: 5" \
  -H "X-Lang: en_US" \
  "http://127.0.0.1:8000/giswater/v1/basic/getlist?schema=ws_40&tableName=ve_arc"
```

```python
import httpx

r = httpx.get(
    "http://127.0.0.1:8000/giswater/v1/basic/getlist",
    params={"schema": "ws_40", "tableName": "ve_arc"},
    headers={
        "Host": "test.bgeo360.localhost",
        "X-Device": "5",
        "X-Lang": "en_US",
    },
    auth=("alice", "s3cretPass!"),
)
r.raise_for_status()
print(r.json())
```

Missing/invalid credentials → **401** with `WWW-Authenticate: Basic realm="tenant"`.

Each user's `db_role` must exist as a PostgreSQL role (`SET ROLE` on the request).

---

## Tenant API — `AUTH_MODE=keycloak`

Send a Bearer JWT issued by that tenant's Keycloak realm. The API validates RS256 locally against the tenant IDP public key (audience = tenant `KEYCLOAK_CLIENT_ID`).

Swagger UI at `${API_ROOT}/v1/docs` exposes **Authorize** with two OAuth2 flows (`keycloakPassword` and `keycloakAuthCode`) backed by the tenant token proxy below. You can also obtain tokens directly from Keycloak.

### 1. Obtain a token via the tenant API proxy

The proxy injects `KEYCLOAK_CLIENT_ID` / `KEYCLOAK_CLIENT_SECRET` server-side. Callers never send the client secret.

**Password grant** (realm or LDAP user):

```bash
curl -sS -X POST \
  -H "Host: test.bgeo360.localhost" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=alice" \
  -d "password=s3cretPass!" \
  "http://127.0.0.1:8000/giswater/v1/auth/token"
```

**Authorization code exchange** (after browser redirect from Keycloak):

```bash
curl -sS -X POST \
  -H "Host: test.bgeo360.localhost" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=..." \
  -d "redirect_uri=https://test.example.com/giswater/v1/docs/oauth2-redirect" \
  -d "code_verifier=..." \
  "http://127.0.0.1:8000/giswater/v1/auth/token"
```

**Refresh token**:

```bash
curl -sS -X POST \
  -H "Host: test.bgeo360.localhost" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=..." \
  "http://127.0.0.1:8000/giswater/v1/auth/token"
```

Returns Keycloak's JSON body verbatim (`access_token`, `expires_in`, `refresh_token`, …) or OAuth2 errors (`error`, `error_description`).

### 2. Obtain a token directly from Keycloak (alternative)

```bash
KEYCLOAK_URL="https://idp.example.com"
REALM="acme"
CLIENT_ID="giswater-api"
CLIENT_SECRET="***"

TOKEN=$(curl -sS -X POST \
  "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "username=alice" \
  -d "password=s3cretPass!" \
  | jq -r .access_token)
```

Use whatever grant your client allows (`password`, `client_credentials`, auth code + refresh, etc.). The API only cares about a valid access token.

### 3. Call the tenant API

```bash
curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Host: test.bgeo360.localhost" \
  -H "X-Device: 5" \
  -H "X-Lang: en_US" \
  "http://127.0.0.1:8000/giswater/v1/basic/getlist?schema=ws_40&tableName=ve_arc"
```

```python
import httpx

token = "…"  # from Keycloak token endpoint
r = httpx.get(
    "http://127.0.0.1:8000/giswater/v1/basic/getlist",
    params={"schema": "ws_40", "tableName": "ve_arc"},
    headers={
        "Host": "test.bgeo360.localhost",
        "Authorization": f"Bearer {token}",
        "X-Device": "5",
        "X-Lang": "en_US",
    },
)
r.raise_for_status()
print(r.json())
```

Missing/invalid Bearer → **401**. Roles come from JWT `realm_access.roles` and `resource_access.<client_id>.roles`; the DB role used for `SET ROLE` is the token's `preferred_username` (or `sub`).

---

## Platform admin API (`${API_ROOT}/admin/*`)

Admin lives on the **apex** host in DNS multi-tenant mode (`Host: BASE_DOMAIN`). In single-tenant mode it shares the same host as `/v1`.

Either auth path works (checked independently):

### HTTP Basic (`ADMIN_USER` / `ADMIN_PASSWORD`)

```bash
curl -sS \
  -u 'admin:CHANGE_ME' \
  -H "Host: bgeo360.localhost" \
  "http://127.0.0.1:8000/giswater/admin/tenants"
```

### Platform Keycloak Bearer (`PLATFORM_KEYCLOAK_*`)

Token must include role `platform-admin` (realm or client role).

```bash
PLATFORM_URL="https://idp.example.com"
PLATFORM_REALM="platform"
PLATFORM_CLIENT_ID="giswater-platform"
PLATFORM_CLIENT_SECRET="***"

ADMIN_TOKEN=$(curl -sS -X POST \
  "${PLATFORM_URL}/realms/${PLATFORM_REALM}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=${PLATFORM_CLIENT_ID}" \
  -d "client_secret=${PLATFORM_CLIENT_SECRET}" \
  -d "username=ops" \
  -d "password=***" \
  | jq -r .access_token)

curl -sS \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Host: bgeo360.localhost" \
  "http://127.0.0.1:8000/giswater/admin/tenants"
```

Manage basic-auth users for a tenant (tenant must have `AUTH_MODE=basic`):

```bash
curl -sS -u 'admin:CHANGE_ME' \
  -H "Host: bgeo360.localhost" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"s3cretPass!","db_role":"role_basic","roles":["role_basic"]}' \
  "http://127.0.0.1:8000/giswater/admin/tenants/test/users"
```

---

## Quick reference

| Surface | Config | Request auth |
| ------- | ------ | ------------ |
| Tenant `/v1/*` | `AUTH_MODE=none` | None |
| Tenant `/v1/*` | `AUTH_MODE=basic` | `Authorization: Basic …` |
| Tenant `/v1/*` | `AUTH_MODE=keycloak` | `Authorization: Bearer <tenant JWT>` |
| Admin `/admin/*` | `ADMIN_*` | `Authorization: Basic …` |
| Admin `/admin/*` | `PLATFORM_KEYCLOAK_ENABLED=true` | `Authorization: Bearer <platform JWT>` (+ `platform-admin`) |

OpenAPI: tenant docs at `http://<tenant>.<BASE_DOMAIN>:8000${API_ROOT}/v1/docs`; admin at `http://<BASE_DOMAIN>:8000${API_ROOT}/admin/docs`.

See also: [README – Authentication](../README.md#authentication), [Environment variables](ENVIRONMENT_VARIABLES.md).
