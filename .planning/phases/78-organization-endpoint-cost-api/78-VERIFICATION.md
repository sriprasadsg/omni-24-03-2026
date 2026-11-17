---
phase: 78-organization-endpoint-cost-api
verified: 2026-11-17T01:20:00Z
status: gaps_found
score: 5/6 must-haves verified
covered_files:
  - .planning/phases/78-organization-endpoint-cost-api/78-01-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-01-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-02-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-02-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-03-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-03-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-04-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-04-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-05-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-05-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-06-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-06-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-07-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-07-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-08-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-08-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-09-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-09-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-10-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-10-SUMMARY.md
  - backend/itam_cost_endpoints.py
  - backend/itam_cost_service.py
  - backend/itam_kpi_endpoints.py
  - backend/itam_reporting_endpoints.py
  - backend/itam_reporting_filters.py
  - backend/itam_reporting_kpis.py
  - backend/itam_reporting_prebuilt.py
  - backend/itam_tenant_scope.py
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportsPanel.tsx
covered_digest: "v3:sha256:a5178f1c9288f65cdf9eb4f7836b52a1769b441c1b8218e5a91b7b0fd647781b"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "78-06 / UI-SPEC R3: after the Owner switches tenant, ReportsPanel renders no result table, title or export buttons from the previous tenant (T-78-15 recorded closed)"
    status: failed
    reason: "runPrebuilt awaits runItamPrebuiltReport(..., tenantId) and then calls setResult(r) unconditionally. The tenant-change effect clears result/activeKind/activeKey/page but not running, and cannot cancel an in-flight request. A response issued for tenant A that returns after the switch to tenant B is written into state and rendered (the block renders on (running || result), title from result.title, table from result.rows) under tenant B. Export is hidden only because canExport needs activeKind. No test covers a response that arrives after a switch. Confirmed on committed HEAD (git show HEAD:components/itam/ReportsPanel.tsx has no sequence/cancel guard). This is the same defect as 78-REVIEW WR-01."
    artifacts:
      - path: "components/itam/ReportsPanel.tsx"
        issue: "runPrebuilt (lines ~92-107) and runSavedCustom have no stale-response guard; tenant-change effect (~81-90) does not reset running"
    missing:
      - "Request sequence counter (useRef) bumped in the tenant-change effect; runPrebuilt/runSavedCustom drop a response whose seq is not current and only clear running for the current seq"
      - "Reset running in the tenant-change effect; require activeKind && activeKey for the result block"
      - "ITAMConsole test: resolve a pre-built run for tenant A after rerendering with tenant B and assert no title/rows render"
---

# Phase 78: Organization & Endpoint Cost API Verification Report

**Phase Goal:** A tenant user with ITAM view access can read the organization's total asset cost and each endpoint's cost, computed by the same function that feeds the ITAM KPI tile, and can never see another tenant's numbers.
**Verified:** 2026-11-17T01:20:00Z
**Status:** gaps_found
**Re-verification:** No, initial verification

## Verdict in one paragraph

The server-side goal is achieved and independently re-proven: all five ROADMAP success criteria and all five requirement IDs (COST-01, 02, 03, 06, 07) hold in the code, the 14-suite phase command passes (310 passed, 0 skipped, re-run by this verifier: 82 s) and the two frontend suites pass (50). One plan-level UI truth fails (78-06 R3: ReportsPanel can render a stale previous-tenant report after a tenant switch, WR-01). It is Owner-only and a presentation race, not an authorization leak, so it does not touch the roadmap contract, but it is a falsified must-have and a claim the security register marks closed, hence gaps_found with one narrow gap. WR-02 is judged out of scope (see below).

## Goal Achievement

### Observable Truths (ROADMAP success criteria are the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/itam/costs/summary` returns purchase total + book value total + coverage; no-cost assets are null, never 0 | VERIFIED | `itam_cost_endpoints.get_cost_summary` -> `compute_tenant_costs` -> `summarize_cost_rows`; `_total()` returns `{cents: None, hasData: False}` when no contributor; `compute_asset_cost` sets `bookValueCents=None` plus exactly one reason; coverage has total/priced/valued/reasons/flags. Tests: `test_itam_cost_endpoints.py` (summary tracer on real Mongo, empty tenant), `test_itam_cost_service.py` (13-row golden table, one-reason invariant) pass. |
| 2 | `/costs/assets` (paginated) and `/costs/assets/{id}` return per-asset purchase cost and book value, agent endpoints included via `agents.assetId` | VERIFIED | `list_cost_assets` computes whole tenant set, sorts (D-08), then `paginate()`; `load_agents_by_asset` queries `{"tenantId", "assetId": {"$in": ids}}`, never hostname or the asset's own agentStatus; detail route returns the row or the same 404 for unknown and foreign ids. `test_itam_cost_assets.py` (25) passes. |
| 3 | KPI tile, Asset value report and cost summary show identical figures for the same tenant, enforced by a parity test over a shared per-asset computation + golden table | VERIFIED | All three call `itam_cost_service.compute_asset_cost` (grep: `itam_reporting_kpis.py:88`, `itam_reporting_prebuilt.py:132`, `itam_cost_service.compute_tenant_costs`); custom builder Book Value also routed through it (`itam_reporting_filters.py:279`); depreciation stays `itam_finance_service.compute_book_value` (unchanged). `test_itam_cost_parity.py` (7 tests, real Mongo, fixed clock: KPI = report = summary = list, row-for-row, per-asset book-value route) passes. Note: the tile shares the per-asset function with the cost routes, not `compute_tenant_costs` itself; that matches the goal wording ("same function") and CONTEXT D-04. |
| 4 | Disposed/retired excluded from current book value by default, counted in historical purchase totals only with an explicit filter, same rule in KPI and cost view | VERIFIED | `INACTIVE_STATUSES` is the one set used by `compute_tenant_costs` (default drop; `includeDisposed=true` keeps them with `bookValueCents=None`, reason disposed/retired), by the KPI (`itam_reporting_kpis.py` filters `in_scope`) and by the report (`itam_reporting_prebuilt.py`). `test_itam_kpi_cost_rules.py` (11), `test_itam_report_cost_rules.py` (16), `test_lifecycle_rule_across_surfaces` pass. Minor: IN-02, the report's pre-filter does not normalise a malformed (list/dict) status the way `compute_asset_cost` does (report 500 on that one bad document). Data-quality edge, not a rule violation. |
| 5 | Every cost route: 403 without `view:itam`, 400 for platform-admin/no tenant, two-tenant isolation test proves A never sees B | VERIFIED | Every cost route depends on the imported `_require_itam_viewer` and calls `resolve_itam_tenant` first (400 for empty/platform-admin before any DB read; header honoured only for session + Owner tier); loaders `require_tenant` and carry explicit `tenantId` filters, so the wrapper's platform-admin skip cannot blend; no `$lookup`, no cache decorator (grep clean). `test_itam_cost_isolation.py` (29 tests through the real TenantMiddleware and real tokens: A never sees B on summary, list, detail, KPI, report run/export; foreign detail id 404 identical to unknown; header spoof by tenant admin ignored; viewer without view:itam 403; Billing 403; Support 400/403; 10x8 concurrent-request rounds) passes. API-key scope narrowing covered in `test_catalogue_slice_assets.py` (8) with the router mounted behind `ITAM_API_KEY_GUARD` (`catalogue_mounts_assets.py:56`) and registered in `router_registry.py:121`. |
| 6 | 78-06 (D-14 amended, UI-SPEC R3): after a tenant switch, ReportsPanel shows no result table/title/export from the previous tenant | FAILED | Synchronous reset exists and is tested, but an in-flight run for tenant A resolves after the switch and `setResult(r)` renders it under tenant B (no guard; see gap in frontmatter). The KPI tile (the primary D-14 deliverable) does have the guard (`cancelled` flag, `ItamKpiPanel.tsx:100-121`) and is fine. |

**Score:** 5/6 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_cost_service.py` (338 lines) | One shared computation, loaders, duplicate marks, summary | VERIFIED | Substantive, wired from routes, KPI, report, custom builder; money in integer cents; imports no web framework symbol |
| `backend/itam_cost_endpoints.py` | 3 routes under `/api/itam/costs` | VERIFIED | Registered in `router_registry.py`, mounted behind API-key guard; generic 500 detail |
| `backend/itam_tenant_scope.py` | Shared resolver (D-13) | VERIFIED | Used by cost, KPI and pre-built report run/export routes; writes ambient tenant back |
| `backend/itam_kpi_endpoints.py`, `itam_reporting_kpis.py`, `itam_reporting_prebuilt.py`, `itam_reporting_filters.py` | Rewired onto shared computation | VERIFIED | grep confirms calls to `compute_asset_cost`; no remaining inline `compute_book_value` loop in them |
| `components/itam/ItamKpiPanel.tsx` | Not tracked / Valued X of Y / tenant follow / Select-a-tenant | VERIFIED | Stale-response guard present; vitest 50 pass |
| `components/itam/ReportsPanel.tsx` | Tenant threaded, disabled Run, reset on switch | PARTIAL | Threaded and reset on switch, but no stale-response guard (gap) |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| cost routes | `_require_itam_viewer` | import from `itam_asset_endpoints` (not copied) | WIRED |
| cost / KPI / report run+export routes | `resolve_itam_tenant` | first statement of each body | WIRED |
| KPI, report, custom builder Book Value, cost routes | `compute_asset_cost` | direct call | WIRED |
| `compute_asset_cost` | `compute_book_value` | unchanged finance function | WIRED |
| agent join | `agents.assetId` | `$in` over assetIds, tenant-filtered | WIRED |
| ITAMConsole / App | ItamKpiPanel / ReportsPanel | tenantId, needsTenant props | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| cost summary / list | rows, totals | one projected `assets` find + `asset_models` `$in` + `agents` `$in`, Python loop | Yes (real-Mongo tests) | FLOWING |
| KPI tile | totalBookValueCents | same per-asset function over tenant assets | Yes | FLOWING |
| Asset value report | Book Value column | same | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase command, 14 suites | `backend/venv/bin/python -m pytest <14 files> -q -p no:cacheprovider -rs` | 310 passed, 0 skipped, 82.18 s | PASS |
| Frontend suites | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | 50 passed | PASS |
| Stale-response test for ReportsPanel | grep `stale/race/in-flight` in ITAMConsole.test.tsx | none exist | MISSING (this is the gap) |

### Probe Execution

Step 7c: SKIPPED (the phase declares no probe scripts).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| COST-01 | 78-01, 78-04, 78-05, 78-08, 78-09, 78-10 | Same per-asset computation as the KPI tile, parity-tested | SATISFIED | SC3 evidence; REQUIREMENTS.md marks Complete |
| COST-02 | 78-01, 78-02, 78-09, 78-10 | Org summary with coverage, null never 0 | SATISFIED | SC1 evidence |
| COST-03 | 78-03, 78-10 | Per-asset cost list + detail, agents via `agents.assetId` | SATISFIED | SC2 evidence (WR-03 is a marker inconsistency in an edge case, not a figure error) |
| COST-06 | 78-04, 78-05, 78-08, 78-09, 78-10 | Disposed/retired rule across KPI and cost view | SATISFIED | SC4 evidence |
| COST-07 | 78-01, 78-06, 78-07, 78-08, 78-10 | Explicit tenant, no `$lookup`/cache, two-tenant isolation test | SATISFIED on the server (SC5). The related UI reset (plan 78-06, listed under COST-07) has the gap above. | |

All five IDs appear in plan frontmatter and in REQUIREMENTS.md traceability (Phase 78, Complete). No orphaned requirement: REQUIREMENTS.md maps no other ID to Phase 78 (COST-04/05 are Phase 79, COST-08 Phase 80).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase files) | - | TBD/FIXME/XXX/TODO/HACK scan | none | clean |
| `components/itam/ReportsPanel.tsx` | ~92-107, ~126-140 | unguarded async `setResult` | Blocker (the gap) | stale previous-tenant report can render |
| `backend/itam_reporting_prebuilt.py` | 128-134 | `not in INACTIVE_STATUSES` on an unnormalised status | Info (IN-02) | one malformed doc 500s the report |
| `backend/itam_cost_service.py` | 130-141 | salvage > cost gives book value > cost | Info (IN-03) | no reason code; Phase 59 formula deliberately unclamped |

### The two review warnings, decided explicitly

**WR-01 (ReportsPanel stale response): INSIDE the phase, counted as the gap above.** It falsifies plan 78-06's "UI partial" truth and UI-SPEC R3, which the user approved into scope when D-14 was amended 2026-11-16, and it makes T-78-15 ("closed") overstated. It is not an authorization breach: only the Platform Owner can switch tenant, and that role is entitled to see tenant A's data; the harm is tenant-A figures shown under tenant-B's label. It does not affect any ROADMAP success criterion, so the server-side goal stands. Fix is about 10 lines plus one test. Gating this on the UI is a judgement call; if the user prefers, they can accept it as an override (the "this looks intentional" test does not apply, since no alternative implementation exists).

**WR-02 (custom report routes still use `current_user.tenant_id`): OUTSIDE the phase, not a gap.**
- Requirements and SCs name cost routes, the KPI and the Asset value report. CONTEXT D-13 lists exactly "the cost routes, the KPI route and the Asset value report run/export routes". Custom reports are none of those.
- Plan 78-05 states it as a locked assumption (A-78-17): custom report routes keep their current tenant handling, "flagged for the user as a follow-up candidate". 78-05-SUMMARY repeats it.
- The goal's subject is "a tenant user". A tenant user is still isolated on custom reports by the tenant wrapper (their own tenant id), so tenant A never sees tenant B there. The blending only arises for a Platform Owner session whose own tenant is `platform-admin`; that behaviour pre-dates the phase (the phase only swapped which function computes the Book Value column).
- Open item to carry, WARNING not a blocker: 78-SECURITY.md has no accepted-risk row for it (the review asked for one), so the Owner view currently differs between surfaces (cost/KPI/pre-built = 400 without tenant, custom = blended). Recommend either an AR-78-0x entry or a follow-up task; Phase 80 (Costs tab) does not cover it, so it is not deferred.

WR-03 (detail vs list duplicate markers when the partner is disposed/retired) and IN-01, IN-03, IN-04: confirmed as described, none contradicts a success criterion or a requirement; WARNING-level documentation/contract cleanups. IN-01 (bogus `X-Tenant-ID` from an Owner accepted, empty 200 figures, export record under a nonexistent tenant) is Owner-only and exposes no real tenant data.

### Human Verification (not counted in status, since gaps_found takes precedence)

1. Live ITAM KPI tile check from 78-VALIDATION.md Manual-Only: the live deploy (backend restart, UI publish) has not happened. After deploy, an Owner opens ITAM with a tenant selected and confirms "Not tracked" vs a dollar value, "Valued X of Y", and the Select-a-tenant state; this belongs to the user.

### Gaps Summary

One gap, narrow: add a request-sequence guard to `ReportsPanel` (`runPrebuilt`, `runSavedCustom`), reset `running` on tenant change, and add the stale-response test. Everything on the server, which carries the goal and all five requirements, is verified by code reading and by a re-run of the phase test command. WR-02 should be recorded as an accepted gap or a follow-up in 78-SECURITY.md, not planned into this phase.

---

_Verified: 2026-11-17T01:20:00Z_
_Verifier: Claude (gsd-verifier)_
