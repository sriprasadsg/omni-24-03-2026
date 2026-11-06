---
phase: 84-staged-patch-rollouts
plan: 18
subsystem: ui
status: complete
tags: [react, patching, ring-detail, resume, cancel, dialogs, vitest]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-14 RolloutsTab and RolloutCard (renderRingDetail point, halt block, silent refetch, RolloutChip); 84-16 POST /api/patch-rollouts/{id}/resume and /cancel with 403/404/409/422 sentences and the canResume, canCancel, resumeBlockedReason, revertRunning card fields; 84-09 ring health rows, failure-rate and soak lines, host rows"
provides:
  - components/patchRollouts/RingDetail.tsx (the ring detail disclosure: health rows, failure-rate and soak lines, hosts table and stacked cards)
  - components/patchRollouts/RolloutDialogs.tsx (ResumeDialog, CancelDialog, HaltActions, hasHaltActions)
  - services/patchRollouts/lifecycle.ts (resumeRollout, cancelRollout)
  - RolloutCard props onChanged and tenantId; every card on the Rollouts tab now offers Show details and, when halted, Resume rollout and Cancel rollout
affects: [84-19, 84-21, 84-22]

requirements-completed: [PTCH-02, PTCH-03, PTCH-04, PTCH-01]

actuals:
  tokens: 25900
  tasks: 3
  commits: 6
plan_head_before: c05ddb54531f9dada29abea1843f2aabe6b96857
plan_head_after: d2bd20084cd300dd7fa5dccaab4fe1c942731e2c

tech-stack:
  added: []
  patterns:
    - "the browser orders and pages what the server sent and writes no health sentence: a missing signal reads Waiting or No data with the server's text, never Passed"
    - "a dialog that must not lose a typed reason: no backdrop close, Esc and the dismiss button disabled while a request is in flight, a failure keeps the dialog open with the server message"
    - "the card offers its own halt actions through an onChanged callback; the optional actions prop still replaces them"

key-files:
  created:
    - components/patchRollouts/RingDetail.tsx
    - components/patchRollouts/RolloutDialogs.tsx
    - services/patchRollouts/lifecycle.ts
    - src/__tests__/PatchRolloutRingDetail.test.tsx
    - src/__tests__/PatchRolloutDialogs.test.tsx
  modified:
    - components/patchRollouts/RolloutCard.tsx
    - components/patchRollouts/RolloutsTab.tsx
    - components/patchRollouts/rolloutCopy.ts

key-decisions:
  - "Resume is shown when the server says canResume OR gives resumeBlockedReason. 84-16 sets canResume false while a computer is being reverted and puts the sentence in resumeBlockedReason, so a literal reading of 'render only with canResume' would hide Resume instead of showing it disabled. A viewer never gets resumeBlockedReason (the server sets it only for someone who can act on a halted rollout), so no button reaches the wrong person."
  - "Resume is also disabled whenever revertRunning is true, even if canResume reads true, with the server sentence (or the same constant) described by aria-describedby."
  - "The ring detail and the halt actions are wired as defaults inside RolloutsTab and RolloutCard (RolloutsTab renderRingDetail ?? RingDetail; RolloutCard builds HaltActions when it gets onChanged and no actions). The extension props still replace them and a bare RolloutCard stays read-only, so 84-14's tests keep their meaning."
  - "Keep halted and Keep rollout are disabled while a request is in flight, in addition to Esc and the backdrop, so the dialog cannot be dismissed mid-request."
  - "The reason is sent trimmed; the textarea takes first focus in the Resume dialog, Keep rollout takes it in the Cancel dialog (first focusable in DOM order)."

patterns-established:
  - "Host ordering and 25-row paging live in RingDetail (orderHosts, HOSTS_PER_PAGE); a parent only passes the ring"

coverage:
  - id: D1
    description: "Ring detail health check: four rows (Install result, Inventory after install, Heartbeat after restart, Services) each with a chip and the server text; Waiting before data, red No data with the halts sentence, Failed, agent-only reads Only the agent service is checked and is not No data, Not checked is an outline chip and never Passed (DEV-2)"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutRingDetail.test.tsx#RingDetail health rows"
        status: pass
    human_judgment: false
  - id: D2
    description: "Failure-rate and soak lines render the server text; the hosts table has Computer, State, Result and Changed with min widths 200, 150, 300 and 150, orders problems first then Waiting then by name, pages at 25 with Show more computers, shows each server Result (never claiming a revert that did not happen), and stacks as cards below lg"
    requirement: PTCH-03
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutRingDetail.test.tsx#RingDetail computers"
        status: pass
    human_judgment: false
  - id: D3
    description: "Show details opens one ring at a time behind aria-expanded; server text, long names and results wrap and are rendered as text (T-84-53)"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutRingDetail.test.tsx#RingDetail on the Rollouts tab"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutRingDetail.test.tsx#renders server text as text, never as markup"
        status: pass
    human_judgment: false
  - id: D4
    description: "Resume dialog: required reason (1 to 500, counter, disabled until a non-space character), green check toast, still-red info toast, in-flight lock, failure kept in the dialog with server message or fallback, 403 closes with the no-permission toast; Cancel dialog: Keep rollout first focus, red Cancel rollout, amber revert line, cancelled toast; no button labelled just Cancel"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutDialogs.test.tsx#ResumeDialog"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutDialogs.test.tsx#CancelDialog"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutDialogs.test.tsx#lifecycle calls"
        status: pass
    human_judgment: false
  - id: D5
    description: "Halt block offers exactly Resume rollout and Cancel rollout from the server flags (T-84-54), Resume disabled with Wait for the revert to finish. while a revert runs and enabled during a stop, no skip control, and the list is read again silently after either succeeds"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutDialogs.test.tsx#Halt block actions on the card"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutDialogs.test.tsx#Halt block actions on the Rollouts tab"
        status: pass
    human_judgment: false
  - id: D6
    description: "The hosts table (800px of column minimums) does not scroll horizontally at 1280px with the sidebar open or closed; the disclosure, dialogs and stacked cards read well in light and dark; a real halt, resume and cancel on a live organization"
    verification: []
    human_judgment: true
    rationale: "Layout at a real viewport width, both themes, and a live halted rollout cannot be asserted by jsdom tests; a person checks them after the UI is published (classes are in place: overflow-x-auto, hidden lg:block, lg:hidden, min-w-[200/150/300/150px])"

duration: 16min
completed: 2026-11-06
---

# Phase 84 Plan 18: Ring detail, Resume and Cancel Summary

**A Show details disclosure under each ring (four health rows with chips, failure-rate and soak lines, a hosts table that becomes stacked cards below lg) and, in the halt block, Resume rollout (typed reason, reports whether the check passed) and Cancel rollout, each behind its own dialog and driven only by the server's flags.**

## Performance

- **Duration:** about 16 min (2026-11-06 23:38 to 23:54 UTC; start time was not captured at the very start, so this is an estimate from the first commit)
- **Tasks:** 3 (all `tdd="true"`)
- **Files:** 5 created, 3 edited (frontend only)

## Accomplishments

- **Ring detail (Task 1).** `RingDetail` renders a Health check `dl` in the fixed order with the four titles, a chip from `SIGNAL_CHIP` and the server text; a signal the server has not sent reads `Waiting` with "Waiting for the install result." and so on, a `no_data` row with no text still says "No data for {signal} counts as a failure, so the ring halts.", and `not_checked` is the outline chip and never Passed. Then the failure-rate and soak lines, then the computers: a table at lg and wider (Computer, State, Result, Changed at 200, 150, 300 and 150px inside `overflow-x-auto`) and stacked `dl` cards below lg. Computers are ordered problems first (Failed, Not reverted), then Waiting, then by name, and paged 25 at a time with Show more computers. Names, results and OS wrap (`break-words`), nothing truncates, and everything is React text. `RolloutsTab` now defaults `renderRingDetail` to it, so every card has Show details with one ring open at a time (the 84-14 card state).
- **Resume and Cancel dialogs (Task 2).** `lifecycle.ts` posts to the 84-16 routes and throws `RolloutApiError` with the status and server sentence. `ResumeDialog`: required reason (textarea, 3 rows, 500 max, `{n}/500` counter, aria-required, disabled until a non-space character), toast "Resuming. {ring} passed its check and the rollout continues." on a green check and an info toast "The health check for {ring} still fails. The rollout stays halted." when the server answers `still_halted`, a red block "Couldn't resume the rollout: {message}. Try again." (or the connection fallback) that keeps the dialog and the typed reason, and a 403 that closes with "You don't have permission to resume rollouts." `CancelDialog`: the contract body, the amber "A revert is still running. It finishes on its own." only while a revert runs, first focus on Keep rollout, red Cancel rollout, toast `Rollout "{name}" cancelled.`. Neither dialog closes on backdrop, and neither closes on Esc or its dismiss button while a request is in flight. No button reads just "Cancel".
- **Halt block actions (Task 3).** `HaltActions` renders Resume rollout and Cancel rollout (secondary, `min-h-10`) from `canResume` and `canCancel`; Resume is disabled with "Wait for the revert to finish." and `aria-describedby` while a revert runs and stays enabled during a stop; there is no skip control. `RolloutCard` takes `onChanged` and `tenantId` and builds `HaltActions` itself when it gets `onChanged` and no `actions`; `RolloutsTab` passes its silent `refresh`, so a successful Resume or Cancel reads the list again with no skeleton.

## Task Commits

TDD, each task with a RED test commit (with an empty shell where a module did not exist yet, so the tests fail on their assertions) and a GREEN commit:

1. **Task 1: ring detail** - RED `575d82f46` (25 of 26 failed), GREEN `c66244a6e`
2. **Task 2: Resume and Cancel dialogs** - RED `c85289c69` (28 of 28 failed), GREEN `736ef5d05`
3. **Task 3: halt block actions** - RED `5ca9150f9` (13 failed), GREEN `d2bd20084`

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified

- `components/patchRollouts/RingDetail.tsx` - the disclosure (164 lines)
- `components/patchRollouts/RolloutDialogs.tsx` - ResumeDialog, CancelDialog, HaltActions (289 lines)
- `services/patchRollouts/lifecycle.ts` - resumeRollout, cancelRollout
- `components/patchRollouts/RolloutCard.tsx` - `onChanged`, `tenantId`, built-in halt actions (159 lines)
- `components/patchRollouts/RolloutsTab.tsx` - default ring detail, passes `onChanged` and `tenantId` (375 lines)
- `components/patchRollouts/rolloutCopy.ts` - `HEALTH_SIGNALS`, `HEALTH_TITLES`, `HEALTH_SIGNAL_NAMES`, `WAIT_FOR_REVERT`, `showMoreComputers`
- `src/__tests__/PatchRolloutRingDetail.test.tsx` (26 tests), `PatchRolloutDialogs.test.tsx` (45 tests)

## Decisions Made

See key-decisions. The one a person may want to review: Resume is shown disabled (not hidden) while a revert runs, which needed the UI to read `resumeBlockedReason` as well as `canResume`.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks, in order. Each RED commit fails on its assertions rather than on a missing module: Task 1 and Task 2 commit an empty shell (`RingDetail` returning null; `lifecycle.ts` throwing, dialogs returning null) with the tests, and Task 3's RED needed no shell because the card ignored the new props (13 of 45 tests failed on missing buttons; the 32 passing were earlier tests plus absence checks). `workflow.tdd_mode` is false, so `gsd_run check tdd-red-evidence` was not run (this plan is `type: execute` and the formats are vitest console output). All tests passed on the first GREEN run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Resume would have been hidden, not disabled, during a revert**
- **Found during:** Task 3
- **Issue:** the plan says Resume renders only with `canResume` and is disabled while a revert runs. 84-16 and `views.py` compute `canResume = can_act and halted and not reverting` and `resumeBlockedReason` for exactly the revert case, so during a revert `canResume` is false and a strict reading never shows the disabled button or its reason line.
- **Fix:** `HaltActions` shows Resume when `canResume` or `resumeBlockedReason` is set, disabled with the server sentence while `revertRunning` or a reason is present. A viewer gets neither field, so the button never reaches someone who cannot act (T-84-54).
- **Files modified:** components/patchRollouts/RolloutDialogs.tsx
- **Commit:** d2bd20084

**2. [Rule 3 - Blocking] The plan's wiring needs files it does not list**
- **Found during:** Task 1 and Task 3
- **Issue:** `RolloutsTab` is what passes `renderRingDetail` to cards and the card had no way to tell its parent to refetch; `rolloutCopy.ts` is where chip titles and shared sentences live (and the copy gate scans the directory).
- **Fix:** `RolloutsTab.tsx` defaults `renderRingDetail` and passes `onChanged` and `tenantId`; `RolloutCard.tsx` takes both props; `rolloutCopy.ts` gained the health titles and the revert sentence. `components/patchRollouts/RolloutsTab.tsx` and `rolloutCopy.ts` are not in `files_modified`.
- **Commits:** c66244a6e, d2bd20084

**3. [Rule 2 - Missing critical] Honest handling of a ring with more computers than the server sent**
- **Found during:** Task 1
- **Issue:** the server's `host_rows` returns at most 25 computers per ring (`HOST_PAGE`) with `hostTotal`, and no route returns more. Client paging alone would silently hide the rest.
- **Fix:** RingDetail shows "Showing {n} of {total} computers." when the payload holds fewer than `hostTotal`, and pages whatever it holds 25 at a time (Show more computers works as soon as the server sends more). The missing route is logged in `deferred-items.md`.
- **Commit:** c66244a6e

**4. [Scope note] Small wording not in the contract**
- "No computers are in this ring." (a ring with no computers), "Showing {n} of {total} computers." and the Cancel 403 toast "You don't have permission to cancel rollouts." (parallel to the contract's Resume 403 toast, which has no Cancel twin). Keep halted and Keep rollout are also disabled in flight.

---

**Total deviations:** 4 (1 bug, 1 blocking, 1 missing critical, 1 scope note)
**Impact on plan:** none on the plan's truths; the only visible difference is where the disabled Resume comes from (see deviation 1).

## Issues Encountered

- None blocking. The possible flake from 84-17 (a first-load-failure test in `PatchRolloutsTab.test.tsx`) did not appear in any of this plan's runs (the file passed in all 4 full runs).
- `npm run build` left no tracked changes; `dist-new/` is gitignored and nothing was published.

## Known Stubs

None. The ring detail renders the server payload; nothing is hardcoded empty. Deferred, not a stub: a ring with more than 25 computers shows its first 25 and the "Showing 25 of N" line, because no route returns the rest (see `deferred-items.md`).

## Threat Flags

None beyond the plan's register. T-84-53: every host name, result, health text, failure line and halt reason is React text, and tests assert that markup in names, results, health text and ring names never becomes an element (no `dangerouslySetInnerHTML`). T-84-54: Resume and Cancel render only from `canResume`, `canCancel` and the server-only `resumeBlockedReason`; the routes re-check `manage:patches` and the session (84-16), and a 403 closes the dialog with a no-permission toast.

## Verification

- `npx vitest run` on PatchRolloutDialogs, PatchRolloutCard, PatchRolloutsTab, PatchRolloutRingDetail, PatchRolloutStartDialog, PatchRolloutRings, RolloutApprovalCard, rolloutCopy, autonomousOpsCopy and PatchingUi: 10 files, 326 tests passed, exit 0 (the copy gate scans the new files)
- `npx tsc --noEmit`: no errors in rollout files; `npx eslint components/patchRollouts services/patchRollouts` and both new test files `--max-warnings 0`: clean
- `npm run build`: exit 0 (dist-new only, nothing published)
- Acceptance: `min-w-[300px]` and `min-w-[200px]` lines in RingDetail.tsx: 2 (at least 2); `Keep halted` in RolloutDialogs.tsx: 2; `Wait for the revert to finish.` in rolloutCopy.ts: 1 (RolloutCard.tsx 0, at least 1 in one of them); RingDetail 164 and RolloutCard 159 lines (both under 500); `/resume` in lifecycle.ts 2

## User Setup Required

None. Nothing was deployed, restarted, published or pushed. The disclosure and the Resume and Cancel buttons show on the Rollouts tab once the UI is published.

## Next Phase Readiness

- 84-19 and later plans can rely on every Rollouts card offering Show details and, when halted and allowed, Resume and Cancel. `renderRingDetail` and `renderActions` still replace the defaults.
- Open: a paged hosts route for rings over 25 computers (deferred-items.md), and a person checking the layout at 1280px and in both themes after publish (D6).

## Self-Check: PASSED

- Created files exist: RingDetail.tsx, RolloutDialogs.tsx, lifecycle.ts, PatchRolloutRingDetail.test.tsx, PatchRolloutDialogs.test.tsx; commits 575d82f46, c66244a6e, c85289c69, 736ef5d05, 5ca9150f9, d2bd20084 are ancestors of HEAD; `git rev-list --count` from the recorded base gives 6.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
