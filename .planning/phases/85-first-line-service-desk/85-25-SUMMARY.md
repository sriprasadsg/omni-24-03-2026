---
phase: 85-first-line-service-desk
plan: 25
subsystem: service-desk
tags: [reporter-projection, d-11, cr-401, tickets-endpoints, history, information-disclosure]

requires:
  - phase: 85-first-line-service-desk
    provides: "85-08 comment visibility, 85-13/14 lifecycle history entries, 85-19 requester_items / is_reporter in projection.py"
provides:
  - "projection.requester_may_read / reporter_ticket / reporter_history / for_viewer / history_for_viewer: the one rule for what the reporter may read of their own ticket"
  - "tickets_endpoints._shown and _shown_history applied to every ticket-returning route (12 routes)"
  - "shared/service-desk-requester-comments.json: the case table the server rule is tested against here and the UI helper in 85-26"
affects: [85-26 UI half of CR-401, 85-29 phase gate, 85-VERIFICATION gap 2 re-verification]

actuals:
  tokens: 11500
  tasks: 2
  commits: 2
plan_head_before: 41c6b56364426cde6cb6438b2b86054613f67249
plan_head_after: f4ce6404da2ba2f0afeb20bbc3a9cd2de1f32b0b
commits: 2

tech-stack:
  added: []
  patterns:
    - "One visibility helper (_requester_visible) shared by the answer panel and the reporter's comment list"
    - "Route-level projection helpers (_shown / _shown_history) pinned by an AST test over the router module"
    - "Shared JSON case table asserted by both the Python and the UI rule"

key-files:
  created:
    - shared/service-desk-requester-comments.json
    - backend/tests/test_service_desk_reporter_ticket.py
    - .planning/phases/85-first-line-service-desk/deferred-items.md
  modified:
    - backend/service_desk/projection.py
    - backend/tickets_endpoints.py

key-decisions:
  - "A-85-G05: the reporter's own comments are always readable (a portal comment is stored staff-only), except an ai_draft"
  - "A-85-G06: a reporter with staff permissions still gets the requester projection of their own ticket (same rule as GET /{id}/service-desk)"
  - "A-85-G07: a withdrawn AI answer stays hidden in the full ticket JSON; the requester-visible withdrawn_notice is kept"
  - "A-85-G08: reporter history drops draft_sent/draft_discarded and commented entries by someone else unless desk-marked requester or the preview matches a readable comment"
  - "The projection only rebuilds keys the ticket has: the list route (no history key) gets no history added"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "CR-401 server / D-11: GET /api/tickets/{id} for the reporter carries only requester-readable comments (own comments included), no desk key, AI comments cut to REPORTER_AI_KEYS; staff and other tenants unchanged"
    requirement: "DESK-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_the_reporter_reads_their_own_ticket_without_the_staff_side"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_a_technician_who_did_not_raise_the_ticket_gets_it_unchanged"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_a_reporter_with_an_admin_role_still_gets_the_requester_view"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single source: the shared case table (16 cases) agrees with projection.requester_may_read"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_the_case_table_agrees_with_the_server_rule"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every other ticket-returning route (list, create, patch, comments, links, work-log, approve, reject, escalate) projects the reporter's own ticket; the history route applies the history rule"
    requirement: "DESK-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_the_list_projects_the_reporters_ticket_and_leaves_the_others"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_the_history_route_drops_what_the_reporter_may_not_read"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_approve_reject_and_escalate_project_whatever_the_service_returns"
        status: pass
    human_judgment: false
  - id: D4
    description: "A future ticket-returning route that skips the projection fails an AST test"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_reporter_ticket.py#test_every_route_that_returns_a_ticket_goes_through_the_projection"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-09
status: complete
---

# Phase 85 Plan 25: Reporter projection of the legacy ticket JSON Summary

**The person who raised a ticket now receives only what the requester may read (requester-visible and own comments, no desk key, no draft or hidden history entry) on all 12 ticket-returning routes of tickets_endpoints.py, through one rule in projection.py; staff and other tenants are unchanged (CR-401 server half, T-85-77 accepted residual now mitigated as T-85-90).**

## Performance

- **Duration:** about 8 min (11 min wall clock including the reproduction runs)
- **Started:** 2026-11-09T16:09Z (approx.)
- **Completed:** 2026-11-09T16:20Z
- **Tasks:** 2
- **Files modified:** 5 (3 created)

## Accomplishments
- `projection.py`: `_requester_visible` (now the filter of `requester_items` too), `requester_may_read` (requester-visible and not withdrawn, or written by the reporter; never an `ai_draft`), `reporter_ticket` (copy with comments filtered, AI comments cut to `REPORTER_AI_KEYS` with citations reduced to `articleId` and `title`, `desk` removed, history filtered), `reporter_history`, `for_viewer`, `history_for_viewer`, and the constants `REPORTER_AI_KEYS`, `REPORTER_DESK_KEYS` (empty), `REPORTER_HIDDEN_HISTORY_ACTIONS`.
- `tickets_endpoints.py`: `_shown(ticket, user)` and `_shown_history(ticket, history, user)` (lazy imports, the file's style); applied at GET list (each ticket), POST create, GET /{id}, PATCH, POST comments, POST/DELETE links, POST work-log, POST approve/reject/escalate, and GET history. Intake, webhook, the comment hook and mention notices still read the full ticket; only the returned value is projected.
- `shared/service-desk-requester-comments.json`: 16 cases (version, description, reporter, cases[]) for the server rule here and the UI helper in 85-26.
- `test_service_desk_reporter_ticket.py` (368 lines, 19 tests): case table, projection keys, shared-rule guard, GET as reporter / technician / other tenant / admin-role reporter, list (with and without `?reporter=`), PATCH, comments, links, work-log, approve/reject/escalate (service patched to return the full ticket), create, history, and the AST route check over the twelve route names.

## Task Commits

1. **Task 1 (tracer): the reporter reads their own ticket through GET /api/tickets/{id}** - `927bcff49` (feat)
2. **Task 2: every other ticket-returning route and the history route, pinned by an AST check** - `f4ce6404d` (feat)

**Plan metadata:** the SUMMARY/STATE/ROADMAP docs commit follows this file.

TDD note (Task 2 is `tdd="true"`): the tests were written in the same working pass as the call-site edits, so there is no separate RED commit. RED was reproduced afterwards on a throwaway detached checkout of `927bcff49` (Task 1 state) with the final test file: 12 failed, 7 passed, each failure on the planned assertion (a planted staff text, draft text or desk key in the reporter's response, or `list_tickets skips the reporter projection` in the AST test); the checkout was removed. The `check tdd-red-evidence` classifier does not read pytest output, so this semantic assessment is recorded here.

## Files Created/Modified
- `backend/service_desk/projection.py` - reporter projection (372 lines)
- `backend/tickets_endpoints.py` - `_shown`, `_shown_history` and 12 call sites (the user's hunks left unstaged)
- `shared/service-desk-requester-comments.json` - the case table
- `backend/tests/test_service_desk_reporter_ticket.py` - new tests
- `.planning/phases/85-first-line-service-desk/deferred-items.md` - the out-of-scope wall-clock failure below

## Decisions Made
Followed A-85-G05..G08 as planned. One small choice: `reporter_ticket` rebuilds `comments` and `history` only when the ticket carries those keys, so the list route (history excluded by the service) does not gain a history key. The AST test also checks `result` (the list route's return name) and exempts only `list_tickets`, whose tickets are projected one by one.

## Deviations from Plan

### Auto-fixed Issues

None - the code and tests follow the plan. Two process notes:

**1. [Plan convention - TDD] Task 2 has one commit, not a RED/GREEN pair** - see the TDD note above; RED reproduced after the fact.

**2. [Test setup] The test `world` fixture also patches `ticket_notifications.notify_comment_added` and `service_desk.intake.on_ticket_created`** so the comment route's background notice task and the desk intake do not write into the throwaway database after a test ends; the tests assert the projection, not the notices.

---

**Total deviations:** 0 auto-fixed, 2 process notes
**Impact on plan:** none on scope.

## Issues Encountered
`backend/tests/test_service_desk_lifecycle.py::test_this_fixed_it_resolves_the_ticket_and_only_this_does` fails in the Task 2 verify run (1 failed, 187 passed): the test confirms the ticket at the fixed `NOW = 2026-11-09 14:30 UTC` while the hold started at the real clock, so `total_hold_duration` is negative once the real time passes 14:30 UTC that day. It exercises `lifecycle.confirm` and the write helpers only, none of this plan's files; reproduced identically on a detached checkout of the pre-plan commit `41c6b5636`; logged in `deferred-items.md` (fix in 85-29 or a test-hygiene pass: derive the hold start from `NOW`). Not fixed here (scope boundary). All other tests in the Task 2 command passed with 0 skipped.

## Known Stubs
None.

## Threat Flags
None. T-85-90, T-85-91 and T-85-92 are mitigated as planned; T-85-93 is accepted as planned. No new endpoint, auth path or schema; CR-401 stays open in the disposition until 85-26 lands the UI half.

## User WIP
`backend/tickets_endpoints.py` was committed through an index blob built from `HEAD` plus only this plan's edits (`git update-index --cacheinfo`). After each commit `git diff --numstat -- backend/tickets_endpoints.py` printed `38 11` (the pre-plan counts), `HEAD` plus the saved user diff is byte-identical to the working file (`cmp` silent), and no added line of either commit matches the user's attachment hunks. No other user file was staged or changed.

## Verification
- Task 1 command: 100 passed, 0 skipped (reporter, comments, portal routes, tray routes, tickets).
- Task 2 command: 187 passed, 1 failed (the pre-existing wall-clock lifecycle test above), 0 skipped, on the private mongod (27998).
- `grep -c "_shown(" backend/tickets_endpoints.py` prints 12, `grep -c "_shown_history("` prints 2; the AST test names exactly twelve routes. projection.py 372 and the test file 368 lines (under 500).
- Not run (by plan): the whole backend suite (85-29), restarts, publishes, push.

## Self-Check: PASSED
Files present: backend/service_desk/projection.py, backend/tickets_endpoints.py, shared/service-desk-requester-comments.json, backend/tests/test_service_desk_reporter_ticket.py, deferred-items.md. Commits present: 927bcff49, f4ce6404d.
