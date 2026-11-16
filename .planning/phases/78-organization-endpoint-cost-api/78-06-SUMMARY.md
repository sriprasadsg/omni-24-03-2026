---
phase: 78-organization-endpoint-cost-api
plan: 06
subsystem: ui
tags: [itam, reports, kpi, tenant-isolation, react, vitest]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: "78-02 ItamKpiPanel tenantId / needsTenant / onGoToTenants props, fetchItamKpis(tenantId), ITAM_KPI_COPY.reportsSelectTenantNote; 78-04 KPI route 400 for the platform context; 78-05 pre-built report run/export on resolve_itam_tenant"
provides:
  - "App.tsx passes viewingTenantId and a manage:tenants-gated onGoToTenants to ITAMConsole"
  - "ITAMConsole tenantId / onGoToTenants props and derived needsTenant, forwarded to ItamKpiPanel and ReportsPanel"
  - "runItamPrebuiltReport(reportKey, page, pageSize, tenantId?) and generateItamReport(kind, reportKey, format, tenantId?) sending X-Tenant-ID"
  - "ReportsPanel tenantId / needsTenant props, DOM id itam-reports-select-tenant-note, disabled Run Report, reset on tenant change"
affects: [78-09, phase-80]

actuals:
  tokens: 5700
  tasks: 2
  commits: 4
plan_head_before: 556d0f273f848c9818934ac06b5975cf2968bdbb
plan_head_after: 2a7a4e41b2c3bafba5c07fc1e5e29616aa70c43d

tech-stack:
  added: []
  patterns:
    - "Ref-guarded tenant-change reset: effect compares against a useRef of the previous tenantId so first mount (drill-down run) is never cleared"
    - "needsTenant = isSuperAdminView && !tenantId computed once in the console body and passed down"

key-files:
  created: []
  modified:
    - App.tsx
    - components/itam/ITAMConsole.tsx
    - components/itam/ReportsPanel.tsx
    - services/apiService.ts
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "Custom reports are untouched: handleExport passes tenantId only when activeKind is 'prebuilt'; saved custom runs and the builder send nothing new"
  - "runPrebuilt always passes tenantId as the fourth argument (undefined for tenant users), so the existing drill-down test's expected call gained a trailing undefined"

requirements-completed: [COST-07]

coverage:
  - id: D1
    description: "The Platform Owner's selected tenant reaches the KPI request; no tenant shows Select a tenant and sends no request; Go to Tenants only with a handler; tenant user unchanged"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#a Platform Owner's selected tenant reaches the KPI request on the Reports tab"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#a Platform Owner with no tenant selected sees the Select a tenant block and no KPI request is sent"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pre-built runs and exports carry the selected tenant; saved custom runs and exports carry none"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#runs and exports a pre-built report for the selected tenant"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#runs and exports a saved custom report without any tenant argument"
        status: pass
    human_judgment: false
  - id: D3
    description: "With no tenant, Run Report is disabled and described by the visible role=status note; a tenant user sees enabled buttons and no note"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#disables Run Report with a described status note when a Platform Owner has no tenant"
        status: pass
    human_judgment: false
  - id: D4
    description: "A tenant change (to another tenant or to none) clears the result table, title and export buttons; first-mount drill-down is kept"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#clears the previous tenant's result when the tenant changes, and when none is selected"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#does not clear a drill-down run started on first mount"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live behaviour after backend restart and UI publish: Total Asset Value tile equals the cost summary's bookValueTotal for the selected tenant"
    requirement: COST-07
    verification: []
    human_judgment: true
    rationale: "Live deploy (backend restart, UI publish) is the user's action; the automated tests use mocked API responses"

duration: 5 min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 06: Tenant threading into the ITAM Reports tab Summary

**The Platform Owner's selected tenant now flows App.tsx -> ITAMConsole -> ItamKpiPanel and ReportsPanel: pre-built runs and exports send X-Tenant-ID, Run Report is disabled with a one-line reason when no tenant is selected, and a tenant switch clears the previous tenant's report table.**

## Accomplishments

- Task 1 (tracer): `App.tsx` itam case passes `tenantId={viewingTenantId}` and `onGoToTenants` (only with `manage:tenants`, opens Tenant Management). `ITAMConsole` computes `needsTenant = isSuperAdminView && !tenantId` and forwards `tenantId`, `needsTenant`, `onGoToTenants` to `ItamKpiPanel`.
- Task 2: `runItamPrebuiltReport` and `generateItamReport` take a trailing `tenantId?` and pass it to `authFetch`. `ReportsPanel` passes it on pre-built runs, paging and exports (custom reports unchanged), renders the `role="status"` note `#itam-reports-select-tenant-note` under the Pre-built Reports heading when `needsTenant`, disables every pre-built Run Report button with `aria-describedby`, and resets result/activeKind/activeKey/page when `tenantId` differs from the previous value (never on first mount).

## TDD

- RED `5959922ce` (Task 1): 3 of 4 new tests failed on the planned assertions (`fetchItamKpis` not called with `'t-1'`; no Select block; no Go to Tenants button). The fourth (tenant user: `fetchItamKpis(undefined)`) already held and pins unchanged behaviour. No import or fixture faults.
- GREEN `3e11506d3`: 44 passed (ITAMConsole + ITAMKpiPanel).
- RED `79055015f` (Task 2): 5 of 6 new tests failed on the planned assertions (missing fourth argument, Run not disabled, stale table kept). The custom-report test already held (unchanged behaviour, regression pin).
- GREEN `2a7a4e41b`: full frontend suite 134 files / 2234 tests passed; `npm run build` exit 0.
- Tracer gate: Task 1 verify (ITAMConsole + ITAMKpiPanel, 44 passed) was green at commit; Task 2 tests extended the same file and the suite passed in full before expansion was committed.
- The classifier `tdd-red-evidence` was not run; this is not a `type: tdd` plan.
- No REFACTOR commit.

## Task Commits

1. Task 1 RED: `5959922ce` test(78-06)
2. Task 1 GREEN: `3e11506d3` feat(78-06) (App.tsx staged hunk-only, ITAMConsole.tsx)
3. Task 2 RED: `79055015f` test(78-06)
4. Task 2 GREEN: `2a7a4e41b` feat(78-06) (apiService.ts, ReportsPanel.tsx staged hunk-only, ITAMConsole.tsx, test fixes)

## User hunks (still unstaged in the working tree)

Staged with the save-patch / reverse-apply / update-index procedure (no fuzz; two hunks applied with a line offset only). After the last commit `git diff --cached` is empty and `git diff` still shows:

- `App.tsx`: user diff intact (`handleSetUserPassword` present in the unstaged diff; the staged diff had 0).
- `components/itam/ReportsPanel.tsx`: the removed `// eslint-disable-next-line react-hooks/exhaustive-deps` line (HEAD keeps it, count 1).
- `services/apiService.ts`: the `setUserPassword` hunk (present in the unstaged diff).
- `src/__tests__/ITAMConsole.test.tsx`: the removed `// eslint-disable-next-line no-bitwise` line (HEAD keeps it, count 1).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing drill-down test expected a three-argument call**
- **Found during:** Task 2 GREEN
- **Issue:** `clicking a KPI tile sets reportFocus...` asserted `runItamPrebuiltReport` called with `('asset_value', 1, 50)`; the plan's required call shape `runItamPrebuiltReport(key, targetPage, PAGE_SIZE, tenantId)` now passes a fourth `undefined` for a tenant user, and vitest treats the argument lists as different.
- **Fix:** expectation changed to `('asset_value', 1, 50, undefined)`. Behaviour unchanged.
- **Files modified:** src/__tests__/ITAMConsole.test.tsx
- **Commit:** 2a7a4e41b

**2. [Rule 1 - Bug] My own negative heading assertion matched the pre-built card title**
- **Found during:** Task 2 GREEN
- **Issue:** `queryByRole('heading', { name: 'Asset Value' })` also matches the card's h4, so the clear test failed for a test reason, not a product reason.
- **Fix:** scoped the assertion to `level: 3` (the result title).
- **Commit:** 2a7a4e41b

**Total deviations:** 2 auto-fixed (both test-side). **Impact:** none on product behaviour.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-78-15 mitigated (ref-guarded reset, rerender tests for another tenant and for none); T-78-16 mitigated (Run buttons disabled with needsTenant; the 78-05 resolver 400s regardless).

## Issues Encountered

None. Line counts: ReportsPanel.tsx 402, ITAMConsole.tsx 201 (both under 500).

## Next Phase Readiness

The console side of D-13/D-14 is complete. Live check (human): after the user restarts the backend and publishes the UI, sign in as Platform Owner, open ITAM > Reports with no tenant (Select block, disabled Run buttons with note), then open a tenant and confirm the Total Asset Value tile matches `GET /api/itam/costs/summary` for that tenant.

## Self-Check: PASSED

Files found: App.tsx, components/itam/ITAMConsole.tsx, components/itam/ReportsPanel.tsx, services/apiService.ts, src/__tests__/ITAMConsole.test.tsx. Commits 5959922ce, 3e11506d3, 79055015f, 2a7a4e41b present on branch npx.
