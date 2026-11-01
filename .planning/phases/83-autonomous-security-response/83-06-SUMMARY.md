---
phase: 83-autonomous-security-response
plan: 06
subsystem: autonomous-ops
tags: [autonomous-ops, fence, swarm, soar, xdr, delivery, pytest, vitest]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-03 response_messages.FENCE (swarm, soar, worker, swarm_mission) and the suggestion views"
provides:
  - "propagate-antibody, the SOAR block_ip_firewall and isolate_host plugins and the execute_remediation_script worker task send nothing and answer not_sent with the Autonomous Ops sentence"
  - "swarm_endpoints.CONTAINMENT_MISSION_TYPES: a swarm mission never queues isolate_host (keyword map or model)"
  - "SOAR run log node status not_sent; agents.isolated is no longer set"
  - "test_nothing_writes_the_dead_instructions_queue (with a negative control); swarm_service, soar_engine and tasks left GRANDFATHERED_WRITERS"
  - "playbook_engine_actions: xdr-auto, ai-selector and fallback-selector only reach gate.suggest; rows carry suggestionOnly and a correlation suggestion"
  - "delivery.GATE_ONLY_COMMANDS and error autonomy_gate_required: an unstamped gate-only command is refused at every instruction poll"
  - "SwarmDashboard shows the server not-sent message in the amber style and wraps it"
affects: [83-08, 83-11, 83-16, 83-17]

actuals:
  tokens: 40000
  tasks: 2
  commits: 2
plan_head_before: 6d057b05a059eb84e4bd7d3037dd722d5e462e06
plan_head_after: 3b6cab52506bf984966091021a49a4fc676cef37

tech-stack:
  added: []
  patterns:
    - "A path that sent nothing answers action/status not_sent and the node/run log never says success (PROH-83-10)"
    - "The last place an unstamped command can be stopped is the poll: delivery refuses it whatever wrote it"

key-files:
  created:
    - backend/tests/test_swarm_soar_fence.py
    - src/__tests__/SwarmDashboardNotSent.test.tsx
  modified:
    - backend/swarm_service.py
    - backend/swarm_endpoints.py
    - backend/soar_engine.py
    - backend/tasks.py
    - backend/playbook_engine_actions.py
    - backend/autonomous_ops/delivery.py
    - components/SwarmDashboard.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - backend/tests/test_autonomous_ops_structural.py
    - backend/tests/test_autonomous_ops_xdr_fence.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "An LLM swarm plan that is only isolate_host falls back to the keyword plan (which holds no containment) so the mission still dispatches something honest."
  - "The block plugin answers not_sent with or without an agent id (nothing is sent either way)."
  - "gate_request adds suggestionOnly and the correlation suggestion for every automatic origin, so the two selectors get the same row shape without a change to correlation_engine_threat.py."
  - "delivery matches the command on type, instruction and action, using the same normalisation as the capability check (text before ':', lower case, space and '-' to '_')."

requirements-completed: [RESP-11]

coverage:
  - id: D1
    description: "propagate-antibody writes nothing and answers not_sent, dispatched 0 and the swarm sentence"
    requirement: "RESP-11"
    verification:
      - kind: integration
        ref: "backend/tests/test_swarm_soar_fence.py#test_propagate_antibody_writes_nothing_and_says_not_sent"
        status: pass
  - id: D2
    description: "SOAR block and isolate plugins write nothing, return not_sent; agents.isolated absent; run log marks the node not_sent and the run still completes"
    requirement: "RESP-11"
    verification:
      - kind: integration
        ref: "backend/tests/test_swarm_soar_fence.py#test_isolate_plugin_sends_nothing_and_marks_no_agent_isolated"
        status: pass
      - kind: integration
        ref: "backend/tests/test_swarm_soar_fence.py#test_run_log_marks_the_node_not_sent_and_the_run_goes_on"
        status: pass
  - id: D3
    description: "No tracked backend module writes the instructions collection; scanner has a negative control; three modules left GRANDFATHERED_WRITERS"
    requirement: "RESP-11"
    verification:
      - kind: structural
        ref: "backend/tests/test_autonomous_ops_structural.py#test_nothing_writes_the_dead_instructions_queue"
        status: pass
      - kind: structural
        ref: "backend/tests/test_autonomous_ops_structural.py#test_dead_queue_scanner_negative_control"
        status: pass
  - id: D4
    description: "A swarm mission never queues isolate_host (keyword or LLM); the log carries the fence line once; other steps still run"
    requirement: "RESP-11"
    verification:
      - kind: integration
        ref: "backend/tests/test_swarm_soar_fence.py#test_an_llm_plan_with_isolate_host_is_filtered_and_logged"
        status: pass
  - id: D5
    description: "An unstamped gate-only command is refused at delivery (autonomy_gate_required) and never returned; a stamped one and an unstamped block_ip pass; a list with none is unchanged and nothing is written"
    requirement: "RESP-11"
    verification:
      - kind: integration
        ref: "backend/tests/test_swarm_soar_fence.py#test_an_unstamped_gate_only_command_is_refused_at_delivery"
        status: pass
      - kind: integration
        ref: "backend/tests/test_swarm_soar_fence.py#test_a_stamped_gate_only_command_passes"
        status: pass
  - id: D6
    description: "Automatic XDR executors only reach gate.suggest; rows are suggestionOnly with a correlation suggestion; no response_tasks; a manual run is unchanged"
    requirement: "RESP-11"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_no_automatic_executor_reaches_allow_auto_or_needs_approval"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_manual_block_ip_keeps_the_unstamped_task_shape"
        status: pass
  - id: D7
    description: "A 300-character server not-sent message renders verbatim and wraps in the SwarmDashboard status element, never in the green style"
    requirement: "RESP-11"
    verification:
      - kind: unit
        ref: "src/__tests__/SwarmDashboardNotSent.test.tsx#renders a 300-character server message whole and lets it wrap"
        status: pass
---

# Phase 83 Plan 06: The old containment paths are fenced Summary

**Swarm, SOAR, worker tasks and automatic XDR steps no longer send containment on their own, say so honestly, and a new unstamped 2.1.16 action can only reach an agent through a gate-decided instruction.**

## Fenced entry points

| Entry point | Before | Now |
|---|---|---|
| `POST /api/swarm/propagate-antibody` (`swarm_service.propagate_antibody`) | queued `apply_block_rule` into `instructions` for every online agent, answered `Propagating` | writes nothing; `{status: not_sent, dispatched: 0, antibody_id, threat_type, indicator, message: FENCE["swarm"]}`; `BackgroundTasks` parameter dropped |
| SOAR plugin `block_ip_firewall` | queued `block_ip` into `instructions` | `{action: not_sent, ip, agent_id, message: FENCE["soar"]}` |
| SOAR plugin `isolate_host` | queued `network_isolate` and set `agents.isolated` | `{action: not_sent, host_id, message}`; `agents.isolated` / `isolation_time` never set |
| `SOAREngine.execute_playbook` | every plugin result logged as `success` | a result whose action is `not_sent` is logged as node status `not_sent`; the run keeps going and ends `completed` |
| Celery `tasks.execute_remediation_script` | queued `run_script` and polled 60 seconds | returns `{status: not_sent, output: FENCE["worker"]}` at once; opens no database client |
| Celery `tasks.run_periodic_patch_scan` | queued `run_software_scan` per active agent | queues nothing; the SLA breach part is unchanged (`scans_triggered` is now 0) |
| `swarm_endpoints.run_swarm_lifecycle` / `_goal_to_instructions` | keyword map and model could queue `isolate_host` for every online agent | `CONTAINMENT_MISSION_TYPES = {"isolate_host"}`; keyword branch removed, type removed from the model prompt, plan filtered just before dispatch, `FENCE["swarm_mission"]` logged once; a plan left empty falls back to the keyword plan |
| `playbook_engine_actions._fence_automatic_step` (xdr-auto, ai-selector, fallback-selector) | `gate.decide`, then a stamped response task or approval card | `gate.suggest` only; no `execute_response_task` call; output is the refusal, the simulation or `Suggested only: ...` |
| `playbook_engine_actions.gate_request` | no suggestion inputs | for an automatic origin adds `reason.inputs.suggestionOnly = true` and `suggestion = {kind: correlation, rule: pattern_id}` (the two selectors pick this up through `selector_request`) |
| `delivery.hold_back_autonomous` | looked only at stamped items | also marks any unstamped item whose type, instruction or action is in `GATE_ONLY_COMMANDS` as `refused` / `autonomy_gate_required` and drops it, on all three instruction polls |
| `SwarmDashboard.tsx` | green `Antibody dispatched to 0 agents.` | `dispatched 0` or `status not_sent` shows the server message (or the UI-SPEC fallback) in `bg-amber-50` with an `Info` icon and `break-words`; real counts keep the green style; errors keep red |

Rows an earlier version left in `db.instructions` stay (D-18: fence, do not delete). `gate.execute_response_task` stays in `gate.py` because the `response_task` dispatcher still names it.

## Phase 81 tests that changed

All in `backend/tests/test_autonomous_ops_xdr_fence.py` (docstring states: D-25 amends Phase 81 D-21):

- `test_tracer_xdr_block_ip_at_defaults_is_a_simulation`: `wouldHave` is now `suggest` (was `allow_auto`).
- `test_xdr_block_ip_with_shadow_off_writes_one_stamped_task` became `..._leaves_one_suggestion_and_no_task`.
- `test_isolate_and_rollback_from_an_automatic_executor_become_approval_cards` became `..._are_only_suggestions`.
- `test_quarantine_file_from_an_automatic_executor_is_decided_by_the_gate` became `..._is_only_a_suggestion`.
- `test_a_playbook_step_with_gate_class_approve_raises_block_ip_to_an_approval_card` became `..._is_still_only_a_suggestion` (row is `suggested` / `suggest_requested`, was `awaiting_approval` / `playbook_raised`).
- Added `test_no_automatic_executor_reaches_allow_auto_or_needs_approval`; the two selector tests gained the correlation-suggestion assertion.
- No manual-run assertion was touched; `test_manual_block_ip_keeps_the_unstamped_task_shape` passes unedited.

Also changed: `test_autonomous_ops_structural.py` (three modules removed from `GRANDFATHERED_WRITERS`, new dead-queue scan and negative control), `test_autonomous_ops_copy.py` and `autonomousOpsCopy.test.ts` (`components/SwarmDashboard.tsx` added to the file lists; the frontend count went from 13 to 14).

## Verification

- Plan Task 1 pytest set (fence, structural, copy): 67 passed. Plan Task 2 pytest set (xdr fence, fence, stop, structural): 104 passed. Re-run together with the copy tests at the end: 131 passed. No skips (private mongod on 27998; live 27017 never touched).
- `npx vitest run src/__tests__/SwarmDashboardNotSent.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: 2 files, 24 tests passed, exit 0.
- Extra run of 238 neighbouring tests (capabilities, instruction polls, isolation, dispatch binding, gate order, approvals, block contract, remediation loop): all passed.
- `grep -rnE "(db|mongodb.db|_db|raw(db))(\.|\[['\"])instructions\b"` over backend (no venv, no tests): no match.
- `test_catalogue_route_parity.py::test_ledger_ratchets` still fails with the same pre-existing list; no new name (swarm, soar and tasks are not in it).
- No agent, firewall, service or process call was made; no live restart, deploy or push.

## TDD

- **Task 1 RED:** 11 failed, 1 passed, all on behaviour (old `Propagating`, queued instructions, `isolate_host` still chosen, MongoClient opened). One failure at first was an argument-shape artefact (the old signature took `background_tasks` second); it was real RED for the signature change. Not an import error. The SwarmDashboard test: 5 failed, 1 passed (the red-style test, which was already true) after fixing a helper bug in my own test.
- **Task 2 RED:** the six Phase 81 cases failed on behaviour once the fence changed (suggested row instead of task/card); the delivery tests failed 7 on behaviour and the constant test on `AttributeError`. `gsd_run check tdd-red-evidence` was not run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Dashboard subtitle claimed a broadcast that no longer happens**
- **Found during:** Task 1
- **Issue:** the Digital Immune System subtitle said "Broadcast a block rule (antibody) to all online agents in the tenant."; after the fence that is false.
- **Fix:** changed to the sentence listed under Wording below.
- **Files modified:** `components/SwarmDashboard.tsx`
- **Commit:** 51304de5d

**2. [Rule 3 - Blocking] `soar_engine.py` carried a user hunk**
- `from typing import Any` was uncommitted in the working tree. I committed only my hunks by building a patch from `git show HEAD:backend/soar_engine.py` and `git apply --cached`; the user's import line is still uncommitted.

Otherwise the plan was executed as written. The acceptance grep on the structural test prints 2 for `swarm_service.py|soar_engine.py|"tasks.py"` (a comment I added and the new test's loop over those names), neither in the tuple, as the plan allowed.

## Wording

User-visible sentences the UI-SPEC does not word (please read them):

- `components/SwarmDashboard.tsx` subtitle under Digital Immune System: "Propagating an antibody no longer sends anything to agents. Containment is handled in Autonomous Ops."
- An `aria-label="Dismiss"` on the status close button (accessibility label, not shown).
- Everything else the plan's fences show is an existing `response_messages.FENCE` text or the UI-SPEC fallback, verbatim. The "Suggested only: ..." output of an automatic step is the sentence that already existed in `_fence_automatic_step`.

## Known Stubs

None.

## Notes and observations for the user and later plans

- **Delivery rule reach:** any unstamped queue row that names `quarantine_file`, `unquarantine_file`, `restart_service`, `isolate_host`, `restore_host` or `reboot_host` (as `type`, `instruction` or `action`) is now refused at the poll. A grep of backend writers found no other unstamped writer of those names into `agent_instructions` (the swarm mission was the only one, now fenced), but an operator-typed free-text instruction with one of those names would also be refused. That is the intended RESP-11 behaviour.
- **A-83-PATCHED stays open:** `remediation_service.py` still marks a vulnerability Patched right after calling `execute_remediation_script.delay(...)`, which now answers `not_sent` (and before this plan it never reached an agent either). The false "Patched" status predates the phase and is outside D-18's named paths; it is reported here as a separate defect and not changed.
- **UI not published:** the SwarmDashboard change is in the checkout only. The human-check (open the swarm screen, propagate an antibody, confirm the amber message and narrow-window wrapping) waits for the user's UI publish.
- **A-83-SOAR-UI confirmed by the plan, not re-grepped by me:** I did not re-run the grep for SOAR result renderers; I relied on the plan's finding that none render step results, so no other UI file was touched.
- **Files not read in full:** `83-CONTEXT.md`, `83-RESEARCH.md`, `83-PATTERNS.md`, `83-03-SUMMARY.md` and `.planning/PROJECT.md` were not read; `83-UI-SPEC.md` only section 8; `correlation_engine_threat.py` only lines 40-140; `STATE.md` only the frontmatter. I did not read `.planning/config.json` beyond what the state tools use.
- **Requirements:** `RESP-11` is ticked: this is the only plan that lists it. `RESP-01` is NOT ticked: it spans later plans (83-11 file stage, 83-15); the orchestrator ticks it at the phase gate.
- **Cross-plan facts for the orchestrator:** (1) `delivery.GATE_ONLY_COMMANDS` / `autonomy_gate_required` is live: later plans that write the six commands into `agent_instructions` must stamp them via `gate.execute`. (2) Automatic XDR rows now read as correlation suggestions (`reason.inputs.suggestion.kind == "correlation"`, `rule` = pattern id) and never reach `allow_auto` or `needs_approval`. (3) `swarm_service`, `soar_engine`, `tasks` are no longer grandfathered queue writers; the old `instructions` collection is scanned for any write.

## Self-Check: PASSED

- Files found: `backend/swarm_service.py`, `backend/swarm_endpoints.py`, `backend/soar_engine.py`, `backend/tasks.py`, `backend/playbook_engine_actions.py`, `backend/autonomous_ops/delivery.py`, `components/SwarmDashboard.tsx`, `shared/autonomous-ops-banned-terms.json`, `backend/tests/test_swarm_soar_fence.py`, `src/__tests__/SwarmDashboardNotSent.test.tsx`, the changed tests.
- Commits found in HEAD: `51304de5d`, `3b6cab525`.
