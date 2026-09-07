#!/usr/bin/env bash
# Run the pytest suite the same way .github/workflows/test.yml does:
#   1. Boot the matching ghcr.io/giswater/gw-db image on $DB_PORT.
#   2. Wait for Postgres to be ready.
#   3. Run pytest with the right DB_SCHEMA and marker filter.
#   4. Tear the container down (unless KEEP_DB=1).
#
# Usage:
#   ./scripts/test_local.sh ws         # ws_40 schema, skip 'ud' tests
#   ./scripts/test_local.sh ud         # ud_40 schema, skip 'ws' tests
#   ./scripts/test_local.sh all        # run ws then ud sequentially
#
# Extra pytest args after `--` are forwarded:
#   ./scripts/test_local.sh ws -- -k mincut -x
#
# Env overrides:
#   DOCKER=podman|docker            (auto-detected)
#   DB_PORT=5432                    (host port to publish; conftest reads it
#                                   to render a per-run tenant .env)
#   PG_TAG=main-pg17                (image tag prefix; suffix -ws/-ud appended)
#   PULL=newer|never                (refresh the moving image tag; never = offline)
#   CONTAINER_NAME=gw_db_test
#   KEEP_DB=1                       (don't remove container after tests)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer the project venv: a `pytest` picked up from ~/.local/bin runs against a
# different interpreter and dependency set than CI's `pip install ".[dev]"`.
if [[ -x "${ROOT}/.venv/bin/pytest" ]]; then
  PATH="${ROOT}/.venv/bin:${PATH}"
fi

DOCKER="${DOCKER:-}"
if [[ -z "${DOCKER}" ]]; then
  if command -v podman >/dev/null 2>&1; then DOCKER=podman
  elif command -v docker >/dev/null 2>&1; then DOCKER=docker
  else echo "ERROR: need podman or docker on PATH" >&2; exit 1
  fi
fi

DB_PORT="${DB_PORT:-5432}"
PG_TAG="${PG_TAG:-main-pg17}"
CONTAINER_NAME="${CONTAINER_NAME:-gw_db_test}"

mode="${1:-}"; shift || true
# Strip a leading `--` so callers can pass `./test_local.sh ws -- -k foo` or `./test_local.sh ws -k foo`.
if [[ "${1:-}" == "--" ]]; then shift; fi
extra_args=("$@")

case "${mode}" in
  ws|ud|all) ;;
  *) echo "Usage: $0 {ws|ud|all} [-- pytest args...]" >&2; exit 2 ;;
esac

cleanup() {
  if [[ "${KEEP_DB:-0}" != "1" ]]; then
    "${DOCKER}" rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# pg_isready via `podman exec` only proves Postgres is up *inside* the container.
# Rootless Podman (and sometimes Docker) can lag publishing `-p host:port`; the app
# connects from the host, so we must wait until a real TCP/psycopg handshake works.
wait_host_postgres() {
  local variant="$1"
  local py="${ROOT}/.venv/bin/python"
  [[ -x "$py" ]] || py="python3"
  echo -n "==> [${variant}] waiting for 127.0.0.1:${DB_PORT} (host → container)"
  local i
  for i in $(seq 1 120); do
    if DB_PORT="$DB_PORT" "$py" -c "
import os, sys
try:
    import psycopg
    psycopg.connect(
        host='127.0.0.1',
        port=int(os.environ['DB_PORT']),
        dbname='gw_db',
        user='postgres',
        password='postgres',
        connect_timeout=3,
        sslmode='disable',
    ).close()
except Exception:
    sys.exit(1)
sys.exit(0)
" 2>/dev/null; then
      echo " ready"
      return 0
    fi
    echo -n "."
    sleep 1
  done
  echo
  echo "ERROR: cannot connect to Postgres on 127.0.0.1:${DB_PORT} (tried 120s)." >&2
  echo "Try: ${DOCKER} ps  &&  ${DOCKER} logs ${CONTAINER_NAME}" >&2
  exit 1
}

run_variant() {
  local variant="$1"   # ws | ud
  local schema marker image
  case "${variant}" in
    ws) schema=ws_40; marker="not ud"; image="ghcr.io/giswater/gw-db:${PG_TAG}-ws" ;;
    ud) schema=ud_40; marker="not ws"; image="ghcr.io/giswater/gw-db:${PG_TAG}-ud" ;;
  esac

  echo "==> [${variant}] booting ${image} on :${DB_PORT}"
  "${DOCKER}" rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  # `main-pg17-*` is a moving tag: GH Actions always fetches it fresh, so refresh
  # the local copy too or the suite runs against a stale dump and diverges from CI.
  # PULL=never skips this when offline.
  "${DOCKER}" run -d --rm --name "${CONTAINER_NAME}" \
    --pull="${PULL:-newer}" \
    -p "${DB_PORT}:5432" \
    -e POSTGRES_DB=gw_db \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    "${image}" >/dev/null

  wait_host_postgres "${variant}"

  echo "==> [${variant}] pytest -m \"${marker}\" (DB_SCHEMA=${schema})"
  DB_HOST=127.0.0.1 \
  DB_PORT="${DB_PORT}" \
  DB_NAME=gw_db \
  DB_USER=postgres \
  DB_PASSWORD=postgres \
  DB_SCHEMA="${schema}" \
  pytest -v -m "${marker}" "${extra_args[@]}"
}

if [[ "${mode}" == "all" ]]; then
  run_variant ws
  run_variant ud
else
  run_variant "${mode}"
fi
