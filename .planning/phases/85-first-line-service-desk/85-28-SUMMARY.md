---
phase: 85-first-line-service-desk
plan: 28
subsystem: service-desk-backend
tags: [wr-201, wr-202, notifications, audience, reporter-privacy, gap-closure]

requires:
  - phase: 85-first-line-service-desk
    provides: "85-08 comment visibility and the ticket_staff / recipient notice tags; 85-27 disposition ordering"
provides:
  - "notification_endpoints._reader_names / _reader_filter: the one reader filter (tenant, tenant_admins audience, recipient rule, excludeRecipients rule) used by the list, mark-read, read-all and delete routes"
  - "ticket_notifications.notify_comment_added: staff-only comment notices carry metadata.excludeRecipients with the reporter (stripped, casefolded)"
  - "notification_service.send_alert: no tenant-wide WebSocket push for metadata.audience ticket_staff"
  - "backend/tests/test_service_desk_notification_audience.py: 16 tests (feed, socket, write routes)"
  - "WR-201 and WR-202 recorded fixed in 85-REVIEW-DISPOSITION.md (open 23 -> 21)"
affects: [85-29 phase gate, 85-VERIFICATION re-verification]

actuals:
  tokens: 16000
  tasks: 3
  commits: 6
plan_head_before: 22c43fea2b343196a193699b0d205dd7faa0376f
plan_head_after: fa0b80b6bb8dc5758eb2da49d2969dbefc920f52
commits: 6

tech-stack:
  added: []
  patterns:
    - "One reader filter shared by the list and the write routes: a user changes only what they can read"
    - "An exclusion list on the notice (excludeRecipients) next to the inclusion tag (recipient)"

key-files:
  created:
    - backend/tests/test_service_desk_notification_audience.py
  modified:
    - backend/ticket_notifications.py
    - backend/notification_endpoints.py
    - backend/notification_service.py
    - backend/tests/test_service_desk_comments.py
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md

key-decisions:
  - "A-85-G13: a ticket_staff notice is not pushed on the tenant socket at all (stronger than blanking title and message): staff lose only the instant toast and see it in the bell on the next 60 s poll"
  - "A-85-G14: ticket_staff notices stored before this plan carry no excludeRecipients and stay readable by the whole tenant, reporter included (no text in them, 85-08); no migration"
  - "A-85-G15: tenant_admins notices are still pushed tenant-wide on the socket while the feed hides them from non-admins; outside WR-201, left unchanged, reported as a follow-up"
  - "Title decision (85-SECURITY residual for 85-08): the reporter never reads the staff notice in the feed or on the socket, so the '[TKT-n] New comment by {author}' title of a staff-only comment does not reach them"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "WR-201 feed: the staff-only comment notice is stored with excludeRecipients [reporter]; the reporter's feed never lists it (case-insensitive, by username or email), colleagues still read it with its title; a ticket with no reporter stores no exclusion"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_the_reporter_never_reads_the_staff_notice_but_colleagues_do"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_the_exclusion_matches_case_insensitively_and_by_email"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_a_staff_notice_of_a_ticket_with_no_reporter_reaches_everyone"
        status: pass
    human_judgment: false
  - id: D2
    description: "WR-201 socket: a ticket_staff notice is stored but not pushed on the tenant socket; recipient notices keep their blank-message push and every other notice its full push"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_a_staff_comment_is_not_pushed_on_the_tenant_socket_at_all"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_a_requester_reply_keeps_its_blank_push_for_the_recipient"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_comments.py#test_a_staff_comment_notice_has_no_text_and_does_not_address_the_reporter"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-202 / D-33: mark-read, read-all and delete start from the reader filter; a colleague gets 404 and no change on an addressed notice, read-all touches only readable notices, the reporter keeps her own, tenant_admins notices need manage:agents"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_a_colleague_cannot_mark_an_addressed_notice_read"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_read_all_without_ids_marks_only_what_the_reader_can_read"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_the_tenant_admin_notice_needs_manage_agents_to_be_changed"
        status: pass
    human_judgment: false

duration: "about 30 min"
completed: 2026-11-09
status: complete
---

# Phase 85 Plan 28: notice audience in the feed, on the socket and on the write routes (WR-201, WR-202) Summary

The reporter no longer learns that a staff-only comment exists or who wrote it (not in the bell, not on the socket), and a user can mark read or delete only the notices they can read.

## Accomplishments

- **WR-201 feed (tracer, `9840a7fdf`).** `notify_comment_added` writes `metadata.excludeRecipients: [reporter]` on the staff-only notice (nothing when the ticket has no reporter). `notification_endpoints` gets `_reader_names` and `async _reader_filter`, which adds `{"metadata.excludeRecipients": {"$nin": names}}` to the existing tenant, tenant_admins and recipient rules. `get_notifications` uses it unchanged otherwise. RED was observed before the code: 3 of 4 new tests failed on the planned assertions (KeyError excludeRecipients, Alice's feed listing the notice).
- **WR-201 socket (`9f5d01275` RED, `b49c68fa4`).** `send_alert` skips the tenant-wide broadcast when `metadata.audience == "ticket_staff"`; the notice is still stored once. The 85-08 test's push assertions now expect no push and no staff-author name anywhere on the socket. Two guard tests pin the recipient-notice blank push and the full push of notices with no metadata, an unrelated dict and the tenant_admins audience.
- **WR-202 (`0b473b477` RED, `89f7786bd`).** `mark_as_read`, `mark_all_as_read` and `delete_notification` build their query from `_reader_filter` plus the alert_id condition; read-all with no ids no longer touches the whole tenant. A colleague's mark-read or delete on an addressed notice answers 404 and changes nothing; read-all with an unreadable id modifies nothing for it. RED: 7 failing tests (6 behavior, 1 structural), all on the planned assertions.
- **Disposition (`fa0b80b6b`).** WR-201 fixed (9840a7fdf, b49c68fa4) and WR-202 fixed (89f7786bd); open 23 -> 21. WR-401..405 and every IN-* row stay open.

## Task Commits

1. Task 1 (tracer): `9840a7fdf` feat - excludeRecipients, `_reader_filter`, 4 tests
2. Task 2: `9f5d01275` test (RED, 2 failing) -> `b49c68fa4` feat
3. Task 3: `0b473b477` test (RED, 7 failing) -> `89f7786bd` fix; `fa0b80b6b` docs (disposition)

## Verification

`test_service_desk_notification_audience.py`, `test_service_desk_comments.py`, `test_notification_service.py` (user WIP, run read-only), `test_service_desk_withdraw.py` and `test_route_auth_baseline.py` on the private mongod 27998: 91 passed, 0 failed, 0 skipped. `grep -c "_reader_filter(" backend/notification_endpoints.py` = 5 (definition plus four routes). `backend/tests/test_notification_service.py` still shows the user's ` M` and was never staged. `notification_endpoints.py` is 363 lines.

## Deviations from Plan

None - plan executed exactly as written. (The new test file imports the `mongo_db` fixture beside `world`, because pytest resolves the imported fixture's own dependency from the importing module.)

## Known Stubs

None.

## Threat Flags

None. T-85-98 and T-85-99 are mitigated; T-85-100 and T-85-101 stay accepted (A-85-G14, A-85-G15). Follow-up for the user: tenant_admins notices are still pushed to every user of the tenant on the socket.

## Self-Check: PASSED

- backend/tests/test_service_desk_notification_audience.py exists; commits 9840a7fdf, 9f5d01275, b49c68fa4, 0b473b477, 89f7786bd, fa0b80b6b are on the branch.
