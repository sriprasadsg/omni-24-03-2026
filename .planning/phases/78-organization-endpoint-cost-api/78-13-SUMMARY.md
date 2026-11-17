---
phase: 78-organization-endpoint-cost-api
plan: 13
subsystem: ui
tags: [itam, reports, react, request-sequence, tenant-isolation, export, vitest, gap-closure]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: ReportsPanel runSeq request-sequence guard and tenant-clear-on-switch (78-06, 78-11)
provides:
  - ReportsPanel keeps the shown report and its identity as one value (shown: kind, key, page, data) written only by the current request, plus a separate pending run
  - ReportResultView presentational component that derives title, rows, export buttons and page controls from that one value
  - tenantEpoch export guard: an export started for one tenant never downloads or toasts after a tenant switch, and the switch resets the exporting state
  - Seven new tests (T-h..T-n) in ITAMReportsPanelStaleResponse.test.tsx
affects: [phase-78-reverification, 78-14, 78-15]

actuals:
  tokens: 7279
  tasks: 2
  commits: 4
plan_head_before: c34c887bbe8fd864f3184e59091ff65748ab48fc
plan_head_after: 5f4ddc66563dea0d5f3399b844f93839683e4582

tech-stack:
  added: []
  patterns:
    - "One shown value (kind, key, page, data): displayed rows and their identity change in a single setState, only after the runSeq check"
    - "tenantEpoch ref moves only on a tenant switch (unlike runSeq, which moves on every run), so an async export is cancelled by a switch but not by a new run in the same tenant"

key-files:
  created:
    - components/itam/ReportResultView.tsx
  modified:
    - components/itam/ReportsPanel.tsx
    - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx

key-decisions:
  - "A failed current run keeps the previous consistent result (A-78-29), preserving the Phase 72 behaviour pinned by the existing 'rejected run' test"
  - "While a run is in flight the export buttons and page controls are hidden and the heading shows the run's own title (A-78-28); previously they stayed visible under the old result and targeted the new report"
  - "Export guard uses a tenant-only counter instead of runSeq (A-78-30) so an export started in a tenant still downloads when a new run starts in that same tenant"
  - "Result block moved into components/itam/ReportResultView.tsx (A-78-31) to keep ReportsPanel.tsx well under 500 lines and make the one-shown-value rule structural"

patterns-established:
  - "Export target is read from the shown report at click time (const { kind, key } = shown), never from separately tracked active state"

requirements-completed: [COST-07]
gap_ids: [G-78-WR04, G-78-IN05]

coverage:
  - id: D1
    description: "A failed run after a successful one leaves the earlier report's title, rows, export target and pages on screen (WR-04)"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#a failed run after a successful one keeps the earlier report's title, rows and export target"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#pagination follows the shown report after a failed run"
        status: pass
    human_judgment: false
  - id: D2
    description: "A builder preview that supersedes an in-flight run and fails keeps the earlier report with its export target; the superseded run renders nothing when it resolves"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#a builder preview that supersedes an in-flight run and fails keeps the earlier report and its export target"
        status: pass
    human_judgment: false
  - id: D3
    description: "An in-flight run shows the Loading line under its own title with no export buttons, table or page controls"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#an in-flight run shows its own title and no export buttons"
        status: pass
    human_judgment: false
  - id: D4
    description: "An export started before a tenant switch neither downloads, toasts on failure, nor keeps the next result's buttons disabled; an export in the same tenant still downloads (IN-05)"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#an export started before a tenant switch neither downloads nor keeps the buttons disabled"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#an export that fails after a tenant switch raises no toast"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#an export in the same tenant still downloads when a new run starts"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual result of the in-flight state (title with Loading line, hidden export buttons) in the live Reports tab"
    verification: []
    human_judgment: true
    rationale: "A-78-28 is a small visible change; whether it reads well in the real UI is a post-deploy look, not asserted by tests"

duration: 9 min
completed: 2026-11-17
status: complete
---

# Phase 78 Plan 13: ReportsPanel shown report and tenant-bound exports Summary

**ReportsPanel now holds the displayed report and its identity as one `shown` value with a separate `pending` run, rendered by a new ReportResultView, and binds each export to the tenant it started in with a tenant-only `tenantEpoch` guard.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-11-17T07:27:00Z (approx.)
- **Completed:** 2026-11-17T07:36:00Z
- **Tasks:** 2
- **Files modified:** 3 (1 created)

## Accomplishments

- G-78-WR04 closed: after report A succeeds, a failed run of B, a failed builder preview that superseded B, or a page change leaves A's title, rows, export target and pagination on screen; Export CSV calls `generateItamReport('prebuilt', 'asset_value', 'csv', 't-1')` and Next runs `asset_value` page 2.
- In-flight state: the result area shows the Loading line under the title of the run being run, with no table, export buttons or page controls (A-78-28).
- G-78-IN05 closed: a tenant switch bumps `tenantEpoch` and resets `exportingFormat`; a stale export resolves or fails silently, while an export in the same tenant still downloads when a new run starts.
- ReportsPanel.tsx 427 -> 320 lines; new ReportResultView.tsx is 129 lines; the test file is 372 lines (14 tests, was 7).

## Task Commits

1. **Task 1: Tracer, failed run keeps the earlier report's title, rows and export target**
   - RED: `3a3353c21` (test)
   - GREEN: `a3a57c911` (fix)
2. **Task 2: Preview supersede, pagination, in-flight state and tenant-bound export**
   - RED/pins: `cd2ac7ab4` (test)
   - GREEN: `5f4ddc665` (fix)

**Plan metadata:** the docs(78-13) commit that carries this SUMMARY, STATE.md, ROADMAP.md.

## RED evidence

- **Task 1:** before the GREEN edit, "a failed run after a successful one keeps the earlier report's title, rows and export target" failed on the `generateItamReport` argument assertion (`ITAMReportsPanelStaleResponse.test.tsx:226`): expected `['prebuilt', 'asset_value', 'csv', 't-1']`, received `'warranty_expiring'` in the second position. 7 other tests passed; no import, mock or fixture error. Semantic assessment: the target test executed and failed on the planned assertion (the export pointing at the failed report) for the intended reason.
- **Task 2:** before the GREEN edit, 12 of 14 tests passed and 2 failed: "an export started before a tenant switch neither downloads nor keeps the buttons disabled" failed on the enabled Export CSV button lookup (the stale 'Exporting…' label kept the buttons disabled) and "an export that fails after a tenant switch raises no toast" failed on `showToast` being called with `('boom', 'error')`. T-i, T-j, T-k and T-n passed through Task 1, as the plan expected (they pin the remaining WR-04 paths and the same-tenant adjacency).
- The `gsd_run check tdd-red-evidence` classifier was not run: the plan is `type: execute` (not `type: tdd`) and the RED outcomes above come from the real vitest runs.

## Verification

- `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx`: 3 files, 69 passed, 0 failed (ITAMReportsPanelStaleResponse alone: 14 passed).
- `npx vitest run src/__tests__`: 135 files, 2249 passed, 0 failed.
- `npm run typecheck`: exit 0.
- `npm run build`: built in 3.90 s.
- Acceptance greps: `useState<ShownReport | null>(null)` 1, `<ReportResultView` 1, `useState<ItamReportRunResult | null>` 0, the three argument-list greps 1 each, anchor `  }, [focusReportKey]);` 1, `tenantEpoch.current` in handleExport 4 (at least 4 required), reset block has `tenantEpoch.current += 1`, `setExportingFormat(null)` and `runSeq.current += 1` once each, all six new test names present once.

## User hunk and user-modified files

- The user's hunk in `components/itam/ReportsPanel.tsx` (removed `// eslint-disable-next-line react-hooks/exhaustive-deps` above `}, [focusReportKey]);`) is untouched and unstaged: each commit was staged by inserting that line into a scratchpad copy and `git update-index --cacheinfo`; after the last commit HEAD still contains the line (`grep -c` prints 1) and `git diff --numstat` for the file prints `0 1`.
- App.tsx (21/15), services/apiService.ts (10/0), src/__tests__/ITAMConsole.test.tsx (0/1) and src/__tests__/ITAMReportsPanel.test.tsx (4/3) are unedited and unstaged (numstat identical to the start); `git diff --cached --quiet` exits 0 after every commit.
- No stash, checkout, restore, clean or reformat was run.

## Decisions Made

See key-decisions above; all five plan assumptions (A-78-28..A-78-32) were implemented as written.

## Deviations from Plan

None - plan executed exactly as written. (The tracer feedback gate: interactive-equivalent `end-of-phase` mode with an automated-only verify, so the three-suite run and typecheck were re-run after the GREEN edit and passed; "Tracer verified end-to-end — expanding".)

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. The change adds no endpoint, auth path or schema; it tightens T-78-33 (shown/export coupling), T-78-34 (stale export after tenant switch) and T-78-35 (user hunk preserved) as planned.

## User Setup Required

None - no external service configuration required. The UI is not published and no service was restarted (both are the user's).

## Next Phase Readiness

- 78-14 (custom-report tenant argument on the client, WR-02) and 78-15 (IN-04) can build on the `shown` / `ReportResultView` split; the custom run, preview and custom export argument lists are unchanged here, as the plan required.
- The in-flight presentation (A-78-28) deserves a look in the live Reports tab after the next UI publish.

## Self-Check: PASSED

- `components/itam/ReportResultView.tsx`, `components/itam/ReportsPanel.tsx`, `src/__tests__/ITAMReportsPanelStaleResponse.test.tsx` exist.
- Commits `3a3353c21`, `a3a57c911`, `cd2ac7ab4`, `5f4ddc665` are ancestors of HEAD; `git rev-list --count c34c887bb..HEAD` is 4.

---
*Phase: 78-organization-endpoint-cost-api*
*Completed: 2026-11-17*
