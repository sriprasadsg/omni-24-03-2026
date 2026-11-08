---
phase: 85-first-line-service-desk
plan: 04
subsystem: autonomous-ops-gate
tags: [gate, service-desk, rate-limit, approvals, undo, reconciler, activity]
status: complete

requires: [85-01, 85-03]
provides:
  - "desk_gate.DESK_RATE_LIMIT (20) and desk_gate.rate_step: the desk's own hourly pool; the 21st automatic answer is suggested with reason desk_rate_limit, never an approval card, never a page"
  - "decision_row._NO_EXPIRY_DISPATCHERS: a service_desk draft row carries approval.expiresAt None and is never expired by approvals.expire_due"
  - "approvals.register_undo_handler and _UNDO_HANDLERS: the undo of a dispatcher is plugged in by name; the desk with no handler is refused not_undoable"
  - "approvals.approve and approvals.deny refuse a service_desk row with reason desk_draft (409 text API_DETAIL desk_draft)"
  - "dispatch_check.bind refuses every ticket command (target_kind ticket) with unregistered_action; the reconciler skips service_desk rows"
  - "Undo route body field deskBreakerTripped"
  - "autonomous_ops/desk_views.py row_extras; Activity fields ticketId and ticketNumber on every row (None for non-desk rows)"
affects: [85-13, 85-16, 85-18]

actuals:
  tokens: 10400
  tasks: 3
  commits: 3
plan_head_before: 383f6a4ea6e7d835c20cd05afe0f0c3833e7521a
plan_head_after: 04617de159455ce962edc9712e58b301c5ae850d

tech-stack:
  added: []
  patterns:
    - "Add-alongside: gate.py gained one delegation line (blast radius) and one reason code; every desk rule lives in desk_gate.py and desk_views.py"
    - "Undo handler registry beside the dispatcher registry; a handler wins over the instruction undo, and the desk fails closed without one"
    - "Fence by dispatcher at every place that could touch an agent or a clock: bind, reconciler, approve, deny, expiry"

key-files:
  created:
    - backend/autonomous_ops/desk_views.py
    - backend/tests/test_service_desk_gate.py
  modified:
    - backend/autonomous_ops/gate.py
    - backend/autonomous_ops/desk_gate.py
    - backend/autonomous_ops/decision_row.py
    - backend/autonomous_ops/approvals.py
    - backend/autonomous_ops/dispatch_check.py
    - backend/autonomous_ops/reconciler.py
    - backend/autonomous_ops/response_views.py
    - backend/autonomous_ops_endpoints.py
    - backend/tests/test_autonomous_ops_response_rows.py

key-decisions:
  - "Desk rows are refused in approve and deny before the stop check, so a desk draft always answers desk_draft (never stopped or no_dispatcher)"
  - "A desk row's Undo is shown only for an executed, non-simulated row with desk.undoable True and desk.phase posted or sent, to a viewer who may act; the handler itself is 85-18's"
  - "row_extras returns only the keys that differ from the generic row plus the two ticket fields; response_views merges it over EMPTY_EXTRAS"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "D-03 outcome matrix through gate.decide for a desk request: only Undoable-auto, shadow off, no stop, no force_suggest and under 20 an hour posts; Suggest, force_suggest, shadow, stops, Off and an unticked tenant, another tenant's ticket, no ticket and an agent target each give the stated outcome"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_gate.py (matrix cases, 12 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The desk's hourly pool: the 21st answer is a draft with desk_rate_limit, no notification, no on-call document and no rate-limit marker; 20 desk rows leave a security request allowed and 20 security rows leave the desk allowed; an unreadable count drafts"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_gate.py#test_the_21st_answer_in_an_hour_is_a_draft_and_nobody_is_told; #test_twenty_desk_rows_leave_the_security_limit_untouched; #test_an_unreadable_pool_count_drafts_instead"
        status: pass
    human_judgment: false
  - id: D3
    description: "A draft never expires as an approval (expiresAt None, still suggested 25 hours later); any other suggestion keeps its 24 hour expiry"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_gate.py#test_a_draft_has_no_expiry_and_expire_due_leaves_it; #test_another_dispatchers_suggestion_still_expires"
        status: pass
    human_judgment: false
  - id: D4
    description: "Approve and deny refuse a desk row, undo calls the registered handler and with none refuses not_undoable writing nothing, no ticket command can be bound to an agent dispatch, the reconciler leaves a dispatching desk row alone, and the undo route body carries deskBreakerTripped"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_gate.py (approve/deny, undo handler, bind invariant, reconciler, undo and approve route tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Activity rows for desk decisions carry ticketId and ticketNumber, the draft label, the stored result and Undo only for a posted or sent answer that can still be withdrawn"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_gate.py (Task 3 view cases); backend/tests/test_autonomous_ops_response_rows.py"
        status: pass
    human_judgment: true
    rationale: "The rows are proven at the view-function level; how they read on the Activity screen (copy, Undo button, link to the ticket) is judged when the UI plan for them lands"
---

# Phase 85 Plan 04: The gate's side of the desk Summary

The gate now gives a service desk request exactly the D-03 outcomes, gives the desk its own 20-an-hour pool whose 21st answer becomes a draft without paging anyone, keeps drafts alive until a person acts on the ticket, closes approve and deny to desk rows, delegates undo to a registered handler (failing closed with none), fences desk rows off from agent queues and the reconciler, and shows desk decisions in Activity with their ticket.

Duration: about 25 min. Tasks: 3. Files: 11 (2 created, 9 modified). Completed 2026-11-08.

## Accomplishments

- **Pool and drafts (Task 1, 7af1b7fa7).** `desk_gate.rate_step` counts `ledger.count_auto_since(pool="servicedesk")` over the rolling hour; at 20 it escalates to suggest with `desk_rate_limit` (an unreadable count does the same). `gate._step_blast_radius` starts with one delegation line for the desk dispatcher, so it never reaches `_notice_rate_limit`, `notify` or the on-call notice (PROH-85-07), and `desk_rate_limit` joined `REASON_CODES`. `decision_row._NO_EXPIRY_DISPATCHERS` gives desk rows `approval.expiresAt` None; `expire_due` filters on `$lte`, so None never matches.
- **Closed doors (Task 2, ec968f482).** `approve` and `deny` return `{"status": "refused", "reason": "desk_draft"}` for a service_desk row (the route turns it into the 409 `API_DETAIL["desk_draft"]` text). `approvals.register_undo_handler` plus a lookup at the top of `undo`; the desk without a handler returns `not_undoable` and writes nothing. `dispatch_check.bind` returns `unregistered_action` for any spec with `target_kind == "ticket"`, whatever the row says, so `gate.execute` can never queue a ticket command. The reconciler skips service_desk rows (otherwise an old `dispatching` desk row with no instruction would have been failed `not_delivered`). The undo route body gains `deskBreakerTripped`.
- **Activity (Task 3, 04617de15).** `desk_views.row_extras` (pure) returns `ticketId`, `ticketNumber`, the draft label for a suggested row or a simulated drafted row, the stored `activityResult` as `resultText`, and Undo with `DESK_UNDO_HINT` only for a person who may act on an executed, non-simulated row with `desk.undoable` True and `desk.phase` posted or sent. `response_views.row_extras` hands service_desk rows to it before any security or rollout logic; `EMPTY_EXTRAS` gains `ticketId` and `ticketNumber` (None for every non-desk row).

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 7af1b7fa7 | feat | The desk's own hourly pool turns the 21st answer into a draft, and drafts never expire |
| 2 | ec968f482 | feat | Desk rows cannot be approved or denied, undo is delegated, no ticket command reaches an agent |
| 3 | 04617de15 | feat | Activity rows for desk decisions link to the ticket and offer Undo only for a posted answer |

Each task is one commit (tests and implementation together), as in 85-02 and 85-03.

## Verification

- Task 1 command (gate_desk, gate, gate_order, approvals): 99 passed, no skips.
- Task 2 command (gate_desk, approvals, dispatch_binding, reconciler, endpoints_writes, structural): 190 passed, no skips.
- Task 3 command (gate_desk, response_rows, endpoints, patch_rollout_activity) and 8 more Activity-adjacent files (block_contract, confirm_isolation, incident_route, range_block, sweep_dedupe, two_signal, structural, copy): 332 passed.
- Final combined run (gate_desk, gate, gate_order, approvals, dispatch_binding, reconciler, endpoints_writes, stop, ledger, service_desk_ledger, service_desk_tracer): 324 passed.
- test_service_desk_gate.py: 48 tests. All used the private mongod on 27998; nothing touched the live database.
- Acceptance greps: `def rate_step` 1, `rate_step` in gate.py 1, `_NO_EXPIRY_DISPATCHERS` 2, `def register_undo_handler` 1, `desk_draft` in approvals.py 2, `target_kind` in dispatch_check.py 1, `deskBreakerTripped` 1, `desk_views` in response_views.py 2, `ticketNumber` in response_views.py 1. Sizes: gate.py 465, approvals.py 300, response_views.py 286, desk_views.py 45, the test file 444 lines.

## Existing tests whose expectation changed

- `test_autonomous_ops_response_rows.py`: the pinned key set `KEYS` of `row_extras` gains `ticketId` and `ticketNumber` (the plan adds them to `EMPTY_EXTRAS`). No Phase 81, 83 or 84 approvals, dispatch-binding, reconciler, endpoint, gate or rollout test changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test fit] Pinned Activity key set**
- **Found during:** Task 3
- **Issue:** `test_a_row_with_no_inputs_keeps_its_stored_wording` asserted `set(out) == KEYS` of five keys; the plan's `EMPTY_EXTRAS` change makes seven.
- **Fix:** Added the two ticket keys to `KEYS` with a comment naming this plan.
- **Files modified:** backend/tests/test_autonomous_ops_response_rows.py
- **Commit:** 04617de15

**2. [Rule 2 - Fail closed] Desk refusal ordered before the stop and dispatcher checks in approve**
- **Found during:** Task 2
- **Issue:** The plan says only that approve refuses desk rows. Without a dedicated early check, a desk row would answer `stopped` during a stop or `no_dispatcher` (service_desk has no registered dispatcher).
- **Fix:** The desk check runs right after the not-found check, so the answer is always `desk_draft`.
- **Commit:** ec968f482

**Total deviations:** 2 (1 test fit, 1 ordering). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-85-12 (approve and deny refuse desk drafts, tested), T-85-13 (bind refuses every ticket command for every dispatcher, tested, plus gate.execute writes no agent instruction), T-85-14 (the desk pool escalates to suggest; no notification, no on-call document, no rate-limit marker, tested), T-85-15 (undo with no handler refused and writes nothing, tested), T-85-SC accepted (no package installed). No new endpoint or collection was added.

## Left for later plans

- **85-18** registers the desk's undo handler with `approvals.register_undo_handler("service_desk", ...)`; until then every desk undo returns `not_undoable` (the Undo button already follows `desk.undoable` and `desk.phase`, so it will show for a posted answer but the click is refused with the 409 "not undoable" text until the handler exists). It also owns the desk breaker that sets `desk_breaker_tripped` in the handler result.
- **85-16 / UI plans:** the Activity screen does not yet render `ticketId` or `ticketNumber` (the backend fields exist on every row); the draft and hand-off wording is in place, the link and its styling are UI work. Desk rows in state `verified` get no Undo (the desk never sets that state).
- A `shadow` desk row that is a simulated post (not a draft) keeps the generic simulation result line; only drafted shadow rows get the draft label.

## User steps

None done and none needed for this plan's tests. The backend runs from the checkout, so these gate changes go live with the next backend restart (the user's step, later). No push, publish, install or agent build was done.

## Notes

- The user's uncommitted work (`backend/tickets_endpoints.py`, `components/InternalTicketsDashboard.tsx`, `shared/catalogue-gaps.json`, the Rust `Cargo.toml` and `Cargo.lock`, `App.tsx`, `backend/requirements.txt`) was not touched and is still unstaged. None of this plan's files carried user changes before it started.

## Self-Check: PASSED

Created files desk_views.py and test_service_desk_gate.py exist; commits 7af1b7fa7, ec968f482 and 04617de15 are ancestors of HEAD (3 commits measured from plan_head_before); every task's acceptance greps and the plan-level verification commands were re-run green.
