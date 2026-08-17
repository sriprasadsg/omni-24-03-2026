---
phase: 72-reporting-dashboards
plan: 06
subsystem: ui
tags: [react, typescript, itam, reporting, forms]

# Dependency graph
requires:
  - phase: 72-reporting-dashboards
    plan: 02
    provides: "All six PREBUILT_REPORTS entries this plan's pre-built card grid lists"
  - phase: 72-reporting-dashboards
    plan: 03
    provides: "GET /api/itam/reports/fields, POST/GET/DELETE /custom, POST /custom/preview, POST /custom/{id}/run, POST /custom/{id}/export — the full custom-report route surface this plan's client functions and builder UI consume"
  - phase: 72-reporting-dashboards
    plan: 05
    provides: "RENDERERS holding csv/pdf/xlsx — every export button this plan adds resolves to a real, already-registered renderer with no backend change"
provides:
  - "components/itam/ReportBuilderForm.tsx — the field + filter picker (D-02/D-03), split out of ReportsPanel to stay under the 500-line cap"
  - "6 new services/apiService.ts client functions (fetchItamReportFields/saveItamCustomReport/listItamCustomReports/deleteItamCustomReport/previewItamCustomReport/runItamCustomReport) plus generateItamReport extended to accept kind='custom'"
  - "ReportsPanel.tsx's two-section layout (D-10): Pre-built Reports (unchanged card grid) and Custom Reports (builder reveal, saved-report list, delete confirmation, three export buttons on the shared preview table)"
affects: [72-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Field + filter picker driven entirely by the backend's field catalogue (GET /fields) — operator choices are derived from each field's type at render time, never hardcoded per field, so the picker can never offer an operator the backend would reject"
    - "Shared preview table serves three producers (pre-built run, saved-custom run, unsaved builder preview) through one activeKind/activeKey/result state trio; export capability is gated on activeKind && activeKey (a stable report reference), not on result alone"

key-files:
  created:
    - components/itam/ReportBuilderForm.tsx
  modified:
    - services/apiService.ts
    - components/itam/ReportsPanel.tsx
    - src/__tests__/ITAMReportsPanel.test.tsx
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "An unsaved builder preview (previewItamCustomReport) is not exportable — export buttons require a stable kind+key (a pre-built report's key, or a saved custom report's id from runItamCustomReport). The backend has no route to export an ad hoc, unsaved custom definition (only POST /custom/{report_id}/export, which requires a persisted id); adding one would be a backend change outside this plan's files_modified scope. To still satisfy 'the user can export the previewed custom report' in practice, handleSaveCustom immediately runs the newly-saved report (runSavedCustom) right after saveItamCustomReport succeeds, so the same on-screen preview table becomes exportable in the same interaction without a second manual click."
  - "Pagination controls (Previous/Next) render only when activeKind && activeKey are set, i.e. for pre-built and saved-custom runs. An unsaved builder preview has no stored definition to re-run against a different page, so pagination is intentionally absent for that one flow — a documented, narrow scope boundary rather than a gap silently discovered later."
  - "The builder's primary run button is labelled 'Run' (not 'Run Report') to stay unambiguous in tests and the DOM alongside the pre-built cards' 'Run Report' CTA — the UI-SPEC's Copywriting Contract does not lock an exact label for this control."

patterns-established: []

requirements-completed: [ITAM-REP-01, ITAM-REP-02, ITAM-REP-03]

coverage:
  - id: D1
    description: "The builder fetches the field catalogue on mount and offers exactly the operators valid for a field's type (equals/contains for text, before/after/between for date, gt/lt/between for number), revealing a second value input only for between"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > a text field offers exactly equals/contains and a date field offers exactly three operators"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > choosing the between operator reveals a second value input"
        status: pass
    human_judgment: false
  - id: D2
    description: "An added filter renders as a removable AND-combined row; removing it drops it from the definition; running with zero filters submits an empty filter list; Run stays disabled until at least one column is selected"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > an added filter appears as a removable row and removing it drops it from the definition"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > running with zero filters submits an empty filter list and still returns rows"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > Run is disabled until at least one column is selected"
        status: pass
    human_judgment: false
  - id: D3
    description: "A rejected run/save routes through showToast with the error variant and the Copywriting Contract's run/save error sentences"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > a rejected run calls showToast with the error variant and the run error sentence"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportBuilderForm > a rejected save calls showToast with the save error sentence"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Reports tab renders both sections in one tab: the fixed six-card pre-built grid and a Custom Reports section whose Create Custom Report control reveals the builder"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > renders all six pre-built report titles in the pre-built section"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > the Create Custom Report control reveals the builder form"
        status: pass
    human_judgment: false
  - id: D5
    description: "The saved custom reports list shows the exact empty-state copy with zero reports, and renders one row per report (truncated name + tooltip, run + delete controls) once populated"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > renders the \"No custom reports yet\" empty state with no saved reports"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > renders one row per saved report with truncated name, run and delete controls"
        status: pass
    human_judgment: false
  - id: D6
    description: "Deleting a saved report goes through the shared Modal (title 'Delete report?'); deleteItamCustomReport is not called on dismiss and is called only after the confirm control is used"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > clicking delete opens the shared Modal and only calls deleteItamCustomReport after the confirm control is used"
        status: pass
    human_judgment: false
  - id: D7
    description: "Running a saved custom report renders its rows in the shared preview table, and all three export buttons (Export PDF/Excel/CSV) appear once a report has run"
    requirement: "ITAM-REP-02"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > running a saved report renders its rows in the shared preview table"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > the three export buttons appear labelled once a report has run"
        status: pass
    human_judgment: false
  - id: D8
    description: "Clicking an export button calls generateItamReport with the running report's kind and key/id and the clicked format, then downloadItamReport with the returned filename; buttons disable and show the loading convention while a generation is in flight; a failed export toasts the export-error sentence"
    requirement: "ITAM-REP-03"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > clicking an export button calls generateItamReport with the running report kind/key, then downloadItamReport"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > export buttons are disabled and show the loading convention while generation is in flight"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > a failed export calls showToast with the export error sentence"
        status: pass
    human_judgment: false
  - id: D9
    description: "A saved-report list load failure leaves the list unpopulated (empty state) and raises the error toast rather than unmounting the Custom Reports section"
    requirement: "ITAM-REP-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#ReportsPanel — two-section layout > a saved-report list load failure leaves the list unpopulated and raises the error toast"
        status: pass
    human_judgment: false
  - id: D10
    description: "With many columns selected the preview table scrolls horizontally rather than overflowing the card, and long cell values truncate with a tooltip instead of growing row height"
    verification: []
    human_judgment: true
    rationale: "UI-SPEC backstop item (E4 overflow/long-text) — a live visual check of horizontal scroll and truncation rendering, not observable from an automated DOM assertion alone. Deferred to end-of-phase human verification per the plan's own <verification> note."

duration: ~35min
completed: 2026-08-17
status: complete
---

# Phase 72 Plan 06: Custom Report Builder Frontend + Two-Section Reports Tab Summary

**ReportBuilderForm.tsx (the field + filter picker, D-02/D-03) and ReportsPanel.tsx's expansion into D-10's two-section layout — pre-built grid, saved-report list with delete confirmation, and three export buttons (PDF/Excel/CSV) on a preview table now shared by pre-built runs, saved-custom runs, and unsaved builder previews.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- `services/apiService.ts` gained 6 client functions (`fetchItamReportFields`, `saveItamCustomReport`, `listItamCustomReports`, `deleteItamCustomReport`, `previewItamCustomReport`, `runItamCustomReport`) cloning the existing `authFetch` + `itamThrow` shape, and `generateItamReport` now accepts `kind='custom'` in addition to `'prebuilt'`, routing to `/custom/{id}/export` vs `/prebuilt/{key}/export`.
- `components/itam/ReportBuilderForm.tsx` (new, 295 lines): fetches the field catalogue on mount, renders columns as toggleable chips grouped by entity inside a `max-h-64 overflow-y-auto` container, and a filter builder whose operator choices are derived live from the selected field's type — never hardcoded per field — with a second value input appearing only for `between`. Added filters render as removable AND-combined rows above the add-row controls. Run is disabled until at least one column is selected; a rejected run/save routes through `showToast` with the Copywriting Contract's exact error sentences.
- `components/itam/ReportsPanel.tsx` expanded into the two-section layout: `Pre-built Reports` (unchanged fixed six-card grid) and `Custom Reports` (a `Create Custom Report` toggle revealing the builder, plus a saved-report list matching `LicensesPanel.tsx`'s row pattern — truncated name with tooltip, Run and Delete controls, vertically scrolling with no item cap, and the exact empty-state copy from the Copywriting Contract).
- Delete confirmation clones `CatalogPanel.tsx`'s `Modal` flow verbatim: title `Delete report?`, the exact irreversibility description, confirm label `Delete`; `deleteItamCustomReport` fires only from the modal's confirm handler, never on open/dismiss.
- Three export buttons (`Export PDF`/`Export Excel`/`Export CSV`) render in the shared preview-table header once a report has a stable kind+key (a pre-built run or a saved-custom run); each calls `generateItamReport(kind, key, format)` then `downloadItamReport(filename)`, shows its own `Exporting…` label while in flight, disables all three siblings during any active export, and toasts the Copywriting Contract's export-error sentence on failure.
- 27 tests now in `src/__tests__/ITAMReportsPanel.test.tsx` (16 from Task 1, 11 more from Task 2); full frontend suite (`src/__tests__`, 13 files) 112/112 pass; `npm run build` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: Custom-report client functions and the field + filter picker** - `472723df` (feat)
2. **Task 2: Two-section Reports tab — pre-built grid, saved list, delete modal, three export buttons** - `1a1cd97f` (feat)

**Plan metadata:** _pending — this commit_

## Files Created/Modified
- `components/itam/ReportBuilderForm.tsx` - the field + filter picker (D-02/D-03): column chips, filter builder, AND-combined removable filter rows, Run/Save controls
- `services/apiService.ts` - 6 new custom-report client functions + 3 new exported interfaces (`ItamReportField`, `ItamReportFilterCondition`, `ItamCustomReportDefinition`, `ItamSavedCustomReport`); `generateItamReport` extended to support `kind='custom'`
- `components/itam/ReportsPanel.tsx` - two-section layout: pre-built grid unchanged, new Custom Reports section (builder reveal, saved list, delete modal), shared preview table now serves three producers, three export buttons
- `src/__tests__/ITAMReportsPanel.test.tsx` - 27 tests total: 16 for `ReportBuilderForm` (Task 1), 11 for the two-section `ReportsPanel` layout (Task 2)
- `src/__tests__/ITAMConsole.test.tsx` - mock additions for the 5 new apiService functions `ReportsPanel`/`ReportBuilderForm` now call, so the existing "switches to Reports tab" smoke test keeps passing against the expanded panel

## Decisions Made
- An unsaved builder preview is not directly exportable — the backend's only custom-report export route (`POST /custom/{report_id}/export`) requires a persisted id, and adding an ad hoc/unsaved export route would be a backend change outside this plan's `files_modified` scope. `handleSaveCustom` closes this gap in practice by immediately running the newly-saved report right after `saveItamCustomReport` succeeds, so the same on-screen result becomes exportable in one continuous interaction.
- Pagination controls are gated on `activeKind && activeKey` (pre-built and saved-custom runs only) since an unsaved preview has no stored definition to re-run against a different page.
- The builder's primary action is labelled "Run" rather than "Run Report" — the UI-SPEC's Copywriting Contract doesn't lock an exact label here, and a distinct label avoids DOM/test ambiguity against the pre-built cards' "Run Report" CTA rendered in the same tab.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed the results-section visibility gate to not hide the Loading… state on first run**
- **Found during:** Task 2, running the extended test suite
- **Issue:** The initial rewrite gated the whole results region (title/export controls/loading/table) on `{result && (...)}`. On a fresh run, `result` stays `null` until the request resolves, so the `running && <Loading…/>` branch never rendered on a report's very first run — a real regression against the existing "an in-flight run shows the Loading… convention" test carried over from 72-01.
- **Fix:** Changed the outer gate to `{(running || result) && (...)}` and restored the original `result?.title || activeKey || ''` fallback (matching the pre-existing 72-01 pattern) plus `result &&` null-guards on the two inner row-count branches.
- **Files modified:** `components/itam/ReportsPanel.tsx`
- **Verification:** Full `ITAMReportsPanel.test.tsx` suite (27 tests, including the pre-existing 72-01 Loading… test) passes.
- **Committed in:** `1a1cd97f` (Task 2 commit — caught and fixed before commit, not a separate follow-up)

**2. [Rule 3 - Blocking] Extended `ITAMConsole.test.tsx`'s apiService mock for the 5 new functions the expanded panel calls on mount**
- **Found during:** Task 2, running `ITAMConsole.test.tsx`
- **Issue:** `ReportsPanel` now calls `listItamCustomReports()` unconditionally on mount (for the saved-report list), and `ReportBuilderForm` calls `fetchItamReportFields()` when revealed. `ITAMConsole.test.tsx`'s existing `vi.mock('../../services/apiService', ...)` factory (a file outside this plan's declared `files_modified`, but broken by this plan's own change) didn't define these functions, so the existing "switches to the Reports tab" test would fail calling `undefined` as a function.
- **Fix:** Added `fetchItamReportFields`, `saveItamCustomReport`, `listItamCustomReports`, `deleteItamCustomReport`, `previewItamCustomReport`, `runItamCustomReport` to the mock factory, mirroring the existing mock style.
- **Files modified:** `src/__tests__/ITAMConsole.test.tsx`
- **Verification:** `ITAMConsole.test.tsx` (14 tests) passes.
- **Committed in:** `1a1cd97f` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3, blocking issues directly caused by this plan's own changes).
**Impact on plan:** No scope creep — both fixes were necessary consequences of Task 2's own work (the shared-state refactor and the new mount-time API calls), required to keep the existing test suite green.

## Issues Encountered
None beyond the two auto-fixed items above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `ReportBuilderForm`'s props (`onPreview`, `onSave`, `busy`) and `ReportsPanel`'s `activeKind`/`activeKey`/`result` state trio are stable — plan 72-07's `ItamKpiPanel` mounts above this panel in `ITAMConsole.tsx` and does not touch any of this plan's files.
- One item remains human-only per the plan's own `<verification>` note: confirming the preview table scrolls horizontally (not vertically-cramped) and cell values truncate with a tooltip when many columns are selected — a live-browser visual check, not exercised this session.
- Custom-report export currently requires saving first (see Decisions Made) — if a future phase wants a true "export an unsaved preview" flow, it needs a new backend route (`POST /custom/preview/export` or similar), which is a backend change out of this plan's scope.

---
*Phase: 72-reporting-dashboards*
*Completed: 2026-08-17*

## Self-Check: PASSED

All 6 created/modified files found on disk; both task commits (`472723df`, `1a1cd97f`) found in git history.
