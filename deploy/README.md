# Production deployment (single-tenant)

Interactive installer for Debian/Ubuntu servers with Docker. Creates `/opt/giswater-api` with:

- `docker-compose.yml` — published image, log volume fix, loopback bind
- `.env` — `SINGLE_TENANT_ID=main`, admin password, image tag
- `config/tenants/main.env` — Postgres + optional Keycloak
- `docker-entrypoint.sh` — ensures `/app/logs` is writable

## Quick start

From any directory on the server:

```bash
curl -fsSL https://raw.githubusercontent.com/Giswater/giswater-api/main/deploy/install.sh | sudo bash
```

Pin deploy templates to a release (`docker-compose.yml`, entrypoint, env examples — separate from the Docker image tag prompt):

```bash
GISWATER_API_REF=v1.3.2 curl -fsSL https://raw.githubusercontent.com/Giswater/giswater-api/main/deploy/install.sh | sudo bash
```

Or download first:

```bash
wget -O install.sh https://raw.githubusercontent.com/Giswater/giswater-api/main/deploy/install.sh
chmod +x install.sh
sudo GISWATER_API_REF=v1.3.2 ./install.sh
```

## What the installer asks

| Prompt | Purpose |
|--------|---------|
| Public URL / IP | Printed endpoints; default Keycloak callback |
| Docker image tag | `GISWATER_API_TAG` — which image to pull from Docker Hub (default `latest`) |
| Admin password | HTTP Basic for `${API_ROOT}/admin/*` |
| DB connection | Host, port, name, user, password, schema |
| Keycloak (optional) | Per-tenant auth for `${API_ROOT}/v1/*` |

When Postgres runs on the same host as Docker, use **`host.docker.internal`** as DB host (default).

**Existing install with `Permission denied` on `main.env`?** The tenant file must be readable by the container user:

```bash
sudo chmod 644 /opt/giswater-api/config/tenants/main.env
cd /opt/giswater-api && docker compose restart app
```

## Manual setup

```bash
sudo mkdir -p /opt/giswater-api/config/tenants
cd /opt/giswater-api
# copy deploy/docker-compose.yml, docker-entrypoint.sh,
#       deploy/.env.prod.example → .env,
#       deploy/main.env.example → config/tenants/main.env
# edit secrets, then:
chmod 600 .env
chmod 755 config config/tenants
chmod 644 config/tenants/*.env
docker compose pull && docker compose up -d
```

## Files

| File | Role |
|------|------|
| [docker-compose.yml](docker-compose.yml) | Production Compose (no local build) |
| [docker-entrypoint.sh](docker-entrypoint.sh) | Fix log volume permissions |
| [.env.prod.example](.env.prod.example) | Root `.env` template |
| [main.env.example](main.env.example) | Single-tenant `main.env` template |
| [nginx.conf.example](nginx.conf.example) | Reverse proxy (single-tenant block at bottom) |
| [install.sh](install.sh) | Interactive installer |

## Upgrade

```bash
cd /opt/giswater-api
# bump GISWATER_API_TAG in .env, or re-run install.sh with GISWATER_API_REF
docker compose pull && docker compose up -d
```

Production Compose runs `app`, `redis`, `celery-worker`, and `celery-beat`. Set `CELERY_BROKER_URL=redis://redis:6379/0` in `.env` (default in compose).

See also [docs/DEPLOYMENT_CHECKLIST.md](../docs/DEPLOYMENT_CHECKLIST.md) and [docs/ENVIRONMENT_VARIABLES.md](../docs/ENVIRONMENT_VARIABLES.md).
