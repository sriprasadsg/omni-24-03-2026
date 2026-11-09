---
phase: 85-first-line-service-desk
plan: 20
subsystem: service-desk-ui
tags: [service-desk, tickets-screen, draft-panel, requester-panel, cited-articles, reply-visibility, pending-customer]
status: complete

requires: [85-02, 85-08, 85-14, 85-18]
provides:
  - "services/serviceDesk/ticketApi.ts: fetchTicketDesk, sendDraft, editAndSendDraft, discardDraft, confirmFixed, stillNeedHelp, fetchCitedArticle, postTicketComment, and mapRequesterKind (the one tested map from stored comment kinds to client kinds)"
  - "components/serviceDesk/CitedArticles.tsx (shared read-only list), RequesterAnswerPanel.tsx, TicketDraftPanel.tsx, ReplyVisibilityPicker.tsx (picker plus CommentMarks and CommentBody), deskUi.tsx (chips, text styles, date words, failure helpers)"
  - "InternalTicketsDashboard.tsx: pending_customer as Waiting on customer (badge, filter, board column), Draft waiting chip (list row and header), draft and requester panels mounted above the tab bar from GET /api/tickets/{id}/service-desk, the picker hooked to the comment composer, comment marks"
affects: [85-21, 85-22, 85-23]

actuals:
  tokens: 28000
  tasks: 3
  commits: 3
plan_head_before: e0d827bda4f477e693da4bd5022d3f6d10958d07
plan_head_after: 08b0b9d84d5602e40dc9780d1714859f49e62476

tech-stack:
  added: []
  patterns:
    - "The server's stored comment kinds are mapped to the client kinds in one function (mapRequesterKind) inside fetchTicketDesk; the server and the 85-01 tracer test stay unchanged"
    - "Panels present what the server flags say (canActOnDraft, blockedReason, canConfirm, canReplyToRequester, isRequester); no client-side derivation of who may act"
    - "The 1,525-line dashboard gains only imports, state, one effect pair, mount points, the status entries, chips and the composer hook-up; every behaviour lives in components/serviceDesk/"

key-files:
  created:
    - components/serviceDesk/CitedArticles.tsx
    - components/serviceDesk/RequesterAnswerPanel.tsx
    - components/serviceDesk/TicketDraftPanel.tsx
    - components/serviceDesk/ReplyVisibilityPicker.tsx
    - components/serviceDesk/deskUi.tsx
    - services/serviceDesk/ticketApi.ts
    - src/__tests__/ServiceDeskTicketPanels.test.tsx
    - src/__tests__/ServiceDeskReplyVisibility.test.tsx
  modified:
    - components/InternalTicketsDashboard.tsx
    - components/serviceDesk/serviceDeskCopy.ts

key-decisions:
  - "Server-to-client kind map (ticketApi.mapRequesterKind): ai_answer -> answer, requester_reply -> you, withdrawn_notice -> withdrawn, handoff_notice -> notice, null (a plain staff reply) -> reply, any kind this build does not know -> notice (never a reply from a person). author null shows IT (R12)."
  - "The draft panel renders whenever the server supplies a draft (it never does for the reporter), not only when canActOnDraft is true: the blocked states of UI-SPEC section 3 (ticket resolved or closed, a person already replied) keep the answer visible with the reason and leave Discard draft, and the no-requester state replaces the actions with its text; all three come with canActOnDraft false from the server."
  - "A staff-only comment still goes through the existing addTicketComment; only a Reply to requester goes through postTicketComment with visibility requester. services/apiService.ts is untouched."
  - "The viewer who raised the ticket never sees a draft: the dashboard hides ai_draft comments and the Reply picker when the server says isRequester, and the list row hides Draft waiting for the reporter (the ticket JSON carries the draft; T-85-77 accepted this, this is the cheap presentation guard)."

requirements-completed: []

coverage:
  - id: R1
    description: "The requester's answer panel: AI-assisted mark, answer, cited articles, footer, return date (R3), replies from IT with the staff name or IT (R12), This fixed it and I still need help with a 1,000-character note, one request per click, and every notice (confirmed, helped, handed to a person, withdrawn with the original hidden, no reply in 3 days as the same hand-off notice, staff resolved, nothing visible renders no panel)"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskTicketPanels.test.tsx (RequesterAnswerPanel: states; RequesterAnswerPanel: This fixed it and I still need help)"
        status: pass
    human_judgment: false
  - id: R2
    description: "Shared cited-article list: collapsed disclosure buttons, one read per article, Loading article..., read-only text in a max-h-64 region, Try again on a failed read, a deleted article keeps its title, text rendered as text"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskTicketPanels.test.tsx (CitedArticles)"
        status: pass
    human_judgment: false
  - id: R3
    description: "The staff draft panel: five zones, Send as is, Edit and send (server length limit, empty or unchanged or over-limit blocked, Back to draft, Esc asks Discard your edits?), Discard this draft? dialog with a red confirm and the toast, Sending... and Discarding... with all actions disabled, the one-line result with focus, failure and fallback copy, 409 already handled, and the blocked states"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskTicketPanels.test.tsx (TicketDraftPanel: the five zones; Send as is; Edit and send; Discard draft; blocked states)"
        status: pass
    human_judgment: false
  - id: R4
    description: "Reply to requester: radiogroup Who can see this comment, Staff only by default and after every send and on ticket switch, posts {text, visibility: requester}, disabled with its reason when the server says no requester, the 400 no_reply_target and network failures shown in plain words, comment marks and the explanatory line"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskReplyVisibility.test.tsx (ReplyVisibilityPicker; CommentMarks and CommentBody; Reply to requester in the comment composer)"
        status: pass
    human_judgment: false
  - id: R5
    description: "pending_customer reads Waiting on customer in the badge, the status filter and a board column; Draft waiting chip in the list row and header; both panels mount above the tab bar and show on every tab; the desk view and the ticket are read again after a desk action"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskReplyVisibility.test.tsx (Waiting on customer (R2); the draft panel and the Draft waiting chip; the requester panel on the ticket)"
        status: pass
    human_judgment: false
  - id: R6
    description: "Visual fit of the panels inside the older slate/teal ticket pane (spacing, the 50vh cap above the tab bar, chips wrapping beside a long comment without overlapping the text), light and dark"
    requirement: "DESK-01"
    human_judgment: true
    rationale: "No test measures layout; the long-comment-with-chips wrap truth is a UI-SPEC backstop item. The user checks it when the UI is published."
---

# Phase 85 Plan 20: The desk on the ticket screen Summary

Staff now send, edit and send, or discard a waiting draft from the ticket, the person who raised the ticket reads the cited answer and says whether it worked, Reply to requester is a deliberate Staff-only-by-default choice with marks on every comment, and a ticket waiting on its requester finally reads Waiting on customer instead of Open.

Duration: about 12 minutes of execution, finished 2026-11-09 05:52 UTC. Tasks: 3. Files: 10 (8 created, 2 modified).

## Accomplishments

- **Task 1 (3c3d10da4), the requester's side.** `ticketApi.ts` holds the seven desk calls the plan names plus `postTicketComment`, each JSDoc-ed with its route and permission and failing with the `AutonomousOpsApiError` of 85-11. `CitedArticles` is the shared read-only list (disclosure buttons, one read per article, loading, error with Try again, deleted keeps its title, `max-h-64` region). `RequesterAnswerPanel` renders every state of UI-SPEC section 4 from the server's requester view and never works out who may act.
- **Task 2 (ba4206723), the staff side.** `TicketDraftPanel` has the five zones, the edit mode (counter from the server's `maxAnswerLength`, Send edit blocked when empty, unchanged or over the limit, Esc asks before dropping edits), the `Discard this draft?` dialog with the red confirm, the one-line result with focus, and every refusal in the server's words.
- **Task 3 (08b0b9d84), the ticket screen.** `ReplyVisibilityPicker` (radiogroup), `CommentMarks` and `CommentBody` (Sent to requester, AI-assisted with Sent by or Posted automatically, Withdrawn with Show original, Draft). In `InternalTicketsDashboard.tsx`: `pending_customer` in `STATUS_META`, the status filter and the board; the Draft waiting chip; both panels above the tab bar; the picker above the comment textarea with its choice sent as `visibility`.

## Server-to-client kind mapping (environment note 2)

`GET /api/tickets/{id}/service-desk` sends the stored comment kind in `requester.items[].kind`. `fetchTicketDesk` maps it with `mapRequesterKind`, the one place, tested in `ServiceDeskTicketPanels.test.tsx`:

| Server (stored) | Client (`types.ts`) |
|-----------------|---------------------|
| `ai_answer` | `answer` |
| `requester_reply` | `you` |
| `withdrawn_notice` | `withdrawn` |
| `handoff_notice` | `notice` |
| `null` (plain staff reply) | `reply` |
| any other kind | `notice` |

The server and the 85-01 tracer test are unchanged. `author` is the profile name from the server; the panel shows `IT` when it is null (R12).

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 3c3d10da4 | feat | Cited articles, the requester's answer panel, the ticket API client |
| 2 | ba4206723 | feat | The staff draft panel |
| 3 | 08b0b9d84 | feat | Reply to requester, comment marks, Waiting on customer, the mount points |

Plan type `execute` with `tdd="true"` tasks: as in 85-01 to 85-19, tests and implementation were written together and committed together per task (no separate RED commit). Mutation checks were run by hand and restored: dropping the unchanged/empty guard of Send edit failed 2 tests; mapping `ai_answer` to `reply` failed 2; dropping `pending_customer` from the board columns failed 1; not resetting the picker on ticket switch failed 1; sending `staff` instead of `requester` failed 1; removing the explicit reset after a send failed 1 (after the test double returned the updated ticket instead of `{}`, which had hidden it). Removing the `busy` ref guard did not fail a test because a disabled button already blocks the second click; it stays as a backstop.

## User's uncommitted work in InternalTicketsDashboard.tsx

The file carries the user's attachment download button (+14/-1). It was edited in the working tree so the tests ran against both. The commit took `git show HEAD:components/InternalTicketsDashboard.tsx`, applied only this plan's edits (the same edit script that produced the working-tree change, each replacement matching exactly once), and staged that copy with `git update-index --cacheinfo`. Checks: the staged diff contains no `downloadTicketAttachment` or `handleDownloadAttachment` line; the HEAD-plus-my-edits copy type-checks on its own (placed temporarily as a component file, `tsc --noEmit` clean, removed); after the commit `git diff --numstat` on the file still shows `14 1`, unstaged. `App.tsx` was not touched.

## Verification

- Task commands: `ServiceDeskTicketPanels.test.tsx` + `autonomousOpsCopy.test.ts` (81 passed) and `ServiceDeskReplyVisibility.test.tsx` + `ServiceDeskTicketPanels.test.tsx` + `autonomousOpsCopy.test.ts` + `serviceDeskCopy.test.ts` (127 passed). The ACTV-08 copy gate scans `components/serviceDesk` and `services/serviceDesk` and passes.
- Full suite `npx vitest run src/__tests__`: 114 files, 1,793 tests passed (1,706 before, plus 58 and 29 new). `npx tsc --noEmit -p .` clean. `npm run build` succeeded (writes the ignored `dist-new/`; nothing was copied anywhere).
- Acceptance greps: `service-desk/articles` in ticketApi.ts 1; exported functions in ticketApi.ts 9; `serviceDeskCopy` in TicketDraftPanel.tsx 1; `pending_customer` in the dashboard 3; panel and picker names in the dashboard 6; new files 89 to 295 lines (the dashboard stays at 1,596 lines, well over the cap before this plan).
- The `/verify` skill was not invoked; its checks (type check, the touched and the full test suites, build) were run directly instead.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] A shared `deskUi.tsx`**
- **Found during:** Task 1
- **Issue:** The chip anatomy, text styles, the red and text buttons, the date words ("Tue 12 Nov", "14:30") and the failure helpers are needed by four components, and the older Autonomous Ops files do not export them. The plan's file list names none.
- **Fix:** `components/serviceDesk/deskUi.tsx` (89 lines) holds them and re-exports `ACCENT_BUTTON`, `SECONDARY_BUTTON` and `HealthNotice`. **Commit:** 3c3d10da4.

**2. [Rule 2 - Missing critical functionality] Two reply failure lines in the copy module**
- **Found during:** Task 3
- **Issue:** A Reply to requester that fails with something other than the 400 `no_reply_target` needed words, and every user-visible string must come from `serviceDeskCopy.ts`.
- **Fix:** `REPLY_PICKER.sendFailed` ("Couldn't send the reply: {message}. Try again.") and `sendFailedFallback`. The 400 `no_reply_target` shows the server text verbatim. **Commit:** 08b0b9d84.

**3. [Rule 1 - Spec conflict] The draft panel is not gated on `canActOnDraft`**
- **Found during:** Task 2
- **Issue:** The plan's truth says the panel renders only while a draft is waiting and `canActOnDraft`, but the UI-SPEC panel-state table (resolved or closed, person already replied, no requester) needs the panel with `canActOnDraft` false, which is exactly what the server sends for them (`canActOnDraft = blocked is None`).
- **Fix:** The panel renders whenever the server supplies `view.draft` (never for the reporter) and reads the rest from `canActOnDraft` and `blockedReason`. Recorded in key-decisions.

**4. [Rule 2 - Missing critical functionality] The requester never sees a draft in the comment list**
- **Found during:** Task 3
- **Issue:** The ticket JSON carries `ai_draft` comments, so the Comments tab and the list chip would show a staff-only draft to the person who raised the ticket.
- **Fix:** When the server says `isRequester`, the dashboard filters `ai_draft` comments out, omits the Reply picker, and the Draft waiting chip is hidden for a reporter in the list. The server remains unchanged (T-85-77 accepted).

**5. [Order] The Task 1 commit holds the first part of the shared test file**
- `ServiceDeskTicketPanels.test.tsx` covers Tasks 1 and 2; the Task 1 commit staged the requester and cited-article part (37 tests, run on its own) and the Task 2 commit the full file, so each commit passes by itself.

**Total deviations:** 5 (1 blocking helper, 2 missing-critical, 1 spec conflict, 1 ordering). **Impact:** none on scope; no architectural change; no server file touched.

## Decisions Made and Notes

- Dates in the panels ("by Tue 12 Nov", the confirmed time) use the viewer's own calendar and clock; the server computes `returnAt` in the tenant's zone, so near midnight in another zone the shown day could differ by one.
- The result line after a send or discard stays until the ticket is switched (the panel is keyed by ticket id); the draft itself is gone from the next desk view.
- The sticky composer was restructured by one wrapper `div` so the picker sits with the textarea (the picker must stay visible while the composer is stuck to the bottom: T-85-76).
- Status quick-action buttons and bulk "Set status" in the dashboard still list only the four old statuses; the plan asked for the badge, the filter and the board only.

## Still open

- **Deep link from Activity (environment note 4).** The plan's dashboard does not take an initial ticket id and `App.tsx` carries user changes, so the 85-16 "Open ticket" link still opens the Tickets screen without selecting the ticket. Not wired here.
- Kanban cards do not show the Draft waiting chip (the spec asks for the list row and the header).
- `on_hold` tickets still fall back to the Open badge (pre-existing, outside this plan).

## Known Stubs

None.

## Threat Flags

None: the plan adds no network endpoint; every call goes to an existing portal route (85-08, 85-14). T-85-76 is mitigated by Staff only as the default, reset after every send and on ticket switch, with the info line naming the reporter; the picker stays disabled (with its reason) when the server says there is no requester.

## Self-Check: PASSED

- Created files exist: CitedArticles.tsx, RequesterAnswerPanel.tsx, TicketDraftPanel.tsx, ReplyVisibilityPicker.tsx, deskUi.tsx, ticketApi.ts, both test files (checked below).
- Commits 3c3d10da4, ba4206723 and 08b0b9d84 are on the branch; `git rev-list --count` from the ledger base gives 3.
- The user's +14/-1 hunk in `components/InternalTicketsDashboard.tsx` is still present, unstaged and uncommitted.
