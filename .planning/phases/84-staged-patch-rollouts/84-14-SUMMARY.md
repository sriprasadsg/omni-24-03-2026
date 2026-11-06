---
phase: 84-staged-patch-rollouts
plan: 14
subsystem: ui
status: complete
tags: [react, patching, rollouts-tab, ring-strip, halt-block, polling, vitest]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-02 services/patchRollouts/types.ts and rolloutCopy.ts (chips, assurance line, link labels); 84-09 GET /api/patch-rollouts, /window and /{id} with server-decided flags and server-written sentences; 84-12 windows.ts and the Settings window panel"
provides:
  - services/patchRollouts/rollouts.ts (fetchRollouts, fetchRollout, fetchWindowStrip, RolloutApiError, rolloutFailure)
  - components/patchRollouts/RolloutsTab.tsx (the Rollouts tab; extension props onStartRequested, renderStartDialog, renderRingsCard, renderRingDetail, renderActions, refreshSignal, onAttentionCount, active)
  - components/patchRollouts/RolloutCard.tsx (card header, ring strip, halt block, completed lines; props renderRingDetail, actions)
  - components/patchRollouts/RolloutChip.tsx (RolloutChip, chipClasses: the shared chip for rolloutCopy ChipSpecs)
  - Rollouts tab on the Patching screen with an amber attention badge; onOpenView wired from App.tsx
affects: [84-15, 84-17, 84-18, 84-19, 84-22]

requirements-completed: [PTCH-01, PTCH-04, PTCH-05]

actuals:
  tokens: 18700
  tasks: 3
  commits: 6
plan_head_before: b007d10a6c7927e88902f0bfc0b4f5b4f8f454f7
plan_head_after: c3623b6f386eaa3696a222ebe28a5f58cf71570d

tech-stack:
  added: []
  patterns:
    - "one sequence-guarded loader for first read, poll, focus, Refresh and action refetch; a background read never touches the loading state and a failed one keeps the last cards"
    - "extension points as optional render props (renderRingDetail, renderActions, renderRingsCard, renderStartDialog): with none given, no control renders"
    - "badge is the dashboard's own limit=1 read on mount and focus; the open tab also reports its count through onAttentionCount"

key-files:
  created:
    - services/patchRollouts/rollouts.ts
    - components/patchRollouts/RolloutsTab.tsx
    - components/patchRollouts/RolloutCard.tsx
    - components/patchRollouts/RolloutChip.tsx
    - src/__tests__/PatchRolloutsTab.test.tsx
    - src/__tests__/PatchRolloutCard.test.tsx
    - src/__tests__/_patchRolloutFixtures.ts
  modified:
    - components/PatchManagementDashboard.tsx
    - App.tsx

key-decisions:
  - "The Open maintenance windows link navigates to the Settings screen (onOpenView('settings')): SettingsDashboard keeps its tab in local state, so it cannot open on the Maintenance tab without changing that file. The link is a button only for a Super Admin or a person holding manage:settings, plain text otherwise"
  - "Review in Needs your decision renders from ring.decisionsLink (the server's per-viewer flag) plus an onOpenView handler; a ring without it shows ring.waitingText"
  - "The shared chip lives in its own RolloutChip.tsx (not in the plan's file list) so 84-17 and 84-18 reuse it for host and health chips"
  - "RolloutsTab is mounted with key={tenantId ?? 'own'} so switching the viewed organization resets its state instead of showing the old organization's cards"
  - "The Show details disclosure state and the ring detail region live in RolloutCard (one ring open at a time, region under the strip); 84-18 only supplies the content"

patterns-established:
  - "Fixtures for rollout screens live in src/__tests__/_patchRolloutFixtures.ts (payload builders card, ring, flags, openWindow, rolloutPage)"

coverage:
  - id: D1
    description: "Rollouts tab sits between OS Patches and Agent Approvals with no emoji; amber badge from a limit=1 read on mount and focus, hidden at zero, silent when the read fails"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutsTab.test.tsx#PatchManagementDashboard Rollouts tab"
        status: pass
    human_judgment: false
  - id: D2
    description: "Calls hit /api/patch-rollouts, /window and /{id}, send tenantId, and a failure carries status and the server sentence"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutsTab.test.tsx#rollouts calls"
        status: pass
    human_judgment: false
  - id: D3
    description: "Assurance line always visible (loading, error, populated); window strip open, closed and none with the zone in mono or 'No time zone set. Windows use UTC.'; Start disabled with a reason line under a stop or with no window"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutsTab.test.tsx#RolloutsTab"
        status: pass
    human_judgment: false
  - id: D4
    description: "Tab states: first-load skeleton and alert, silent background polls, polling paused when hidden or inactive, empty states by ringsSet and canStart, platform state, stop and shadow blocks, Show more rollouts, live region only on a rise"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutsTab.test.tsx#RolloutsTab"
        status: pass
    human_judgment: false
  - id: D5
    description: "Card header, one chip and server detail line per ring state, aria-current on the current ring, group names mono, Review link only with the flag and a handler, halt alert with the second line and the server revert summary, not-reached chip and closes line, singular forms"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutCard.test.tsx"
        status: pass
    human_judgment: false
  - id: D6
    description: "Rollout and ring text is never rendered as markup (T-84-44)"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/PatchRolloutCard.test.tsx#rollout files render server text as text only"
        status: pass
    human_judgment: false
  - id: D7
    description: "With 4 rings the four blocks (min 200px, 16px gaps, 848px) sit on one row at 1280px with the sidebar open and wrap without horizontal scroll when narrower; the tab reads well in light and dark"
    verification: []
    human_judgment: true
    rationale: "Layout at a real viewport width and both themes is not asserted by jsdom tests; the classes are in place (min-w-[200px] flex-1 flex-wrap gap-4) and a person checks it after the UI is published"

duration: 12min
completed: 2026-11-06
---

# Phase 84 Plan 14: Rollouts tab and rollout card Summary

**A Rollouts tab on the Patching screen (window strip, assurance line, 30 s polling list with every loading, empty, error, stop and shadow state, amber attention badge) and the rollout card with its ring strip and honest halt block, all rendering the 84-09 server flags and sentences as React text.**

## Performance

- **Duration:** about 12 min (2026-11-06 20:12 to 20:24 UTC)
- **Tasks:** 3 (all `tdd="true"`)
- **Files:** 7 created, 2 edited (App.tsx by one line)

## Accomplishments
- `rollouts.ts` holds the three calls; a failed call becomes a `RolloutApiError` carrying the server sentence, and the functions are `async` so a missing base path becomes a rejected promise, never a throw during render.
- The Patching screen lists Rollouts between OS Patches and Agent Approvals. Its amber badge counts rollouts needing a person (limit=1 read on mount and on focus, hidden at zero, nothing shown when the read fails).
- `RolloutsTab` shows the header, the assurance line, the window strip (green Window open, outline Window closed, or the amber "Add a maintenance window first." block with Open maintenance windows) and the time zone line in mono. First load shows three `h-24` skeletons with `aria-busy`; background polls (30 s, focus, Refresh, `refreshSignal`) are silent, pause while the document is hidden or the tab is inactive, and a failed poll keeps the last cards. Start rollout renders only with `canStart` and a handler, and is disabled with a reason line under a stop or with no window. The live region speaks only when the attention count rises after a read.
- `RolloutCard` shows the header (name, "2 patches · 12 computers · Started 3 hr ago by Asha", status, Simulation and "n not reached" chips), the ring strip as an `ol` (one `min-w-[200px] flex-1` block per ring with chip, server detail line, mono group names, `aria-current="step"` on the current ring), Review in Needs your decision only with the server's flag and a handler, the red halt alert with the mandatory second line and the server revert summary, and the completed closes line. Show details and the halt actions are optional props for 84-18.

## Task Commits

TDD (each task has a RED test commit, then the implementation):

1. **Task 1: calls and tab mount** - RED `21df4beb2` (test), GREEN `2f5655b5f` (feat)
2. **Task 2: Rollouts tab** - RED `2f8ef7486` (test), GREEN `3fadffb47` (feat)
3. **Task 3: rollout card** - RED `9835b6b23` (test), GREEN `c3623b6f3` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `services/patchRollouts/rollouts.ts` - fetchRollouts, fetchRollout, fetchWindowStrip, RolloutApiError
- `components/patchRollouts/RolloutsTab.tsx` - the tab (331 lines)
- `components/patchRollouts/RolloutCard.tsx` - the card (150 lines)
- `components/patchRollouts/RolloutChip.tsx` - shared chip
- `components/PatchManagementDashboard.tsx` - tab, badge, `onOpenView` prop (463 lines)
- `App.tsx` - `onOpenView={handleSetCurrentView}` on the PatchManagementDashboard line only
- `src/__tests__/PatchRolloutsTab.test.tsx` (39 tests), `PatchRolloutCard.test.tsx` (42 tests), `_patchRolloutFixtures.ts`

## Decisions Made
See key-decisions above. The one a person may want to change: the Open maintenance windows link opens Settings but not its Maintenance tab.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks. Task 1's RED is a module-resolution failure (rollouts.ts did not exist), weak by the INVALID_RED rule; `workflow.tdd_mode` is false so no gate enforced it. Tasks 2 and 3 have genuine assertion RED: 29 of 39 tab tests failed against the Task 1 shell, and 35 of 42 card tests failed against the Task 2 shell (the passing remainder were absence checks that a shell satisfies). The tests were written from the plan and UI-SPEC before the components existed, and all passed on the first full GREEN run apart from one test bug in Task 1 (a call-count assertion that counted unrelated authFetch calls), fixed in the test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task order forces a shell component**
- **Found during:** Task 1 and Task 2
- **Issue:** Task 1 mounts RolloutsTab and Task 2 renders RolloutCard, but those components belong to Tasks 2 and 3.
- **Fix:** Task 1 committed a header-only RolloutsTab; Task 2 committed a name-only RolloutCard; Tasks 2 and 3 replaced them. Nothing ships between commits (all in one plan run).
- **Commits:** 2f5655b5f, 3fadffb47

**2. [Rule 1 - Bug avoided] Fetch helpers made `async`**
- **Found during:** Task 1
- **Issue:** `PatchingUi.test.tsx` mocks `apiService` without `API_BASE`; the badge read threw synchronously during an effect and failed 4 existing tests.
- **Fix:** `fetchRollouts`, `fetchRollout` and `fetchWindowStrip` are `async`, so any failure is a rejected promise the badge read already swallows.
- **Commit:** 2f5655b5f

**3. [Rule 2 - Missing critical] Tab remounts per organization**
- **Found during:** Task 2
- **Issue:** a super admin switching the viewed organization would see the previous organization's cards until the next read.
- **Fix:** the dashboard mounts the tab with `key={tenantId ?? 'own'}`.
- **Commit:** 3fadffb47

**4. [Scope note] Extra file RolloutChip.tsx** (see key-decisions). Not in the plan's `files_modified`; it keeps both components under 500 lines and gives 84-17 and 84-18 one chip implementation.

---

**Total deviations:** 4 (1 bug avoided, 1 missing critical, 1 blocking sequencing, 1 scope note)
**Impact on plan:** none on the plan's truths.

## Issues Encountered
- `App.tsx` carries the user's uncommitted set-password edit (+21/-15). Only my one-line hunk was committed (patch built against `HEAD`, applied with `git apply --cached`); afterwards `git diff --ignore-cr-at-eol --stat HEAD -- App.tsx` still shows exactly 21 insertions and 15 deletions, all the user's.
- `npm run build` left `dist-test/assets/PatchManagementDashboard-DCpk-Aqy.js` shown as deleted in `git status`; that directory is not touched by this plan and was not staged.

## Known Stubs
None. `onStartRequested`, `renderStartDialog`, `renderRingsCard`, `renderRingDetail` and `renderActions` are intentional extension points, not wired anywhere yet: the Start button, the rings card, the ring detail and Resume/Cancel appear when 84-17 and 84-18 supply them. Until then the Rollouts tab is read-only.

## Threat Flags
None beyond the plan's threat model. T-84-44: both files render server text as React text and a test asserts neither contains `dangerouslySetInnerHTML`. T-84-45: every control (Start rollout, Review link, actions) renders only from a server flag or a prop the parent supplied; the server re-checks every write.

## Verification
- `npx vitest run src/__tests__/PatchRolloutCard.test.tsx src/__tests__/PatchRolloutsTab.test.tsx src/__tests__/PatchingUi.test.tsx src/__tests__/rolloutCopy.test.ts src/__tests__/autonomousOpsCopy.test.ts`: 5 files, 122 tests passed (the copy gate scans the new files)
- `npx tsc --noEmit`: no errors in touched files; `npx eslint` on the new and edited files `--max-warnings 0`: clean
- `npm run build`: exit 0 (dist-new only, nothing published)
- Acceptance: `'rollouts'` appears 5 times in the dashboard (at least 2); dashboard 463 lines, RolloutsTab 331, RolloutCard 150 (all under 500); `aria-busy` in RolloutsTab (2); `aria-current` in RolloutCard (1); `dangerouslySetInnerHTML` 0 in both files

## User Setup Required
None. Nothing was deployed, restarted, published or pushed. The Rollouts tab shows on the Patching screen once the UI is published.

## Next Phase Readiness
- 84-17 passes `onStartRequested`, `renderStartDialog` and `renderRingsCard` to `RolloutsTab` (the dashboard mounts it with only `tenantId`, `onOpenView` and `onAttentionCount`, so 84-17 must add its props at that mount line) and can bump `refreshSignal` after Start.
- 84-18 supplies `renderRingDetail` and `renderActions(card, refresh)`; the card owns the Show details toggle and the halt block's button row.
- Known limit: Open maintenance windows opens Settings, not its Maintenance tab.

## Self-Check: PASSED

- Created files exist: rollouts.ts, RolloutsTab.tsx, RolloutCard.tsx, RolloutChip.tsx, both test files and the fixtures file; commits 21df4beb2, 2f5655b5f, 2f8ef7486, 3fadffb47, 9835b6b23, c3623b6f3 are ancestors of HEAD.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
