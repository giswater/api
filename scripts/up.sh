#!/usr/bin/env bash
# Start the local stack with Keycloak and print the URLs once both answer.
#
#   ./scripts/up.sh
#
# DOCKER=docker|podman picks the runtime (default: podman if it has compose, else docker).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -t 1 ]]; then
  B=$'\033[1m' D=$'\033[2m' G=$'\033[32m' C=$'\033[36m' R=$'\033[31m' Z=$'\033[0m'
else
  B='' D='' G='' C='' R='' Z=''
fi

step() { printf '%s==>%s %s\n' "$C" "$Z" "$*"; }
die() { printf '%serror%s %s\n' "$R" "$Z" "$*" >&2; exit 1; }

env_get() {
  local key="$1" default="$2" line val
  line="$(grep -E "^${key}=" .env 2>/dev/null | tail -n1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  val="${line#*=}"
  val="${val%$'\r'}"
  val="${val#\"}" val="${val%\"}"
  val="${val#\'}" val="${val%\'}"
  printf '%s' "${val:-$default}"
}

DOCKER="${DOCKER:-}"
if [[ -n "$DOCKER" ]]; then
  COMPOSE=("$DOCKER" compose)
elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
  COMPOSE=(podman compose)
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  die "need podman compose or docker compose on PATH"
fi

[[ -f .env ]] || die "missing .env — cp .env.example .env"

API_ROOT="$(env_get API_ROOT /giswater)"
BASE_DOMAIN="$(env_get BASE_DOMAIN bgeo360.com)"
[[ "$API_ROOT" == /* ]] || API_ROOT="/${API_ROOT}"
API_ROOT="${API_ROOT%/}"

printf '\n%s giswater-api%s\n\n' "$B" "$Z"
step "Starting app, redis, celery, keycloak  (${COMPOSE[*]})"
"${COMPOSE[@]}" --profile keycloak up -d --build

wait_url() {
  local label="$1" url="$2" tries="$3" i
  for i in $(seq 1 "$tries"); do
    if curl -fsS -o /dev/null --max-time 2 "$url"; then
      printf '\r  %s%-12s%s up          \n' "$G" "$label" "$Z"
      return 0
    fi
    printf '\r  %s%-12s%s waiting %3ss' "$D" "$label" "$Z" "$i"
    sleep 1
  done
  printf '\n'
  die "${label} did not answer ${url}"
}

echo
wait_url "api" "http://127.0.0.1:8000${API_ROOT}/health" 90
wait_url "keycloak" "http://auth.localhost:8080/realms/giswater" 180

echo
printf '%sopen%s\n' "$B" "$Z"
printf '  %-12s %s\n' "api" "http://127.0.0.1:8000${API_ROOT}/health"
printf '  %-12s %s\n' "admin" "http://${BASE_DOMAIN}:8000${API_ROOT}/admin/docs"

shopt -s nullglob
found=0
for f in config/tenants/*.env; do
  id="$(basename "$f" .env)"
  [[ "$id" == "example" ]] && continue
  printf '  %-12s %s\n' "docs" "http://${id}.${BASE_DOMAIN}:8000${API_ROOT}/v1/docs"
  found=1
done
if [[ "$found" -eq 0 ]]; then
  printf '  %-12s %s\n' "docs" "http://<tenant>.${BASE_DOMAIN}:8000${API_ROOT}/v1/docs"
fi

printf '  %-12s %s\n' "keycloak" "http://auth.localhost:8080/admin"
printf '  %-12s %sadmin / admin%s\n' "" "$D" "$Z"
printf '  %-12s %stest / test%s\n' "user" "$D" "$Z"
printf '\n%s  %s logs -f app keycloak%s\n\n' "$D" "${COMPOSE[*]} --profile keycloak" "$Z"
