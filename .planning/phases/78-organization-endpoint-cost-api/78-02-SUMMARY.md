---
phase: 78-organization-endpoint-cost-api
plan: 02
subsystem: ui
tags: [itam, kpi, tenant-isolation, react, vitest, asset-value]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: "78-01 TENANT_REQUIRED_DETAIL (400 detail starting 'Select a tenant'); 78-04 (not yet run) emits valuedCount / inScopeAssetCount and null book value"
provides:
  - fetchItamKpis(tenantId?) sending X-Tenant-ID through authFetch
  - ItamAssetValueKpi.valuedCount / inScopeAssetCount optional fields
  - ITAM_KPI_COPY exported constant (consumed by ReportsPanel in 78-06)
  - ItamKpiPanel tile states (Not tracked, Valued x of y, excluded, No active assets), Select-a-tenant block, tenant-change reset
affects: [78-03, 78-06, 78-09, phase-80]

actuals:
  tokens: 12500
  tasks: 2
  commits: 4
plan_head_before: 7f58affa67018ada6da341647e909ad8dd8aefba
plan_head_after: 2ff6c20e0b340726022bcb650d2606809f30ca19

tech-stack:
  added: []
  patterns:
    - "Fetch effect clears data/failed/rejected first, then requests; a per-run cancelled flag drops stale responses"
    - "Server 400 detail is only regex-matched (/^Select a tenant/i), never rendered"
    - "New tile strings in one exported English constant (ITAM_KPI_COPY), not itamI18n"

key-files:
  created: []
  modified:
    - services/apiService.ts
    - components/itam/ItamKpiPanel.tsx
    - src/__tests__/ITAMKpiPanel.test.tsx

key-decisions:
  - "Select block returns early after all hooks, so hook order is stable across needsTenant/tenantRejected"
  - "aria-describedby is set only when the summary element exists (not loading, not failed, hasData), so it never points at a missing id"
  - "Tenant-change reset behavior was already delivered by Task 1's effect change; Task 2 added the tests that prove it (they were green at RED)"

patterns-established:
  - "KpiTile describedBy prop for tiles whose aria-label would otherwise hide their figure"

requirements-completed: [COST-02, COST-07]

coverage:
  - id: D1
    description: "A null book value renders 'Not tracked' (never $0) with 'Valued x of y assets', singular for 1, and an older response still renders"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#a null book value renders \"Not tracked\" and \"Valued 0 of 12 assets\", never $0"
        status: pass
    human_judgment: false
  - id: D2
    description: "The selected tenant reaches the KPI request as fetchItamKpis(tenantId)"
    requirement: COST-02
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#passes the tenantId prop to fetchItamKpis, and undefined when none is given"
        status: pass
    human_judgment: false
  - id: D3
    description: "Excluded line, No active assets state, and the accessible description of the Total Asset Value tile"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#shows the excluded line for disposed or retired assets, plural and singular, and none when counts match"
        status: pass
    human_judgment: false
  - id: D4
    description: "needsTenant or a 'Select a tenant' rejection shows the role=status block with no request; Go to Tenants only with a handler"
    requirement: COST-02
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#needsTenant replaces the grid with a Select a tenant status block and sends no request"
        status: pass
    human_judgment: false
  - id: D5
    description: "A tenant change clears the previous figure, shows Loading, and a late response for the old tenant is never rendered"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#a response for the older tenant that arrives after the switch is never rendered"
        status: pass
    human_judgment: false
  - id: D6
    description: "A $9,999,999,999 figure and 5-digit counts fit or wrap at 320px (backstop)"
    requirement: COST-07
    verification: []
    human_judgment: true
    rationale: "Overflow at 320px is a layout judgment jsdom cannot measure; lines are short wrapping text with no truncate class (asserted), but the real width needs a browser."

duration: 6 min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 02: ITAM Total Asset Value Tile Summary

**Total Asset Value tile now renders the server's null book value as "Not tracked" with a "Valued x of y assets" line, follows the selected tenant via X-Tenant-ID, and shows a "Select a tenant" state instead of a blended or failed tile.**

## Accomplishments

- `fetchItamKpis(tenantId?)` passes `{ tenantId }` to `authFetch`; `ItamAssetValueKpi` gained optional `valuedCount` and `inScopeAssetCount` (D-13, D-14, UI-SPEC R2).
- Tile states per UI-SPEC section 2: figure or neutral gray "Not tracked", Valued line (singular for 1, falls back to 0 / assetCount for an older response), not-tracked hint, excluded line, "No active assets". The old "{n} assets" line is gone; the pie still plots every status.
- Select-a-tenant block (`role="status"`, no icon, `max-w-prose` body, "Go to Tenants" only with a handler) for `needsTenant` (no request sent) and for a rejection matching `/^Select a tenant/i`.
- Tenant change clears figures and shows Loading before the new request; stale responses are dropped by the per-run `cancelled` flag (T-78-06).
- Total Asset Value button is described by `#itam-kpi-asset-value-summary` (figure and lines), only when that element is rendered.

## TDD

- RED (985b8d95c, a33d1ed95): target tests failed on the planned assertions (missing "Not tracked", "Valued ..." text, `fetchItamKpis` not called with 't-1', no `role="status"` block, no `aria-describedby`; the two needsTenant tests failed because the unmodified panel still called `fetchItamKpis`, whose mock returned undefined). Semantic assessment: every failure traced to missing behavior, no import/syntax/fixture faults. The format classifier (`tdd-red-evidence`) was not run; this is not a `type: tdd` plan.
- GREEN (664007784, 2ff6c20e0): 23/23 tests pass.
- Two Task 2 tenant-reset tests were already green at RED because Task 1's effect change (dependency on tenantId, clear before request) delivered that behavior; they are kept as regression proof of T-78-06.
- No REFACTOR commit.

## Task Commits

1. Task 1 RED: `985b8d95c` test(78-02)
2. Task 1 GREEN: `664007784` feat(78-02) (apiService.ts staged hunks-only)
3. Task 2 RED: `a33d1ed95` test(78-02)
4. Task 2 GREEN: `2ff6c20e0` feat(78-02)

## Verification

- `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx`: 23 passed.
- `npx vitest run src/__tests__/ITAMConsole.test.tsx`: 17 passed (unchanged, still green).
- `npm run build`: exit 0.
- Acceptance greps: `ITAM_KPI_COPY` 1, `role="status"` 1, `itam-kpi-asset-value-summary` 2, `/^Select a tenant/i` 1, `fetchItamKpis = async (tenantId` 1; ItamKpiPanel.tsx is 295 lines.
- apiService.ts staging check: `git diff --cached` for it contained 0 `setUserPassword` before the Task 1 commit; after the commit `git diff -- services/apiService.ts` still shows the user's `setUserPassword` hunk (10 lines) unstaged in the working tree.

## Deviations from Plan

None - plan executed exactly as written. (Task 1 also placed the `itam-kpi-asset-value-summary` wrapper element, which the plan assigned to Task 2; Task 2 added the `describedBy` wiring.)

## Issues Encountered

None.

## Notes for Later Plans

- `components/itam/ReportsPanel.tsx` showed as modified in the working tree before and after this plan (not touched here); 78-06 owns it.
- `ITAMConsole` does not yet pass `tenantId` / `needsTenant` / `onGoToTenants` to the panel; that wiring is a later plan (UI-SPEC R4). Until then the panel behaves as before for tenant users.
- 78-04 must emit `valuedCount`, `inScopeAssetCount` and a null `totalBookValueCents` with `hasData` true for the "Not tracked" state to be reachable live.

## Self-Check: PASSED

- Files modified exist: services/apiService.ts, components/itam/ItamKpiPanel.tsx, src/__tests__/ITAMKpiPanel.test.tsx.
- Commits 985b8d95c, 664007784, a33d1ed95, 2ff6c20e0 are ancestors of HEAD.
