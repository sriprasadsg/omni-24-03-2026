---
phase: 86-activity-reporting-hardening-live-validation
plan: 04
subsystem: autonomous-ops-reporting-ui
tags: [react, vitest, tailwind, autonomous-ops, statistics, simulation]
status: complete

requires:
  - phase: 86-01
    provides: GET /api/autonomous-ops/statistics payload, collapsed StatsCard, reportingCopy.ts, services/autonomousOpsReporting.ts
provides:
  - expanded Statistics card (period pills, headline readout, dashed simulation line, empty and error states)
  - TimeSavedBlock (Estimate chip, always-visible method, read-only minutes-per-kind table)
  - StatsRuleTable (table at lg, stacked cards below, totals row, show-all past 15, column glossary)
  - reportingCopy.ts constants for every fixed string of the card
affects: [86-05, 86-13]

actuals:
  tokens: 12928
  tasks: 2
  commits: 4
plan_head_before: d98f29979eb336d8e0d47863e34e0d3e2af49900
plan_head_after: 3efaa474ea8940f85ad763d4e30603d224e522c0

tech-stack:
  added: []
  patterns:
    - useWideLayout matchMedia hook (lg, defaults to wide when matchMedia is absent), same shape as PartnerPortal
    - a count the server omits renders an em dash, never a zero; the row still renders
    - period or organization change clears the shown payload so skeletons appear in place

key-files:
  created:
    - components/autonomousOpsStats/TimeSavedBlock.tsx
    - components/autonomousOpsStats/StatsRuleTable.tsx
  modified:
    - components/autonomousOpsStats/StatsCard.tsx
    - components/autonomousOpsStats/reportingCopy.ts
    - src/__tests__/autonomousOpsStats.test.tsx

key-decisions:
  - "Refused glossary line is widened to 'blocked by a limit, a never-touch entry or a stop, or nobody answered the approval in time' (flagged assumption A-86-A2); the UI-SPEC section 2e text said only 'a limit or a never-touch entry'. Matches the 86-01 server column (refused + expired + cancelled_by_stop)."
  - "The All rules footer reads the payload totals (not a client-side sum of the visible rows), so it stays correct when only the first 15 rules are listed; its simulation cell is totals.wouldHaveDone only."
  - "The By rule section and glossary are omitted when the payload has no rules, even in shadow mode (the simulation line carries that case); the empty-state card applies only when not shadowOnly, no real decisions, no simulation and no rules."
  - "Below lg the stacked cards carry no All rules card (UI-SPEC defines none); the headline readout already shows the totals."

requirements-completed: [ACTV-05, ACTV-07]

coverage:
  - id: D1
    description: "Period pills 7/30/90 with aria-pressed, refetch and skeletons in place, Updated clock"
    requirement: ACTV-05
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsStats.test.tsx#the period pills"
        status: pass
    human_judgment: false
  - id: D2
    description: "Dashed simulation line and shadow-only behaviour kept apart from the four real headline numbers"
    requirement: ACTV-05
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsStats.test.tsx#the simulation line"
        status: pass
    human_judgment: false
  - id: D3
    description: "Time saved block: Estimate chip, always-visible method, read-only minutes-per-kind table with Total"
    requirement: ACTV-07
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsStats.test.tsx#the Time saved block"
        status: pass
    human_judgment: false
  - id: D4
    description: "Per-rule table with a separate dashed simulation column, totals row, stacked cards below lg, show-all and glossary"
    requirement: ACTV-05
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsStats.test.tsx#the per-rule table (lg and wider)"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsStats.test.tsx#the stacked cards below lg"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual fit at 320px and at lg, light and dark, as drawn by the browser (888px table budget, wrapping minutes table)"
    requirement: ACTV-05
    verification: []
    human_judgment: true
    rationale: "jsdom has no layout engine; overflow, wrapping and the dashed-rule appearance need a real browser pass once the UI is published (86-13)."

duration: ~10min
completed: 2026-11-13
---

# Phase 86 Plan 04: Statistics card, per-rule table and Time saved Summary

**The Statistics card now carries the full UI-SPEC section 2 contract: period pills, the four real headline numbers, a dashed simulation line kept out of every real count, a Time saved block that always shows its Estimate chip and method with a read-only minutes-per-kind table, and a per-rule table (stacked cards below lg) with a separate "Would have done (simulation)" column, totals row, show-all and a column glossary.**

## What was built

- **TimeSavedBlock.tsx** (84 lines): h3 `Time saved` with the outline `Estimate` chip, the 18/600 figure from `formatMinutes`, the method paragraph (always visible, plus the shadow sentence when `shadowOnly`), and a `Show / Hide minutes per kind of action` disclosure opening a real table (`Kind of action`, `Counted`, `Minutes each`, `Subtotal`, `Total` footer). Every perKind row renders, including `Counted 0`; the Total is the sum of the listed subtotals. `break-words` cells, `table-fixed` below `sm` so nothing forces page scroll at 320px.
- **StatsCard.tsx** (now 184 lines): controls row copy from constants; skeletons in place on a period change (the shown payload is cleared when the period or organization changes); expanded loading is four `h-20` cells plus an `h-40` block under `aria-busy`; `EmptyStateCard` `No decisions in the last {n} days` in place of the simulation line, time saved and rules; dashed simulation line with `FlaskConicalIcon` when the period holds simulation rows or shadow mode is on; `By rule` section with `StatsRuleTable`. No write controls exist (read-only), no polling.
- **StatsRuleTable.tsx** (165 lines): table at lg and wider (Rule min 240, seven counts min 72, simulation min 144 = 888px), stacked `li` cards with a two-column `dl` and a dashed-top `Would have done (simulation): {n}` block below lg, defensive sort (fired descending, name, id), muted zeros, em dash for a missing count, `tfoot` `All rules`, first 15 rules with `Show all {n} rules` / `Show fewer rules`, and the `What the columns mean` disclosure.
- **reportingCopy.ts** (now 103 lines): every fixed string of the card, including the method paragraph exactly as UI-SPEC 2d, the glossary, and `plainMinutes` for table cells.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | RED | 2bc7c4b1e | test(86-04): add failing tests for the expanded Statistics card, simulation line and Time saved block |
| 1 | GREEN | f33245903 | feat(86-04): expanded Statistics card with simulation line and Time saved block |
| 2 | RED | a660dde68 | test(86-04): add failing tests for the per-rule table, stacked cards and column glossary |
| 2 | GREEN | 3efaa474e | feat(86-04): per-rule table, stacked cards, totals row and column glossary |

## TDD Gate Compliance

The plan is `type: execute` with both tasks `tdd="true"`; each followed RED then GREEN with no refactor commit needed.

- **RED, Task 1:** 9 of 17 tests failed on assertion errors (missing pills group, simulation line, Time saved block, empty card), not load errors.
- **RED, Task 2:** 11 of 29 tests failed on missing table, cards and glossary (`findByRole` timeouts for the rule table).
- **GREEN:** 17/17 then 29/29 pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in my own test] expandCard and error-state test harness**
- **Found during:** Task 1 GREEN
- **Issue:** the error-state test waited for a `Last N days` summary that does not exist on failure, and its single `mockImplementationOnce` rejection was consumed by the mount fetch while the expand refetch resolved, hiding the error.
- **Fix:** `expandCard` waits for either summary or the failed summary; the error test rejects until a flag flips, then `Try again` resolves.
- **Files modified:** src/__tests__/autonomousOpsStats.test.tsx
- **Commit:** f33245903

**2. [Plan note] Earlier tracer test loosened**
- The 86-01 test `starts collapsed and the toggle flips aria-expanded` used `getByText('Time saved' | 'Estimate' | 'About 30 min')`. The expanded card now shows each twice by spec (readout cell and Time saved block), so those three assertions use `getAllByText`. Changed in the RED commit 2bc7c4b1e, not a behaviour change.

**Flagged assumption A-86-A2 recorded:** the `Refused` glossary line is widened as described under key-decisions.

**Total deviations:** 1 auto-fixed (test harness), 1 plan note. **Impact:** none on the delivered behaviour.

## Verification

- `npx vitest run src/__tests__/autonomousOpsStats.test.tsx src/__tests__/autonomousOpsCopy.test.ts src/__tests__/AutonomousOpsActivity.test.tsx`: 3 files, 89 tests passed.
- `npx vitest run src/__tests__`: 127 files, 2092 tests passed (was 2069 after Wave 1).
- `npm run build`: exit 0 (writes dist-new/ only; nothing published).
- Acceptance greps: `aria-pressed` 1; `This is an estimate, not a measurement` 1; shadow sentence 1; `Would have done (simulation)` in StatsRuleTable.tsx 1 and reportingCopy.ts 1; `border-dashed` in StatsRuleTable.tsx 2; `nobody answered the approval in time` 1; `dangerouslySetInnerHTML` 0 in all three components; every file under 500 lines (test file 450).
- Nothing run against the live database or services; no restart, no publish, no push.

## Known Stubs

None. Every section reads the live payload; `perKind` and `rules` come from the 86-01 endpoint.

## Threat Flags

None. No new endpoint or trust boundary; T-86-06 is mitigated and covered by two tests that render hostile kind labels, rule names and rule ids as text (no `img` or `b` element appears).

## Notes for later plans

- PROH-86-02-UI (no simulation number in a real cell, real totals or green) is covered by the unit tests on cell order, totals and class names; the visual check at 320px and lg is left to the browser pass in 86-13 (coverage item D5).
- `StatsCard` still owns no period state; the screen's `statsDays` is unchanged for the later Export dialog.

## Self-Check: PASSED

Created files exist (TimeSavedBlock.tsx, StatsRuleTable.tsx); commits 2bc7c4b1e, f33245903, a660dde68, 3efaa474e are ancestors of HEAD.
