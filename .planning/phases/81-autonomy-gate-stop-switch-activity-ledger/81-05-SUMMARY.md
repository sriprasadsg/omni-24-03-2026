---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 05
subsystem: autonomous-ops
tags: [stop-switch, delivery-hold-back, fail-closed, tenant-isolation, capability-map, mongo, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01)
    provides: settings.platform_stop / load / stop_active, ledger.transition / record_control, gate.execute stamps
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-11)
    provides: messages.NOTICES (stop notices), notify.notify
provides:
  - "stop.press / clear / can_clear / cancel_undelivered / platform_stop_doc / REASON_MAX"
  - "delivery.hold_back_autonomous / hold_back_response_tasks"
  - "hold-back wired into all three instruction polls and the response-task poll"
  - "agent_capabilities mapping for every registry command"
affects: [81-08, 81-09, 81-12]

actuals:
  tokens: 21000
  tasks: 3
  commits: 3

plan_head_before: eb6c8c23f14f1bf94a779630592d80fd6cb2b1c6
plan_head_after: c8921839b791be0fb082bd7ff6da2d2c26a1f352
commits: 3

tech-stack:
  added: []
  patterns:
    - "Stop pressed/cleared by conditional update_one on stop.active (modified_count == 1 wins); stop never cached"
    - "Delivery screen: no stamped item means the list is returned and no database call is made"
    - "Fail closed: unreadable stop or ledger leaves the stamped item pending (withheld), unreadable never cancels"

key-files:
  created:
    - backend/autonomous_ops/stop.py
    - backend/autonomous_ops/delivery.py
    - backend/tests/test_autonomous_ops_stop.py
  modified:
    - backend/agent_tasks_endpoints.py
    - backend/deployment_result_endpoints.py
    - backend/agent_instruction_endpoints.py
    - backend/response_orchestrator.py
    - backend/agent_capabilities.py
    - backend/tests/test_agent_instruction_poll_tenant_scoping.py
    - backend/tests/test_agent_capabilities.py

key-decisions:
  - "A stop-withheld stamped action/probe becomes terminal cancelled_by_stop on the instruction (or response task) and its ledger row moves approved/dispatching -> cancelled_by_stop; a row already executed is left alone"
  - "An unreadable stop, settings or ledger row withholds the stamped item but leaves it pending (retried next poll); only a known stop cancels, only a known ledger problem refuses"
  - "Tenant agreement is checked without a database call first: instruction tenantId, stamp tenantId and the polling tenant must be one value, then the ledger row tenant must equal it; any disagreement marks the item refused"
  - "can_clear lets a manage holder clear only a tenant stop whose stored pressedByTier is exactly tenant; a missing or unknown tier needs the Super Admin (fail closed)"
  - "press never undoes itself: a failed bulk cancel, control row or notice is logged after the stop is on"
  - "The unmounted agent_instruction_endpoints handler passes the polled agent's own tenantId as the polling tenant, so a Super Admin polling another tenant's agent is not mis-refused"

requirements-completed: [GATE-06]

coverage:
  - id: D1
    description: "A tenant stop pressed now holds back that tenant's queued stamped instruction at the next agent poll with no restart; the unstamped instruction is delivered; the held-back one stays cancelled_by_stop after clear"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py#test_tracer_tenant_stop_holds_back_the_queued_instruction_at_the_next_poll"
        status: pass
    human_judgment: false
  - id: D2
    description: "Hold-back at the deployment-result poll, the unmounted instruction handler and the response-task poll; platform stop covers every tenant while undo and compensate flow"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py#test_stamped_is_held_back_and_unstamped_delivered_by_the_other_handlers"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py#test_platform_stop_holds_every_tenant_but_undo_and_compensate_flow"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py#test_response_tasks_are_held_back_under_a_stop_but_manual_ones_are_returned"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fail closed: unreadable stop or ledger withholds stamped items and leaves them pending; no stamped item means no database call; other-tenant, missing and non-dispatchable ledger rows are refused"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py (unreadable stop, unreadable ledger, other tenant, missing/non-dispatchable tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_stop.py#test_no_stamped_instruction_means_no_database_call"
        status: pass
    human_judgment: false
  - id: D4
    description: "Press-time bulk cancel for its scope (tenant or every tenant) returns the count; undo/compensate untouched"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py#test_press_bulk_cancels_for_its_scope_and_returns_the_count"
        status: pass
    human_judgment: false
  - id: D5
    description: "can_clear matrix (seven cases), reason rules (press optional/500, clear required/trimmed/500), not_stopped/already_stopped, control rows and audit mirror, nothing else clears a stop"
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_stop.py#test_can_clear_matrix"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py#test_nothing_but_clear_turns_an_active_stop_off"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every registry command resolves to an agent capability; the six new mappings and autonomous_remediation hold"
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_stop.py#test_every_registry_command_maps_to_a_capability"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_capabilities.py#test_autonomous_ops_commands_need_the_capability_that_carries_them_out"
        status: pass
    human_judgment: false
  - id: D7
    description: "Holding back a queued instruction on a real agent poll on the live server after the backend restart"
    requirement: GATE-06
    human_judgment: true
    rationale: "Needs the user's backend restart and a real agent poll (A-81-LIVE-STOP); mocks cannot prove the live path"

duration: 30min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 05: Stop switch and delivery hold-back Summary

**Stop press/clear service (compare-and-set, D-11 authority from the stored press tier, typed reason, control rows plus audit mirror) and a fail-closed delivery hold-back that cancels queued stamped autonomous work at every queue an agent reads, plus the capability map for every registry command**

## Performance

- **Duration:** about 30 min
- **Completed:** 2026-10-26
- **Tasks:** 3 (1 tracer, 2 auto)
- **Files:** 3 created, 7 modified

## Accomplishments

- Pressing a tenant stop is effective on the very next agent poll with no restart (stop state is read fresh on each call): the stamped instruction becomes terminal `cancelled_by_stop`, its ledger row follows, the unstamped human instruction is delivered, and the cancelled instruction stays cancelled after `stop.clear` (PROH-81-09).
- `press` bulk-cancels undelivered stamped action/probe instructions and queued stamped response tasks for its scope (one tenant, or every tenant for the platform stop) and returns the count; undo and compensate are never cancelled.
- `clear` is the only code that sets an active stop inactive (PROH-81-07; a test runs `ensure_tenant`, `ensure_all_tenants`, level/shadow setters and `reconciler.tick` against active stops).

## Delivery paths hooked

| Path | Where | Call |
|---|---|---|
| Mounted agent poll (`GET /api/agents/{hostname}/instructions`) | `backend/agent_tasks_endpoints.py:get_agent_instructions` | `delivery.hold_back_autonomous` right after `agent_capabilities.hold_back` |
| Mounted deployment-result poll | `backend/deployment_result_endpoints.py:get_agent_instructions` | same, right after the capability hold-back |
| Unmounted third handler | `backend/agent_instruction_endpoints.py:get_agent_instructions` | after the `agent_instructions` find, before the status "delivered" update |
| Response-task queue (third queue, D-21) | `backend/response_orchestrator.py:ResponseOrchestrator.get_pending_tasks` | `delivery.hold_back_response_tasks` before return |

Other readers of these collections (`mdr_service`, `chaos_engineering_service`, `software_endpoints`, `response_endpoints` list routes) are dashboards or lookups, not agent delivery.

## can_clear matrix (tested)

| Stop (scope / pressedByTier) | manage:autonomous_ops holder | Super Admin |
|---|---|---|
| tenant / tenant | yes | yes |
| tenant / tenant, approver without manage | no | - |
| tenant / platform | no | yes |
| platform / platform | no | yes |
| missing or unknown origin | no | yes |

## Task Commits

1. **Task 1 (tracer): stop + hold-back on the mounted poll** - `97f08c757`
2. **Task 2: other delivery paths, fail-closed reads, cross-tenant rows** - `7a0294675`
3. **Task 3: authority/reason tests and capability map** - `c8921839b`

Task 3's `can_clear`/`clear` behaviour was already complete from Task 1 (the plan said Task 1 "can stay minimal"); its authority tests passed on first run, only the capability-map test was red before the mapping was added.

## Deviations from Plan

None - plan executed exactly as written.

**Own-hunk confirmation:** only this plan's hunks of `backend/deployment_result_endpoints.py` (import + hook, 3 lines) and `backend/agent_capabilities.py` (six mapping lines at the end of `_INSTRUCTIONS`) were committed, staged with `stage-own.sh` and checked with `git diff --cached`. The user's newest-wins comment and `sort=[("_id", -1)]` in `deployment_result_endpoints.py`, the collection-interval code in `agent_capabilities.py`, and the `import sys, os` split in the tenant-scoping test file remain unstaged and uncommitted.

## Issues Encountered

- Task 2's first "other handlers" test passed before the hook existed, because `stop.press` had already bulk-cancelled the work. The test now writes the stop straight into settings (no bulk cancel), the state of a stop pressed while a poll was about to deliver; it then failed red and passed once hooked.

## Known Stubs

None.

## Residual race (accepted)

A poll that has already fetched an instruction can still return it if the stop lands between the find and the "sent" update; the window is the length of one request. The press-time bulk cancel plus the hold-back on every later poll closes everything else.

## Steps for the user

- Restart `omni-backend.service` (the backend runs from this checkout without reload) before the hold-back is live; not done here.
- Live check (A-81-LIVE-STOP): queue a stamped test instruction for a shadow-off test tenant, press the stop, confirm the next real agent poll does not deliver it. HTTP routes for press/clear arrive in 81-09.
- A-81-ROLLOUTS: no rollout engine exists in Phase 81; Phase 84 rollouts must read `settings.platform_stop` and the tenant stop.

## Threat Flags

None. No new endpoint or schema at a trust boundary; T-81-19 to T-81-23 are mitigated and tested.

## Self-Check: PASSED

Created files exist (stop.py, delivery.py, test_autonomous_ops_stop.py); commits 97f08c757, 7a0294675, c8921839b are ancestors of HEAD; acceptance greps re-run (hold_back_autonomous( count 1 in each of the three handlers, hold_back_response_tasks( 1, stop.py def count 4, capability mapping grep 3). Verification: `pytest test_autonomous_ops_stop test_agent_instruction_poll_tenant_scoping test_agent_instruction_poll_identity test_agent_capabilities test_response_orchestrator_tenant test_autonomous_ops_registry` -> 87 passed, 0 skipped; the other autonomous_ops suites (gate, ledger, approvals, reconciler, isolation, breaker) -> 109 passed.

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
