---
phase: 22-api-extensions
reviewed: 2026-07-03T22:57:55Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/mcp_server_endpoints.py
  - backend/ocsf_endpoints.py
  - backend/cloud_checks_service.py
  - backend/scripts/omni-cli.py
  - backend/router_registry.py
  - components/ApiExtensionsDashboard.tsx
findings:
  critical: 3
  warning: 6
  info: 2
  total: 11
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-07-03T22:57:55Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the four API-extension features (MCP protocol server, OCSF export, DigitalOcean cloud checks, CLI tool) plus the dashboard wiring against `.planning/phases/22-api-extensions/22-01-PLAN.md`'s must-haves. `router_registry.py` correctly registers both new routers and is otherwise clean.

The most severe finding is that `backend/scripts/omni-cli.py` does not implement the plan's explicit must-have — "a Click CLI" — at all (no `import click` anywhere in the file), and its hand-rolled parser cannot handle `--flag value` syntax. All three CLI invocations given verbatim in the plan's objective (`scan cloud --provider digitalocean --account-id 12345`, `findings list --severity high --limit 10`, `score --framework soc2`) silently produce wrong API calls with no error. This was independently reproduced by tracing/executing the parsing logic (see CR-01).

Beyond that, `mcp_server_endpoints.py`'s `execute_tool()` accepts an entirely untyped `dict` body and splices several of its values (`control_id`, `account_id`, `severity`) directly into MongoDB filter documents with no type/shape validation, which is a NoSQL query-operator injection vector (CR-02), and separately fails to validate the `limit` parameter's type/sign before calling `min()` and Motor's `to_list()`, both of which raise unhandled exceptions on malformed input (WR-01). The MCP `run_cloud_check` tool also skips the `aws/azure/gcp` provider allowlist that the equivalent REST endpoint (`cloud_checks_endpoints.py`) enforces, which can violate the coverage-percentage invariant documented in `cloud_checks_service.py` (WR-02). The DigitalOcean check set silently substitutes an unlisted check for the plan's explicitly-named "snapshot retention" check (WR-03). The dashboard's OCSF export buttons don't check response status before treating an error body as a successful download (WR-04).

## Critical Issues

### CR-01: CLI is not a Click CLI and cannot parse the plan's own example invocations

**File:** `backend/scripts/omni-cli.py:1-91` (see especially lines 67-86)
**Issue:** The plan's must-have requires "a Click CLI" (`.planning/phases/22-api-extensions/22-01-PLAN.md:24,67`) with example invocations using `--flag value` syntax:
```
python omni-cli.py scan cloud --provider digitalocean --account-id 12345
python omni-cli.py findings list --severity high --limit 10
python omni-cli.py score --framework soc2
```
The shipped file has no `import click` (confirmed: `grep -n "import click" backend/scripts/omni-cli.py` matches nothing) and instead does:
```python
cmd = " ".join(sys.argv[1:])
for prefix, fn in sorted(COMMANDS.items(), key=lambda x: -len(x[0])):
    if cmd.startswith(prefix):
        rest = cmd[len(prefix):].strip().split()
        return fn(rest)
```
`rest` is passed to each `cmd_*` handler as a plain positional list (`args[0]`, `args[1]`) — there is no flag parsing at all. Independently reproduced by tracing the exact logic:
```
argv = ['scan', 'cloud', '--provider', 'do']
  -> cmd = 'scan cloud --provider do'
  -> matched prefix 'scan cloud'
  -> rest = ['--provider', 'do']
  -> provider = rest[0] = '--provider'   (WRONG — literal flag string)
  -> account_id = rest[1] = 'do'          (WRONG — this was meant to be the provider value)

argv = ['findings', 'list', '--severity', 'high']
  -> rest = ['--severity', 'high']
  -> sev = rest[0] = '--severity'         (WRONG; 'high' silently discarded)

argv = ['score', '--framework', 'soc2']
  -> rest = ['--framework', 'soc2']
  -> framework = rest[0] = '--framework'  (WRONG; 'soc2' silently discarded)
```
All three of the plan's own documented example commands, run exactly as specified, silently call the backend with a garbage value (the literal flag name) instead of the intended value, and produce no error — `run_cloud_check` gets `provider="--provider"`, which matches no real provider, and the tool reports success/empty results rather than failing loudly. This is a functional must-have that is not met.

Note: `components/ApiExtensionsDashboard.tsx:113-129` documents a *different*, positional-only invocation style (`scan cloud digitalocean`, `findings list high`, `score soc2`) that happens to work with the actual parser — but that only papers over the gap versus the plan's spec; it doesn't fix the missing Click implementation or the missing flag support, and it means the dashboard's own quickstart contradicts the plan's objective section.

**Fix:** Rewrite as an actual Click CLI, e.g.:
```python
import click

@click.group()
def cli(): ...

@cli.group()
def frameworks(): ...

@frameworks.command("list")
def frameworks_list():
    data = _get("/api/compliance/frameworks")
    ...

@cli.group()
def scan(): ...

@scan.command("cloud")
@click.option("--provider", default="digitalocean")
@click.option("--account-id", default="")
def scan_cloud(provider, account_id):
    ...
```
and register the remaining `findings list --severity/--limit` and `score --framework` commands with proper `click.option` flags, matching the plan's documented invocations exactly.

---

### CR-02: MCP `execute_tool` splices unvalidated client JSON directly into MongoDB filters (NoSQL injection)

**File:** `backend/mcp_server_endpoints.py:57-67`
**Issue:** `execute_tool()` accepts `params: dict = Body(default={})` with no schema/type validation, then uses values straight from that dict as MongoDB filter values:
```python
control_id = params.get("control_id")
...
results = await db.asset_compliance.find({"controlId": control_id, "tenantId": tenant_id}, {"_id": 0}).to_list(length=200)
```
and
```python
result = await cloud_checks_service.run_checks(
    params.get("account_id", ""), params.get("provider", ""), tenant_id
)
```
which in turn (`backend/cloud_checks_service.py:65`) does `db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id}, ...)`. Because `control_id`/`account_id` can be any JSON type from the request body (object, array, bool), a caller can submit e.g. `{"control_id": {"$ne": null}}` and have it interpreted by MongoDB as a query operator rather than a literal equality match, widening the intended filter to match every document in the tenant (or, with `$where`, potentially trigger server-side JS evaluation depending on MongoDB configuration). The blast radius is bounded to the caller's own `tenantId` (server-derived from context, not user input), but it still lets any user holding only `view:dashboard` permission bypass the endpoint's documented per-control/per-account scoping and enumerate broader data than the API contract allows, and (via `run_cloud_check`) causes a raw dict/object to be persisted as the literal `accountId` field value in `cloud_check_results` documents (`cloud_checks_service.py:89`, `doc["accountId"] = account_id`), corrupting stored data types for any downstream code that expects `accountId` to be a string.
**Fix:** Validate parameter types before using them in queries — e.g.:
```python
control_id = params.get("control_id")
if not isinstance(control_id, str) or not control_id:
    raise HTTPException(status_code=400, detail="control_id must be a non-empty string")
```
Apply the same `isinstance(..., str)` guard to `account_id`, `provider`, and `severity` before they reach any `db.*.find(...)` call. Prefer a Pydantic model for `params` (or per-tool sub-models) instead of a bare `dict` so FastAPI performs this validation automatically.

---

### CR-03: `list_findings`/`get_control_status` limit input unvalidated — unhandled exception on bad input

**File:** `backend/mcp_server_endpoints.py:72`
**Issue:** `limit = min(params.get("limit", 20), 100)` performs no type or range check on the caller-supplied `limit` before comparing it with `min()`. Verified two failure modes directly:
- String input: `min("50", 100)` raises `TypeError: '<' not supported between instances of 'int' and 'str'` (reproduced locally) — this is unhandled anywhere in the request path, so it propagates to FastAPI's default exception handler and surfaces as an opaque `500 Internal Server Error` instead of a `400` with a clear validation message.
- Negative input: `min(-5, 100) == -5`, which is then passed as `to_list(length=-5)`. Motor's `AsyncIOMotorCursor.to_list` explicitly checks `elif length < 0: raise ValueError("length must be non-negative")` (confirmed by reading the installed `motor` 3.7.1 source) — another unhandled exception surfacing as a bare `500`.

Both are directly reachable by any authenticated caller of `POST /api/mcp/execute/list_findings` with a crafted body (`{"limit": "50"}` or `{"limit": -1}`), i.e. exactly the class of "AI-assistant-supplied param" input this endpoint exists to accept.
**Fix:**
```python
raw_limit = params.get("limit", 20)
if not isinstance(raw_limit, int) or isinstance(raw_limit, bool) or raw_limit < 1:
    raise HTTPException(status_code=400, detail="limit must be a positive integer")
limit = min(raw_limit, 100)
```

## Warnings

### WR-01: `get_control_status` returns a Python `set` — serializes correctly but ordering is nondeterministic

**File:** `backend/mcp_server_endpoints.py:61`
**Issue:** `"statuses": {r.get("status") for r in results}` returns a raw Python `set`. Confirmed FastAPI's `jsonable_encoder` does support sets and converts this to a JSON array without crashing (`jsonable_encoder({"a","b","c"})` → `['a', 'c', 'b']`), so this is not a runtime bug — but the element order is dependent on Python's (randomized, per-process) string hashing, so two identical requests in different server processes can return the `statuses` array in different orders. Callers (including AI assistants consuming this MCP tool) may reasonably assume list/array output has some stable ordering.
**Fix:** `"statuses": sorted({r.get("status") for r in results})` (or `list(...)` at minimum) for deterministic, readable output.

### WR-02: MCP `run_cloud_check` bypasses the provider allowlist enforced by the equivalent REST endpoint

**File:** `backend/mcp_server_endpoints.py:63-68`, `backend/cloud_checks_service.py:34-35,62,78`
**Issue:** `backend/cloud_checks_endpoints.py:73-74` (the direct REST route for the same operation) validates `if payload.provider not in ("aws", "azure", "gcp"): raise HTTPException(400, ...)` before calling `cloud_checks_service.run_checks()`. The MCP tool path does not apply this check — it forwards `params.get("provider", "")` straight through:
```python
result = await cloud_checks_service.run_checks(
    params.get("account_id", ""), params.get("provider", ""), tenant_id
)
```
`cloud_checks_service.py` itself documents (lines 31-35) an explicit invariant: `RUNNABLE_PROVIDERS = ("aws", "azure", "gcp")` and "K8s and DigitalOcean checks are defined but never evaluated by run_checks(), so they must be excluded from the coverage denominator or coverage could never reach 100%." That invariant is only true through the REST path. Via the MCP tool, a caller can pass `"provider": "digitalocean"` (or `"kubernetes"`, or any string) and `run_checks()` will happily filter `CLOUD_CHECKS` for that provider (`cloud_checks_service.py:78`) and persist real `cloud_check_results` documents for it. Those results then get counted in `get_summary()`'s `total` (line 114) while `_RUNNABLE_CHECKS_COUNT`'s denominator still excludes DO/K8s (line 35), meaning `coverage` (line 139) can be pushed above 100% — violating the documented invariant.
**Fix:** Enforce the same allowlist inside `run_checks()` itself (so both call sites are protected), or at minimum replicate the check in `mcp_server_endpoints.py`:
```python
if params.get("provider") not in ("aws", "azure", "gcp"):
    raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")
```

### WR-03: DigitalOcean check set silently drops the plan's required "snapshot retention" check

**File:** `backend/cloud_checks_service.py:15-26`
**Issue:** The plan's must-have (`22-01-PLAN.md:23`) explicitly enumerates 10 required DO checks including "snapshot retention" (`do-*-snapshot`-style). The shipped `DO_CHECKS` list has 10 entries but no snapshot-retention check; instead it contains a second firewall check (`do-fw-002`, "DO Firewall Rules Restrict RDP") that is not named in the must-haves list. The check count (10) matches, masking the substitution, but the specific required control described in the plan is missing entirely.
**Fix:** Replace `do-fw-002` (or add an 11th check and drop a duplicate) with a DO snapshot-retention check, e.g.:
```python
{"id": "do-droplet-002", "name": "DO Droplet Snapshot Retention Configured", "description": "Droplets should have automated snapshots with a defined retention policy", "provider": "digitalocean", "service": "droplet", "severity": "medium", "frameworks": ["NIST-CP-9"], "remediation": "Enable scheduled snapshots with a retention policy on DO Droplets."}
```

### WR-04: OCSF export buttons treat any HTTP response (including errors) as a successful download

**File:** `components/ApiExtensionsDashboard.tsx:39-48`
**Issue:**
```javascript
const exportOcsf = async (endpoint: string, filename: string) => {
  try {
    const res = await authFetch(endpoint);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename;
    a.click(); URL.revokeObjectURL(url);
    showToast(`Exported ${filename}`, 'success');
  } catch { showToast('Export failed', 'error'); }
};
```
`res.ok` is never checked. If `/api/ocsf/findings` or `/api/ocsf/cloud-checks` returns a non-2xx status (e.g. `401` if the session expired, `500` on a backend error), `res.blob()` still resolves successfully (it just contains the JSON error body), so the code downloads a file named `findings-ocsf.json` containing `{"detail": "..."}` and shows a green "Exported findings-ocsf.json" success toast — misleading the user into thinking the export succeeded.
**Fix:**
```javascript
const res = await authFetch(endpoint);
if (!res.ok) throw new Error(`Export failed (${res.status})`);
const blob = await res.blob();
```

### WR-05: MCP tool execution UI doesn't distinguish failed tool calls from successful ones

**File:** `components/ApiExtensionsDashboard.tsx:26-37`
**Issue:** `runTool()` calls `.json()` on the raw fetch response without checking `res.ok`. `execute_tool()` on the backend returns `HTTPException` bodies (e.g. 400 for missing `control_id`, 404 for unknown tool) as JSON, so `.json()` still resolves — the error detail is displayed inside the same neutral result panel as a successful call, with no visual indication (e.g. red border/toast) that the call failed. A user could easily miss that `list_findings` failed validation versus returned zero findings.
**Fix:** Check `res.ok` and route to `showToast(..., 'error')` (or visually flag the result panel) when the tool call fails:
```javascript
const rawRes = await authFetch(`/api/mcp/execute/${name}`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(params) });
const res = await rawRes.json();
if (!rawRes.ok) { showToast(res.detail || 'Tool execution failed', 'error'); }
setToolResult(res);
```

### WR-06: `omni-cli.py` has no error handling for network/HTTP failures

**File:** `backend/scripts/omni-cli.py:16-25`
**Issue:** `_get`/`_post` call `r.raise_for_status()` and neither is wrapped in a `try/except`. Any connectivity failure (backend down, DNS failure, invalid `OMNI_API_TOKEN` producing a 401, `requests.exceptions.ConnectionError`, etc.) will raise an unhandled exception all the way out of `main()`, printing a raw Python traceback to the CLI user instead of a clean, actionable error message — poor UX for what is meant to be a user-facing CLI tool.
**Fix:**
```python
def _get(path: str, params: dict = None):
    try:
        r = requests.get(f"{API_URL}{path}", headers=_headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```
(apply symmetrically to `_post`; also note neither call currently sets a `timeout`, so a hung backend would hang the CLI indefinitely.)

## Info

### IN-01: `_to_epoch` silently substitutes "now" for any malformed timestamp with no logging

**File:** `backend/ocsf_endpoints.py:14-18`
**Issue:**
```python
def _to_epoch(iso_str: str) -> int:
    try:
        return int(datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp())
    except Exception:
        return int(datetime.now(timezone.utc).timestamp())
```
Any parse failure (missing `created_at`/`checked_at`, malformed date, `None` passed to `.replace()`) is swallowed and replaced with the current wall-clock time, with no logging. Since this feeds directly into OCSF `time` fields consumed by downstream SIEMs, silently fabricating a "now" timestamp for bad/missing data could produce misleading time-based correlation in the SIEM with no trace in application logs that a substitution occurred.
**Fix:** At minimum log a warning on the fallback path:
```python
except Exception:
    logger.warning("Failed to parse OCSF timestamp %r, using current time", iso_str)
    return int(datetime.now(timezone.utc).timestamp())
```

### IN-02: `omni-cli.py` requests have no timeout

**File:** `backend/scripts/omni-cli.py:16-25`
**Issue:** `requests.get(...)` / `requests.post(...)` are called with no `timeout=` argument, so a hung/unresponsive backend will cause the CLI to hang indefinitely rather than failing fast.
**Fix:** Add `timeout=30` (or similar) to both calls, as noted in WR-06's fix snippet.

---

_Reviewed: 2026-07-03T22:57:55Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
