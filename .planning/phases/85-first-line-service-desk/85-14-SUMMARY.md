---
phase: 85-first-line-service-desk
plan: 14
subsystem: service-desk
tags: [service-desk, lifecycle, drafts, confirm, working-days, cited-articles, portal-routes]
status: complete

requires: [85-01, 85-03, 85-04, 85-08, 85-12]
provides:
  - "service_desk/lifecycle.py: send_draft, discard_draft, confirm, still_need_help, on_comment_added (all compare-and-set on the raw handle with an explicit tenantId)"
  - "service_desk/workdays.py: add_working_days(start, days, zone), tenant_zone(db, tenant_id), zone_of(name)"
  - "service_desk/projection.py: is_reporter, same_person, waiting_draft, person_replied, blocked, can_reply, staff_view, confirmable, return_at, requester_view(ticket, zone, names), cited_articles, cited_article_ids; requester_items leaves out withdrawn answers"
  - "routes under /api/tickets/{ticket_id}/service-desk: GET (full TicketDeskView), POST drafts/{comment_id}/send, /edit, /discard, POST /confirm, /help, GET articles/{article_id}"
  - "ticket fields desk.personReplied, desk.sentBy/sentAt/edited, desk.discardedBy/discardedAt, desk.helpedAt, desk.confirmedAt, resolved_at; comment ai.state sent/discarded, ai.sentBy, ai.edited"
  - "API_DETAIL keys draft_empty, draft_too_long, help_too_long, article_not_found"
affects: [85-15, 85-16, 85-17, 85-18, 85-19, 85-20, 85-21, 85-22]

actuals:
  tokens: 26700
  tasks: 3
  commits: 3
plan_head_before: 23f113851b97d877e323b7b36cafc90ac0f2f5c4
plan_head_after: 1f893eeebe5c0737ed8a2d4ba787c2b5bc42924b

tech-stack:
  added: []
  patterns:
    - "One compare-and-set on the comment ($elemMatch kind ai_draft and ai.state draft) decides the winner of a send or discard; the status, desk fields, Activity row and notice follow, each wrapped on its own"
    - "A person-sent draft turns the suggested row to executed with approval.approver set and is never autoDispatched, so it is outside the hourly pool and the breaker"
    - "Return date computed from desk.postedAt on every read (never stored), same local hour in the tenant zone"

key-files:
  created:
    - backend/service_desk/lifecycle.py
    - backend/service_desk/workdays.py
    - backend/tests/service_desk_portal_support.py
    - backend/tests/test_service_desk_lifecycle.py
    - backend/tests/test_service_desk_portal_routes.py
    - backend/tests/test_service_desk_workdays.py
  modified:
    - backend/service_desk/projection.py
    - backend/service_desk/messages.py
    - backend/service_desk_endpoints.py
    - backend/tickets_endpoints.py
    - backend/tests/service_desk_support.py

key-decisions:
  - "The comment CAS runs before the status move: the loser of two concurrent sends gets already_handled, and a lost status race after a win only logs (the comment is already with the requester)"
  - "still_need_help writes desk.phase helped after the hand-off, because handoff() sets handed_off; the requester view reads helped"
  - "Cited articles are read from knowledge_docs with {id, tenantId of the ticket, helpdesk true}; a removed, unmarked or forged-global citation answers available False with the cited title and no text"
  - "Staff reply names on the portal come from the users profile name; a person with no profile shows author None so the screen says IT, never an address"
  - "The GET items keep the stored comment kind (ai_answer, requester_reply, handoff_notice, withdrawn_notice, None for a plain staff reply); services/serviceDesk/types.ts RequesterItem.kind names a different set (answer, reply, you, withdrawn, notice) - see hand-over"

requirements-completed: []

coverage:
  - id: D1
    description: "Staff (any user with view:dashboard other than the reporter) send, edit and send, or discard a waiting draft; a sent draft is a requester-visible AI answer keeping citations, with sentBy, edited, status pending_customer, row executed with approver (shadow or refused rows keep their state and get desk fields and a servicedesk.sent event), one requester notice; discard keeps it staff-only, denies the row and starts no second attempt"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_lifecycle.py (send, edit, discard, shadow, refused-row tests); backend/tests/test_service_desk_portal_routes.py#test_staff_send_a_draft_and_the_requester_reads_it; #test_staff_edit_and_send_and_the_refusals_use_the_table_texts; #test_staff_discard_a_draft_and_the_requester_never_sees_it"
        status: pass
    human_judgment: false
  - id: D2
    description: "Refusals read from API_DETAIL: ticket_closed, person_replied, no_requester, already_handled (409), empty / over 900 / unchanged edit (422); two concurrent sends give one 200 and one 409; the reporter is refused 403 on all three draft routes and never sees the draft"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_portal_routes.py#test_two_sends_at_once_through_http_give_one_200_and_one_409; #test_the_reporter_cannot_send_edit_or_discard_their_own_draft; #test_a_resolved_ticket_refuses_the_send_with_the_table_text_and_allows_the_discard; backend/tests/test_service_desk_lifecycle.py#test_the_compare_and_set_refuses_a_draft_that_was_discarded_or_sent_in_between"
        status: pass
    human_judgment: false
  - id: D3
    description: "This fixed it resolves the ticket (resolved_at, phase confirmed, no Undo) and is the only path to resolved; I still need help (optional note up to 1000) reopens it, stores the requester_reply, hands off did_not_help with no requester notice and no second attempt; the reporter typing a comment does the same; a staff comment to the requester sets personReplied and ends Undo, a staff-only note does not; no lifecycle path writes closed"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_lifecycle.py#test_this_fixed_it_resolves_the_ticket_and_only_this_does; #test_i_still_need_help_reopens_the_ticket_for_a_person_with_no_second_attempt; #test_no_path_of_the_lifecycle_closes_a_ticket_and_only_a_yes_resolves_one; backend/tests/test_service_desk_portal_routes.py#test_the_reporter_typing_on_the_portal_sends_it_to_a_person"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cited articles open read-only only when cited on this ticket (reporter: a requester-visible, not withdrawn answer; staff: an answer or the waiting draft), from the ticket's own tenant Help desk set, never global; uncited, global, unknown and cross-tenant ids are 404; a deleted or unmarked article answers available False with its cited title"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_portal_routes.py#test_the_reporter_opens_only_the_articles_cited_on_their_answer; #test_a_citation_naming_a_global_article_never_serves_it; #test_a_deleted_or_unmarked_article_answers_unavailable_with_its_cited_title; #test_staff_open_the_articles_of_the_waiting_draft_and_the_reporter_does_not"
        status: pass
    human_judgment: false
  - id: D5
    description: "returnAt is 3 working days after desk.postedAt, Monday to Friday in the tenant's maintenance_settings.timeZone (UTC when absent or unknown), same local hour across a weekend and a daylight saving change, never stored; notice and confirmedAt follow desk.phase; staff replies carry the profile name"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_workdays.py (14 tests); backend/tests/test_service_desk_portal_routes.py#test_the_requester_view_gives_the_return_date_in_the_tenant_zone; #test_the_notice_follows_the_desk_phase; #test_a_reply_from_staff_shows_the_staff_name_or_none"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 14: Draft actions, the requester's answer and cited articles Summary

Staff can now send, edit or discard a waiting draft through the portal; the requester resolves the ticket only by saying This fixed it, and I still need help (or typing on the ticket) sends it to a person with no second attempt; cited articles open read-only, scoped to the ticket and its tenant; the return date is three Monday-to-Friday days after the answer in the tenant's zone.

Duration: about 40 minutes, finished 2026-11-09 01:14 UTC. Tasks: 3. Files: 11 (6 created, 5 modified).

## Accomplishments

- **Task 1 (035e778d3), draft actions.** `send_draft` reads the ticket, checks in order: waiting draft (else `already_handled`), `projection.blocked` (`ticket_closed`, `person_replied`, `no_requester`), then the edit rules (empty, over 900, unchanged). One compare-and-set on `comments.$` (kind `ai_draft`, `ai.state` draft) turns the comment into a requester-visible `ai_answer` with `ai.state sent`, `sentBy`, `sentAt`, `edited` and the same citations. Then the status moves to `pending_customer`, the ticket's desk fields are set, the suggested row becomes `executed` with `approval.approver` (shadow and refused rows keep their state and get desk fields plus a `servicedesk.sent` audit event) and the requester gets one tagged notice. `discard_draft` mirrors it (row `denied`, no notice, no job). The routes need `view:dashboard`, refuse the reporter 403 `staff_only`, and map every refusal to the `API_DETAIL` text.
- **Task 2 (5da69cdf5), the requester's answer.** `confirm` is the only function that sets `resolved` (with `resolved_at`), `still_need_help` moves `pending_customer` to `open`, stores the optional note as a `requester_reply`, hands off `did_not_help` with `notify_requester=False`, and ends Undo. `on_comment_added` turns the reporter's own comment on an answered ticket into the same effect (no extra comment, no job) and sets `desk.personReplied` plus `undoable False` (ticket and row, with the person-replied Activity sentence for a posted or sent answer) on a staff comment to the requester. `tickets_endpoints.add_comment` calls it inside try/except that only logs.
- **Task 3 (1f893eeeb), articles and the return date.** `workdays.add_working_days` keeps the local clock time in the tenant's zone and skips Saturday and Sunday; `requester_view` computes `returnAt` from `desk.postedAt` on every read (only while the answer waits on the requester). `GET .../articles/{article_id}` serves only ids cited on this ticket for this viewer, read with the ticket's own `tenantId` and `helpdesk: true`. `requester_items` drops withdrawn answers; staff replies show the profile name (R12).

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 035e778d3 | feat | Staff send, edit or discard a waiting draft |
| 2 | 5da69cdf5 | feat | The requester confirms or asks for a person, and a reply ends Undo |
| 3 | 1f893eeeb | feat | Cited articles read-only and the return date in working days |

Plan type `execute` with `tdd="true"` tasks: as in 85-01 to 85-13, tests and implementation were written together and committed together per task (no separate RED commit). Mutation checks were run by hand and restored: removing the reporter refusal failed the reporter test; dropping `ai.state` from the CAS failed the new CAS test; making confirm set `closed` failed 5 tests; letting a staff-only note end Undo failed 3; dropping the tenant filter on the article read failed 2; counting weekend days failed 12 workday tests.

## Verification

- Task 1 command (lifecycle, portal routes, tracer): passed; Task 2 command (plus comments and test_tickets): 148 passed together with structural and copy; Task 3 command (workdays, portal routes): 49 passed. No skips (private mongod on 27998).
- Final run on 27998 of every `test_service_desk_*.py` file plus `test_autonomous_ops_copy.py`, `test_autonomous_ops_structural.py`, `test_tickets.py`, `test_catalogue_route_parity.py` and `test_route_auth_baseline.py`: 764 passed, 0 skipped, 0 failed.
- Acceptance greps: `async def send_draft|discard_draft` 2; `drafts/{comment_id}` in the endpoints file 3; `async def confirm|still_need_help|on_comment_added` 3; `on_comment_added` in tickets_endpoints.py 1; `def add_working_days` 1; `ZoneInfo` in workdays.py 4. Sizes: lifecycle.py 276, projection.py 205, service_desk_endpoints.py 207, the largest test file 485.
- `ruff --select F` is clean on every file this plan touched; it reports 3 unused imports in `test_service_desk_injection.py` and `test_service_desk_ledger.py` (85-13 and 85-03, not touched here).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Four API_DETAIL texts added**
- **Found during:** Task 1 and 3
- **Issue:** The plan reuses `article_content` ("Enter the article text.") and `article_too_long` for an empty or long edited answer, which names an article where the user edits an answer; it has no text for a help note over 1000 characters or an unreadable article.
- **Fix:** `draft_empty`, `draft_too_long` ("The answer is over {max} characters. Shorten it."), `help_too_long` ("Use up to {max} characters.") and `article_not_found` were added to `messages.API_DETAIL` so every refusal still reads from that table. `edit_unchanged` is the UI-SPEC text as planned.
- **Files modified:** backend/service_desk/messages.py (not in the plan's list). **Commit:** 035e778d3.

**2. [Rule 3 - Blocking] The desk test app now patches `get_database` in `service_desk_endpoints`**
- **Found during:** Task 1
- **Issue:** The routes read the database through `database.get_database`; `DeskApp` patched only the three ticket modules, so the existing tracer GET would have reached the live database.
- **Fix:** `service_desk_endpoints` added to the patched module tuple in `tests/service_desk_support.py` (one line). **Commit:** 035e778d3.

**3. [Rule 3 - Blocking] A shared test support module**
- **Issue:** The lifecycle and route test files need the same world (three tenants, a posted answer, a waiting draft, the notice writer wired to the test database).
- **Fix:** `tests/service_desk_portal_support.py` (not in the plan's list) holds it; `service_desk_support.py` was left otherwise unchanged as its docstring asks.

**4. [Order] `workdays.py` begins in Task 1**
- `tenant_zone` is needed by Task 1 for the Activity sentence time ("Sent by Bob at 14:30"), so the file was created with `tenant_zone` in Task 1 and `add_working_days` was added in Task 3 as planned.

**Total deviations:** 4 (2 Rule 2/3 additions, 1 Rule 3 helper, 1 ordering). **Impact:** none on scope or behaviour; no architectural change.

## Authentication Gates

None.

## Known Stubs

None. `requester_view` returns every field of `RequesterView`.

## Threat Flags

None beyond the plan's register. T-85-51 (article browsing) is covered by tests with uncited, global, unknown, cross-tenant and forged-global ids; T-85-52 by the 403 on all three draft routes and the hidden draft; T-85-53 by the comment CAS (a deterministic test plus two concurrent-send tests); T-85-54 by `sentBy`, `approval.approver` and the `executed` / `servicedesk.sent` / `servicedesk.discarded` / `servicedesk.confirmed` events. T-85-55 accepted as planned (the portal panel is a presentation). T-85-SC accepted (no package installed).

## User WIP preserved

`backend/tickets_endpoints.py` still shows the user's `+38/-11` unstaged (`git diff --numstat` after each commit). The Task 2 commit staged a blob built from `HEAD` with only the eight-line `on_comment_added` hook through `git update-index --cacheinfo 100755`; `git diff --cached` showed no attachment, download, `FileResponse` or `_UPLOAD_DIR` line. No other file with user changes was touched.

## Hand-over for later plans

- **85-15 / 85-16 / UI plans:** the GET `requester.items[].kind` is the stored comment kind (`ai_answer`, `requester_reply`, `handoff_notice`, `withdrawn_notice`, or null for a plain staff reply), not the `answer | reply | you | withdrawn | notice` union that `services/serviceDesk/types.ts` declares; the 85-01 tracer test pins `ai_answer`. Map them in the client (or change the server and the tracer test together). The requester block also carries `canSee`. `author` is the profile name, null when there is none (show IT).
- **85-17 (returns sweep):** `projection.return_at` / `workdays.add_working_days` / `workdays.tenant_zone` are the date source; the sweep acts on tickets with `desk.phase` posted or sent, status `pending_customer` and `desk.postedAt`. A person-sent draft sets the same fields.
- **85-18 (Undo):** a sent row has `desk.sentBy` and is not `autoDispatched`; decision 8 (person-sent drafts do not feed the breaker) needs the withdrawal counter to skip rows with `desk.sentBy`. The comment ids are the draft's own (`sd-{actionId}`); the comment is a requester-visible `ai_answer` with `ai.state sent`. `requester_items` and `cited_articles` already treat `ai.state withdrawn` as hidden.
- **85-19 (tray routes):** reuse `projection.cited_articles(ticket, for_requester=True)` for the allow-list.
- A reporter's own plain comment is stored staff-visible by default (85-08), so it does not appear in `requester.items`; the `requester_reply` written by the help button is requester-visible and does.

## Self-Check: PASSED

lifecycle.py, workdays.py, the three test files and the support module exist; commits 035e778d3, 5da69cdf5 and 1f893eeeb are ancestors of HEAD; the three plan commands and the wider run were re-run green (764 passed, 0 skipped).
