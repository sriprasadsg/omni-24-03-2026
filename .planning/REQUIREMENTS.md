# Requirements: Catalogue Access Control & Asset Costing (v4.2)

**Defined:** 2026-10-12
**Core Value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with evidence proving it — at any moment.
**Goal:** Give tenants role-scoped visibility of the left-nav catalogues and a cost view of their assets at organization and endpoint level, both built on systems already shipped (RBAC, ITAM finance). No new permission model; one minimal additive cost field.

## v1 Requirements

### 1. Catalogue Access Control

- [ ] **ACC-01**: `/login` and `/me` return a server-evaluated *effective* permission set (role-doc permissions unioned with defaults) from a single resolver, so no role logs in with an empty permission list.
- [ ] **ACC-02**: The drifted permission defaults (`rbac_utils.DEFAULT_PERMISSIONS` vs `rbac_service.default_roles`) are collapsed into one source of truth, and the missing `itam_admin/itam_user/itam_viewer` role documents are seeded.
- [ ] **ACC-03**: A single shared catalogue manifest maps each left-nav catalogue to its required permission and its backend route(s); the frontend reads it instead of the divergent `Sidebar.tsx` / `App.tsx viewPermissionMap` tables (the 9 mismatched views reconciled).
- [ ] **ACC-04**: Backend route-permission guards are added to the priority unguarded router groups (Assets, ITAM, Settings, financial, identity, security-operations); routers not yet guarded are recorded in a committed gap ledger. Agent-authenticated `/api/agents/*` routes are excluded by design.
- [ ] **ACC-05**: A deny-by-default route-parity test fails when an in-scope catalogue's routes are not guarded per the manifest, plus a frontend test that fails on manifest/sidebar drift.
- [ ] **ACC-06**: The sidebar fails closed (a catalogue is hidden unless the user holds its permission — no fail-open fallback), a render-time gate guards the active view and every navigation path, and a user with no permitted catalogue sees a clear no-access/empty state with a guaranteed landing view and sign-out (no empty-sidebar lockout).
- [ ] **ACC-07**: An admin "what can this role see" view lists which catalogues each role can access.
- [ ] **ACC-08**: The client refreshes its effective permissions on a 403 and on window focus, so a role-permission edit takes effect without a full re-login.
- [ ] **ACC-09**: Regression tests prove catalogue visibility and route guards hold per role and per tenant, including super-admin / `platform-admin` handling.

### 2. Asset Costing (Organization & Endpoint)

- [ ] **COST-01**: Organization and endpoint cost reuse the *same* per-asset book-value computation as the existing ITAM KPI tile (Phase 72), enforced by a parity test so the tile, report, and cost view cannot disagree.
- [ ] **COST-02**: A read-only org-level cost summary (`/api/itam/costs/summary`, gated by `view:itam`) returns the tenant's total purchase cost and current depreciated book value, with coverage reported and assets lacking cost shown as null (never 0).
- [ ] **COST-03**: Endpoint/asset-level cost (`/api/itam/costs/assets` paginated and `/assets/{id}`) returns per-asset purchase cost and book value; endpoints are assets (joined only via `agents.assetId`).
- [ ] **COST-04**: One optional integer-cents cost field (with a billing basis) is added to the License model, with a minimal UI input, so license spend can be recorded. Consumables and components are deferred.
- [ ] **COST-05**: Org license spend and per-endpoint allocation of *asset-assigned* license seats are reported; user-assigned seats surface as an "unattributed" bucket, with the invariant `sum(endpoint allocations) + unallocated == org license spend`.
- [ ] **COST-06**: Disposed/retired assets are excluded from current book-value totals by default and included in historical purchase totals only behind an explicit filter — the same rule applied in the KPI and the cost view.
- [ ] **COST-07**: Every cost route requires an explicit tenant (a `platform-admin` context with no tenant returns 400), uses no `$lookup` or request-cache, and is covered by a mandatory two-tenant isolation test.
- [ ] **COST-08**: A "Costs" tab in the existing ITAM console (no new sidebar module or permission) shows the org summary and per-asset breakdown with a coverage banner, shared currency formatting, and export through the existing report registry.

## v2 Requirements

### Deferred

- **COST-F1**: Consumable and component cost fields and rollups.
- **COST-F2**: Display/selectable currency and FX (single implicit currency per tenant in v4.2).
- **COST-F3**: Idle-seat / renewal-cost forecasting and true total-cost-of-ownership.
- **COST-F4**: MSP cross-tenant cost rollup for platform operators.
- **ACC-F1**: ITAM/console *tab-level* permission gating (cost lives under `view:itam` in v4.2).
- **ACC-F2**: Guarding the remaining (non-priority) unguarded routers recorded in the gap ledger.

## Out of Scope

| Feature | Reason |
|---------|--------|
| New permission model / OPA / Casbin / CASL engine | Reuse the existing RBAC (`rbac_utils` / `db.roles`); the milestone aligns and hardens it, not replaces it |
| Guarding all ~188 catalogues this milestone | Priority groups + tracked gap ledger instead (decision D-4) — caps milestone size while closing the real exposure |
| User-RBAC guards on agent-authenticated `/api/agents/*` routes | Those use agent auth, not user permissions; guarding them with user RBAC would break telemetry |
| Persisted cost rollups / caching / background snapshot jobs | Compute at read time; a rollup cache keyed on tenant ContextVar leaks across tenants |
| Multi-currency / FX / chargeback | Single implicit currency per tenant for v4.2 |
| Rolling purchase-order / request money into cost totals | PO/request fields are float dollars vs asset integer cents — mixing units double-counts |
| Backend enforcement of tenant `enabledFeatures` | It is a UI-only gate today; changing that is out of scope (noted in the verification matrix) |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (pending roadmap) | | |

**Coverage:**
- v1 requirements: 17 total (ACC: 9, COST: 8)
- Mapped to phases: 0 (pending roadmapper)
- Unmapped: 17 ⚠️

---
*Requirements defined: 2026-10-12*
*Last updated: 2026-10-12 after milestone v4.2 definition*
