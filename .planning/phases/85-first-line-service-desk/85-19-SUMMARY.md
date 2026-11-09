---
phase: 85-first-line-service-desk
plan: 19
subsystem: service-desk
tags: [service-desk, tray, agent-key, projection, my-tickets, contract, copy-gate]
status: complete

requires: [85-02, 85-09, 85-10, 85-14, 85-18]
provides:
  - "backend/service_desk_tray_endpoints.py: the five agent-key tray routes (create, list, confirm, help, article), projection only, included in the agent aggregator"
  - "projection.tray_view, projection.tray_status, projection.tray_display: the enforced requester projection for the tray"
  - "tests/service_desk_tray_support.py: a three-tenant, three-agent world with real signed agent tokens through the production verify_agent_key"
  - "backend/service_desk_tray_endpoints.py on the ACTV-08 copy gate (JSON list and both EXPECTED_FILES lists)"
affects: [85-23]

actuals:
  tokens: 17000
  tasks: 3
  commits: 3
plan_head_before: 6634bea9ba72b05700806c921f2f23d02ca88717
plan_head_after: e1903231fe424a792402542e4a915c030193992c

tech-stack:
  added: []
  patterns:
    - "The requester boundary is an allow-list by comment kind: tray_view reads requester-visible comments of five kinds (answer, requester_reply, handoff_notice, a plain reply from someone else, a withdrawn answer as the notice) and builds every field by name; no stored ticket is ever returned"
    - "Ownership is tenant + agent bound to the token + Windows user compared casefolded; every refusal for a ticket the caller does not own is the same 404"
    - "Route tests sign a real agent JWT per request so the token-to-path binding (403), the registration-key refusal and the capability check are the production code, not an override"

key-files:
  created:
    - backend/service_desk_tray_endpoints.py
    - backend/tests/service_desk_tray_support.py
    - backend/tests/test_service_desk_tray_routes.py
    - backend/tests/test_service_desk_tray_actions.py
    - backend/tests/test_service_desk_tray_server_contract.py
  modified:
    - backend/agent_endpoints.py
    - backend/service_desk/projection.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The AI-assisted line is added by the tray script only: the stored answer text carries no mark and the server never prepends one, so the line shows exactly once (a test simulates the script's guard for a text with and without the mark)"
  - "answerIds lists requester-visible, not withdrawn answers of every listed ticket; a withdrawn answer is an entry of kind withdrawn (its own at/withdrawnAt, the withdrawal notice text, no citations) and the separate withdrawn_notice comment is not projected, so the notice appears once"
  - "The rate limit is agent_limiter (agent id plus socket address), not the per-address limiter: 10 a minute on each write route, 30 a minute on each read route, per agent"
  - "The Windows user is soft scoping (D-34): compared casefolded and stripped in code after a query that already filters tenant, agent_id, raised_via tray and myTickets True; the list scans at most 500 tickets of one computer in 60 days and stops at 20 matches"
  - "tray_view takes only the ticket (the plan's signature had a now argument; nothing in the view is time dependent, the 60-day window is in the route)"
  - "shared/catalogue-gaps.json needed no change: the ratchets count agent-capable (get_current_user_or_agent) routes and these routes use verify_agent_key"

requirements-completed: []

coverage:
  - id: D1
    description: "Create: POST /api/agents/{agent_id}/tray/tickets makes a tray ticket by route identity (reporter the agent, tags user-raised and tray, channel with myTickets from client.features, windowsUser, template), queues it, answers {ticket_id, ticket_number, message}; bad template, title over 200, blank or missing username, bad type and priority are 422 and store nothing; a body field cannot decide who raised it"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_routes.py#test_create_marks_the_ticket_as_a_tray_ticket_by_route_identity; #test_a_tray_without_the_my_tickets_claim_is_marked_so; #test_a_body_field_cannot_decide_who_raised_the_ticket; #test_a_malformed_create_is_refused_and_stores_nothing; #test_the_longest_allowed_title_and_a_missing_template_are_accepted"
        status: pass
    human_judgment: false
  - id: D2
    description: "Agent auth: another agent's token is 403, the registration key 403, no credentials 401, a tenant without ticket_reporter 403, an unknown agent 403/404"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_routes.py#test_create_needs_the_agents_own_token_and_the_capability; #test_an_agent_that_is_not_enrolled_in_the_tenant_gets_404; #test_another_agent_cannot_list_this_computers_tickets"
        status: pass
    human_judgment: false
  - id: D3
    description: "List boundary (PROH-85-05, D-11): the serialized response never contains a draft, a staff-only comment, a staff note, a hand-off reason or a withdrawn answer's text or citations; entries are answer, reply, you, notice in time order; a withdrawn answer is one withdrawn entry and not an answerId"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_routes.py#test_the_list_holds_only_what_a_requester_may_read; #test_a_withdrawn_answer_reads_as_the_withdrawal_notice_and_is_not_an_answer_id; #test_the_answer_buttons_follow_the_desk_phase_and_the_status"
        status: pass
    human_judgment: false
  - id: D4
    description: "List scope (D-06, D-34): only this tenant, this computer (agent bound to the token) and this Windows user (casefolded), only tickets from a tray that can show answers, the last 60 days, at most 20 newest first; another user, another computer, another tenant (also one reusing the same agent id), an old tray's ticket and a 61-day-old ticket are never listed"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_routes.py#test_a_user_sees_only_their_own_tickets_from_this_computer; #test_the_list_is_the_20_newest_tickets_of_the_last_60_days"
        status: pass
    human_judgment: false
  - id: D5
    description: "Pipeline: a new-route ticket with my_tickets at undoable_auto, mode post, shadow off is posted and the tray list carries the answer with its citation and the buttons; the same ticket without the claim, or through the legacy route, stays a draft with no_tray_window"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_routes.py#test_a_new_tray_ticket_is_posted_and_the_tray_reads_the_answer; #test_a_ticket_from_a_tray_without_the_claim_stays_a_draft; backend/tests/test_service_desk_tray_actions.py#test_the_same_ticket_through_the_legacy_route_stays_a_draft"
        status: pass
    human_judgment: false
  - id: D6
    description: "Confirm and help run the portal lifecycle (resolved only by This fixed it; I still need help reopens, stores the note as the requester's reply, hands off did_not_help with no second notice); 404 for another user, computer or tenant and for an old tray's ticket; 409 with no answer waiting; note over 500 characters is 422"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_actions.py (this_fixed_it, no_answer_waiting, only_the_owner_acts, old_trays_ticket, i_still_need_help, the_note_is_optional, user_name_is_required)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Article reads (D-14): only an article cited on the caller's own requester-visible, not withdrawn answer opens; an uncited, drafted, withdrawn or unknown id is 404; a cited global, other-tenant, unmarked or deleted article answers available false with the cited title and no text; another user, computer or tenant gets 404"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_actions.py#test_a_cited_article_is_read_from_the_callers_own_answer; #test_only_an_article_cited_on_this_ticket_opens; #test_a_citation_never_opens_a_global_foreign_or_unmarked_article; #test_only_the_owner_reads_an_article"
        status: pass
    human_judgment: false
  - id: D8
    description: "Contract: router paths and methods (also through the agent aggregator) equal tray_contract; every field the script reads is served (a missing one is named); every field and every template (id, type, priority) the script sends is accepted; the AI-assisted line shows once; rate limits 10 writes and 30 reads a minute per agent; the route file is on the ACTV-08 copy gate; catalogue parity and route-auth ratchets pass"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_tray_server_contract.py (9 tests); backend/tests/test_service_desk_tray_routes.py#test_writes_are_limited_to_10_a_minute_and_reads_to_30_per_agent; backend/tests/test_autonomous_ops_copy.py; src/__tests__/autonomousOpsCopy.test.ts; backend/tests/test_catalogue_route_parity.py; backend/tests/test_route_auth_baseline.py"
        status: pass
    human_judgment: false
  - id: D9
    description: "A real Windows tray raising a ticket, receiving the pop-up, reading the window and pressing the two buttons against these routes"
    requirement: "DESK-01"
    verification: []
    human_judgment: true
    rationale: "No PowerShell exists on this VM and the agent carrying the window is unpublished; the server side is proven against the script as text, the live round trip is the user's step after the agent release"
---

# Phase 85 Plan 19: The tray routes of the service desk Summary

The tray window now has a tested server: five agent-key routes create a ticket the desk may post to, list only this Windows user's tickets from this computer as an explicit requester projection, run This fixed it and I still need help through the portal lifecycle, and serve only the articles cited on the caller's own visible answer, all pinned to the frozen tray contract and the tray script.

Duration: about 22 minutes (started 2026-11-09 05:12 UTC, finished 05:35 UTC). Tasks: 3. Files: 10 (5 created, 5 modified).

## Accomplishments

- **Task 1 (aff41298f), create and list.** `service_desk_tray_endpoints.py` holds the five routes under `/api/agents/{agent_id}/tray/tickets` (the plan put the routes of Tasks 1 and 2 in one module, so this commit carries all five). Create validates the body (title 1 to 200, type and priority from the existing values, template in `TEMPLATE_IDS`, `endpoint_info.username` required, client features and version), keeps only four `endpoint_info` keys, stores the ticket through `tickets_service.create_ticket` with `raised_via` tray, reporter the agent id, tags `user-raised` and `tray`, and a channel `{tray True, myTickets (my_tickets in client.features), windowsUser, template}`, calls `intake.on_ticket_created`, and answers `{ticket_id, ticket_number, message}` with the TRAY_CREATED text. List reads at most 500 tickets of this tenant, agent, tray and myTickets True from the last 60 days newest first, keeps the matches for the Windows user (casefold) up to 20, and returns `{tickets, user, display}`. `projection.tray_view` builds each ticket field by field from requester-visible comments by an allow-list of kinds; `tray_status` picks the status words; `tray_display` gives the footnote (says what is shown, never claims privacy), the footer and the empty text.
- **Task 2 (2ade19647), confirm, help and article.** All three route through one ownership check (`tenant`, `agent_id` of the token, `raised_via` tray, `myTickets` True, Windows user casefold-equal; anything else is the same 404). Confirm and help call `lifecycle.confirm` and `lifecycle.still_need_help` with requester `tray:<agent id>`; the note is capped at 500 characters at the body. The article route uses `projection.cited_articles(ticket, for_requester=True)` and reads the article from `knowledge_docs` with the ticket's tenant and `helpdesk` True, so a global, another tenant's, an unmarked or a deleted article answers `available` false with the cited title and no text.
- **Task 3 (e1903231f), contract, copy gate, ratchets.** Router paths and methods equal `tray_contract` (also through the aggregator, read from the OpenAPI document because this FastAPI wraps included routers). A text parse of the tray script finds every `$tk.`, `$en.`, `$ci.`, `$dp.`, `$ar.`, `$lr.` and create-response read and fails naming each one the server does not produce (a negative control proves the check can fail). The script's create body, client, endpoint info and confirm and help payloads are subsets of the request models, and all six templates (id, type, priority) are accepted by the live create route. `backend/service_desk_tray_endpoints.py` is on the ACTV-08 copy gate in the JSON list and both expected lists.

## Decisions on the hand-overs from 85-10 and 85-14

- **AI-assisted line:** the server never sends it. Stored answers carry no mark; the heading says "Answer from IT support (AI-assisted)" and the script adds the mark line once unless the text already starts with it. A test asserts the server text does not start with the mark, the script has the guard, and the rule shows the mark once for either kind of text.
- **Create response:** carries `message` and `ticket_number` (and `ticket_id`).
- **answerIds:** requester-visible, not withdrawn answers only; tested with a withdrawn answer present.
- **Pop-up:** no pop-up fields were added; the frozen list response has none.
- **Cited articles:** `projection.cited_articles(..., for_requester=True)` reused; only the tenant's Help desk set.
- **Scope:** agent (bound to the token) and Windows user, plus tenant. The Windows user name is client-reported: a local user who can read `tray-config.json` could ask for another user's list. This is D-34 soft privacy, stated in the footnote (it says what is shown, not that it is private) and for the UAT; it is not claimed anywhere as a security boundary.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | aff41298f | feat | The tray raises tickets the desk may answer and lists only what its user may read (all five routes, the projection, the mount) |
| 2 | 2ade19647 | test | A tray user confirms, asks for a person and reads cited articles of their own tickets only |
| 3 | e1903231f | test | The tray routes and the tray script are tested against the same frozen contract, plus the copy gate entry |

Plan type `execute` with `tdd="true"` tasks: as in 85-01 to 85-18, tests and implementation were written together; the implementation of the five routes went in with Task 1's commit because they share one module, so Tasks 2 and 3 are test and configuration commits and there is no separate RED commit. No formal RED evidence was captured; the mutation checks below stand in for it.

## Mutation checks (by hand, each restored and compared byte for byte with the saved original)

- Agent scope removed from the list filter: `test_a_user_sees_only_their_own_tickets_from_this_computer` failed (and, in the actions file, three ownership tests failed).
- Windows-user compare replaced by True: the same list test failed; with it removed from the ownership check, `test_only_the_owner_acts_on_a_ticket` (both actions) and `test_only_the_owner_reads_an_article` failed.
- Withdrawn filter made to say never: `test_a_withdrawn_answer_reads_as_the_withdrawal_notice_and_is_not_an_answer_id` failed.
- Tenant filter removed: first it passed because a different agent id already isolated the other tenant; a ticket of another tenant that reuses the same agent id was added to the list test, after which the mutation failed it.
- Article allow-list bypassed, tenant filter dropped from the article read, Help desk mark dropped from the article read, `myTickets` dropped from the scope: each failed at least one test.
- Contract: a projection field renamed (`statusText`), a route path renamed and the mark prepended to the answer text each failed the contract tests, the first one naming the field.

## Verification

- Task 1 command (tray routes, intake): 57 passed. Task 2 command (tray routes, tray actions, pipeline): 76 passed. Task 3 command (tray routes, actions, server contract, copy gate, catalogue parity, agents slices, route-auth baseline): 159 passed; vitest `autonomousOpsCopy.test.ts`: 23 passed. No skips (private mongod 27998).
- Final run: every `test_service_desk_*.py` (including `test_service_desk_tray_contract.py`, `test_service_desk_tray_static.py` and `test_service_desk_structural.py`, which scans the new route file), `test_autonomous_ops_copy.py`, `test_autonomous_ops_structural.py`, `test_catalogue_route_parity.py`, `test_route_auth_baseline.py`, `test_catalogue_slice_agents.py`, `test_catalogue_slice_agents_dataplane.py` and `test_tickets.py`: 911 passed, 0 skipped, 0 failed.
- Acceptance greps: `verify_agent_key` in the route file 7; `service_desk_tray_endpoints` in `agent_endpoints.py` 1; `/tray/tickets/{ticket_id}` in the route file 3; `service_desk_tray_endpoints.py` in the banned-terms JSON 1. The leak test asserts the serialized list response contains neither the draft text, the staff note text nor the hand-off reason.
- `ruff --select F` is clean on every file this plan touched. Sizes: route file 253 lines, `projection.py` 294, the four test files 307, 212, 177 and 132.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The conftest turns every capability on**
- **Found during:** Task 1 (the capability refusal test got 200)
- **Issue:** `tests/conftest.py` patches `agent_capabilities.allowed` to allow everything unless a test carries the `real_agent_capabilities` marker.
- **Fix:** the one test that proves a tenant without `ticket_reporter` is refused carries the marker.
- **Commit:** aff41298f

**2. [Rule 3 - Blocking] A shared test support module and two extra test files**
- **Issue:** the plan names one test file; the route, action and contract tests together exceed the 500-line limit and share one world (three tenants, three agents, signed tokens).
- **Fix:** `tests/service_desk_tray_support.py` holds the world; `test_service_desk_tray_actions.py` and `test_service_desk_tray_server_contract.py` are new files (not in the plan's file list). Task 2's verify command should include the actions file.
- **Commits:** aff41298f, 2ade19647, e1903231f

**3. [Plan conflict] `tray_view(ticket, now)` has no `now`**
- Nothing in the projection depends on the time; the 60-day window is applied in the route. The function is `tray_view(ticket)`.

**4. [Rule 2 - Critical] Rate limit is per agent**
- The plan says "per agent"; the existing agent routes use the per-address `limiter`. These routes use `agent_limiter` (keyed by agent id and socket address) so several computers behind one address do not share a bucket. A test shows one agent's limit does not limit another.

**5. [Plan note] `shared/catalogue-gaps.json` was not edited**
- The ratchets count agent-capable routes (`get_current_user_or_agent`); the five routes use `verify_agent_key`, so the parity, route-auth and agents-slice tests passed without a counter change. The user's uncommitted +4/-34 in that file is untouched and unstaged.

**Total deviations:** 5 (2 blocking test helpers, 1 signature, 1 limiter choice, 1 file not needed). **Impact:** none on scope or behaviour.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-85-71 (staff-only content to the tray) is covered by the leak test and the kind allow-list; T-85-72 (another computer's tickets) by the agent binding and tenant and agent filters with the mutation checks above; T-85-73 (another Windows user on one PC) is accepted as planned (D-34) and stated in the footnote and here; T-85-74 (article browsing) by the allow-list and the tenant Help desk read; T-85-75 (polling) by the two rate limits, the 20-ticket and 60-day list and the 500-ticket scan cap. T-85-SC accepted (no package installed).

## User WIP preserved

`shared/catalogue-gaps.json` still shows the user's `+4/-34` unstaged (`git diff --numstat` after the last commit) and was not touched or staged; `backend/tickets_endpoints.py` still shows `+38/-11`. `backend/catalogue_mounts_agents.py` was not edited. Every commit staged explicit paths only; no stash, restore or checkout of a working file was used (the mutation checks restored files from saved copies and compared them).

## User steps

None done on the user's behalf: no restart (the five routes go live on the user's next backend restart), no UI publish, no push, no agent build. After the agent that carries the window is released, the Windows round trip of 85-10's list applies against these routes; one more check for the UAT: a second Windows user on the same computer sees an empty My tickets (soft scoping, not privacy).

## Notes for later plans

- **85-23 (validation map).** The server side of the tray window is proven against the frozen contract and the script text; the real Windows round trip, the pop-up and the display scaling remain the user's steps. `client.version` is empty until the tray config writes `agent_version` (85-10 hand-over, unchanged).
- The tray ticket tags are `user-raised` and `tray` only; the legacy route also appends `agent-raised`. Nothing reads that tag for display (checked), but a staff filter on `agent-raised` would not show new-tray tickets.
- The list reads at most 500 tickets per call (one computer, 60 days) before applying the Windows-user match; a computer with a very large number of other users' tickets could in theory push a user's older tickets out of the scan.

## Self-Check: PASSED

Files present: service_desk_tray_endpoints.py, projection.py, the three tray test files, service_desk_tray_support.py. Commits aff41298f, 2ade19647 and e1903231f are ancestors of HEAD. The plan commands and the wider run were re-run green (911 passed, 0 skipped); `shared/catalogue-gaps.json` +4/-34 and `backend/tickets_endpoints.py` +38/-11 remain unstaged.
