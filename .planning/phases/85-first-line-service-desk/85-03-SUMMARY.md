---
phase: 85-first-line-service-desk
plan: 03
subsystem: autonomous-ops-gate
tags: [gate, registry, ledger, service-desk, breaker, rate-limit, audit]
status: complete

requires: []
provides:
  - "registry rows ticket_answer (auto, undo ticket_withdraw) and ticket_withdraw (undo_only), target_kind ticket, dispatchers (service_desk,); registry.agent_commands()"
  - "backend/autonomous_ops/desk_gate.py: DISPATCHER and ticket_owner_step, the ownership step that replaces the agent target check for the service desk"
  - "gate.ActionRequest.desk and the row's desk subdocument (decision_row.build_row)"
  - "autonomous_ops/messages.py: ACTION_LABELS ticket_answer / ticket_withdraw / ticket_handoff, DESK_ACTION_LABELS, DESK_UNDO_HINT, REASON_TEXT desk_rate_limit, API_DETAIL desk_draft"
  - "ledger.DESK_KIND, _pool_filter, count_auto_since(pool=); recent_finished_auto excludes desk rows"
  - "ledger.DESK_FIELDS, record_desk_event, set_desk_fields (audit events autonomous_ops.servicedesk.handoff and autonomous_ops.servicedesk.<event>)"
affects: [85-01, 85-04, 85-13, 85-18]

actuals:
  tokens: 7500
  tasks: 3
  commits: 3
plan_head_before: 096f50d98211f0a888ce0625dc773fa05e240aa0
plan_head_after: 86f7a5530fedf795768742c69e3495038ccc8dd0

tech-stack:
  added: []
  patterns:
    - "Add-alongside: the gate keeps agent as its primary target; the ticket target is one dispatcher-scoped step (desk_gate) behind a single delegation in _step_protected_targets"
    - "Two automatic-action pools selected by a kind filter (_pool_filter); the default pool keeps every Phase 81 to 84 caller unchanged"
    - "Desk rows are excluded from the Phase 81 breaker at the query (recent_finished_auto), not in breaker.py"

key-files:
  created:
    - backend/autonomous_ops/desk_gate.py
    - backend/tests/test_service_desk_ledger.py
  modified:
    - backend/autonomous_ops/registry.py
    - backend/autonomous_ops/gate.py
    - backend/autonomous_ops/decision_row.py
    - backend/autonomous_ops/messages.py
    - backend/autonomous_ops/ledger.py
    - backend/service_desk/messages.py
    - backend/tests/test_autonomous_ops_registry.py
    - backend/tests/test_autonomous_ops_stop.py

key-decisions:
  - "Add-alongside accepted as written (registry rows plus a dispatcher-scoped ownership step); promoting a general target model is deferred until a third non-agent actor exists"
  - "Activity words are declared once in autonomous_ops/messages.py; service_desk/messages.py now refers to them (service_desk may import autonomous_ops, never the reverse)"
  - "set_desk_fields also filters on kind servicedesk, so desk.* keys can never be written onto a security or patch row"

requirements-completed: [DESK-01, DESK-02]

coverage:
  - id: D1
    description: "The gate takes ticket_answer from the service_desk dispatcher only, on a ticket of the caller's own tenant; the row keeps the request's desk subdocument; no ticket command is an agent command"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_ledger.py; backend/tests/test_autonomous_ops_registry.py#test_ticket_answer_only_for_the_service_desk; backend/tests/test_autonomous_ops_stop.py#test_every_registry_command_maps_to_a_capability"
        status: pass
    human_judgment: false
  - id: D2
    description: "Desk rows are counted in their own pool and never reach the Phase 81 breaker or the security and patch rate limit"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_ledger.py (pool and breaker cases); backend/tests/test_autonomous_ops_breaker.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every hand-off is an audited ledger row; the draft lifecycle can be recorded on a desk row without a state change"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_ledger.py (hand-off and set_desk_fields cases)"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 03: The desk's place in the Autonomous Ops ledger Summary

The gate now accepts a ticket answer from the service desk only and only on a ticket of the caller's own tenant, desk rows live in their own rate pool and stay out of the Phase 81 breaker, and every hand-off and draft action can be written as an audited ledger row.

Duration: about 35 min (19:00 to 19:13 UTC for the three commits, plus reading). Tasks: 3. Files: 10 (2 created, 8 modified). Completed 2026-11-08.

## Accomplishments

- **Gate seam (Task 1, 99ebadc73).** `ticket_answer` (auto, undone by `ticket_withdraw`) and `ticket_withdraw` (undo_only) are registry rows with `target_kind="ticket"` and `dispatchers=("service_desk",)`. Any other dispatcher is refused `unregistered_action` and records nothing (existing `_step_class` logic, no change). `_step_protected_targets` delegates to `desk_gate.ticket_owner_step` for the service_desk dispatcher. `ActionRequest.desk` is copied onto the row only when it is a dict. `registry.agent_commands()` excludes the ticket commands, and the capability test now iterates it.
- **Pools (Task 2, dc8193ab3).** `count_auto_since(..., pool="actions")` excludes control and servicedesk rows; `pool="servicedesk"` counts only the desk. `recent_finished_auto` uses the actions pool filter, so withdrawn desk answers cannot trip `breaker.evaluate` (test: three undone desk rows leave the level at undoable_auto; three undone security rows still trip it). The gate's `_step_blast_radius` and `rollout/installs.py` keep calling the default pool unchanged.
- **Hand-offs and updater (Task 3, 86f7a5530).** `record_desk_event` writes the finished `servicedesk` / `ticket_handoff` row with the full `build_row` field set and one audit event; `set_desk_fields` updates allow-listed `desk.*` keys with one audit event naming the actor and never touches `state`.

## Interface the 85-01 tracer builds on

- `ActionRequest` fields used: `tenant_id`, `kind="servicedesk"`, `origin="service_desk"`, `actions=["ticket_answer"]`, `targets=[]`, `params={"ticketId": <id>}`, `dedupe_key`, `reason={"ruleId": "service_desk:answer", "inputs": {..., "suggestionOnly": True}}`, `dispatcher="service_desk"`, `force_suggest`, and the new `desk={"ticketId", "ticketNumber", "title", "phase"}`.
- Registry rows: `ticket_answer` = auto, undo `ticket_withdraw`, `target_kind="ticket"`, `dispatchers=("service_desk",)`; `ticket_withdraw` = undo_only, same kind and dispatchers. `ticket_handoff` is a label and a row command only (not a registry action).
- `desk_gate.ticket_owner_step` refusal codes, in order: `invalid_target` (any target given), `no_target` (ticketId missing, empty or not a string), `cross_tenant_target` (no ticket with that id and the request's tenantId), `protected_target` (the ticket read raised: fail closed). Refusals other than the unregistered dispatcher are recorded as `refused` rows; none leaves a dispatching, suggested or executed row. `ctx.distinct` stays empty, so the host cap is inert; 85-04 adds the rate step in `desk_gate.py`.
- Test note: `gate.decide(..., master_shadow=False)` plus `seed_tenant(shadow=False)` gives `allow_auto` / `dispatching`; with the env var unset the deployment master is shadow on.
- Audit actions are `autonomous_ops.servicedesk.handoff` and `autonomous_ops.servicedesk.<event>` (the existing `_mirror` prefix is kept).
- `ledger.transition(... "dispatching" -> "executed", **{"desk.phase": "posted", ...})` works as 85-01 plans it (kwargs become `$set` keys); `set_desk_fields` is the audited route for desk keys outside a state change.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 99ebadc73 | feat | Gate takes a ticket answer from the service desk only, on the caller's own ticket |
| 2 | dc8193ab3 | feat | Own automatic-action pool for the desk and no part in the breaker |
| 3 | 86f7a5530 | feat | Hand-off row writer and audited desk-field updater |

Each task is one commit (plan type `execute`, tasks marked `tdd="true"`): tests and implementation were written together and committed together, as in 85-02.

## Verification

- Task 1 command (ledger, registry, gate, gate_order, stop, structural, copy): 161 passed, no skips.
- Task 2 command (ledger, breaker, gate): 83 passed. Task 3 command (ledger, ledger test, structural): 76 passed.
- Combined run adding the starters and tray-contract tests: 268 passed. Extra regression run (approvals, dispatch_binding, multi_step_rows, response_rows, endpoints, origins, reconciler, two_signal, restart_budget): 274 passed.
- `npx vitest run src/__tests__/serviceDeskCopy.test.ts`: 17 passed.
- Acceptance greps: `ticket_answer` in registry.py 1, `def agent_commands` 1, `ticket_owner_step` in gate.py 1, no `service_desk` import in desk_gate.py (0), `DESK_KIND` 3+ and `pool` 13 in ledger.py, record_desk_event and set_desk_fields 2. Sizes: gate.py 463, desk_gate.py 41, ledger.py 426 lines.
- Every test used the private mongod on 27998; nothing touched the live database.

## Existing tests whose expectation changed

- `test_autonomous_ops_registry.py`: `AUTO` gains `ticket_answer`; the dispatchers loop allows `ticket_answer` and `ticket_withdraw` (as the plan named). New test `test_ticket_answer_only_for_the_service_desk`.
- `test_autonomous_ops_stop.py::test_every_registry_command_maps_to_a_capability`: iterates `registry.agent_commands()` and asserts the two desk commands are absent (as the plan named).
- No Phase 81, 83 or 84 gate, breaker, ledger, rollout or response test changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Single source] Duplicate Activity words in service_desk/messages.py**
- **Found during:** Task 1 (orchestrator note from the 85-02 hand-over)
- **Issue:** 85-02 had put `ACTION_LABELS` (post, draft, handoff) and `UNDO_HINT` in `backend/service_desk/messages.py`; this plan declares the same strings in `autonomous_ops/messages.py`. Two copies of user-facing text drift.
- **Fix:** Kept the declarations in `autonomous_ops/messages.py` and made the service_desk entries read them (`from autonomous_ops import messages as _ao_messages`). service_desk imports autonomous_ops; the reverse never happens (structural test green). The docstring of `service_desk/messages.py` says so.
- **Files modified:** backend/service_desk/messages.py
- **Verification:** test_service_desk_starters, test_service_desk_tray_contract, test_autonomous_ops_copy, test_autonomous_ops_structural and serviceDeskCopy.test.ts all pass.
- **Commit:** 99ebadc73

**2. [Rule 2 - Safety] set_desk_fields also filters on kind servicedesk**
- **Found during:** Task 3
- **Issue:** The plan filters on id and tenantId. With only those, a wrong id could write `desk.*` keys onto a security or patch row.
- **Fix:** The update filter also requires `kind: servicedesk`. Wrong tenant, unknown id and non-desk rows all return None with no audit event.
- **Commit:** 86f7a5530

**3. [Rule 1 - Test fit] hand-off Result text is not asserted on the view**
- **Found during:** Task 3
- **Issue:** The plan's behavior lists only bucket and label for `present_row`. The view currently shows `Done.` for the hand-off row, not the stored `activityResult`, because `response_views` reads `activityResult` for the rollout dispatcher only.
- **Fix:** The test asserts bucket done, label "Send ticket to a person", `canUndo` False and no exception. Wiring the Result column is left to the Activity-rows plan (see Notes).

**Total deviations:** 3 (1 single-source, 1 safety filter, 1 test fit). **Impact:** none on scope; no architectural change.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-85-02, T-85-09, T-85-10 and T-85-11 are covered by tests; T-85-SC accepted (no package installed). `ticket_owner_step` reads `tickets` by id and tenantId only; it adds no endpoint.

## User steps

None. No restart, publish, push, migration or agent build was needed or done. The backend runs from the checkout, so these gate changes go live with the next backend restart (the user's step, later).

## Notes for later plans

- The Activity view still presents desk rows generically. `views._can_undo` (response_views.py) requires non-empty `targets`, so a posted `ticket_answer` row (targets `[]`) shows no Undo button, and `activityResult` is shown for rollout rows only. The Activity-rows plan (85-04 or later) must extend `row_extras` for the `service_desk` dispatcher to show `activityResult` and to offer Undo from `desk.undoable`.
- 85-04 adds the desk rate step in `desk_gate.py` using `ledger.count_auto_since(..., pool="servicedesk")` and `messages.REASON_TEXT["desk_rate_limit"]`; 85-18 owns the desk breaker over desk rows.
- The 85-02 hand-off activity string (`ACTIVITY["handoff_result"]`) and the `activity_result` argument of `record_desk_event` are the same sentence; the caller formats and passes it.
- The user's uncommitted work (`backend/tickets_endpoints.py`, `components/InternalTicketsDashboard.tsx`, `shared/catalogue-gaps.json`, the Rust `Cargo.toml` and `Cargo.lock`) was not touched and is still unstaged.

## Self-Check: PASSED

Created files desk_gate.py and test_service_desk_ledger.py exist; commits 99ebadc73, dc8193ab3 and 86f7a5530 are ancestors of HEAD; all task acceptance criteria and the plan-level verification commands were re-run green.
