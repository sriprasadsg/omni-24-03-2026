# Phase 76: Catalogue Manifest & Backend Route Enforcement - Research

**Researched:** 2026-10-13
**Domain:** FastAPI route-permission enforcement + shared JSON manifest consumed by React/Vite and pytest
**Confidence:** HIGH on measured baselines and mechanics (scripted and probed this session); MEDIUM on the view-to-route mapping (heuristic, must be confirmed while authoring the manifest)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Backend route guards land this phase for the routers behind three sidebar groups: **"Infrastructure & Assets"** (including ITAM), **"Management & Settings"** (users, roles, SSO/LDAP, settings, billing/finops), and **"Security (SecOps)"**. This is the milestone's priority list (Assets, ITAM, Settings, financial, identity, security-operations). Routers behind the other five groups (Dashboards & Insights, Observability, DevSecOps & Engineering, Governance & Compliance, Automation & Intelligence) are recorded in the gap ledger, not guarded.
- **D-02:** Agent-authenticated routes (`/api/agents/*` called by agents via `get_current_user_or_agent`) keep agent auth and get no user-permission guard; enrollment and heartbeat must keep working. Existing API-key callers on ITAM routers must keep working (role check first, then API-key scope narrowing — the existing `_scopes_allow` order).
- **D-03:** Read routes are guarded by the catalogue's `view:X`; write routes keep/require `manage:X`. For read guards, **holding `manage:X` satisfies `view:X`** (the same implication closure Phase 75 D-20 uses for the role-assignment ceiling). Writes still require `manage:X` itself. All checks go through the Phase 75 resolver (`rbac_service.effective_permissions` / `rbac_utils.verify_permission`), never a new table.
- **D-04:** Asset read routes (`/api/assets*`) stay readable with `view:assets`, but for a caller without `view:itam` the finance fields (purchase cost, book value and related purchase/finance fields) are **stripped from the response**. Callers with `view:itam` see them unchanged. This prepares the Phase 78 cost routes, which are gated by `view:itam`.
- **D-05:** **Deny-by-default:** the backend route-parity test fails when an in-scope catalogue route is unguarded, **and** when any router has no permission guard and is not listed in the committed gap ledger. Adding a router therefore requires either a guard or a ledger entry with a stated reason.
- **D-06:** A frontend test fails when the sidebar and the manifest drift (e.g. a nav item with no manifest entry, or a manifest entry with no nav item).

### Claude's Discretion
- Manifest location and format (research suggested `shared/catalogue-access.json` plus a typed `catalogueAccess.ts` reader) and how Vite/vitest import it.
- Gap-ledger file format and location (research suggested `shared/catalogue-gaps.json`), and how each entry states its reason.
- Router-level vs route-level guard placement, and how guards are tagged so the parity test can read them.
- Re-measuring the baseline counts (researchers' ad-hoc counts disagreed: 50 vs 63 unguarded routers; 64 of 89 sidebar strings unenforced) before guarding.
- Which exact finance field names are stripped (D-04), as long as purchase cost and book value are covered.

### Deferred Ideas (OUT OF SCOPE)
- Guards for the five non-priority sidebar groups — tracked by the gap ledger (ACC-F2).
- ITAM/console tab-level permission gating (ACC-F1).
- (Also out of phase per CONTEXT: fail-closed sidebar, render-time view gate, no-access screen, permission refresh, "what can this role see" view = Phase 77; persisted role editing; backend enforcement of tenant `enabledFeatures`.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACC-03 | One shared catalogue manifest (permission + backend routes) read by Sidebar.tsx and the App.tsx lookup; 9 mismatches reconciled | "Manifest shape", "Nine mismatched views", "Frontend wiring"; JSON import probed under vitest + tsc |
| ACC-04 | Guards on priority router groups; committed gap ledger; `/api/agents/*` agent routes excluded | "Guard mechanics", "Measured baseline", "Appendix B/C", D-04 asset finance strip |
| ACC-05 | Deny-by-default route-parity test + frontend drift test | "Parity test design", "Validation Architecture" |
</phase_requirements>

## Summary

The backend is far less uniform than the milestone research assumed, and the earlier counts disagree because they measured different units. Measured this session by walking the mounted app (1601 route entries, 277 endpoint modules): 733 routes carry a parseable `require_permission`/`has_permission` dependency, 107 carry a named guard whose string is hard-coded inside the function (all ITAM `_require_itam_*`, `_require_ops_permission`, `require_super_admin`), 112 check a permission/role inside the handler body, **556 are login-only**, 49 are public by design/credential-in-handler, 44 are agent-only. Guarding is therefore a **route-level** problem (guarded routers still contain login-only GETs), and 64 of the 89 sidebar permission strings do not appear as the literal string of any introspectable dependency guard (confirms the "64/89" figure; only 25 do).

Recommended mechanism: one tagged dependency factory (`backend/catalogue_guards.py: catalogue_guard()`) that implements D-03 (read = `view:X` or `manage:X`, write = explicit write permission, then `_scopes_allow`, super-admin bypass through `verify_permission`) and stamps `__catalogue_guard__` on the dependency callable. Apply it at **mount time** in `router_registry._load(..., dependencies=[Depends(...)])` for routers that contain only user-authenticated routes, and at **route level** for the ~20 mixed routers (agent, public or credential-in-handler routes beside user routes). I prototyped the introspection: the baseline walker reads the tag from both mount-level and route-level dependencies under FastAPI 0.141.1. The manifest (`shared/catalogue-access.json`) is read only by the frontend and by tests, never at backend runtime, so there is no deployment coupling.

The riskiest facts for planning: (1) the resolver does **not** apply `implied_closure`, so the guard must check `view:X` OR `manage:X` itself, and 26 of the 48 in-scope `view:` permissions have **no granted `manage:` twin**, so the manifest needs an explicit `write` permission per catalogue; (2) `itam_admin` holds `manage:assets` but not `view:assets`, so it sees no Assets nav item today although the backend (post D-03) will allow it; (3) three Management nav items (`subscriptionManagement`, `invoices`, `knowledgeBase`) use `view:dashboard` (every role) yet back billing/payment routes; (4) `@cached` on `GET /api/assets` and `/api/assets/search` returns the same dict object from an in-memory cache, so the D-04 strip must copy, never mutate in place.

**Primary recommendation:** Build manifest + `catalogue_guard()` + shared route walker first (Wave 1), wire the frontend to the manifest (Wave 2), guard the three groups by mount-level where pure and route-level where mixed (Wave 3), then generate the ledger and enable the strict parity test last (Wave 4). Keep every existing guard; the catalogue guard is additive, so existing write semantics do not weaken.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Catalogue to permission/route definition | Shared data file (`shared/*.json`) | Browser (reader), CI tests | Defined once, read by Sidebar/App and pytest; never loaded by the API at runtime |
| Authorization decision (403) | API / Backend | — | Only the backend is a trust boundary; sidebar hiding is cosmetic |
| Finance-field stripping (D-04) | API / Backend (handler) | — | Must be server-side; a client filter leaks data |
| Drift detection | CI (pytest + vitest) | — | Tests compare manifest vs mounted route table vs Sidebar |
| Sidebar rendering / view lookup | Browser / Client | — | Reads manifest; fail-closed behavior is Phase 77 |
| Agent enrollment/heartbeat | API / Backend (agent auth) | — | Untouched; guards must not wrap it |

## Standard Stack

No new packages are required. [VERIFIED: probe this session] A JSON file under `shared/` imported from a vitest test (`import m from '../../shared/x.json'`) ran green and `tsc -p` with the repo tsconfig (moduleResolution `bundler`, TypeScript 5.7.3) reported no errors, so `resolveJsonModule` need not be added. The probe files were removed afterwards.

### Core (existing, reuse)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| FastAPI | 0.141.1 [VERIFIED: `backend/venv/bin/python -c "import fastapi"`] | `include_router(dependencies=…)`, `Depends` tree introspection | Mount-level deps are visible to the baseline walker via `_IncludedRouter.include_context.dependencies` |
| pytest + pytest-asyncio | existing (`asyncio_mode = auto`) | parity + guard matrix tests | Existing convention (`tests/conftest.py: make_test_app, make_token_data`) |
| vitest | 5.0.0 [VERIFIED: run output "RUN v5.0.0"] | frontend drift test | Test glob is `src/**/*.{test,spec}.?(c|m)[jt]s?(x)` (vite.config.ts) so the test must live in `src/__tests__/` |
| Phase 75 resolver | in repo | `verify_permission`, `effective_permissions`, `implied_closure`, `_scopes_allow` | D-03 mandates reuse |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Backend reading the JSON manifest at runtime | Permission strings declared in code, test cross-checks manifest | Runtime read couples deploy to `shared/`; test-time check gives the same drift protection |
| Decorator tagging | Tag attribute on the dependency callable | Dependency attribute survives mount-level and route-level use and needs no AST parsing |
| Router-level guard everywhere | Mixed mount/route-level | Router-level breaks agent tokens and public routes in mixed routers |

**Package Legitimacy Audit:** No external packages are installed by this phase. Packages removed (SLOP): none. Packages flagged (SUS): none.

## Measured Baseline (settles the 50 vs 63 and 64/89 disagreement)

Method [VERIFIED: scripted walk of `register_all_routers(FastAPI())`, same `_IncludedRouter` walk as `backend/tests/test_route_auth_baseline.py`; closure introspection for `require_permission`/`has_permission`]. Unit = route entry (path with its method set); module = `route.endpoint.__module__`.

| Class | Routes | Meaning |
|-------|--------|---------|
| P | 733 | dependency-level guard with parseable permission string |
| N | 107 | named dependency guard, string hard-coded inside (`_require_itam_admin` 30, `_require_itam_viewer` 23, `_require_itam_admin_session_only` 20, `require_super_admin` 10, `_require_ops_permission` 8, `_require_procurement_admin` 5, `check_ops_permission` 5, asset-request guards 5, `_require_role_list_access` 1) |
| B | 26 | permission check inside handler body (`verify_permission(` etc.) |
| R | 86 | role comparison + 403 inside the body |
| L | 556 | login-only (any signed-in user) |
| U | 49 | unauthenticated (all but a few already on `REVIEWED_UNAUTHENTICATED`; includes GraphQL) |
| A | 44 | agent-token only |
| total | 1601 | |

- Modules: 277. Zero dependency-level guards in **65** modules; zero guards of any kind (incl. body checks) in **36**. 97 modules have every route guarded, agent-only or public.
- **Strict definition recommended for D-05** (dependency tree carries a catalogue tag or a known guard factory/`_require_*`/`check_ops_permission`; body checks do not count): 189 modules still hold at least one login-only user route; 88 are clean.
- Heuristic split of those 188 (path-prefix map in Appendix B; **confirm while authoring the manifest**): about **108 modules / 388 routes in scope** (D-01 groups) and about **81 modules / 272 routes to the ledger**.
- Sidebar: 89 distinct permission strings; 25 appear as the literal string of an introspectable dependency guard, **64 do not**. `view:itam` is enforced by `_require_itam_viewer` but is invisible to string introspection (reason to tag, not parse).
- Workload implication: ~100 in-scope routers, of which the mount-level path covers most; the D-04 strip touches 3 handlers.

## Architecture Patterns

### System Architecture Diagram

```
shared/catalogue-access.json  ---------------------------+
   (id, view, label, group, permission, nav, routes[])   |
        |                    \                           |
        | import (Vite)       \ json.load (pytest)       |
        v                      v                         v
 utils/catalogueAccess.ts   backend/tests/              backend/tests/
   NAV_GROUPS, viewPermission   test_catalogue_*.py       test_catalogue_route_parity.py
        |                          ^                         ^           ^
        v                          |                         |           |
 components/Sidebar.tsx      tests build app via         walk mounted   shared/catalogue-gaps.json
 App.tsx (3 lookup sites)    register_all_routers        route table    (unguarded, out-of-scope routers
                                  |                      (tags read)     + reason + maxUnguardedRoutes)
                                  v
 HTTP request --> auth dep (get_current_user | _or_api_key | _or_agent)
              --> catalogue_guard(catalogue, view, write)   [mount-level or route-level]
                    GET/HEAD/OPTIONS: verify_permission(view) OR verify_permission(manage twin)
                    other methods   : verify_permission(write)
                    then _scopes_allow (API-key narrowing); super-admin via verify_permission
              --> handler  (assets: strip finance fields unless view:itam)
```

### Recommended Project Structure
```
shared/
├── catalogue-access.json      # manifest (all 202 AppViews; nav:true for the 188 sidebar items)
└── catalogue-gaps.json        # gap ledger (out-of-scope routers with reason + ratchet count)
backend/
├── catalogue_guards.py        # catalogue_guard() factory, tag attribute, shared read/write rule
├── router_registry.py         # mount-level dependencies for pure routers
└── tests/
    ├── _route_walk.py         # walker extracted from test_route_auth_baseline.py (shared)
    ├── test_catalogue_route_parity.py
    ├── test_catalogue_guards.py          # 403/200 matrix, scope narrowing, agent unaffected
    └── test_asset_finance_fields.py      # D-04
utils/catalogueAccess.ts       # typed reader (next to utils/permissions.ts)
src/__tests__/catalogueAccess.test.ts   # D-06 drift test
```

### Manifest shape (recommended)
```json
{
  "version": 1,
  "groups": [
    {"id": "infra", "title": "Infrastructure & Assets", "enforce": true},
    {"id": "dashboards", "title": "Dashboards & Insights", "enforce": false}
  ],
  "catalogues": [
    {"view": "mobileDeviceManagement", "label": "Mobile Device Management", "group": "infra",
     "nav": true, "permission": "view:mdm", "write": "manage:assets",
     "routes": ["/api/mdm"]},
    {"view": "serviceCatalog", "label": "Service Catalog", "group": "infra",
     "nav": true, "permission": "view:service_catalog", "routes": [], "noBackendReason": "no backend route exists"},
    {"view": "userManagement", "label": "User Management", "group": "mgmt",
     "nav": false, "permission": "manage:rbac", "routes": ["/api/users", "/api/roles"]}
  ]
}
```
- Group order and item order in the array are the sidebar order (replaces `navGroups`). `nav:false` entries replace the 14 App-only views so `viewPermissionMap` can be deleted entirely (`AppView` has 202 members = 188 nav + 14 non-nav; App map had 202 keys) [VERIFIED: script comparing `types.ts` AppView union and the App map].
- `permission` = what the sidebar and read guard require; `write` = the permission mutating routes need. `write` is mandatory whenever `manage:<suffix of permission>` is not granted by `rbac_defaults` (26 of 48 in-scope `view:` strings, Appendix A column 4 = N). Default when absent: `manage:` + suffix.
- `routes` are path prefixes; a catalogue may list several. Routes under a prefix inherit the catalogue unless listed in `exemptions` (agent-only/public handled by the shared reviewed list, not by the manifest).
- Presentation (icons) and entitlement (`minTier`, `featureKey`) stay in `Sidebar.tsx` as a `Record<AppView, {icon, minTier?, featureKey?}>` map; access data lives only in the manifest.

### Pattern 1: tagged catalogue guard (D-03 and D-02 together)
```python
# backend/catalogue_guards.py  (sketch; values below match files read this session)
SAFE = frozenset({"GET", "HEAD", "OPTIONS"})

def _twin(perm: str) -> str:            # "view:mdm" -> "manage:mdm"; "manage:x" -> "manage:x"
    return perm if perm.startswith("manage:") else "manage:" + perm.split(":", 1)[1]

async def check_catalogue_access(user, method: str, view: str, write: str) -> None:
    if method in SAFE:
        ok = await verify_permission(user, view) or await verify_permission(user, _twin(view))
        scope_ok = _rbac_service._scopes_allow(user, view) or _rbac_service._scopes_allow(user, _twin(view))
    else:
        ok = await verify_permission(user, write)
        scope_ok = _rbac_service._scopes_allow(user, write)
    if not ok:      raise HTTPException(403, f"Missing required permission: {view if method in SAFE else write}")
    if not scope_ok: raise HTTPException(403, "API key scope does not permit: ...")   # role first, scope second

def catalogue_guard(catalogue: str, *, view: str, write: str, auth=get_current_user):
    async def dependency(request: Request, user: TokenData = Depends(auth)):
        await check_catalogue_access(user, request.method, view, write)
        return user
    dependency.__catalogue_guard__ = {"catalogue": catalogue, "view": view, "write": write}
    return dependency
```
- Role check first, scope second reproduces `_require_itam_viewer`/`_require_itam_admin` order [VERIFIED: backend/itam_asset_endpoints.py:38-93, quote: "Role check (verify_permission) — the outer bound" / "Scope-narrowing check (_rbac_service._scopes_allow) — only once the role check passes"]. For ITAM, rewrite `_require_itam_viewer`/`_require_itam_admin` to call `check_catalogue_access` and stamp the same tag, keeping `auth=get_current_user_or_api_key` and the `view:itam`-or-`manage:assets` read rule and `manage:assets` write rule unchanged (API-key behavior must not change).
- Super-admin bypass is inside `verify_permission` (`is_super_admin(user.role)` returns True) and API-key scope narrowing still applies afterwards [VERIFIED: backend/rbac_utils.py:63-85].
- `get_current_user` appears in the guard and the route: FastAPI de-duplicates per request, so no double auth. Test overrides of `get_current_user` (the `make_test_app` convention) apply to the guard automatically.

### Pattern 2: mount-level vs route-level placement
- **Mount-level** (`_load(app, "mdm_endpoints", "router", dependencies=[Depends(catalogue_guard("mobileDeviceManagement", view="view:mdm", write="manage:assets"))])`). `_load` forwards `**kwargs` to `include_router` [VERIFIED: backend/router_registry.py:51-61, quote: `app.include_router(getattr(mod, attr), **kwargs)`]. Use when every route in the router is user-authenticated. Advantage: unit tests that mount a router directly (the dominant `make_test_app` style, 110 test files use `dependency_overrides`) are unaffected; only full-app tests see the new 403s.
- **Route-level** (`@router.get(..., dependencies=[Depends(guard)])`) for mixed routers. In-scope mixed modules include `agent_approval_endpoints`, `agent_core_endpoints`, `agent_metrics_endpoints`, `agent_security_endpoints`, `agent_tasks_endpoints`, `agent_telemetry_endpoints`, `agentic_tasks_endpoints`, `response_endpoints`, `software_endpoints`, `remote_endpoints`, `alert_endpoints`, `agent_download_endpoints`, `agent_registry_endpoints`, `update_endpoints`, `deployment_result_endpoints`, `sso_endpoints`, `ldap_endpoints`, `tenant_endpoints`, `edr_telemetry_endpoints`, `webhook_endpoints`, `settings_endpoints`, `stream_processing_endpoints`. A router-level user guard would reject agent tokens (`get_current_user` rejects them, `allow_agent` is only True in `get_current_user_or_agent`) and public routes. Script-generate the exact pure/mixed split from the walk (a router is "pure" when it has no A and no U route).
- The same router object can be mounted twice (`itam_component_endpoints` mounts `router` and `asset_components_router`; `trust_endpoints` mounts public_router): guard each `_load` call explicitly.
- **Prototype result** [VERIFIED: scratchpad prototype under FastAPI 0.141.1]: a tag attached at `include_router(dependencies=…)` and a tag attached via route `dependencies=[…]` were both found by `dep.call` tree walk plus `include_context.dependencies`.

### Pattern 3: parity test design (D-05)
Extract `_WALK`/`REVIEWED_UNAUTHENTICATED` from `test_route_auth_baseline.py` into `backend/tests/_route_walk.py` (keep the fresh-interpreter subprocess, whose stated reason is that other tests reload `authentication_service`), extend the walk to emit per route: `tags` (list of `__catalogue_guard__` dicts), `has_known_guard` (qualname matches the baseline `PERM_DEP` regex), `agent_only`, `public`. Then:
1. Manifest sanity: every `permission`/`write` string is granted to some role in `rbac_defaults.ROLE_DEFAULTS` or is in `SUPER_ADMIN_ONLY_PERMISSIONS`; every nav entry has exactly one permission (the 9 views); every `routes` prefix matches at least one mounted route, or the entry has `noBackendReason`; no prefix claimed by two catalogues.
2. In-scope parity: for every mounted route under an `enforce:true` catalogue prefix that is user-authenticated and not on the reviewed public list or agent-only, a tag with the same `catalogue`, `view` and `write` as the manifest must be present. Failure message: `GET /api/mdm/devices: expected catalogue_guard("mobileDeviceManagement", view="view:mdm", write="manage:assets")`.
3. Deny-by-default: any module with a user-authenticated route lacking both a tag and a known guard, not under an enforced prefix, must be in `shared/catalogue-gaps.json`; the failure message prints a paste-ready entry. Ledger entries carry `maxUnguardedRoutes` (ratchet: the count may fall, never rise) and a stale entry (module fully guarded or gone) also fails so the ledger only shrinks. This closes the hole where a new unguarded route silently joins a ledgered module.
4. Do not weaken the baseline tests; parity extends them (CONTEXT canonical reference).

### Anti-Patterns to Avoid
- **Router-level user guard on routers with agent/public routes**: breaks enrollment/heartbeat (D-02).
- **Treating body-level `is_super_admin(` as a guard**: most hits only choose a tenant filter (`asset_endpoints.py` GET routes are login-only despite matching). Use the strict dependency definition.
- **Reading permission strings via closure introspection as the parity mechanism**: fails for `_require_itam_*` (107 routes). Tag instead.
- **Two permission strings per view**: Sidebar and App must both call the manifest reader.
- **Mutating cached results in place** (see Pitfall 3).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Implication `manage:X` implies `view:X` | New implication table | `rbac_defaults.implied_closure` / check `view:X` or `manage:X` twin explicitly | Phase 75 D-20; one definition |
| Role-to-permission lookup | New role map or DB query in guards | `rbac_utils.verify_permission` | Super-admin bypass, defaults-first, fail-closed on role-store error |
| API-key narrowing | New scope logic | `rbac_service._scopes_allow` after the role check | Order is a security property (ITAM-USR-05) |
| Route table walking | A new walker | Extract the baseline walker | Handles `_IncludedRouter` of FastAPI 0.141 |
| Unauthenticated/agent exemptions | A second allow-list | Import `REVIEWED_UNAUTHENTICATED` | One reviewed list |
| JSON loading in the app | Runtime fetch of manifest in API | Declare strings in code; tests cross-check | No deploy coupling |

## Runtime State Inventory

Not a rename/refactor/migration phase. Omitted deliberately. (Mongo role documents are untouched; permission strings are not renamed.)

## Common Pitfalls

### Pitfall 1: Resolver does not apply the `manage ⇒ view` closure
**What goes wrong:** A read guard that only checks `view:X` 403s roles that hold only `manage:X` (D-03 violated).
**Why:** `effective_permissions` returns defaults plus role documents with no closure [VERIFIED: backend/rbac_service.py:74-99]; `implied_closure` is used only by `ceiling_allows` [VERIFIED: grep of backend: only rbac_defaults.py:199 and :225].
**Real example:** `itam_admin` is `("manage:assets", "manage:finance", "manage:itam", "manage:licenses", "manage:procurement", "manage:users", "view:itam", "view:profile")` [VERIFIED: backend/rbac_defaults.py itam_admin block]. It has no `view:assets` or `view:licenses`, so `Sidebar` hides Assets for it today.
**Avoid:** Read rule = `view:X` or the manage twin (Pattern 1). Raise as Open Question 1 whether delivery (`/me`) should also apply the closure.
**Warning signs:** `itam_admin` 403 on `GET /api/assets`.

### Pitfall 2: 26 of 48 in-scope view permissions have no `manage:` twin
`view:security`, `view:patching`, `view:cloud_security`, `view:finops`, `view:remote_access`, `view:mdr`, `view:xdr`, `view:threat_intel`, `view:vulnerabilities`, `view:zero_trust` and others (Appendix A). Writes must use an existing granted permission (for security the current guards use `investigate:security` / `manage:security_cases`; `manage:security` is NOT granted to `tenant_admin`, so requiring it would lock tenant admins out of writes). Choose `write` per catalogue from the strings the routers already use, never invent a new one.

### Pitfall 3: `@cached` and in-place mutation for D-04
`get_assets` (`ttl=60`) and `search_assets` (`ttl=30`) are wrapped by `cached`; the key is `prefix:funcname:` plus every kwarg except `request`/`db`, so it includes `current_user=TokenData(username=…, role=…, tenant_id=…, scopes=…)` (a dataclass repr) [VERIFIED: backend/cache_service.py:175-183; TokenData repr printed this session]. So caching is effectively per-user and safe across roles, but the cache returns the stored object by reference. Strip on a copy (build a new dict per item) so a `view:itam` caller's later hit is not stripped and a stripped result never poisons a full one. A role edit can stay stale for up to 60 s (acceptable; note in plan).

### Pitfall 4: mount-level guard on routers with credential-in-handler routes
`REVIEWED_UNAUTHENTICATED` lists routes like `POST /api/deployments/{job_id}/result` and `GET /api/agent/download/{tenant_id}` that authenticate inside the handler. Wrapping their router breaks agent installs. The pure/mixed split must be generated from the walk, not guessed from filenames.

### Pitfall 5: legacy API-key role
Legacy tenant API keys authenticate as `TokenData(role="api-integration")`, which has no entry in `rbac_defaults`, so only a role document could grant it anything [VERIFIED: backend/api_key_auth.py:282 and `rbac_defaults.defaults_for` returns `()` for unknown roles]. Preserve current behavior on ITAM routes; do not extend the new guard to accept legacy keys on non-ITAM routers (they use `get_current_user`).

### Pitfall 6: nav permissions that are the same string for read and write
Several Management items use `manage:settings` as the nav permission (`settings`, `webhooks`, `hadr`, ...). Read and write both need `manage:settings`; `view` is a `manage:` string, `_twin` returns it unchanged. Make sure the factory handles that (Pattern 1) and the parity test accepts `view == write`.

### Pitfall 7: tenant management is not a normal catalogue
`tenantManagement` and `bundleManagement` require `manage:tenants`, which only `super_admin` can hold (`SUPER_ADMIN_ONLY_PERMISSIONS`). `tenant_endpoints` also serves tenant-scoped self-service routes (and `POST /api/tenants/lookup-key` is public). Guard route-level, per route, not by prefix.

### Pitfall 8: existing tests that will turn red
Full-app tests that call in-scope routes as `Viewer`/`user` (29 and 35 occurrences of those roles in tests) and tests that assert specific permission strings (`investigate:security` etc.) can break when new 403s land. Mount-level placement limits this to tests that build the real app. Plan a full backend run after each guard wave, and update the affected tests to a role that holds the permission rather than loosening guards. `test_route_auth_baseline.py` itself needs no change (guards only add dependencies); only the shared-walker extraction touches it.

## Code Examples

### D-04: finance strip in `asset_endpoints.py` (three handlers)
```python
# Source: derived from backend/itam_models.py:120-130, 138-157, 284-292 (read this session)
ASSET_FINANCE_FIELDS = frozenset({
    "purchaseCostCents", "purchaseDate", "poNumber", "purchase_order_id", "supplierId",
    "warrantyMonths", "warranty_expiry_date", "warrantyAlertSentAt",
    "salvage_value", "useful_life_years",
    "bookValueCents", "currentBookValueCents",          # defensive: computed names, none stored today
})

async def can_view_finance(user) -> bool:
    return await verify_permission(user, "view:itam")   # super-admin True; manage:itam held by tenant_admin also holds view:itam

def strip_finance(doc: dict) -> dict:                    # copy, never mutate (cached object)
    return {k: v for k, v in doc.items() if k not in ASSET_FINANCE_FIELDS}
```
Apply in `get_assets` (list), `search_assets`, `get_asset_details`; keep the `@cached` decorators. Quoted model fields: `purchaseCostCents: Optional[int] = Field(None, ge=0)`, `poNumber: Optional[str] = Field(None, max_length=100)`, `salvage_value: Optional[float] = Field(None, ge=0)`, `useful_life_years: Optional[int] = Field(None, gt=0)`, `warrantyAlertSentAt: Optional[str] = None`. Whether the warranty fields and `supplierId` are "finance" is the user's call (Assumption A3); purchase cost, purchase date, PO and salvage/useful-life are unambiguous.

Response-path audit for `/api/assets*` [VERIFIED: route walk + reading handlers]: only `GET /api/assets`, `GET /api/assets/search`, `GET /api/assets/{asset_id}` return whole asset documents (`projection={"_id": 0}` / `find(query, {"_id": 0})`). `GET /api/assets/{id}/book-value` and `/warranty` are already `_require_itam_viewer`. `global_search_endpoints` projects `id, hostname, ipAddress, osName, status` only. `export_service._format_asset` whitelists columns (no cost keys). GraphQL (`graphql_api`) has no asset cost fields (grep for purchase/cost/warranty returned nothing). `/api/itam/data/export` and ITAM reports are already ITAM-gated.

### Frontend: typed reader and Sidebar/App wiring
```ts
// utils/catalogueAccess.ts
import manifest from '../shared/catalogue-access.json';
import type { AppView, Permission } from '../types';
export const CATALOGUES = manifest.catalogues as ReadonlyArray<{view: AppView; label: string; group: string; nav: boolean; permission: Permission}>;
export const viewPermission = (v: AppView): Permission => CATALOGUE_BY_VIEW[v].permission;
```
- `components/Sidebar.tsx`: replace the 208-440 `navGroups` literal by manifest-driven groups joined with a local presentation map (icons, `minTier`, `featureKey`). Current shape: `{ view: 'dashboard', label: 'Overview', icon: <DashboardIcon size={20} />, permission: 'view:dashboard' }` [VERIFIED: components/Sidebar.tsx:212]; `visibleGroups` (441-466) keeps its filter logic, which Phase 77 will make fail-closed.
- `App.tsx`: `viewPermissionMap` is declared at line 243 and read at lines 646 (hash routing: `Object.keys(viewPermissionMap).find(...)`) and 1337 (`handleSetCurrentView`). Replace all three with the reader.
- Vitest picks up `src/__tests__/catalogueAccess.test.ts` only; `Dockerfile.frontend*` use `COPY . .` so `shared/` ships in the build context.

## Nine mismatched views (single winner = the Sidebar string)
Sidebar value vs App `viewPermissionMap` [VERIFIED: scripted parse of components/Sidebar.tsx and App.tsx 243-…]:

| View | Sidebar.tsx | App.tsx | Winner and why |
|------|-------------|---------|----------------|
| agentCapabilities | view:agent_capabilities | view:agents | Sidebar; granted to `tenant_admin`, `user` |
| jobs | view:jobs | view:dashboard | Sidebar; `view:jobs` is in `SUPER_ADMIN_ONLY_PERMISSIONS` (line 114) by Phase 75 D-03, so jobs stays super-admin only. Backend `/api/jobs` read must therefore be `view:jobs` |
| llmops | view:llmops | view:ai_governance | Sidebar; granted to `tenant_admin` |
| persistenceDetection | view:persistence | view:security | Sidebar; `tenant_admin` only |
| sustainability | view:sustainability | view:dashboard | Sidebar; `tenant_admin` only |
| swarm | view:swarm | view:dashboard | Sidebar; `tenant_admin` only |
| unifiedOps | view:unified_ops | view:dashboard | Sidebar; `tenant_admin` only |
| vulnerabilityManagement | view:vulnerabilities | view:patching | Sidebar; `tenant_admin`, `analyst`, `security_analyst` |
| zeroTrustQuantum | view:zero_trust | view:security | Sidebar; `tenant_admin` only |

Effect: roles that could navigate by hash/click through App's weaker string (for example `user` on `swarm` via `view:dashboard`) will lose that path. The sidebar already hid these items for them.

## Appendix A: in-scope nav items (98) seeded for the manifest

Columns: group (I = Infrastructure & Assets 23, S = Security 49, M = Management & Settings 26) | view | sidebar permission | manage twin granted to some role (Y/N) | frontend `/api/<seg>` hits (HEURISTIC from the component and apiService imports, empty = not found; confirm each when authoring `routes`). Group totals [VERIFIED: parse of Sidebar.tsx]: 188 items across 8 groups, 89 distinct strings.

```
I|agents|view:agents|Y|agents,ai,kpi
I|agentCapabilities|view:agent_capabilities|N|agents
I|assetManagement|view:assets|Y|(assets via props: /api/assets)
I|itam|view:itam|Y|itam (+ /api/assets lifecycle/finance/labels, /api/v1/itam procurement and asset-requests)
I|patchManagement|view:patching|N|patches
I|deploymentApprovals|view:patching|N|approvals,deployments
I|softwareUpdates|view:software_updates|N|software
I|softwareDeployment|view:software_deployment|N|agents,software,tasks
I|stagedDeployments|view:software_deployment|N|(none found)
I|windowsAutopilot|view:autopilot|Y|autopilot
I|mobileDeviceManagement|view:mdm|Y|mdm
I|mobileAppManagement|view:mam|Y|mam
I|androidEnterprise|view:android_enterprise|Y|android-enterprise
I|branchSites|view:branch_sites|Y|branch-sites
I|appCatalog|view:app_catalog|Y|app-catalog
I|assetIntelligence|view:asset_intelligence|Y|asset-intelligence
I|deviceConfigProfiles|view:device_config_profiles|Y|device-config-profiles
I|firmwareDriverUpdates|view:firmware_drivers|Y|firmware-drivers
I|serviceCatalog|view:service_catalog|N|(no backend route)
I|jobs|view:jobs|N|jobs
I|remoteAccess|view:remote_access|N|agents,remote
I|chat|manage:agents|Y|support
I|certificates|view:assets|Y|certificates
S|security|view:security|N|playbooks,threat-intel
S|alertManagement|view:security|N|alerts
S|edr|view:security|N|(edr)   S|yaraRules|view:security|N|analysis
S|mdr|view:mdr|N|response     S|xdr|view:xdr|N|(none found)
S|mitreAttack|view:security|N|mitre   S|dlp|view:security|N|(dlp)
S|cloudSecurity|view:cloud_security|N|(none)  S|cloudAccounts|view:cloud_security|N|cloud-accounts
S|cloudChecksScanner|view:cloud_security|N|cloud-accounts,cloud-checks
S|iacContainer|view:cloud_security|N|container,iac
S|threatHunting|view:threat_hunting|N|(none)  S|siem|view:security|N|siem
S|threatIntelligence|view:threat_intel|N|(threat-intel)  S|securityIntelConnectors|view:security|N|(security-intel)
S|siemRules|view:security|N|siem  S|incidentResponse|investigate:security|Y|(none)
S|incidentWarRoom|investigate:security|Y|correlations,incidents
S|deception|view:security|N|deception  S|aiAnomaly|view:security|N|ndr,ueba
S|ueba|view:security|N|(ueba)  S|shadowAI|view:security|N|ueba  S|ndr|view:security|N|ndr
S|correlations|view:security|N|correlations  S|emailSecurity|view:security|N|email-security
S|incidentImpact|investigate:security|Y|agent  S|dataSecurity|view:dspm|N|(none)
S|attackPath|view:attack_path|N|(security/attack-path)  S|pentest|view:security|N|pentest
S|dast|view:security|N|dast  S|zeroTrustQuantum|view:zero_trust|N|quantum-security,zero-trust
S|vulnerabilityManagement|view:vulnerabilities|N|(vulnerabilities, vulnerability-scans)
S|persistenceDetection|view:persistence|N|persistence  S|securitySimulation|view:security|N|simulation
S|securityAudit|view:security_audit|N|security  S|runtimeSecurity|view:security|N|(none)
S|pam|manage:settings|Y|pam  S|advancedHunting|view:advanced_hunting|Y|advanced-hunting
S|detectionRules|view:detection_rules|Y|detection-rules  S|connectorsHub|view:connectors_hub|Y|connectors-hub
S|securityCopilot|view:security_copilot|N|security-copilot  S|attackTimeline|view:attack_timeline|N|advanced-hunting
S|geographicMap|view:geographic_map|N|advanced-hunting  S|scaAssessment|view:sca|Y|sca,security-ops
S|agentGroups|view:agent_groups|Y|agent-groups  S|configDrift|view:config_drift|Y|config-drift
S|fimMonitoring|view:fim|Y|fim  S|activeResponse|view:active_response|Y|active-response
M|finops|view:finops|N|finops  M|servicePricing|manage:pricing|Y|finops
M|paymentSettings|manage:settings|Y|payments  M|subscriptionManagement|view:dashboard|N|payments
M|invoices|view:dashboard|N|payments  M|cloudIntegrations|manage:settings|Y|cloud-integrations
M|secretsManagement|manage:settings|Y|secrets  M|hadr|manage:settings|Y|hadr
M|retentionPolicy|manage:settings|Y|retention  M|retentionPolicies|view:retention_policies|Y|retention-tiers
M|msspMonitoring|view:mssp|Y|alerts,mssp  M|knowledgeBase|view:dashboard|N|knowledge
M|geoSecurity|manage:settings|Y|settings  M|fleetObservability|manage:agents|Y|fleet
M|fleetGeoMap|manage:agents|Y|fleet  M|nativeSecurity|manage:active_response|Y|(security-ops)
M|systemHealth|manage:settings|Y|system  M|apiStatus|manage:settings|Y|system
M|settings|manage:settings|Y|integrations,settings  M|tenantManagement|manage:tenants|N|(tenants)
M|bundleManagement|manage:tenants|N|(bundles)  M|webhooks|manage:settings|Y|webhooks
M|ticketing|manage:settings|Y|(ticketing)  M|ticketWebhooks|manage:settings|Y|tickets
M|notificationPrefs|view:profile|N|users  M|dataWarehouse|view:reporting|N|etl,warehouse
```
Non-nav views that carry identity routes (need manifest entries, `nav:false`): `userManagement` and `roleManagement` (App map: `manage:rbac`), `apiKeys` (`manage:api_keys`), `profile`, `notifications`, `integrations`. SSO/LDAP admin routes (`/api/admin/...`, `/api/sso`, `/api/auth/ldap`, `/api/auth/saml`) have no sidebar item; attach them to the `settings` catalogue or a `nav:false` identity entry. Nav items with no backend route found: `serviceCatalog`, `stagedDeployments` (verify), `runtimeSecurity`, `threatHunting`. Backend routers behind an in-scope prefix with no nav item are covered by Appendix B.

## Appendix B: heuristic router scope (to be replaced by manifest `routes`)

In-scope (about 108 modules) by owning prefix: Infra = `/api/agents` (user routes only), `/api/assets`, `/api/itam`, `/api/v1/itam` (procurement, asset-requests), `/api/patches`, `/api/approvals`, `/api/deployments`, `/api/software`, `/api/autopilot`, `/api/mdm`, `/api/mam`, `/api/android-enterprise`, `/api/branch-sites`, `/api/app-catalog`, `/api/asset-intelligence`, `/api/device-config-profiles`, `/api/firmware-drivers`, `/api/jobs`, `/api/remote`, `/api/support`, `/api/certificates`, `/api/network-devices`, `/api/agent-groups`. Security = `/api/security*`, `/api/alerts`, `/api/response`, `/api/mitre`, `/api/analysis`, `/api/cloud-*`, `/api/container*`, `/api/iac*`, `/api/siem`, `/api/threat-intel`, `/api/incidents`, `/api/deception`, `/api/ndr`, `/api/ueba`, `/api/correlations`, `/api/email-security`, `/api/pentest`, `/api/dast`, `/api/zero-trust`, `/api/quantum-security`, `/api/vulnerabilit*`, `/api/persistence`, `/api/simulation`, `/api/pam`, `/api/advanced-hunting`, `/api/detection-rules`, `/api/connectors-hub`, `/api/sca`, `/api/config-drift`, `/api/fim`, `/api/active-response`, `/api/mdr`, `/api/edr`, `/api/dlp`, `/api/itdr`, `/api/insider-threat`, `/api/k8s-security`, `/api/pipeline-security`, `/api/supply-chain-security`, `/api/api-security`, `/api/dam`, `/api/ot-ics`. Mgmt = `/api/finops`, `/api/payments`, `/api/billing`, `/api/cloud-integrations`, `/api/secrets`, `/api/hadr`, `/api/retention*`, `/api/mssp`, `/api/knowledge`, `/api/settings`, `/api/fleet`, `/api/system`, `/api/tenants`, `/api/bundles`, `/api/webhooks`, `/api/ticketing`, `/api/tickets`, `/api/users`, `/api/roles`, `/api/api-keys`, `/api/admin`, `/api/sso`, `/api/auth/ldap|saml`, `/api/etl`, `/api/warehouse`, `/api/notifications`, `/api/integrations`, `/api/logs`, `/api/cache`, `/api/maintenance`.

Modules with login-only user routes under those prefixes (count of such routes): `asset_endpoints` 9, `vendor_endpoints` 13 (misfiled by my map; it is Governance, so ledger), `tenant_endpoints` 10, `support_endpoints` 9, `billing_endpoints` 8, `settings_endpoints` 8, `mitre_endpoints` 7, `mssp_endpoints` 7, `cloud_integrations_endpoints` 7, `agent_core_endpoints` 7, `binary_analysis_endpoints` 7, `autopilot_endpoints` 6, `mdm_endpoints` 6, `mdr_endpoints` 6, `siem_endpoints` 6, `ueba_service` 6, `supply_chain_security_endpoints` 6, `cache_endpoints` 6, `advanced_hunting_endpoints` 6, plus about 90 smaller modules (full per-module list is regenerated by the parity test's failure output). Out of scope, ledger (about 81 modules): compliance_*, questionnaire_*, privacy_endpoints, dpa/baa, risk/vendor/soa/maturity, audit_program, ai_governance, ai_system, future_ops, platform_endpoints, playbook_endpoints, soar, analytics, tracing, insights, dora, digital_twin, service_mesh, sustainability, swarm_endpoints, training, trust_endpoints, webgpu_inference, route_aliases (18 login-only alias routes), plus self-service identity routers (`mfa_endpoints`, `passkey_endpoints`, `jit_access_endpoints`). `route_aliases` shadows canonical paths and is registered first, so the path-based parity test covers aliases under in-scope prefixes automatically.

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| Two nav permission tables (Sidebar vs App) | One manifest with a typed reader | Delete `viewPermissionMap`; tests lock the invariant |
| Per-router ad-hoc `_require_*` with embedded strings | Tagged `catalogue_guard` carrying catalogue/view/write | Parity test can read intent without parsing function bodies |
| Ad-hoc router audit counts | Test-generated ledger with ratchet | Counts stop drifting between researchers |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The view-to-route-prefix map (Appendix A frontend hits, Appendix B) is heuristic; some prefixes belong to other catalogues | Appendix A/B | Wrong guard permission on a router; mitigated by the parity test diff and a review of the manifest |
| A2 | `/api/users` writes keep `_require_itam_admin_session_only` (`manage:assets`) while UI nav uses `manage:rbac`; reads need a decision | Open Question 3 | Locking out or over-granting user administration |
| A3 | Warranty fields and `supplierId` count as "related purchase/finance fields" for D-04 | Code Examples | Over-stripping hides warranty status for non-ITAM viewers, under-stripping leaks vendor pricing context |
| A4 | Billing/finops routes should require a new or existing permission other than `view:dashboard` | Open Question 2 | `view:dashboard` (every role) would expose invoices and payments |
| A5 | Up to 60 s staleness from the asset cache after a role edit is acceptable | Pitfall 3 | Stale finance visibility for 60 s |
| A6 | Strict ledger definition (body-only checks do not count) is wanted: it puts 112 body-guarded routes in scope or ledger | Measured Baseline | Ledger larger/smaller than expected |

## Open Questions

1. **`manage:X` without `view:X` in the delivered permission list (itam_admin).**
   - Known: the resolver adds no closure, `itam_admin` lacks `view:assets`/`view:licenses`, so the Assets nav item is hidden for it though the D-03 backend guard will allow reads.
   - Unclear: whether Phase 76 should also make `effective_permissions`/`/me` apply `implied_closure` (single answer, sidebar matches guard, touches Phase 75 tests that assert exact lists) or leave delivery to Phase 77.
   - Recommendation: guard-level closure now (locked D-03); decide delivery closure with the user, ideally in Phase 77.
2. **Financial nav items on `view:dashboard`.** `subscriptionManagement`, `invoices`, `knowledgeBase` use `view:dashboard`; `view:billing`/`manage:billing` exist in `rbac_utils.Permission` but are in no role default. Needs a user decision on the permission for `/api/payments`, `/api/billing` reads (recommend `manage:settings` for billing/payments, matching the existing write guards, and `view:finops` for `/api/finops`).
3. **Users/roles permission.** App says `manage:rbac`, the user CRUD guard says `manage:assets`, role listing accepts `manage:users` or `manage:rbac`. Recommend keeping current guards (already stricter than login-only), tagging them, and putting `manage:users` OR `manage:rbac` in the manifest read rule for those entries (confirm).
4. **Public/credential routes inside in-scope routers** are carried by the reviewed list; confirm no new entries are wanted.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| backend venv python/pytest | parity and guard tests | yes | `backend/venv/bin/python` (58 tests ran in 10 s) | none |
| Node/npx + vitest | frontend drift test | yes | vitest 5.0.0, TypeScript 5.7.3 | none |
| MongoDB `omni_platform` | not needed | not used | live DB must stay untouched | tests are hermetic (mock collections) |

No blocking missing dependencies.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Backend pytest + pytest-asyncio (`asyncio_mode = auto`, root `pytest.ini`); frontend vitest 5.0.0 + jsdom + @testing-library/react |
| Config file | `pytest.ini`; `vite.config.ts` (`test` block, setup `src/__tests__/setup.ts`) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_route_parity.py backend/tests/test_catalogue_guards.py backend/tests/test_asset_finance_fields.py backend/tests/test_route_auth_baseline.py -q -p no:cacheprovider` and `npx vitest run src/__tests__/catalogueAccess.test.ts` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider`, `npx vitest run src/__tests__`, `npm run build` (writes `dist-new/`) |

Baselines [CITED: orchestrator brief]: backend 3276 passed / 47 skipped; frontend 209 tests. [VERIFIED: this session] `test_route_auth_baseline.py` + `test_rbac_defaults.py` = 58 passed in 10 s; `permissions.test.ts` + `SidebarAuditFixes.test.tsx` = 31 passed in 1 s.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACC-03 | Manifest valid; 9 views single permission; permissions grantable; Sidebar/App read it; `viewPermissionMap` gone | unit (py + ts) | `pytest backend/tests/test_catalogue_manifest.py -q`; `npx vitest run src/__tests__/catalogueAccess.test.ts` | W0 |
| ACC-04 | 403 without view, 200 (non-403) with it, write needs write perm, agent token and API-key paths unchanged, asset finance strip | unit/integration | `pytest backend/tests/test_catalogue_guards.py backend/tests/test_asset_finance_fields.py -q` | W0 |
| ACC-04 | Gap ledger committed and not stale | unit | `pytest backend/tests/test_catalogue_route_parity.py -q` | W0 |
| ACC-05 | Parity fails on unguarded in-scope route and on unledgered router | unit (with injected offender fixtures) | `pytest backend/tests/test_catalogue_route_parity.py -q` | W0 |
| ACC-05 | Sidebar/manifest drift fails | unit | `npx vitest run src/__tests__/catalogueAccess.test.ts` | W0 |

### Sampling Rate
- Per task commit: quick run command (about 15-25 s)
- Per wave merge: full backend suite plus `npx vitest run src/__tests__`
- Phase gate: full backend + frontend suites + `npm run build` green

### Wave 0 Gaps
- [ ] `shared/catalogue-access.json`, `shared/catalogue-gaps.json` (seed)
- [ ] `backend/tests/_route_walk.py` (extract from baseline), `test_catalogue_route_parity.py`, `test_catalogue_manifest.py`, `test_catalogue_guards.py`, `test_asset_finance_fields.py`
- [ ] `src/__tests__/catalogueAccess.test.ts`
- [ ] Negative-control tests: parity test run against a synthetic app with an unguarded route and an unledgered router must fail.

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (unchanged) | Existing `get_current_user`, agent auth, API key auth; guard must not alter them |
| V3 Session Management | no | untouched |
| V4 Access Control | yes | `catalogue_guard` via Phase 75 resolver; deny-by-default parity test; role then scope order |
| V5 Input Validation | minimal | no new inputs |
| V6 Cryptography | no | none |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Missing function-level access control on a new router | Elevation of Privilege | Parity test fails build for unguarded, unledgered routers |
| Finance data disclosure via asset reads | Information Disclosure | Server-side strip unless `view:itam` (D-04) |
| API-key scope bypass | Elevation of Privilege | `_scopes_allow` after role check, tested with a narrowed key |
| Guard breaks agent flows (availability) | Denial of Service | Route-level guards on mixed routers; agent regression tests |
| Cache serving one role's data to another | Information Disclosure | Per-user cache key (verified) plus copy-on-strip |

## Project Constraints (from CLAUDE.md)
- Do what was asked; do not create files unless necessary (the files listed here are the deliverables); keep files under 500 lines (split large walkers and tests).
- Read before editing; never commit secrets; validate input at system boundaries.
- Always run tests after code changes; verify the build before committing (`npm run build && npm test` in CLAUDE.md; this repo's real commands are in Validation Architecture).
- Tests and working files go under `/tests`, `/backend/tests`, `/src`, not the repo root.
- Never restart services, deploy, or write to the live Mongo DB `omni_platform` (brief); no commits by the researcher.

## Sources

### Primary (HIGH)
- In-repo files read this session: `backend/rbac_utils.py`, `backend/rbac_service.py` (74-135, 194-252), `backend/rbac_defaults.py`, `backend/itam_asset_endpoints.py` (30-125), `backend/itam_models.py` (103-160, 262-300), `backend/asset_endpoints.py`, `backend/cache_service.py` (162-199), `backend/router_registry.py`, `backend/api_key_auth.py` (257-286), `backend/authentication_service.py` (393-402), `backend/tests/test_route_auth_baseline.py`, `backend/tests/conftest.py`, `components/Sidebar.tsx`, `App.tsx` (243-262, 1325-1345), `utils/permissions.ts`, `vite.config.ts`, `tsconfig.json`, `types.ts`.
- Scripted: mounted-route walk (1601 routes), sidebar/App parse, FastAPI dependency-tag prototype, vitest + tsc JSON import probe.

### Secondary (MEDIUM)
- Prior milestone research (`.planning/research/*`) as the source of the manifest/ledger file names; CONTEXT.md.

### Tertiary (LOW)
- Appendix A/B view-to-route heuristics (frontend literal path grep).

## Metadata
**Confidence breakdown:**
- Standard stack: HIGH (no new packages; JSON import probed)
- Architecture: HIGH (tag introspection prototyped on the installed FastAPI)
- Pitfalls: HIGH for resolver/closure/cache; MEDIUM for per-router mixed-route split
- Mapping tables: MEDIUM-LOW (heuristic)

**Research date:** 2026-10-13
**Valid until:** 2026-11-12 (route counts change with every merged router)
