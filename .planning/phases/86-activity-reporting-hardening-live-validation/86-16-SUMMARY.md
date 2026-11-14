---
phase: 86-activity-reporting-hardening-live-validation
plan: 16
subsystem: ui
tags: [react, vitest, tailwind, autonomous-ops, accessibility, gap-closure]
gap_closure: true
gap_ids: [G-86-5]

requires:
  - phase: 86-activity-reporting-hardening-live-validation
    provides: Going live Organizations table (86-07/86-14) and Statistics per-rule table (86-04)
provides:
  - Going live Organizations table inside its own labelled, focusable overflow-x-auto region
  - Statistics per-rule table inside its own labelled, focusable overflow-x-auto region
  - Organizations card dl one column below sm (chip no longer overlaps Days observed at 320 to 366 px)
  - Structural vitest regression for both tables (wide and card layouts)
  - 86-UI-SPEC.md with measured widths and the scroll-region rule
affects: [86-verify-work, 86-UAT test 5]

plan_head_before: 16bbdda58f9237efa2ba3d7db06f924a01287a52
plan_head_after: 1b7b2857e5dfba1c4f34bc69b3b5d3fb3a935724

actuals:
  tokens: 9000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Wide table component owns its scroll wrapper: div role=region, aria-label = caption, tabIndex 0, min-w-0 overflow-x-auto (RingDetail.tsx:64 precedent)"

key-files:
  created:
    - src/__tests__/autonomousOpsTableScroll.test.tsx
  modified:
    - components/autonomousOpsGoLive/GoLiveOrganizations.tsx
    - components/autonomousOpsStats/StatsRuleTable.tsx
    - .planning/phases/86-activity-reporting-hardening-live-validation/86-UI-SPEC.md

key-decisions:
  - "Fix condition (b) of the AND-gate (nothing scrolls, main's overflow-x-hidden clips) with a per-table scroll region; the 1024 px switch, useWideLayout, App.tsx and all copy stay untouched"
  - "Use as test organization button left as is (Claude's discretion): it already wraps to its longest word and its 16 px overhang at 320 px stays inside the card"
  - "aria-label reuses the existing caption constants (ORG_CAPTION, rulesCaption(days)), so no new copy and the copy gate is untouched"

requirements-completed: [ACTV-05, GATE-09]

coverage:
  - id: D1
    description: "Going live Organizations table scrolls sideways inside its own labelled, focusable region; every Action control reachable at every width"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsTableScroll.test.tsx#Going live organizations table (G-86-5)"
        status: pass
    human_judgment: true
    rationale: "Real layout widths (1024 to 1440 px, sidebar open and collapsed, light and dark) cannot be measured in jsdom; the visual check is UAT test 5 on the published UI"
  - id: D2
    description: "Statistics per-rule table scrolls sideways inside its own labelled, focusable region; Refused and Would have done (simulation) reachable; Show all and glossary outside it"
    requirement: ACTV-05
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsTableScroll.test.tsx#Statistics per-rule table (G-86-5)"
        status: pass
    human_judgment: true
    rationale: "Same as D1: real widths and the visible focus ring need a browser on the published build"
  - id: D3
    description: "Organizations card dl one column below sm, two from sm, simulation cell spans the row"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsTableScroll.test.tsx#stacks the card dl in one column below sm"
        status: pass
    human_judgment: true
    rationale: "The chip overlap at 320 to 366 px is a rendering fact that only a real browser shows"
  - id: D4
    description: "86-UI-SPEC.md records measured widths (884 and 946 px), content-column arithmetic and the scroll-region rule; wrong budget claims removed"
    verification:
      - kind: other
        ref: "Task 3 grep gates on 86-UI-SPEC.md (GATES_PASS)"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-14
status: complete
---

# Phase 86 Plan 16: Table scroll regions (G-86-5) Summary

**Both wide Autonomous Ops tables (Going live Organizations, Statistics per rule) now scroll sideways inside their own labelled, keyboard-focusable overflow-x-auto region, so no column is clipped by main's overflow-x-hidden at any width; the 320 px card chip overlap is fixed and the UI-SPEC carries the measured widths.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-11-14T11:27:50Z
- **Completed:** 2026-11-14T11:33Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- Going live: `OrganizationTable` owns a `div role="region" aria-label={ORG_CAPTION} tabIndex={0} className="min-w-0 overflow-x-auto"` around the table, so Lift shadow mode, Turn shadow mode back on, Use as test organization and Clear test mark are always reachable by scrolling or Tab.
- Statistics: `RuleTable` owns the same wrapper (label `rulesCaption(days)`); `Show all {n} rules` and `What the columns mean` stay outside it.
- Organizations card `dl` is `grid-cols-1 sm:grid-cols-2` with the simulation cell `col-span-full`, so the Shadow mode on chip no longer overlaps Days observed at 320 to 366 px.
- New `autonomousOpsTableScroll.test.tsx` (8 tests, 163 lines) pins the structure for both tables in wide and card layouts.
- 86-UI-SPEC.md corrected: Organizations about 884 px, per-rule about 946 px, content column viewport minus 358 px minus scrollbar (656 px at 1024, 180 px more with the sidebar collapsed), scroll-region rule in sections 2e and 6c, E2 and E10 rows and the Accessibility notes. The wrong 888 px / "inside the 900px budget" claims are gone.

## RED evidence (TDD)

- **Task 1 RED** (before the wrapper existed): `npx vitest run src/__tests__/autonomousOpsTableScroll.test.tsx` gave 2 failed, 1 passed (3 tests). Failing: "sits in its own labelled, focusable overflow-x-auto region" and "keeps the Action header and every action button inside the scroll region", both on `getByRole('region', { name: 'Shadow mode by organization' })` finding no region (the planned assertion, for the intended reason). The card-layout case passed by design: it is a guard that the cards add no tab stop.
- **Task 2 RED**: 8 tests, 4 failed, 4 passed. Failing: the dl case (old `grid-cols-2`), and the three wide per-rule cases (no region). Passing: the three Task 1 cases (guarding), plus the per-rule card-layout case (a guard).
- The Task 2 "Show all outside the region" case fails in RED for the same missing-region reason (the region query throws first); it is meaningful after GREEN because the region exists and the buttons are asserted not contained in it.

## Task Commits

1. **Task 1: Tracer, Organizations table scroll region + test file** - `2a4e2ea4e` (fix; RED and GREEN in one commit, per the plan's single commit)
2. **Task 2: Per-rule table scroll region + card dl one column below sm** - `ad556c174` (fix)
3. **Task 3: UI-SPEC measured widths** - `1b7b2857e` (docs)

**Plan metadata:** committed separately after this SUMMARY (docs: complete plan).

Tracer gate: Task 1 `<verify>` re-run end-to-end (67 tests in the three suites plus eslint) passed before expansion; no human check on the tracer (only `<automated>`), so expansion continued.

## Files Created/Modified

- `src/__tests__/autonomousOpsTableScroll.test.tsx` - G-86-5 structural regression, both tables, wide and card layouts
- `components/autonomousOpsGoLive/GoLiveOrganizations.tsx` - scroll region around the table, card dl one column below sm, JSDoc note
- `components/autonomousOpsStats/StatsRuleTable.tsx` - scroll region around the table, JSDoc note
- `.planning/phases/86-activity-reporting-hardening-live-validation/86-UI-SPEC.md` - measured widths and scroll-region rule

## Test counts and build

- New file: 8 passed.
- Five-suite verify (`autonomousOpsTableScroll`, `autonomousOpsStats`, `autonomousOpsGoLive`, `autonomousOpsGoLiveTestOrg`, `autonomousOpsCopy`): 124 passed (116 existing + 8 new). The plan quoted a 93-test baseline for three suites; the three suites in Task 1's verify held 64 existing tests (67 with the 3 Task 1 cases), and the five-suite total was 116 before this plan. All existing tests, including the card-layout dt order and test-organization flows, still pass.
- `npx eslint --max-warnings 0` clean on the three source/test files; `tsc --noEmit` (gstack typecheck) PASS.
- `npm run build` succeeded; dist-new entry is **`index-BeV-nK0J.js`**.
- `WIDE_QUERY = '(min-width: 1024px)'` count is 1 in each component (switch unchanged).

## Decisions Made

- `Use as test organization` button left as it is (Claude's discretion per the plan): it already wraps down to its longest word and the debug probe shows its 16 px overhang at 320 px stays inside the card.
- The duplicated `useWideLayout` and constants in the two files were left untouched (the UI review's de-duplication finding is not part of G-86-5).

## Deviations from Plan

**1. [Rule 1 - Bug] Test fixture typing**
- **Found during:** Task 1 (the pre-commit typecheck from /verify)
- **Issue:** the ACME and BOLT fixtures copied from the existing test were untyped, so `reasons[].code` widened to `string` and `tsc --noEmit` failed on the new test file
- **Fix:** typed both fixtures as `GoLiveOrganization`
- **Files modified:** src/__tests__/autonomousOpsTableScroll.test.tsx
- **Verification:** typecheck PASS, tests green
- **Committed in:** 2a4e2ea4e

**Total deviations:** 1 auto-fixed (1 bug in the new test). **Impact on plan:** none; no scope change.

## Issues Encountered

None. App.tsx and the user's other uncommitted work were never staged (`git log --name-only --grep='86-16'` lists only this plan's files). The pre-existing flakes (ServiceDeskKnowledgeGaps, FinancePanel) were not hit because the full suite was not run; only the five Phase 86 suites listed in the plan plus typecheck and build.

## Authentication Gates

None.

## Known Stubs

None. No placeholder values introduced.

## Threat Flags

None. The wrappers add only `role`, an `aria-label` from existing copy constants and `tabIndex`; no new endpoint, auth path or server string in an attribute (T-86-33/35 accepted, T-86-34 mitigated by path-by-path staging).

## User Setup Required

None for configuration. **Publish hand-off (the user's, the auto-mode classifier blocks these for agents):** the fix is in the checkout but not live. Build output is `dist-new` (entry `index-BeV-nK0J.js`). Publish it to `/var/www/omni-agent` with your usual `sudo cp`, first keeping a rollback copy of the current `index.html`, which serves `index-BwnVKpDW.js` (confirmed on this VM). Then push the branch and run `/gsd-verify-work 86` to re-run UAT test 5 on the published UI: as a Super Admin (platform scope) and as a tenant admin, sidebar open then collapsed, at 1024, 1100, 1180, 1280 and 1440 px, light and dark, both tables fit or scroll inside their card, every Action control and the Refused and Would have done (simulation) columns reachable by scroll or Tab with a visible focus ring, no horizontal page scroll at 320 px, and the Shadow mode on chip not overlapping Days observed.

## Next Phase Readiness

Gap plan 86-16 is the last open gap plan for Phase 86 per its checker; remaining Phase 86 open items (CR-01 DLP fail-open, WR-01..06, security R1..R4, the T-86-14-03 restart) are outside this plan. Next: publish, push, `/gsd-verify-work 86`.

---
*Phase: 86-activity-reporting-hardening-live-validation*
*Completed: 2026-11-14*

## Self-Check: PASSED

- FOUND: src/__tests__/autonomousOpsTableScroll.test.tsx, GoLiveOrganizations.tsx, StatsRuleTable.tsx, 86-UI-SPEC.md
- FOUND commits: 2a4e2ea4e, ad556c174, 1b7b2857e (all ancestors of HEAD)
- Task 3 grep gates: pass; vitest five suites 124 passed; eslint clean; build OK
