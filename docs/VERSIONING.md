# Versioning policy

There are **three independent version layers**. Keep them separate.

| Layer | Where | Example | Changes when |
| --- | --- | --- | --- |
| API package (semver) | `pyproject.toml` `version`, surfaced as `request.app.version` and in response `version.api` | `1.5.0` | Any release (features, fixes, internal refactors) |
| URL version | HTTP path segment under `${API_ROOT}/vN` | `/giswater/v1/...`, `/giswater/v2/...` | Only on a **breaking HTTP contract** change |
| Per-tenant Giswater DB version | `sys_version.giswater` per tenant schema | `4.8.1` | Independently, per tenant, as DBs are upgraded |

## Guidance

- **Keep semver + a single `/v1` + per-tenant DB readiness.** Do not add `/v1.1`
  or `/v2` mounts for ordinary changes.
- **One codebase serving tenants on different DB versions is normal.** Business
  logic lives in `gw_fct_*` DB functions, not in Python branches. The DB version
  is a *tenant capability*, surfaced via [`/ready`](../app/api/v1/endpoints/system.py)
  and optionally gated by `GISWATER_DB_VERSION_CHECK` /
  `GISWATER_DB_MIN_VERSION` (see [README compatibility](../README.md#compatibility)).
- **Additive Pydantic fields do not need a new URL version.** Adding optional
  response fields or new endpoints is a minor semver bump, still under `/v1`.

## `/v2`

`/v2` exists and is **unreleased**. `API_V2` defaults to `false`. The docs title
is marked `(unreleased)` while `v2` is in `UNRELEASED_API_VERSIONS`
(`app/core/constants.py`). Endpoints on an existing tag (`mincut`, `features`, …)
use that tag's `API_*` toggle. v1 stays the default (`API_V1=true`).

Add another version (v3, v4, …) by:

1. adding `app/api/vN/router.py` with a `ROUTERS` list,
2. appending `"vN"` to `API_VERSIONS`,
3. adding `"vN": vN_router.ROUTERS` to `VERSION_ROUTERS` in `app/main.py`,
4. adding `api_vN: bool = False` on `TenantSettings`.

The env name, admin `api` map, and tenant `.env` writer come from that field.
Put a version in `UNRELEASED_API_VERSIONS` until its contract is stable. Releasing
it is removing it from that set. Run the previous version in parallel for at least
one major cycle before turning its `API_V*` default off.
