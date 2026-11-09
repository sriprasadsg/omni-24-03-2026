---
phase: 85-first-line-service-desk
plan: 32
subsystem: service-desk-ticket-access
tags: [g-85-4, wr-502, ud-2, ticket-viewer, router-guard, gap-closure]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: "85-30: ticket_access.is_ticket_staff, manage:tickets and the staff identities of the desk test world"
provides:
  - "backend/ticket_access.py ticket_viewer(detail='Ticket not found'): router dependency, 404 unless ticket staff or the ticket's reporter"
  - "tickets_endpoints.router carries the guard: every {ticket_id} route (get, history, comments, links, work-log, attachments, approve, reject, escalate, patch, delete, and the user's uncommitted download route once restored) is covered by construction"
affects: [85-33, 85-34, 85-35, 85-36]

actuals:
  tokens: 11000
  tasks: 2
  commits: 2
plan_head_before: de5d2b61f5e002611ed974327aff7f8bfb3105da
plan_head_after: 6686731c59a71bc43a1f5ae889f8bb32625fcabc
commits: 2

tech-stack:
  added: []
  patterns:
    - "One router dependency decides who reaches a ticket at all; the route bodies are unchanged. Staff skip the ticket read, everybody else is checked against the ticket of their own tenant, and the refusal is the same 404 and detail as a missing ticket"

key-files:
  created: []
  modified:
    - backend/ticket_access.py
    - backend/tickets_endpoints.py
    - backend/tests/test_ticket_staff_access.py
    - backend/tests/test_tickets.py
    - backend/tests/test_service_desk_portal_routes.py

key-decisions:
  - "A-85-G24 kept: the guard is a router dependency (3 added lines in tickets_endpoints.py), so present and future {ticket_id} routes are covered, including the user's uncommitted download route, which this plan did not touch"
  - "The guard runs before each route's own has_permission dependency: a caller who is neither staff nor the reporter gets 404 even where the route would have answered 403 (for example DELETE without manage:settings). The 404 never confirms that a ticket id exists"
  - "A caller without a tenant (and not a Super Admin, who is staff by the wildcard) gets 404: no tenant means no ticket"
  - "A-85-G25 kept: this plan decides who reaches a ticket at all; which actions need staff (85-34), the list scope (85-33) and the desk routes (85-35) are unchanged, so a reporter can still call bulk, patch and the other routes on their own ticket"

requirements-completed: [DESK-01]

coverage:
  - deliverable: "UD-2 / WR-502 / PROH-85-23: a requester who did not raise a ticket gets 404 on GET /api/tickets/{id}; staff and the reporter keep their access (stored ticket for staff, requester projection for the reporter)"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_requester_who_did_not_raise_the_ticket_gets_not_found"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_staff_who_did_not_raise_it_get_the_stored_ticket"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_the_reporter_still_gets_the_requester_projection"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_the_reporter_passes_the_guard_with_the_name_in_another_case"
        status: pass
    human_judgment: false
  - deliverable: "T-85-113: the refusal equals the answer for a missing ticket (404, same detail), on get and comments"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_real_ticket_and_a_made_up_id_give_the_same_answer"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_requester_cannot_comment_on_a_colleagues_ticket"
        status: pass
    human_judgment: false
  - deliverable: "UD-3: tenant boundary, custom role with and without manage:tickets, API-key scopes"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_user_of_another_tenant_gets_not_found_even_as_staff_or_namesake"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_custom_role_reads_a_colleagues_ticket_only_with_manage_tickets"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_an_analyst_api_key_without_manage_tickets_is_a_requester"
        status: pass
    human_judgment: false
  - deliverable: "T-85-112 on history, comment, upload (nothing stored, no file written) and delete"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_requester_gets_not_found_on_the_history_of_a_colleagues_ticket"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_requester_cannot_attach_to_a_colleagues_ticket_and_nothing_is_written"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_custom_role_with_manage_settings_but_not_manage_tickets_cannot_delete"
        status: pass
    human_judgment: false
  - deliverable: "Legacy ticket tests reflect who is staff (_STAFF analyst identity; requester 404 and 200 cases)"
    verification:
      - kind: test
        ref: "backend/tests/test_tickets.py (23 tests)"
        status: pass
    human_judgment: false
  - deliverable: "T-85-114: the user's uncommitted attachment download route is covered by the router guard"
    verification: []
    human_judgment: true
    rationale: "That route is not in HEAD (the orchestrator set it aside), so no test could exercise it; coverage is by construction (same router). Re-check once the user's edits return."
---

# Phase 85 Plan 32: The ticket viewer guard Summary

**One router dependency, `ticket_access.ticket_viewer`, now sits on `tickets_endpoints.router`: on every `{ticket_id}` route a caller who is neither ticket staff (manage:tickets) nor the ticket's reporter gets the same 404 "Ticket not found" as for a missing ticket, and nothing is read, written or stored.**

Duration: about 25 minutes (2026-11-09). 2 tasks, 5 files, 2 commits.

## Accomplishments

- **Task 1 (tracer, fd671c60e):** `ticket_viewer(detail)` in `backend/ticket_access.py` returns an async dependency that takes the request and `get_current_user` (the callable the tests override and `has_permission` shares). No `ticket_id` path parameter: return. Staff (`is_ticket_staff`): return without reading the ticket. Otherwise it reads the ticket in the caller's own tenant (`_effective_tenant`; none means no ticket) and raises 404 unless `projection.is_reporter`. `tickets_endpoints.py` gained 3 lines (the import and the `dependencies=` argument of `APIRouter`). Eight HTTP tests on the throwaway database: Carol 404 with a body equal to a made-up id's; Bob 200 with the staff-only comment; Alice 200 without it; Alice's name in another case; other tenant 404 (also for t2 staff); custom role Technician 404 without and 200 with manage:tickets in its document; analyst API key 404 with narrow scopes and 200 with manage:tickets.
- **Task 2 (test commit 6686731c5):** the same guard proven on history (Carol 404, Bob full, Alice projected and shorter), comments (404, comments unchanged, same answer as a missing ticket; Alice still comments), attachments (Carol 404, nothing stored, `TICKET_ATTACHMENT_DIR` empty; Alice 200 and exactly one file) and delete (a custom role holding manage:settings but not manage:tickets gets 404 and the ticket stays). In `test_tickets.py` a new `_STAFF` (role analyst, t1) reads the mocked tickets of other people, and two requester cases (404 on another person's ticket, 200 on one reported by v@test.com) plus a history 404 case were added; the list, create and SLA tests stay on `_VIEWER`.

## TDD Gate Compliance

Task 1 is a tracer: the HTTP tests were written first and run before the guard existed (4 of 28 failed on the planned assertions: the Carol read, the made-up-id equality, the custom role and the API-key case returned 200; the other tests passed because they describe access that must not change). One test of my own (reporter by email) was dropped because `TokenData` has no email field; it was a test error, not RED. GREEN: 47 passed. Task 2 (tdd=true): the legacy RED was observed (3 `test_tickets.py` get/history tests failed with 200-versus-404 once the guard existed, then went green on `_STAFF`); the new route tests describe behavior Task 1 already delivers, so I proved they have teeth by pointing the router's `dependencies` at an empty list: 10 tests failed (8 in the access file, 2 in `test_tickets.py`), then restored the guard (diff against HEAD empty). No REFACTOR.

## Verification

- Task 1 command (access suite + reporter-ticket suite): 47 passed, 0 skipped.
- Task 2 desk regression command: 1095 collected, 1094 passed, 1 failed (a test identity, see Deviations); after the fix the file re-ran green (portal routes, ticket tests and access tests: 91 passed). No test was skipped.
- `backend/tests/test_catalogue_route_parity.py`: 48 passed, 2 failed (`test_unguarded_routers_are_ledgered`, `test_ledger_ratchets`), exactly the two known failures of the working-tree rules (the user's `catalogue-gaps.json` expects the set-aside `reporting_endpoints.py` edits); not caused by this plan.
- Acceptance: `def ticket_viewer(` present; `ticket_access.ticket_viewer()` in the `APIRouter` call; `git show fd671c60e -- backend/tickets_endpoints.py` adds 3 lines and touches no line of `download_attachment` (the route is not in HEAD); `git diff --numstat -- backend/tickets_endpoints.py` is empty because the user's edits are currently set aside (the 38 11 check applies when they return; nothing of theirs was staged or edited); Carol tests assert equal status and detail for a colleague's ticket and a made-up id; the attachment test asserts the 404 and an empty `TICKET_ATTACHMENT_DIR`; `_STAFF` has role analyst.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking, test identity] A profile-less technician in the portal route tests used `portal_user`**
- **Found during:** Task 2 desk regression run
- **Issue:** `test_a_reply_from_staff_shows_the_staff_name_or_none` had a technician "zed@x.co" comment on Alice's ticket as a requester-role user; under the guard that caller gets 404 and the comment is never written (KeyError 'Me too').
- **Fix:** the identity is now `staff_user` (the plan anticipated this: "fix only test identities if a technician in some other desk test still uses portal_user").
- **Files modified:** backend/tests/test_service_desk_portal_routes.py
- **Commit:** 6686731c5

**2. [Process] Co-Authored-By trailer removed from the Task 1 commit**
- The harness attribution reminder asked for a trailer; CLAUDE.md and the plan forbid one (no `attribution.commit` in `.claude/settings.json`). The Task 1 commit was amended before anything else depended on it (`fd671c60e`); no trailer on any 85-32 commit.

**Total deviations:** 1 auto-fixed (test identity), 1 process note. **Impact:** none on behavior or scope.

## Known Stubs

None.

## Threat Flags

None. T-85-112 and T-85-113 are mitigated and tested; T-85-114 is mitigated by construction (same router) and cannot be tested until the user's uncommitted download route returns to the tree. T-85-SC accepted (no install).

## Follow-ups

- Guard order: because the router dependency runs before each route's `has_permission`, a caller who is neither staff nor reporter now sees 404 where a route used to answer 403. Intended (T-85-113); the staff-only actions (85-34) will still need their own permission checks for reporters on their own ticket.
- When the user's uncommitted `tickets_endpoints.py` edits come back, add a test that a requester gets 404 on `GET /{ticket_id}/attachments/{attachment_id}/download` of a colleague's ticket (T-85-114).

## Next

Ready for 85-33.

## Self-Check: PASSED

- FOUND: backend/ticket_access.py (ticket_viewer), backend/tickets_endpoints.py (guard), backend/tests/test_ticket_staff_access.py, backend/tests/test_tickets.py, backend/tests/test_service_desk_portal_routes.py
- FOUND commits: fd671c60e, 6686731c5
