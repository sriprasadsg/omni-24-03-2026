---
phase: 85-first-line-service-desk
plan: 16
subsystem: service-desk-ui
tags: [service-desk, autonomous-ops, settings-card, activity-rows, undo, vitest, copy-gate]
status: complete

requires: [85-02, 85-04, 85-11]
provides:
  - "services/serviceDesk/settingsApi.ts: fetchDeskSettings, saveDeskSettings, restoreDeskPosting and the window event name DESK_SETTINGS_CHANGED ('service-desk-settings-changed')"
  - "components/serviceDesk: DeskSettingsCard (collapsed card, summary, status line, staged form, one Save), DeskModeGroup (radiogroup and DeskReadiness list), DeskWords, DeskDialogs (PostAnswersDialog, RestorePostingDialog)"
  - "AutonomousOpsActivity mounts DeskSettingsCard directly under AutonomousOpsResponseSettings, same showResponseSettings gate and tenant key"
  - "AutonomousOpsRow.ticketId and ticketNumber, UndoResult.deskBreakerTripped, open-view handler internalTickets(ticketId), DeskTicketLink in the Result cell, desk toasts in the Undo flow"
affects: [85-17, 85-18, 85-20, 85-22]

actuals:
  tokens: 23200
  tasks: 3
  commits: 3
plan_head_before: feeb7571f6c269ffe18f8e612fcbeba99534c581
plan_head_after: ea119853120356a225dfaf5ca9693f4af094eea8

tech-stack:
  added: []
  patterns:
    - "A background read (expand, 60 s poll, window event) never throws away what the person has staged; an older read cannot overwrite a newer save (sequence counter)"
    - "Every control follows a server flag (canManage, canRestore, canUndo); the readiness list renders only the server's posting.blockers"
    - "A desk row is recognised by ticketNumber; it gets the desk's own link, aria-label and toasts, and never the security breaker wording or a Needs your decision link"
    - "Only the Tickets opener is new on the open-view handlers; it is offered only when canReadView('internalTickets') says the viewer may open Tickets"

key-files:
  created:
    - components/serviceDesk/DeskSettingsCard.tsx
    - components/serviceDesk/DeskModeGroup.tsx
    - components/serviceDesk/DeskWords.tsx
    - components/serviceDesk/DeskDialogs.tsx
    - services/serviceDesk/settingsApi.ts
    - src/__tests__/ServiceDeskSettings.test.tsx
    - src/__tests__/ServiceDeskSettingsWords.test.tsx
    - src/__tests__/ServiceDeskActivityRows.test.tsx
    - src/__tests__/_serviceDeskSettingsHarness.tsx
  modified:
    - components/AutonomousOpsActivity.tsx
    - components/AutonomousOpsRowActions.tsx
    - services/autonomousOpsApi.ts
    - src/__tests__/AutonomousOpsActivity.test.tsx

key-decisions:
  - "The readiness list shows only while the SAVED mode is Post answers (UI-SPEC S2 'saved mode is not Post answers: hidden', and the server sends posting.blockers for a saved Post answers only); UI-SPEC 2d's 'staged or saved' cannot be honoured without guessing, which the card must never do"
  - "A tripped breaker reads 'Drafts only (restore needed)' in the summary when the saved mode is drafts, because the server's trip sets mode drafts (85-11 hand-over)"
  - "When the server sends canManage false the card renders read-only (controls disabled, no footer, no Restore); the Phase 83 gate normally keeps such viewers out"
  - "Status chips reuse HealthChip kinds healthy, down, unknown and checking with the desk's labels (Online, Offline, Not checked, Posting, Drafts for now), so no new tone or chip is added"
  - "Selected mode option is a 1px border plus a 1px ring in the neutral dark colour (a 2px outline without a layout shift), never the accent"

requirements-completed: [DESK-01, DESK-02, DESK-04, DESK-05]

coverage:
  - id: D1
    description: "Service desk card under Response settings: collapsed summary variants, status line (Online, Offline, Not checked, typical answer time or not measured, queue limit), loading skeletons, load error with Try again, unreadable and screens-off notices, read on expand and every 60 s while expanded, window-event refresh"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskSettings.test.tsx#Service desk card: collapsed summary; #loading and errors; #status line; #reading the settings"
        status: pass
    human_judgment: false
  - id: D2
    description: "Mode radiogroup (exactly Off, Drafts only, Post answers), readiness list from posting.blockers, breaker block with Restore for canRestore and the Post answers option locked with 'Restore Post answers first.'"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskSettings.test.tsx#Service desk card: modes and readiness; #breaker, screens off and unreadable"
        status: pass
    human_judgment: false
  - id: D3
    description: "The card renders for holders of manage:autonomous_ops in a tenant organization only: not for a viewer without manage, Platform Support or the platform organization, and then makes no request"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskSettings.test.tsx#Service desk card: who sees it on the Autonomous Ops screen"
        status: pass
    human_judgment: false
  - id: D4
    description: "Words: add by Enter or button, casefolded chips, the four inline validation messages, remove, counter, empty line, six built-in rules"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskSettingsWords.test.tsx#Service desk words"
        status: pass
    human_judgment: false
  - id: D5
    description: "One staged Save: words alone, Off and Drafts only without a dialog, Post answers behind its confirm dialog, Restore behind its dialog, 403 closes the form with the toast, 422 shows the server words, one request per click, Esc ignored in flight"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskSettingsWords.test.tsx#Service desk Save; #Post answers to requesters? dialog; #Restore Post answers? dialog"
        status: pass
    human_judgment: false
  - id: D6
    description: "Desk rows in Activity: 'Open ticket {TKT-number}' through the Tickets opener (plain text without it), no decision control, Undo only for canUndo with the desk aria-label, success and Drafts-only toasts, the settings-changed event, refusal text, server result text as sent"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskActivityRows.test.tsx"
        status: pass
    human_judgment: false
  - id: D7
    description: "Wrapping at 320px (summary, status line, long save error, model tag, long readiness text, 200-character ticket title) and the 1-article plural forms"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "break-words classes asserted in ServiceDeskSettingsWords.test.tsx and ServiceDeskActivityRows.test.tsx; no browser check was run"
        status: pass
    human_judgment: true
    rationale: "Layout at a 320px viewport is a visual judgment; jsdom proves only the wrapping classes. The plural 'Help desk article' wording is composed by the server (85-04), not by this plan."
---

# Phase 85 Plan 16: The Service desk card and desk rows in Activity Summary

A tenant admin can now read and change the desk from the Autonomous Ops screen (mode switch with a confirm before Post answers, readiness list straight from the server, own hand-off words, model status, typical answer time, Restore after the breaker), and staff see desk decisions in Activity with an Open ticket link and Undo that says what happened.

Duration: about 16 minutes (01:42 to 01:58 UTC). Tasks: 3. Files: 13 (9 created, 4 modified). Completed 2026-11-09.

## Accomplishments

- **Task 1, the card (89f09144f).** `DeskSettingsCard` is a collapsed `.card` under Response settings with the TicketIcon title button, a one-line summary (mode, model, typical answer time, word count), and an expanded body: unreadable block, breaker block with Restore (only with `canRestore`), the status line with chip, offline explanation, typical answer time and queue limit, the screens-off block, the mode radiogroup, the readiness list and the words. It reads on mount, on expand and every 60 s while expanded (never while collapsed), and when the window event `service-desk-settings-changed` arrives. A read in the background keeps staged changes; a save invalidates reads still in flight. `settingsApi.ts` holds the three calls. The card is mounted next to Response settings under the same gate and tenant key.
- **Task 2, words, Save and dialogs.** `DeskWords` validates like the server (2 to 40 characters, letters and digits of any script plus space, hyphen, apostrophe, ampersand, slash and dot, at most 50, no duplicate after lower-casing) with the four inline `role="alert"` sentences. `DeskDialogs` has `PostAnswersDialog` and `RestorePostingDialog` following `TurnOffRuleDialog` (Modal md, no close button, no backdrop close, Esc ignored in flight, Keep Drafts only in first focus). One Save sends only what changed; Post answers newly chosen opens the dialog first; 403 closes the form with the permission toast; any other refusal shows the server words in the red block, inside the dialog when one is open.
- **Task 3, Activity (ea1198531).** `AutonomousOpsRow` gains `ticketId` and `ticketNumber`, the undo answer gains `deskBreakerTripped`. `DeskTicketLink` renders 'Open ticket {TKT-number}' (14/600, underline, 12px external-link icon) through a new `internalTickets` open-view handler, or plain text when the viewer cannot open Tickets. Desk rows never show a Review-in-decision link. Undo keeps the Phase 83 button and gets the aria-label 'Undo: Post ticket answer on {TKT-number}'; success toasts 'Answer withdrawn. Ticket {TKT-number} went to a person.'; when the withdrawal dropped the desk to Drafts only the info toast is shown and the card is told to read again.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 89f09144f | feat | The Service desk settings card under Response settings (with the words and dialog components the card imports) |
| 2 | b55e88f88 | test | Words, Save and the two confirm dialogs: 32 tests |
| 3 | ea1198531 | feat | Desk rows in Activity: ticket link, Undo and the desk toasts |

Plan type `execute` with tasks marked `tdd="true"`: as in 85-01 to 85-15, tests and implementation were written together per task; Task 2 has no separate production commit (see Deviations).

## Verification

- Task 1 command (`ServiceDeskSettings`, `AutonomousOpsActivity`, `autonomousOpsCopy`): green; 35 card tests.
- Task 2 command (`ServiceDeskSettings`, `autonomousOpsCopy`) plus the new `ServiceDeskSettingsWords.test.tsx` and `serviceDeskCopy.test.ts`: 107 passed across the four files.
- Task 3 command (`ServiceDeskActivityRows`, `AutonomousOpsActivity`, `autonomousOpsDecisions`, `autonomousOpsCopy`) plus `autonomousOpsResponse` and `PatchRolloutDraftEntry`: 146 passed.
- Full suite `npx vitest run src/__tests__`: 112 files, 1706 passed (1623 before, plus 83 new). Exit code read directly.
- `npx tsc --noEmit -p .`: no output (clean, whole project).
- ACTV-08 copy gate: `autonomousOpsCopy.test.ts` and `serviceDeskCopy.test.ts` pass over `components/serviceDesk` and `services/serviceDesk`. Every label comes from `serviceDeskCopy.ts`; the only literals added elsewhere are none.
- Acceptance greps: `DeskSettingsCard` in AutonomousOpsActivity.tsx 2 (needs 2); `/autonomous-ops/service-desk` in settingsApi.ts 6; `PostAnswersDialog|RestorePostingDialog` in DeskDialogs.tsx 2; `deskBreakerTripped` 1 in autonomousOpsApi.ts and 1 in AutonomousOpsRowActions.tsx; `ticketNumber` 5 in AutonomousOpsRowActions.tsx. Line counts: DeskSettingsCard 355, DeskModeGroup 113, DeskWords 109, DeskDialogs 94, settingsApi 33, AutonomousOpsRowActions 343, autonomousOpsApi 483, AutonomousOpsActivity 154; AutonomousOpsActivityList.tsx untouched at 499.
- Mutation checks by hand: removing the duplicate-word check and the Post answers confirm made 8 words and dialog tests fail; removing the desk-breaker branch and the desk exclusion on the decision link made 2 row tests fail. Files were restored from copies before committing.
- No browser run and no `npm run build` here (the orchestrator builds after the wave). Nothing was published.

## Existing tests whose expectation changed

- `AutonomousOpsActivity.test.tsx`: `routeFetch` answers `/api/autonomous-ops/service-desk` with a quiet Drafts only view, because the screen now mounts the card and the old harness threw on an unknown request (which made the card's load error appear in two tests that count alerts). No assertion changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 2 files were committed with Task 1**
- **Found during:** Task 1
- **Issue:** `DeskSettingsCard` imports `DeskWords` and `DeskDialogs`. A Task 1 commit without them would not build.
- **Fix:** Committed the two components with Task 1; Task 2's commit holds its tests (`test(85-16)`), proven by mutation checks.
- **Commits:** 89f09144f, b55e88f88

**2. [Rule 3 - Size cap] Words and dialog tests live in a second test file**
- **Found during:** Task 2
- **Issue:** The plan lists one test file, `ServiceDeskSettings.test.tsx`, but both tasks' tests do not fit under 500 lines.
- **Fix:** `ServiceDeskSettingsWords.test.tsx` (Task 2) and a shared `_serviceDeskSettingsHarness.tsx` (not collected as a test, like the existing `_autonomousOpsCardHarness.tsx`). Task 2's verify command should also name the new file; it was run with it.

**3. [Rule 2 - Missing critical] AutonomousOpsActivity.tsx also computes `canTickets`**
- **Found during:** Task 3
- **Issue:** The plan says the file gains only the import and the mount, but 'plain text when the viewer cannot open Tickets' needs the Tickets opener to depend on the viewer's access.
- **Fix:** `canReadView('internalTickets', currentUser, hasPermission)` feeds `buildOpenViewHandlers` (a new optional `canTickets`). Four lines.
- **Commit:** ea1198531

**Total deviations:** 3 auto-fixed (1 Rule 2, 2 Rule 3). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None.

## Open items and hand-over

- **Post answers dialog blocker block.** The server sends `posting.blockers` only while the saved mode is Post answers (85-11), so when someone newly chooses Post answers from Drafts only the amber 'Answers will stay drafts for now: ...' block has nothing to quote; the card shows it whenever the server sends a blocker, and the readiness list appears as soon as the save returns. Showing the unmet conditions before the save needs the backend view to compute blockers for any mode. Not done here (it would be a guess on the client).
- **Open ticket selects nothing yet.** The link opens the Tickets screen and the id reaches the `internalTickets` handler, but `App.tsx`'s `handleOpenFromAutonomousOps` and `InternalTicketsDashboard` do not accept a ticket to select. Both files carry the user's uncommitted work, so this was left alone; a later plan (85-20 touches ticket detail) or the user can add the intent.
- **Undo is refused until 85-18.** A desk Undo returns 409 `not_undoable` until the desk undo handler is registered; the button still follows `canUndo`, and the 409 text is shown in plain words under it.
- **'Median of the last 1 answers.'** The UI-SPEC gives one timing sentence and no singular form; it is shown as written.
- The 320px wrapping and visual spacing were not checked in a browser (backstop items); the classes are in place.

## Threat Flags

None beyond the plan's register. T-85-60 (controls render from `canManage`, `canRestore`, `canUndo`; tests prove a no-manage card is read-only and a no-restore view has no Restore button) and T-85-61 (Post answers and Restore each need a confirm dialog; nothing is written before it) are covered by tests. T-85-SC accepted: no package installed. No new endpoint was added.

## User WIP preserved

`App.tsx`, `components/InternalTicketsDashboard.tsx`, `backend/tickets_endpoints.py`, `shared/catalogue-gaps.json` and `backend/requirements.txt` still show as modified and unstaged; none was touched. The index was empty after each commit.

## User steps

None for this plan. Not done, by design: UI publish (the card and the Activity changes go live with the next publish), git push, service restarts, live database writes.

## Self-Check: PASSED

- Files: all nine created and four modified files exist and are committed.
- Commits 89f09144f, b55e88f88 and ea1198531 are ancestors of HEAD; `git rev-list --count` from the recorded base gives 3.
- All `<acceptance_criteria>` of the three tasks and the plan-level verification were re-run and pass.
