---
phase: 85-first-line-service-desk
plan: 39
subsystem: service-desk
tags: [ticket-create, staff-only-fields, tenant-websocket, notice-audience, gap-closure, G-85-5, WR-602, WR-603]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: 85-34 ticket_access.is_ticket_staff, 85-28/85-31 reader_filter and the notice audience (D-11, D-33)
provides:
  - create_ticket drops assignee, assignee_group, watchers, approval_required, sla_hours and due_date for callers who are not ticket staff, before and after the template merge (a template's own approval requirement stays)
  - notification_audience.broadcastable(metadata), the one rule for the tenant-wide WebSocket push
  - send_alert and pending_agents._post_in_app push only notices that carry no audience
  - a scan test that fails when any backend function calls broadcast_notification without broadcastable
affects: [gsd-verify-work 85, UAT round 4 of G-85-5, 85-42 (records D-42 and D-43)]

actuals:
  tokens: 26000
  tasks: 2
  commits: 2
plan_head_before: da7e71c8bc41c96c2b9ab0607dd02ad192ea4fd2
plan_head_after: 0efe58463c66318e5e4b32e24e2ee2dc233670b1
commits: 2

tech-stack:
  added: []
  patterns: ["one pure push rule (broadcastable) with an AST scan that holds it for future callers", "requester input filtered by key tuple before and after the template merge"]

key-files:
  created:
    - backend/tests/test_ticket_staff_create_fields.py
  modified:
    - backend/tickets_endpoints.py
    - backend/notification_audience.py
    - backend/notification_service.py
    - backend/pending_agents.py
    - backend/tests/test_service_desk_notification_audience.py
    - backend/tests/test_pending_agents.py

key-decisions:
  - "A-85-G38: a requester's ticket keeps approval_required true when its template's defaults say so (fail closed); every other staff-only template default is dropped; a requester can never set it either way"
  - "A-85-G39: API-key callers need manage:tickets in the key's scopes to set the six fields (is_ticket_staff applies scope narrowing)"
  - "A-85-G40: the platform tenant's untagged pending-agent notice keeps its push; the tenant's tenant_admins notice is feed-only"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "A requester's POST /api/tickets stores none of the six staff-only fields they sent, answers 200, and stores title, description, type, priority, tags and custom fields as sent; staff still set all six"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_ticket_staff_create_fields.py#test_requester_cannot_set_the_staff_fields"
        status: pass
      - kind: integration
        ref: "backend/tests/test_ticket_staff_create_fields.py#test_staff_set_all_six_fields"
        status: pass
    human_judgment: false
  - id: D2
    description: "Through a template, a requester gets none of the staff defaults (assignee, group, watchers, SLA, due date) but keeps the template's approval requirement; staff get every default; a requester cannot set approval through a template that does not require it"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_ticket_staff_create_fields.py (4 template tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A notice whose metadata carries any audience is stored once and never pushed on the tenant socket; untagged notices keep their push; pending-agent notices push only to the platform tenant"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_notification_audience.py#test_a_notice_with_an_audience_is_stored_once_and_never_pushed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pending_agents.py#test_pending_alert_for_the_tenant_is_never_pushed_on_the_socket"
        status: pass
    human_judgment: false
  - id: D4
    description: "One rule (broadcastable) decides the push and a scan fails when another function calls broadcast_notification without it"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_notification_audience.py#test_every_caller_of_the_tenant_broadcast_asks_broadcastable_first"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 39: requester-set staff fields and audience notices on the socket Summary

A requester's new ticket now stores none of the assignee, group, watchers, approval, SLA or due-date values they (or a template's staff defaults) supplied, and a notice addressed to any audience is never pushed on the tenant-wide WebSocket, pending-agent notices included. Closes the WR-603 and WR-602 half of UAT gap G-85-5.

## Accomplishments

- **Task 1 (tracer, 6fcb73084):** `create_ticket` asks `ticket_access.is_ticket_staff(current_user)` once. For a non-staff caller the six keys in `_STAFF_ONLY_CREATE_FIELDS` are removed from the body before the template merge and again after it; `approval_required` is set true afterwards only when the template's defaults set it true (A-85-G38). Staff are unchanged. 5 new tests (requester, staff, template for each, requester approval through a template that does not require it). Verify run: 138 passed, 0 skipped.
- **Task 2 (0efe58463):** `broadcastable(metadata)` is true only when the metadata has no `audience` (a non-dict is broadcastable only when None or empty). `send_alert` and `_post_in_app` use it, so tenant_admins notices (agent hostname, seat usage) no longer reach the tenant's sockets; the platform tenant's untagged notice keeps its push (A-85-G40). Tests: broadcastable unit cases, never-pushed for tenant_admins / ticket_staff / anything_new, the pending-agent push test, and an AST scan over backend/ that fails for any function calling `broadcast_notification` (any alias) without `broadcastable` (it also proves itself on a bad and a good sample). Verify run: 99 passed, 0 skipped. TDD: the tests were run first and failed (14 failed) before the implementation; one commit per task per the plan.

## Deviations from Plan

None - plan executed exactly as written. (The scan test reads files as bytes because one backend file is not valid UTF-8.)

## Needs the user

- Confirm A-85-G38 (a requester's ticket keeps a template's `approval_required` true; the other five template defaults are dropped for requesters).
- A-85-G39: an integration that creates tickets with an API key needs `manage:tickets` in the key's scopes to set the six fields; without it they are dropped and the queue rules route the ticket.
- Nothing is live yet: the backend (no --reload) must be restarted by the user to ship both fixes.

## WIP safety

backend/tickets_endpoints.py carries the user's uncommitted attachment changes. Staged with the index-blob method: the commit holds only the create_ticket change (no FileResponse / download_attachment / ticket_attachments line), and `git diff --numstat -- backend/tickets_endpoints.py` still prints 38 11. All other files were clean before the edit.

## Known Stubs

None.

## Threat Flags

None. T-85-133 and T-85-134 are mitigated; T-85-135 (platform tenant push) accepted as planned.

## Self-Check: PASSED

- backend/tests/test_ticket_staff_create_fields.py: FOUND
- commits 6fcb73084 and 0efe58463: FOUND
- acceptance greps: is_ticket_staff(current_user) present; `def broadcastable` 1; broadcastable( in both callers; the only broadcast_notification callers outside websocket_manager are notification_service.py and pending_agents.py
