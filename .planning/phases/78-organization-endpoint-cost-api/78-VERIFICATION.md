---
phase: 78-organization-endpoint-cost-api
verified: 2026-11-17T05:35:00Z
status: human_needed
score: 6/6 must-haves verified
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
  - .planning/phases/78-organization-endpoint-cost-api/78-11-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-11-SUMMARY.md
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
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
covered_digest: "v3:sha256:ac144127dac0efb47fe448f07a7bf83752ae4c46c6ec924acecf8df3ab8b3a70"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "78-06 / UI-SPEC R3: ReportsPanel renders no result from the previous tenant after a switch, including a response that arrives after the switch (WR-01, closed by gap plan 78-11)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "After the user deploys (backend restart + UI publish), a Platform Owner opens ITAM with a tenant selected, then with none selected."
    expected: "KPI tile shows 'Not tracked' for a tenant with no cost data and a dollar value otherwise, 'Valued X of Y', the Select-a-tenant state when no tenant is chosen, and the Reports tab Run buttons are disabled with the note until a tenant is selected; switching tenants mid-run leaves no previous-tenant table."
    why_human: "Live rendering on the deployed UI. The deploy (backend restart, UI publish, git push) has not happened and belongs to the user. This is the Manual-Only row in 78-VALIDATION.md; no code gap is implied."
---

# Phase 78: Organization & Endpoint Cost API Verification Report

**Phase Goal:** A tenant user with ITAM view access can read the organization's total asset cost and each endpoint's cost, computed by the same function that feeds the ITAM KPI tile, and can never see another tenant's numbers.
**Verified:** 2026-11-17T05:35:00Z
**Status:** human_needed
**Re-verification:** Yes, after gap closure (plan 78-11)

## Verdict in one paragraph

The one gap from the previous report is closed and every truth now holds in committed HEAD. ReportsPanel has a request-sequence guard (`runSeq`) on all three async writers, the tenant-change effect bumps it and resets `running`, and the result block is gated on `resultIsCurrent`. I confirmed it by reading HEAD source, by running the guard's tests (4 frontend suites, 85 passed), and by re-running the full backend phase command (14 suites, 310 passed, 0 failed). The server-side goal was already verified and the backend files are unchanged since (diff `edbb1bb46..HEAD` touches no backend file; the phase backend files are clean in the working tree). The status is `human_needed` rather than `passed` only because one post-deploy live check remains, which is a user action. There is no code gap and no blocker.

## Re-verification: the closed gap

Previous gap: a pre-built run for tenant A that resolves after the Owner switches to tenant B was written into state and rendered under tenant B.

Evidence on committed HEAD (`git show HEAD:components/itam/ReportsPanel.tsx`):

- `runSeq = useRef(0)`; the tenant-change effect does `runSeq.current += 1; setRunning(false); setShowingPreview(false); setResult(null); setActiveKind(null); setActiveKey(null); setPage(1)`.
- `runPrebuilt`, `runSavedCustom` and `handlePreviewCustom` each take `const seq = ++runSeq.current`, drop a response or a failure when `seq !== runSeq.current` (no result write, no toast), and only clear `running` for the current seq.
- `runPrebuilt` still calls `runItamPrebuiltReport(key, targetPage, PAGE_SIZE, tenantId)`; prebuilt export still passes `tenantId`; saved custom runs, preview and custom export send no tenant argument (PROH-78-08 respected, no custom-report tenant handling was changed).
- Render gate: `(running || result) && resultIsCurrent`, with `resultIsCurrent = Boolean(activeKind && activeKey) || showingPreview`.
- Tests: `ITAMConsole.test.tsx` "a pre-built run for the previous tenant that resolves after the switch renders nothing" (holds the request, rerenders with tenant B, resolves, asserts no row, no title, no Export button, then a fresh run under B shows only B's rows with `tenantId` `t-2`). `ITAMReportsPanelStaleResponse.test.tsx` adds 7 tests: stale saved custom run, switch to no tenant mid-run, out-of-order runs, late failure with no toast, preview still renders and offers no export, stale preview after switch, same-tenant rerender keeps the result. Run by this verifier: `npx vitest run` on ITAMConsole, ITAMReportsPanelStaleResponse, ITAMReportsPanel and ITAMKpiPanel suites: 4 files, 85 tests passed.

Judgement on assumption A-78-19 (render gate is `activeKind && activeKey || showingPreview`, not the literal `activeKind && activeKey` from the previous report): accepted. The literal gate would have hidden every unsaved builder preview (Phase 72 D-02 deliberately sets both to null), a regression. The widened gate is safe for the gap's intent: `showingPreview` is reset in the tenant-change effect and on every run start, and is only set after the seq check passes, so a previous-tenant preview can never satisfy it. The gap's intent (no previous-tenant title, rows or export controls after a switch) is met, and a test pins both the preview rendering and its stale-drop.

## Goal Achievement

### Observable Truths (ROADMAP success criteria are the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/itam/costs/summary` returns purchase total + book value total + coverage; no-cost assets are null, never 0 | VERIFIED (regression check) | Backend unchanged since the prior verification; `test_itam_cost_endpoints.py` and `test_itam_cost_service.py` in the 310-pass re-run. |
| 2 | `/costs/assets` (paginated) and `/costs/assets/{id}` return per-asset purchase cost and book value, agent endpoints included via `agents.assetId` | VERIFIED (regression check) | `test_itam_cost_assets.py` passes in the re-run. |
| 3 | KPI tile, Asset value report and cost summary show identical figures for the same tenant, enforced by a parity test over a shared per-asset computation | VERIFIED (regression check) | `test_itam_cost_parity.py` passes in the re-run; `compute_asset_cost` remains the single per-asset function used by the KPI, report, custom builder and cost routes. |
| 4 | Disposed/retired excluded from current book value by default, counted in historical purchase totals only with an explicit filter, same rule in KPI and cost view | VERIFIED (regression check) | `test_itam_kpi_cost_rules.py`, `test_itam_report_cost_rules.py` pass in the re-run. |
| 5 | Every cost route: 403 without `view:itam`, 400 for platform-admin/no tenant, two-tenant isolation test proves A never sees B | VERIFIED (regression check) | `test_itam_cost_isolation.py` (through the real middleware) and `test_catalogue_slice_assets.py` pass in the re-run. |
| 6 | 78-06 (D-14 amended, UI-SPEC R3): after a tenant switch, ReportsPanel shows no result table/title/export from the previous tenant, including a response that arrives after the switch | VERIFIED | See "Re-verification: the closed gap". Guard present on HEAD, behavioural test passes (a named test that holds a request across the switch, so presence is not the only evidence). |

**Score:** 6/6 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_cost_service.py` | One shared computation, loaders, summary | VERIFIED | Unchanged, wired from routes, KPI, report, custom builder |
| `backend/itam_cost_endpoints.py` | 3 routes under `/api/itam/costs` | VERIFIED | Unchanged |
| `backend/itam_tenant_scope.py` | Shared resolver (D-13) | VERIFIED | Unchanged |
| KPI / report backend modules | Rewired onto shared computation | VERIFIED | Unchanged |
| `components/itam/ItamKpiPanel.tsx` | Not tracked / Valued X of Y / tenant follow, stale guard | VERIFIED | Suite passes |
| `components/itam/ReportsPanel.tsx` | Tenant threaded, disabled Run, reset on switch, stale-response guard | VERIFIED | Was PARTIAL; now guarded (above) |
| `src/__tests__/ITAMReportsPanelStaleResponse.test.tsx` | Guard tests | VERIFIED | 7 tests, pass |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| tenant-change effect | `runSeq` | `runSeq.current += 1` | WIRED |
| `runPrebuilt` | `runItamPrebuiltReport` | `(key, targetPage, PAGE_SIZE, tenantId)` kept verbatim | WIRED |
| result block | `resultIsCurrent` | `(running \|\| result) && resultIsCurrent` | WIRED |
| cost / KPI / report routes | `resolve_itam_tenant`, `_require_itam_viewer`, `compute_asset_cost` | unchanged, re-proven by tests | WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend phase command (14 suites) | `backend/venv/bin/python -m pytest <14 files> -q -p no:cacheprovider -rs` | 310 passed, 0 skipped, 102 s | PASS |
| Frontend guard + console + KPI suites | `npx vitest run src/__tests__/ITAMConsole.test.tsx ITAMReportsPanelStaleResponse.test.tsx ITAMReportsPanel.test.tsx ITAMKpiPanel.test.tsx` | 4 files, 85 passed | PASS |
| Orchestrator gates (not re-run by me) | `npm run build`; `npx vitest run src/__tests__` | exit 0; 135 files / 2,242 tests passed (reported) | accepted as reported |

### Probe Execution

Step 7c: SKIPPED (the phase declares no probe scripts).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| COST-01 | 78-01, 78-04, 78-05, 78-08, 78-09, 78-10 | Same per-asset computation as the KPI tile, parity-tested | SATISFIED | Truth 3 |
| COST-02 | 78-01, 78-02, 78-09, 78-10 | Org summary with coverage, null never 0 | SATISFIED | Truth 1 |
| COST-03 | 78-03, 78-10 | Per-asset cost list + detail via `agents.assetId` | SATISFIED | Truth 2 |
| COST-06 | 78-04, 78-05, 78-08, 78-09, 78-10 | Disposed/retired rule across KPI and cost view | SATISFIED | Truth 4 |
| COST-07 | 78-01, 78-06, 78-07, 78-08, 78-10, 78-11 | Explicit tenant, no `$lookup`/cache, two-tenant isolation test; UI reset now guarded | SATISFIED | Truths 5 and 6 |

All five IDs appear in plan frontmatter and in REQUIREMENTS.md. No orphaned requirement (COST-04/05 are Phase 79, COST-08 Phase 80). REQUIREMENTS.md currently shows all five as "Gaps Found" / Pending after the earlier revert; flipping them back to Complete is the orchestrator's completion step, not edited here.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| phase files | - | TBD/FIXME/XXX scan on ReportsPanel and the new test file | none | clean |
| `components/itam/ReportsPanel.tsx` | 102-118, 220-223 | WR-04: `result` and `activeKind/activeKey` written at different times; a failed run B after success A shows A's rows under B's export target | Warning | Within one tenant only: a tenant switch clears all three, so this is not a cross-tenant leak and does not falsify any must-have. Real wrong-export-target defect, worth a follow-up. |
| `components/itam/ReportsPanel.tsx` | 205-218 | IN-05: an export started before a switch still downloads and keeps `exportingFormat` set | Info | User-initiated, Owner-only, not a rendered result; PROH-78-07 is about rendered title/rows/controls. |
| `components/itam/ITAMConsole.tsx` | 81-82 | IN-04 (still open): `needsTenant` keyed to Super Admin role name only | Info | Other platform tiers fall through to a toast |
| `backend/itam_reporting_prebuilt.py` | 128-134 | IN-02: unnormalised malformed status | Info | One bad document 500s the report |

### Review items carried (none blocks the goal)

- WR-02 (custom report routes keep `current_user.tenant_id`): still outside the phase (A-78-17, A-78-21); awaits the user's accept-risk or follow-up decision. 78-SECURITY.md has no accepted-risk row for it; recommend recording one.
- WR-03, IN-01, IN-03: unchanged, documentation/contract cleanups.
- WR-04 and IN-05 are new from the incremental review of 78-11; both are outside the roadmap contract and outside the tenant-leak truth as shown above. Recommend a small follow-up gap or backlog item for WR-04 (store the shown result with its identity).

### Human Verification Required

#### 1. Live check on the deployed build

**Test:** After the user restarts the backend and publishes the UI, open ITAM as a Platform Owner with a tenant selected and again with none; start a pre-built report and switch tenant while it loads.
**Expected:** KPI tile shows "Not tracked" vs a dollar value, "Valued X of Y", the Select-a-tenant state; Reports Run buttons disabled with the note when no tenant; after a mid-run switch no previous-tenant title, rows or export buttons appear.
**Why human:** Needs the deployed system; deploy and publish are the user's actions. The automated evidence above already covers the code paths.

### Gaps Summary

None. Gap plan 78-11 closed the only gap. The phase goal and all five requirements are verified in code and by tests; the only open item is the user-owned post-deploy live check.

---

_Verified: 2026-11-17T05:35:00Z_
_Verifier: Claude (gsd-verifier)_
