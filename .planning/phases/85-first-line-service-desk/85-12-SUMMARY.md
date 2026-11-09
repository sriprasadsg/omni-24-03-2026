---
phase: 85-first-line-service-desk
plan: 12
subsystem: service-desk
tags: [handoff, gaps, notify, queue-rules, ledger, requester-notice]
status: complete

requires: []
provides:
  - "backend/service_desk/handoff.py: handoff(db, ticket, reason, *, now, notify_requester, actor, question) -> bool, the one way a ticket is sent to a person"
  - "backend/service_desk/gaps.py: record(db, tenant_id, *, ticket_id, ticket_number, text, reason, now) -> bool, gap rows for no_article and not_english"
  - "backend/service_desk/notify.py: requester_notice(db, ticket, *, event, title, message) -> bool, a recipient-tagged in-app notice for a portal requester"
  - "comment ids sd-note-{reason}-{ticketId} and sd-notice-{reason}-{ticketId}; ticket field desk.lastReason"
affects: [85-04, 85-13, 85-14, 85-15, 85-18]

actuals:
  tokens: 14500
  tasks: 2
  commits: 2
plan_head_before: d517d313a886848db8a091283b3fdef309611ff0
plan_head_after: 0b693fb74f48b882da6cd5f89b06b5f35d55fc4a

tech-stack:
  added: []
  patterns:
    - "Raw handle with an explicit tenantId for every desk write; only the tenant-wrapped queue helpers (auto_assign, update_ticket) run inside tenant_scope"
    - "Every step of a hand-off is wrapped on its own so one failing write is logged and the ticket still reaches a person"
    - "Idempotency by comment id: the ledger row, the notice and the gap are written only when the staff note was new"

key-files:
  created:
    - backend/service_desk/handoff.py
    - backend/service_desk/gaps.py
    - backend/service_desk/notify.py
    - backend/tests/test_service_desk_handoff.py
  modified: []

key-decisions:
  - "The stored assignee is re-read before the queue rules run, so a person who took the ticket after the caller read it is never overridden"
  - "The hand-off's requester notice is the requester-visible comment only; notify.requester_notice is a separate tool for callers (answers, withdrawals) and the hand-off itself writes no notification, as the plan's test requires"
  - "gaps.record cleans the text itself (sanitize.clean_text, 300 characters), so no caller can store raw ticket text; an empty cleaned question writes no row"

requirements-completed: [DESK-02, DESK-06]

coverage:
  - id: D1
    description: "A hand-off routes the ticket by the tenant's queue rules, adds a staff-only reason note and a plain requester notice, marks desk.phase handed_off and writes one audited ledger row; nothing is paged and the priority is unchanged"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_handoff.py#test_a_hand_off_routes_the_ticket_notes_it_tells_the_requester_and_records_it"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_handoff.py#test_a_hand_off_pages_no_one_and_changes_no_priority"
        status: pass
    human_judgment: false
  - id: D2
    description: "The requester notice never names the reason; stopped, automated and legacy tray tickets get none; a second call adds nothing"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_handoff.py#test_the_requester_notice_never_names_the_reason_and_the_reason_stays_with_staff"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_handoff.py#test_a_second_call_adds_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "Recipient-tagged in-app notice for a portal requester with the ticket number only"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_handoff.py#test_a_portal_requester_gets_one_tagged_in_app_notice_with_no_preview"
        status: pass
    human_judgment: false
  - id: D4
    description: "Gap rows only for no_article and not_english, one per tenant, ticket and reason, cleaned and cut to 300 characters"
    requirement: "DESK-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_handoff.py#test_only_no_article_and_not_english_leave_a_gap_row"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 12: The hand-off, gap rows and requester notice Summary

Sending a ticket to a person is now one tested function: it routes the ticket through the tenant's own queue rules, tells staff why in a staff-only note, tells the requester plainly without naming a reason, records an audited ledger row, pages no one, and keeps the cleaned question for the knowledge-gap list only when no article covered it or it was not English.

Duration: about 25 min. Tasks: 2. Files: 4 created. Completed 2026-11-09.

## Accomplishments

- **Hand-off (Task 1, c69ee8af9).** `handoff.handoff` validates the reason against `HANDOFF_REASONS`, then in order: assigns an unassigned ticket with `tickets_service.auto_assign` and `update_ticket` inside `tenant_scope`; adds the staff note `Service desk: {label}.` (comment id `sd-note-{reason}-{ticketId}`); adds the requester notice `A person from IT will look at this.` (id `sd-notice-...`) unless the reason is `desk_stopped`, `notify_requester` is False or `projection.can_see` is False; sets `desk.phase`, `desk.lastReason` and `draftWaiting False`; writes one `record_desk_event` row whose reason text is the sentence-cased label. It returns True only when the staff note was new, so a repeated call adds nothing. Each step is wrapped separately.
- **Requester notice (Task 1).** `notify.requester_notice` stores one in-app notice through `send_alert` with `recipients=[]` and `channels=[]`, tagged `metadata.recipient` (lowercase reporter), only for a portal requester with a reporter. Title and text are the ticket number alone (or the caller's generic text). It never raises.
- **Gap rows (Task 2, 0b693fb74).** `gaps.record` upserts one row per tenant, ticket and reason with id `SDG-...`, the cleaned question cut to 300 characters, `status open` and a `createdAt` datetime. A reason outside `GAP_REASONS` raises ValueError. The hand-off writes a row only for `no_article` and `not_english` (the question defaults to the ticket title; callers may pass `question=`).
- **Code lists.** A test pins `HANDOFF_REASONS` (19) to the keys of `STAFF_REASON_LABELS` and `DRAFT_REASONS` (8) to the keys of `DRAFT_REASON_TEXT`.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | c69ee8af9 | feat | The hand-off to a person and the recipient-tagged requester notice |
| 2 | 0b693fb74 | feat | Gap rows for questions no article covered |

The plan type is `execute` (tasks marked `tdd="true"`, not `type: tdd`), so the three-commit RED/GREEN gate does not apply. As in 85-02 and 85-03, tests and implementation were written together and committed together per task.

## Verification

- `test_service_desk_handoff.py`: 24 passed, no skips (Task 1 alone: 17).
- Plan commands plus structural, copy gate, ledger and Autonomous Ops structural tests: 138 passed, no skips (handoff, tracer, service_desk_structural, autonomous_ops_copy, service_desk_ledger, autonomous_ops_structural).
- Acceptance greps: `auto_assign` in handoff.py 2, `record_desk_event` 1, `channels=[]` in notify.py 1, `async def record` in gaps.py 1. The test asserts the notice text equals `HANDOFF_NOTICE` exactly and iterates every reason in `HANDOFF_REASONS` for the gap rule.
- Sizes: handoff.py 102, gaps.py 33, notify.py 37, test 351 lines.
- Every test used the private mongod on 27998; nothing touched the live database. No restart, publish, push, install or agent build.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Safety] The assignee is re-read before the queue rules run**
- **Found during:** Task 1
- **Issue:** The plan applies `auto_assign` when "the ticket has no assignee", judged from the caller's copy. A caller's copy can be stale, and a second hand-off for another reason would then overwrite a person's assignment with the queue's.
- **Fix:** `_assign` reads the stored assignee (id and tenantId filter) first and skips the rule when one is set. Test: `test_a_person_who_took_the_ticket_after_it_was_read_is_not_overridden`.
- **Commit:** c69ee8af9

**2. [Rule 2 - Safety] gaps.record cleans the text itself**
- **Found during:** Task 2
- **Issue:** The plan has the caller pass the cleaned question; a caller that forgot would store raw ticket text (T-85-44).
- **Fix:** `record` runs `sanitize.clean_text(text, GAP_TEXT_CAP)` itself (idempotent on cleaned text) and writes no row when the result is empty. The hand-off passes the raw title or the caller's `question`.
- **Commit:** 0b693fb74

**3. [Rule 1 - Test fit] The stored notification has a title but no message**
- **Found during:** Task 1
- **Issue:** `send_alert` stores `title`, severity, channels and metadata but not the message text, so a test asserting a stored `message` failed.
- **Fix:** The tests assert the stored title and the metadata only. The title is the ticket number alone, so no ticket text is stored either way.
- **Commit:** c69ee8af9

**Total deviations:** 3 (2 safety, 1 test fit). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-85-42 (the requester notice is a fixed sentence, checked for every reason), T-85-43 (no on-call document, no notification, no `autonomous_ops.notify` call, priority and escalated unchanged), T-85-44 (cleaned, 300 characters, 90-day TTL index from 85-01; read access is 85-15), T-85-45 (one ledger row per hand-off) are covered by tests. T-85-SC accepted (no package installed).

## User steps

None. The backend runs from the checkout, so this goes live with the next backend restart (the user's step, later).

## Notes for later plans

- Callers (85-04, 85-13, 85-14) pass the ticket dict they already hold; it must carry `id`, `tenantId`, `ticket_number`, `type`, `priority`, `tags`, `reporter` and `requester_channel`, since the queue rules and the notice read them.
- A hand-off does not call `notify.requester_notice`: the requester-visible comment is its notice, and the plan's test requires that a hand-off writes no notification. The "answer posted" and "answer withdrawn" paths use `requester_notice` themselves.
- The assignment still goes through `update_ticket`, so the assignee gets the normal "assigned to you" notice from the ticket queue (the existing behaviour for any assignment). The tests replace `ticket_notifications.notify_assigned` with a mock for that reason.
- A stopped desk (decision 3) calls `handoff(..., "desk_stopped")`: no requester notice, as built.
- The user's uncommitted work (`backend/tickets_endpoints.py`, `components/InternalTicketsDashboard.tsx`, `shared/catalogue-gaps.json`, Rust `Cargo.toml` and `Cargo.lock`, `App.tsx` and others) was not touched and is still unstaged.

## Self-Check: PASSED

handoff.py, gaps.py, notify.py and test_service_desk_handoff.py exist; commits c69ee8af9 and 0b693fb74 are ancestors of HEAD; the acceptance criteria and both plan verification commands were re-run green.
