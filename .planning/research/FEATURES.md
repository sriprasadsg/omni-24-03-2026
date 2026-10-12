# Feature Research — v4.2 Catalogue Access Control & Asset Costing

**Domain:** Permission-gated navigation in a multi-tenant SaaS console (Feature 1) and ITAM asset cost rollup / TCO-lite (Feature 2), added to an existing FastAPI + React/TS + MongoDB platform
**Researched:** 2026-10-12
**Confidence:** MEDIUM overall. Codebase findings are HIGH (read directly from source). Product-behavior conventions (Snipe-IT / ServiceNow / Lansweeper style costing, nav-gating patterns) are MEDIUM: web search returned only generic secondary sources, so conventions are stated from domain knowledge and marked as such.
**Supersedes:** the 2026-08-04 FEATURES.md (v4.0 ITAM lifecycle research); that milestone is shipped.

---

## Existing System Baseline (grounding — read from code, do not re-build)

### Feature 1 baseline (RBAC / nav)

| Fact | Where | Implication |
|------|-------|-------------|
| Sidebar already filters by permission: `navGroups` items carry `permission: 'view:...'`; `visibleGroups` drops items where `hasPermission()` is false and drops empty groups; super-admin bypasses; `manage:tenants` hidden when super-admin is viewing a tenant | `components/Sidebar.tsx` L208-466 | The "hide menu items" behavior largely EXISTS. v4.2 is about making it authoritative, consistent with the backend, and visible to admins, not building it from scratch. |
| ~187 nav items, **89 distinct permission strings** | `Sidebar.tsx` | Large surface; need a registry + automated check, not hand audits. |
| **Second hand-maintained map** `viewPermissionMap: Record<AppView, Permission>` used by `handleSetCurrentView` (click and hash-deep-link guard) | `App.tsx` L242-446, L1379-1395 | Two sources of truth. **9 views disagree** with the sidebar permission today: `agentCapabilities`, `jobs`, `llmops`, `persistenceDetection`, `sustainability`, `swarm`, `unifiedOps`, `vulnerabilityManagement`, `zeroTrustQuantum`. Item can render in the nav yet the click is silently refused (or vice versa). |
| Blocked navigation is silent: `console.warn` only, no user-visible state | `App.tsx` L1392 | No fallback/empty state exists. |
| `hasPermission` fails OPEN if `UserContext` is absent: `userContext?.hasPermission \|\| (() => true)` | `Sidebar.tsx` L178 | Must become fail-closed. |
| `currentView` initial state is `'dashboard'`; `renderView()` switches on `currentView` with no permission check at render time | `App.tsx` L481, L1806 | Guard exists only at the navigation entry points, not at render. Any direct `setCurrentView` caller bypasses it. |
| Frontend effective permissions = login-time `user.permissions` (from the `db.roles` doc via `find_role_doc`) ∩ tenant `enabledFeatures`; if the list is empty it falls back to the `/api/roles` **static stub** (`Admin -> ["all"]`) | `App.tsx` L1185-1242, `authentication_endpoints.py` L223-231, `role_endpoints.py` | Frontend evaluator is NOT the backend evaluator. Backend `verify_permission` = hardcoded `DEFAULT_PERMISSIONS` dict first, then `db.roles` doc. A role with defaults but no role doc logs in with `permissions: []`. UI and API can disagree. |
| Backend evaluator: `rbac_utils.verify_permission` / `require_permission`; ITAM uses `_require_itam_viewer` (`view:itam` OR `manage:assets`, plus API-key scope narrowing) and `_require_itam_admin` (`manage:assets`) | `rbac_utils.py`, `itam_asset_endpoints.py` L38-95 | The "mirror backend authorization" target. Reuse, do not fork. |
| Backend `require_permission('view:...')` coverage is thin: of 89 nav permission strings, most `require_permission` call sites use `manage:*`/`investigate:*`; a spot grep found few `view:` guards (e.g. `view:security`, `view:reporting`, `view:dashboard`, `view:compliance`, `view:devsecops`) | `grep require_permission backend/*.py` | Many catalogues are UI-gated only. "Mirrors backend" cannot be asserted without a parity audit. (Grep covers only the literal `require_permission("x")` form; other guard styles may exist. Treat as a lead, verify in phase research.) |
| 3 nav permissions are granted by no seeded default role: `view:goal_system`, `view:jobs`, `view:predictive_health` | grep of `app_startup.py`, `rbac_utils.py`, `authentication_endpoints.py`, `rbac_service.py` | Those catalogues are visible to super-admin only unless a custom role doc grants them. |
| Three orthogonal gates already stack on a nav item: role permission, tenant `enabledFeatures`/bundle (`featureKey`), subscription tier (`minTier` -> shown **locked**) | `Sidebar.tsx` L449-463 | Keep distinct: permission-denied = hidden; tier-locked = shown with lock. Do not merge. |
| "Phase 36 ReBAC" is an OpenFGA wrapper (`rebac_service.py`) that the sidebar does NOT consult. Nav gating is flat role-permission. | `rebac_service.py` | The milestone phrase "ReBAC permissions" means the flat `view:` permissions on roles, not OpenFGA tuples. Requirements should say "role permissions (`rbac_utils`/`db.roles`)". |

### Feature 2 baseline (ITAM cost data)

| Fact | Where | Implication |
|------|-------|-------------|
| Asset purchase cost: `purchaseCostCents` (int, `>=0`), `purchaseDate` (ISO), `poNumber`, `purchase_order_id`, `warrantyMonths`, `lifecycleStatus`, `modelId`, `locationId` | `itam_models.py` L123-157, L270-295 | Per-asset purchase cost exists. |
| Depreciation policy lives on the **model** (`usefulLifeYears`, `salvageValueCents` on `asset_models`), not the asset | `itam_finance_endpoints.py` L160-190, `itam_models.py` L218-232 | Book value needs asset + model join. Assets without a model policy have no book value. |
| `compute_book_value(purchase_date, purchase_cost_cents, useful_life_years, salvage_value_cents, now)`: straight-line, whole-year steps, floors at salvage, read-time only, never persisted. Returns `bookValueCents`, `yearsElapsed`, `annualDepreciationCents` | `itam_finance_service.py` L70-115 | The single source of truth for book value. Costing MUST call it verbatim. |
| Per-asset read route `GET /api/assets/{id}/book-value` (viewer-gated); `reason` codes `no_purchase_record`, `no_depreciation_policy_assigned` | `itam_finance_endpoints.py`, `itam_finance_service.py` L48-49 | Existing per-asset contract to mirror for the endpoint-level view. |
| Org-level book-value rollup ALREADY exists as a KPI: `_compute_asset_value_kpi` sums `bookValueCents`, tallies `withoutPolicyCount`, never fakes zero, `hasData:false` when empty, drill-down to `asset_value` report | `itam_reporting_kpis.py` L60-125, `itam_reporting_prebuilt.py` L120-175 | Do not write a second rollup that can disagree (PROJECT.md decision: "every ITAM report/KPI reuses its owning surface's computation verbatim"). Extract/extend, then have KPI + new cost view share one function. |
| **Licenses have NO cost field.** `LicenseCreate` = `name, notes, seatCount, expiryDate, isReassignable, manufacturerId, productKey` (`extra="forbid"`). **Consumables and components have no cost field either.** | `itam_models.py` L84-91, L319-345, L391-475 | **Biggest scope finding.** "License spend" and "allocated license cost" cannot be computed from existing data. See Open Decision D-1. |
| License seats: `license_assignments` rows `{licenseId, targetType: "user"\|"asset", targetId}`; unique on (licenseId, targetType, targetId); `seatCount` on license | `itam_license_service.py`, `itam_models.py` L361-380 | Seat-to-asset allocation is possible for `targetType == "asset"`; user-assigned seats have no asset to land on. |
| **No currency anywhere in ITAM.** Asset costs are integer cents with implicit currency. `finops_service.py` hardcodes `"USD"`. PO model uses **float** `total_cost`/`unit_price`; asset request `estimated_cost` is float. | `itam_models.py`, `finops_service.py` L137,184 | Single implicit currency. Cents arithmetic must stay integer. Do not sum PO float totals with asset cents. |
| Reporting framework: pre-built report registry, custom report builder, PDF/Excel/CSV export, KPI tiles with drill-down | `itam_reporting_*.py`, `ItamKpiPanel.tsx` | Cheap export/drill-down path for a new `asset_cost` report. |
| UI home: `components/itam/FinancePanel.tsx` inside `ITAMConsole` (tab list `catalog, lifecycle, finance, purchaseOrders, requests, licenses, ...`) | `ITAMConsole.tsx` L32-49 | Natural place for an org/asset cost view without a new sidebar module or permission. |
| Agent-discovered assets are keyed `asset-{hostname}` and may carry no purchase data | `.planning` baseline, `assets` collection | "Endpoint cost" = the ITAM asset record. Many endpoints will legitimately have no cost. |

---

# FEATURE 1 — Role-based catalogue access

## How mature multi-tenant apps do it (conventions, MEDIUM confidence)

1. **Menu is derived from permission, per item, default-deny.** Items the user cannot use are *absent*, not greyed out (GitHub, Azure Portal, Okta admin, Jira admin, AWS console services via IAM). Greyed/locked rendering is reserved for *plan/tier* gating (upsell), not for authorization.
2. **Groups with no visible children disappear.** (Already implemented.)
3. **Route guard is separate from the menu.** Hiding a link does not stop a deep link, bookmark, or hash change; the router guard re-checks the same predicate and renders an explicit "no access" screen (403 page) rather than a blank page, silent no-op, or redirect loop. Standard guidance: client-side gating is UX; the API is the security boundary.
4. **One predicate, one registry.** Menu, guard, and API reference the same permission key. Drift between "link visible" and "page allowed" is the classic bug class; mature apps generate both from one route/nav definition (and/or from a server-provided effective-permission set).
5. **Server is the authority for effective permissions.** The client receives the *evaluated* permission set (what the API will accept), not a re-implementation of role logic. Permissions refresh on role change (re-fetch on focus/interval or on a 403), not only at login.
6. **API 403 inside a visible page is handled gracefully** (permission revoked mid-session): inline "you no longer have access" state, not a toast storm.
7. **Admins can see what a role grants.** Role editors show the effective capability/menu set; larger products offer a role x module matrix or "preview as role".
8. **Super/platform admin sees everything; tenant-scoped admins see their tenant's enabled modules.**

## Table Stakes

| Feature | Why Expected | Complexity | Notes / Dependencies |
|---------|--------------|------------|----------------------|
| T1-01 Single authoritative **nav registry** (view id -> permission, group, label) consumed by BOTH `Sidebar` and the `App.tsx` navigation guard; delete the duplicate `viewPermissionMap` permission values | Spec says "UI gating mirrors backend route authorization"; today 9 views already disagree | MEDIUM | Touch `Sidebar.tsx` `navGroups`, `App.tsx` `viewPermissionMap`. Mechanical but wide (187 items). A unit test that sidebar and guard agree for every view is the acceptance test. |
| T1-02 **Fail-closed default**: no `UserContext` or no `permission` on an item -> hidden / denied | Default-deny is the baseline of any access-control UI; current `() => true` fallback is fail-open | LOW | `Sidebar.tsx` L178. |
| T1-03 **Render-time guard**: `renderView()` (or a wrapper) re-checks the permission for `currentView` before rendering any module | Menu hiding != access control; `setCurrentView` has callers other than the guarded handler | LOW-MEDIUM | `App.tsx` L1806. Audit direct `setCurrentView(...)` callers; route them through the guarded handler or guard at render. |
| T1-04 **Visible "no access" state** replacing silent `console.warn`: names the module, says contact your admin, offers return to Overview | Silent no-op reads as a broken app; every mature app has a 403 page | LOW | New small component; reuse existing empty-state styling. Do NOT leak other tenants' info. |
| T1-05 **Backend parity for gated catalogues**: every catalogue whose nav permission is `view:X` has its list/read routes guarded by `require_permission("view:X")` (or the module's existing equivalent). Produce a parity matrix; fix gaps for catalogues in scope | The milestone's stated defense-in-depth requirement; spot grep shows thin `view:` coverage | HIGH (breadth) / LOW per route | Largest risk in the milestone. Scope by sensitivity and by "what the sidebar exposes", not by touching all ~187 modules blindly. Router-level `dependencies=[Depends(require_permission(...))]` is cheaper than per-route edits. Must not break the API-key scope-narrowing path (`_scopes_allow`). |
| T1-06 **Effective-permission source of truth is the backend evaluator**: `/api/auth/me` (and login) return permissions computed by the same function the guards use (`DEFAULT_PERMISSIONS` UNION `db.roles` doc), instead of only the raw `db.roles` doc; remove reliance on the `/api/roles` static stub for non-super-admins | A role that has defaults but no role doc logs in with `permissions: []` and falls back to a stub; UI/API can disagree | MEDIUM | `authentication_endpoints.py` L223-231 & `/me` L253-281; `rbac_utils.verify_permission`; `App.tsx` L1185-1242. Keep `rbac_service._normalize_role` as the only role normalizer (existing PROJECT decision). |
| T1-07 **Seed gap closure**: nav permissions granted by no default role (`view:jobs`, `view:goal_system`, `view:predictive_health`) are either granted to appropriate default roles or consciously left super-admin-only (documented) | Otherwise "role holds the matching view: permission" is vacuous for those catalogues | LOW | Decision, then edit `app_startup.py`/`rbac_utils.py` seed dicts in lockstep (they are duplicated; see Pitfall: lockstep edits, as in Phase 25). |
| T1-08 **Tenant isolation holds**: nav/permission evaluation uses the caller's own tenant role docs only; super-admin "view as tenant" does not leak other tenants' role definitions | Non-negotiable platform invariant | LOW (verify) | `find_role_doc(db, role, tenant_id)` already handles tenant + global; add a regression test. |
| T1-09 **Permission changes take effect without re-login** (re-fetch effective permissions on window focus / after role edit / on first 403) | Nav derived only from login-time permissions leaves revoked users seeing modules until token expiry | LOW-MEDIUM | `App.tsx` already fetches roles; add a lightweight `/me` refresh. |
| T1-10 Keep **tier-lock vs permission-hide** semantics distinct and unchanged | Existing behavior users already see | LOW | Regression test only. |

## Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| D1-01 **Admin "what can this role see" view**: in role management, a read-only grouped list of the catalogues a role resolves to, computed from the same registry (T1-01) + the role's permission list | Directly answers "admin visibility of what a role can see"; makes the feature auditable; sells RBAC to compliance buyers | MEDIUM | Reuse registry + a shared `visibleViewsFor(permissions)` pure function. No new data model. Surfaces in the existing role/user management UI (`roleManagement`/`userManagement`, `manage:rbac`). |
| D1-02 **Role x catalogue matrix** (rows = roles, columns = catalogue groups) | Fast review of least-privilege across roles; useful for access reviews (platform already has an Access Reviews module) | MEDIUM | Same pure function over all roles in the tenant. Read-only. |
| D1-03 **CI parity test**: for every nav permission string, assert either a backend route guard exists or an explicit, reviewed "UI-only" allowlist entry | Makes "UI mirrors backend" a permanent regression net instead of a one-off audit | MEDIUM | Static scan of `require_permission(...)` literals vs registry. Fits the existing pytest suite. |
| D1-04 **Sub-module (tab) gating inside multi-tab consoles** (e.g. ITAM console tabs: finance/settings/purchase orders visible only if the role's backend guards would allow them) | An `itam_viewer` currently sees tabs whose writes/reads would 403 | MEDIUM | `ITAMConsole.tsx` TABS is static. Optional; do after catalogue-level gating. Keep to ITAM console to avoid creep. |
| D1-05 Audit log entry for **denied navigation / 403 on a gated catalogue** | Compliance-product expectation (who tried to reach what) | LOW-MEDIUM | Only if existing audit sink makes it a one-liner; otherwise defer. |

## Anti-Features

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| New permission model / `catalogue:*` permission namespace / per-catalogue ACL tuples | "Cleaner" mapping of menu to access | Explicitly out of scope; duplicates `view:` permissions, creates a third source of truth, needs a migration | Reuse existing `view:` strings; fix mapping drift (T1-01) |
| Routing nav decisions through OpenFGA/ReBAC tuples | Milestone text mentions "Phase 36 ReBAC" | Sidebar does not use OpenFGA today; per-item network authz checks for ~187 items = latency + new failure mode | Keep flat role permissions for nav; ReBAC stays for resource-level checks |
| Showing denied catalogues greyed/locked with "request access" | Discoverability | Leaks existence of security modules to low-privilege users; conflicts with tier-lock visual language | Hide; admins use D1-01 to see the grants |
| Frontend-only enforcement ("hide and done") | Fast | Zero security; URL/API still open | T1-03 + T1-05 |
| "Impersonate role" / "view as user" mode | Admin convenience | High-risk (session confusion, audit complexity, token handling) | Read-only preview (D1-01) |
| Server-driven menu (backend returns the whole nav tree) | Single source of truth | Rewrites 187 items + icons + labels; large regression surface for a gating milestone | Shared frontend registry + effective-permission set from server (T1-01/T1-06) |
| Per-user nav overrides / custom hide lists | Personalization | Muddies "role determines visibility"; breaks audit story | Out of scope; favorites/pins would be a separate feature |
| Granting access by hiding `manage:*` logic in the client | Convenience | Client must never decide manage rights | Server returns effective set |

---

# FEATURE 2 — Asset costing (organization and endpoint level)

## How asset costs are typically rolled up and shown (conventions, MEDIUM confidence)

- **Two numbers, never one.** ITAM tools (Snipe-IT, GLPI, ServiceNow, Lansweeper) show *Purchase / original cost* and *Current (depreciated / book) value* side by side; both roll up to org totals. Disposed/retired assets are shown separately or filtered, not silently mixed into "current value".
- **Org total is the sum of the rows beneath it**, and the drill-down must reconcile exactly to the headline figure (the tile-says-X, report-says-Y bug is trust-breaking; PROJECT.md already records this as a decision).
- **Coverage is explicit.** Assets missing a cost or a depreciation policy are counted and surfaced ("42 of 310 assets have no purchase cost"), not treated as $0 and not silently dropped.
- **Groupings:** by category / model / location / lifecycle status / purchase year, plus an assets-table export (CSV/Excel). Per-asset detail shows purchase cost, purchase date, age, annual depreciation, book value, % depreciated.
- **Software cost is a different shape than hardware cost.** A license has a purchase/subscription cost and a seat count; per-seat cost = cost / seats. Seat-level allocation to a device = per-seat cost x seats assigned to that device. Idle (unassigned) seats are a recognized optimization signal. Licenses are normally *not* depreciated alongside hardware in ITAM views (tools like Snipe-IT track license purchase cost; some finance teams amortize, which is out of scope here).
- **Currency:** ITAM tools store one currency per instance/tenant and format with a configured symbol; real multi-currency with FX is a finance-system (ERP) concern. Mixed-currency summation without conversion is a known correctness bug.
- **TCO** in the textbook sense (purchase + operation + maintenance + disposal) requires data ITAM tools usually do not hold; mid-market ITAM shows "acquisition cost + licenses" and calls it cost, not TCO.

## Table Stakes

| Feature | Why Expected | Complexity | Notes / Dependencies |
|---------|--------------|------------|----------------------|
| T2-01 **Org-level cost summary** for the tenant: total purchase cost, total current book value, asset counts (with cost / without cost / without depreciation policy) | The milestone goal; the core of any ITAM cost view | MEDIUM | Build on `_compute_asset_value_kpi` logic (`itam_reporting_kpis.py`) + `compute_book_value`. Extract one shared per-asset cost function used by KPI, pre-built report, and the new endpoint. |
| T2-02 **Endpoint/asset-level cost**: per asset purchase cost, purchase date, depreciation basis (life/salvage from model), annual depreciation, book value, with the same reason codes as `GET .../book-value` when data is missing | Milestone goal; drill-down target of T2-01 | LOW-MEDIUM | Existing `GET /api/assets/{id}/book-value` is the per-asset seed; extend response or add `/cost`. Viewer-gated (`_require_itam_viewer`). |
| T2-03 **Reconciliation**: org totals equal the sum of the per-asset rows plus explicitly labelled unattributed buckets; tested | Trust. Per PROJECT.md key decision (reports reuse owning computation verbatim) | LOW (design) | Single function; test asserts `sum(rows) == headline`. |
| T2-04 **Missing-data honesty**: asset with no `purchaseCostCents` -> "cost not recorded" (null), never `0`; asset with cost but no model policy -> purchase cost counted, book value null + `withoutPolicyCount`; `hasData:false` for empty tenant | Existing KPI already behaves this way; a cost view that shows $0 for unrecorded endpoints would mislead (many agent-discovered endpoints have no purchase data) | LOW | Note: the current KPI drops assets with cost-but-no-policy from the *whole* tally; costing needs purchase-total to include them and book-value-total to exclude them, with both counts. |
| T2-05 **Integer-cents arithmetic and explicit currency label**: all rollups in integer cents; every amount rendered with a clearly stated tenant currency (default USD constant today), never a bare number or assumed `$` | Float money is a known bug source (PO model already uses floats; do not mix) | LOW | Format only at the UI edge. Do NOT add PO `total_cost` into asset totals. |
| T2-06 **Lifecycle-aware scope**: current book value excludes disposed/retired assets by default (shown separately or via filter); counts reflect the filter | Standard ITAM expectation; otherwise "current value" includes things already gone | LOW-MEDIUM | Uses `lifecycleStatus` on the asset. Define the included set in requirements (e.g. exclude disposed). |
| T2-07 **License cost at org level**: total license spend and (assigned vs unassigned) split, from the licenses catalogue | Explicitly in the milestone ("license spend") | MEDIUM | **BLOCKED on D-1: no cost field exists on licenses.** Needs one additive optional field on License create/update/edit form (see D-1). |
| T2-08 **Allocated license cost per endpoint**: per-seat cost (license cost / `seatCount`) x seats assigned with `targetType == "asset"` for that asset, listed per license | Explicitly in the milestone ("allocated license cost") | MEDIUM | Uses `license_assignments` (unique per license+target). Seats assigned to `user` targets are shown at org level as "assigned to users (not attributed to an endpoint)", never guessed onto a device. Guard `seatCount == 0` (divide by zero). |
| T2-09 **Authorization + tenant isolation**: cost endpoints use the existing `_require_itam_viewer` (`view:itam` or `manage:assets`, API-key scope-aware); every query tenant-scoped via the DB wrapper | Costs are financial data; the existing book-value route is already viewer-gated | LOW | Do not invent a `view:costs` permission (no new permission model). If the product owner wants costs hidden from `itam_viewer`, use the existing `manage:finance`/`manage:itam` permissions that already exist on `itam_admin`; this is a requirements decision (D-2). |
| T2-10 **UI placement in the existing ITAM console** (Finance tab section or sibling "Cost" tab) with org summary cards + per-asset table (sortable, filterable) and per-asset detail | Avoids a new sidebar module/permission; mirrors where users already look for finance data | MEDIUM | `FinancePanel.tsx`, `ITAMConsole.tsx` TABS. |
| T2-11 **CSV/Excel export** of the per-asset cost table | Every ITAM tool exports asset cost; reporting framework makes it cheap | LOW | Register an `asset_cost` entry in `itam_reporting_prebuilt.py`'s registry (PDF/Excel/CSV exporters exist). Keep CSV formula-injection protection already built in Phase 70. |
| T2-12 Cost view works for a **super-admin viewing a selected tenant** and never crosses tenants | Existing console pattern (`isSuperAdminView`, `tenants` prop) | LOW | Follow `FinancePanel` conventions. |

## Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| D2-01 **Group-by breakdowns** (category, model, location, lifecycle status, purchase year) with totals | Answers "where is our money" fast; standard in mature ITAM | MEDIUM | Aggregation over the same shared per-asset function. Reconcile to headline. |
| D2-02 **Cost-coverage indicator** ("N% of assets have purchase cost; M lack a depreciation policy") with a link to the offending assets | Turns the missing-data honesty into a data-quality worklist; fits the platform's compliance-evidence mindset | LOW | Falls out of T2-04 counts + existing filtered asset list. |
| D2-03 **Idle-seat cost** (unassigned seats x per-seat cost) and license-expiry-with-cost forecast (next 12 months) | Software cost optimization is the main reason buyers want license cost in ITAM | MEDIUM | Uses existing `expiryDate`, `_next_twelve_month_keys`-style bucketing. Depends on D-1 cost field. |
| D2-04 **Total endpoint cost** line = purchase cost + allocated license cost, displayed with book value as a separate line (do not add a depreciating stock value to a flow) | Single "what does this endpoint cost us" figure | LOW | Pure presentation; define the formula in requirements. |
| D2-05 **MSP cross-tenant rollup** for super-admins (per-tenant rows, no cross-tenant sum unless currencies are known identical) | Matches the MSP positioning in PROJECT.md | MEDIUM | Super-admin only. Per-tenant rows; no grand total in v4.2. |
| D2-06 Configurable **tenant display currency code** (symbol only, no FX) | Non-USD tenants see correct symbols | LOW-MEDIUM | Needs one setting (existing `itam_warranty_alert_window`-style settings doc is the precedent). Defer if D-1 already stretches scope. |
| D2-07 Cost KPI tile(s) on the existing ITAM KPI dashboard with drill-down to the cost table | Consistency with Phase 72 dashboard | LOW | `ItamKpiPanel.tsx`; reuse `drilldownReportKey`. |

## Anti-Features

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| New cost-entry system / separate cost ledger / cost-center module | "Real" costing | Explicitly out of scope; duplicates `purchaseCostCents`, PO data | Roll up existing fields; at most ONE additive optional cost field on License (D-1) |
| Multi-currency with FX conversion / historical exchange rates | Global tenants | Needs a rates source, rounding policy, restatement rules; correctness minefield; no currency data exists | Single tenant currency, label explicitly, never sum across currencies |
| Declining-balance / MACRS / units-of-production depreciation | Snipe-IT offers more methods | Breaks the "reuse `compute_book_value` verbatim" invariant; only straight-line is shipped and tested | Keep straight-line; revisit as its own milestone |
| True TCO (maintenance, support labor, power, disposal costs) | "Total cost of ownership" is a buzzword | No data source in the platform; invented numbers | Label the figure "acquisition + license cost" |
| Depreciating licenses | Finance teams amortize software | No amortization schedule/data; scope creep | Show license cost as spend, not as a depreciating asset |
| Summing PO `total_cost` into asset totals | PO has a cost | Double-counts purchases already on the asset (`purchaseCostCents` + `purchase_order_id` link); PO fields are floats | PO spend remains in the PO panel; costing uses asset cents only |
| Persisting computed book value / cost snapshots | Faster queries | Contradicts D-04 (never persisted); staleness; new write paths | Compute at read time; add caching only if measured necessary |
| Guessing user-assigned seat cost onto the user's devices | Wants "complete" per-endpoint figure | Fabricates attribution (one user, many devices) | Show as "assigned to users - not attributed to an endpoint" |
| Consumable/component costing in v4.2 | Milestone text says "licenses/consumables" | Consumables/components have no cost field and are checked out to users/locations (no asset link; components do have `assetIds`) | Defer to a follow-up; if requirements insist, org-level only after adding a unit-cost field (second D-1-style decision) |
| Budgeting, forecasting, chargeback invoicing | Natural next step | Different product surface (FinOps-style) | Out of scope |

---

## Open Decisions for Requirements (flag to the user)

| ID | Decision | Why it matters | Recommendation |
|----|----------|----------------|----------------|
| **D-1** | Licenses (and consumables/components) have **no cost field**. "Total license spend" and "allocated license cost per endpoint" are impossible without data. | Violates the milestone premise "reuse existing data only" for the license half of Feature 2. | Add exactly **one optional, additive** `purchaseCostCents` (total cost for the license, integer cents) to License create/update/response and the existing `LicensesPanel` form. Note `extra="forbid"` on the Pydantic models, so the model change is mandatory, not optional. Treat absence as "cost not recorded". Alternatively ship asset-level cost only and display licenses as seat counts. Do NOT do consumables/components in v4.2. |
| **D-2** | Who may see costs: any `view:itam` holder (matches existing `GET .../book-value`) or only admins (`manage:assets`/`manage:itam`)? | Costs are sensitive; `itam_viewer` can already read book value. | Default: same as existing book-value (`_require_itam_viewer`), because hiding it only in the new view while the old route exposes it is inconsistent. |
| **D-3** | Definition of "current" rollup scope (exclude disposed? archived?). | Changes headline numbers. | Exclude disposed/retired from current book value, include in purchase total only if a "include disposed" filter is on; state in the UI. |
| **D-4** | Parity scope for Feature 1 (T1-05): all ~187 catalogues or those in specified groups? | Backend guard retrofits are the milestone's largest unknown. | Ship the registry, guard, no-access state, and D1-03 test for all; retrofit backend guards in priority order (financial, identity, security-operations, ITAM), with the rest on a reviewed "UI-only" allowlist. |

---

## Feature Dependencies

```
T1-01 nav registry ──requires──> (nothing; refactor of Sidebar.tsx + App.tsx map)
    ├──enables──> T1-03 render-time guard ──enables──> T1-04 no-access state
    ├──enables──> D1-01 role->visible catalogues view ──enables──> D1-02 role x catalogue matrix
    └──enables──> D1-03 CI parity test <──requires── T1-05 backend parity audit

T1-06 backend-evaluated effective permissions ──enhances──> T1-01 (UI and API share one evaluator)
T1-07 seed gap closure ──requires──> T1-06 (so the grants are actually delivered to the client)
T1-09 live permission refresh ──requires──> T1-06 (/me returns evaluated set)

T2-04 missing-data honesty ──enables──> T2-01 org summary ──enables──> T2-03 reconciliation
T2-02 per-asset cost ──requires──> compute_book_value (itam_finance_service.py) + model depreciation policy
T2-01 ──requires──> shared per-asset cost function (extracted from _compute_asset_value_kpi)
T2-07 license org spend ──requires──> D-1 license cost field
T2-08 allocated license cost per asset ──requires──> T2-07 + license_assignments (targetType=asset)
D2-03 idle-seat / renewal forecast ──requires──> D-1 cost field + T2-08
D2-04 total endpoint cost ──requires──> T2-02 + T2-08
T2-11 export ──requires──> T2-02 + reporting registry (itam_reporting_prebuilt.py)
T2-10 UI ──requires──> T2-01/T2-02 endpoints

Cross-feature:
Costing UI (T2-10) lives in the ITAM console, which is itself a gated catalogue (view:itam).
Cost endpoints reuse _require_itam_viewer; no coupling that would force new permissions.
```

### Dependency Notes

- **T1-01 before everything in Feature 1:** the 9 existing mismatches mean any new guard/state would inherit inconsistent answers.
- **T1-06 is the keystone for "mirrors backend":** without a server-evaluated permission set the client keeps a parallel evaluator.
- **D-1 gates half of Feature 2:** requirements must resolve it before planning license phases; asset-level cost (T2-01/02/03/04/05/06/09/10/11) is unblocked and should land first.
- **Features are independent of each other:** sequence is free; Feature 1 touches `Sidebar.tsx`/`App.tsx`/auth endpoints, Feature 2 touches `itam_*` and ITAM UI. Only shared file risk is `App.tsx` (both may add nothing there for Feature 2, so low conflict).

---

## MVP Definition

### Launch With (v4.2)

**Feature 1**
- [ ] T1-01 nav registry shared by Sidebar + guard (9 mismatches resolved)
- [ ] T1-02 fail-closed default
- [ ] T1-03 render-time guard + T1-04 visible no-access state
- [ ] T1-06 server-evaluated effective permissions in login and `/me`
- [ ] T1-05 backend parity matrix + guards for in-scope catalogues (per D-4), T1-07 seed gap decision
- [ ] T1-08 tenant-isolation regression test, T1-10 tier-lock regression test
- [ ] D1-01 "what can this role see" view (the explicit admin-visibility ask)

**Feature 2**
- [ ] T2-01..T2-06, T2-09, T2-10, T2-11, T2-12 (asset-level + org-level hardware cost, honest about missing data, reconciled, exportable)
- [ ] T2-07/T2-08 license spend and per-endpoint allocation, **conditional on D-1 being approved**

### Add After Validation (v4.x)

- [ ] D1-02 role x catalogue matrix, D1-03 CI parity test (promote to launch if cheap during T1-05), T1-09 live refresh (promote if auth refresh is easy)
- [ ] D2-01 group-by breakdowns, D2-02 coverage indicator, D2-07 KPI tile
- [ ] D1-04 ITAM tab-level gating

### Future Consideration

- [ ] D2-03 idle-seat/renewal forecast, D2-05 MSP cross-tenant rollup, D2-06 display currency
- [ ] Consumable/component costing, additional depreciation methods, true TCO, FX

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| T1-01 shared nav registry | HIGH | MEDIUM | P1 |
| T1-02 fail-closed | HIGH | LOW | P1 |
| T1-03/04 render guard + no-access state | HIGH | LOW-MED | P1 |
| T1-06 server-evaluated permissions | HIGH | MEDIUM | P1 |
| T1-05 backend parity (in-scope) | HIGH | HIGH (breadth) | P1 |
| D1-01 role -> visible catalogues | HIGH | MEDIUM | P1 |
| D1-03 parity CI test | MEDIUM | MEDIUM | P2 |
| T1-09 live refresh | MEDIUM | LOW-MED | P2 |
| D1-02 role matrix | MEDIUM | MEDIUM | P2 |
| T2-01/02/03/04/05/06 asset + org hardware cost | HIGH | MEDIUM | P1 |
| T2-09/12 authz + tenant scope | HIGH | LOW | P1 |
| T2-10/11 UI + export | HIGH | MEDIUM | P1 |
| T2-07/08 license spend + allocation | HIGH | MEDIUM | P1 (blocked on D-1) |
| D2-01 group-by | MEDIUM | MEDIUM | P2 |
| D2-02 coverage indicator | MEDIUM | LOW | P2 |
| D2-03 idle-seat/forecast | MEDIUM | MEDIUM | P3 |
| D2-05 MSP rollup | MEDIUM | MEDIUM | P3 |
| D2-06 currency code | LOW | LOW-MED | P3 |

## Competitor / Convention Analysis

| Aspect | Snipe-IT / GLPI style (MEDIUM) | Enterprise (ServiceNow, Azure/Okta consoles) (MEDIUM) | Our Approach |
|--------|-------------------------------|-------------------------------------------------------|--------------|
| Nav gating | Role/permission-driven menu, hidden when not permitted | Hidden items + 403 page; admin role-capability views | Hide + 403 state + admin "role sees" view |
| Asset cost | Purchase cost + depreciated value per asset, asset reports, CSV export | Cost per CI/asset, roll-ups by group, TCO with extra cost sources | Purchase + book value, org + asset, export; label "acquisition + license" |
| License cost | Purchase cost on the license, seats | Cost per seat, optimization (idle seats) | Add one cost field (D-1); per-seat allocation to assets |
| Currency | One instance currency | Multi-currency via finance integrations | Single labelled tenant currency; no FX |

## Sources

- Codebase (HIGH): `components/Sidebar.tsx`, `App.tsx` (L242-446 `viewPermissionMap`, L1185-1242, L1379-1395, L1806), `backend/rbac_utils.py`, `backend/authentication_endpoints.py` (L215-281), `backend/role_endpoints.py`, `backend/rebac_service.py`, `backend/itam_finance_service.py`, `backend/itam_finance_endpoints.py`, `backend/itam_models.py`, `backend/itam_license_service.py`, `backend/itam_reporting_kpis.py`, `backend/itam_reporting_prebuilt.py`, `backend/itam_asset_endpoints.py`, `components/itam/ITAMConsole.tsx`, `.planning/PROJECT.md`
- Web (LOW-MEDIUM, generic secondary sources): [Snipe-IT overview (Dashen)](https://dashen-tech.com/en/dev-tools/snipe-it-self-hosted-asset-management/) - straight-line/declining depreciation, license seats; [Angular role-based security (Microsoft DevBlogs)](https://devblogs.microsoft.com/premier-developer/angular-how-to-implement-role-based-security/) - route guards vs hidden menu items, client-side authz is UX only; [ITAM cost / TCO (NinjaOne)](https://www.ninjaone.com/itam-software-cost/) and [Xurrent ITAM glossary](https://www.xurrent.com/glossary/it-asset-management-itam) - TCO and cost-allocation concepts
- Conventions not backed by a specific fetched source (stated from domain knowledge, MEDIUM): hide-vs-lock semantics, reconciliation and coverage UX, single-currency-per-instance norm, license per-seat allocation.

---
*Feature research for: v4.2 Catalogue Access Control & Asset Costing*
*Researched: 2026-10-12*
