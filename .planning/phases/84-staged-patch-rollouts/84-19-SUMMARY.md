---
phase: 84-staged-patch-rollouts
plan: 19
subsystem: ui
status: complete
tags: [react, patching, rollouts-tab, start-dialog, draft-entry, autonomous-ops, vitest]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-17 StartDialog (draftSuggestionId, unreadable-draft handling) owned by RolloutsTab; 84-14 RolloutsTab flags and PatchManagementDashboard wiring; 84-09 GET /api/patch-rollouts/draft"
provides:
  - "OpenViewPayload {tab: 'rollouts', draft} and the draftRollout opener flag; buildOpenViewHandlers (components/AutonomousOpsRowActions.tsx)"
  - "App state patchingIntent; PatchManagementDashboard props intent and onIntentConsumed; RolloutsTab props intent and onIntentConsumed; exported PatchingIntent type"
  - "OsPatchesTab optional onRollOut prop: the secondary Roll out in rings button beside Refresh"
affects: [84-20, 84-21, 84-22]

requirements-completed: [PTCH-01, PTCH-06]

actuals:
  tokens: 21000
  tasks: 2
  commits: 3
plan_head_before: e2ccb58edd0ec7f403ccfad65224d315d1cad919
plan_head_after: ef172f0a40686df90944ebd63efeed0caa40e89e

tech-stack:
  added: []
  patterns:
    - "a one-shot navigation intent: App stores it, the dashboard copies it into its own state and clears App's at once, the tab clears the copy after acting on it, so a later visit never reopens the dialog"
    - "the opener map stays the only thing threaded through AutonomousOpsActivityList (untouched): the payload rides the existing OpenViewHandlers and a boolean key says whether drafting is offered"
    - "opener calls without a payload keep their old one-argument shape, so existing callers and tests are unchanged"

key-files:
  created:
    - src/__tests__/PatchRolloutDraftEntry.test.tsx
  modified:
    - App.tsx
    - components/AutonomousOpsActivity.tsx
    - components/AutonomousOpsRowActions.tsx
    - components/OsPatchesTab.tsx
    - components/PatchManagementDashboard.tsx
    - components/patchRollouts/RolloutsTab.tsx

key-decisions:
  - "The dialog opens once the Rollouts tab's first read has said whether the viewer may start (not before): a viewer without canStart never gets a dialog, and the intent is still consumed. The dialog's own preflight Checking... state covers the wait after that."
  - "The intent is consumed whether or not the dialog opened (no start access, or the platform organization), so it cannot fire later."
  - "buildOpenViewHandlers lives in AutonomousOpsRowActions.tsx so the screen's wiring is unit-tested without mounting the whole Activity screen."
  - "The Showing x of y line inside a suggestion keeps the plain Open patching link; only the main link becomes Draft a rollout."

patterns-established:
  - "display-only canDraft = view:patching and manage:patches, the same way as the existing canPatch link; the draft route and Start re-check on the server"

coverage:
  - id: D1
    description: "A vulnerability suggestion's link reads Draft a rollout (aria-label with the host) for a viewer who can open Patching and start rollouts, and sends {tab: 'rollouts', draft: suggestion id}; it stays Open patching without start access and plain text without Patching access; file-change rows never offer it; nothing is called on the server"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutDraftEntry.test.tsx#Draft a rollout link on a vulnerability suggestion"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutDraftEntry.test.tsx#buildOpenViewHandlers"
        status: pass
    human_judgment: false
  - id: D2
    description: "A draft intent switches to Rollouts and opens the Start dialog in draft state (name, ticks, blue block), with the removed-count empty case, an unreadable draft, a viewer without start access, and no POST to /api/patch-rollouts before Start; the intent is consumed once and a closed dialog does not return"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutDraftEntry.test.tsx#PatchManagementDashboard opens the Start dialog from an intent"
        status: pass
    human_judgment: false
  - id: D3
    description: "The OS Patches tab shows a secondary Roll out in rings button (min-h-10) beside Refresh only with onRollOut; it switches to Rollouts and opens an empty Start dialog; Deploy All is unchanged"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutDraftEntry.test.tsx#Roll out in rings on the OS Patches tab"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutDraftEntry.test.tsx#PatchManagementDashboard opens the Start dialog from an intent"
        status: pass
    human_judgment: false
  - id: D4
    description: "The link, the new button and the opened dialog look right at real widths in light and dark and read well in sequence (Autonomous Ops to Patching to the dialog)"
    verification: []
    human_judgment: true
    rationale: "Layout of the header button row beside Refresh and the screen-to-screen flow are not asserted by jsdom; a person checks them after the UI is published"

duration: "about 15 min"
completed: 2026-11-07
---

# Phase 84 Plan 19: Entry points into the Start dialog Summary

**A vulnerability suggestion's link becomes Draft a rollout for anyone who can start rollouts and lands on Patching > Rollouts with the Start dialog open on the drafted patches, and the OS Patches tab gets a Roll out in rings button; neither ever stores or starts a rollout.**

## Performance

- **Duration:** about 15 min
- **Tasks:** 2 (both `tdd="true"`); 3 commits (one RED for both, two GREEN)
- **Files:** 1 created, 6 modified

## Accomplishments
- `OpenViewHandlers` entries accept an optional `OpenViewPayload`; `draftRollout: true` (set when the viewer holds view:patching and manage:patches) turns the main link of a vulnerability suggestion into Draft a rollout with the aria-label `Draft a rollout for the vulnerabilities on {host}`. Without it the link stays Open patching, and with no Patching access it is plain text. `AutonomousOpsActivityList.tsx` is untouched.
- `App.tsx` keeps `patchingIntent`; the Autonomous Ops opener stores a payload for Patching and switches view. `PatchManagementDashboard` selects the Rollouts tab from the intent, copies it into its own state and clears App's at once. `RolloutsTab` opens `StartDialog` with `draftSuggestionId` once its first read says the viewer may start, then reports the intent consumed. Closing the dialog drops the draft, so the header Start rollout opens a plain dialog afterwards.
- `OsPatchesTab` has an optional `onRollOut`: a secondary `min-h-10` Roll out in rings button beside Refresh; the dashboard sets an intent with no draft. Deploy All is unchanged.
- Every UI-SPEC S11 state is a test: populated, empty (none still pending: nothing ticked, the removed-count line, Start disabled), error (unreadable draft: no draft block, nothing ticked), partial, and the one-or-several name (the server writes the name; the dialog shows it as sent). A call spy shows no POST to `/api/patch-rollouts` happens until Start.

## Task Commits

1. **RED (both tasks):** `486843fd2` - 22 tests: 17 failed against the 84-17 code (missing `buildOpenViewHandlers`, no link text, no button, no intent), 5 passed (absence checks)
2. **Task 1: Draft a rollout from a vulnerability suggestion** - `2da27876a`
3. **Task 2: Roll out in rings from the OS Patches tab** - `ef172f0a4`

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `components/AutonomousOpsRowActions.tsx` (297 lines), `components/AutonomousOpsActivity.tsx` (144), `components/PatchManagementDashboard.tsx` (482), `components/patchRollouts/RolloutsTab.tsx` (398), `components/OsPatchesTab.tsx` (131)
- `App.tsx`: two type imports, the `patchingIntent` state, two callbacks and two prop changes on their own lines (the file was already over 500 lines)
- `src/__tests__/PatchRolloutDraftEntry.test.tsx` (22 tests)

## Decisions Made
See key-decisions above. The one a person may want to change: the dialog opens after the tab's first read rather than before it, so a viewer who may not start never sees it flash open.

## TDD Gate Compliance

One RED commit covers both tasks (the tests for the OS Patches button and the dashboard intent were written together), then one GREEN per task. RED was real: 17 of 22 tests failed on assertions or a missing export, not on a missing module. `workflow.tdd_mode` is false and the plan is `type: execute`, so no gate enforced it. GREEN needed two small follow-ups, both caught by running the wider suite: the first opener version called `onOpenView('patchManagement', undefined)`, which broke an existing 83 test that asserts the one-argument call, so the opener now calls `go(view)` when there is no payload; and the test for it was updated to say so.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Opener called the navigator with an extra undefined argument**
- **Found during:** Task 1 (wider test run)
- **Issue:** `autonomousOpsResponse.test.tsx` asserts `onOpenView` is called with exactly `'patchManagement'`.
- **Fix:** `buildOpenViewHandlers` passes a payload only when there is one.
- **Files modified:** components/AutonomousOpsRowActions.tsx, src/__tests__/PatchRolloutDraftEntry.test.tsx
- **Commit:** 2da27876a

**2. [Plan wording] The opener builder is a named, exported function**
- The plan describes the change inside `AutonomousOpsActivity.tsx`; the logic moved to `buildOpenViewHandlers` in `AutonomousOpsRowActions.tsx` so it can be unit-tested without mounting the whole screen. `AutonomousOpsActivity.tsx` calls it.

**3. [Plan wording] The dialog opens after the first read**
- The plan says S11 loading opens the dialog at once. Opening before the flags are known could show a dialog to a viewer who may not start, so the tab waits for its first read (a fast call) and then opens it; the dialog's Checking... state covers the preflight wait as specified.

**Total deviations:** 3 (1 bug caught by an existing test, 2 wording notes). **Impact:** none on the plan's truths.

## Issues Encountered
- `App.tsx` carries the user's uncommitted Super Admin set-password edit (+21/-15). Only my hunks were committed (a zero-context patch built against `git show HEAD:App.tsx`, applied with `git apply --cached --unidiff-zero`); afterwards `git diff --ignore-cr-at-eol --stat HEAD -- App.tsx` still shows the user's +21/-15 and nothing of mine.
- `npm run build` writes only `dist-new/` (gitignored, not live).

## Known Stubs
None.

## Threat Flags
None beyond the plan's threat model. T-84-55: the link only opens a dialog; `canDraft` is display only and the draft route and the Start route check on the server. T-84-56: the suggestion id is sent to the draft route, which resolves it inside the caller's tenant (404 otherwise); an unreadable draft opens an ordinary dialog.

## Verification
- `npx vitest run src/__tests__/PatchRolloutDraftEntry.test.tsx src/__tests__/PatchRolloutsTab.test.tsx`: passed (62 tests); the 31 patch, autonomous-ops, rollout and navigation test files together: 763 tests passed
- `npx tsc --noEmit`: no errors in touched files; `npx eslint` on the six touched components and the test `--max-warnings 0`: clean
- `npm run build`: exit 0
- Acceptance: `Draft a rollout` in AutonomousOpsRowActions.tsx 4 (at least 1); `git diff --stat components/AutonomousOpsActivityList.tsx` empty; AutonomousOpsRowActions 297, AutonomousOpsActivity 144, PatchManagementDashboard 482 lines (all under 500); `Roll out in rings` in OsPatchesTab.tsx 1

## User Setup Required
None. Nothing was deployed, restarted, published or pushed.

## Next Phase Readiness
- 84-20 onward can rely on `intent` and `onIntentConsumed` on the dashboard and tab if they need another entry point.
- The UI is unpublished; a person should look at the new button row and the flow from Autonomous Ops after the next publish.

## Self-Check: PASSED

- Created file exists: src/__tests__/PatchRolloutDraftEntry.test.tsx; commits 486843fd2, 2da27876a, ef172f0a4 are ancestors of HEAD.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-07*
