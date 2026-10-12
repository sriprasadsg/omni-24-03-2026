# Architecture Research: v4.2 Catalogue Access Control & Asset Costing

**Domain:** Role-scoped left-nav visibility + tenant/endpoint asset costing on an existing multi-tenant security/compliance + ITAM platform
**Researched:** 2026-10-12
**Confidence:** HIGH. Every claim below was read directly from this repo (file paths given). Nothing is from generic literature. Items marked ASSUMPTION need a decision or a live check.

## Scope note

This is a subsequent-milestone integration study. The tenant-isolation layer (`TenantIsolatedCollection`, `tenant_context` ContextVar, `TenantMiddleware`), the RBAC layer, the ITAM finance/license services and the React + `apiService` pattern already exist and are not re-researched. This file answers only how the two v4.2 features attach to them.

The most important discovery is that **feature (1) is not greenfield**. The sidebar is already permission-gated today. The work is making that gating trustworthy (one permission resolver, one access manifest, backend routes that actually refuse) rather than building gating. Feature (2) is mostly an aggregation layer, but it hits one real data gap: licenses and consumables have no cost field at all.

---

## 1. Feature 1: Role-based catalogue access

### 1.1 What exists today (verified)

```
Login / refresh                                  Browser
POST /api/auth/login  ──► user{ permissions[] }  App.tsx  hasPermission (useMemo, ~L1185)
GET  /api/auth/me     ──► user{ permissions[] }    │  Super Admin -> always true
   (authentication_endpoints.py L223-231, L266-281)│  else: currentUser.permissions ∩ tenant.enabledFeatures
                                                   │  else fallback: roles[] from /api/roles stub
JWT claims = { sub, role, tenant_id }  (no perms)  ▼
                                              UserContext  (contexts/UserContext.tsx)
                                                   │ hasPermission, enabledFeatures
                                                   ▼
                                  components/Sidebar.tsx  navGroups (188 items, 89 distinct `view:`/`manage:` strings)
                                     visibleGroups filter: hasPermission(item.permission)
                                                          + minTier lock + bundle featureKey
                                                   ▼
                                  App.tsx handleSetCurrentView  (viewPermissionMap, L242-440)
```

Key facts:

| Fact | Where | Consequence |
|------|-------|-------------|
| Permissions reach the frontend as a `permissions: string[]` field on the user object returned by `/api/auth/login` and `/api/auth/me`. They are NOT JWT claims and there is no dedicated permissions endpoint. | `backend/authentication_endpoints.py` L223-231, L266-281; JWT payload L214 is `{sub, role, tenant_id}` | No token staleness problem. A role edit takes effect on next `/me` fetch. No new delivery channel is needed, only a correct payload. |
| The sidebar is defined in `components/Sidebar.tsx`, a `NavItem{view,label,icon,permission,minTier?,featureKey?}` array inside `navGroups`. Filtering is `hasPermission(item.permission)` at L449-456. | `components/Sidebar.tsx` L208-466 | The "nav gated by `view:`" mechanism already exists. The feature is correctness and parity, not creation. |
| A second, independent view-to-permission table exists in `App.tsx` (`viewPermissionMap`, `Record<AppView, Permission>`). The two tables disagree. Example: `agentCapabilities` is `view:agents` in App.tsx but `view:agent_capabilities` in Sidebar. `softwareDeployment`, `trustPage` and others are similar. | `App.tsx` L242-440 vs `Sidebar.tsx` | Two sources of truth in the frontend alone. Click-time check and render-time check can disagree. |
| `/login` and `/me` build `permissions` ONLY from a `roles` collection document (`find_role_doc`). If no role doc exists, `permissions` is `[]`. No fallback to the in-code `default_roles`. | `authentication_endpoints.py` L227-231; `rbac_service.find_role_doc` | `itam_admin`, `itam_user`, `itam_viewer` have in-code defaults (`rbac_service.default_roles`, `rbac_utils.verify_permission`) but are NOT seeded as role docs (`app_startup.py` seeds only Super Admin, Tenant Admin, analyst, security_analyst, incident_responder, user, viewer). Those three roles are authorized by the backend but get `permissions: []` and an empty sidebar. This is a live UI-vs-backend mismatch. |
| Backend has TWO permission engines with different semantics. `rbac_utils.verify_permission` (used by `require_permission`, `_require_itam_admin`, `_require_itam_viewer`) = in-code defaults OR role doc (union). `rbac_service.get_user_permissions` / `has_permission` = role doc, else in-code defaults (not a union). Their default tables are separate copies and have already drifted (e.g. only rbac_utils lists `view:sbom` etc. for Tenant Admin, `control:remote_access`). | `backend/rbac_utils.py` L62-214; `backend/rbac_service.py` L50-201 | "What the UI shows" can only equal "what the backend allows" if both read ONE resolver. |
| The frontend intersects `currentUser.permissions` with `tenant.enabledFeatures` (a per-tenant feature allowlist). The backend does not enforce `enabledFeatures` (only `autonomous_remediation_service.py` reads it). | `App.tsx` L1202-1212 | Tenant feature flags are a UI-only gate. This is a subscription/bundle concern separate from role access. Do not "fix" it in v4.2, but do not confuse it with RBAC. |
| In-app navigation bypasses the gate. `onNavigate={(view) => setCurrentView(view)}` (App.tsx L2192) and `setCurrentView` calls at L807/1066/1365 skip `handleSetCurrentView`. `renderView` has no per-view permission check. `handleSetCurrentView` special-cases only `'Super Admin'`/`'superadmin'`, not `'super_admin'`. | `App.tsx` L1379-1395, L2192 | A hidden catalogue is still reachable through a cross-link. Only the backend stops it, so backend parity is mandatory, not optional. |
| Backend route authorization is heavily uneven. Of 284 router files, 63 contain no permission-guard reference at all (auth-only `Depends(get_current_user)`). Includes `asset_endpoints.py` (`/api/assets`, `GET` has no `view:assets` check), `agent_core_endpoints.py`, `vendor_endpoints.py`, `mssp_endpoints.py`, `jit_access_endpoints.py`, `trust_endpoints.py`. Router-level `include_router(..., dependencies=...)` is not used anywhere. | grep of `backend/*.py`; `router_registry.py` | "Backend already refuses these routes to that role" is false for a large share of catalogues. The requirement cannot be assumed satisfied. It must be measured, then closed. |
| Vocabulary mismatch. 64 of the 89 permission strings used by Sidebar items are not the string any backend `require_permission/has_permission/verify_permission` call checks (e.g. `view:agent_capabilities`, `view:mdr`, `view:patching`, `view:logs`, `view:finops`, `view:network`). The backend mostly enforces coarse strings (`manage:settings` x122, `manage:compliance` x69, `view:dashboard` x58, `investigate:security` x48). | grep, 61 enforced strings total | A sidebar item gated on `view:mdr` has no backend route that checks `view:mdr`. Mirroring needs a route-to-catalogue map, not string equality. |
| `/api/roles` is a hard-coded stub (`role_endpoints.py`) returning `Admin/User/Viewer` with `read:*` permissions. The frontend falls back to it when the user has no permissions. | `backend/role_endpoints.py` | The fallback path can never match the real permission vocabulary. Remove or neutralize it. |

### 1.2 Recommended architecture

Principle: **the backend resolves the effective permission set once; the frontend only renders it; a test proves the two agree.** No new permission model.

```
                    ┌──────────────────────────────────────────────┐
                    │ shared/catalogue-access.json   (NEW, source of truth)
                    │  { "<AppView>": { "permission": "view:x",
                    │                   "routes": ["/api/assets", ...] } }
                    └───────┬───────────────────────────┬──────────┘
          imported by       │                           │  read by
                            ▼                           ▼
   Frontend (Vite JSON import)                Backend (tests + optional startup check)
   catalogueAccess.ts (NEW)                   tests/test_catalogue_route_parity.py (NEW)
     ├─ Sidebar.tsx  (permission lookup)        introspects FastAPI routes: each route in the
     ├─ App.tsx handleSetCurrentView            manifest must carry a guard dependency whose
     └─ App.tsx renderView <ViewGate>           tagged permission == manifest permission
                                                (or the route is on an explicit gap ledger)

   Effective permissions (one resolver)
   rbac_utils.effective_permissions(user)  (NEW, one function)
     = normalize role -> (default table ∪ tenant/global role doc) ; "*" for super admin
     used by: verify_permission, require_permission, rbac_service.has_permission (delegates),
              /api/auth/login, /api/auth/me   (so `permissions` in the payload == enforcement)
```

#### Component boundaries

| Component | Status | Responsibility | Talks to |
|-----------|--------|----------------|----------|
| `backend/rbac_utils.py` `effective_permissions()` | NEW function in MODIFIED file | Single resolver: normalized role, in-code defaults union role doc (tenant doc, then `all`/`platform` doc via `find_role_doc`), `*` for super admin, fail closed on DB error. | `rbac_service.find_role_doc`, `database.get_database` |
| `backend/rbac_utils.py` `verify_permission`, `require_permission` | MODIFIED | Delegate to `effective_permissions`; tag the returned dependency `dependency.required_permission = permission` so tests can introspect it. | `effective_permissions` |
| `backend/rbac_service.py` `get_user_permissions`, `has_permission` | MODIFIED | Delegate to the same resolver. Delete the duplicate `default_roles`/`DEFAULT_PERMISSIONS` drift by keeping ONE table (move to a small `rbac_defaults.py`, imported by both). | `effective_permissions` |
| `backend/authentication_endpoints.py` `/login`, `/me` | MODIFIED | Return `permissions = await effective_permissions(user)` instead of "role doc or []". Keep the field name so `App.tsx` needs no contract change. Note: `/login` has the MFA branch; apply to the full-JWT branch and the `/me` path. | `effective_permissions` |
| `backend/role_endpoints.py` stub | MODIFIED (or retire) | Stop being a fallback source for the UI. | none |
| `backend/itam_asset_endpoints.py` `_require_itam_admin/_viewer` | MODIFIED (tag only) | Tag with `required_permission`/`accepts` metadata for parity test. Logic unchanged. | `verify_permission` |
| `shared/catalogue-access.json` | NEW | View id to permission and the backend route prefixes that must be guarded by it. | frontend + tests |
| `catalogueAccess.ts` | NEW | Typed re-export of the manifest; `permissionForView(view)`. | `Sidebar.tsx`, `App.tsx` |
| `components/Sidebar.tsx` | MODIFIED | Replace the inline `permission:` literals with `permissionForView(view)` (or assert at module load that they match). Keep label/icon/tier fields inline. | `catalogueAccess.ts`, `UserContext` |
| `App.tsx` | MODIFIED (small) | Delete `viewPermissionMap`, use the manifest; fix `super_admin` omission; add `<ViewGate>` around `renderView` so cross-links obey the same rule; drop `/api/roles` fallback. File is already 2,211 lines, so put new logic in new files. | `catalogueAccess.ts` |
| `components/common/ViewGate.tsx` | NEW | Renders "access denied" if `!hasPermission(permissionForView(view))`. Cosmetic only. | `UserContext` |
| Backend route guards in the 63 unguarded routers | MODIFIED (many files) | Add `dependencies=[Depends(require_permission("view:x"))]` at `APIRouter(...)` for read-only catalogue routers, per-route `manage:*` for writes. | `rbac_utils` |
| `backend/tests/test_catalogue_route_parity.py` | NEW | Builds the app (or loads routers via `router_registry`), walks `app.routes`, resolves each manifest route's dependency tree, asserts a tagged guard permission. Emits a gap report. | manifest, FastAPI |
| `src/__tests__` / vitest `catalogueAccess.test.ts` | NEW | Every Sidebar item's permission equals manifest; every AppView has an entry; no view is present in Sidebar but absent from manifest. | manifest, Sidebar |
| `app_startup.py` role seeding | MODIFIED | Seed `itam_admin/itam_user/itam_viewer` role docs (idempotent `update_one(..., upsert=True)`, same pattern as the standard roles block L446-527) so the DB view matches defaults. Optional if the resolver unions defaults, but cheap and removes an operator trap. | `db.roles` |

### 1.3 Why a manifest, and why not "compute visibility server-side"

Considered: a `GET /api/auth/navigation` that returns allowed view ids. Rejected as primary design.
- Labels, icons, tier locks and bundle flags already live in `Sidebar.tsx`. Moving them server-side is a large rewrite with no security gain; the backend route guard is the security boundary regardless.
- Delivering the full effective `permissions[]` (already the contract) plus a shared view-to-permission manifest gives the same result with zero new endpoints.
- What matters for defense in depth is the parity test and the route guards, not where the boolean is computed.

Considered: keep `Sidebar.tsx` literals and diff them by parsing TSX in pytest. Rejected: brittle. A JSON manifest imported by both sides is the smallest durable seam. (ASSUMPTION: Vite resolves JSON import from a repo-level `shared/` folder. `tsconfig` `resolveJsonModule` and the vitest config need a one-line check in the first plan.)

### 1.4 Defense-in-depth rule, made explicit

1. **Authoritative layer = backend.** A catalogue's routes must refuse a role lacking the manifest permission with 403. This is enforced by FastAPI dependencies, not by the UI.
2. **UI layer = convenience.** Hiding a nav item is a UX mirror. If the UI hides something the backend still serves, nothing is protected. If the UI shows something the backend refuses, the user sees 403 pages (this is today's `itam_viewer` bug the ITAM viewer helper comment already describes).
3. **The mirror is enforced by a test, not by convention.** `test_catalogue_route_parity` fails CI when a manifest catalogue has a route with no guard or a guard with a different permission, unless that route is on a committed, reviewed gap ledger (`deferred-items` style). The ledger shrinks phase by phase.
4. **Rule for hiding:** a nav item may be hidden by permission only when the manifest lists at least one backend route prefix guarded by that permission. Catalogues with no guarded backend yet stay visible to today's audience and are listed as gaps. This avoids the false-security failure mode of hiding UI for data the API still serves.

### 1.5 Scope control (decision needed from the roadmapper)

"Catalogue" = 188 nav items across about 8 groups. Hardening 63 unguarded routers is the largest hidden cost of this milestone. Recommended cut:
- v4.2 delivers the resolver, manifest, parity test with gap report, ViewGate, and full guard coverage for the groups the stakeholder cares about first (Assets/Agents/ITAM/Management & Settings, which also contain the costing surface).
- Remaining groups are closed in later phases from the gap ledger, ordered by data sensitivity. Stating this up front prevents the phase from silently ballooning.

---

## 2. Feature 2: Org-level and endpoint-level asset costing

### 2.1 What exists today (verified)

| Need | Existing piece | Where |
|------|----------------|-------|
| Purchase cost per asset | `assets.purchaseCostCents` (int cents), `purchaseDate`, `modelId`, `purchase_order_id`, `supplierId` | `itam_models.py` L123, L284; written by `PATCH /api/assets/{id}/purchase` (`itam_finance_endpoints.py`) |
| Straight-line book value (pure fn) | `compute_book_value(purchase_date, cost_cents, useful_life_years, salvage_cents, now)` returns `bookValueCents`, `yearsElapsed`, `annualDepreciationCents`. Whole-year steps, floors at salvage. Raises `ValueError` on bad input. | `itam_finance_service.py` L70-115 |
| Depreciation policy | On the asset MODEL: `asset_models.usefulLifeYears`, `salvageValueCents`. Per-asset `useful_life_years`/`salvage_value` fields exist on the asset model but `get_asset_book_value` and the KPI ignore them. | `itam_models.py` L219-220; `itam_finance_endpoints.py` L162-169 |
| Tenant-wide book value rollup | `_compute_asset_value_kpi(db, assets)` (batched `asset_models` lookup; counts `withoutPolicyCount`; `hasData` flag; never fabricates 0) | `itam_reporting_kpis.py` L53-124, served by `GET /api/itam/kpis` |
| Per-asset cost rows | `_build_asset_value_rows` (inlined copy of the same logic for a report) | `itam_reporting_prebuilt.py` L109+ |
| Licenses | `licenses`: `seatCount`, `expiryDate`. NO cost field. `license_assignments`: `licenseId`, `targetType` (`user` or `asset`), `targetId`. | `itam_models.py` L319-385 |
| Consumables | `itam_consumables`: `initialQuantity`, `availableQuantity`, embedded `checkoutRecords[]` with `assignedToType` in `user/asset/location/system`. NO cost field. | `itam_models.py` L391-449; `itam_consumable_service.py` |
| Components | `ComponentCreate` has no cost field either. | `itam_models.py` L453+ |
| Auth guards for ITAM reads | `_require_itam_viewer` (`view:itam` or `manage:assets`, API-key scope aware) | `itam_asset_endpoints.py` L68-93 |
| Asset to endpoint mapping | Agent heartbeat upserts the asset doc with `id = f"asset-{hostname}"` and `tenantId`. Agent docs carry `assetId`. Manual assets have no agent. | `agent_heartbeat_endpoints.py` L235, L311-324; `agent_registry_endpoints.py` L238, L299 |
| Asset to tenant mapping | Every `assets` doc has `tenantId`; reads through `get_database()` are auto-scoped by `TenantIsolatedCollection`. | `database.py` L38-155 |
| Super-admin tenant selection | `TenantMiddleware` sets the ContextVar from JWT `tenant_id`, overridden by `X-Tenant-ID` header for super admins. `authFetch(url, {tenantId})` already sends that header. Un-overridden super admin context is `platform-admin` (isolation bypass). | `tenant_middleware.py` L82-96; `apiService.ts` L244-259 |

Two blocking data gaps (flag to roadmapper):
1. **License and consumable cost fields do not exist.** The milestone text says "no new cost-entry system", but "license spend" and "allocated license cost" cannot be computed without a cost number on the license. The minimal, additive fix is optional fields on the existing models (not a new system): `licenses.totalCostCents` + `costPeriod` (`one_time|monthly|annual`), `itam_consumables.unitCostCents`. This needs a small entry affordance in `LicensesPanel.tsx` and the consumable UI. Without it the license column ships permanently empty.
2. **Currency and period.** Everything is integer cents with no currency field (UI hard-codes `$`). Annual vs monthly vs one-time license cost must not be summed naively. Define allocation as: per-seat cost = `totalCostCents / seatCount`; allocated to an asset = per-seat cost x its asset-targeted seats; unassigned seats are "idle license spend" at org level. State the period in the response (`costPeriod`) and sum only like periods, or annualize explicitly.

### 2.2 Recommended architecture

A new **read-only aggregation layer**. No writes, no new collections, no stored derived values (matches the repo's "computed at read time, never persisted" convention for book value and warranty).

```
 Frontend                                         Backend
 ITAMConsole.tsx  (new "Costs" tab)               itam_cost_endpoints.py  (NEW router /api/itam/costs)
   └─ CostsPanel.tsx (NEW)                          ├─ GET /summary                 org rollup
        ├─ org tiles + breakdown charts             ├─ GET /assets                  per-endpoint rows (paginated, sortable)
        ├─ per-endpoint table                       └─ GET /assets/{asset_id}       one asset, license + consumable lines
        └─ asset drill-in (lines)                       Depends(_require_itam_viewer)   <- same guard as /book-value and /kpis
   apiService.ts (+3 fns, authFetch, tenantId opt)      │
   types.ts (+ItamCostSummary, ItamAssetCost)           ▼
                                                    itam_cost_service.py  (NEW, pure, db passed in; no FastAPI import)
                                                      ├─ asset_cost_snapshot(asset, model, now)  -> uses compute_book_value verbatim
                                                      ├─ license_allocation(licenses, assignments) -> per-asset + idle
                                                      ├─ consumable_allocation(consumables)       -> per-asset
                                                      └─ rollup(...) -> summary + coverage
                                                            │ reads (tenant-scoped via wrapper)
                                                            ▼
                                                    assets, asset_models, licenses,
                                                    license_assignments, itam_consumables, agents (assetId join)
```

#### Component boundaries

| Component | Status | Responsibility | Communicates with |
|-----------|--------|----------------|-------------------|
| `backend/itam_cost_service.py` | NEW | Pure computation module (follows `itam_reporting_kpis.py` shape: imports no FastAPI, receives `db`). Single place where org and endpoint cost are derived. Imports `compute_book_value` from `itam_finance_service`. | `itam_finance_service`, passed-in `db` |
| `backend/itam_cost_endpoints.py` | NEW | Router `prefix="/api/itam/costs"` (distinct prefix, same reason as `itam_kpi_endpoints.py`: cannot shadow `/api/assets/{id}` routes). Resolves tenant, calls service, shapes JSON, 500 handling like the KPI route. | `itam_cost_service`, `_require_itam_viewer`, `get_database` |
| `backend/router_registry.py` (and `app.py` `_load` list L92-108) | MODIFIED (1 line) | Register `_load(app, "itam_cost_endpoints", "router")` after `itam_kpi_endpoints`. | |
| `backend/itam_finance_service.py` | MODIFIED (optional, additive) | Add a small DB-free `compute_asset_book_value_for(asset, model_doc, now)` returning `{bookValueCents, reason}` so cost service, KPI and the asset_value report share one resolution path. Existing KPI/report keep working; refactor them onto it as a follow-up guarded by an equality test (cost summary `totalBookValueCents` == `/api/itam/kpis` `asset_value.totalBookValueCents`). | |
| `backend/itam_models.py` | MODIFIED | Add optional `totalCostCents`, `costPeriod` to `LicenseCreate/Update`; `unitCostCents` to `ConsumableCreate/Update`. `extra="forbid"` means the models MUST be extended or the UI cannot save the field. Optional + nullable, so no migration. | |
| `components/itam/CostsPanel.tsx` | NEW | The surface. Keep under 500 lines; split `CostSummaryTiles.tsx` and `EndpointCostTable.tsx` if needed. | `apiService`, `UserContext` |
| `components/itam/ITAMConsole.tsx` | MODIFIED | Add `'costs'` to `Tab` + `TABS` (+ i18n keys in `itamI18n.tsx`). Pass `tenants`/`isSuperAdminView`. | `CostsPanel` |
| `components/itam/LicensesPanel.tsx` (+ consumable UI) | MODIFIED | Add optional cost inputs. | `apiService` |
| `services/apiService.ts`, `types.ts` | MODIFIED | `fetchItamCostSummary`, `fetchItamAssetCosts`, `fetchItamAssetCost` using `authFetch` + `itamThrow`, same shape as `fetchItamKpis` (L6061). | |
| Sidebar | UNCHANGED | Costing lives inside the existing `itam` catalogue (`view:itam`), so no new nav item and no new permission. | |

#### Response contract (proposed)

```jsonc
// GET /api/itam/costs/summary
{
  "tenantId": "t-123", "currency": null, "computedAt": "...",
  "assets": { "total": 120, "withPurchaseCost": 74, "withDepreciationPolicy": 61, "withoutCostCount": 46 },
  "purchase":  { "totalCents": 18400000 },
  "bookValue": { "totalCents": 11200000, "accumulatedDepreciationCents": 6100000, "unvaluedCount": 59 },
  "licenses":  { "period": "annual", "totalCents": 5200000, "allocatedCents": 3900000, "idleCents": 1300000,
                 "unattributedUserSeatsCents": 800000 },
  "consumables": { "allocatedToAssetsCents": 120000, "unitCostMissingCount": 4 },
  "byLifecycleStatus": [ { "status": "deployed", "assetCount": 80, "purchaseCents": ..., "bookValueCents": ... } ],
  "hasData": true
}
// GET /api/itam/costs/assets?sort=-totalCostCents&limit=50&cursor=...
{ "items": [ { "assetId": "asset-LAPTOP01", "hostname": "LAPTOP01", "assetTag": "T-0012",
               "agentId": "agent-...", "lifecycleStatus": "deployed",
               "purchaseCostCents": 180000, "bookValueCents": 90000, "bookValueReason": null,
               "licenseAllocatedCents": 21000, "consumableAllocatedCents": 0,
               "totalCostCents": 111000 } ], "nextCursor": null }
```

`hasData`/`reason` fields follow the ITAM-REP-04 precedent: a missing input yields `null` plus a reason, never a fabricated `0`.

### 2.3 Asset to endpoint to tenant mapping

- **Tenant:** never taken from the request body or a query parameter by a normal user. Resolve as: `tenant_id = current_user.tenant_id`; run all reads through `get_database()` (wrapper auto-injects `tenantId`). The service also adds an explicit `tenantId` filter on every raw `find` as belt and braces, because `itam_*` services are also called from background paths.
- **Super admin:** the ContextVar is `platform-admin` (isolation bypassed) unless `X-Tenant-ID` is sent. The cost route must reject `platform-admin`/missing tenant with 400 "select a tenant" rather than silently aggregating across all tenants. This is a deliberate decision: a cross-tenant total is a different product feature and a data-leak surface. The UI sends the tenant via the existing `authFetch(..., {tenantId})` option.
- **Endpoint:** an endpoint is an `assets` document. Agent-discovered assets have `id = asset-{hostname}` (heartbeat upsert); manual ITAM assets have `asset-<hex>` ids and no agent. "Per endpoint" rows are all assets; the agent link is a batched join `agents.find({assetId: {$in: ids}})` projected to `{id, assetId, hostname}`. Show `agentId` when present; manual assets still appear (they are costed assets even without telemetry).
- **License to asset:** `license_assignments` rows with `targetType == "asset"` and `targetId == asset.id`. Seats assigned to a `user` target are not attributable to an endpoint; report them as `unattributedUserSeatsCents`, do not guess. (Optional later enhancement: attribute via the user's checked-out assets.)
- **Consumable to asset:** `checkoutRecords` with `assignedToType == "asset"`; cost = quantity x `unitCostCents`. Check-ins reduce effective quantity; confirm the record semantics against `itam_consumable_service.py` before coding (ASSUMPTION: records are append-only checkouts and check-ins adjust `availableQuantity` only).
- **Do not sum purchase orders.** `PurchaseOrder.total_cost` is a float in dollars and overlaps with asset `purchaseCostCents`. Summing both double counts. PO data is a drill-through/reconciliation aid only.

### 2.4 Authorization for the cost surface

- Reuse `_require_itam_viewer` (`view:itam` or `manage:assets`). Principle: **a role that can already read per-asset book value (`GET /api/assets/{id}/book-value`, same guard) may read its rollup; a role that cannot, cannot.** The KPI route already exposes `totalBookValueCents` to `view:itam`.
- Decision flag: if finance wants costs visible to fewer roles than ITAM viewers, the existing unused permission `manage:finance` (present in `itam_admin` defaults, enforced nowhere today) is the no-new-model option. Recommend NOT tightening in v4.2 unless asked.
- Cost routes are covered by the new parity test: manifest entry `itam` lists `/api/itam/costs`.
- API-key access works automatically via `_require_itam_viewer` scope narrowing.

---

## 3. Data flow summary

```
Feature 1 (visibility)
  login/me -> effective_permissions(user)  [single resolver, same one require_permission uses]
           -> user.permissions[] -> App.tsx hasPermission (∩ tenant.enabledFeatures, UI-only)
           -> Sidebar filter via catalogueAccess.permissionForView(view)
           -> click/cross-link -> ViewGate (same rule)
           -> any API call -> route dependency require_permission(...)  <-- authoritative 403
  CI: manifest + FastAPI route introspection proves every manifest route is guarded by that permission.

Feature 2 (costing)
  CostsPanel mount -> fetchItamCostSummary()/fetchItamAssetCosts()  (authFetch; X-Tenant-ID for super admin)
    -> TenantMiddleware sets ContextVar -> _require_itam_viewer (403 if no view:itam / manage:assets)
    -> itam_cost_service reads assets/asset_models/licenses/license_assignments/itam_consumables/agents
         (all through tenant-wrapped db) -> compute_book_value per asset -> allocate licenses/consumables
    -> JSON with coverage + reasons -> tiles, charts, endpoint table
```

## 4. Patterns to follow

### Pattern 1: Pure service plus thin router (repo convention)
**What:** `itam_cost_service.py` imports no FastAPI and resolves no DB handle itself; the router passes `db`. Matches `itam_finance_service.py` / `itam_reporting_kpis.py` / `itam_kpi_endpoints.py`.
**When:** All aggregation logic. Keeps it unit-testable with `asyncio.run()` (the repo's established test style; pytest-asyncio is not installed).

### Pattern 2: Reuse the owning function verbatim
**What:** Cost figures call `compute_book_value` directly (Key Decision, v4.1 Phase 72). Add an equality test against `/api/itam/kpis` so the two can never diverge.

### Pattern 3: Tag guards for introspection
**What:** `require_permission` returns a closure; set `dependency.required_permission = permission` (and the same on `_require_itam_viewer/_admin`). The parity test reads that attribute while walking `route.dependant.dependencies`.
**Example:**
```python
def require_permission(permission: str):
    async def dependency(user: TokenData = Depends(get_current_user)):
        ...
    dependency.required_permission = permission   # NEW: lets tests prove route -> permission
    return dependency
```

### Pattern 4: Explicit gap ledger instead of silent coverage
**What:** The parity test reads `shared/catalogue-gaps.json` (route prefix, reason, owner phase). A route not guarded and not on the ledger fails CI. Gaps are visible, shrinking, and reviewable.

### Pattern 5: Null plus reason, never a fabricated zero
**What:** Missing purchase record, policy, or license cost produces `null` and a counted `unvaluedCount`/`reason`, mirroring `REASON_NO_PURCHASE_RECORD` and the KPI `hasData` pattern.

## 5. Anti-patterns to avoid

| Anti-pattern | Why it is wrong here | Do this instead |
|--------------|---------------------|-----------------|
| Gate the UI on a permission the backend does not enforce | Looks secure, protects nothing, and the cross-links in `App.tsx` still reach the view | Parity test plus gap ledger; hide only where a guarded route exists |
| Add a second role to permission table for the UI (e.g. `GET /api/catalogue-permissions`) | A third source of truth next to `default_roles`, `DEFAULT_PERMISSIONS`, and `db.roles` | One resolver, one defaults table, existing `permissions[]` field |
| Put permissions in JWT claims | Stale after role edit; token bloat; `/me` already carries them | Keep `/login` + `/me` delivery |
| Compute cost with a new stored field or nightly job | Repo rule: derived finance values are read-time only; stored copies drift from `compute_book_value` | Read-time aggregation |
| Loop per asset with `find_one` for model/agent/assignments | N+1 on large tenants; the KPI explicitly batches `asset_models` | Batch with `$in` and group in Python; stream with projection |
| Reuse `GET /api/assets` pagination for totals | Capped at `page_size<=100` and cached 60s with `@cached` | Own full-scan with projection (KPI uses `to_list(None)`) |
| Sum POs plus asset purchase cost | Double counts | Asset `purchaseCostCents` is the figure; POs are reference only |
| Aggregate across tenants for super admin | `platform-admin` bypasses isolation; cross-tenant leak | Require an explicit tenant; 400 otherwise |
| Add the costing to the Sidebar as a new item | New catalogue means new permission pressure | Tab inside the existing `itam` catalogue |

## 6. Multi-tenant isolation checklist (must hold)

1. Every cost query goes through `get_database()` (wrapped) or carries an explicit `tenantId` filter. No `db._db` raw access in the cost path.
2. Super admin without `X-Tenant-ID` gets 400, never an all-tenant aggregate.
3. Joins (`agents`, `asset_models`, `license_assignments`) are tenant-scoped; ids from one tenant's asset must never be looked up unscoped. A colliding `asset-{hostname}` id across tenants resolves per tenant because the wrapper injects `tenantId`.
4. Tests: two-tenant fixture where tenant B has costed assets; tenant A's summary/rows/detail contain none of B's totals, and `GET /assets/{id}` for B's id returns 404 (not 403), matching `_load_asset`'s same-404 rule.
5. `effective_permissions` resolves the role doc through `find_role_doc` (tenant doc first, then `all`/`platform` sentinels), never an unscoped `roles.find_one`.

## 7. Scalability

| Concern | Typical tenant (100s of assets) | Large tenant (10K+ assets) | Action |
|---------|--------------------------------|-----------------------------|--------|
| Summary scan | One projected `find` + one `$in` model lookup | Still O(assets) in Python; seconds | Stream cursor with projection; consider a short TTL cache keyed by `(tenant, version)`, but only after measuring |
| Per-endpoint table | Return all | Keyset pagination on `id`; sort in Python only for the page set, or sort server-side by a stored sort key | Start with limit/cursor from day one so the contract does not change |
| License allocation | A few licenses | Thousands of assignments | Single `aggregate` grouping `license_assignments` by `licenseId,targetId` (wrapper prepends tenant `$match`) |
| Parity test runtime | Imports ~300 routers | Same | Run in CI only; load via `router_registry` with mongomock fallback already present in `database.py` |

First bottleneck: the summary scan on very large tenants (fix with aggregation pushdown for purchase totals, keep depreciation in Python since it needs the model policy).

## 8. Suggested build order (dependency-driven)

Phases continue from 75 per PROJECT.md. Suggested numbers are indicative.

| # | Phase | Contains | Depends on | Why this position |
|---|-------|----------|-----------|-------------------|
| 75 | Permission resolver unification + delivery fix | `effective_permissions()`, single defaults table, `/login` + `/me` return effective perms, tag guards, seed `itam_*` role docs, neutralize `/api/roles` fallback | none | Everything in Feature 1 depends on "what the UI shows == what the backend decides". Also fixes the live `itam_*` empty-sidebar bug. Low UI risk. |
| 76 | Catalogue manifest + parity test + gap ledger | `shared/catalogue-access.json`, `catalogueAccess.ts`, vitest drift test, `test_catalogue_route_parity.py`, initial gap report (read-only audit, no behavior change) | 75 | Converts an unknown (how many routes are unguarded) into a measured backlog before any hiding/hardening decisions. Also resolves the Sidebar vs `viewPermissionMap` divergence. |
| 77 | Backend route guards for in-scope catalogues | Router-level `require_permission` on the unguarded routers in the agreed groups (start with Assets/Agents/ITAM-adjacent/Settings), shrink ledger | 76 | Must precede any UI claim of "mirrors backend". Largest effort; can split into batches by sidebar group. |
| 78 | Sidebar + ViewGate rewiring | Sidebar reads manifest, `handleSetCurrentView` + `renderView` ViewGate, `super_admin` fix, role-matrix manual verification per role | 75, 76 (77 for any catalogue it hides) | UI change is last for Feature 1 so hiding never outruns enforcement. |
| 79 | Cost data model additions | `licenses.totalCostCents/costPeriod`, `itam_consumables.unitCostCents` (models + create/update + minimal inputs in `LicensesPanel`/consumable UI) | none (parallel with 75-78) | Unblocks license/consumable cost. Independent of Feature 1, so it can run in parallel if capacity allows. |
| 80 | Cost aggregation API | `itam_cost_service.py`, `itam_cost_endpoints.py`, router registration, optional shared book-value helper, equality test vs KPI, two-tenant isolation tests | 79 for license/consumable lines; purchase/book-value part can start immediately | Cost UI needs a stable contract first. Ship purchase + book value first, license lines when 79 lands. |
| 81 | Cost UI | `CostsPanel` (+ split components), `ITAMConsole` tab, `apiService`/`types`, i18n keys, per-endpoint table, drill-in, coverage banner linking to Finance tab | 80 | Pure consumer of the API. Includes the super-admin tenant picker behavior. |

Parallelism: Feature 2 (79 to 81) is independent of Feature 1 (75 to 78) except that the new `/api/itam/costs` routes must be added to the manifest (a one-line entry in 76/80 whichever lands second). Two parallel tracks are viable.

## 9. Research flags for phases

| Phase | Flag |
|-------|------|
| 77 (route guards) | Needs per-group research: for each unguarded router, which `view:` string is the right guard, and whether agents or tokens call these routes without a user session (agent endpoints under `/api/agents/*` use agent auth, not user RBAC; guarding them with user permissions would break telemetry). Agent-facing routes must be excluded from the manifest and the parity test. |
| 75 | Needs a role x catalogue matrix review with the stakeholder: today many sidebar permissions (`view:autopilot`, `view:mdm`, `view:unified_ops`, ...) exist only in the Super Admin role doc, so Tenant Admin does not see those catalogues. Decide whether to grant them, since visibility will now be intentionally defined. |
| 79/80 | Confirm period/currency semantics and the consumable checkout/check-in record semantics (see 2.3). |
| 81 | Standard patterns (clone `ItamKpiPanel`/`FinancePanel`); low risk. |
| 76 | Standard patterns once the JSON import is confirmed in Vite/vitest/tsconfig. |

## 10. Integration points by file (quick index)

Modified: `backend/rbac_utils.py`, `backend/rbac_service.py`, `backend/authentication_endpoints.py`, `backend/role_endpoints.py`, `backend/itam_asset_endpoints.py` (tag only), `backend/app_startup.py` (role seeds), `backend/itam_models.py`, `backend/itam_finance_service.py` (optional helper), `backend/router_registry.py` (+ the `_load` list in `app.py`), up to ~63 unguarded router files in `backend/`, `components/Sidebar.tsx`, `App.tsx`, `components/itam/ITAMConsole.tsx`, `components/itam/LicensesPanel.tsx`, `components/itam/itamI18n.tsx`, `services/apiService.ts`, `types.ts`.

New: `shared/catalogue-access.json`, `shared/catalogue-gaps.json`, `catalogueAccess.ts`, `components/common/ViewGate.tsx`, `backend/rbac_defaults.py` (single defaults table), `backend/itam_cost_service.py`, `backend/itam_cost_endpoints.py`, `components/itam/CostsPanel.tsx` (+ split children), `backend/tests/test_catalogue_route_parity.py`, `backend/tests/test_itam_cost_service.py`, `backend/tests/test_itam_cost_endpoints.py`, vitest `catalogueAccess.test.ts`, `CostsPanel.test.tsx`.

Unchanged: tenant isolation layer, `compute_book_value` semantics, warranty sweep, existing ITAM routers' guards.

## Open questions for the user or roadmapper

1. Catalogue scope for v4.2: all 188 nav items, or the ITAM/Assets/Settings groups first with the rest on a tracked ledger? (Recommendation: the latter.)
2. License cost basis: single total cost per license with a period (recommended) versus per-seat price. Currency: single implicit tenant currency, or add a `currency` field now?
3. Should cost visibility require something tighter than `view:itam` (e.g. `manage:finance`)? (Recommendation: no, keep parity with the existing book-value route.)
4. Super admin behavior: tenant-picker required (recommended) versus a platform-wide cost rollup as a separate future feature.

## Sources

All first-party, read in this session (HIGH confidence): `backend/rbac_utils.py`, `backend/rbac_service.py`, `backend/authentication_endpoints.py`, `backend/role_endpoints.py`, `backend/app_startup.py`, `backend/database.py`, `backend/tenant_middleware.py`, `backend/router_registry.py`, `backend/itam_finance_service.py`, `backend/itam_finance_endpoints.py`, `backend/itam_models.py`, `backend/itam_asset_endpoints.py`, `backend/itam_license_endpoints.py`, `backend/itam_license_service.py`, `backend/itam_reporting_kpis.py`, `backend/itam_kpi_endpoints.py`, `backend/itam_reporting_prebuilt.py`, `backend/asset_endpoints.py`, `backend/agent_heartbeat_endpoints.py`, `components/Sidebar.tsx`, `App.tsx` (L242-440, L1185-1242, L1379-1395, L2060-2080, L2192), `contexts/UserContext.tsx`, `components/itam/ITAMConsole.tsx`, `components/itam/ItamKpiPanel.tsx`, `components/itam/FinancePanel.tsx`, `services/apiService.ts` (`authFetch`, `fetchItamKpis`), `.planning/PROJECT.md`. Counts (284 routers, 63 unguarded, 188 nav items, 89/64 permission strings) come from ad-hoc greps over `backend/*.py` and `components/Sidebar.tsx` on 2026-10-12; re-run when planning phase 76.

---
*Architecture research for: v4.2 Catalogue Access Control & Asset Costing*
*Researched: 2026-10-12*
