# Technology Stack

**Project:** Enterprise OmniAgent - v4.2 Catalogue Access Control & Asset Costing
**Researched:** 2026-10-12
**Confidence:** HIGH (every claim below was checked against the repo source, `backend/requirements.txt` and `package.json`; no external ecosystem claims are load-bearing)

This file replaces the v4.0 ITAM STACK.md (stale for this milestone). It covers ONLY what v4.2 adds. The existing FastAPI / Motor / React / agents / RBAC / ITAM stack is not re-researched.

## Verdict

**v4.2 needs ZERO new dependencies - not on the Python side, not on the JS side, and not in the agents.** Both features are integration work over code that already exists. The real risks are data-model gaps and permission-source drift, not tooling. Do not open a "stack" phase; do not add a blocking dependency-approval checkpoint (v4.1's ldap3/python3-saml checkpoints do not apply here).

Two non-dependency findings matter more than any library choice and should shape the roadmap:

1. **Sidebar gating already exists** (`components/Sidebar.tsx` filters every nav item with `hasPermission(item.permission)`; `App.tsx` `viewPermissionMap: Record<AppView, Permission>` gates `setCurrentView`). Feature 1 is therefore an audit-and-align task, not a build task. See "Feature 1" below for the concrete drift found.
2. **Licenses and consumables have NO cost field today** (`itam_models.py` `LicenseCreate` = seatCount/expiryDate/isReassignable/manufacturerId/productKey; `ConsumableCreate` = initialQuantity/unitType/reorderThreshold). The milestone text says costing is "rolled up from EXISTING data ... software licenses/consumables (Phase 60)", but only asset purchase cost + depreciation (Phase 59) exists. License/consumable cost needs **additive optional fields** (a schema change, still no new dependency, and arguably a small "cost-entry" addition that PROJECT.md says to avoid - the roadmap must make this scope call explicitly).

## Recommended Stack

### Core Framework - ALL EXISTING, UNCHANGED

| Technology | Version (from repo) | Purpose in v4.2 | Why no change |
|------------|--------------------|-----------------|---------------|
| FastAPI | `>=0.110.0,<1.0.0` (requirements.txt) | New read-only cost routes + one permissions route | Standard `APIRouter` + `Depends`; matches 40+ existing ITAM routers |
| Pydantic | `>=2.5.0,<3.0.0` | Response models + optional cost fields on `LicenseCreate/Update` | `Field(None, ge=0)` pattern already used for `purchaseCostCents` |
| Motor / pymongo | `>=3.3.0,<4.0.0` / `>=4.6.0,<5.0.0` | Batched tenant-scoped reads | Same pattern as `itam_reporting_kpis.compute_itam_kpis` (one `find` + Python loop) |
| React | `^19.2.0` | Cost panel + sidebar | No router library exists or is needed (app uses `AppView` state, not routes) |
| TypeScript | `~5.7` | `Permission` union + `Record<AppView, Permission>` exhaustiveness | Compile-time guard already enforces every view has a permission |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| MongoDB (existing) | unchanged | Reads from `assets`, `asset_models`, `licenses`, `license_assignments`, (`consumables`) | **Do not persist rolled-up totals.** Phase 59's contract is "book value never persisted, computed at read time" and Phase 72's contract is "every report reuses the owning computation verbatim". A cached/stored rollup would be a second source of truth that can disagree with the live panel (the exact bug class Phase 72 forbade). |
| New fields (schema only) | n/a | `licenses.purchaseCostCents` (optional int, `ge=0`); optionally `consumables.unitCostCents` | Required to make license spend real. Integer cents to match `assets.purchaseCostCents` / `asset_models.salvageValueCents`. Nullable, no backfill (pre-existing docs simply contribute 0 and are counted in a `withoutCostCount`, mirroring KPI's `withoutPolicyCount`). Extend `LicenseCreate`, `LicenseUpdate`, and the `extra="forbid"` models together or writes will 422. |

### Infrastructure

No infrastructure change. No new service, queue, cache, index, or env var. (An index on `licenses.tenantId`/`license_assignments.licenseId` already exists via `database.py` index setup; verify but do not add speculatively.)

### Supporting Libraries - REUSE ONLY

| Library | Version (from repo) | Purpose in v4.2 | When to use |
|---------|--------------------|-----------------|-------------|
| `recharts` | `^3.5.1` (package.json) | Org-level cost breakdown chart (book value vs purchase vs license spend) | Same lib/`CHART_COLORS` as `components/itam/ItamKpiPanel.tsx` |
| `openpyxl` / `reportlab` | `>=3.1.0` / `>=4.0.0` | Optional cost export | Only via the existing `itam_reporting_excel.py` / `itam_reporting_pdf.py` + `itam_reporting_prebuilt.py` registry; add an `asset_cost` prebuilt report rather than a new exporter |
| `date-fns` | `^4.1.0` | None required (backend computes everything) | Only if a UI date label is needed |
| `vitest` + `@testing-library/react` | `^5.0.0` / `^16.3.0` | Sidebar gating tests | Existing frontend test runner (`npm test`) |
| `pytest` (+ `asyncio.run()` pattern) | existing | Backend RBAC/tenant-isolation/cost tests | Project convention: `asyncio.run()`, NOT pytest-asyncio |
| `Intl.NumberFormat` (platform built-in) | n/a | Currency display | Replaces the hardcoded-`$` private `formatCurrency` in `ItamKpiPanel.tsx`; extract to a shared util in `components/itam/` |

## Integration Points (the actual work)

### Feature 1 - Role-based catalogue access (audit and align, no new library)

Existing mechanism (verified):
- **Nav**: `components/Sidebar.tsx` -> `visibleGroups` filters items by `hasPermission(item.permission)`; Super Admin short-circuits `true`; bundle/tier checks layered on top (`featureKey`, `minTier`).
- **Page guard**: `App.tsx` `viewPermissionMap` + the `setCurrentView` check (note: it only special-cases `'Super Admin' | 'superadmin'`, not `super_admin`/`platform-admin`; the `hasPermission` memo does handle them - low-risk inconsistency to normalize).
- **Permission source for the UI**: `currentUser.permissions` from `POST /login` and `GET /me` in `backend/authentication_endpoints.py` - populated from `find_role_doc(...)` **only**; if no `db.roles` doc matches, the array is `[]` and the UI falls back to the `roles` list/tenant `enabledFeatures` intersection in `App.tsx` (lines ~1185-1241).
- **Backend authority**: `rbac_service.has_permission()` / `rbac_utils.require_permission()` / `verify_permission()` (the latter is what `_require_itam_viewer` uses - accepts `view:itam` OR `manage:assets`).

Drift found that Feature 1 must resolve (this IS the milestone's core risk):
- **Three independent sources of role->permission truth**: `rbac_service.RBACService.default_roles`, `rbac_utils.verify_permission.DEFAULT_PERMISSIONS` (comment says "kept in sync", they are not identical - e.g. `compliance` vs `manage:compliance`, `view:remote_access`/`control:remote_access` only in one), and the seeded role documents in `backend/app_startup.py` (the only place `view:autopilot` etc. are granted). `/me` and `/login` report only the DB doc, so a built-in role with no DB doc shows an empty sidebar until the frontend fallback kicks in.
- **29 sidebar `permission:` strings are granted by neither in-memory default**: `view:advanced_hunting, agent_groups, analytics, android_enterprise, app_catalog, asset_intelligence, attack_timeline, autopilot, branch_sites, conditional_access, config_drift, connectors_hub, detection_rules, device_config_profiles, fim, firmware_drivers, geographic_map, goal_system, jobs, mam, mdm, mssp, persistence, predictive_health, retention_policies, sca, security_copilot, web_monitoring, zero_trust`. Some are covered by seeded DB roles (`app_startup.py`), some may not be - this must be checked per-string, not assumed.
- **UI permission != backend route permission** for many catalogues (e.g. `viewPermissionMap` reuses `view:security` for dast/edr/siem/...; `ticketing`/`geoSecurity`/`hadr`/`pam` map to `manage:settings`). "UI mirrors backend" can only be claimed after a catalogue-by-catalogue table of nav permission vs. the guard on that catalogue's primary read route.

Recommended implementation (code only):
1. **One backend source of truth for the effective permission list**: add a single route (e.g. `GET /api/auth/effective-permissions`, or make `/me` do it) that returns `rbac_service.get_user_permissions(user)` (already handles super-admin `["*"]`, tenant role doc, global-role fallback, in-memory default fallback) so the sidebar and route guards are driven by the same resolver. Do NOT reimplement role resolution a fourth time in TS.
2. **Collapse the duplicated default tables** (`rbac_service.default_roles` vs `rbac_utils.DEFAULT_PERMISSIONS`): have `verify_permission` read `rbac_service.default_roles` instead of its own literal dict. This is a refactor, not a dependency. (Match the repo's stated pattern: `_normalize_role` is "single source of truth".)
3. **Contract test (pytest, no new libs)**: parse `permission: '...'` strings from `components/Sidebar.tsx` and `viewPermissionMap` values from `App.tsx`; assert each is either granted by some built-in role or seeded in `app_startup.py`, or explicitly allow-listed as "super-admin only". This is what makes the 29-string drift above stay fixed.
4. **Defense in depth**: for each catalogue whose backend router uses bare `Depends(get_current_user)` (the Phase 63 class of bug), switch to `require_permission(<same string the nav uses>)`. Phase 63 already established the pattern and a regression-net weakness (tests asserting 403 on only 1-2 routes per router) - enumerate routes in the test via `app.routes` instead of hand-listing.
5. **Tenant `enabledFeatures` intersection** (App.tsx) silently removes nav items; document it as a second hiding layer and include it in the verification matrix so "missing menu" bugs are triaged correctly.

### Feature 2 - Asset cost rollup (reuse existing computation, add read routes)

Existing building blocks (verified):
- `itam_finance_service.compute_book_value(purchase_date, purchase_cost_cents, useful_life_years, salvage_value_cents, now)` - pure function, integer cents, whole-year straight-line, floors at salvage. **Call it; do not re-derive.**
- `itam_reporting_kpis._compute_asset_value_kpi` - already does the exact batched pattern needed for org level (single `asset_models` `$in` lookup, `withoutPolicyCount` for assets with no purchase record/policy). Org book value is effectively already shipped as the "Asset Value" KPI tile; v4.2 org-level cost should **extract/extend this function** (add `totalPurchaseCostCents`, `totalDepreciationCents`) rather than write a parallel loop.
- `itam_reporting_prebuilt._build_asset_value_rows` - per-asset purchase cost + book value rows (already the per-endpoint data shape).
- `itam_license_endpoints` + `license_assignments` (`licenseId`, target user or asset) - seat assignment data for allocation.
- Tenant isolation: `TenantIsolatedCollection` auto-injects `tenantId` on `find/count/aggregate`; `aggregate` prepends `$match`. Endpoint access: `_require_itam_viewer` (`view:itam` OR `manage:assets`) for reads.

Recommended implementation (code only):
- New module `backend/itam_cost_service.py` in the same style as `itam_finance_service.py`: pure functions, **no FastAPI/DB imports** (db handle passed in), integer cents everywhere, delegating to `compute_book_value`. Plus `backend/itam_cost_endpoints.py` mounted via `router_registry.py` (note the registry-order caveat documented in `itam_asset_endpoints.py`: any new multi-segment path under the assets prefix must not be shadowed by `asset_endpoints.py`'s `GET /{asset_id}`; use a distinct prefix such as `/api/itam/costs/...`).
- Routes: `GET /api/itam/costs/summary` (org: total purchase, total book value, accumulated depreciation, license spend, unallocated/shelfware license cost, counts of assets lacking cost/policy) and `GET /api/itam/costs/assets` (paginated per-asset rows: purchase, book value, allocated license cost, total). Guard with `_require_itam_viewer` as the minimum; **decide explicitly** whether cost is more sensitive than inventory (itam_viewer/itam_user hold `view:itam`; `viewer` role does NOT hold it, but does hold `view:finops`, which is cloud-spend and must NOT be reused for ITAM cost).
- Per-asset license allocation: `licenseCostPerSeat = purchaseCostCents // seatCount` (guard `seatCount == 0`); allocated cost for an asset = sum over its `license_assignments`. Integer division leaks remainder cents, so report `unallocatedLicenseCostCents = licenseCost - allocated` rather than letting totals silently disagree. Seats assigned to *users* (not assets) have no endpoint to charge - surface as "user-assigned, not attributed to an endpoint", do not guess.
- Computation location: keep it in **Python over one batched projected `find`** (same as `compute_itam_kpis`). Book value uses whole-year proration in Python, so it cannot be a Mongo `$group` anyway. Do not hand-write a `$lookup` pipeline: `TenantIsolatedCollection.aggregate` only injects the tenant `$match` on the *first* collection, so a `$lookup` into `licenses`/`asset_models` would pull un-scoped documents across tenants. If a lookup is ever unavoidable, add an explicit `tenantId` condition inside the `$lookup`.
- Super-admin / "platform-admin" tenant context: `aggregate` skips the `$match` and `insert_one` skips stamping for `tenant_id == "platform-admin"`, so a super-admin viewing "org level" without a tenant selected would sum across tenants. The cost route must require a resolved tenant (or group by `tenantId`), and the test suite must include a two-tenant isolation case.
- Data-quality display: assets with no `purchaseCostCents`/`purchaseDate`/model policy must show "-" / "not set", never `$0` (follows `REASON_NO_PURCHASE_RECORD` / `REASON_NO_DEPRECIATION_POLICY` from `get_asset_book_value`).
- Endpoint <-> asset linkage: agent-registered endpoints are rows in the same `assets` collection (`agent_registry_endpoints.py` upserts `db.assets` by `id`), so "endpoint-level cost" = asset-level cost on the agent-backed asset; no join to a separate `agents` collection is needed. Agent-discovered assets usually have no purchase record, so most endpoints will legitimately show "no cost data" until costs are entered via the existing `PATCH /api/assets/{id}/purchase` (Phase 59). That is a UX/onboarding point for the roadmap, not a stack gap.
- Money conventions to stay consistent with: integer **cents**, **no currency field anywhere** (single-currency assumption; `ItamKpiPanel` hardcodes `$`). Note the inconsistency: Phase 71 purchase orders (`total_cost`, `unit_price`) and asset requests (`estimated_cost`) are **float dollars** - do not roll POs into totals (they would double-count assets and mix units); asset-level `purchaseCostCents` is the cost source of record.
- Frontend: a new tab/panel inside `components/itam/ITAMConsole.tsx` (not a new top-level `AppView`, which would force a new `viewPermissionMap` entry and a new nav item), calling new `apiService.ts` functions, reusing recharts and the shared currency util. Gate the tab with the same permission as the backend route.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Frontend permission check | Server-resolved `permissions` list + existing `hasPermission` | CASL / casbin / `react-guard`-style RBAC lib | Duplicates `rbac_service`, introduces a second policy engine that would drift from backend; the permission model is explicitly "no new model" |
| Backend permission eval | Existing `rbac_service` / `require_permission` | OPA, Oso, Casbin, `fastapi-permissions` | Same: a parallel authorization engine; the repo already has ReBAC (Phase 36) + two resolvers |
| Money type | Python `int` cents + JS `Intl.NumberFormat` | `Decimal`, `py-moneyed`, `dinero.js`, `currency.js` | Whole system is integer cents; no multi-currency requirement; sums of ints are exact. Add a money library only if multi-currency ever lands (it is out of scope) |
| Depreciation | `compute_book_value` (existing) | `numpy-financial`, `pandas`, QuantLib | Existing function is the Phase 59 contract; pandas is installed but pulling it into a request path adds latency and a second formula |
| Rollup execution | Python loop over one projected `find` | Mongo `$group`/`$lookup` pipeline; materialized rollup collection; Redis cache | Book value is non-trivially computed in Python; `$lookup` bypasses tenant wrapper; stored rollups break the "never persisted" contract. Redis (`>=5.0.0`) is available - add caching only if measured latency demands it, keyed by tenant and invalidated on asset/license writes |
| Cost charts | recharts (existing) | Chart.js, nivo, D3 | Already shipped and styled in `ItamKpiPanel` |
| Exports | existing `itam_reporting_*` | new CSV/PDF libs | openpyxl + reportlab already cover XLSX/PDF; CSV is stdlib |
| Routing/nav | Existing `AppView` + `viewPermissionMap` | `react-router` | Would be a large unrelated refactor |

## What NOT to Add (explicit)

- **No new Python packages** (no `py-moneyed`, `numpy-financial`, `casbin`, `oso`, `opa-client`, `fastapi-permissions`, `fastapi-cache`/`cachetools` for this).
- **No new npm packages** (no `@casl/*`, `react-router*`, `dinero.js`, `currency.js`, `big.js`, `react-query`/`swr`, additional chart libs).
- **No new permission strings or role model** - reuse `view:*` as stated. (Only exception to consider: if cost must be hidden from `itam_viewer`, that needs a *new* permission and therefore contradicts "no new permission model" - resolve at requirements time; default to `view:itam`.)
- **No new collection for cost rollups**, no scheduler/sweep, no cached/persisted totals.
- **No new datastore, queue, or env var.**
- **No agent changes** (Python or Rust) - cost data is entered/stored server-side on existing `assets`.
- **No cost-entry UI redesign** beyond the minimal license/consumable cost field(s); asset purchase cost entry already exists (`PATCH /purchase`, `FinancePanel.tsx`).
- **Do not use `view:finops`** for ITAM cost - it is the cloud-spend permission and is granted to the broad `viewer` role.
- **Do not roll up Phase 71 PO totals** (float dollars, different grain).
- **Do not hand-roll `$lookup` aggregations** across collections.

## Installation

```bash
# Nothing to install. v4.2 adds no dependencies.
# Verify the tree is unchanged after the milestone:
git diff --stat -- backend/requirements.txt package.json package-lock.json   # expect empty
```

## Sources

- `backend/rbac_service.py`, `backend/rbac_utils.py`, `backend/authentication_endpoints.py` (/login, /me), `backend/app_startup.py` (seeded roles) - HIGH (read directly)
- `components/Sidebar.tsx`, `App.tsx` (`viewPermissionMap`, `hasPermission` memo, `setCurrentView` guard), `types.ts` (`Permission`) - HIGH
- `backend/itam_finance_service.py`, `itam_finance_endpoints.py`, `itam_reporting_kpis.py`, `itam_reporting_prebuilt.py`, `itam_models.py`, `itam_license_endpoints.py`, `itam_asset_endpoints.py` (`_require_itam_admin/_viewer`) - HIGH
- `backend/database.py` (`TenantIsolatedCollection.aggregate/find`), `backend/agent_registry_endpoints.py` (asset upsert) - HIGH
- `backend/requirements.txt`, `package.json` (versions quoted above) - HIGH
- `.planning/PROJECT.md` (Phase 63 RBAC-gap history, Phase 72 "reuse computation verbatim" decision, v4.1 dependency-approval precedent) - HIGH
- Sidebar-vs-default-role permission diff computed locally (89 distinct sidebar strings vs 96 granted strings across `rbac_service.py` + `rbac_utils.py`); the 29 ungranted strings must be re-checked against `app_startup.py` seed data and live `roles` documents before treating any as a bug - MEDIUM
