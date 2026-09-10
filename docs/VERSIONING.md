# Versioning policy

There are **three independent version layers**. Keep them separate.

| Layer | Where | Example | Changes when |
| --- | --- | --- | --- |
| API package (semver) | `pyproject.toml` `version`, surfaced as `request.app.version` and in response `version.api` | `1.5.0` | Any release (features, fixes, internal refactors) |
| URL version | HTTP path segment under `${API_ROOT}/v1` | `/giswater/v1/...` | Only on a **breaking HTTP contract** change |
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

## When to introduce `/v2`

Add a `/v2` mount **only** on a breaking HTTP change, such as:

- changing path parameters or route shapes,
- dropping or renaming response fields clients depend on,
- redesigning the response envelope.

Then run `/v1` and `/v2` in parallel for at least one major cycle before removing
`/v1`. Until such a break is required, all work stays under `/v1`.
