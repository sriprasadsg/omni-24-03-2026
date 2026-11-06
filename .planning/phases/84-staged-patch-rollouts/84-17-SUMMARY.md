---
phase: 84-staged-patch-rollouts
plan: 17
subsystem: ui
status: complete
tags: [react, patching, rollouts-tab, start-dialog, preflight, rollout-rings, vitest]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-09 /api/patch-rollouts routes (pending-patches, preflight, start, draft, rings); 84-14 RolloutsTab with its flags and extension points; 84-02 types.ts and rolloutCopy.ts"
provides:
  - services/patchRollouts/start.ts (fetchPendingPatches, postPreflight, startRollout, fetchDraft, StartApiError with code and rows)
  - services/patchRollouts/rings.ts (fetchRings, saveRings)
  - components/patchRollouts/StartDialog.tsx (Start a rollout dialog; props open, onClose, onStarted, draftSuggestionId, stopped, tenantId, onOpenMaintenance, onOpenRings, onOpenAgentGroups)
  - components/patchRollouts/RingsSettings.tsx (collapsible Rollout rings card; props canManageRings, tenantId, expanded, onExpandedChange, onOpenAgentGroups, onSaved)
  - components/patchRollouts/StartPatchPicker.tsx, StartPreflight.tsx, ringsForm.ts (the dialog's picker and check rows, the rings form logic)
  - RolloutsTab owns both: Start opens the dialog, a started rollout focuses its card, Open rollout rings expands the card
affects: [84-18, 84-19]

requirements-completed: [PTCH-01, PTCH-05, PTCH-07]

actuals:
  tokens: 33600
  tasks: 3
  commits: 6
plan_head_before: 6f84bc772fc400f88f605bc25e5d86c3500cd119
plan_head_after: 348ae643c7b22411132dd5051f783ebb434f922e

tech-stack:
  added: []
  patterns:
    - "a dialog keeps its state in an inner component that mounts only while open, so every open starts clean"
    - "Start's aria-describedby points at the visible text that already says why (name error, Nothing is waiting, Checking..., the first blocker row's detail); one separate reason line only when no visible text carries it (stop, no patch ticked)"
    - "preflight read debounced 300 ms on the selection key, a sequence guard drops stale answers, the previous result stays on screen, and a 409 or 422 reads it again with no delay"
    - "ring form numbers stay text until Save; ringsForm.ts returns problem codes and the card words them"

key-files:
  created:
    - services/patchRollouts/start.ts
    - services/patchRollouts/rings.ts
    - components/patchRollouts/StartDialog.tsx
    - components/patchRollouts/StartPatchPicker.tsx
    - components/patchRollouts/StartPreflight.tsx
    - components/patchRollouts/RingsSettings.tsx
    - components/patchRollouts/ringsForm.ts
    - src/__tests__/PatchRolloutStartDialog.test.tsx
    - src/__tests__/PatchRolloutRings.test.tsx
  modified:
    - components/patchRollouts/RolloutsTab.tsx
    - src/__tests__/PatchRolloutsTab.test.tsx

key-decisions:
  - "RolloutsTab renders StartDialog and RingsSettings itself (the plan's wording), so PatchManagementDashboard.tsx is not edited; 84-19 adds draftSuggestionId to the tab"
  - "Start rollout no longer needs a parent handler: it renders with the server's canStart flag, calls onStartRequested if one is given, and opens the dialog"
  - "A rings form with nothing saved starts as Canary plus a last ring named Everyone else; a new ring is appended and named Ring {n}"
  - "A middle ring with no group is refused on screen with the server's own sentence (Pick at least one group for every ring except the last.); the last ring may have none"
  - "Left out applies the 3-lines-then-and-{k}-more cap to all left_out rows together, including the CANNOT_TAKE reason rows"
  - "A blank rings load result (unreadable settings) still shows the form from defaults so a deliberate Save can repair it; the blue block explains no rollout can start meanwhile"

patterns-established:
  - "The tab passes onOpenView('agentGroups') and onOpenView('settings') to the dialog's links; a link renders as plain text when its handler is absent"

coverage:
  - id: D1
    description: "Start and rings calls hit the 84-09 routes, send the viewed organization, and a failed Start carries the status, the server sentence, the 409 code and the 422 rows"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutRings.test.tsx#start and rings calls"
        status: pass
    human_judgment: false
  - id: D2
    description: "Rollout rings card: collapsed summary, loading, error, unreadable, populated, every validation sentence, Canary fixed, move and remove, 2 to 4 rings, dirty Save and Discard, save failure and 403"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutRings.test.tsx#RingsSettings card"
        status: pass
    human_judgment: false
  - id: D3
    description: "Start dialog form: name default and 60-character cap, patch picker with search, 50 per page and counter, empty, error and long-text states, What will happen block"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutStartDialog.test.tsx#StartDialog: the form"
        status: pass
    human_judgment: false
  - id: D4
    description: "Check before starting comes from the server preflight (debounced 300 ms, Checking... with the previous result kept), Start disabled with aria-describedby for a blocker, a stop, no patch, a blank name or before the first check; Left out singular, plural, 3 then and k more, Show hosts 10 then Showing 10 of n; offline info row"
    requirement: PTCH-05
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutStartDialog.test.tsx#StartDialog: the check before starting"
        status: pass
    human_judgment: false
  - id: D5
    description: "Start sends the trimmed name and ticked ids, toasts (simulation variant), Esc and Close are ignored while in flight, a failure keeps the form, a 409 or 422 reads the check again, nothing is stored before Start"
    requirement: PTCH-07
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutStartDialog.test.tsx#StartDialog: Start"
        status: pass
    human_judgment: false
  - id: D6
    description: "A draft pre-ticks the suggested patches, sets the name, shows the blue block and the removed-count line, and starts nothing; an unreadable draft opens an ordinary dialog"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutStartDialog.test.tsx#StartDialog: a draft from a vulnerability suggestion"
        status: pass
    human_judgment: false
  - id: D7
    description: "Rollouts tab wiring: Start from the header and the empty state, refetch and focus on the new card, Open rollout rings expands the card, the card only with canManageRings, a save reads the list again, links navigate or read as text"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutStartDialog.test.tsx#RolloutsTab starts rollouts and holds the rings card"
        status: pass
    human_judgment: false
  - id: D8
    description: "The dialog and the rings card read well at real widths in light and dark, with a long patch list and four rings"
    verification: []
    human_judgment: true
    rationale: "Layout, scrolling inside max-h-72, the footer arrangement and both themes are not asserted by jsdom; a person checks them after the UI is published"

duration: "146 min wall clock including a usage-limit pause (about 45 min of work)"
completed: 2026-11-06
---

# Phase 84 Plan 17: Start dialog and Rollout rings card Summary

**An operator can set up rings from agent groups and start a rollout from the Rollouts tab: a Start a rollout dialog that picks pending patches, shows the server preflight (blockers, left-out computers, offline computers) and what will happen before anything is stored, plus the collapsible Rollout rings card with every limit checked on screen.**

## Performance

- **Duration:** 146 min wall clock (a usage-limit pause is included); Task 1 and the start of Task 2 ran before it
- **Tasks:** 3 (all `tdd="true"`); 6 commits
- **Files:** 9 created, 2 modified

## Accomplishments
- `start.ts` and `rings.ts` carry the calls; a failed Start is a `StartApiError` with the 409 `already_in_rollout` code and the 422 preflight rows.
- `RingsSettings` collapsed is one button under an `h2` and the saved rings in a line (`Canary (Canary) -> Pilot (Servers) -> Everyone else · 24-hour soak`, written the way the server writes it); expanded it is 2 to 4 ring blocks, each a checkbox row per agent group (a group used by another ring reads `(in Pilot)` and is disabled), soak, and a failure limit after the Canary ring. Save is disabled when clean or invalid, accent when dirty; a 403 closes the form with a toast; a failed save keeps the edits.
- `StartDialog` follows UI-SPEC section 3. The check reads the server preflight 300 ms after the ticks change, keeps the last result while `Checking...`, and Start is disabled with an `aria-describedby` that points at the text already on screen (the first blocker row, `Nothing is waiting to be installed.`, the name error, `Checking...`) or at one reason line when nothing else says it (stop, no patch ticked). Esc and Close are ignored while Start is in flight; a 409 or 422 reads the check again at once.
- `RolloutsTab` now owns the dialog and the card: Start rollout opens it, a started rollout reads the list again and focuses `#rollout-{id}`, Open rollout rings closes the dialog and expands the card, and the card appears under the list only with `canManageRings`.

## Task Commits

TDD, three cycles:

1. **Task 1: calls and rings card** - RED `734da5abc` (test), GREEN `971e4fc56` (feat)
2. **Task 2: Start dialog** - RED `1b3e1b0ce` (test), GREEN `6062552c5` (feat)
3. **Task 3: tab wiring** - RED `d482d5b7e` (test), GREEN `348ae643c` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `services/patchRollouts/start.ts` (91), `rings.ts` (32)
- `components/patchRollouts/StartDialog.tsx` (244), `StartPatchPicker.tsx` (158), `StartPreflight.tsx` (139), `RingsSettings.tsx` (337), `ringsForm.ts` (125)
- `components/patchRollouts/RolloutsTab.tsx` (369, was 331)
- `src/__tests__/PatchRolloutStartDialog.test.tsx` (55 tests), `PatchRolloutRings.test.tsx` (37 tests), `PatchRolloutsTab.test.tsx` (two edits)

## Decisions Made
See key-decisions above. The one a person may want to change: a ring with no name typed gets `Ring {n}` as a default so a new ring never opens with an error showing.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks. RED evidence, honestly graded: Task 1 and Task 2 REDs are module-resolution failures (the modules did not exist), which is weak by the INVALID_RED rule; `workflow.tdd_mode` is false and the plan is `type: execute`, so no gate enforced it, and `gsd_run check tdd-red-evidence` was not run. Task 3's RED is a genuine assertion RED: 8 of 11 new tab tests failed against the 84-14 tab (the other 3 are absence checks a missing feature satisfies). GREEN needed three small test fixes, all test bugs rather than behaviour bugs: a swap test that did not account for the new middle-ring rule, a preflight test that released its promise before the call was made, and a test that matched two `Start rollout` buttons.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extra files to keep every file under 500 lines**
- **Found during:** Tasks 1 and 2
- **Issue:** The plan lists StartDialog.tsx and RingsSettings.tsx only; the preflight rows, the patch picker and the ring form logic would have pushed them past 500 lines.
- **Fix:** `StartPatchPicker.tsx`, `StartPreflight.tsx` and `ringsForm.ts` (all inside the already copy-gated `components/patchRollouts`). The Canary-group sentence stays in `RingsSettings.tsx` (acceptance grep prints 1); `ringsForm.ts` returns problem codes.
- **Commits:** 971e4fc56, 6062552c5

**2. [Rule 3 - Blocking] Existing 84-14 tab tests updated**
- **Found during:** Task 3
- **Issue:** `PatchRolloutsTab.test.tsx` asserted that Start rollout is absent without a parent handler, and its mock answered every URL with a rollout page, so the new rings card read garbage and showed an alert.
- **Fix:** the Start test now says the button renders with `canStart` and opens the dialog; the mock answers `/rings` with an empty settings payload. No 84-14 behaviour changed otherwise.
- **Files modified:** src/__tests__/PatchRolloutsTab.test.tsx
- **Commit:** 348ae643c

**3. [Plan wording] PatchManagementDashboard.tsx not edited**
- The plan wires the dialog inside RolloutsTab, which the handoff note allowed; the dashboard mount line is unchanged. 84-19 adds the intent and `draftSuggestionId` there.

**4. [Rule 2 - Missing critical] Copy for states the contract does not word**
- Added `Couldn't load the patches. Check your connection and try again.`, `No patches match your search.`, `Couldn't check this rollout. Check your connection and try again.` and the reason `Try the check again first.`, each plain English, no banned term (the copy gate passes).

**Total deviations:** 4 (2 blocking, 1 missing critical, 1 note). **Impact:** none on the plan's truths.

## Issues Encountered
- One first-load-failure test in `PatchRolloutsTab.test.tsx` failed once in a first full run and passed in every later run (three more runs of the file, 40 of 40 each time); no cause found, recorded as a possible timing flake in that older test.
- `npm run build` writes only `dist-new/` (not live, gitignored).

## Known Stubs
None.

## Threat Flags
None beyond the plan's threat model. T-84-51: every check shown is the server preflight; the dialog adds none and the server runs it again at Start (a 422 or 409 re-reads it). T-84-52: patch titles, group names and server sentences render as React text only, with a test for each.

## Verification
- `npx vitest run` on `PatchRolloutStartDialog`, `PatchRolloutRings`, `PatchRolloutsTab`, `PatchRolloutCard`, `PatchingUi`, `autonomousOpsCopy`, `rolloutCopy`: 7 files, 214 tests passed
- `npx tsc --noEmit`: no errors in touched files; `npx eslint` on `components/patchRollouts`, `services/patchRollouts` and the three test files `--max-warnings 0`: clean
- `npm run build`: exit 0
- Acceptance: `Pick at least one group for the Canary ring.` in RingsSettings.tsx 1; RingsSettings 337, StartDialog 244, RolloutsTab 369 lines (all under 500); `aria-describedby` in StartDialog 3; `StartDialog|RingsSettings` in RolloutsTab 7

## User Setup Required
None. Nothing was deployed, restarted, published or pushed.

## Next Phase Readiness
- 84-19 passes `draftSuggestionId` and an intent to the tab (the dialog already takes the prop and handles an unreadable draft).
- 84-18 still supplies `renderRingDetail` and `renderActions`; the tab's refresh and focus wiring is unchanged.

## Self-Check: PASSED

- Created files exist: start.ts, rings.ts, StartDialog.tsx, StartPatchPicker.tsx, StartPreflight.tsx, RingsSettings.tsx, ringsForm.ts and both test files; commits 734da5abc, 971e4fc56, 1b3e1b0ce, 6062552c5, d482d5b7e, 348ae643c are ancestors of HEAD.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
