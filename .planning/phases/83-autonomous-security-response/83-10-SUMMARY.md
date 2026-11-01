---
phase: 83-autonomous-security-response
plan: 10
subsystem: autonomous-ops-ui
tags: [autonomous-ops, undo, activity-list, suggestions, react, vitest]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-03 row payload: canUndo, undoHint, incidentId, blockedUntil, suggestion on every Activity row"
  - phase: 83-autonomous-security-response
    provides: "83-07 settings events written to the ledger as control rows"
provides:
  - components/AutonomousOpsRowActions.tsx with RowActions, ResultCell, SuggestionBody, TargetSummary
  - undoAutonomousOpsAction and the AutonomousOpsSuggestion types in services/autonomousOpsApi.ts
  - Undo in the Result cell of Done rows (one click, one request, allowed during a stop)
  - Review link on Pending rows, shown only for a card that is rendered (decisionIds prop on the list)
  - block times filled in local time, the Setting chip, and links out to Patching and File Integrity
affects: [83-18, 83-19, 83-20]

actuals:
  tokens: 13200
  tasks: 2
  commits: 3
plan_head_before: 49dac9ccf9d4ff643edb7b7ec9e58ae54682dad1
plan_head_after: cad2548cfbf268d11551d7c8ac5248e0938935e0

tech-stack:
  added: []
  patterns:
    - "Row actions live in their own file and reach the list through one ResultContext object, so the 460-line list file gained wiring only"
    - "A link out exists for a target only when the screen hands over an opener for it (Partial<Record<view, () => void>>); no opener renders plain text"
    - "The Result wrapper is the focus target after an action (data-result-cell, tabIndex -1); focus moves to it before the row is swapped so it is never left on a removed button"

key-files:
  created:
    - components/AutonomousOpsRowActions.tsx
    - src/__tests__/autonomousOpsResponse.test.tsx
  modified:
    - components/AutonomousOpsActivityList.tsx
    - components/AutonomousOpsActivity.tsx
    - services/autonomousOpsApi.ts
    - App.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The list's onOpenView prop is a map of openers (patchManagement, fimMonitoring), not one function, because the list has to know per target whether to draw a link or plain text; the Activity screen builds the map from view:patching and view:fim"
  - "A server 409 detail is inserted into the error frame without its closing full stop, so it reads 'Couldn't undo this action: This action cannot be undone. Try again.' with one stop"
  - "RowActions takes an optional onStale callback; the list passes a silent reload so a 409 refetches the rows"
  - "The setting chip is neutral (reuses NEUTRAL) with SlidersHorizontalIcon, as assumption A-83-SETTING-CHIP said"

requirements-completed: [ACTV-02, RESP-02, RESP-03]

coverage:
  - id: D1
    description: "A Done row the server marks canUndo shows Undo with its hint in the Result cell; other rows show nothing; two clicks send one POST to /actions/{id}/undo; the button reads Undoing... and is disabled while pending; a stop does not disable it"
    requirement: "ACTV-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsResponse.test.tsx#Undo on Done rows"
        status: pass
    human_judgment: false
  - id: D2
    description: "Success toasts and swaps in the server row and moves focus to the Result cell; breakerTripped shows the info toast and refreshes the status; a 409 shows the server text under the button and refetches; a network failure shows the fallback"
    requirement: "ACTV-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsResponse.test.tsx#Undo on Done rows"
        status: pass
    human_judgment: false
  - id: D3
    description: "{until} and {at} are filled from blockedUntil in local 24-hour time with the full timestamp in title, and read as a dash if blockedUntil is missing"
    requirement: "RESP-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsResponse.test.tsx#Block times and the Setting chip"
        status: pass
    human_judgment: false
  - id: D4
    description: "A Pending row links to #approval-{incidentId} only when decisionIds holds it"
    requirement: "ACTV-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsResponse.test.tsx#Pending rows and the Review link"
        status: pass
    human_judgment: false
  - id: D5
    description: "A grouped suggestion is one row: three ids and +237 more in Target, Show details lists 10 items and Showing 10 of 240; the links render as plain text for a viewer who cannot open the screen; single-signal and correlation suggestions stay ordinary rows"
    requirement: "ACTV-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsResponse.test.tsx#Suggested rows in volume"
        status: pass
    human_judgment: false
  - id: D6
    description: "The Activity table with an Undo button does not scroll sideways at 1280 px, sidebar open and closed, light and dark"
    requirement: "ACTV-02"
    verification: []
    human_judgment: true
    rationale: "Layout needs a real browser after the user publishes the UI; jsdom has no layout. UI-SPEC marks it as a backstop."

duration: 20min
completed: 2026-11-01
status: complete
---

# Phase 83 Plan 10: Undo on the Activity list, and suggestions that stay one quiet row

**An operator can undo a block or a quarantine from the row that reports it, a host with hundreds of vulnerabilities is one row that links to Patching, and block times read in the viewer's local time. The server decides who sees Undo; the browser infers nothing.**

## Performance

- **Duration:** about 20 min
- **Tasks:** 2 (both TDD)
- **Commits:** 3 (1 test, 2 feat), measured from `49dac9ccf` to `cad2548cf`
- **Line counts:** `AutonomousOpsActivityList.tsx` 460 (439 before, limit 480), `AutonomousOpsRowActions.tsx` 264, `AutonomousOpsActivity.tsx` 115, `autonomousOpsApi.ts` 411

## Task Commits

| Task | Commit | Type |
|------|--------|------|
| RED: 20 tests for Undo, Review link, block times, Setting chip, suggestions | `85c2d0a88` | test |
| 1 Undo, Review link, block times, Setting chip, API, copy gate | `061539253` | feat |
| 2 Activity screen and App pass onOpenView by permission | `cad2548cf` | feat |

## What was built

- `RowActions`: the Undo button (`min-h-10`, `RefreshCcwIcon`, `aria-label` `Undo: {action} on {host}`), the hint under it, the red `role="alert"` line, and the `Review in Needs your decision` text button. A ref guards a double click and the button is disabled while pending.
- `ResultCell`: the focusable Result wrapper both layouts share (text, suggestion body, row actions).
- `SuggestionBody` and `TargetSummary`: the link, the `Show details` disclosure (items come with the row, no fetch), and the Target cell of a grouped suggestion (three ids or paths, `+{k} more`, or a count line when no items came).
- `fillBlockTimes`: `{until}` becomes `Mon D, HH:MM` and `{at}` becomes `HH:MM`, 24-hour, local; the result span's `title` carries the full local timestamp.
- `undoAutonomousOpsAction(id, tenantId)` posts to `/autonomous-ops/actions/{id}/undo` and returns `{status, action, breakerTripped}`.
- The `Setting` chip for `two_signal_on`, `two_signal_off`, `block_length_changed` and `watched_services_changed` control rows.
- `AutonomousOpsRowActions.tsx` is on all three copy lists (JSON, pytest, vitest); the vitest file-count assertion went from 14 to 15.

## Deviations from Plan

**1. [Commit boundary] SuggestionBody and TargetSummary shipped in the Task 1 commit**
- They live in the same new file as `RowActions`, so Task 1's commit holds the whole file and the list's Target and Result wiring. Task 2's commit is therefore only the Activity screen and `App.tsx` wiring. The tests for both tasks were committed together as one RED commit. No behaviour changed from the plan.

**2. [Choice] `onOpenView` on the list is a map of openers**
- The plan says the Activity screen passes `onOpenView` wrapped so it is defined only for an allowed target. A single function cannot tell the list whether to draw a link, so the list prop is `Partial<Record<'patchManagement' | 'fimMonitoring', () => void>>`. `AutonomousOpsActivity` keeps the plain `onOpenView(view)` prop the plan names, and `App.tsx` passes `handleSetCurrentView`.

**3. [Rule 2 - small additions the plan did not list]**
- `RowActions` takes `onStale` so a 409 reloads the rows (the plan says the row refetches but names no prop for it).
- `classLine` widened to include `Suggestion only`; the four settings events added to the control event type.
- `src/__tests__/autonomousOpsCopy.test.ts` asserts a file count of 14; changed to 15 for the new file. Files: that test, in the plan's file list.

**Total deviations:** 1 commit-boundary note, 1 choice, 1 set of small additions. **Impact:** none on the plan's truths.

## User-visible sentences the UI-SPEC does not word (please read)

- When a row has no host, the toast and the button's accessible name use `this computer` (`Undo sent to this computer.`, `Undo: Block IP address on this computer`). The UI-SPEC only says `{host}`.
- A server 409 text is shown without its closing full stop inside the frame (see key decisions); the frame itself is the UI-SPEC's.
- `Showing {shown} of {count}.` uses the number of items actually delivered, not a literal 10, and only appears when `count` is larger than the items. The UI-SPEC wording is `Showing 10 of {n}`.
- When `blockedUntil` is missing but the text still holds `{until}` or `{at}`, the token is replaced by an em dash so a raw token never shows.
- No other sentence was written by me. The existing UI-SPEC rows (toasts, hints, labels, the breaker toast, `Review in Needs your decision`) are verbatim.

## Verification Results

- RED run: 18 of 20 new tests failed on behaviour (no Undo button, no Setting chip, no suggestion body, no opener). The 2 that passed were negative cases (no Review link without a card; single-signal row has no disclosure). It was not an ImportError RED, because the new tests go through the existing screen and list.
- Task commands: `npx vitest run src/__tests__/autonomousOpsResponse.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/autonomousOpsCopy.test.ts` 72 passed, exit 0.
- Wave: `npx vitest run src/__tests__` 72 files, 844 tests passed, exit 0.
- `npx tsc --noEmit -p tsconfig.json` exit 0, no output (58 s).
- `npm run build` exit 0, no "error" in the output. It writes to `dist-new` (git-ignored), so it replaced whatever build was there; nothing was published.
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py` 27 passed (private mongod set in the environment; the file needs no database).
- Acceptance greps: `dangerouslySetInnerHTML` in the new file 0; `truncate` 0; list file 460 lines (below 480); the file appears once in the JSON; `onOpenView` in `App.tsx` 1 (committed) .

## Not done / for the user

- Human check from the plan, not done: after the UI is published, at 1280 px with the sidebar open and closed, the Activity table holding an Undo button must not scroll sideways, light and dark. The table column minimums and the Result cell wrapping are unchanged in kind, but nothing here has laid it out in a browser.
- The UI is not published and no version was bumped.
- `decisionIds` is accepted by the list but nothing passes it yet: the Needs your decision section (83-18) must pass the set of incident ids it renders, and give each card `id="approval-{incidentId}"` with `tabIndex={-1}`. Until then no Review link shows (correct per the UI-SPEC).
- `App.tsx` carries user hunks (password handler and others); only the one-line `onOpenView` change was staged, by writing a blob from `HEAD:App.tsx` and `git update-index --cacheinfo`. The working-tree diff still holds the user's hunks and none of mine.
- Not read: `83-RESEARCH.md`, `83-VALIDATION.md`, `83-PATTERNS.md`, `.planning/PROJECT.md`, `.planning/config.json`, the project skills, the execution-context workflow/template/checkpoint/tdd/example reference files (the summary template was only skimmed), UI-SPEC sections 2 and 2a (lines 130 to 199), section 6 and 7 (lines 264 to 305), and STATE.md outside the frontmatter, the head and the tail.

## Requirements

`requirements.mark-complete` was not run. ACTV-02 also needs the approve and deny cards (83-18, 83-19); RESP-02 and RESP-03 span the agent and sweep plans. This plan finishes the Undo half of ACTV-02 and the display of block expiry (RESP-02) and quarantine wording (RESP-03).

## Known Stubs

None.

## Threat Flags

None. T-83-39 (agent strings only as React text, targets never linkified, only the two fixed links navigate), T-83-40 (Undo drawn only from `canUndo`; the route still enforces control and an interactive session) and T-83-41 (ref guard plus disabled state) are covered by tests; no new network surface beyond the existing undo route.

## Self-Check: PASSED

Created and modified files exist on disk (`components/AutonomousOpsRowActions.tsx`, `src/__tests__/autonomousOpsResponse.test.tsx`, this summary); commits `85c2d0a88`, `061539253`, `cad2548cf` are ancestors of HEAD.
