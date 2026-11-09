---
phase: 85-first-line-service-desk
plan: 31
subsystem: service-desk-notifications
tags: [g-85-4, cr-501, notification-audience, history, ticket-staff, structural-test, gap-closure]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: "85-30: backend/ticket_access.py is_ticket_staff and the staff identities of the desk test world"
provides:
  - "backend/notification_audience.py: reader_names(user) and async reader_filter(user, tenant_id, *, all_tenants=False), the one notice audience filter"
  - "GET /api/notifications/history on the shared filter, keyed on tenantId, Super Admin cross-tenant under the per-person rules, 403 for a tenant-less non-super caller"
  - "ticket_staff notices hidden from every reader without manage:tickets (feed, mark-read, read-all, delete, history)"
  - "tests/test_notification_audience_structure.py: repository-wide AST scan of every reader of db.notifications with a non-rotting allow-list"
affects: [85-32, 85-33, 85-34, 85-35, 85-36]

actuals:
  tokens: 9200
  tasks: 2
  commits: 3
plan_head_before: 559c57b3bbc5037c1d47e3046b283e011a7babba
plan_head_after: 4f5ad02b931f5177b70850b8004cbef11626ce5a
commits: 3

tech-stack:
  added: []
  patterns:
    - "One audience filter module that every route reading db.notifications starts from; a repository-wide AST scan (routes must call reader_filter, system jobs sit on a named allow-list that fails when an entry rots) makes a second unfiltered reader fail the suite"
    - "all_tenants drops only the tenantId clause; recipient, excludeRecipients, tenant_admins and ticket_staff rules always apply, a Super Admin included"

key-files:
  created:
    - backend/notification_audience.py
    - backend/tests/test_notification_history_audience.py
    - backend/tests/test_notification_audience_structure.py
  modified:
    - backend/reporting_endpoints.py
    - backend/notification_endpoints.py
    - backend/tests/test_service_desk_notification_audience.py
    - backend/tests/test_service_desk_comments.py

key-decisions:
  - "A-85-G21 kept: ticket lifecycle notices without audience or recipient still reach every tenant user in feed and history; not decided by UD-1..UD-4, reported as a follow-up (T-85-111)"
  - "A-85-G22: reporting_endpoints.py matched HEAD at run time (the orchestrator had set the user's decorator edits aside), so the file was staged by path with only the get_notification_history hunk; the index-blob method was not needed"
  - "A-85-G23 kept: a Super Admin holds *, so tenant_admins and ticket_staff clauses hide nothing from them; only recipient and excludeRecipients narrow their cross-tenant history"
  - "The old structural test of the four feed routes was deleted (superseded by the repository-wide scan, said so in the audience test's docstring)"

requirements-completed: [DESK-01]

coverage:
  - deliverable: "CR-501 / D-33: history reads through reader_filter; a requester, a colleague, staff and a tenant admin each read exactly what the feed serves them"
    verification:
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_a_requester_reads_her_own_and_the_tenant_wide_notices_only"
        status: pass
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_a_colleague_never_reads_a_notice_addressed_to_someone_else"
        status: pass
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_staff_read_the_staff_notice_unless_it_excludes_them"
        status: pass
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_a_tenant_admin_reads_the_admin_and_staff_notices"
        status: pass
    human_judgment: false
  - deliverable: "UD-4: history keys on tenantId (tenantId-only notice present, snake tenant_id mismatch follows tenantId)"
    verification:
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_a_notice_stored_with_tenant_id_only_is_read_and_the_snake_field_does_not_decide"
        status: pass
    human_judgment: false
  - deliverable: "UD-4 / PROH-85-22: Super Admin spans every tenant, never reads a notice addressed to someone else; no-tenant caller gets 403; severity, limit, order, shape unchanged"
    verification:
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_the_super_admin_spans_every_tenant_under_the_per_person_rules"
        status: pass
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_a_caller_without_a_tenant_is_refused_not_served_or_crashed"
        status: pass
      - kind: test
        ref: "backend/tests/test_notification_history_audience.py#test_severity_and_limit_narrow_the_history_newest_first"
        status: pass
    human_judgment: false
  - deliverable: "UD-2 / D-11: ticket_staff notices hidden from non-staff in feed, read-all, delete and history; staff colleagues still read them"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_notification_audience.py#test_a_requester_colleague_has_no_staff_comment_notice_in_the_feed"
        status: pass
      - kind: test
        ref: "backend/tests/test_service_desk_notification_audience.py#test_read_all_without_ticket_staff_permission_leaves_the_staff_notice_alone"
        status: pass
      - kind: test
        ref: "backend/tests/test_service_desk_notification_audience.py#test_read_all_without_ids_marks_only_what_the_reader_can_read"
        status: pass
    human_judgment: false
  - deliverable: "Repository-wide scan: every route touching db.notifications calls reader_filter; allow-list holds three system jobs and no route; stale entries and blind scans fail"
    verification:
      - kind: test
        ref: "backend/tests/test_notification_audience_structure.py (5 tests, three synthetic negative cases)"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 31: Notice history on the shared audience filter Summary

**GET /api/notifications/history now builds its query from one shared `notification_audience.reader_filter` (tenantId-keyed, per-person rules, ticket_staff notices for staff only, Super Admin cross-tenant under the same rules), the four feed routes use it too, and a repository-wide AST scan fails the suite when any route reads db.notifications without it.**

Duration: about 10 minutes (2026-11-09). 2 tasks, 7 files, 3 commits.

## Accomplishments

- **Task 1 (tracer, b7e178bd3):** `backend/notification_audience.py` holds `reader_names` and `reader_filter` (tenantId clause unless `all_tenants`; `tenant_admins` hidden without `*` or `manage:agents`; `ticket_staff` hidden unless `ticket_access.is_ticket_staff`; recipient and excludeRecipients rules). `get_notification_history` imports it inside the function, drops its `tenant_id`-keyed query, raises 403 "Tenant context required" before the try block for a non-super caller without a tenant, and keeps severity, limit, newest-first order and the `{notifications, count}` shape. Eight behaviour tests on the throwaway database cover requester, colleague, staff, excluded reporter, tenant admin, Super Admin (t2-wide and t2-super present; alice-only, carol-only, t2-alice-only absent), tenantId-only and mismatch notices, 403, severity and limit.
- **Task 2 (TDD; RED 975d2d5dc, GREEN 4f5ad02b9):** `notification_endpoints.py` loses its private `_reader_names`/`_reader_filter` and its four routes call `reader_filter(current_user, tenant_id)`. `test_notification_audience_structure.py` parses every `.py` under `backend/` (tests, `venv*`, site-packages, node_modules, `__pycache__` pruned), finds every function calling a reading or changing method on `notifications`, requires routes to call `reader_filter`, and holds the allow-list `pending_agents.notify_pending`, `retention_service.cleanup_notifications`, `send_pending_emails.send_pending_notifications` (exactly the three the scan finds) with a reason each; three synthetic-source tests prove it fails for an unfiltered route, an allow-listed route and a stale allow-list entry. The audience and comments suites give staff readers `manage:tickets`, and gain the non-staff read-all and Erin feed cases.

## TDD Gate Compliance

Task 2 RED: `test(85-31)` 975d2d5dc, 4 failed / 18 passed. The three behaviour failures were on the planned assertions (a non-staff reader's feed or read-all still held the staff notice: Erin, Alice with no reporter, Carol read-all 3 instead of 2); the fourth was the repository scan reporting the four feed routes without `reader_filter`. Semantic assessment: the target tests executed and failed for the intended reason, no collection, import or fixture fault. GREEN: `feat(85-31)` 4f5ad02b9, 97 passed. No REFACTOR needed.

## Verification

- Task 1 command (3 files): 37 passed, 0 skipped.
- Task 2 command (7 files): 97 passed, 0 skipped. Extra suites run for blast radius: `test_itam_warranty_notify`, `test_itam_finance_sweep_resilience`, `test_service_desk_portal_routes`, `test_service_desk_lifecycle`, `test_service_desk_tracer`: 108 passed.
- Acceptance: no `def _reader_filter`/`def _reader_names` left in `notification_endpoints.py`; `grep -c "reader_filter(current_user, tenant_id)"` prints 4; the user's ` M` on `backend/tests/test_notification_service.py` is untouched and not committed; `reporting_endpoints.py` diff holds only `get_notification_history`.
- The two catalogue route-parity tests named in the working-tree rules were not part of this plan's verify commands and were not run.

## Deviations from Plan

None - plan executed exactly as written. Two points worth knowing, neither a deviation:

- `reporting_endpoints.py` showed no ` M` at run time (the orchestrator had set the user's decorator edits aside), so the numstat 5 5 acceptance line is moot in this tree; the commit holds only the `get_notification_history` hunk, which keeps the user's edits restorable without a conflict beyond that function.
- `test_a_staff_notice_of_a_ticket_with_no_reporter_reaches_everyone` was renamed to `..._reaches_every_staff_member` and now asserts the requester colleague does not read it: under UD-2 a ticket_staff notice never reaches a non-staff reader, whatever its exclusion list says.

**Total deviations:** 0. **Impact:** none.

## Follow-up for the user (T-85-111, A-85-G21)

Ticket lifecycle notices written without an audience or recipient (created, status changed, assigned, SLA breached, escalated with its reason) still reach every user of the tenant in the feed and the history. The diagnosis names them as the same class of exposure; UD-1..UD-4 do not decide it, so they are unchanged and need a product decision.

## Known Stubs

None.

## Threat Flags

None. T-85-107 to T-85-110 are mitigated as planned; T-85-111 is the accepted follow-up above.

## Next

Ready for 85-32.

## Self-Check: PASSED

- FOUND: backend/notification_audience.py, backend/tests/test_notification_history_audience.py, backend/tests/test_notification_audience_structure.py
- FOUND commits: b7e178bd3, 975d2d5dc, 4f5ad02b9
