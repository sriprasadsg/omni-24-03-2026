# Phase 76: Catalogue Manifest & Backend Route Enforcement - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Phase Boundary

One shared manifest defines each left-nav catalogue once (required permission + backend route(s)) and is read by both `components/Sidebar.tsx` and the `App.tsx` view-permission lookup (the two divergent tables and the 9 mismatched views go away). The backend refuses (403) what the sidebar would hide for the priority route groups, a committed gap ledger records every router still unguarded, and deny-by-default tests fail on drift (backend route parity + frontend manifest/sidebar drift). Requirements: ACC-03, ACC-04, ACC-05.

**Not in this phase:** fail-closed sidebar behaviour, render-time view gate, no-access screen, landing view, permission refresh, "what can this role see" view (all Phase 77); persisted role editing; guards for the non-priority groups (ACC-F2, ledger only); ITAM tab-level gating (ACC-F1); backend enforcement of tenant `enabledFeatures` (out of scope for v4.2).

</domain>

<decisions>
## Implementation Decisions

### Guard scope
- **D-01:** Backend route guards land this phase for the routers behind three sidebar groups: **"Infrastructure & Assets"** (including ITAM), **"Management & Settings"** (users, roles, SSO/LDAP, settings, billing/finops), and **"Security (SecOps)"**. This is the milestone's priority list (Assets, ITAM, Settings, financial, identity, security-operations). Routers behind the other five groups (Dashboards & Insights, Observability, DevSecOps & Engineering, Governance & Compliance, Automation & Intelligence) are recorded in the gap ledger, not guarded.
- **D-02:** Agent-authenticated routes (`/api/agents/*` called by agents via `get_current_user_or_agent`) keep agent auth and get no user-permission guard; enrollment and heartbeat must keep working. Existing API-key callers on ITAM routers must keep working (role check first, then API-key scope narrowing — the existing `_scopes_allow` order).

### Permission semantics
- **D-03:** Read routes are guarded by the catalogue's `view:X`; write routes keep/require `manage:X`. For read guards, **holding `manage:X` satisfies `view:X`** (the same implication closure Phase 75 D-20 uses for the role-assignment ceiling). Writes still require `manage:X` itself. All checks go through the Phase 75 resolver (`rbac_service.effective_permissions` / `rbac_utils.verify_permission`), never a new table.

### Cost-field exposure
- **D-04:** Asset read routes (`/api/assets*`) stay readable with `view:assets`, but for a caller without `view:itam` the finance fields (purchase cost, book value and related purchase/finance fields) are **stripped from the response**. Callers with `view:itam` see them unchanged. This prepares the Phase 78 cost routes, which are gated by `view:itam`.

### Drift and new-router policy
- **D-05:** **Deny-by-default:** the backend route-parity test fails when an in-scope catalogue route is unguarded, **and** when any router has no permission guard and is not listed in the committed gap ledger. Adding a router therefore requires either a guard or a ledger entry with a stated reason.
- **D-06:** A frontend test fails when the sidebar and the manifest drift (e.g. a nav item with no manifest entry, or a manifest entry with no nav item).

### Claude's Discretion
- Manifest location and format (research suggested `shared/catalogue-access.json` plus a typed `catalogueAccess.ts` reader) and how Vite/vitest import it.
- Gap-ledger file format and location (research suggested `shared/catalogue-gaps.json`), and how each entry states its reason.
- Router-level vs route-level guard placement, and how guards are tagged so the parity test can read them.
- Re-measuring the baseline counts (researchers' ad-hoc counts disagreed: 50 vs 63 unguarded routers; 64 of 89 sidebar strings unenforced) before guarding.
- Which exact finance field names are stripped (D-04), as long as purchase cost and book value are covered.

### Reviewed Todos (not folded)
- "Fix stale capability-count assertions in integration.rs" (Rust agent tests) — matched on keywords only; unrelated to route guards.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and decisions
- `.planning/REQUIREMENTS.md` — ACC-03, ACC-04, ACC-05; out-of-scope table; ACC-F1/ACC-F2 deferrals.
- `.planning/ROADMAP.md` § "Phase 76" — goal and 5 success criteria.
- `.planning/research/SUMMARY.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` — manifest/parity/ledger design; Pitfalls 1, 2, 14, 16, 17.
- `.planning/phases/75-permission-resolver-single-source-of-truth/75-CONTEXT.md` — locked RBAC decisions (D-01..D-26), esp. D-20 closure.
- `.planning/phases/75-permission-resolver-single-source-of-truth/75-0*-SUMMARY.md` — what exists now: `backend/rbac_defaults.py`, resolver, `backend/role_assignment.py`, drift guard `test_no_second_permission_table`.
- `.planning/phases/75-permission-resolver-single-source-of-truth/75-REVIEW-DISPOSITION.md` — open items WR-04/WR-06 (not this phase).

### Code
- `components/Sidebar.tsx` (8 groups, 188 items, 89 permission strings) and `App.tsx` `viewPermissionMap` — the two tables the manifest replaces.
- `backend/router_registry.py` — router mounting; `backend/rbac_utils.py` `require_permission` / `require_super_admin`; `backend/rbac_service.py` `_scopes_allow` (API-key narrowing).
- `backend/tests/test_route_auth_baseline.py` — existing route-auth guard test to extend, not duplicate.
- `backend/authentication_service.py` `get_current_user_or_agent` — agent-auth routes to exclude.

</canonical_refs>

<code_context>
## Existing Code Insights

- Sidebar groups (`components/Sidebar.tsx`): Dashboards & Insights, Observability, Infrastructure & Assets, Security (SecOps), DevSecOps & Engineering, Governance & Compliance, Automation & Intelligence, Management & Settings.
- Nine views mismatch between Sidebar.tsx and `App.tsx` `viewPermissionMap`: agentCapabilities, jobs, llmops, persistenceDetection, sustainability, swarm, unifiedOps, vulnerabilityManagement, zeroTrustQuantum.
- `frontend fetchWithCache` already drops cached data on 403 (Phase 75 WR-08), so new 403s degrade cleanly in the UI.
- Phase 75 made enforcement and delivery share one resolver, so guarding a route with `view:X` matches exactly what `/me` tells the UI.

</code_context>

<specifics>
## Specific Ideas

- The parity test should name each offending router/route and the expected permission in its failure message, so a red CI run tells the developer exactly what to guard or ledger.

</specifics>

<deferred>
## Deferred Ideas

- Guards for the five non-priority sidebar groups — tracked by the gap ledger (ACC-F2).
- ITAM/console tab-level permission gating (ACC-F1).

</deferred>

---

*Phase: 76-catalogue-manifest-backend-route-enforcement*
*Context gathered: 2026-10-12*
