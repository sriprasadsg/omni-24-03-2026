---
phase: 85-first-line-service-desk
plan: 18
subsystem: service-desk
tags: [service-desk, undo, withdraw, breaker, approvals, activity]
status: complete

requires: [85-04, 85-11, 85-12, 85-14]
provides:
  - "service_desk/withdraw.py: undo_answer (registered with approvals.register_undo_handler at import) and evaluate_breaker"
  - "autonomous_ops_service_desk_endpoints imports service_desk.withdraw at module load, so the required router registers the handler in every running app"
  - "ticket fields desk.withdrawnAt, desk.withdrawnBy (also on the row); comment ai.state withdrawn with ai.withdrawnBy/withdrawnAt; comment kind withdrawn_notice id sd-withdrawn-{rowId}"
  - "setting serviceDesk.breaker {trippedAt, actionIds}; control event service_desk_breaker_tripped; in-app notice (metadata.audience tenant_admins)"
  - "constants DESK_BREAKER_WINDOW (24 h); messages WITHDRAWN_NOTICE_TITLE, BREAKER_NOTICE_TITLE, BREAKER_NOTICE, CONTROL_REASONS service_desk_breaker_tripped; Activity label for the control event"
affects: [85-19, 85-20, 85-21, 85-22]

actuals:
  tokens: 21000
  tasks: 2
  commits: 2
plan_head_before: 324a3d4e352fce4ead550095ebe0b5864f0c1341
plan_head_after: ae88625b2e6a2a349dda1f39072cce2639e60b8a

tech-stack:
  added: []
  patterns:
    - "Row transition first (one winner), then one compare-and-set on the ticket that hides the answer only while the ticket still shows it posted/sent and undoable; if that fails the row is put back, so a row never says undone while the requester can read the answer"
    - "Every step after the hide is wrapped on its own: the ticket must reach a person even if a notice fails"
    - "Desk breaker is one compare-and-set on serviceDesk.mode post with no breaker; the Phase 81 breaker module is never called"

key-files:
  created:
    - backend/service_desk/withdraw.py
    - backend/tests/test_service_desk_withdraw.py
  modified:
    - backend/autonomous_ops_service_desk_endpoints.py
    - backend/service_desk/__init__.py
    - backend/service_desk/messages.py
    - backend/autonomous_ops/messages.py
    - backend/tests/test_service_desk_gate.py

key-decisions:
  - "The ticket-side compare-and-set (desk.undoable true, desk.phase posted or sent, comment ai.state posted or sent) is the last word: a stale Activity row cannot withdraw an answer the requester confirmed or a person already answered"
  - "Decision 8 is enforced twice: the count requires autoDispatched true AND desk.sentBy absent, so a person-sent draft never counts even if its row were flagged automatic"
  - "The withdrawal notice to the requester has its own generic title (Your ticket {number} has an update) instead of reusing the answer notice"

requirements-completed: []

coverage:
  - id: D1
    description: "Undo on a posted desk answer through the real route: hides the answer (staff keep the original), requester reads only the withdrawn notice and no citations, ticket back to open and handed to a person (answer_withdrawn, no handoff_notice), row undone naming the person with the Withdrawn-by sentence, audit event, one recipient-tagged requester notice; a person-sent draft can be withdrawn too"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_withdraw.py#test_a_person_withdraws_a_posted_answer_and_the_requester_is_told; #test_a_draft_a_person_sent_can_be_withdrawn"
        status: pass
    human_judgment: false
  - id: D2
    description: "Undo works during a tenant stop and a platform stop; refused 409 after confirm, I still need help, a person reply, for a shadow row, for a never-sent draft and on a stale row; a second or simultaneous click is one withdrawal; analyst, API key and another tenant are refused; a failed hide puts the row back"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_withdraw.py (stop, second click, two clicks, refusals, stale row, shadow and draft, permissions, tenant, failed hide)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Desk breaker: the second withdrawal does not trip, the third sets serviceDesk.mode drafts with {trippedAt, actionIds}, writes one control row and one tenant-admin notice, deskBreakerTripped true, tenant level, Phase 81 breaker and on-call untouched; 25-hour-old withdrawals, person-sent drafts and I still need help never count; already-Drafts trips nothing; concurrent evaluations trip once; other tenants' rows, non-desk rows and the platform tenant are ignored; Restore (needs manage) lets the next answer post"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_withdraw.py (Task 2 tests, 9 cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "How the withdrawn state reads on the Activity screen and the portal panel (the 85-16 UI toast pair, the notice wording in context)"
    requirement: "DESK-01"
    verification: []
    human_judgment: true
    rationale: "The backend fields and sentences are proven; how they look in the UI is judged at phase UAT"
---

# Phase 85 Plan 18: Withdraw a posted answer and the desk-only breaker Summary

A person can take back a posted (or person-sent) answer from Activity: it is hidden from the requester, who reads that a person will follow up, the ticket goes to a person, and three automatically posted answers withdrawn within 24 hours drop only the service desk to Drafts only, leaving the tenant's Autonomous Ops level alone.

Duration: about 2.5 hours elapsed including a session pause (started 2026-11-09 02:44 UTC, finished 05:11 UTC). Tasks: 2. Files: 7 (2 created, 5 modified).

## Accomplishments

- **Task 1 (67541ebfc), withdraw.** `withdraw.undo_answer` is registered with `approvals.register_undo_handler("service_desk", ...)` at import, and `autonomous_ops_service_desk_endpoints` imports the module (the router is in `router_registry`'s required list), so the 85-04 route stops answering 409 `not_undoable` for a posted answer. It refuses `not_undoable` unless the row is a desk `ticket_answer` that is executed or verified, not shadow, `desk.undoable` true and `desk.phase` posted or sent (the platform tenant never), and `already_handled` for a row already undone. It moves the row `executed` to `undone` with the undo block and the person, then runs one compare-and-set on the ticket that turns the comment `withdrawn` and ends Undo only while the ticket still shows the answer as posted or sent and undoable; if that loses (the requester confirmed or a person replied in between) or throws, the row is put back. Then: the requester-visible `withdrawn_notice` comment, `pending_customer` to `open`, the Activity sentence (`Withdrawn by Bob at 14:30. The ticket went to a person.`), `handoff(..., "answer_withdrawn", notify_requester=False)`, `desk.phase` withdrawn again (handoff sets handed_off), and one recipient-tagged requester notice through `notify.requester_notice`. Works under a tenant or platform stop. `projection.requester_items` and `cited_articles` (85-14) already hide a withdrawn answer from the requester and keep it for staff; no change was needed there.
- **Task 2 (ae88625b2), the desk breaker.** `evaluate_breaker` reads the newest 3 rows of the tenant with kind servicedesk, state undone, `autoDispatched` true, no `desk.sentBy` and `undo.undoneAt` within `DESK_BREAKER_WINDOW`; at 3 it does one compare-and-set on `autonomy_settings` `{serviceDesk.mode: post, serviceDesk.breaker: null}` setting mode drafts and `serviceDesk.breaker {trippedAt, actionIds}`. Only the winner writes the control row `service_desk_breaker_tripped` (`ledger.record_control`, mirrored to audit) and one `send_alert` with `channels=[]` and `metadata.audience tenant_admins`. It never calls `autonomous_ops.breaker`, `notify.notify` or the on-call outbox. `undo_answer` returns `desk_breaker_tripped`, which the existing route already puts in the body as `deskBreakerTripped`.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 67541ebfc | feat | A person can withdraw a posted answer and the requester is told a person will follow up |
| 2 | ae88625b2 | feat | Three withdrawn automatic answers in 24 hours drop only the service desk to Drafts only |

Plan type `execute` with `tdd="true"` tasks: as in 85-01 to 85-17, tests and implementation were written together and committed together per task (no separate RED commit). The first test run failed on the missing module (`ImportError`), not a behaviour assertion, so no formal RED evidence was captured; mutation checks stand in for it (below).

## Mutation checks (by hand, restored before the commit)

- Threshold 3 to 2 (`DESK_BREAKER_THRESHOLD`): `test_the_third_withdrawal_drops_...` failed (the second withdrawal tripped it).
- sentBy exclusion removed from the count: `test_a_draft_a_person_sent_never_counts[True]` failed.
- Tenant-level isolation (the trip also set `level: suggest`): the third-withdrawal test and the restore test failed.
- Ticket-side compare-and-set filter dropped (`desk.undoable` and `desk.phase`): the person-replied case and the stale-row test failed.
- `cmp` against the saved originals confirmed every file was restored.

## Verification

- Task 1 command (withdraw, gate, approvals): 93 passed. Task 2 command (withdraw, settings, breaker): 102 passed. No skips (private mongod 27998).
- Final run: `test_autonomous_ops_copy.py`, `test_autonomous_ops_structural.py`, `test_autonomous_ops_approvals.py`, `test_autonomous_ops_breaker.py` (the Phase 81 breaker tests), every `test_service_desk_*.py`, plus `test_tickets.py`, `test_route_auth_baseline.py`, `test_catalogue_route_parity.py` and `test_router_registry_required.py`: 923 passed, 0 skipped, 0 failed. The ACTV-08 copy gate scans the new `withdraw.py` and it is clean.
- Acceptance greps: `register_undo_handler` in withdraw.py 1; `service_desk import withdraw` in the endpoints file 1; `def evaluate_breaker` 1; `service_desk_breaker_tripped` 1 (held in one constant). The stop test asserts 200 with a tenant stop (and a platform stop); the breaker test compares the tenant's `level`, `maxLevel`, `shadow`, `stop` and `breaker` before and after the third withdrawal, and `breaker.evaluate` stays false.
- Sizes: withdraw.py 203 lines, the test file 463. `ruff --select F` clean on both.

## Existing tests whose expectation changed

- `test_service_desk_gate.py::test_undo_with_no_desk_handler_refuses_and_writes_nothing` asserted `"service_desk" not in approvals._UNDO_HANDLERS`, which is false in any process that imports `service_desk.withdraw` (the router, or this plan's tests). It now removes the handler with `monkeypatch.delitem(..., raising=False)` for its own run and still proves the fail-closed path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] A failed or lost hide puts the row back**
- **Found during:** Task 1
- **Issue:** The plan orders the row transition before the comment compare-and-set. If the ticket write fails or loses (requester confirmed in between), the row would say undone while the requester can still read the answer, and a retry would answer already_handled forever.
- **Fix:** The ticket write also checks `desk.undoable` and `desk.phase` and ends Undo in the same update; on failure or a lost race the row transition is reversed (`_put_row_back`) and the click answers 503 or 409. Tested with a forced failure and a stale row.
- **Commit:** 67541ebfc

**2. [Rule 2 - Missing critical functionality] Activity label and wording for the control event; own requester notice title**
- **Found during:** Task 1 and 2
- **Issue:** `autonomous_ops/messages.CONTROL_LABELS` had no `service_desk_breaker_tripped`, so the trip row would read "Control event"; reusing the answer notice title would tell the requester "Your ticket has an answer" about a withdrawal; the plan's "breaker text from messages" did not exist.
- **Fix:** Added the label, `CONTROL_REASONS["service_desk_breaker_tripped"]`, `WITHDRAWN_NOTICE_TITLE`, `BREAKER_NOTICE_TITLE` and `BREAKER_NOTICE` (and `DESK_BREAKER_WINDOW` in `service_desk/__init__.py`). These files are not in the plan's list.
- **Commit:** 67541ebfc, ae88625b2

**3. [Rule 1 - Test fit] The 85-04 fail-closed test** (see above): one hunk, no behaviour change to approvals.

**4. [Shape] Control row actor** uses the ledger's `{username, display, tier}` shape (`Service desk`, tier system) instead of the plan's `{id, name}`, so the audit mirror names it.

**Total deviations:** 4 (2 Rule 2 additions, 1 test fit, 1 shape). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-85-68 (desk-only breaker, level untouched, restore needs manage: analyst 403, tenant admin 200), T-85-69 (requester projection shows the notice only, staff keep the original, tested), T-85-70 (ledger transition with the person, control row, audit mirror; one winner under concurrent clicks and concurrent trips, tested), T-85-SC accepted (no package installed). No new endpoint or collection.

## Hand-over for later plans

- The 85-16 UI already reads `deskBreakerTripped` for the breaker toast; the route body now carries it.
- The desk breaker's stored `serviceDesk.breaker` is what `settings.restore`, the settings card and `desk_breaker` draft reason (85-11, 85-02) already read; nothing else needs wiring.
- The control row has `actor.display` "Service desk" and scope tenant; the Activity list shows it with the label "Service desk dropped to Drafts only".

## User steps

None done and none needed for this plan's tests. The backend runs from the checkout, so the Undo handler and the breaker go live with the next backend restart (the user's step). No push, publish, install or agent build was done.

## User WIP preserved

None of this plan's files carried user changes. `git status` shows no staged files after each commit; the user's uncommitted files were not touched or staged.

## Self-Check: PASSED

withdraw.py and test_service_desk_withdraw.py exist; commits 67541ebfc and ae88625b2 are ancestors of HEAD (2 commits measured from plan_head_before); both task commands and the wider 923-test run were re-run green.
