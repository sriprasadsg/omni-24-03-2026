---
phase: 85-first-line-service-desk
plan: 33
subsystem: service-desk-ticket-access
tags: [g-85-4, wr-502, ud-2, ticket-scope, reports, csv-export, projection, gap-closure]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: "85-30 ticket_access.is_ticket_staff; 85-32 ticket_access.ticket_viewer router guard"
provides:
  - "backend/ticket_access.py own_tickets_filter(user) and async tickets_scope(user): None for ticket staff, an escaped, anchored, case-insensitive reporter filter for everybody else"
  - "GET /api/tickets, GET /api/tickets/stats, the six /api/tickets/reports/* routes and GET /api/tickets/export/csv restricted to the caller's own tickets for non-staff, in the database query"
  - "projection.for_viewer / history_for_viewer with a keyword-only staff=False input: stored ticket and full history only for staff who did not raise the ticket"
affects: [85-34, 85-35, 85-36]

actuals:
  tokens: 8500
  tasks: 3
  commits: 5
plan_head_before: a9a0eee05f7b4a3f213069dd8e7c9e13820e815e
plan_head_after: 03d6efce5b854279816eb0e983f7cdc1ed95af56
commits: 5

tech-stack:
  added: []
  patterns:
    - "One helper (tickets_scope) decides what a caller may count or list; the restriction is ANDed into the Mongo query ($and), never applied to rows afterwards, so totals, pages, aggregations and exports agree"
    - "The projection is told who is staff by an explicit input with a closed default, instead of inferring it from the absence of a reporter match"

key-files:
  created:
    - backend/tests/test_ticket_staff_lists.py
  modified:
    - backend/ticket_access.py
    - backend/tickets_service.py
    - backend/tickets_endpoints.py
    - backend/tickets_config_mixin.py
    - backend/ticket_reports_endpoints.py
    - backend/service_desk/projection.py
    - backend/tests/test_service_desk_reporter_ticket.py

key-decisions:
  - "A-85-G26 kept: the six report routes and the CSV export (a fifth router on /api/tickets, guarded by view:dashboard only) get the same query-level scope as the list rather than staying open or becoming staff-only"
  - "A-85-G27 kept: the AI chat /tickets skill is untouched and is a follow-up for the user (T-85-118 accepted)"
  - "The scope joins the query as $and: [scope], so it combines with the reporter, search and status filters; a ?reporter= naming someone else returns nothing, a ?search= cannot reach another person's title"
  - "A name with no characters (empty username and email) matches nothing: an empty $in"
  - "For a staff caller the list route reuses tickets_scope's verdict (scope is None) as the projection's staff flag, so the permission lookup happens once per request, not once per ticket"

requirements-completed: [DESK-01]

coverage:
  - deliverable: "UD-2 / WR-502 / T-85-115: GET /api/tickets for a non-staff caller lists only tickets they raised (case-insensitive), total and paging count only those, a reporter parameter or search cannot widen it; staff and the Super Admin list as before"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_a_requester_lists_only_the_tickets_they_raised_and_the_total_agrees"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_a_reporter_parameter_or_a_search_cannot_widen_the_scope"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_staff_and_the_super_admin_list_everything_as_before"
        status: pass
    human_judgment: false
  - deliverable: "T-85-116: a name made of regex characters, or no name at all, matches only itself / nothing"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_a_name_made_of_regex_characters_matches_only_itself"
        status: pass
    human_judgment: false
  - deliverable: "A-85-G26: stats, the six reports and the CSV export count and export only a requester's own tickets; staff keep the tenant"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_stats_count_only_a_requesters_own_tickets"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_the_summary_sla_and_resolution_reports_count_only_a_requesters_own_tickets"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_the_trends_assignee_and_ageing_reports_count_only_a_requesters_own_tickets"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_the_csv_export_holds_only_a_requesters_own_tickets"
        status: pass
    human_judgment: false
  - deliverable: "T-85-117: the projection without a staff argument returns the requester projection; staff who did not raise the ticket get the stored ticket; a reporter who is also staff still gets the projection (T-85-93 / AR-85-09)"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_the_projection_without_a_staff_argument_fails_closed"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_staff_who_did_not_raise_the_ticket_get_it_stored_and_the_reporter_never_does"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_lists.py#test_a_reporter_with_the_admin_role_still_gets_the_projection_of_their_own_ticket"
        status: pass
    human_judgment: false
  - deliverable: "The twelve ticket-returning routes still go through the projection (AST check) and the existing ticket, desk, comment and portal suites stay green"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_every_route_that_returns_a_ticket_goes_through_the_projection"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 33: Own-tickets scope for lists, counts, reports and export Summary

**A caller who is not ticket staff (no manage:tickets) now lists, counts, reports on and exports only the tickets they raised: `ticket_access.tickets_scope` is ANDed into the database query of GET /api/tickets, /stats, the six /reports/* routes and /export/csv, and `projection.for_viewer` / `history_for_viewer` take an explicit `staff=False` input so the stored ticket reaches only staff who did not raise it.**

Duration: about 25 minutes (2026-11-09). 3 tasks, 8 files (1 created), 5 commits.

## Accomplishments

- **Task 1 (tracer, 6458b0f62):** `own_tickets_filter(user)` builds a reporter `$in` of anchored, `re.escape`d, case-insensitive patterns from the username and email (an empty `$in` for a nameless caller); `tickets_scope(user)` returns None for staff. `tickets_service.list_tickets(..., scope=None)` appends it as `$and: [scope]` (3 added lines), and the list route passes it. Tests on the desk app and the throwaway database: Alice (and her name in another case) lists exactly her 3 tickets with total 3 and correct paging; `?reporter=bob@x.co` and a search for Bob's title return nothing; a user named `a.*@x.co` lists only the ticket whose reporter is literally that name and a nameless user lists nothing; Bob (staff) lists the tenant's six tickets; the Super Admin lists the seven of both tenants. The reporter-ticket list test now expects the reporter not to see another person's ticket, while staff (a second technician who raised neither ticket) still do, with their comments.
- **Task 2 (test 765d2cf9a, feat 59e98958d):** `get_stats(..., scope=None)` puts the scope in the base filter every count and aggregation reads; `ticket_reports_endpoints._scope(user)` returns `{"$and": [scope]}` or `{}` and is merged into the base filter of all seven routes (summary, trends, SLA, resolution, assignee, ageing and the CSV export). Tests compare totals, status counts, escalated, SLA, resolution counts, opened counts per day, assignee rows, ageing totals and the exported ticket numbers for Alice and Bob; an `?assignee=zed` on the export gives a requester nothing.
- **Task 3 (test 4840f5125, feat 03d6efce5):** `for_viewer(ticket, user, *, staff=False)` and `history_for_viewer(ticket, entries, user, *, staff=False)` return the stored ticket or full history only when `staff` is true and the user did not raise the ticket, the reporter projection otherwise. `tickets_endpoints._shown` and `_shown_history` are async with an optional `staff` argument (looked up with `is_ticket_staff` when absent); every route awaits them; the list route passes `staff=scope is None`, so the permission lookup happens once per request. Unit tests cover the closed default, staff, staff who raised the ticket, and `None`; an HTTP test shows a reporter with role admin gets the projection on GET and on the list while a technician gets the stored ticket.

## TDD Gate Compliance

Task 1 is a tracer: the list tests ran first and 3 of 4 failed (the requester listed 6 tickets instead of 3, `?reporter=bob@x.co` returned Bob's ticket, the regex name matched everything), the fourth (staff and Super Admin as before) passed because it describes behavior that must not change. Task 2 and Task 3 followed the test then feat sequence: the RED commits `765d2cf9a` (4 of 8 failed with counts of 6 instead of 3 and an export holding Bob's ticket) and `4840f5125` (2 failed: the non-reporter received the staff-only comment without the argument, and `for_viewer()` rejected `staff=`; the HTTP admin-reporter test passed because that behavior is unchanged), then GREEN commits `59e98958d` and `03d6efce5`. No REFACTOR commit.

## Verification

- Task 1 command (lists, reporter-ticket, staff-access and ticket suites): 79 passed, 0 skipped.
- Task 2 command (lists, bundles-and-reports, tickets): 77 passed; `test_sidebar_audit_fixes.py` (which touches the stats and list routes): 11 passed.
- Task 3 command (lists, reporter-ticket, staff-access, tickets, comments, portal routes): 133 passed, 0 skipped.
- `test_catalogue_route_parity.py`: 48 passed, 2 failed (`test_unguarded_routers_are_ledgered`, `test_ledger_ratchets`), exactly the two known failures of the working-tree rules (the user's `catalogue-gaps.json` expects the set-aside `reporting_endpoints.py` edits); no route was added or its guard changed by this plan.
- Acceptance: `own_tickets_filter` and `async def tickets_scope(` present, `re.escape` used; Alice's total equals the number of tickets returned (query-level); `grep -c "await _scope(current_user)" backend/ticket_reports_endpoints.py` prints 7; `get_stats` accepts `scope`; both projection helpers have a keyword-only `staff` defaulting to False; `tickets_endpoints.py` is 607 to 611 lines (net +4, limit 8), `ticket_reports_endpoints.py` net +7 (limit 12), `tickets_service.py` +3 (limit 4). The "numstat 38 11" check does not apply: the user's uncommitted `tickets_endpoints.py` edits are currently set aside, so the file matched HEAD when edited and was staged by plain path; none of the user's attachment lines (`download_attachment`, `_UPLOAD_DIR`, the FileResponse import) were touched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking, test identity] The reporter-ticket list test listed Bob's ticket as Bob**
- **Found during:** Task 1
- **Issue:** After updating the legacy list test, staff Bob listing his own ticket returned the requester projection (he raised it; T-85-93), so "staff still see the other ticket with its comments" failed for the wrong reason.
- **Fix:** the staff part of that test now uses a second technician (`dave@x.co`) who raised neither ticket.
- **Files modified:** backend/tests/test_service_desk_reporter_ticket.py
- **Commit:** 6458b0f62

**2. [Rule 3 - Blocking, test harness] The export's own decorator limiter returned 429 in the report tests**
- **Found during:** Task 3 (test run after the RED commit; the 5-per-minute export limit counted calls across runs of the file)
- **Issue:** disabling the app-level slowapi limiter does not disable the module-level decorator limiter of `ticket_reports_endpoints`.
- **Fix:** the `reports` fixture also sets `ticket_reports_endpoints.limiter.enabled = False` with monkeypatch (the plan asked for the limiter off for the test).
- **Files modified:** backend/tests/test_ticket_staff_lists.py
- **Commit:** 4840f5125

**3. [Process] Co-Authored-By trailer not added** per CLAUDE.md and the plan; no 85-33 commit has one.

**4. [Scope note] Test data holds six t1 tickets, not five** (an extra `a.*@x.co` ticket for the regex-character case); the plan's behavior block asked for that name case and the near-miss ticket separately.

**Total deviations:** 2 auto-fixed (test identity, test harness), 2 notes. **Impact:** none on behavior or scope.

## Known Stubs

None.

## Threat Flags

None. T-85-115 (lists, counts, reports, export) and T-85-116 (regex names) and T-85-117 (projection default) are mitigated and tested. T-85-118 (AI chat `/tickets` skill, titles only, no user identity) is accepted and reported below. T-85-SC accepted (no install).

## Follow-ups

- **For the user (A-85-G27 / T-85-118):** `backend/skill_handlers_queries.py handle_tickets` still lists the five newest ticket titles and statuses of the tenant to any chat user. It receives no user identity, so it cannot be scoped without a signature change; it was left unchanged by plan.
- The one query-level scope covers `view:dashboard` callers; `POST /api/tickets/bulk` and the other staff-only actions on a reporter's own ticket remain for 85-34.
- When the user's uncommitted `tickets_endpoints.py` edits come back, the merge touches the lines of `list_tickets`/`get_stats` this plan changed only at the call sites (scope argument); re-check that the router guard and the scope still sit on the restored file.

## Next

Ready for 85-34.

## Self-Check: PASSED

- FOUND: backend/ticket_access.py (tickets_scope), backend/tickets_service.py, backend/tickets_config_mixin.py, backend/tickets_endpoints.py, backend/ticket_reports_endpoints.py, backend/service_desk/projection.py, backend/tests/test_ticket_staff_lists.py, backend/tests/test_service_desk_reporter_ticket.py
- FOUND commits: 6458b0f62, 765d2cf9a, 59e98958d, 4840f5125, 03d6efce5
