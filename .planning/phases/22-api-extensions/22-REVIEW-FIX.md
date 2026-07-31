---
phase: 22-api-extensions
fixed_at: 2026-07-04T13:40:00Z
review_path: .planning/phases/22-api-extensions/22-REVIEW.md
iteration: 1
findings_in_scope: 14
fixed: 14
skipped: 0
status: all_fixed
---

# Phase 22: Code Review Fix Report

**Fixed at:** 2026-07-04T13:40:00Z
**Source review:** .planning/phases/22-api-extensions/22-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 14 (CR-01 through CR-05, WR-01 through WR-06, IN-01 through IN-03 — fix_scope: `--all`)
- Fixed: 14
- Skipped: 0

Note: CR-04, CR-05, and IN-03 were not in the original review pass — they were found during a fresh independent re-audit (prompted by lessons from phase 21's re-review) and folded into `22-REVIEW.md` before this fix pass, raising the finding count from 11 to 14.

## Fixed Issues

### CR-01: CLI is not a Click CLI and cannot parse the plan's own example invocations

**Files modified:** `backend/scripts/omni-cli.py`, `backend/requirements.txt`
**Applied fix:** Rewrote the CLI as a real Click CLI (`@click.group()` with `frameworks`/`scan`/`findings` subgroups and a top-level `score` command), matching the plan's documented invocations exactly (`scan cloud --provider X --account-id Y`, `findings list --severity X --limit Y`, `score --framework X`). Added `click>=8.1.0,<9.0.0` to `requirements.txt` (it was present transitively but never pinned as an explicit dependency).
**Verification:** Used `click.testing.CliRunner` to invoke all three of the plan's example commands verbatim and confirmed the parsed values are now correct (`provider='digitalocean'`, `account_id='12345'`, `severity='high'`, `limit=10`, `framework='soc2'`) — a direct contrast to the old parser, which produced the literal flag-name string as the value.

### CR-02: MCP `execute_tool` splices unvalidated client JSON directly into MongoDB filters (NoSQL injection)

**Files modified:** `backend/mcp_server_endpoints.py`
**Applied fix:** Added `isinstance(..., str)` + non-empty guards on `control_id` (get_control_status), `account_id`/`provider` (run_cloud_check), and `severity` (list_findings) before any value reaches a `db.*.find(...)` call — each now raises `HTTPException(400)` on a non-string/empty value instead of passing it through as a raw MongoDB filter value.
**Verification:** Confirmed `{"control_id": {"$ne": None}}` (a NoSQL query-operator injection attempt) now raises 400 instead of being accepted.

### CR-03: `list_findings`/`get_control_status` limit input unvalidated — unhandled exception on bad input

**Files modified:** `backend/mcp_server_endpoints.py`
**Applied fix:** `limit` is now validated as a non-bool `int >= 1` before `min(raw_limit, 100)`, raising `HTTPException(400)` otherwise.
**Verification:** Confirmed `{"limit": "50"}` (previously an unhandled `TypeError` → bare 500) and `{"limit": -5}` (previously an unhandled `ValueError` from Motor's `to_list` → bare 500) both now raise a clean 400.

### CR-04: `list_frameworks` MCP tool always returned an empty list, for every tenant, permanently

**Files modified:** `backend/mcp_server_endpoints.py`
**Applied fix:** Replaced the `{"tenantId": tenant_id}` filter (a field no writer in the codebase ever sets on this collection) with the same `$or` pattern the real `/api/compliance` route (`compliance_framework_mgmt_endpoints.py`) already uses: match frameworks with no `tenant_id` field (or an empty/null one — global/seeded frameworks) OR `tenant_id` equal to the caller's tenant.
**Verification:** Seeded a mongomock database with a global framework (no tenant field) and a tenant-scoped custom framework under a different tenant; confirmed the tool now returns exactly the global framework plus the caller's own tenant's framework, excluding the other tenant's.

### CR-05: `get_compliance_score` MCP tool ignored the `framework` filter and fabricated per-framework numbers

**Files modified:** `backend/mcp_server_endpoints.py`
**Applied fix:** The tool now looks up the named framework by `id`, 404s if unknown, extracts its `controls[].id` list, and filters `asset_compliance` by `controlId: {"$in": control_ids}` (in addition to the existing `tenantId` filter) before computing `passing`/`total` — instead of aggregating the tenant's entire `asset_compliance` collection regardless of which framework was requested.
**Verification:** Confirmed with two seeded frameworks (different control sets) that requesting each by name now returns genuinely different `score`/`passing`/`total` values instead of byte-identical numbers differing only in the echoed `framework` label; confirmed an unknown framework raises 404.

## Warnings

### WR-01: `get_control_status` returns a Python `set` — serializes correctly but ordering is nondeterministic

**Files modified:** `backend/mcp_server_endpoints.py`
**Applied fix:** `"statuses": sorted({r.get("status") for r in results})` instead of the raw set.
**Verification:** Confirmed the result is a Python `list` in sorted order.

### WR-02: MCP `run_cloud_check` bypasses the provider allowlist enforced by the equivalent REST endpoint

**Files modified:** `backend/mcp_server_endpoints.py`, `backend/cloud_checks_service.py`
**Applied fix:** Enforced the `("aws", "azure", "gcp")` allowlist in two places for defense-in-depth: inside `cloud_checks_service.run_checks()` itself (returns `{"error": ..., "ran": 0}` for any other provider, protecting every current and future caller), and explicitly in the MCP handler (raises `HTTPException(400)` before calling `run_checks()`, giving proper HTTP semantics to API consumers).
**Verification:** Confirmed `run_checks("acc-1", "digitalocean", "tenant-a")` called directly now returns an error dict with `ran: 0` instead of silently persisting `cloud_check_results` for an unsupported provider (which was pushing `coverage` above the documented 100% ceiling); confirmed the MCP tool path raises 400 for the same input.

### WR-03: DigitalOcean check set silently drops the plan's required "snapshot retention" check

**Files modified:** `backend/cloud_checks_service.py`
**Applied fix:** Replaced the duplicate `do-fw-002` ("DO Firewall Rules Restrict RDP", not in the plan's must-haves) with `do-droplet-002` ("DO Droplet Snapshot Retention Configured"), matching the plan's explicitly-named required check.
**Verification:** Confirmed all 10 DO check IDs are unique and `do-droplet-002` is present.

### WR-04: OCSF export buttons treat any HTTP response (including errors) as a successful download

**Files modified:** `components/ApiExtensionsDashboard.tsx`
**Applied fix:** `exportOcsf` now checks `res.ok` and throws before calling `.blob()`, so a non-2xx response (e.g. an expired-session 401 or a backend 500) surfaces the existing error toast instead of downloading a JSON error body as if it were a successful export.

### WR-05: MCP tool execution UI doesn't distinguish failed tool calls from successful ones

**Files modified:** `components/ApiExtensionsDashboard.tsx`
**Applied fix:** `runTool` now captures the raw response before parsing JSON and shows an error toast (using the FastAPI `detail` field where available) when `rawRes.ok` is false, in addition to still displaying the result body.

### WR-06: `omni-cli.py` has no error handling for network/HTTP failures

**Files modified:** `backend/scripts/omni-cli.py`
**Applied fix:** `_get`/`_post` now wrap the request in `try/except requests.exceptions.RequestException`, printing a clean `Error: ...` message to stderr and exiting with code 1 instead of letting a raw Python traceback propagate to the CLI user.

## Info

### IN-01: `_to_epoch` silently substitutes "now" for any malformed timestamp with no logging

**Files modified:** `backend/ocsf_endpoints.py`
**Applied fix:** Added `logger.warning("Failed to parse OCSF timestamp %r, using current time", iso_str)` on the fallback path.
**Verification:** Confirmed the warning is emitted when `_to_epoch` is called with an unparseable string.

### IN-02: `omni-cli.py` requests have no timeout

**Files modified:** `backend/scripts/omni-cli.py`
**Applied fix:** Added `timeout=30` (via a module-level `_TIMEOUT_SECONDS` constant) to both `_get` and `_post`.

### IN-03: Documented MCP tool params silently ignored by their handlers

**Files modified:** `backend/mcp_server_endpoints.py`
**Applied fix:** Removed the unimplemented `framework_id` (get_control_status) and `check_id` (run_cloud_check) params from the published `MCP_TOOLS` schema, since neither handler ever read them and implementing genuine per-framework/per-check filtering was a larger feature addition out of scope for this fix pass. The documented contract now matches actual behavior.

## Skipped Issues

None — all 14 in-scope findings were fixed.

## Notes for follow-up (not fixed, out of scope for this pass)

- `backend/tests/test_cloud_checks_expansion.py` is a 0-byte empty placeholder — none of the 6 files in this phase have any test coverage. Adding tests wasn't one of the review's 14 findings, so it wasn't done here, but is worth a follow-up pass given how many real bugs (CR-01 through CR-05) existed with zero tests to catch them.

---

_Fixed: 2026-07-04T13:40:00Z_
_Fixer: Claude Sonnet 5_
_Iteration: 1_
