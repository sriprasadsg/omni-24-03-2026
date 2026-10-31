---
phase: 83-autonomous-security-response
plan: 01
subsystem: autonomous-ops
tags: [autonomous-ops, sweep, gate, agent-contract, block-ip, mongodb, pytest]

requires:
  - phase: 81-autonomous-ops-safety-core
    provides: gate.decide / gate.execute, the decision ledger, reconciler, approvals.undo, dispatch_check.bind
provides:
  - shared/agent-response-contract.json, the single contract file the backend and the Rust agent both read
  - autonomous_ops.sweep (single-runner loop + per-tenant tick) and sweep_security (candidate -> gate.decide -> dispatch)
  - autonomous_ops.signals (autonomy_signals store, hostname-to-agent-id resolution, two-origin rule, decision memory)
  - autonomous_ops.verify (bounded_result + settle: the agent's own verify result moves executed to verified or failed)
  - autonomous_ops.response_dispatch (the security_response dispatcher shared by the sweep and approvals)
  - autonomous_ops.agent_support, response_settings, decision_row (undo claim id)
affects: [83-02, 83-03, 83-05, 83-07, 83-09, 83-16, 83-17]

actuals:
  tokens: 23327
  tasks: 3
  commits: 6
plan_head_before: 5d26d6dcdca17dd4984b7858d24e0ceee9655695
plan_head_after: 201bd86d3f0ffe56f0bab63ac051e8a678914538

tech-stack:
  added: []
  patterns:
    - "Agent contract as a shared JSON file read by both backend tests and agent tests"
    - "Verify is the agent's own result, stored bounded and whitelisted; the backend never re-reads a finding"
    - "Undo carries the original instruction's task id as the claim id, read from the row"

key-files:
  created:
    - shared/agent-response-contract.json
    - backend/autonomous_ops/agent_support.py
    - backend/autonomous_ops/decision_row.py
    - backend/autonomous_ops/response_dispatch.py
    - backend/autonomous_ops/response_settings.py
    - backend/autonomous_ops/signals.py
    - backend/autonomous_ops/sweep.py
    - backend/autonomous_ops/sweep_security.py
    - backend/autonomous_ops/verify.py
    - backend/tests/test_autonomous_ops_block_contract.py
    - backend/tests/test_autonomous_ops_sweep.py
  modified:
    - backend/autonomous_ops/gate.py
    - backend/autonomous_ops/approvals.py
    - backend/autonomous_ops/reconciler.py
    - backend/agent_tasks_endpoints.py
    - backend/app_startup.py
    - backend/tests/autonomy_support.py

key-decisions:
  - "The sweep's memory (autonomy_signals.decision) holds a dispatched block quiet until its blockedUntil; if no window was recorded it holds for 24 hours from the decision. The fuller memory table is 83-05."
  - "A refused dispatch moves the row out of dispatching at once: stopped -> cancelled_by_stop (reasonCode platform_stop, as approvals does), anything else -> failed dispatch_failed."
  - "settle treats verify.ok false as winning over outcome already_applied: a failed check is never reported as verified."
  - "A feed row corroborates only an address some host already has from a host-bound observation (native verdict in this plan); a global feed row alone never names a host."

patterns-established:
  - "Stage signature run(db, tenant_id, tenant, response, now) -> Dict[str, int]; sweep.tick sums the counts"
  - "Tests that need the real capability rule use @pytest.mark.real_agent_capabilities (conftest switches every capability on otherwise)"

requirements-completed: [RESP-01, RESP-02, RESP-06, ACTV-02]

coverage:
  - id: D1
    description: "Tracer: a native Malicious ip verdict posted under the hostname plus a global URLhaus row for the same address becomes one gate-decided block_ip row (origin sweep, dispatcher security_response) and one stamped instruction addressed to agents.id, with ttl_seconds 86400"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_tracer_two_origins_one_block_then_verified"
        status: pass
    human_judgment: false
  - id: D2
    description: "The agent's own verify result (replayed from the contract through the real result route) moves the row dispatching -> executed -> verified with blockedFrom/blockedUntil; verify ok false ends failed verify_failed and dispatches nothing; absent verify leaves it executed"
    requirement: "RESP-06"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_a_failed_verify_ends_failed_and_dispatches_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_verify_true_false_and_absent_are_three_different_outcomes"
        status: pass
    human_judgment: false
  - id: D3
    description: "A block whose address stays flagged is never lifted or repeated; a structural test fails if verify.py, response_dispatch.py or reconciler.py names remediate, _dispatch_and_verify, _check_nscan_resolved, security_scan_results or imports the old remediation service"
    requirement: "RESP-06"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_a_block_that_is_still_flagged_is_never_lifted_or_repeated"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_verify_path_never_reads_findings"
        status: pass
    human_judgment: false
  - id: D4
    description: "Operator undo of a verified block writes one stamped unblock_ip with params {ip_address, block_id}, block_id equal to the first instruction id; other dispatchers keep the old undo params; an expired block refuses not_undoable"
    requirement: "ACTV-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_undo_sends_one_unblock_that_names_the_original_block_instruction"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_an_expired_block_can_no_longer_be_undone_and_nothing_is_written"
        status: pass
    human_judgment: false
  - id: D5
    description: "The sweep starts with the backend, runs under one renewed lock (a second runner gets None), stops between tenants when the lock is lost, contains one tenant's failure, and a crash between decide and execute ends as not_delivered"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_sweep.py#test_only_one_sweep_runner_ticks_at_a_time"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_sweep.py#test_a_crash_between_decide_and_execute_ends_as_not_delivered"
        status: pass
    human_judgment: false
  - id: D6
    description: "Shadow mode records one shadow row with wouldHave allow_auto and writes no instruction"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_block_contract.py#test_shadow_records_would_have_and_writes_no_instruction"
        status: pass
    human_judgment: false
  - id: D7
    description: "A real firewall rule is applied and lifted on a real host by the published agent"
    requirement: "RESP-02"
    verification: []
    human_judgment: true
    rationale: "Nothing in this plan runs a real firewall. A stand-in agent replays the contract examples; 83-02 makes the Rust agent produce them and the live round trip stays a UAT item (A-83-E2E)."

duration: 20min
completed: 2026-10-31
status: complete
---

# Phase 83 Plan 01: Tracer - one flagged IP to one verified, undoable block Summary

**A native Malicious ip verdict (posted under the hostname) corroborated by a global URLhaus row now becomes one gate-decided `block_ip` instruction addressed to `agents.id`, the agent's own verify result marks it verified or failed with nothing compensated, and an operator undo removes only that block's claim.**

## Performance

- **Duration:** 20 min
- **Tasks:** 3 (1 tracer, 2 auto), all TDD
- **Commits:** 6 (3 test, 3 feat), measured from `5d26d6dcd` to `201bd86d3`
- **Files:** 17 changed in the production range (11 created, 6 modified)

## Accomplishments

- **Contract file** `shared/agent-response-contract.json` keys: `version`, `description`, `tokens` (10), `commandToken`, `rangeToken`, `blockTtlSeconds` {min 3600, max 604800, default 86400}, `isolationRevertSeconds` 14400, `rebootDelaySeconds` {min 30, max 300}, `stillRunningCap` 128, `outcomes` (19), `checks` (9), `protectedPaths` {windows, linux}, `criticalServices` (18), `examples` (17 named result bodies including `kill_done`, `kill_gone`, `kill_survived`, `kill_refused`; every `still_running` entry is `{pid, name, start_time}`).
- **Tracer path** (`signals` -> `sweep_security` -> `gate.decide` -> `response_dispatch.send`): hostname resolves to one agent of the same tenant or to nothing; a hostname shared by two agents, or one from another tenant, produces no row; one origin alone produces nothing while the two-source rule is on; two origins more than 24 hours apart do not corroborate (D-03).
- **Verify without compensation**: `verify.bounded_result` whitelists `outcome`, `verify{ok,check}`, `expires_in` (0..604800), `healthy_after` (0..3600) and a capped `still_running` list before `report_instruction_result` stores them (one added line). `verify.settle` is called by the reconciler for `security_response` rows after they reach `executed`; `ok true` or `already_applied` -> `verified` (with `blockedUntil` from now + `expires_in`), `ok false` -> `failed` / `verify_failed`, no verify block -> stays `executed`. With the finding still Malicious and five extra reconciler ticks the row, its `verifiedAt` and the one instruction are unchanged, for both the applied and the verify-failed result.
- **Undo claim** (ACTV-02): `decision_row` (moved out of `gate.py`, which drops from 500 to 446 lines) adds `CLAIM_KEYS` and `undo_block(..., claim=)`; `approvals.undo` reads the claim from `instructionIds[0]` for `security_response` rows only and refuses `not_undoable` once `blockedUntil` has passed. `dispatch_check.bind` is unchanged and accepts the dispatch; a foreign `block_id` is a `step_mismatch`.
- **Runner**: `sweep.run_once` / `sweep_loop` under lock `autonomous_ops_sweep` (TTL 120, renew 30, `AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC` default 60), started in `app_startup.run_startup_services` beside the reconciler.
- **Quiet repeat ticks**: ten more sweep ticks after a verified block, and five after an undo, add no row and no instruction.

## Task Commits

| Task | Commit | Type |
|------|--------|------|
| Contract file + RED tests for Task 1 | `bb2def77c` | test |
| 1 Tracer: two origins -> one block -> verified | `93197ee98` | feat |
| 2 RED: single-runner loop and wiring | `0d5bf6949` | test |
| 2 Sweep every minute, one runner | `aab0c4191` | feat |
| 3 RED: undo claim and row builder | `223893b42` | test |
| 3 Undo removes only this claim | `201bd86d3` | feat |

## Verification Results

- Task 1 command (block contract, sweep, reconciler, structural): 122 passed, 0 skipped.
- Task 2 command (sweep, reconciler, structural): 96 passed, 0 skipped.
- Task 3 command (block contract, approvals, gate, gate order, dispatch binding, structural): 190 passed, 0 skipped.
- Plan verification `test_autonomous_ops_copy.py`: passed (run together with the gate-order tests: 40 passed).
- Wider regression run, every `test_autonomous_ops_*.py` plus `test_agent_task_dispatch.py`, `test_agent_capabilities.py` and `test_agent_instruction_poll_identity.py` on the private mongod (27998): 558 passed, no skips, no Phase 81 test edited.
- Acceptance criteria re-run: `tokens` = 10; `stillRunningCap`/`kill_survived.verify.ok` = `128 False`; `grep -c bounded_result agent_tasks_endpoints.py` = 1 (file grew by one net line); `test_verify_path_never_reads_findings` present once; `sweep.py` 125 lines, `gate.py` 446, `approvals.py` 249, `sweep_security.py` 88; `CLAIM_KEYS` appears 4 times in `decision_row.py`; `autonomous_ops_sweep` in `sweep.py` and `sweep_loop` in `app_startup.py`.
- Tracer gate (`human_verify_mode` end-of-phase, automated-only verify): re-ran the tracer verify end to end before Task 2 and Task 3, passed, so expansion continued.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Capability rule is switched on by conftest in every test**
- **Found during:** Task 1 (`test_check_names_the_first_reason_a_host_cannot_act` returned `None`, not `capability_off`)
- **Issue:** `tests/conftest.py` patches `agent_capabilities.allowed_for` to allow everything unless a test carries the `real_agent_capabilities` marker.
- **Fix:** marked that one test; the other tests rely on the permissive default and `seed_response_agent(capable=True)` also stores `agentCapabilities: ["all"]` so the data matches.
- **Files modified:** `backend/tests/test_autonomous_ops_sweep.py`
- **Commit:** `93197ee98`

**2. [Rule 2 - Missing critical] Memory fallback when a block window was not recorded**
- **Found during:** Task 1 design of `_remembered_block_holds`
- **Issue:** if `blockedUntil` failed to record, the sweep would have repeated the block every tick.
- **Fix:** hold for 24 hours from the decision time when no window is stored.
- **Files modified:** `backend/autonomous_ops/sweep_security.py`
- **Commit:** `93197ee98`

### Plan departures that are choices, not fixes

- `seed_response_agent` takes two extra keywords, `capable` and `status`; `signals` has two extra helpers, `index_agents` and `global_ip`, and `ensure_indexes`. `resolve(hosts_by_key, name)` takes the dict of lists that `index_agents` builds, so a shared name is visible rather than overwritten.
- Task 3 step 5 (skip while `now < blockedUntil`) was already in `sweep_security` from Task 1, because the tracer needed quiet repeat ticks; Task 3 only added the tests for it.
- RED evidence: the Task 1 RED run was a collection `ImportError` (every module under test is new), which the strict RED classifier would call `fixture_or_load_failure`. Tasks 2 and 3 failed on the target assertions (missing `run_once` / `_interval`, wrong undo params, `not_undoable`, gate over 500 lines). No `gsd_run check tdd-red-evidence` record was produced.

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing-critical), 3 choices. **Impact:** none on the plan's truths; all verified.

## Phase 81 tests

No Phase 81 gate, approvals or reconciler test changed its expectation or was edited. `gate.APPROVAL_TTL` is still imported in `gate.py` because `test_autonomous_ops_gate.py` reads it.

## Known Limitations (carried forward, not stubs)

- A crash between the reconciler's `dispatching -> executed` move and the `settle` call leaves a `security_response` row at `executed`: the reconciler only visits tenants with open rows and re-reads only `dispatching` rows. Rare and visible in the ledger; a re-settle pass for `executed` rows with no `verifiedAt` belongs with the 83-05 memory table or 83-09.
- A block whose verify failed (or whose send failed after queueing) is held quiet until `blockedUntil` by the sweep memory, so it is not retried inside that window.
- `autonomy_signals` has its unique index created by `signals.ensure_indexes` (called in tests); the migration that creates it on the live database is a later plan (028).
- `autonomy_settings.response` keys are `twoSignal`, `blockHours`, `watchedServices`; the write path, validation and control rows are 83-07.
- Inputs not read in full for this run: `83-CONTEXT.md`, `83-VALIDATION.md`, `83-UI-SPEC.md`, `.planning/PROJECT.md`, and the parts of `83-RESEARCH.md` outside Patterns 1-5, Q1-Q7, Code Examples and Anti-Patterns. `STATE.md` was read from the frontmatter only before the state update.

## Known Stubs

None.

## Threat Flags

None. The new network-facing surface (the result route storing `verify`/`outcome`) is the T-83-01 mitigation named in the plan.

## Self-Check: PASSED

Files verified on disk and commits verified as ancestors of HEAD before this summary was committed (see the command output in the run log).
