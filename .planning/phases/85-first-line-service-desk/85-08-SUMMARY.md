---
phase: 85-first-line-service-desk
plan: 08
subsystem: service-desk
tags: [service-desk, comments, visibility, notifications, tenant-feed, information-disclosure]
status: complete

requires: [85-01]
provides:
  - "AddCommentRequest.visibility (staff | requester, default staff); tickets_service.add_comment(visibility=) stores it on the comment"
  - "POST /api/tickets/{id}/comments refuses a requester reply 400 (messages.API_DETAIL no_reply_target) on an automated ticket or one the requester cannot read"
  - "ticket_notifications.notify_comment_added(visibility=): staff notices carry no preview, skip the reporter, tagged metadata.audience ticket_staff; requester notices keep the preview and are tagged metadata.recipient (lowercase reporter)"
  - "GET /api/notifications serves a metadata.recipient-tagged notice only to the user whose username or email (casefolded) equals it; untagged notices stay tenant-wide"
affects: [85-12, 85-19]

actuals:
  tokens: 14500
  tasks: 2
  commits: 2
plan_head_before: 1377e402c158b4fc396ac0e428b939ba59ea2582
plan_head_after: 0e90c9a92fc40534eca8323b2f5841219e211129

tech-stack:
  added: []
  patterns:
    - "Recipient tag on a notice document plus a reader filter ($and of an $or: absent, null, or in the caller's casefolded names)"
    - "Staff-only text is withheld at the source (no preview in the notice, none in history) rather than filtered on read"

key-files:
  created:
    - backend/tests/test_service_desk_comments.py
  modified:
    - backend/tickets_models.py
    - backend/tickets_service.py
    - backend/tickets_endpoints.py
    - backend/ticket_notifications.py
    - backend/notification_endpoints.py
    - backend/notification_service.py

key-decisions:
  - "A requester-visible comment by the reporter themself, or on a ticket with no reporter, sends no notice at all: an untagged preview would reach the whole tenant feed"
  - "Recipient-tagged notices push only their title on the tenant-wide socket (notification_service.send_alert); the stored notification document never held a message, so the socket was the real preview channel"

requirements-completed: [DESK-01]

coverage:
  - id: C1
    description: "A comment is stored staff-only unless the body says requester; any other value is 422; the history entry keeps a preview only for requester comments"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_comments.py#test_a_comment_is_staff_only_unless_the_technician_chooses_the_requester; #test_history_keeps_a_preview_only_for_requester_comments"
        status: pass
    human_judgment: false
  - id: C2
    description: "A requester reply on an automated ticket, a legacy tray ticket without My tickets, a ticket with no requester channel, or a missing or foreign ticket is refused (400 no_reply_target or 404) and nothing is stored"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_comments.py#test_a_reply_to_an_automated_ticket_is_refused_but_a_staff_note_is_not; #test_a_reply_where_the_requester_cannot_read_it_is_refused; #test_a_requester_reply_on_a_missing_or_foreign_ticket_is_not_found"
        status: pass
    human_judgment: false
  - id: C3
    description: "The requester projection and the requester view return requester comments only; a comment with no visibility key reads as staff"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_comments.py#test_the_requester_projection_returns_requester_comments_only"
        status: pass
    human_judgment: false
  - id: C4
    description: "A staff-only comment notice has no text, is not addressed to the reporter and is tagged ticket_staff; a requester comment notice keeps the preview and is tagged with the lowercase reporter; its text is not pushed on the tenant-wide socket; a mention notice is tagged with the mentioned address"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_comments.py#test_a_staff_comment_notice_has_no_text_and_does_not_address_the_reporter; #test_a_requester_comment_notice_keeps_the_preview_and_names_the_reporter; #test_a_mention_notice_is_tagged_with_the_mentioned_address"
        status: pass
    human_judgment: false
  - id: C5
    description: "GET /api/notifications returns a tagged notice only to its recipient (casefolded, by username or email), keeps untagged, null-tagged and metadata-less notices tenant-wide, keeps the tenant and tenant-admin audience filters, and staff-only text appears in no reader's feed or push"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_comments.py#test_the_feed_serves_a_tagged_notice_only_to_its_recipient; #test_the_feed_matches_the_recipient_case_insensitively_and_by_email; #test_staff_only_text_reaches_neither_the_reporters_feed_nor_the_tenants"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 08: Comment visibility and the notice leaks Summary

Every new comment is staff-only unless a technician chooses to reply to the requester, that choice is refused where no requester can read it, and no comment notice leaks staff-only text: the notice carries no preview, skips the reporter and is tagged for ticket staff, while a notice meant for one person is now read only by that person.

Duration: about 8 minutes (20:14 to 20:22 UTC). Tasks: 2. Files: 7 (1 created, 6 modified). Completed 2026-11-08.

## Accomplishments

- **Task 1, the flag (162cdc92e).** `AddCommentRequest.visibility` is `Literal["staff", "requester"]` with default `staff` (anything else is a 422). `add_comment(visibility=)` stores it on the comment and writes the history `preview` only for requester comments (a staff comment's history entry has empty `changes`). The route reads the ticket first for a requester reply and answers 400 with `no_reply_target` unless `raised_via` is person-raised and `projection.can_see` is true (404 for a missing or other-tenant ticket). Old comments need no migration: no `visibility` key reads as staff in `projection.requester_items`.
- **Task 2, the notices and the reader (0e90c9a92).** `notify_comment_added(visibility=)` sends staff comments as "New staff comment on ticket '{title}'" to the assignee and watchers without the reporter, tagged `audience: ticket_staff`; a requester comment keeps the preview and is tagged `recipient` with the lowercase reporter. The mention notice is tagged `recipient` with the mentioned address, lowercase. `get_notifications` adds a `$and` of an `$or` (recipient absent, null, or in the caller's casefolded username and email) to the existing tenant and tenant-admin filter.
- **Mutation check run by hand:** removing the reader filter failed 3 tests, restoring the staff preview 1, flipping the default to `requester` 6, and removing the socket guard 2. Every mutation was reverted and the 12 tests pass.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 162cdc92e | feat | A comment is staff-only unless a technician chooses to reply to the requester |
| 2 | 0e90c9a92 | fix | Comment notices stop previewing staff-only text and the feed respects recipients |

Plan type `execute` with `tdd="true"` tasks: as in 85-01 to 85-03, tests and implementation were written together. Task 1's commit holds the six flag tests and Task 2's holds the six notice and feed tests, so each commit is self-consistent (Task 1's `add_comment` does not yet pass `visibility` to the notifier; Task 2 adds that call with the new parameter).

## Verification

- Task 1 command (comments, test_tickets) and Task 2 command (comments, test_notification_service, test_tickets): 50 passed, no skips.
- Wider regression run: `test_service_desk_tracer` (16), `test_service_desk_structural` (15), `test_pending_agents` (17, includes the feed's tenant-admin filter test), `test_control_comments` (5), `test_autonomous_ops_copy` (33, the ACTV-08 scan): 136 passed with the plan's own tests, no skips.
- Acceptance greps: `visibility` in `tickets_models.py` 1 and in `tickets_service.py` 6 (needs 1 and 2); `metadata.recipient` in `notification_endpoints.py` 1; `ticket_staff` in `ticket_notifications.py` 4 (needs 1); the staff-notice test asserts the message and the stored notice hold no part of the comment text. `ruff --select F` is clean on the touched files.
- Every DB test used the private mongod on 27998; nothing touched the live database.

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] The tenant-wide socket carried every notice's text**
- **Found during:** Task 2, while writing the "stored notification has no preview" test. `send_alert` never stores a `message` on the notification document (it stores title, severity, time, channels and metadata), so the document the reader returns held no preview. The text goes out in the `broadcast_notification` push to every connected client of the tenant, tagged only in `metadata`, which the browser does not filter.
- **Issue:** the plan's recipient filter on the reader alone would leave a requester-visible comment's preview readable by the whole tenant over the socket, defeating "a notice meant for one person is read only by that person".
- **Fix:** `notification_service.send_alert` now broadcasts an empty `message` when `metadata.recipient` is set; the title still goes out. The plan's tests that read "the stored notification's message" check the message handed to the sender and to the socket instead, because the document has none.
- **Files modified:** backend/notification_service.py (not in the plan's list; no user changes in it). **Commit:** 0e90c9a92.

**Total deviations:** 1 auto-fixed (Rule 2). **Impact:** one four-line change in a file outside the plan's list; no other caller sets `metadata.recipient`, so nothing else changes behaviour.

Choices inside the plan's latitude, not deviations:
- A requester-visible comment written by the reporter, or on a ticket with no reporter, sends no notice, because an untagged preview would go to the whole feed.
- Staff notices keep the title "[TKT-n] New comment by {author}", so the author's name still shows; only the text is withheld, as the plan states.

## User WIP preserved

`backend/tickets_endpoints.py` still shows the user's `+38/-11` unstaged (attachment directory and download route) after both commits. Each commit staged a blob built from `HEAD` with only this plan's hunks (the comment route hunk in 162cdc92e, the one mention-metadata line in 0e90c9a92) through `git update-index --cacheinfo 100755`; `git diff --cached` showed no attachment, `FileResponse` or `_UPLOAD_DIR` line. The plan's other files had no user changes.

## Hand-over for later plans

- **85-12 (the requester notice):** a notice addressed to the requester should be tagged `metadata.recipient` with the lowercase reporter, as `notify_comment_added` does; the reader now serves it to that person only and the socket pushes its title only.
- **85-19 (tray routes):** staff-only comments are still readable by any user with ticket access through the ticket routes (T-85-29, accepted); the tray routes are the enforced boundary.

## Deferred (not fixed, outside this plan)

- The @mention notice in `tickets_endpoints.add_comment` calls `_send` without a `tenant_id`, so it is stored with tenantId empty and no tenant feed ever returns it. The new recipient tag is correct but the notice is unreachable until `tenant_id=_effective_tenant(current_user)` is passed. It predates this plan; passing the tenant would make mentions start appearing (to the mentioned user only), so it needs the user's call.

## User steps

None required. Not done, by design: restart of the backend (the new comment flag and the reader filter go live on the user's next restart), publishing the UI, git push. Existing comments need no backfill (no flag reads as staff); existing notification documents have no recipient tag and stay tenant-wide, as before.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-85-26 and T-85-27 are mitigated and tested; T-85-28 is mitigated by the `Literal` type and the 400 refusal; T-85-29 is accepted as planned.

## Self-Check: PASSED

- Files: `backend/tests/test_service_desk_comments.py` exists; all six modified files exist; 162cdc92e and 0e90c9a92 are ancestors of HEAD.
- All `<acceptance_criteria>` of both tasks re-run and pass (see Verification). `git diff --numstat -- backend/tickets_endpoints.py` shows the user's 38/11 unstaged.
