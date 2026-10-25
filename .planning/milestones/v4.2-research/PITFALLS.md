# Pitfalls Research: v4.2 Catalogue Access Control & Asset Costing

**Domain:** Adding (1) permission-driven left-nav gating and (2) tenant/endpoint cost rollups to an existing multi-tenant security/compliance + ITAM platform (FastAPI + Motor/MongoDB, React/TS, Python + Rust agents)
**Researched:** 2026-10-12
**Confidence:** HIGH. Almost every finding is a primary-source read of this repo (file and line cited). Generic cost-accounting guidance is marked MEDIUM. No external sources were needed. This replaces the prior v4.0 PITFALLS.md. The v4.0 tenant-isolation/background-scheduler pitfall still applies to any cost sweep or snapshot job.

**Method note:** Verified against `backend/rbac_utils.py`, `backend/rbac_service.py`, `backend/tenant_middleware.py`, `backend/database.py` (`TenantIsolatedCollection`), `backend/authentication_service.py`, `backend/authentication_endpoints.py`, `backend/asset_endpoints.py`, `backend/itam_finance_service.py`, `backend/itam_finance_endpoints.py`, `backend/itam_license_service.py`, `backend/itam_reporting_kpis.py`, `backend/itam_models.py`, `backend/cache_service.py`, `components/Sidebar.tsx`, `contexts/UserContext.tsx` and `App.tsx`. I also ran a scripted diff of the 188 sidebar items against the backend permission tables and against `viewPermissionMap`.

Suggested phase numbers continue from 75, as the milestone requires. They are labels for the roadmapper, not commitments:

| Label | Scope |
|-------|-------|
| **P75** | Backend authorization audit and enforcement for every catalogue's routes, plus the permission manifest |
| **P76** | Sidebar and route gating UI (fail-closed, single source of truth, refresh, empty state) |
| **P77** | Cost data foundation and rollup service (money model, license/consumable cost source, tenant scoping) |
| **P78** | Org-level cost API and UI |
| **P79** | Endpoint-level cost API and UI (asset mapping, license allocation) |

---

## Critical Pitfalls

### Pitfall 1 (TOP): Hiding the menu item without the backend enforcing the matching permission (defense in depth missing)

**What goes wrong:**
The sidebar hides "Compliance" (or any other catalogue) from a role. Any logged-in user of that tenant can still `curl` the catalogue's routes and get data, because many routers only check that the caller is authenticated, not that they hold the permission the nav item claims. The UI looks locked and the system is open.

**Why it happens / evidence in this repo:**
- 269 `*endpoints*.py` files exist. A scripted check found about 50 that import `get_current_user` and contain none of `require_permission`, `verify_permission`, `require_role`, `has_permission`, `_require_itam_admin` or `require_super_admin`. Many map directly to sidebar catalogues:

| Backend file | Catalogue it backs |
|--------------|--------------------|
| `compliance_*` (9 files) | `view:compliance` (23 nav items) |
| `attack_path_endpoints.py` | `view:attack_path` |
| `automation_endpoints.py` | `view:automation` |
| `dora_endpoints.py` | `view:dora_metrics` |
| `ai_system_endpoints.py` | `view:ai_governance` |
| `tracing_endpoints.py` | `view:tracing` |
| `asset_endpoints.py` | `view:assets` |
| `agent_*` (7 files) | `view:agents` |

- The sharpest example is `backend/asset_endpoints.py`. `GET /api/assets` and `GET /api/assets/{id}` depend only on `get_current_user` and project `{"_id": 0}`. The response includes `purchaseCostCents` and `purchaseDate`. The "view:assets" catalogue is therefore open to every authenticated tenant user, and it exposes the same cost data that `GET /{id}/book-value` correctly protects with `_require_itam_viewer`. The new costing feature must not widen this existing hole. Cost fields must be field-gated, or the asset list must be permission-gated.
- The existing precedent that worked is Phase 63. Consumable/component routers used bare `get_current_user` and were found as audit BLOCKERs. The fix was to switch them to `_require_itam_admin`. Phase 62 deliberately shipped an unrestricted GET with an admin-gated PATCH. Catalogue gating needs the same discipline across every router, not only the ones ITAM already covers.

**How to avoid:**
1. **Backend first.** P75 completes before the UI work ships. A nav item may only be gated on `view:X` once every route behind that nav item is verified to enforce `view:X` (or a stricter permission).
2. **Build the manifest.** Create one table: nav view, then permission, then backend router(s) and prefix, then dependency used. Generate it from `Sidebar.tsx` plus an `app.routes` introspection so it cannot rot.
3. **Add a deny-by-default contract test.** For each nav view, call every GET route with (a) a token whose role lacks the permission, expecting 403, and (b) one that has it, expecting non-403. Introspect `app.routes` for any `/api` route whose dependency tree lacks a permission dependency and fail on the new ones (allowlist the intentionally public ones). The Phase 63 review already noted that RBAC test classes assert 403 on only 1-2 of the routes they gate. This milestone needs a per-route sweep.
4. Prefer router-level `dependencies=[Depends(require_permission("view:X"))]` over per-handler wiring, so a new route inherits the guard.
5. Reads need `view:X`. Writes keep their existing `manage:X`. Do not use a `view:` permission to unlock a write.

**Warning signs:**
- A viewer or analyst token returns 200 on a route whose nav item they cannot see.
- A grep for `get_current_user` with no `require_*` nearby in a router that a nav item points at.
- A PR that edits only `Sidebar.tsx`.

**Phase to address:** P75 (enforcement and manifest), then P76 consumes the manifest. The manifest is the contract between the phases.

---

### Pitfall 2: Two divergent permission tables and about 30 sidebar permissions that no backend role grants

**What goes wrong:**
"Show an item only when the role holds the matching view: permission" silently hides about a third of the catalogues from every non-super-admin. Alternatively, someone "fixes" the empty menus by granting the missing permissions broadly and over-grants.

**Why it happens / evidence:**
- A scripted diff of the 188 sidebar items (89 distinct permission strings) against the built-in role tables found 29 strings absent from both `rbac_service.default_roles` and `rbac_utils.verify_permission`'s `DEFAULT_PERMISSIONS`. Examples: `view:mdm`, `view:mam`, `view:autopilot`, `view:app_catalog`, `view:jobs`, `view:web_monitoring`, `view:predictive_health`, `view:goal_system`, `view:zero_trust`, `view:fim`, `view:sca`, `view:mssp`, `view:security_copilot`, `view:config_drift`, `view:retention_policies`, `view:analytics`.
- Another 17 are in only one of the two tables, for example `view:unified_ops`, `view:integrations`, `view:xai`, `view:remote_access`, `manage:agents` (absent from `rbac_service`) and `view:vector_db`, `view:webgpu_inference` (absent from `rbac_utils`).
- Those sidebar strings are matched against the user's `permissions` array. That array comes only from the `roles` collection document, via `find_role_doc` in `authentication_endpoints.py` (the `/login` handler around line 229, and `/me` around line 279). Built-in defaults that `verify_permission` uses are never sent to the client. The UI can therefore show nothing for a role the backend would happily authorize, or the reverse.
- Two enforcement stacks coexist. `rbac_utils.verify_permission` and `require_permission` check defaults first, then the DB role. `rbac_service.has_permission` checks the DB role first, then falls back to its own in-memory `default_roles`. Their default tables have already drifted, and `rbac_utils` comments say so. A new gate on either stack can disagree with a nav item evaluated against the other.
- The `viewPermissionMap` in `App.tsx` (used by `handleSetCurrentView` and the hash router) disagrees with `Sidebar.tsx`'s per-item permission for 9 views: `unifiedOps`, `sustainability`, `agentCapabilities`, `jobs`, `zeroTrustQuantum`, `vulnerabilityManagement`, `persistenceDetection`, `llmops`, `swarm`. A user can see an item the router then silently refuses, or navigate by hash to one the menu hides.

**How to avoid:**
- Pick one source of truth, a single permission catalogue that backend dependencies, role seeding and the frontend nav all read from. At minimum, one JSON/TS manifest that `Sidebar.tsx` and `viewPermissionMap` both import, plus a test asserting every manifest permission exists in the effective default roles.
- Decide deliberately which built-in role gets each currently-ungranted `view:` string. Do not blanket-add them to "user"/"viewer". Record the decision in the manifest.
- The milestone says "no new permission model". Honor that by reconciling existing strings, not inventing new ones. Treat `view:itam` vs `view:assets` carefully: ITAM viewers get `view:itam`, but plain "user"/"viewer" roles have only `view:assets`.
- Existing tenant-defined role documents will not contain any strings added to defaults. Plan a data decision: either defaults are authoritative for the UI too (return effective permissions from `/me`, see Pitfall 5), or run a migration over custom roles.

**Warning signs:**
- Test accounts with role "user" or "viewer" see far fewer items than expected.
- `console.warn("User does not have permission to view: ...")` in the browser for an item the menu displayed.
- A permission string added to `Sidebar.tsx` with no matching string in any backend table.

**Phase to address:** P75 (reconcile tables, define the manifest), enforced in P76.

---

### Pitfall 3: The frontend trusts a client-side permission list, and the Sidebar fails open

**What goes wrong:**
Frontend permission state is treated as authoritative. It is a UI hint only. It is also computed in ways that can fail open or diverge from the backend.

**Why it happens / evidence:**
- `Sidebar.tsx` line about 168: `const hasPermission = userContext?.hasPermission || (() => true);`. If the context is ever missing or not yet provided, every nav item renders. The context default in `UserContext.tsx` is `() => false`, so the two defaults disagree. The fail-open fallback must go.
- `App.tsx` lines about 1185-1241 build `hasPermission` from `currentUser.permissions` (set at login) and then intersect it with `tenant.enabledFeatures`. The backend does no such intersection. A permission the backend would allow can be hidden because the tenant's feature list lacks it, and vice versa. The UI effectively adds a second, undocumented gate that does not exist server-side. Any "UI mirrors the backend" claim must account for it.
- When `permissions` is empty, the UI falls back to `roles.find(...)` by lowercase name. That is a third derivation path.
- Bypass paths around the gate exist. `App.tsx` line about 2192 passes `onNavigate={(view) => setCurrentView(view as any)}`, and lines about 807, 1066 and 1365 call `setCurrentView` directly, so only the sidebar/hash/command paths go through `handleSetCurrentView`. `renderView()` itself has no permission check. Anything that sets `currentView` without the guard renders the dashboard.
- Tampering with the client list (devtools, `sessionStorage`) is irrelevant if Pitfall 1 is fixed, which is why Pitfall 1 is the top item. Without it, this is the whole security model.

**How to avoid:**
- Treat `permissions` as presentation state. State this in code comments and docs.
- Make the nav gate fail closed: `hasPermission` defaults to `() => false`, and an unloaded context renders a skeleton, not the full menu.
- Add a guard inside `renderView()` (or a wrapper `<RequirePermission view=...>`) so every code path that sets `currentView` is gated. Route all `setCurrentView` calls through one guarded function.
- If the `enabledFeatures` intersection stays, mirror it on the backend or drop it from the permission check and keep it as a separate "feature locked" state (`featureKey`/`minTier` already model that).
- Have the backend return effective permissions (defaults plus role doc) so the client list is a faithful projection of what `verify_permission` would answer.

**Warning signs:**
- A nav item visible when the user context is `null`.
- `setCurrentView(` calls outside the guarded handler.
- An item visible to a role and 403 on click, or hidden but the API works.

**Phase to address:** P76 (UI), with P75 providing the effective-permission endpoint.

---

### Pitfall 4: Super-admin / platform-admin handling is inconsistent and leaks across tenants

**What goes wrong:**
Gating tests pass as super-admin (everything visible) and hide real role bugs. Separately, super-admin requests to cost endpoints aggregate every tenant's data.

**Why it happens / evidence:**
- Client super-admin checks differ by place. `Sidebar.tsx` `visibleGroups` recognises `'Super Admin'`, `'superadmin'`, `'super_admin'`. `App.tsx` `hasPermission` recognises `'super admin'`, `'superadmin'`, `'super_admin'`, `'platform-admin'`. `handleSetCurrentView` recognises only `'Super Admin'` and `'superadmin'`. The backend normalises everything through `rbac_service._normalize_role`, which folds `platform-admin` into `super_admin`.
- The `TenantMiddleware` `X-Tenant-ID` override applies only for `role in ["super_admin","Super Admin","superadmin"]`, not for `platform-admin`.
- Super-admin tokens carry `tenant_id = "platform-admin"`. `TenantIsolatedCollection._inject_tenant_id` and `.aggregate` skip tenant scoping entirely when `get_tenant_id() == "platform-admin"`. So **any cost route that uses `get_database()` and no explicit tenant scope, called by a super-admin without `X-Tenant-ID`, returns the sum across all tenants** (and across currencies, see Pitfall 11). `asset_endpoints.get_assets` already shows the pattern of a super-admin being allowed an optional `tenant_id` query parameter.
- The Sidebar shows every item to a super-admin even while "viewing a tenant". There is no way to preview what a tenant role sees.

**How to avoid:**
- Cost endpoints must require an explicit resolved tenant. If the caller is `platform-admin` and no `X-Tenant-ID`/`tenant_id` is supplied, either return 400 ("select a tenant") or return a per-tenant breakdown, never a silent global sum. Add `tenantId` to every aggregation `$match` explicitly (defense in depth on top of the wrapper), as `itam_reporting_kpis.compute_itam_kpis(db, tenant_id)` already accepts a `tenant_id` argument.
- Centralise one `isSuperAdmin(role)` helper on the client, mirroring `is_super_admin`/`_normalize_role`, and replace all five hand-rolled checks.
- Add role-fixture tests for gating. Never rely on super-admin sessions to validate nav behaviour. Consider a super-admin "preview as role" later, but do not build it in this milestone.
- Note that the X-Tenant-ID override is logged but is a cross-tenant read path. Cost views are financial data, so keep the audit log entry.

**Warning signs:**
- A cost total larger than the tenant's asset count could explain, when viewed as super-admin.
- A super-admin screen with no tenant picker whose numbers change when tenants are added.
- Different role strings behaving differently in Sidebar vs router.

**Phase to address:** P78 and P79 (cost scoping), P76 (client helper).

---

### Pitfall 5: Stale permissions after a role change

**What goes wrong:**
An admin removes a role's permission or re-roles a user. The sidebar and in-flight session still reflect the old state, or the backend enforces the old role.

**Why it happens / evidence:**
- Backend `role` comes from the JWT claim (`verify_token`: `payload.get("role")`), valid up to `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60, max 120). Re-roling a user does call `revoke_user_sessions` (`user_endpoints.py` line about 402), so that case is mostly covered and forces a fresh login. Grep shows `revoke_user_sessions` is called from `user_endpoints.py` and `tenant_endpoints.py` only. I found no caller in a role-permission-edit path. Editing what a role can do does not invalidate the sessions of users holding it.
- The role document is re-read per request in `verify_permission`, so the backend picks up a role-permission edit immediately. The client list does not: it is fetched at login and held in React state until reload. A revoked permission stays visible (benign: the click gets 403). A newly granted permission stays hidden until re-login (annoying, and "I granted it but it's not there" support tickets).
- `@cached` (`cache_service.py`) keys on function name plus stringified kwargs. It currently varies by user (the `TokenData` dataclass repr is in the kwargs), but a cost endpoint that is `@cached` and derives the tenant from the ContextVar rather than a kwarg would share one cache entry across tenants (see Pitfall 8).

**How to avoid:**
- The client must tolerate drift. On a 403 from any `/api` call, refetch `/api/auth/me` and recompute the nav. Also refetch on window focus and on a modest interval, or push a WebSocket "permissions changed" event (the repo already has socket infrastructure).
- Have role-permission edits call `revoke_user_sessions` for affected users, or at least emit the refresh event.
- Never cache a permission-gated response without keying on tenant and role/permission set. Prefer not caching cost endpoints at all, or cache with an explicit `tenant_id` and permission key.
- Treat the server as the only authority. Stale UI only ever costs convenience if Pitfall 1 is closed.

**Warning signs:**
- A grant made in settings does not appear without logout/login.
- A cost response still returned after the role lost `view:itam`.

**Phase to address:** P76 (refresh and 403 handling), P75 (revocation on role edit).

---

### Pitfall 6: Empty-sidebar lockout and silent navigation failure

**What goes wrong:**
A role holds no, or few, matching permissions. The user lands on a blank or broken page with no explanation and no way to proceed.

**Why it happens / evidence:**
- `visibleGroups` drops empty groups, so a role with zero matches yields an empty `<nav>`. Roles that already trip this: custom tenant roles that lack `view:dashboard`, and the ITAM roles. `itam_viewer` holds only `view:assets`, `view:licenses`, `view:itam`. It has no `view:dashboard` and no `view:profile`, so the default landing view and the Profile page are both unreachable.
- `handleSetCurrentView` on a denied view only does `console.warn`; the user sees nothing happen. App initialisation and logout call `setCurrentView('dashboard')` (lines about 807 and 1365) regardless of whether the user may view it.
- The hash router (`hashchange` handler around line 645) routes deep links through the same guard, so a bookmarked forbidden view is silently ignored and leaves the previous view showing.

**How to avoid:**
- Landing view = the first nav item the user can see, not a hard-coded `'dashboard'`.
- Always render a minimal footer: Profile (or a guaranteed-safe item), Sign out, and a "No catalogues are assigned to your role. Contact your administrator" empty state. Never an empty void.
- A denied navigation shows a visible "You don't have access to X" notice (toast or inline), and the URL hash is reset.
- Add a test: for every built-in role, `visibleGroups` is non-empty and the landing view is permitted.

**Warning signs:**
- A blank `<nav>` for any seeded role.
- A "dashboard" render for a user whose role cannot view the dashboard.

**Phase to address:** P76.

---

### Pitfall 7: The cost data sources the milestone assumes do not exist (licenses and consumables have no cost field)

**What goes wrong:**
The plan says to "roll up license spend and allocated license cost from existing data". There is no cost data to roll up. A rollup built anyway returns zero or fabricated numbers, or someone invents a hidden cost-entry system, contradicting "no new cost-entry system".

**Why it happens / evidence:**
- `itam_models.License` has `seatCount`, `expiryDate`, `isReassignable`, `productKey`, `manufacturerId`. There is no cost, price, billing cycle or currency. `Consumable` has `initialQuantity`, `unitType`, `reorderThreshold`, and no unit cost. `Component` is the same. `grep -iE "cost|price|spend"` over `itam_license_endpoints.py`, `itam_consumable_endpoints.py`, `itam_component_endpoints.py` and `LicensesPanel.tsx` returns nothing.
- Money that does exist: `Asset.purchaseCostCents` (int), model-level `usefulLifeYears` and `salvageValueCents`, `PurchaseOrder.total_cost` and `PurchaseOrderItem.unit_price` as **floats**, and `AssetRequest.estimated_cost` as a float. Purchase orders carry free-text `items[].name`, with no link to a license or consumable.
- The Phase 71 summary line "purchase/PO/supplier" lives on the asset, not the license.

**How to avoid:**
- Resolve this at requirements time, before P77. Options, in order of preference:
  1. Add a minimal, optional, integer-cents `costCents` (plus an explicit billing basis: one-time or per-year) to `License`, and `unitCostCents` to `Consumable`. This is a field extension on existing entities, not a new cost-entry system.
  2. Defer license and consumable cost and ship asset purchase/book-value rollups only, labelling the license line "not tracked".
  3. Derive from POs only if a real PO-to-license link is added (it does not exist today).
- Whatever is chosen, the UI must show **coverage** ("12 of 40 licenses priced") next to every total, so zero is never confused with unpriced.
- Do not let the v4.2 rollups silently treat `None` as 0 (see Pitfall 10).

**Warning signs:**
- The requirement "license spend" has no field in the schema.
- A rollup test that uses fixtures with a cost field production data does not have.

**Phase to address:** Requirements/P77 (decision), P77 (schema change if option 1).

---

### Pitfall 8: Multi-tenant cost leakage through aggregation, caching and raw handles

**What goes wrong:**
One tenant sees another tenant's totals, or a super-admin sees a blended total.

**Why it happens / evidence:**
- The wrapper helps: `TenantIsolatedCollection.aggregate` prepends `{"$match": {"tenantId": ...}}`. That protects **only the first stage**. A `$lookup` into another collection from inside a pipeline reads the foreign collection through the raw Motor driver and is **not** tenant-filtered. An asset to `asset_models`, `suppliers`, `purchase_orders`, `license_assignments` join done with `$lookup` can pull rows from other tenants. Existing KPIs avoid this by doing batched `find` calls per collection through the isolated handle (`itam_reporting_kpis._compute_asset_value_kpi` uses `db.asset_models.find({"id": {"$in": model_ids}})`). Follow that pattern or add an explicit `tenantId` match inside every `$lookup` sub-pipeline.
- Model IDs, supplier IDs and PO IDs are looked up by `id`. Always scope by tenant, and never trust an ID supplied by the client without tenant-scoped resolution (the Phase 71 review found exactly this, T-71-04: `purchase_order_id` accepted without ownership check).
- `@cached(ttl=60, key_prefix="assets")` keys on `func.__name__` and non-`request`/`db` kwargs. A cost endpoint where the tenant comes from the ContextVar (not a kwarg) would collide across tenants. Do not apply `@cached` to cost endpoints, or key on tenant explicitly.
- Background jobs run without a tenant ContextVar. The wrapper then fails closed with `NON_EXISTENT_TENANT_ISOLATION_EMERGENCY`, so a nightly cost-snapshot job silently computes nothing. The "fix" of using the raw handle (as the warranty sweep does) removes isolation. The v4.0 research and `compliance_remediation_sla_service.py` document the correct loop-per-tenant pattern with `set_tenant_id`/`reset_tenant_id` in `try/finally`. If P78/P79 add snapshots or trend history, reuse that pattern. Prefer compute-at-read (as depreciation already does, per D-04) so there is no job to get wrong.
- Collections exempted from isolation (`TENANT_ISOLATION_EXEMPT_COLLECTIONS`: `tenants`, `system_features`, etc.) are shared. Do not read tenant currency or settings from a place that returns another tenant's row.

**How to avoid:**
- All cost reads go through the tenant-isolated handle plus an explicit `tenantId` in the query. No `$lookup`. No raw `db._db`.
- A mandatory two-tenant fixture test for every cost route: seed tenants A and B with distinct costs, assert A's response contains only A's numbers, assert a super-admin without a tenant is rejected or returns a labelled breakdown (see Pitfall 4).
- The existing Phase 72 decision "every report/KPI reuses its owning surface's computation function verbatim" is the right precedent. Org-level cost must call `compute_book_value` and share the asset-selection logic with the KPI. Do not re-derive depreciation in a third place.

**Warning signs:**
- `$lookup` in a cost pipeline.
- `@cached` on a route that reads the ContextVar tenant.
- A totals mismatch between the new cost view and the existing "asset value" KPI tile for the same tenant (trust-breaking bug class per Phase 72).

**Phase to address:** P77 (service design), P78 (org route), P79 (endpoint route). The two-tenant test is a P78 exit criterion.

---

### Pitfall 9: Depreciation / book-value math errors and policy-source confusion

**What goes wrong:**
The cost view shows book values that disagree with the existing per-asset and KPI figures, or that are subtly wrong.

**Why it happens / evidence:**
- `compute_book_value` is **whole-year step depreciation**: `years_elapsed` increments only on the anniversary, so book value is flat for 12 months then drops. An asset bought 11 months ago shows full purchase cost. A "straight-line" expectation of monthly decline will be violated. Annual depreciation is `(cost - salvage) // useful_life` using **integer division**, so up to `useful_life - 1` cents per asset are never depreciated, and book value at end of life is `cost - years*floor(...)`, which is not exactly salvage (it is floored up to `max(.., salvage)`, so it can sit slightly above salvage then clamp). Rolled up over thousands of assets, rounding drift exists. Document it as the platform's definition (Phase 59 D-04) and test against it; do not "improve" it in the rollup only.
- **Two competing policy sources.** The endpoint and the KPI use the asset-model's `usefulLifeYears`/`salvageValueCents`. The `Asset` and `ManualAssetCreate` models also carry **asset-level** `useful_life_years` and `salvage_value` (a **float**, dollars not cents) that `get_asset_book_value` ignores. A rollup that reads the asset-level fields would disagree with the live panel. Use the model-level policy exactly as `get_asset_book_value` does, or deliberately define an override order and apply it in `compute_book_value`'s caller everywhere.
- Non-depreciating states: disposed/retired/lost assets. The existing KPI counts every asset including those; decide whether disposed assets contribute purchase cost, book value (should be 0 or excluded) or neither, and apply it uniformly in both KPI and cost view.
- Date edge cases: `purchaseDate` strings that are naive vs tz-aware, a purchase date in the future (negative years clamps to 0, so book value = full cost; arguably should flag), `now` captured per-asset vs once per request (use one `now` for the whole rollup for stable totals).
- Cents vs dollars: PO and request fields are float dollars, assets are int cents. Mixing them in one sum without conversion is an off-by-100 bug, and float sums accumulate error.

**How to avoid:**
- Org and endpoint cost call `compute_book_value` only. Add a golden-value test table (cost, salvage, life, purchase date, `now`, expected cents) that both the KPI and the cost rollup must satisfy, including life=1, salvage>=cost, cost=0, leap-day purchase, anniversary-day boundary, and future date.
- Do integer-cents arithmetic end to end. Convert PO floats once at the boundary with `Decimal`/rounding rules, only if POs are used at all.
- Surface the whole-year behavior in the UI copy ("depreciates annually on purchase anniversary") so users do not file a bug.
- Define disposed-asset treatment in requirements.

**Warning signs:**
- Org total differs from the dashboard "Total book value" tile by any amount.
- Sums differing by a few cents with life > 1.
- Any `* 100` or `/ 100` in new cost code.

**Phase to address:** P77.

---

### Pitfall 10: Null / unpriced / unmapped assets silently treated as zero, hiding coverage gaps

**What goes wrong:**
The cost view looks authoritative but reports a small number because most assets have no cost, no purchase date, or no depreciation policy. Agent-discovered assets (the bulk of the inventory) have none of these.

**Why it happens / evidence:**
- Assets are discovered by agents via heartbeat upsert (`agent_heartbeat_endpoints.py` upserts into `db.assets` by `id` with `$setOnInsert type: "server"`) or created manually (`itam_asset_endpoints.create_manual_asset`) in the **same** `assets` collection. Agent-discovered rows have no `purchaseCostCents`, `purchaseDate`, `modelId`, `assetTag` or `lifecycleStatus` (read-time default). `get_asset_book_value` returns `bookValueCents: None` with `reason` (`no_purchase_record` / `no_depreciation_policy_assigned`). The KPI counts these in `withoutPolicyCount` but its total silently excludes them.
- Mongo `None` vs missing vs `0`: `purchaseCostCents: 0` is a legitimate value (donated or internally built), and distinct from null.
- A single asset can exist as two records (agent-discovered and manually entered ITAM record for the same physical device) because nothing reconciles `hostname`/`serialNumber`. That is both a double-count (Pitfall 12) and a missing-cost problem.

**How to avoid:**
- Every response includes `pricedCount`, `unpricedCount`, `noPolicyCount`, `totalAssets`, and a per-reason breakdown, and the UI renders "Totals cover X of Y assets" prominently with a drill-down to the unpriced list (reuse the `asset_value` report/drill-down key pattern).
- Keep `None` distinct from `0` throughout. A tenant with no priced assets returns `total: null` / `hasData: false` (the KPI's convention), not `0`.
- Decide and document the endpoint mapping rule: how an agent endpoint is tied to an ITAM costed record (asset id, serial, or hostname), and where no mapping exists, show the row as "unmapped". Do not guess a match by hostname alone across the fleet without a uniqueness check.

**Warning signs:**
- Org total of `0` or `$0.00` on a tenant with 500 assets.
- An asset count in the cost view that differs from the Assets page.
- Endpoint cost view empty for agent-only tenants.

**Phase to address:** P77 (schema of response, reason codes), P79 (endpoint mapping).

---

### Pitfall 11: Currency is implicit, so cross-tenant and cross-asset sums are meaningless

**What goes wrong:**
Costs are presented with a `$` sign that is not true for the tenant, or sums mix currencies (especially for a super-admin cross-tenant view, or tenants whose POs are in different currencies).

**Why it happens / evidence:**
- `purchaseCostCents` has no currency. Nothing in `itam_models.py` carries one. Currency appears only in `finops_service.py`, `payment_*` and a couple of report helpers (cloud billing), unrelated to ITAM. The existing KPI returns bare `totalBookValueCents`.

**How to avoid:**
- Explicitly scope v4.2 to a **single reporting currency per tenant**, stored as a tenant setting (a display label only, no conversion), and say so in the UI. Do not build FX conversion (out of scope, and the milestone has no new cost-entry system).
- Never sum across tenants (see Pitfall 4). If a super-admin overview is wanted, show per-tenant rows with their own currency label and no grand total.
- Format with `Intl.NumberFormat` from integer cents on the client; never `float` on the server.

**Warning signs:**
- Hard-coded `$` in cost components.
- A grand-total row in a super-admin view.

**Phase to address:** P77 (decision), P78 (display).

---

### Pitfall 12: Double-counting shared and licensed assets, and unassigned seat cost

**What goes wrong:**
License cost counted once per assignment target rather than once per license, assets counted in both a parent and its components, or a seat attributed to both a user and the user's endpoint.

**Why it happens / evidence:**
- `license_assignments` rows target either a `user` or an `asset` (`targetType`). Allocating license cost to endpoints naively as `licenseCost / seats` per assignment gives the right per-seat price but breaks in three ways:
  1. **Unassigned seats.** `seatsAvailable = seatCount - assigned`. Cost for unassigned seats (shelfware) must not vanish from the org total, and must not be dumped onto any endpoint. The org total uses the full license cost; the endpoint allocation sums to `perSeat * assignedSeats`; the difference is shown as "unallocated".
  2. **User-assigned seats.** A seat assigned to a user is not tied to an endpoint. Mapping it to the user's checked-out assets (`assignment_history`) risks counting one seat on several devices. Define a single rule (e.g. user-assigned seats are reported under the user and not allocated to endpoints, or allocated only when exactly one asset is checked out to them).
  3. **Expired or reclaimed licenses.** `expiryDate` in the past: is its cost current spend? `reclaim_license_seat` deletes the assignment and writes history, so history is not a reliable count of seats.
- Assets can have `parentAssetId` and `components` (attached component IDs). If component cost is ever added to the parent's cost while the component also appears as its own row, the sum doubles.
- A seat-count race exists and the code compensates (insert, then count, then delete if over). During the window the count can transiently exceed `seatCount`. Compute `assigned` as `min(count, seatCount)` for cost purposes, or read at a consistent point.
- The agent-plus-manual duplicate (Pitfall 10) double counts purchase cost.

**How to avoid:**
- Org license spend is computed per **license** (cost is an attribute of the license), never by summing over assignments.
- Endpoint allocation is a derived, labelled field ("allocated license cost") and the invariant `sum(endpoint allocations) + unallocated == org license spend` is a test.
- Exclude component rows from parent totals or exclude them from the top-level list, never both.
- Decide a dedupe key for agent vs manual assets (serial number first) and report potential duplicates instead of auto-merging.

**Warning signs:**
- Endpoint allocations exceed the org total.
- Total changes when seats are reassigned but the license did not change.
- Same serial number on two rows.

**Phase to address:** P77 (invariants), P79 (allocation).

---

### Pitfall 13: Rollup performance, including unbounded reads and per-asset loops

**What goes wrong:**
The org cost page times out or hammers Mongo for tenants with many assets, and is slower for every request because nothing is precomputed.

**Why it happens / evidence:**
- `compute_itam_kpis` does `db.assets.find({}, projection).to_list(length=None)` (unbounded) and loops in Python. That is fine at hundreds of assets, and the tenant sizes at which it stops being fine are unmeasured (assume trouble around tens of thousands, MEDIUM confidence). `list_license_assignments` caps at `to_list(length=1000)`, so a license with more than 1000 assignments is silently truncated; a cost allocation built on it would undercount.
- A per-endpoint cost list that calls `get_asset_book_value` (which does a `find_one` on `asset_models` per call) in a loop is N+1. The KPI already shows the batched pattern: collect `modelId`s, one `$in` query.
- Depreciation is deliberately computed at read time and never stored (D-04). That is correct for correctness but means every request recomputes.
- The existing indexes: `assets` has `tenantId`, `id` (unique), `(tenantId, assetTag)` unique, `(tenantId, lastAuditedAt)`. There is none on `(tenantId, modelId)` or `(tenantId, lifecycleStatus)` for filtered cost slices, and none for `license_assignments` by `(tenantId, targetType, targetId)`. Verify the index set in `database.py` and `migrations/` before relying on it.

**How to avoid:**
- Reuse the batched pattern: one assets read with a narrow projection (cost, date, modelId, lifecycleStatus, id), one `asset_models` `$in`, one `license_assignments` read. No per-asset queries.
- Paginate and cap the **detail** list (endpoint-level rows) server-side, as `get_assets` does with `PaginationParams`; compute the **summary** over the full set separately. Never paginate a total.
- Do not use a hard `to_list(length=1000)` for anything that feeds a sum. Use a count or `$group` aggregation.
- If measured to be slow, an in-process, tenant+permission-keyed short TTL cache is acceptable. A stored snapshot is a last resort and brings the background-job tenant pitfall back (Pitfall 8).
- Add a seeded large-tenant timing test (for example 20k assets) as an exit criterion for P78 so the claim is measured, not assumed.

**Warning signs:**
- Request time that scales linearly with assets.
- Mongo logs with many identical `asset_models` `find_one`.
- Totals that change when a list is paginated.

**Phase to address:** P77 (batched design), P78/P79 (measure).

---

## Moderate Pitfalls

### Pitfall 14: Cost data exposed to users who can only see the catalogue

**What goes wrong:** The cost screen or cost fields are gated only by "can see ITAM / assets", so ordinary users or viewers see purchase prices.
**Why:** `user` and `viewer` default roles hold `view:assets`; `itam_viewer` holds `view:itam`. `_require_itam_viewer` accepts `view:itam` or `manage:assets`. Cost is more sensitive than inventory.
**Prevention:** Decide the cost permission explicitly. The milestone forbids a new permission model, so reuse an existing string: `view:finops` (granted to `admin`, `user`, `viewer` today, so too broad) or `manage:finance` (held by `itam_admin`) are the candidates, or `view:itam` for org-level only. Record the choice in the manifest. Strip cost fields from `GET /api/assets*` for callers without it (Pitfall 1).
**Phase:** P75 (decision), P78/P79.

### Pitfall 15: Duplicated `_require_itam_admin`/`_require_itam_viewer` guards drift

**What goes wrong:** The cost router copies a guard, and a later change updates one copy.
**Why:** `itam_catalog_endpoints.py` already keeps an independent duplicate (flagged T-73-04 and in `deferred-items.md`).
**Prevention:** Import the canonical guard. The cost router must use the dual session/API-key dependency and the scope-narrowing check (`_scopes_allow`), so a scoped API token cannot read cost data its scopes exclude. Add a scope-narrowing test.
**Phase:** P78.

### Pitfall 16: Hidden catalogue entries still reachable through other UI surfaces

**What goes wrong:** Global search, the command palette (`handleExecuteCommand` `navigateToView`), notifications, "recent" links, breadcrumbs and dashboard tiles still link to forbidden views.
**Prevention:** Funnel all navigation through the one guarded function (Pitfall 3). Filter search results and dashboard tiles by the same manifest.
**Phase:** P76.

### Pitfall 17: Tier/feature locking conflated with permission gating

**What goes wrong:** `minTier`/`featureKey` produce a visible-but-locked item ("Requires Pro plan"); permission gating produces a hidden item. Treating "locked" as "authorized" or vice versa shows upgrade prompts to roles that could never use the feature.
**Prevention:** Evaluate permission first (hide), then tier (lock). Keep the two in separate, tested code paths, as `visibleGroups` does today. Do not add cost to the tier system.
**Phase:** P76.

### Pitfall 18: Rollups drift from existing KPI and report numbers

**What goes wrong:** A third computation of "total book value" returns a different number from `itam_reporting_kpis` and the `asset_value` pre-built report.
**Prevention:** Extract the asset-selection plus `compute_book_value` loop into one shared function and have KPI, pre-built report and cost view call it. Add a parity test across all three.
**Phase:** P77.

### Pitfall 19: Date and timezone handling in cost-as-of

**What goes wrong:** "As of" dates use server-local `now`, so anniversary boundaries differ by timezone, and a tenant sees a drop a day early or late.
**Prevention:** Use UTC consistently as `compute_book_value` does; expose `computedAt` (already in the book-value response). Do not add per-tenant timezone logic.
**Phase:** P77.

## Minor Pitfalls

### Pitfall 20: Accordion height with filtered items
**What goes wrong:** `SidebarGroup` sizes `maxHeight` from `group.items.length * 44 + 8`, which already uses the filtered list. A future change that computes it from the unfiltered list clips items.
**Prevention:** Keep computing from the filtered items; add a small render test.

### Pitfall 21: Localization and number formatting
**What goes wrong:** `itamI18n.tsx` exists for ITAM panels; new cost strings and number formats added outside it.
**Prevention:** Add cost strings to the same i18n module and format via `Intl`.

### Pitfall 22: CSV/PDF export of cost data
**What goes wrong:** Exports bypass the new permission or leak formulas (CSV injection).
**Prevention:** Reuse the formula-safe export path from Phase 70/72 and apply the same cost permission.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Gate nav on `Sidebar.tsx` only, "backend later" | Ships the visible feature fast | Security by obscurity; every unguarded route stays open | Never |
| Add the missing `view:` strings to `user`/`viewer` to make menus appear | Menus show immediately | Silent over-grant of whole catalogues | Never (decide per role in the manifest) |
| Keep two default permission tables | No refactor | Drift continues (29 + 17 mismatches today) | Only if a test fails on any mismatch |
| Re-derive book value in the cost service | Avoids touching shared code | A third, divergent number | Never |
| Treat `None` cost as 0 | Simple sums | Misleading totals, hidden coverage gaps | Never |
| Cache cost responses with `@cached` | Fast page | Cross-tenant/cross-role leak risk | Only with tenant and permission in the key |
| Precomputed nightly cost snapshot | Fast reads | Background-job tenant-context bug class returns | Only after compute-at-read is measured too slow |
| Add a cost float field to License | Quick schema | Float money drift | Never; use integer cents |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `TenantIsolatedCollection.aggregate` | Assuming `$lookup` targets are tenant-filtered | Only stage 0 is injected. Use batched `find` per collection, or add `tenantId` inside every lookup |
| `platform-admin` token | Running cost query with no tenant | Require an explicit tenant or return a per-tenant breakdown, never a blended sum |
| `rbac_utils.verify_permission` vs `rbac_service.has_permission` | Mixing them in one router | Pick one per router, from the manifest. Reconcile their default tables |
| `/api/auth/me` `permissions` | Treating it as the effective permission set | It is the role document's list only. Return effective permissions (defaults + doc) |
| `get_current_user_or_api_key` | Cost route accepting API keys without scope check | Apply `_scopes_allow` for the cost permission |
| Agent heartbeat upsert into `assets` | Assuming discovered assets carry cost/model/policy | They carry none. Surface as unpriced |
| `license_assignments` | Counting assignments as cost or capping reads at 1000 | Cost per license. Counts via `count_documents` or `$group` |
| `@cached` decorator | Using it on tenant-from-ContextVar handlers | Avoid, or key on tenant and permission |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded `to_list(length=None)` over assets | Slow page, high memory | Narrow projection, `$group` where possible, paginate detail rows | Likely in the tens of thousands of assets per tenant (unmeasured) |
| N+1 `asset_models` lookup per asset | Chatty Mongo log | One `$in` batch, as the KPI does | Hundreds of assets |
| `to_list(length=1000)` assignments | Silent undercount | `count_documents` | A license with more than 1000 seats |
| Recompute on every request | Linear latency | Short TTL cache keyed by tenant and permission | High refresh rates on a large tenant |
| Missing compound index for filtered slices | Collection scans | Verify or add `(tenantId, modelId)`, `(tenantId, lifecycleStatus)` | Large collections |
| Permission check hitting DB on every route | Added latency | Defaults are checked first, the DB role lookup only on miss. Keep this order | Many gated calls per page load |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| UI-only gating | Unauthorized read of any ungated catalogue (HIGH) | P75 router-level guards plus contract test |
| `GET /api/assets*` returning cost fields to everyone authenticated | Purchase prices leak to all tenant users (HIGH) | Field-gate or permission-gate before shipping costing |
| Super-admin cross-tenant cost aggregate | Blended/leaked totals (HIGH) | Explicit tenant required |
| Sidebar `hasPermission` fail-open fallback | Full menu when context is missing (MEDIUM) | Default to deny |
| `setCurrentView` bypass paths | Forbidden views render (MEDIUM, UI-only) | Guard `renderView`, single navigation function |
| Role permission edits not revoking sessions | Stale access until JWT expiry (MEDIUM) | Revoke or refresh on role edits |
| Cost route ignoring API-key scope | Scoped token reads cost (MEDIUM) | `_scopes_allow` |
| Tenant ID taken from the request instead of the token | Cross-tenant read (HIGH) | Context-var tenant only, as the wrapper enforces |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent denied navigation | "Click does nothing" | Visible notice and hash reset |
| Blank sidebar for a role | Locked out with no explanation | Empty state plus profile/sign-out |
| Cost total with no coverage | False confidence | "X of Y priced" with drill-down |
| Zero vs unknown | Misread spend | `—` for unknown, `0` only when true |
| `$` assumed | Wrong currency | Tenant currency label |
| Flat book value for 11 months | "It's not depreciating" | Copy explaining annual steps |
| New grants only appear after relogin | Support tickets | Refresh on focus/403 |

## "Looks Done But Isn't" Checklist

- [ ] **Catalogue gating:** every nav item's backend routes return 403 for a role lacking the permission. Verify with a per-route sweep, not a sample.
- [ ] **Catalogue gating:** `GET /api/assets` and `/api/assets/{id}` no longer return cost fields to roles without the cost permission.
- [ ] **Permission strings:** every sidebar permission exists in the effective default role tables and in `viewPermissionMap` with the same value.
- [ ] **Fail-closed:** Sidebar with a null user context renders no catalogue items.
- [ ] **Navigation:** all `setCurrentView` call sites go through the guarded handler; `renderView` rejects forbidden views.
- [ ] **Empty role:** each built-in role has at least one visible item and a permitted landing view.
- [ ] **Super-admin:** gating verified with real role fixtures, not only as super-admin; `platform-admin` string handled identically on client and server.
- [ ] **Role change:** a role-permission edit is reflected in the sidebar without logout, or the sessions are revoked.
- [ ] **Tenant isolation:** two-tenant fixture test on every cost route, including super-admin with no tenant.
- [ ] **Parity:** org total equals the Phase 72 KPI tile and the `asset_value` report for the same tenant.
- [ ] **Coverage:** every total shows priced/unpriced/no-policy counts; null is not zero.
- [ ] **License cost source:** the schema actually has a license cost field (or the requirement was explicitly descoped).
- [ ] **Allocation invariant:** endpoint allocations plus unallocated equal org license spend.
- [ ] **Math:** golden-value tests for whole-year depreciation, rounding, life=1, future date, disposed assets.
- [ ] **Scale:** timing test on a seeded large tenant; no `$lookup`, no N+1.
- [ ] **API key scope:** a narrowly scoped token cannot read cost.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| UI-only gating shipped | HIGH | Treat as an incident. Run the route sweep, add router-level guards, rotate nothing but audit access logs for the exposed prefixes |
| Cost fields leaked via `/api/assets` | MEDIUM | Gate or strip fields, review access logs, notify per policy |
| Cross-tenant total shown | HIGH | Disable the route, fix scoping, add the two-tenant test, assess disclosure |
| Role over-granted to make menus show | MEDIUM | Revert the role defaults, migrate custom role docs, revoke sessions |
| Divergent book-value numbers | LOW | Point the cost view at the shared function, add the parity test |
| Totals silently exclude unpriced | LOW | Add coverage fields and UI copy |
| License cost field missing | MEDIUM | Add optional integer-cents field, backfill by tenant admins, show coverage meanwhile |
| Stale client permissions | LOW | Add `/me` refetch on 403 and focus |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. UI-only gating (top) | P75 (enforce), P76 (consume) | Per-route 403 sweep over the manifest; no new `/api` route without a permission dependency |
| 2. Divergent tables, ungranted strings | P75 | Test: every manifest permission is granted by at least one built-in role; the two tables agree |
| 3. Client trust, fail-open | P76 | Null-context renders nothing; `renderView` guard test |
| 4. Super-admin / cross-tenant | P76, P78, P79 | Role-fixture gating tests; super-admin without tenant gets 400/breakdown |
| 5. Stale permissions | P75, P76 | Edit a role, assert refresh or session revoke |
| 6. Empty-sidebar lockout | P76 | Each built-in role has a visible item and landing view |
| 7. Missing license/consumable cost source | Requirements, P77 | Schema has the field, or the descoped requirement is recorded |
| 8. Tenant leakage in aggregation/cache | P77, P78, P79 | Two-tenant test on every cost route; no `$lookup`/`@cached` |
| 9. Depreciation math | P77 | Golden-value table; KPI/report/cost parity |
| 10. Null / unmapped | P77, P79 | Coverage counts in every response |
| 11. Currency | P77, P78 | Tenant currency label; no cross-tenant sum |
| 12. Double counting | P77, P79 | Allocation invariant test; duplicate-serial report |
| 13. Performance | P77, P78, P79 | Large-tenant timing test; no N+1 |
| 14. Cost permission too broad | P75, P78 | Viewer/user role gets 403 on cost routes |
| 15. Guard duplication / API-key scope | P78 | Scoped-token test |
| 16. Other UI surfaces | P76 | Search, palette and notifications respect the manifest |
| 17. Tier vs permission | P76 | Separate tests |
| 18. KPI drift | P77 | Shared function, parity test |
| 19. Timezone | P77 | UTC golden tests |

## Sources

- Primary-source reads of this repository (HIGH): `backend/rbac_utils.py`, `backend/rbac_service.py`, `backend/tenant_middleware.py`, `backend/database.py`, `backend/authentication_service.py`, `backend/authentication_endpoints.py`, `backend/user_endpoints.py`, `backend/asset_endpoints.py`, `backend/itam_finance_service.py`, `backend/itam_finance_endpoints.py`, `backend/itam_license_service.py`, `backend/itam_license_endpoints.py`, `backend/itam_reporting_kpis.py`, `backend/itam_reporting_prebuilt.py`, `backend/itam_models.py`, `backend/itam_catalog_endpoints.py`, `backend/agent_heartbeat_endpoints.py`, `backend/cache_service.py`, `components/Sidebar.tsx`, `contexts/UserContext.tsx`, `App.tsx`.
- Project history (HIGH): `.planning/PROJECT.md` (Phases 59, 60, 62, 63, 69-73 notes, including the Phase 63 audit BLOCKERs, T-71-04, T-73-04 and the Phase 72 "reuse the owning surface's computation" decision); the prior v4.0 PITFALLS.md (background-scheduler tenant isolation).
- Scripted analysis (HIGH, reproducible): diff of Sidebar permissions against `rbac_service.default_roles`/`rbac_utils.DEFAULT_PERMISSIONS`; diff of Sidebar permissions against `viewPermissionMap`; endpoint-file scan for authentication-only routers.
- General cost-accounting and performance guidance (MEDIUM): scale thresholds are estimates, not measurements, and should be validated in P78.

---
*Pitfalls research for: v4.2 Catalogue Access Control & Asset Costing*
*Researched: 2026-10-12*
