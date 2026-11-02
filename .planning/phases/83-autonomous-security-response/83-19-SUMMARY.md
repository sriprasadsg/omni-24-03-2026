---
phase: 83-autonomous-security-response
plan: 19
subsystem: autonomous-ops-decisions-ui
tags: [autonomous-ops, approval-cards, confirm-isolation, countdown, react, vitest]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-18 GET /api/autonomous-ops/incidents, POST confirm-isolation, the server-decided line flags; 83-10 decisionIds and the Review link in the Activity list; 83-13 the screen layout"
provides:
  - components/AutonomousOpsDecisions.tsx (the Needs your decision section)
  - components/AutonomousOpsIncidentCard.tsx (AutonomousOpsIncidentCard, formatExpires, formatReverts, LinePatch)
  - services/autonomousOpsIncidentsApi.ts (IncidentCard, IncidentAction, fetchIncidents, approveAction, denyAction, confirmIsolation)
  - blockedUntil on every card line (backend)
affects: [83-20]

actuals:
  tokens: 21000
  tasks: 2
  commits: 3
plan_head_before: 88d13e6069091322c206648822cec32d91bf8960
plan_head_after: eb8c4b8aef3f3a3c784450ef3bb49f858e7af1c1

tech-stack:
  added: []
  patterns:
    - "The server decides every control: a button renders only when its line flag is true; the browser adds only three rules (stop disables Approve and Confirm isolation, shadow hides buttons, a passed deadline disables the card)"
    - "One timer for the whole section: it re-reads the cards and recomputes every countdown from the server's time; no live region on it"
    - "A decision leaves a LinePatch on the line and holds a snapshot of its card, so a card whose last waiting line was just decided stays in place with its settled lines until the next background read"
    - "One click, one request: a ref guard plus the pending state, because two clicks can land before React disables the button"

key-files:
  created:
    - components/AutonomousOpsDecisions.tsx
    - components/AutonomousOpsIncidentCard.tsx
    - services/autonomousOpsIncidentsApi.ts
    - src/__tests__/autonomousOpsDecisionsCards.test.tsx
    - src/__tests__/_autonomousOpsDecisionsHarness.tsx
  modified:
    - components/AutonomousOpsActivity.tsx
    - services/autonomousOpsApi.ts
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts
    - src/__tests__/autonomousOpsDecisions.test.tsx
    - src/__tests__/AutonomousOpsActivity.test.tsx
    - backend/autonomous_ops/incident_views.py
    - backend/tests/test_autonomous_ops_incident_route.py

key-decisions:
  - "Incident client in a new file, not in autonomousOpsApi.ts: that file is 478 lines and the new types and calls would pass 500. It exports failure, getJson and withTenant (three words changed) and the new file imports them. The new file joins the three copy lists with the two components, so the frontend copy-list count is 21."
  - "A settled card stays: after a decision the section refetches at once, but a card the server no longer returns is kept from a snapshot (with the decided line's result) until the next background read, as the UI-SPEC says. The Activity list is told through onDecided, on a separate counter, so it reloads without clearing the held cards."
  - "A deadline in the past disables every button on the card (UI-SPEC and Task 2). The header chip says Expired for an approval deadline and Reverts in under 1 min for an isolation deadline, which never reads negative."
  - "Confirm isolation and Approve are disabled during a stop when either the status poller or the cards payload says so; a platform stop wins over a tenant stop for the wording."

requirements-completed: [ACTV-02, RESP-05, RESP-09]

duration: 50min
completed: 2026-11-02
status: complete
---

# Phase 83 Plan 19: Needs your decision, on the screen

**The approval cards are on the Autonomous Ops screen: one card per incident, one pair of Approve and Deny per action, Confirm isolation with its revert countdown, the kill cards and every state the UI-SPEC lists. No control exists that decides more than one action.**

## What was built

- `AutonomousOpsDecisions.tsx` (222 lines): the section. First load renders nothing; empty renders nothing; a first-load failure renders the heading, the `role="alert"` block and Try again; a failed background read keeps the cards; 10 cards then `Show more incidents`; stop block (amber, platform wording when the platform stop is the one); one `setInterval` of 30 s re-reads and recomputes the chips; focus and the page Refresh also re-read; the polite announcement fires only when the count rises after the first load.
- `AutonomousOpsIncidentCard.tsx` (366 lines): `<article id="approval-{id}" tabIndex={-1}>`, header with host, `Started {relative} · {n} alerts` and the nearest-deadline chip; a `<ul>` of lines with chip, label, target (and the file path of a kill chain), Why, rule id, the blue notice block, What happens (referenced by `aria-describedby`), the `<ol aria-label="Steps">` after a chain was decided, result; Approve and Deny (named `Approve: Kill process powershell.exe on web-01`), `Confirm isolation` with `LockIcon`; `Show {n} more actions` after five lines. `formatExpires` and `formatReverts` are exported pure functions.
- `services/autonomousOpsIncidentsApi.ts`: the 83-18 payload types and `fetchIncidents`, `approveAction`, `denyAction`, `confirmIsolation`.
- `AutonomousOpsActivity.tsx`: the section sits directly under the status card in tenant scope (before Response settings), not in platform scope and not for the platform organization; it reports the rendered incident ids, which go to the Activity list as `decisionIds`; a decision bumps a separate counter so the list reloads.
- Backend (outside the plan's file list, see deviation 2): every card line now carries `blockedUntil`.

## Deviations from Plan

**1. [Rule 3 - Blocking, CLAUDE.md 500-line rule] New file `services/autonomousOpsIncidentsApi.ts`.** The plan puts the client in `autonomousOpsApi.ts` (478 lines). It also made the test file 800 lines, so the tests are split into `autonomousOpsDecisions.test.tsx` (357), `autonomousOpsDecisionsCards.test.tsx` (342) and a harness `_autonomousOpsDecisionsHarness.tsx` (111; the repo already has `_autonomousOpsCardHarness.tsx`). The plan's key link names `fetchIncidents` in `autonomousOpsApi.ts`; it is in the new file instead. Commit `eb8c4b8ae`.

**2. [Rule 1 - Bug in 83-18's payload] A block line showed a raw `{until}`.** A block done earlier in the same incident is a context line whose result is "Blocked for 24 hours, until {until}. Verified ...", and the line had no time to fill it from. Added `blockedUntil` to the line (`incident_views._line`, one line) and to the existing route test; the browser fills it with `fillBlockTimes`. Commit `ff514e34b`.

**3. [Rule 3 - Blocking] `AutonomousOpsActivity.test.tsx` `routeFetch`** needed a handler for the new request (run notes, 83-13); without it two list-error tests saw a second alert. Added an empty-cards default.

**4. [Choice] Two keys.** The Decisions and Response settings siblings both used key `own`; the new one is `decisions-own`.

## TDD note

- RED: `e80a74c20` holds the tests before any component existed. The RED run was **only an import-resolution failure** ("no tests"), not a failing assertion. GREEN came in one pass: 38 of 38, then 43 of 43 after the extra tests below.
- Both tasks' behaviours were implemented together (the card file holds Task 2's isolation line, chain steps and countdown from the start), so there is one feat commit for the two tasks, not one each.
- Mutations (restored after each): removing the stop check on Approve failed 2 tests; removing the card-level disable on a past deadline failed 1; removing the ref guard first survived (two `fireEvent.click` calls each flush a re-render and hit the disabled button), so the two double-click tests now fire both clicks inside one `act` and then failed 2 of 2 without the guard. Clamping a negative time to zero in `minutesLeft` survived because the `< 1` test already covers a past time: the clamp is redundant, not a missing test.

## Verification

- `npx vitest run src/__tests__`: **76 files, 938 tests passed**, exit 0 (this includes the 43 new tests, `AutonomousOpsActivity.test.tsx` 34 and `autonomousOpsCopy.test.ts` with the count now 21).
- `npm run build`: exit 0, built in 6.4 s into git-ignored `dist-new`; nothing was published.
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_incident_route.py backend/tests/test_autonomous_ops_copy.py` on the private mongod (27998): 47 passed.
- `npx tsc --noEmit -p .` filtered to this plan's files: one error in my test (a null cast), fixed and re-run green; I did not read the rest of tsc's output (it is a whole-project run).
- Acceptance greps: `dangerouslySetInnerHTML` count 0 in both components (the test also checks it, and `truncate`, `TimerIcon`, `HourglassIcon`, `UndoIcon`, and that each file is under 500 lines); `<ol` is present in the card; `AutonomousOpsDecisions.tsx` appears once in the banned-terms JSON.
- Not run: the backend suite beyond the two files above, any live restart, publish or deploy. The plan's human check (four roles, light and dark, 640, 1024 and 1280 px, keyboard path, a stop) is end of phase, after the user publishes the UI.
- Cargo recipe: not used, this plan touches no Rust.

## User-visible sentences NOT worded by the UI-SPEC

- Step state words in the ordered list: `Pending`, `Done`, `Failed`, and **`Not run`** for the `skipped` state 83-18 added.
- The load-more failure under `Show more incidents` reuses the section error sentence (`Couldn't load approvals. Check your connection and try again.`).
- The accessible name of a pending Confirm button is `Confirming...` (the spec words no aria-label for it).
- `Show 1 more actions` reads as the spec's template with n = 1 (not singularised, as the plan's behaviour line writes it).
- A 409 `already_handled` shows the server's own text `This decision was already made.`; a 409 whose text contains "expired" is shown as the spec's `This request has expired and counts as denied.`

## Decisions the plan left open, and what I did

- **Cards that settle.** Kept in place from a snapshot until the next background read (focus, 30 s timer, page Refresh); the immediate post-decision read does not clear them.
- **Review link and `decisionIds`.** The ids of every card rendered, including held ones. The UI-SPEC says the link is omitted "if the viewer lacks approval access", but section 9 and the partial state show view-only viewers the cards without buttons; I followed the second, so the link is shown whenever the card is on screen.
- **Platform Support.** Gets the section with the server's false flags: each waiting line says `Waiting for someone with approval access.` and has no buttons.
- **Confirm in shadow mode** is hidden as well as Approve and Deny.

## Carried forward (not fixed here)

- 83-18's "cards that outlive the problem" (an over-budget restart card stays up to 24 hours after the service recovers) is still open; it needs the restart stage to withdraw the card.
- A Suggest-level block or quarantine line has no What happens text (no UI-SPEC wording).
- A-83-LEVEL-SUGGEST (Suggest-level rows appear as approvable lines) still awaits the user's confirmation; the cards show whatever 83-18 sends.
- `REASON_TEXT["range_block"]` never reaches a card (the Why line is rebuilt from the origins), so the refusal-sounding sentence is not on screen here.

## Not read, or read in part

- `83-RESEARCH.md`, `83-PATTERNS.md`, `83-VALIDATION.md`, `PROJECT.md`, `config.json` and `.claude/skills/` were not read. `83-CONTEXT.md`: the decision list (grep of its D-lines, in part truncated to 400 characters each); D-06, D-12, D-15, D-16, D-17 read. `83-UI-SPEC.md`: sections 1 to 4, 9, the copywriting contract, UI considerations, accessibility and recorded assumptions read; the colour, spacing and typography tables only by their summary (I used the existing chip and notice classes of the neighbouring files). `83-18-SUMMARY.md` read in full; `incident_views.py` lines 1 to 60 and 100 to 309.
- STATE.md: read from line 745.

## Threat model

T-83-69: agent strings (host, process, path, reason) are React text only; no `dangerouslySetInnerHTML`, no links; aria labels are built from the same plain strings; a hostile host name is tested as text. T-83-70: ref guard plus pending state; the double-click test fires both clicks before a re-render. T-83-71: buttons render only from the line's `canApprove`, `canDeny` and `canConfirmIsolation`; a view-only caller sees the waiting line. T-83-SC: no package installed.

## Threat Flags

None: no new route or file access; one extra field (`blockedUntil`, a time) on an existing response.

## Known Stubs

None.

## Self-Check: PASSED

Created files exist (`components/AutonomousOpsDecisions.tsx`, `components/AutonomousOpsIncidentCard.tsx`, `services/autonomousOpsIncidentsApi.ts`, both test files, the harness); commits `e80a74c20`, `ff514e34b`, `eb8c4b8ae` are ancestors of HEAD.
