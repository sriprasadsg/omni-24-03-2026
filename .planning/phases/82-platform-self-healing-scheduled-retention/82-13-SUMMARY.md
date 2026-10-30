---
phase: 82-platform-self-healing-scheduled-retention
plan: 13
subsystem: ui
tags: [autonomous-ops, retention, platform-health, confirm-deletion, react, vitest]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-10 GET /retention/review and POST /retention/confirm with the stateless review token; 82-11 typed client (fetchRetentionReview, confirmRetention, AutonomousOpsApiError); 82-12 Platform health section, HealthChip, HealthCell, HealthNotice, HEALTH_SKELETON, the shared test harness"
provides:
  - "AutonomousOpsRetentionReview: the Scheduled data retention card, last block of the Platform health section, with its own fetch, 30 s poll, review table at xl, stacked cards below, 25-row paging"
  - "RetentionConfirmDialog: the Confirm deletion dialog with the checkbox gate, one request per click, 409 stale-counts, 403 and failure paths"
  - "Harness helpers withUser, routeRetention, retentionReview, retentionItem for later retention UI tests"
affects: [82-14 tenant Retention Policy notices, 82 UAT, operator confirm step after the first 02:00 UTC count]

requirements-completed: [HEAL-06]

actuals:
  tokens: 16170
  tasks: 3
  commits: 7

key-files:
  created:
    - components/AutonomousOpsRetentionReview.tsx
    - components/AutonomousOpsRetentionConfirmDialog.tsx
    - src/__tests__/AutonomousOpsRetentionReview.test.tsx
    - src/__tests__/AutonomousOpsRetentionConfirmDialog.test.tsx
  modified:
    - components/AutonomousOpsPlatformHealth.tsx
    - components/AutonomousOpsHealthCards.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts
    - src/__tests__/_platformHealthHarness.tsx
    - src/__tests__/AutonomousOpsPlatformHealth.test.tsx
    - src/__tests__/AutonomousOpsHealthCards.test.tsx

key-decisions:
  - "The dialog confirms a snapshot (token, totals, count time) taken when it opened, never the live review: a 30 s poll that changes the counts while the dialog is open cannot silently change what one click confirms; the server's 409 then catches the rest"
  - "A background refresh keeps rows already loaded by Load more while the review token is unchanged (the token covers every waiting row and its count); a changed token replaces the rows with the fresh first page"
  - "Confirm deletion is disabled when a run is in progress or when no row is countable (rows minus uncountable is zero), using the server's totals; uncountable rows are never summed and are listed with Couldn't count"
  - "A failed last run is shown once, as the red role=alert block under the header; the Last run cell then carries no helper"
  - "The dialog's two exits are separate: onClose (Keep waiting, Esc) does nothing; onConfirmed (success, 403, Reload review) closes and refetches"
  - "A response without an items array is treated as a load failure, so a malformed answer cannot crash the Platform health page"

patterns-established:
  - "Own-fetch cards inside the Platform health section render after the {doc && ...} branch so a failed health document does not hide them"

duration: 45min
completed: 2026-10-30
status: complete
plan_head_before: 3d9683d25e3c06a716a18159d9edd28e7db24433
plan_head_after: bea0249eda70cef670cf31d2e843ffc446235961
commits: 7

coverage:
  - id: D1
    description: "The Super Admin sees the waiting counts per organization and data type, ticks the review box and confirms once; the API receives the review token once and the card refreshes"
    requirement: HEAL-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsRetentionReview.test.tsx#Retention card (tracer)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every card state: first run, nothing waiting, running, failed last run, loading, load failure, shortened and uncountable rows, singular forms, thousands separators, paging (25 per page, Loading..., failed page retry), refresh that keeps loaded rows"
    requirement: HEAL-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsRetentionReview.test.tsx (21 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The dialog cannot confirm by accident or on stale counts: checkbox gate, no keyboard submit, backdrop does not close, one request per click, 409 replaces confirm with Reload review, 403 closes with a toast, failure copy with and without a server message, snapshot token"
    requirement: HEAL-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsRetentionConfirmDialog.test.tsx (12 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The retention components are scanned by the ACTV-08 copy rules on both sides"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual fit of the card (spacing, light and dark, the xl switch between table and cards) in a real browser"
    verification: []
    human_judgment: true
    rationale: "jsdom has no layout or stylesheet; the xl breakpoint switch and the dark theme can only be judged on the published UI, which is the user's step"
---

# Phase 82 Plan 13: Retention card and Confirm deletion dialog Summary

**The Platform health section ends with a Scheduled data retention card: schedule and mode readouts, the table of counts waiting for confirmation, and a Confirm deletion dialog that is gated by a review checkbox, sends one request per click for the token the person actually saw, and turns a stale count into Reload review.**

## Performance

- **Duration:** about 45 min
- **Completed:** 2026-10-30
- **Tasks:** 3 (1 tracer, 2 auto, all TDD)
- **Commits:** 7 (3 RED, 3 GREEN, 1 test follow-up)
- **Files:** 4 created, 8 modified

## Accomplishments

- **Card** (`AutonomousOpsRetentionReview.tsx`, 333 lines): own fetch on mount, every 30 s while the tab is visible and when the page Refresh counter changes; rendered after the health `{doc && ...}` branch, so it shows when the health document failed or the watchdog is not installed. Header: Mode chip with the helper, Next run as `Mon D, YYYY, 02:00 UTC` in a `time` element with the local time in `title`, Last run relative or Never with the counted or deleted helper, the always-visible scope note.
- **States:** blue first-run block naming the date, nothing-waiting line, Running now with Confirm disabled and `A run is in progress. Confirm after it finishes.`, red `Failed: {error}. It tries again at the next run.` alert, three `h-16` plus one `h-40` skeleton under `aria-busy`, load failure with `Reload retention review`.
- **Review rows:** a real table at xl (`hidden xl:table`, sr-only caption, five `scope=col` headers) and stacked `xl:hidden` cards with the Data type, Keeps, Would be deleted, Why labels; `was {m} days`, `Retention period shortened from {m} to {n} days`, `First run`, `Couldn't count` in red; server order kept; `en-US` thousands separators and `tabular-nums`; singular forms; no `truncate` in the file.
- **Paging:** 25 per page, `Showing {n} of {total} rows` (`Showing 1 row`), `Load more rows` showing `Loading...`, a failed page keeps loaded rows and shows `Couldn't load more rows.` with the same button as retry. A changed review token mid-paging refetches from the first page instead of mixing pages.
- **Dialog** (`AutonomousOpsRetentionConfirmDialog.tsx`, 143 lines): `Modal` size md, no close button, backdrop does not close, Esc closes, checkbox is the first focusable element and gates the red button, no keyboard shortcut, `Confirming...` while pending, an in-flight ref so a double click is one request, success toast plus refetch, 409 stale-counts alert with the checkbox reset and `Reload review` in place of confirm, 403 toast plus close plus refetch, `Couldn't confirm deletion: {message}. Try again.` or the fallback, and `{k} rows could not be counted and stay waiting.` in the summary.
- **Copy lists:** both components added to the ACTV-08 JSON and to the expected lists of the TypeScript and Python copy tests.

## Task Commits

1. Task 1 tracer RED: `51e0fcb03` (test)
2. Task 1 GREEN: `b9c05038e` (feat) - card, dialog, section wiring, existing health tests answer the retention fetch
3. Task 2 RED: `be89f852e` (test)
4. Task 2 GREEN: `b772d58ca` (feat) - states, table and cards, paging
5. Task 3 RED: `3f3cfae12` (test)
6. Task 3 GREEN: `da8c33825` (feat) - dialog error paths, copy lists
7. Follow-up: `bea0249ed` (test) - the test-alert health tests answer the retention fetch

Tracer gate: `<verify>` re-run end to end after Task 1 and passed (`Tracer verified end-to-end - expanding`).

## Verification (exact results)

- `npx vitest run src/__tests__/AutonomousOpsRetentionReview.test.tsx src/__tests__/AutonomousOpsRetentionConfirmDialog.test.tsx src/__tests__/AutonomousOpsPlatformHealth.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: `Test Files  4 passed (4)`, `Tests  86 passed (86)`.
- Whole Autonomous Ops group plus the copy test (`src/__tests__/AutonomousOps` and `autonomousOpsCopy.test.ts`): `Test Files  11 passed (11)`, `Tests  262 passed (262)`.
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider`: `19 passed in 0.35s` (the copy test reads files only; no Mongo started).
- `npm run build`: exit 0, `built in 4.94s`, no error lines. Output went to `dist-new/`; nothing was copied to `/var/www`.
- `npx tsc --noEmit -p .`: 0 `error TS` lines (it caught one missing type after a helper move, fixed before the commit).
- Acceptance greps: `AutonomousOpsRetentionReview` in PlatformHealth 2, `confirmRetention` in the dialog 2, `Retention counts waiting for confirmation` in the review file 1, `truncate` 0, `AutonomousOpsRetentionConfirmDialog.tsx` in the three lists 1 each. Line counts: review 333, dialog 143, PlatformHealth 346, tests 399 and 187 (all under 500).

## TDD Gate Compliance

RED then GREEN commits exist for each of the three tasks (`test(82-13)` precedes `feat(82-13)` every time). RED evidence: for Task 1 a throwaway null-rendering stub (not committed) let both target tests run and fail on the planned assertion (the review table never appeared); for Task 2, 17 of 23 failed on the planned missing behavior; for Task 3, 5 behavior tests and the two copy-list tests failed. `gsd_run check tdd-red-evidence` returned `INVALID_RED / invalid_record` for the Task 1 record because vitest's TAP output carries its DOM dump as non-TAP lines (`Non-TAP data in report`); the semantic assessment was done by hand from the per-test error messages and the classifier rejection is recorded here rather than worked around. The tests that passed in RED (Task 2: header, permission gate, refresh, section wiring; Task 3: summary content, pending, Esc, snapshot) describe behavior implemented earlier in the same plan and are characterization tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing health tests broke once the section mounted the retention card**
- **Found during:** Task 1 and again after Task 2 (the card gained an error block)
- **Issue:** `AutonomousOpsPlatformHealth.test.tsx` counted `.card.p-6` elements, used call counters not keyed by URL, and threw on unknown paths; `AutonomousOpsHealthCards.test.tsx` mocks threw on the review path, which became a second `role="alert"`.
- **Fix:** the mocks answer `/retention/review` with a fixture; the skeleton test now expects 5 cards and waits for the retention table; counters ignore the review path.
- **Files modified:** `src/__tests__/AutonomousOpsPlatformHealth.test.tsx`, `src/__tests__/AutonomousOpsHealthCards.test.tsx`
- **Commits:** `b9c05038e`, `bea0249ed`

**2. [Rule 1 - Bug] A malformed review answer crashed the page**
- **Found during:** Task 1 (a test that returned the health document for every URL)
- **Issue:** `state.items.length` on a response without `items` threw during render.
- **Fix:** a response without an `items` array is a load failure (first page and Load more).
- **Files modified:** `components/AutonomousOpsRetentionReview.tsx`
- **Commit:** `b9c05038e`

**3. [Rule 2 - Missing critical] Confirm used the live review token**
- **Found during:** Task 1 design
- **Issue:** with a 30 s poll, the counts under the dialog could change between "reviewed" and "confirmed" and the click would confirm numbers the person never saw.
- **Fix:** the dialog receives a snapshot (token, totals, count time) taken when it opens; test `confirms the counts that were on screen when the dialog opened`.
- **Commit:** `b9c05038e`

### Plan wording that differs from what shipped

- **Second test file.** The plan lists one test file. The dialog tests live in `AutonomousOpsRetentionConfirmDialog.test.tsx` and the shared render/route helpers moved into `_platformHealthHarness.tsx`, so no file passes 500 lines (CLAUDE.md rule).
- **`SECONDARY_BUTTON`** is now exported from `AutonomousOpsHealthCards.tsx` (a one-word change) and imported by the card and the dialog, instead of a third copy.
- **Zero-countable helper.** The UI-SPEC says Confirm is disabled when zero rows are countable "with helper" but gives no wording; the card uses `No row could be counted, so there is nothing to confirm yet.` (not in the spec; change it in one place if the user wants other words).
- **Card-view list label.** `aria-label="Retention rows waiting for confirmation, card view"`, worded so the table caption string appears once in the file (the acceptance grep expects 1).
- **Dialog props.** `RetentionConfirmDialog({open, review, onClose, onConfirmed})` as planned, with `review` a snapshot subset and `onConfirmed` meaning "closed, refetch needed" (also used for 403 and Reload review).

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug, 1 missing critical) plus the wording differences above. **Impact:** none on scope.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-82-42 (accidental or stale confirmation): checkbox gate, no keyboard submit, one request per click, 409 handled with Reload review, all tested. T-82-43 (visibility): Confirm deletion renders only for `control:platform_autonomous_ops` (tested with a tenant-only user), 403 closes with the toast (tested); the server enforces the same permission (82-10).

## Issues Encountered

None blocking. `components/AutonomousOpsActivity.tsx` and `App.tsx` were not touched.

## User Setup Required

None for this plan. The card only appears once the UI is published, which is the user's step; this plan did not copy anything to `/var/www`, restart a service or push. No retention route was called outside mocks and no database was touched.

## Next Phase Readiness

82-14's tenant notices already landed (its SUMMARY exists). Remaining for the phase: UAT of the card on the published UI after the first 02:00 UTC count (visual fit at 1280 px and below, dark theme, one real Confirm deletion by the Super Admin).

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-30*

## Self-Check: PASSED

Created files exist (review, dialog, both test files). Commits `51e0fcb03`, `b9c05038e`, `be89f852e`, `b772d58ca`, `3f3cfae12`, `da8c33825`, `bea0249ed` are ancestors of HEAD. All acceptance greps and the plan verification commands pass as recorded above.
