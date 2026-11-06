---
phase: 84-staged-patch-rollouts
plan: 12
subsystem: ui
status: complete
tags: [react, maintenance-windows, time-zone, change-management, agent-groups, vitest]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-02 services/patchRollouts/types.ts (MaintenanceWindow, WindowBody, WindowStatus, ChangeWindowRow) and the copy-gate directory entries; 84-05 /api/maintenance/* and /api/changes/maintenance-windows; 84-06 ringName on GET /api/agent-groups/"
provides:
  - services/patchRollouts/windows.ts (fetchWindows, createWindow, updateWindow, deleteWindow, fetchTimeZone, saveTimeZone, fetchWindowStatus, fetchChangeWindows, WindowApiError, time zone helpers)
  - components/patchRollouts/MaintenanceWindowDialog.tsx (WindowDialog, DeleteWindowDialog, DAYS)
  - components/patchRollouts/ChangeManagementWindows.tsx (read-only windows list)
  - components/MaintenanceWindowConfig.tsx reworked for zones, light and dark, shared Modal
  - Ring: name chip on Agent Groups
affects: [84-13, 84-14, 84-17, 84-22]

requirements-completed: [PTCH-05, PTCH-01]

actuals:
  tokens: 19600
  tasks: 3
  commits: 6
plan_head_before: 6d1fa4a38f171ecd31d4c13287260d3095b1281d
plan_head_after: 79c66d39fb89ebabc2321e07ab215e65929b251c

tech-stack:
  added: []
  patterns:
    - "a dialog makes its own call and reports back (onSaved / onDeleted), so the screen only reloads"
    - "an inner form component mounts only while the dialog is open, so its state resets without effects"
    - "a server 422 sentence is shown as-is inside a fixed lead-in; with no sentence the screen shows its own fallback"

key-files:
  created:
    - services/patchRollouts/windows.ts
    - components/patchRollouts/MaintenanceWindowDialog.tsx
    - components/patchRollouts/ChangeManagementWindows.tsx
    - src/__tests__/MaintenanceWindows.test.tsx
    - src/__tests__/ChangeManagementWindows.test.tsx
  modified:
    - components/MaintenanceWindowConfig.tsx
    - components/ChangeManagementDashboard.tsx
    - components/AgentGroupsDashboard.tsx

key-decisions:
  - "Time zone names are checked with the browser's Intl.DateTimeFormat (accepts Asia/Kolkata) instead of requiring membership in Intl.supportedValuesOf('timeZone'): current Chrome lists the canonical Asia/Calcutta, so a strict list check would refuse the spec's own example. The datalist still comes from supportedValuesOf plus UTC; the server stays the final check."
  - "Settings cards carry an Edit (pencil) icon button beside Delete so the Edit maintenance window dialog the spec defines is reachable"
  - "Manage in Settings in Change Management is plain text for now: ChangeManagementDashboard has no view-change handler and App.tsx mounts it with no props, so no onOpenSettings is passed. ChangeManagementWindows accepts the prop for when a later plan wires it."
  - "The Agent Groups chip uses slate colours, not light/dark pairs, because every group card on that screen is a dark-only slate-800 surface; light-theme gray text would be unreadable there"
  - "A save-failure server sentence has its trailing full stop stripped before the lead-in so the line never reads '..first.. Try again.'"

patterns-established:
  - "Dialog footers say what staying means (Close without saving, Keep window); no dialog has a bare Cancel"

coverage:
  - id: D1
    description: "Window calls hit the 84-05 routes and an error carries the server detail"
    requirement: PTCH-05
    verification:
      - kind: unit
        ref: "src/__tests__/MaintenanceWindows.test.tsx#window calls"
        status: pass
    human_judgment: false
  - id: D2
    description: "Add and edit dialog rules: Weekly needs a day, past-midnight and length lines, equal times, 24-hour and one-time end checks, ISO weekdays [6,7], no Monthly, zone required for the first window, Esc blocked in flight"
    requirement: PTCH-05
    verification:
      - kind: unit
        ref: "src/__tests__/MaintenanceWindows.test.tsx#WindowDialog"
        status: pass
    human_judgment: false
  - id: D3
    description: "Delete dialog: first focus on Keep window, last-window amber block, Deleting... and the failure line"
    requirement: PTCH-05
    verification:
      - kind: unit
        ref: "src/__tests__/MaintenanceWindows.test.tsx#DeleteWindowDialog"
        status: pass
    human_judgment: false
  - id: D4
    description: "Settings panel states (loading, empty, error, populated, long text), time zone card rules, banner, delete flow, and no hex or dark-only classes in the file"
    requirement: PTCH-05
    verification:
      - kind: unit
        ref: "src/__tests__/MaintenanceWindows.test.tsx#MaintenanceWindowConfig"
        status: pass
    human_judgment: false
  - id: D5
    description: "Read-only windows list in Change Management: states, five then Show n more, plain-text Manage in Settings, mounted above the filters, changes table unaffected by a failed read"
    requirement: PTCH-05
    verification:
      - kind: unit
        ref: "src/__tests__/ChangeManagementWindows.test.tsx#ChangeManagementWindows"
        status: pass
    human_judgment: false
  - id: D6
    description: "Agent Groups shows an outline Ring: name chip for a group with a ringName, nothing without one, not a link, long names wrap"
    requirement: PTCH-01
    verification:
      - kind: unit
        ref: "src/__tests__/ChangeManagementWindows.test.tsx#Agent Groups ring chip"
        status: pass
    human_judgment: false
  - id: D7
    description: "The reworked screens read well in both themes and the Spatial Glass look is right (spacing, contrast, focus rings)"
    verification: []
    human_judgment: true
    rationale: "Visual quality in light and dark is not asserted by any unit test; the UI is not published, so a person checks it after the publish"

duration: 13min
completed: 2026-11-06
---

# Phase 84 Plan 12: Maintenance windows, Change Management list and ring chip Summary

**Zone-aware maintenance windows in Settings (time zone card, open or closed banner, shared Modal dialogs with ISO weekdays and past-midnight rules), a read-only windows list in Change Management, and a Ring: name chip on Agent Groups**

## Performance

- **Duration:** 13 min
- **Started:** 2026-11-06T19:28:58Z
- **Completed:** 2026-11-06T19:42Z
- **Tasks:** 3
- **Files modified:** 8 (5 created, 3 edited)

## Accomplishments
- windows.ts holds the eight calls the screens need plus time zone helpers; a failed call becomes a `WindowApiError` carrying the server sentence.
- `MaintenanceWindowConfig` is rebuilt on `.card`, `Modal` and tokens (no hex, no hand-built modal, no dark-only classes), with a Time zone card, banner, two-column window cards, and the empty, loading and error states from UI-SPEC section 8. The delete button is always visible.
- The add/edit dialog sends ISO weekday numbers (Saturday and Sunday are `[6, 7]`), explains a window that ends the next day, shows its length, requires a zone for the first window, and never closes on Esc while saving.
- Change Management shows the windows read-only above its filters; a failed windows read shows its own error and leaves the changes table alone.
- Agent Groups shows `Ring: {name}` for a group a ring uses.

## Task Commits

TDD (each task has a RED test commit, then the implementation):

1. **Task 1: window calls and dialogs** - RED `f2fe5456a` (test), GREEN `bafd89af9` (feat)
2. **Task 2: Settings Maintenance panel** - RED `9a96c83f2` (test), GREEN `228a37309` (feat)
3. **Task 3: Change Management list and ring chip** - RED `50c8aa550` (test), GREEN `79c66d39f` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `services/patchRollouts/windows.ts` - window, time zone, status and Change Management calls; zone name helpers
- `components/patchRollouts/MaintenanceWindowDialog.tsx` - WindowDialog, DeleteWindowDialog, DAYS
- `components/patchRollouts/ChangeManagementWindows.tsx` - read-only windows card
- `components/MaintenanceWindowConfig.tsx` - Settings Maintenance panel, rewritten (282 lines)
- `components/ChangeManagementDashboard.tsx` - import and one mount line (476 lines)
- `components/AgentGroupsDashboard.tsx` - ring chip (3 hunks; the user's uncommitted edits to this file were left unstaged)
- `src/__tests__/MaintenanceWindows.test.tsx` (27 tests), `src/__tests__/ChangeManagementWindows.test.tsx` (13 tests)

## Decisions Made
See key-decisions above. The most visible: time zone names are validated by the browser's own `Intl.DateTimeFormat` rather than a strict list match, because current Chrome lists `Asia/Calcutta` and would refuse the spec's `Asia/Kolkata` example.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks. RED evidence for tasks 1 and 3 is a module-resolution failure (the component and service files did not exist yet), not an assertion failure, so by the strict INVALID_RED rule it is weak evidence; `workflow.tdd_mode` is false so no gate enforced it. Task 2's RED is a genuine assertion failure (10 of the new panel tests failed against the old component). Semantic assessment: the behaviours asserted are the planned ones, and all passed on the first GREEN run for tasks 1 and 3, so the tests were not shaped to the implementation after the fact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug avoided] Time zone check relaxed from a strict `supportedValuesOf` list match**
- **Found during:** Task 1 design
- **Issue:** UI-SPEC says the value must be in the supported list, but Chrome's list holds the canonical `Asia/Calcutta`, so `Asia/Kolkata` (the spec's own example) would be refused client-side.
- **Fix:** `isKnownTimeZone` accepts anything `Intl.DateTimeFormat` accepts as written; the datalist is unchanged; the server still has the final check.
- **Files modified:** services/patchRollouts/windows.ts
- **Committed in:** bafd89af9

**2. [Rule 2 - Missing critical] Edit button on window cards**
- **Found during:** Task 2
- **Issue:** the plan builds an Edit maintenance window dialog but the card spec lists only Delete, leaving the edit dialog unreachable.
- **Fix:** a `PencilIcon` button (`aria-label="Edit window {name}"`) beside Delete.
- **Files modified:** components/MaintenanceWindowConfig.tsx
- **Committed in:** 228a37309

**3. [Rule 3 - Blocking] Manage in Settings is plain text in Change Management**
- **Found during:** Task 3
- **Issue:** the plan says to pass the dashboard's Settings handler "if it has one"; ChangeManagementDashboard has none and App.tsx passes it no props.
- **Fix:** `ChangeManagementWindows` takes an optional `onOpenSettings`; the dashboard does not pass one, so the label is plain text (the spec's rule for a viewer who cannot open Settings).
- **Files modified:** components/ChangeManagementDashboard.tsx (mount only)

**4. [Rule 3 - Blocking] Ring chip uses fixed slate colours**
- **Found during:** Task 3
- **Issue:** Agent Groups cards are dark-only (`bg-slate-800`); a light/dark pair would put dark gray text on a dark card in the light theme.
- **Fix:** `border-slate-500 text-slate-200`, matching the card.
- **Files modified:** components/AgentGroupsDashboard.tsx

---

**Total deviations:** 4 (1 bug avoided, 1 missing critical, 2 blocking-context adjustments)
**Impact on plan:** none on scope; each keeps a spec rule working in practice.

## Issues Encountered
- `components/AgentGroupsDashboard.tsx` carried the user's uncommitted edit (+18/-10). My three hunks were committed with a patch built against `HEAD` and applied with `git apply --cached`; afterwards `git diff` on the file still shows exactly the user's 18/10 lines unstaged.
- The old `getMaintenanceWindows`, `createMaintenanceWindow`, `deleteMaintenanceWindow` and `checkMaintenanceStatus` helpers in services/apiService.ts are now unused by this panel; left in place (out of scope).

## Verification
- `npx vitest run src/__tests__/MaintenanceWindows.test.tsx src/__tests__/ChangeManagementWindows.test.tsx`: 40 passed
- copy gate (`autonomousOpsCopy`, `rolloutCopy`) and `SettingsDeepLinkTab`, `QaFixesRegression`: pass
- `npx tsc --noEmit`: no errors in touched files; `npx eslint` on new files and edited files: clean
- `npm run build`: exit 0 (dist-new only, nothing published)
- Acceptance greps: `daysOfWeek` in windows.ts and the dialog; no "monthly" in the dialog; no `bg-[#121212]` and no `fixed inset-0` in MaintenanceWindowConfig; `ChangeManagementWindows` appears twice in the dashboard; `ringName` in AgentGroupsDashboard; line counts 282, 476 (< 500)
- Threat model: no `dangerouslySetInnerHTML` in any new file (T-84-38); write controls rely on the server's 403 and the Settings tab's existing `canManageSettings` gate, and the Change Management list has no writes (T-84-39)

## User Setup Required
None - no external service configuration required. The UI is built to dist-new/ but not published; publishing is the user's step.

## Next Phase Readiness
Windows, zone and the ring chip are ready for the Rollouts tab (84-13/14) to link to. Note for the user: `Manage in Settings` stays plain text until a later plan passes a handler.

## Self-Check: PASSED

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
