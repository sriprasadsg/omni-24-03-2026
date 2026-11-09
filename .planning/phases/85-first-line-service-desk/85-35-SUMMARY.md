---
phase: 85-first-line-service-desk
plan: 35
subsystem: service-desk-ticket-access
tags: [g-85-4, wr-502, ud-2, service-desk, draft-staff-only, knowledge-gaps, structure-test, gap-closure]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: "85-30 ticket_access.TICKET_STAFF and is_ticket_staff; 85-32 ticket_viewer router guard; 85-33 and 85-34 staff-aware projection and staff-only ticket actions"
provides:
  - "service_desk_endpoints.router carries ticket_access.ticket_viewer with the desk's not_found sentence: a colleague who is neither staff nor the reporter gets 404 on the view, the draft routes, confirm, help and the cited-article reader"
  - "the draft panel, canReplyToRequester and send, edit and discard of a draft need ticket staff who did not raise the ticket; the reporter (staff or not) keeps 403 with the staff_only sentence"
  - "projection.staff_view(ticket, row, viewer, *, staff=False)"
  - "knowledge-gap routes (list, dismiss, restore) and Write article need manage:tickets as well as manage:ai_risks"
  - "test_ticket_staff_routes_structure.py: one classification of every route of the five /api/tickets routers, the fifteen named staff routes, and the closed set of modules declaring the prefix"
affects: [85-36]

actuals:
  tokens: 8700
  tasks: 2
  commits: 3
plan_head_before: ad278d7a842de44c822516af6b66a3de6aa99ddc
plan_head_after: 3f2045d09172972aa0e4a080d6eeaba6997d355f
commits: 3

tech-stack:
  added: []
  patterns:
    - "Staff on a ticket is decided by ticket_access.is_ticket_staff and 'did not raise it', never by 'not the reporter' alone"
    - "Route classification by ast plus runtime router dependencies; the classifier itself has tests with synthetic sources so it cannot pass vacuously"

key-files:
  created:
    - backend/tests/test_service_desk_staff_routes.py
    - backend/tests/test_ticket_staff_routes_structure.py
  modified:
    - backend/service_desk_endpoints.py
    - backend/service_desk/projection.py
    - backend/knowledge_helpdesk_endpoints.py
    - backend/tests/service_desk_knowledge_support.py
    - backend/tests/test_service_desk_knowledge_gaps.py

key-decisions:
  - "A-85-G31 kept as planned: the three draft routes keep view:dashboard in their signatures and refuse inside the async _staff_only, so the reporter still reads the desk's staff_only sentence (403); the structure test counts a _staff_only call, also through _draft_action, as staff-only"
  - "A-85-G30 kept as planned: _require_ticket_access is manage:tickets; Write article needs it too, so a custom Knowledge Base editor role without manage:tickets can no longer write Help desk articles until a tenant admin ticks it"
  - "The structure test classifies the user's future download route with no special case: a {ticket_id} path under tickets_endpoints.router is viewer-guarded"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "UD-2 / WR-502 / PROH-85-26 / T-85-121 / T-85-122: a colleague who is not staff gets 404 on every desk route and the draft and ledger row do not change; only staff who did not raise the ticket read or act on the draft; the reporter, staff or not, gets the requester view and 403 staff_only"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_staff_routes.py#test_a_colleague_who_is_not_staff_gets_404_everywhere_and_nothing_changes"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_staff_routes.py#test_staff_who_did_not_raise_the_ticket_get_the_draft_and_can_discard_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_staff_routes.py#test_the_reporter_gets_the_requester_view_and_the_staff_only_refusal_on_the_draft_routes"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_staff_routes.py#test_a_reporter_who_is_staff_still_gets_the_requester_view_and_no_draft_rights"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-14 / T-85-123: the cited-article reader opens the staff list only for staff who did not raise the ticket; staff_view needs the staff flag"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_staff_routes.py#test_the_cited_article_reader_opens_the_staff_list_only_for_staff_who_did_not_raise_the_ticket"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_staff_routes.py#test_staff_view_needs_the_staff_flag"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-27 with UD-1 / PROH-85-27 / T-85-124: a Knowledge Base editor with view:dashboard but not manage:tickets gets 403 on the gap list, dismiss, restore and Write article; the gap row stays open and no article is saved"
    requirement: DESK-06
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_knowledge_gaps.py#test_the_gap_routes_need_ticket_access_and_article_permission_together"
        status: pass
    human_judgment: false
  - id: D4
    description: "T-85-125: every route of the five /api/tickets routers is classified, the fifteen staff routes keep their check, and only the five modules declare the prefix"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "backend/tests/test_ticket_staff_routes_structure.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "A-85-G30 (Write article now needs manage:tickets) and A-85-G31 (draft routes refuse inside _staff_only)"
    human_judgment: true
    rationale: "Planner readings that need the user's confirmation at verification; the Write article side effect changes what a custom Knowledge Base editor role can do"

duration: 7min
completed: 2026-11-09
---

# Phase 85 Plan 35: Service desk routes under the ticket-staff rule Summary

**The service desk router now carries the 85-32 viewer guard, and only ticket staff who did not raise a ticket see its AI draft or send, edit or discard it; the knowledge-gap routes and Write article need manage:tickets; one structure test classifies every route of the five /api/tickets routers.**

Duration: about 7 minutes (2026-11-09, 22:41 to 22:48 UTC). 2 tasks, 7 files (2 created), 3 commits.

## Accomplishments

- **Task 1 (tracer, 37b7f2890):** `service_desk_endpoints.router` got `dependencies=[Depends(ticket_access.ticket_viewer(messages.API_DETAIL["not_found"]))]`. A new `_is_staff_for` (ticket staff who did not raise the ticket) feeds `get_service_desk` (draft, `draftWaiting`, `canReplyToRequester`), the now async `_staff_only` (403 with the `staff_only` sentence for everybody else, so the reporter keeps the desk's sentence) and `read_cited_article` (staff list only for such staff, the requester list otherwise). `projection.staff_view` takes a keyword-only `staff` flag defaulting to False. Six new tests: Erin (a requester who did not raise the ticket) gets 404 with the `not_found` sentence on the view, the three draft routes, confirm, help and the cited-article reader, and afterwards the draft is still waiting, the ticket open and the desk ledger row identical; STAFF2 gets the draft and discards it; the reporter and a reporter holding the admin role get the requester view and 403 on the draft routes; the cited-article branches; `staff_view` without and with the flag.
- **Task 2 (test fa4698cd4, feat 3f2045d09):** `_require_ticket_access` depends on `has_permission(ticket_access.TICKET_STAFF)`; the Knowledge Base test harness gives `manager` manage:tickets and adds `kb_viewer` (manage:ai_risks and view:dashboard); the D-27 test asserts 403 for `kb_viewer` on the list, dismiss, restore and Write article with `gapGroupId`, the gap row open and no article saved. `test_ticket_staff_routes_structure.py` reads each router module's source with `ast` and its runtime dependencies, and checks: every router with a `{ticket_id}` route carries `ticket_viewer`; every route is viewer-guarded, staff-only (also through a delegated helper), own-scoped (`tickets_scope` or the reports' `_scope`), on the reasoned open list (create_ticket, list_templates, get_field_schema) or manage:settings; the fifteen named staff routes each exist once and keep their check; and only the five modules declare the /api/tickets prefix (walk of backend/ excluding tests, venv*, site-packages, node_modules, __pycache__). Three more tests run the classifier and the module scan on synthetic sources (an unknown route, a weakened staff route, a delegated check, a sixth module), so the guard cannot pass vacuously. A mutation check on the real source (approve_ticket reverted to view:dashboard; get_stats with its scope removed) is caught.

## TDD Gate Compliance

Task 1 is a tracer: the new tests ran first and 3 of 6 failed on the planned assertions (a colleague got 200 on the view and the cited-article reader; `staff_view` returned the panel without the staff flag), then the implementation made all pass, and one commit carries both (tracer convention). Task 2 followed test then feat: RED `fa4698cd4` (the D-27 test failed with `kb_viewer` getting 200 on the gap list instead of 403), GREEN `3f2045d09`. The structure test is a regression guard over code that was already correct, so it passed on first run; its own sensitivity is covered by the synthetic-source tests and the mutation check above. No REFACTOR commit.

## Verification

- Task 1 command (staff routes, portal routes, withdraw, write order, tracer, lifecycle, comments): 141 passed, 0 skipped.
- Task 2 command (structure, knowledge gaps, knowledge, reporter ticket, route auth baseline): 85 passed, 0 skipped.
- `test_catalogue_route_parity.py`: 48 passed, 2 failed (`test_unguarded_routers_are_ledgered`, `test_ledger_ratchets`), exactly the two known working-tree failures (the user's `catalogue-gaps.json` expects the set-aside `reporting_endpoints.py` edits); the message names only reporting_endpoints, and no route was added by this plan.
- Acceptance: `service_desk_endpoints.py` contains the `ticket_viewer(messages.API_DETAIL["not_found"])` dependency and `async def _staff_only(` once each; `staff_view` has `*, staff: bool = False`; `_require_ticket_access` uses `TICKET_STAFF`.
- Private mongod on 127.0.0.1:27998 only; the live MongoDB and backend were not touched. No restart, publish or push.

## Deviations from Plan

None - plan executed exactly as written. (Process notes: no commit carries a Co-Authored-By trailer, per CLAUDE.md; every file of the plan was clean before the first edit and was staged by explicit path; Task 2 was committed as test then feat because it is `tdd="true"`.)

## Known Stubs

None.

## Threat Flags

None. T-85-121, T-85-122, T-85-123, T-85-124 and T-85-125 are mitigated and tested; T-85-SC accepted (no install).

## Follow-ups

- **For the user (A-85-G30, needs confirmation at verification):** Write article now needs manage:tickets on top of manage:ai_risks (it can carry `gapGroupId`). A custom Knowledge Base editor role without manage:tickets can no longer write Help desk articles until a tenant admin ticks it; the tenant administrator holds both and is unaffected. The built-in Knowledge Base roles that have view:dashboard but not manage:tickets lose the Knowledge gaps tab (403).
- **For the user (A-85-G31):** the draft routes keep view:dashboard in their signatures and refuse inside `_staff_only`; the test counts that as staff-only.
- **For the user, when your set-aside download route is restored** (`GET /{ticket_id}/attachments/{attachment_id}/download` in `tickets_endpoints.py`, view:dashboard behind the ticket_viewer guard): nothing has to be added to `test_ticket_staff_routes_structure.py`. The structure test classifies it as viewer-guarded by the `{ticket_id}` rule because it sits under `tickets_endpoints.router`, which carries the guard. Only if you later move it to a router without the guard, or drop `{ticket_id}` from its path, must you classify it there: put its function name in `STAFF_ROUTES` (staff only) or in `OPEN_ROUTES` with a reason.
- The service desk screens are unchanged: staff see the draft panel as before; a requester-colleague opening someone else's ticket now gets the plain not-found text. UI work stays with the user.

## Next

Ready for 85-36.

## Self-Check: PASSED

- FOUND: backend/tests/test_service_desk_staff_routes.py, backend/tests/test_ticket_staff_routes_structure.py, backend/service_desk_endpoints.py, backend/service_desk/projection.py, backend/knowledge_helpdesk_endpoints.py, backend/tests/service_desk_knowledge_support.py, backend/tests/test_service_desk_knowledge_gaps.py
- FOUND commits: 37b7f2890, fa4698cd4, 3f2045d09
