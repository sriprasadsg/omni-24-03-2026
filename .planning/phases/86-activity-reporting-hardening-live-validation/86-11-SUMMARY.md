---
phase: 86-activity-reporting-hardening-live-validation
plan: 11
subsystem: autonomous-ops-reporting-ui
tags: [export, csv, pdf, dialog, reporting-card, vitest, react, autonomous-ops]
status: complete

requires:
  - phase: 86-04
    provides: StatsCard, reportingCopy.ts and the statistics payload with canExport
  - phase: 86-08
    provides: GET /api/autonomous-ops/export (X-Export-* headers, 204) and the Autonomous Ops Activity registry type
provides:
  - Export activity button and dialog on the Autonomous Ops screen, exporting the list's active state pill and a chosen period
  - downloadAutonomousOpsExport, downloadAutonomousOpsReport, fileNameFrom and the ExportFormat, ExportDays, ExportOutcome types
  - Autonomous Ops Activity card in the Reporting Data Export Center with disabled reasons
  - EmptyStateCard in its own file, re-exported by the list (list file now 487 lines)
affects: [86-13]

actuals:
  tokens: 22000
  tasks: 2
  commits: 4
plan_head_before: 8eea12b1690fedc15ddfd135963a91018739f5ef
plan_head_after: e5ac7134be589f70be19e2493b7d2004ea9d957f

tech-stack:
  added: []
  patterns:
    - StatsCard reports its payload through an onStats ref callback so the screen reads canExport without a second fetch
    - the list reports its effective pill through onBucketChange so the dialog exports what the operator sees
    - one in-flight ref guards the dialog download; Esc is closed off through Modal closeOnEsc while pending
    - the Reporting card mounts with exactly one import line and one mount line, staged with git apply --cached so the user's KPI hunks stay unstaged

key-files:
  created:
    - components/autonomousOpsStats/ExportDialog.tsx
    - components/autonomousOpsStats/ReportExportCard.tsx
    - components/AutonomousOpsEmptyStateCard.tsx
    - src/__tests__/autonomousOpsExport.test.tsx
  modified:
    - services/autonomousOpsReporting.ts
    - components/autonomousOpsStats/reportingCopy.ts
    - components/autonomousOpsStats/StatsCard.tsx
    - components/AutonomousOpsActivity.tsx
    - components/AutonomousOpsActivityList.tsx
    - components/ReportingDashboard.tsx

key-decisions:
  - "The export result replaces the dialog's choices (cut or empty file): the footer then offers Close only, as the UI-SPEC says the dialog switches to a result block."
  - "canExport is remembered per organization key, so a stale right from a previous organization never shows the button for the next one while its statistics load."
  - "A single row reads '1 row' in the toast and the cap note; the UI-SPEC wording '{n} rows' is kept for every other count."
  - "A whole Reporting-card download shows no toast (the existing ExportCard shows none); only the cut and failure toasts of the contract appear."

requirements-completed: [ACTV-06]

coverage:
  - id: D1
    description: "Export activity button shows beside Newest first only in tenant scope with canExport true"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsExport.test.tsx#the Export activity button"
        status: pass
    human_judgment: false
  - id: D2
    description: "Dialog opens filled, exports the list's state pill and chosen period with one request, states the included rows and the audit sentence, keeps Close enabled and ignores Esc while preparing"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsExport.test.tsx#the Export activity dialog"
        status: pass
    human_judgment: false
  - id: D3
    description: "Whole, cut (amber note with true total), empty (204) and error (red alert, 403 sentence) results"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsExport.test.tsx#the Export activity dialog"
        status: pass
    human_judgment: false
  - id: D4
    description: "Reporting card: both buttons for the right people, spinner on the clicked button, cut and failure toasts, disabled reasons referenced by aria-describedby, mounted after Agent Health"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsExport.test.tsx#the Autonomous Ops Activity card on the Reporting screen"
        status: pass
    human_judgment: false
  - id: D5
    description: "Wrapping of a long file name and of the card note at 320px"
    requirement: ACTV-06
    verification: []
    human_judgment: true
    rationale: "Layout at 320px is a backstop item in the UI-SPEC; break-words classes are in place but no test measures them."

duration: ~25 min
completed: 2026-11-13
---

# Phase 86 Plan 11: Export activity dialog and Reporting card Summary

**The Autonomous Ops screen now has an Export activity dialog (CSV or PDF, a chosen period, exactly the list's active state) and the Reporting screen offers an Autonomous Ops Activity card; both call the 86-08 routes, say honestly when a file was cut at 5,000 rows or empty, and explain in words why they are off.**

## What was built

- **Service (`services/autonomousOpsReporting.ts`):** `downloadAutonomousOpsExport` (URLSearchParams on `/autonomous-ops/export`; 204 gives `{status: 'empty'}` and saves no file; a failure throws the `AutonomousOpsApiError` with its status; a file saves through a blob link and returns rows, total and truncated from `X-Export-Rows`, `X-Export-Total`, `X-Export-Truncated`, parsed as integers with a fallback), `fileNameFrom` (the Content-Disposition regex `exportReport` uses) and `downloadAutonomousOpsReport` (registry type, always all states and 30 days).
- **Dialog (`ExportDialog.tsx`, 135 lines):** Format and Period fieldsets (CSV default, the Statistics period default), the `Activity: {state}. Period: {period}. Newest first, up to 5,000 rows.` status line, the audit-log sentence, Close with first focus, an accent Download CSV or Download PDF button (`Preparing...` while pending, one request however often clicked), `closeOnEsc` off while pending, `showClose={false}` and `closeOnBackdrop={false}`. A whole file closes the dialog with `Export downloaded. {n} rows.`; a cut file keeps an amber `ClockIcon` note naming the file and the true total; 204 shows the blue block; a failure shows a red `role="alert"` with the choices kept and a separate 403 sentence. The file name renders as React text.
- **Screen wiring (`AutonomousOpsActivity.tsx`):** `Export activity` secondary button with `DownloadIcon` in a `flex items-center gap-4` group with `Newest first`, shown only in tenant scope for a non-platform organization when the statistics payload says `canExport`. `StatsCard` gained `onStats`; the list gained `onBucketChange`.
- **Reporting card (`ReportExportCard.tsx`, 72 lines):** the `ExportCard` classes plus a 12/400 note and a reason line (platform staff, then no `export:reports`, then no `view:autonomous_ops`) referenced by `aria-describedby` on both buttons; its own pending state with the `ActivityIcon` spinner on the clicked button; toasts `Export downloaded. Only the newest 5,000 rows are included.` and `Failed to export Autonomous Ops Activity.`. `ReportingDashboard.tsx` gained exactly one import and one mount line after Agent Health.
- **EmptyStateCard move:** into `components/AutonomousOpsEmptyStateCard.tsx`, re-exported from `AutonomousOpsActivityList.tsx` with one line, so the existing importers compile unchanged; the list file is 487 lines.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | RED | 689c0db76 | test(86-11): add failing tests for the Export activity button and dialog |
| 1 | GREEN | c46b5e7a8 | feat(86-11): Export activity button and dialog on the Autonomous Ops screen |
| 2 | RED | 381306eb7 | test(86-11): add failing tests for the Autonomous Ops Activity Reporting card |
| 2 | GREEN | e5ac7134b | feat(86-11): Autonomous Ops Activity card in the Reporting Data Export Center |

## TDD Gate Compliance

- **RED, Task 1 and Task 2:** the test file imports modules that did not exist yet (`ExportDialog`, `AutonomousOpsEmptyStateCard`, `ReportExportCard`), so the file failed at import resolution ("Failed to resolve import ... Does the file exist?") rather than on individual assertions. Semantic assessment: this proves the target tests could not run before the implementation, but it is a load failure, not assertion-level RED evidence. The plan is `type: execute`, so `gsd check tdd-red-evidence` was not required; the RED commits precede their GREEN commits.
- **GREEN:** both feat commits pass. No refactor commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Plan note] RED test assertion on the mount line count**
- **Found during:** Task 2 GREEN
- **Issue:** the test counted regex matches of `ReportExportCard` (3: the import statement names it twice) where the plan's acceptance counts lines (2).
- **Fix:** the test counts lines containing the name; changed in the Task 2 GREEN commit.
- **Commit:** e5ac7134b

**2. [Plan note] Extra `gap-4` and `min-w-0` on the Reporting card**
- The card keeps the ExportCard classes and adds `gap-4` on the row and `min-w-0` on the text column so the note and reason wrap beside the buttons at narrow widths (E6 overflow backstop).

**Total deviations:** 0 behaviour changes against the must-haves, 2 notes.

## Verification

- Task 1 verify (`autonomousOpsExport`, `AutonomousOpsActivity`, `autonomousOpsStats`, `autonomousOpsCopy`): 104 passed.
- Task 2 verify: `autonomousOpsExport` + `autonomousOpsCopy` 47 passed; `npm run build` built in 3.45s (writes dist-new only; not published).
- Plan verification: full `npx vitest run src/__tests__`: 128 files, 2116 tests passed.
- Acceptance greps: list file 487 lines, `onBucketChange` 3, `export { EmptyStateCard }` 1, `X-Export-Total` 2 in the service, `showClose={false}` 1, `closeOnBackdrop={false}` 1, `dangerouslySetInnerHTML` 0 in the dialog; `ReportExportCard` 2 lines in `ReportingDashboard.tsx`, `aria-describedby` 2 in the card.
- `git diff --cached -- components/ReportingDashboard.tsx` for the Task 2 commit added exactly 2 lines and removed none; the user's 3 KPI hunks are still unstaged and intact (`git diff` of the file shows 3 insertions, 3 deletions).
- No UI publish, no restart, no push.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-86-27 mitigated (file name and counts are React text and integers with a fallback; no `dangerouslySetInnerHTML`, a hostile-file-name test asserts no element is created); T-86-28 accepted (the server checks both rights and the organization).

## Notes for later plans

- 86-13: the UI is built to `dist-new/` only; publishing is the user's. 320px wrapping of the result block and the card note is a backstop to check by eye.
- 86-12 can reuse `ACCENT_BUTTON`, `plain` and the dialog shape of `ExportDialog` (one in-flight ref, `closeOnEsc={!pending}`).

## Self-Check: PASSED

Created files `components/autonomousOpsStats/ExportDialog.tsx`, `components/autonomousOpsStats/ReportExportCard.tsx`, `components/AutonomousOpsEmptyStateCard.tsx` and `src/__tests__/autonomousOpsExport.test.tsx` exist; commits 689c0db76, c46b5e7a8, 381306eb7 and e5ac7134b are ancestors of HEAD; `git rev-list --count` from the recorded base gives 4.
