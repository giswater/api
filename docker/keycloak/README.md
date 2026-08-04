# Local Keycloak (Swagger OAuth2)

Dev-only IdP so the Swagger **Authorize** buttons work (`keycloakPassword` + `keycloakAuthCode`).

## Start

```bash
docker compose --profile keycloak up -d keycloak
# (docker compose --profile keycloak up -d keycloak also works)
```

First pull is ~500MB; Keycloak needs ~30–60s after `start-dev` before it answers on `:8080`.

- Admin console: http://auth.localhost:8080/admin (`admin` / `admin`)
- Realm: `giswater` (imported from `giswater-realm.json`)
- Test user: `test` / `test`

## Point a tenant at it

In `config/tenants/<id>.env`:

```env
AUTH_MODE=keycloak
KEYCLOAK_URL=http://auth.localhost:8080
KEYCLOAK_REALM=giswater
KEYCLOAK_CLIENT_ID=giswater-api
KEYCLOAK_CLIENT_SECRET=giswater-api-secret
KEYCLOAK_ADMIN_CLIENT_ID=giswater-api-admin
KEYCLOAK_ADMIN_CLIENT_SECRET=giswater-api-admin-secret
KEYCLOAK_CALLBACK_URI=http://localhost:8000/giswater/v1/docs/oauth2-redirect
```

Reload the tenant (restart the app, or `POST ${API_ROOT}/admin/tenants/<id>/reload`).

`auth.localhost` is intentional: browsers resolve `*.localhost` → `127.0.0.1`, while the API container maps it to the host gateway (see `extra_hosts` in `docker-compose.yml`) so both the Swagger redirect and the `/auth/token` proxy reach Keycloak.

## Swagger

1. Open `${API_ROOT}/v1/docs` on a tenant host (or `localhost` with `DEV_ALLOW_TENANT_HEADER=true` + `X-Tenant-ID`).
2. **Authorize** → either:
   - **keycloakPassword**: username `test`, password `test` (client id pre-filled; leave client secret empty — the API proxy injects it).
   - **keycloakAuthCode**: redirects to Keycloak login (`test` / `test`).

## Reset realm

`start-dev` uses an ephemeral store. Recreate the container to re-import:

```bash
docker compose --profile keycloak up -d --force-recreate keycloak
```
