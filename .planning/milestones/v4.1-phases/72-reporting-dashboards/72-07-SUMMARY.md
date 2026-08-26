---
phase: 72-reporting-dashboards
plan: 07
subsystem: ui
tags: [react, typescript, recharts, itam, dashboard, kpi]

# Dependency graph
requires:
  - phase: 72-reporting-dashboards
    plan: 04
    provides: "compute_itam_kpis / GET /api/itam/kpis / fetchItamKpis() — the tenant-scoped KPI aggregate this plan's tile grid renders"
  - phase: 72-reporting-dashboards
    plan: 06
    provides: "ReportsPanel.tsx's two-section layout and its focusReportKey/onFocusHandled prop pair — the drill-down seam ItamKpiPanel's onDrillDown attaches to"
provides:
  - "components/itam/ItamKpiPanel.tsx — the Reports tab's four-tile KPI grid (assetValue/licenseUtilization/warrantyExpirations/overdue), each tile a clickable drill-down button with a recharts visualisation and an honest empty state"
  - "ItamKpiPanel mounted above ReportsPanel in ITAMConsole.tsx's reports branch, wired to the console's existing reportFocus/setReportFocus state"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "recharts Legend's default itemSorter ('value', alphabetical-by-name) must be overridden with itemSorter={() => 0} whenever a chart's segment order is a correctness requirement (payload order), not just a rendering default"
    - "Testing a recharts ResponsiveContainer under jsdom requires a stub global.ResizeObserver plus a fixed HTMLElement.prototype.getBoundingClientRect — without both, ResponsiveContainer's internal size stays at its -1/-1 initial dimension and renders no children at all"

key-files:
  created:
    - components/itam/ItamKpiPanel.tsx
    - src/__tests__/ITAMKpiPanel.test.tsx
  modified:
    - components/itam/ITAMConsole.tsx
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "ItamKpiPanel takes no accent-color prop (plan's locked signature is only onDrillDown) — icon chips use the console's default cyan (#0891b2/text-cyan-500), the same default DEFAULT_ITAM_SETTINGS.branding.primaryColor an unbranded tenant already renders with"
  - "Empty-state entity/tab copy per tile: assetValue and overdue both use 'an asset' / 'Catalog' (their hasData=false condition is literally 'zero tenant assets'); licenseUtilization uses 'a software license' / 'Licenses & Consumables' (UI-SPEC's own worked example); warrantyExpirations uses 'an asset with a warranty' / 'Procurement & Finance' (where purchaseDate/warrantyMonths are entered, per FinancePanel.tsx)"
  - "The overdue tile renders a plain numeric split (audits vs. check-ins), not a chart, per the plan's own action text — the other three tiles use a PieChart/PieChart/BarChart respectively, matching D-17"

patterns-established: []

requirements-completed: [ITAM-REP-04]

coverage:
  - id: D1
    description: "The Reports tab opens on a four-tile KPI grid (asset value + status breakdown, licence utilisation, warranty expirations, overdue audits/check-ins), each tile a clickable drill-down into its pre-built report"
    requirement: "ITAM-REP-04"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#renders four tiles for a fully-populated payload / clicking a tile invokes onDrillDown with that tile's drilldownReportKey / each tile is reachable as a button element so keyboard activation works"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#renders the KPI grid above the pre-built report sections on the Reports tab / clicking a KPI tile sets reportFocus, driving ReportsPanel to auto-run that report through its focusReportKey seam / clearing the drilled-into focus via ReportsPanel's onFocusHandled prevents a later tab switch from re-triggering the same run"
        status: pass
    human_judgment: false
  - id: D2
    description: "A KPI tile with no underlying data (or a failed fetch) renders 'No data yet' plus entity-specific next-step copy — never a fabricated 0% or 100% — and a single tile's failure never produces a dashboard-wide error banner"
    requirement: "ITAM-REP-04"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#a KPI payload with hasData false renders \"No data yet\" and never a fabricated 0% or 100% / a licence tile with no licences renders the empty state rather than a zero or hundred percent / a rejected fetch leaves every tile in its empty state and renders no dashboard-wide error banner"
        status: pass
    human_judgment: false
  - id: D3
    description: "Status-breakdown chart segments render in the payload's array order, never re-sorted by count — including overriding recharts Legend's default alphabetical itemSorter"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMKpiPanel.test.tsx#renders the status-breakdown segments in the payload array order, never re-sorted by count"
        status: pass
    human_judgment: false
  - id: D4
    description: "The KPI grid sits above the two-section report list as the Reports tab's primary visual anchor (UI-SPEC visual-hierarchy note), and the other 10 console tabs render unchanged"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#renders the KPI grid above the pre-built report sections on the Reports tab (Phase 72 Plan 07) / renders all 11 tabs and defaults to Catalog"
        status: pass
      - kind: other
        ref: "npm run build (exit 0, ITAMConsole confirmed as its own code-split chunk)"
        status: pass
    human_judgment: false

# Metrics
duration: ~20min
completed: 2026-08-17
status: complete
---

# Phase 72 Plan 07: ITAM Reports Tab KPI Grid Summary

**Four-tile recharts KPI grid (asset value, licence utilisation, warranty expirations, overdue audits/check-ins) mounted above ReportsPanel as the Reports tab's primary anchor, each tile a real drill-down button wired through the console's existing reportFocus seam.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `components/itam/ItamKpiPanel.tsx` fetches `ItamKpis` once on mount via `fetchItamKpis`, rendering exactly four button-element tiles (assetValue/licenseUtilization/warrantyExpirations/overdue), each with an accent-tinted icon chip, headline value, and a recharts visualisation cloned from `CXODashboard.tsx`'s usage (`PieChart`/`PieChart`/`BarChart`; the overdue tile is a plain numeric split per the plan's own spec).
- Per-tile states per UI-SPEC E6: `Loading…` while the fetch is in flight; `No data yet` plus entity/tab-specific next-step copy when a KPI's `hasData` is false or the whole fetch fails — never a fabricated 0%/100%, never a dashboard-wide error banner for one tile's failure.
- The asset-value tile's status-breakdown segments render in the payload's array order; caught and fixed a real bug where recharts' `Legend` defaults to alphabetical-by-name sorting (`itemSorter: 'value'`) — overridden with `itemSorter={() => 0}` so the visible legend actually preserves payload order rather than only the underlying (unobservable) data array.
- Clicking any tile calls `onDrillDown(drilldownReportKey)`.
- `ITAMConsole.tsx`'s reports branch now renders `ItamKpiPanel` first and `ReportsPanel` second (UI-SPEC visual-hierarchy note), with `onDrillDown={(reportKey) => setReportFocus(reportKey)}` wired to the console's pre-existing `reportFocus`/`setReportFocus` state — no new state introduced.
- 9 new tests in `ITAMKpiPanel.test.tsx` (including a `ResizeObserver`/`getBoundingClientRect` stub so recharts actually renders under jsdom for the segment-order assertion) and 3 new tests in `ITAMConsole.test.tsx` (grid-above-list ordering, tile-click drill-down reaching `runItamPrebuiltReport`, and focus clearing after `onFocusHandled`). Full frontend suite: 124/124 pass. `npm run build` clean, `ITAMConsole` confirmed as its own code-split chunk.

## Task Commits

Each task was committed atomically:

1. **Task 1: ItamKpiPanel — four recharts tiles with per-tile states** - `3d366f6f` (feat)
2. **Task 2: Mount the KPI grid above the report sections and wire drill-down** - `40e4c1d7` (feat)

**Plan metadata:** _pending — this commit_

## Files Created/Modified
- `components/itam/ItamKpiPanel.tsx` - the four-tile KPI grid: fetch-once state, per-tile Loading/No-data-yet/populated rendering, recharts visualisations, click-to-drill-down
- `src/__tests__/ITAMKpiPanel.test.tsx` - 9 tests covering all `<behavior>` items, including a recharts-under-jsdom `ResizeObserver` stub
- `components/itam/ITAMConsole.tsx` - imports `ItamKpiPanel`, mounts it above `ReportsPanel` in the reports branch, wires `onDrillDown` to `setReportFocus`
- `src/__tests__/ITAMConsole.test.tsx` - `fetchItamKpis` (4 hasData=false KPIs) added to the apiService mock factory, `runItamPrebuiltReport` made independently controllable, 3 new tests for grid ordering/drill-down/focus-clearing

## Decisions Made
- No accent-color prop on `ItamKpiPanel` (plan's props are locked to `onDrillDown` only) — icon chips use the console's default cyan, matching what an unbranded tenant already sees elsewhere.
- Empty-state entity/tab copy assigned per KPI based on where its underlying data is actually entered: assetValue/overdue → "an asset" / Catalog; licenseUtilization → "a software license" / Licenses & Consumables (UI-SPEC's own example); warrantyExpirations → "an asset with a warranty" / Procurement & Finance (where `FinancePanel.tsx` captures `purchaseDate`/`warrantyMonths`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] recharts Legend silently re-sorted status-breakdown segments alphabetically**
- **Found during:** Task 1, writing the segment-order test
- **Issue:** recharts' `Legend` component defaults `itemSorter` to `'value'` (the segment name), so even though the `Pie`'s `data` prop preserved the payload's array order, the rendered legend showed segments alphabetically (`Deployed, In_stock, Retired` instead of the payload's `In_stock, Deployed, Retired` order) — a real violation of the must_haves truth that segments render in payload order, not visible from reading the component's own code, only from the actual rendered DOM.
- **Fix:** Added `itemSorter={() => 0}` (a stable no-op sort) to both `Legend` elements in `ItamKpiPanel.tsx`.
- **Files modified:** `components/itam/ItamKpiPanel.tsx`
- **Verification:** `renders the status-breakdown segments in the payload array order, never re-sorted by count` test passes.
- **Committed in:** `3d366f6f` (Task 1 commit — caught and fixed before commit)

---

**Total deviations:** 1 auto-fixed (Rule 1, a real bug in a must_haves-required behavior).
**Impact on plan:** No scope creep — the fix was required for the plan's own explicit prohibition (segments never re-sorted).

## Issues Encountered
- recharts' `ResponsiveContainer` renders no children at all under jsdom by default (its internal size state starts at `-1/-1` and jsdom's layout engine always reports `0x0`). Worked around in the test file with a stub `global.ResizeObserver` plus a fixed `HTMLElement.prototype.getBoundingClientRect`, exactly as the plan's own action text anticipated ("set an explicit width/height on the mocked container"). This let the real Pie/Bar/Legend markup render so the segment-order test could assert on rendered DOM text rather than SVG geometry.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **Phase 72 (Reporting & Dashboards) is now fully complete — all 7 plans executed, ITAM-REP-01/02/03/04 all done.**
- One item remains human-only per 72-06-SUMMARY.md's carried-forward note: a live-browser check that the report preview table scrolls horizontally and truncates long cell values with a tooltip when many columns are selected (UI-SPEC backstop items E4 overflow/long-text) — not exercised this session.
- A second human-only item from this plan's own `<verification>` note: confirming in a live browser that the KPI row reads as the Reports tab's visual anchor, the charts use the tenant accent as the primary series colour, and a no-data tile reads as genuinely absent rather than as a zero measurement.

---
*Phase: 72-reporting-dashboards*
*Completed: 2026-08-17*

## Self-Check: PASSED

All 4 created/modified files (`components/itam/ItamKpiPanel.tsx`, `src/__tests__/ITAMKpiPanel.test.tsx`, `components/itam/ITAMConsole.tsx`, `src/__tests__/ITAMConsole.test.tsx`) found on disk; both task commits (`3d366f6f`, `40e4c1d7`) found in git history.
