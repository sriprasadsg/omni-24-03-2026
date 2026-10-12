# Project Research Summary
**Project:** Enterprise OmniAgent v4.2, Catalogue Access Control & Asset Costing
**Researched:** 2026-10-12
**Confidence:** HIGH

## Executive Summary
v4.2 is integration work with zero new dependencies (Python, JS or agents). Verify with `git diff --stat -- backend/requirements.txt package.json package-lock.json`, which should be empty. Don't open a stack phase or a dependency-approval checkpoint.

**Feature 1 (catalogue access) is an ALIGN + HARDEN job, not greenfield.**
- The sidebar already gates 188 items (89 permission strings) by permission, and `App.tsx` has a second gate, `viewPermissionMap`.
- The real work is backend enforcement. About 50-63 backend routers have no permission guard, and about 64 of 89 sidebar permission strings are checked by no backend route. UI hiding alone is security-by-obscurity.
- Example: `GET /api/assets*` returns `purchaseCostCents` to any authenticated tenant user.
- Permission-source drift: `rbac_utils.DEFAULT_PERMISSIONS`, `rbac_service.default_roles` and the seeded role docs in `app_startup.py` have diverged. 29 sidebar strings are in neither default table, and 17 more are in only one.
- Nine views mismatch between Sidebar.tsx and the `viewPermissionMap` in App.tsx: `agentCapabilities`, `jobs`, `llmops`, `persistenceDetection`, `sustainability`, `swarm`, `unifiedOps`, `vulnerabilityManagement`, `zeroTrustQuantum`.
- `/login` and `/me` return only the role-doc permissions, so `itam_*` roles get an empty sidebar.
- **Keystone fix:** a single `effective_permissions()` resolver surfaced at `/login` and `/me`, backed by a view→route catalogue manifest and a deny-by-default route parity test with a reviewed gap ledger.

**Feature 2 (asset costing) reuses existing hardware cost.**
- It builds on `purchaseCostCents`, `compute_book_value` and the `_compute_asset_value_kpi` org rollup.
- It must call the SAME per-asset function as the KPI tile, with a parity test.
- It ships as read-only service and endpoints under `/api/itam/costs`, gated by `_require_itam_viewer`. Everything is computed at read time, with no persisted rollups and no `$lookup` (it leaks across tenants).
- Endpoints ARE assets, so no join is needed beyond `agents.assetId`.
- **Blocking data gap:** licenses and consumables have no cost field (`extra="forbid"` models). License spend needs an additive optional integer-cents field, or it must be descoped (D-1).

**Cross-tenant isolation:**
- The platform-admin context bypasses the tenant `$match`. Cost routes must require an explicit tenant and return 400 otherwise.
- A two-tenant isolation test is mandatory.

## Key Findings
- **Stack:**
  - Existing FastAPI, Pydantic, Motor, React 19, TS 5.7, recharts, vitest and the `itam_reporting_*` registry.
  - Schema-only change: an optional license cost in cents.
  - Do NOT add:
    - a new permission model or an OPA/Casbin/CASL engine;
    - a rollup collection or scheduler;
    - a money library or react-router.
  - Don't use `view:finops` for ITAM cost. Don't roll up PO totals (float dollars).
- **Features, Feature 1:**
  - T1-01 shared nav registry/manifest.
  - T1-02 fail-closed default (the Sidebar currently falls back to `() => true`).
  - T1-03/04 render-time `ViewGate` and a no-access state.
  - T1-05 backend parity.
  - T1-06 server-effective permissions.
  - T1-07 seed-gap decision.
  - T1-08/10 tenant-isolation and tier-lock regression tests.
  - D1-01 admin "what can this role see" view.
  - D1-03 CI parity test (promote to launch).
- **Features, Feature 2:**
  - T2-01..06 org and asset cost: purchase plus book value, reconciled to the KPI, null is never zero, integer cents.
  - T2-09/12 `_require_itam_viewer` and tenant scope.
  - T2-10/11 ITAM console tab plus export through the report registry.
  - T2-07/08 license spend and per-endpoint allocation, conditional on D-1.
- **Deferred:**
  - ITAM tab-level gating.
  - Idle-seat/renewal forecast.
  - MSP cross-tenant rollup.
  - Display currency.
  - Consumable/component costing.
  - Other depreciation methods, true TCO, FX, chargeback.
- **Architecture:**
  - One resolver, `rbac_utils.effective_permissions()`, plus a single `rbac_defaults.py`, with guards tagged `required_permission`.
  - `shared/catalogue-access.json` and `catalogueAccess.ts`.
  - `test_catalogue_route_parity.py` and `shared/catalogue-gaps.json`.
  - Router-level `require_permission` on unguarded routers: reads get `view:X`, writes keep `manage:X`.
  - `itam_cost_service.py` (pure, `db` passed in, batched projected `find` plus a `$in` model lookup, Python loop).
  - `itam_cost_endpoints.py` (`/api/itam/costs/summary`, `/assets`, `/assets/{id}`, keyset pagination, coverage and reason fields).
  - `CostsPanel.tsx` as an ITAM console tab, with no new nav item or permission.
- **Top pitfalls:**
  1. UI-only gating. Enforce on the backend first, use the manifest and a per-route sweep, and hide a nav item only when a guarded route exists.
  2. Divergent tables and ungranted strings. Don't blanket-grant to `user`/`viewer`; decide per role and return effective permissions from `/me`.
  3. Cross-tenant leakage. Require an explicit tenant, no `$lookup` or `@cached` on cost routes, and a two-tenant test on every cost route.
  4. Missing license cost source. Resolve D-1, show coverage, and never treat null as 0.
  5. Rollup drift, math and allocation errors:
     - share one book-value function and add a golden-value table;
     - `sum(endpoint allocations) + unallocated == org spend`;
     - the asset-level float policy fields are ignored by `get_asset_book_value`;
     - `to_list(length=1000)` truncates seat counts.
  - Also: fail-open Sidebar and `setCurrentView` bypass paths, stale client permissions after role edits, empty-sidebar lockout (`itam_viewer` lacks `view:dashboard`), and super-admin string handling that differs in five places.

## Implications for Roadmap
Phase numbering continues from 75. There are two parallel tracks, and their only coupling is a manifest entry for `/api/itam/costs`.

- **75. Permission resolver unification and delivery fix.** Everything else in Feature 1 depends on it.
  - Delivers: `effective_permissions()`, one defaults table, `/login` and `/me` returning effective permissions, guard tagging, seeded `itam_*` role docs, a neutralized `/api/roles` stub fallback, and role-edit session revoke or refresh.
  - Avoids pitfalls 2 and 5.
- **76. Catalogue manifest, parity test and gap ledger (audit only).** Turns "how many routes are unguarded" into a measured backlog.
  - Delivers: the manifest, a vitest drift test, `test_catalogue_route_parity.py` and the initial gap report, with `/api/agents/*` excluded.
  - Avoids pitfalls 1 and 2.
- **77. Backend route guards for in-scope catalogues.** The largest effort, split by sidebar group, and it must precede any UI claim.
  - Delivers: guards on the priority groups (Assets/Agents/ITAM/Settings, then financial, identity, security ops), gated or stripped cost fields on `/api/assets*`, and a shrinking ledger.
  - Avoids pitfalls 1 and 14, and the API-key scope narrowing gap.
- **78. Sidebar and ViewGate rewiring (UI last).**
  - Delivers: the Sidebar reading the manifest, `viewPermissionMap` deleted, fail-closed `hasPermission`, `ViewGate` around `renderView`, all `setCurrentView` paths routed through one guard, a shared `isSuperAdmin()`, a no-access state, a permitted landing view, an empty-role state, permission refresh on 403 and focus, and the D1-01 role view.
  - Avoids pitfalls 3, 6, 16 and 17.
- **79. Cost data model (gated on D-1).** Optional integer-cents license cost with a billing basis, plus minimal `LicensesPanel` inputs. Defer consumables. Drop the phase if D-1 is "descope". Avoids pitfall 7.
- **80. Cost aggregation API.** Ship the hardware slice first, then add license lines once 79 lands.
  - Delivers: the shared per-asset helper used by the KPI, report and cost view, golden-value, parity, two-tenant, allocation-invariant and API-key scope tests, and a 20k-asset timing test.
  - Avoids pitfalls 4, 8-13, 15 and 18.
- **81. Cost UI.** `CostsPanel`, an ITAM tab, `apiService` and `types.ts` additions, i18n keys, a coverage banner, the export, a tenant picker, and copy explaining whole-year depreciation.

**Ordering rationale:**
- Feature 1 runs resolver, then measurement, then enforcement, then UI. UI-last is a hard rule.
- Feature 2 runs data model, then API, then UI. The hardware-only part of 80 doesn't depend on 79.
- The main schedule risk is hardening the unguarded routers. Cap it with D-4 and the gap ledger.

**Research flags:**
- **Needs research:**
  - Phase 77: the correct guard per router, agent-auth routes (guarding `/api/agents/*` with user RBAC breaks telemetry), non-user callers and API-key paths.
  - Phase 75: a role × catalogue matrix review with the stakeholder.
  - Phase 79/80: license cost basis, currency, and disposed-asset treatment.
  - Phase 76: a quick spike on the Vite/vitest/tsconfig JSON import of `shared/`.
- **Standard patterns:** Phase 78 (still needs per-role manual verification) and Phase 81.

## Open Decisions (carried forward)
- **D-1: license/consumable cost field vs descoping license spend.**
  - Recommendation: add ONE optional integer-cents field on License (with billing basis) and defer consumables and components.
  - If descoped, label the license lines "not tracked".
  - This is the key open decision.
- **D-2: which permission gates cost views.**
  - Recommendation: `view:itam` via `_require_itam_viewer`, for parity with `/book-value` and the KPI.
  - `manage:finance` is the no-new-model tightening option. Never use `view:finops`.
- **D-3: do disposed/retired assets count.**
  - Recommendation: exclude them from current book value by default, and include them in the purchase total only behind an explicit filter.
  - Apply the same rule in the KPI and the cost view.
- **D-4: backend-guard parity scope.**
  - Recommendation: priority groups plus a tracked gap ledger, not all ~188 catalogues.
  - Exclude the agent-auth `/api/agents/*` routes.

## Confidence
| Area | Confidence | Notes |
|---|---|---|
| Stack | HIGH | Verified against the repo, `requirements.txt` and `package.json`. |
| Features | MEDIUM-HIGH | The codebase baseline is HIGH. ITAM costing and nav-gating conventions are MEDIUM, from generic secondary sources. |
| Architecture | HIGH | First-party reads. Assumptions flagged: the Vite JSON import and consumable record semantics. |
| Pitfalls | HIGH | Repo reads plus scripted diffs. Scale thresholds are unmeasured. |

**Overall:** HIGH.

**Gaps to address:**
- The 50 vs 63 unguarded-router counts and the 64/89 unmatched-string counts differ between researchers because they came from ad-hoc greps. Re-run them in Phase 76 as the baseline.
- Check each of the 29 ungranted sidebar strings against `app_startup.py` seeds and live `roles` documents before calling it a bug.
- License cost basis is undecided: total vs per-seat, billing period, and implicit vs explicit currency.
- User-assigned license seats can't be attributed to an endpoint. Surface them as "unattributed".
- Agent-discovered and manual assets can duplicate the same device. Decide a dedupe key (serial first) and report duplicates rather than auto-merging.
- Large-tenant performance is unmeasured.
- Tenant `enabledFeatures` is a UI-only gate, out of scope for v4.2 but belonging in the verification matrix.
- Existing custom role docs won't contain newly added default strings. Prefer returning effective permissions over a migration.

## Sources
- Primary (HIGH): repo reads of the rbac, auth, tenant, ITAM, Sidebar, App and apiService files, `requirements.txt`, `package.json`, `.planning/PROJECT.md` (Phase 59, 63, 72 and 73 decisions), and the scripted diffs.
- Secondary (MEDIUM): Snipe-IT, GLPI and ServiceNow conventions.
- Tertiary (LOW): generic web sources from Dashen, Microsoft DevBlogs, NinjaOne and Xurrent.
