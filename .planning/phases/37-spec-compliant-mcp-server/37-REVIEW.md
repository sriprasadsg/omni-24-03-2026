---
phase: 37-spec-compliant-mcp-server
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/mcp_server.py
  - backend/mcp_rest_endpoints.py
  - backend/mcp_server_endpoints.py
  - backend/tests/test_mcp_server.py
findings:
  critical: 1
  warning: 2
  info: 4
  total: 7
status: issues_found
---

# Phase 37: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 37 exposes compliance/security data as MCP tools + resources via FastMCP
(stdio + SSE). A thin REST bridge (`mcp_rest_endpoints.py`) lets the in-app UI
call five whitelisted tool coroutines over authenticated HTTP; that bridge is
well-guarded (auth dependency, tenant-context set from the authenticated user,
param-type validation, error mapping). Tool-level input validation on
`list_findings` and `run_cloud_check` is solid — the `limit` check correctly
rejects booleans (`isinstance(raw_limit, bool)`), contrary to first appearance.

The problem is the **MCP protocol surface itself**. Resource handlers take
`tenant_id` straight from the URI and query on it with no authorization
cross-check — a cross-tenant data-leak. The SSE transport handler performs no
authentication and never sets tenant context, so tool coroutines invoked over
SSE run with an unbound tenant. These are only as contained as the transport's
exposure, which is why they must be fixed before ship.

## Critical Issues

### CR-01: Resource templates read `tenant_id` from the URI — cross-tenant IDOR

**File:** `backend/mcp_server.py:131-162`
**Issue:** All three MCP resources bind `tenant_id` from the URI template and
query MongoDB directly on that value, with zero check that the requesting
principal belongs to that tenant:
```python
@mcp.resource("tenant://{tenant_id}/compliance-controls")
async def get_tenant_compliance_controls(tenant_id: str) -> str:
    controls = await mongodb.db.compliance_controls.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=1000)
    return json.dumps(controls, default=str)
```
Any client that can reach the MCP server can request
`tenant://<any-other-tenant>/risks` (or `/evidence`, `/compliance-controls`)
and receive that tenant's full data. This is a classic insecure-direct-object-
reference / broken tenant isolation. Unlike the REST bridge, resources have no
`get_current_user` dependency and no comparison of the URI tenant against the
caller's own tenant.
**Fix:** Derive the tenant from the authenticated MCP session context and reject
(or ignore) a URI tenant that does not match. Do not trust the URI value:
```python
@mcp.resource("tenant://{tenant_id}/risks")
async def get_tenant_risks(tenant_id: str) -> str:
    caller_tenant = get_tenant_id()  # from authenticated session, see WR-01
    if not caller_tenant or tenant_id != caller_tenant:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    ...
```
This depends on WR-01 (the session must actually be authenticated for
`get_tenant_id()` to be trustworthy).

## Warnings

### WR-01: SSE transport is unauthenticated and sets no tenant context

**File:** `backend/mcp_server.py:164-176`
**Issue:** `handle_sse` wires the raw SSE transport straight into
`mcp._mcp_server.run(...)` with no authentication and no `set_tenant_id(...)`
call. Every tool coroutine reads its tenant from `get_tenant_id()`, a contextvar
that this path never populates — so over SSE it resolves to `None`, and queries
become `{"tenantId": None}` (misscoped/empty), while the resource handlers
(CR-01) ignore context entirely. The MCP spec does not mandate auth, so the
server must enforce it; as written, if `handle_sse` is mounted, the tool/resource
surface is reachable without credentials. (It is defined but not obviously
registered in `router_registry.py` — mounting it as-is would be the exploit.)
**Fix:** Authenticate the SSE connection (bearer token in the request), resolve
the user, and `set_tenant_id(user.tenant_id)` before `mcp._mcp_server.run(...)`.
Do not mount `handle_sse` until this is in place.

### WR-02: Stub tools return empty data silently; REST whitelist drifts from tool set

**File:** `backend/mcp_server.py:107-128`, `backend/mcp_rest_endpoints.py:19-25`
**Issue:** Four registered tools — `list_evidence`, `get_compliance_control`,
`get_risk_register`, `get_attack_paths` — are stubs that return `[]`/`{}`
unconditionally. They are advertised over the MCP protocol as working tools, so
an AI client receives an empty-but-successful result and cannot distinguish
"no data" from "not implemented" — a correctness/trust problem for the assistant
consuming them. Separately, `_ALLOWED_TOOLS` hand-maps only five of the nine
tools; when tools are added/renamed in `mcp_server.py`, this map drifts silently.
**Fix:** Either implement the stubs or remove their `@mcp.tool()` registration
until they work. For the bridge, derive the allowed set from a single source
(e.g. a `REST_EXPOSED = {...}` set defined next to the tools) so it cannot drift.

## Info

### IN-01: Dead `tenant_id` variable; `list_frameworks` ignores tenant scope

**File:** `backend/mcp_server.py:30-39`
**Issue:** `list_frameworks` assigns `tenant_id = get_tenant_id()` but never uses
it — the query only returns global (untenanted) frameworks. The REST endpoint
equivalent returns global **plus** the tenant's own frameworks (`$or` with the
tid). The MCP tool is inconsistent and drops tenant-owned frameworks.
**Fix:** Remove the unused variable, or include the tenant's own frameworks to
match REST semantics.

### IN-02: Inconsistent DB access — `db._db.X` vs `db.X`

**File:** `backend/mcp_server.py:32,94` (`db._db.compliance_frameworks`) vs
`46,86,100` (`db.asset_compliance`, `db.cloud_findings`)
**Issue:** Some tools reach through `db._db` (a private attribute), others use
`db` directly. Reaching into `_db` couples the code to the database wrapper's
internals and will break if that private attribute is renamed.
**Fix:** Standardize on one public accessor for all collections.

### IN-03: `handle_sse` uses private `request._send`

**File:** `backend/mcp_server.py:170`
**Issue:** `request._send` is a private Starlette attribute; relying on it is
fragile across framework upgrades.
**Fix:** Use the documented ASGI send channel or the transport's supported API.

### IN-04: `mcp_server_endpoints.py` is effectively empty (dead file)

**File:** `backend/mcp_server_endpoints.py`
**Issue:** Contains only a module docstring, imports, and a logger — no router,
no exports. Dead scaffolding; misleading given its name.
**Fix:** Remove it, or implement the intended endpoints.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
