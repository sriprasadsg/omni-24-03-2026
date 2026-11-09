---
phase: 85-first-line-service-desk
plan: 34
subsystem: service-desk-ticket-access
tags: [g-85-4, wr-502, ud-2, staff-actions, manage-tickets, viewer-guard, gap-closure]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: "85-30 ticket_access.TICKET_STAFF; 85-32 ticket_access.ticket_viewer router guard; 85-33 staff-aware projection"
provides:
  - "bulk update, PATCH, add and remove a link, work log, delete attachment, approve, reject and escalate (tickets_endpoints) on has_permission(ticket_access.TICKET_STAFF)"
  - "merge (tickets_workflow_endpoints) and add or remove a watcher (tickets_config_endpoints) on the staff permission"
  - "tickets_workflow_endpoints.router and tickets_config_endpoints.router carry ticket_access.ticket_viewer(): rating, merge and watcher routes on another person's ticket answer 404 to non-staff"
affects: [85-35, 85-36]

actuals:
  tokens: 9000
  tasks: 2
  commits: 3
plan_head_before: b7b8f64c68c6f34f19ca5c354753980ab83541bb
plan_head_after: 283a1b71ae3e1c29cf0aea54dac01848fb89051a
commits: 3

tech-stack:
  added: []
  patterns:
    - "Router-level viewer guard runs before the route's permission dependency, so a colleague gets 404 (never 403) and only the reporter reaches the 403 on a staff action"

key-files:
  created:
    - backend/tests/test_ticket_staff_actions.py
  modified:
    - backend/tickets_endpoints.py
    - backend/tickets_workflow_endpoints.py
    - backend/tickets_config_endpoints.py
    - backend/tests/test_service_desk_reporter_ticket.py

key-decisions:
  - "A-85-G28 kept as planned: PATCH /api/tickets/{id}, the two link routes and attachment delete are staff-only (they are not among what requesters keep); CSAT stays with view:dashboard, limited to the reporter and staff by the viewer guard"
  - "The reporter-projection tests of the PATCH, link, work-log and approve/reject/escalate routes run as ALICE_ADMIN (reporter with manage:tickets) and also assert the plain requester ALICE gets 403 and the stored ticket is unchanged"
  - "T-85-120 accepted: a staff member keeps staff rights on a ticket they raised and gets the requester projection back"

requirements-completed: [DESK-01]

coverage:
  - deliverable: "UD-2 / WR-502 / PROH-85-25 / T-85-119: the nine staff actions of tickets_endpoints answer 403 to the reporter (stored ticket unchanged), 404 to a colleague (403 on bulk), 200 to staff"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_the_reporter_cannot_use_a_staff_action_on_their_own_ticket"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_staff_can_use_every_staff_action"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_a_colleague_cannot_reach_a_staff_action_on_someone_elses_ticket"
        status: pass
    human_judgment: false
  - deliverable: "Requesters keep commenting and attaching on their own ticket; a reporter with the admin role can still act and gets the requester projection"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_the_reporter_keeps_commenting_and_attaching"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_a_reporter_with_an_admin_role_can_act_and_still_gets_the_requester_view"
        status: pass
    human_judgment: false
  - deliverable: "Merge and watchers are staff actions; the viewer guard covers the workflow and config routers; CSAT stays the reporter's own; template and field routes stay open"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_the_reporter_cannot_merge_or_change_the_watchers_of_their_own_ticket"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_a_colleague_gets_404_on_merge_and_watchers_of_someone_elses_ticket"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_the_reporter_rates_their_resolved_ticket_and_a_colleague_cannot"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_actions.py#test_the_routes_a_requester_needs_to_raise_a_ticket_stay_open"
        status: pass
    human_judgment: false
  - deliverable: "A-85-G28 (four planner choices) and A-85-G29 (the screen still shows staff controls to requesters)"
    human_judgment: true
    rationale: "Planner readings of UD-2 that need the user's confirmation at verification; the screen change is a UI follow-up for the user"
---

# Phase 85 Plan 34: Staff actions on a ticket need manage:tickets Summary

**Eleven ticket routes (bulk update, edit, link and unlink, work log, attachment delete, approve, reject, escalate, merge, add and remove a watcher) now depend on `ticket_access.TICKET_STAFF`, and the workflow and config ticket routers carry the 85-32 viewer guard, so a requester gets 403 on their own ticket (stored ticket unchanged) and 404 on a colleague's.**

Duration: about 25 minutes (2026-11-09). 2 tasks, 5 files (1 created), 3 commits.

## Accomplishments

- **Task 1 (tracer, 638d655b7):** the permission string of nine route signatures in `backend/tickets_endpoints.py` went from `view:dashboard` to `ticket_access.TICKET_STAFF` (net zero lines). `test_ticket_staff_actions.py` runs each action as Alice (reporter, 403 plus the whole stored ticket compared before and after), Bob (staff, 200 and the planned change in the stored ticket) and Carol (colleague, 404; 403 on bulk), and checks Alice still comments and uploads an attachment on her own ticket and that a reporter with role admin can PATCH and gets no `desk` key. The projection tests of PATCH, links, work log and approve/reject/escalate in `test_service_desk_reporter_ticket.py` moved to `ALICE_ADMIN` and each also asserts Alice's 403 and an unchanged ticket.
- **Task 2 (test e1b3d9c21, feat 283a1b71a):** `merge_ticket`, `add_watcher` and `remove_watcher` moved to the staff permission; both routers got `dependencies=[Depends(ticket_access.ticket_viewer())]`. Tests mount the two routers on the desk app: Alice 403 on merge and both watcher routes (neither ticket changed), Bob 200, Carol 404 on merge, watchers and CSAT, Alice rates her resolved ticket (200), and `GET /api/tickets/templates/list` and `/schema/fields` still answer Alice 200.

## TDD Gate Compliance

Task 1 is a tracer: the new action tests ran first and 9 of 26 failed on the planned assertions (the reporter got 200 instead of 403 on all eight reporter-case actions, and Carol got 200 on bulk; the staff cases and the 404 cases already passed because they describe behavior that must not change), then the nine permission strings were changed and all passed. Task 2 followed test then feat: RED `e1b3d9c21` (7 of 37 failed: reporter and colleague on merge and watchers returned 200 instead of 403 and 404, and Carol rated Alice's ticket), GREEN `283a1b71a`. No REFACTOR commit.

## Verification

- Task 1 command (staff actions, reporter ticket, staff access, staff lists, tickets, audit ledger): 121 passed, 0 skipped.
- Task 2 command: `test_ticket_staff_actions.py` 37 passed, `test_tickets.py` 23, `test_route_auth_baseline.py` 20 passed together; `test_catalogue_slice_settings_ops.py` 9 passed in a second run (3 minutes, it exceeded the first command's time limit).
- `test_catalogue_route_parity.py`: 48 passed, 2 failed (`test_unguarded_routers_are_ledgered`, `test_ledger_ratchets`), exactly the two known working-tree failures (the user's `catalogue-gaps.json` expects the set-aside `reporting_endpoints.py` edits); no route was added.
- Acceptance: `grep -c "has_permission(ticket_access.TICKET_STAFF)"` prints 9 on `tickets_endpoints.py`, 1 on `tickets_workflow_endpoints.py`, 2 on `tickets_config_endpoints.py`; both routers contain `ticket_access.ticket_viewer()` in their `APIRouter` call. The "numstat 38 11" check does not apply: the user's uncommitted `tickets_endpoints.py` edits are set aside, so the file matched HEAD when edited and was staged by plain path; `download_attachment`, `_UPLOAD_DIR` and the FileResponse import were not touched.

## Deviations from Plan

None - plan executed exactly as written. (Process note: no commit carries a Co-Authored-By trailer, per CLAUDE.md.)

## Known Stubs

None.

## Threat Flags

None. T-85-119 is mitigated and tested; T-85-120 (a staff member approving their own request) is accepted as planned; T-85-SC accepted (no install).

## Follow-ups

- **For the user (A-85-G28, needs confirmation at verification):** four choices read UD-2 closed: PATCH /api/tickets/{id}, adding or removing a link and deleting an attachment are staff-only; CSAT stays the requester's own on their own resolved ticket.
- **For the user (A-85-G29):** `components/InternalTicketsDashboard.tsx` (user WIP) still shows bulk actions, merge, approve and status changes to requesters, who now get a 403 message when they use them; hiding them by `manage:tickets` is a UI follow-up.
- When the user's set-aside `tickets_endpoints.py` edits are restored, the 3-way merge touches only the dependency line of nine routes from this plan; re-check `grep -c "has_permission(ticket_access.TICKET_STAFF)"` prints 9 afterwards.

## Next

Ready for 85-35.

## Self-Check: PASSED

- FOUND: backend/tests/test_ticket_staff_actions.py, backend/tickets_endpoints.py, backend/tickets_workflow_endpoints.py, backend/tickets_config_endpoints.py, backend/tests/test_service_desk_reporter_ticket.py
- FOUND commits: 638d655b7, e1b3d9c21, 283a1b71a
