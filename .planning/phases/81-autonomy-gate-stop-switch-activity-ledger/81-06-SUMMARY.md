---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 06
subsystem: autonomous-ops
tags: [gate, xdr, playbook-fence, selectors, confidence-bypass, shadow-mode, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01, 81-11)
    provides: gate.decide / gate.suggest / gate.execute_response_task, registry, messages, shadow wrapper
provides:
  - "playbook_engine_actions.AUTOMATIC_EXECUTORS and the gate fence on block_ip, isolate_endpoint, quarantine_file, rollback_ransomware"
  - "playbook_engine_actions.gate_request / selector_request: the single request builders for the fence and the selectors"
  - "_ai_select_playbook and _fallback_select_playbook record a suggestion through gate.suggest and never run a playbook"
  - "backend_safety.evaluate_action without the 0.90 confidence auto-approve"
affects: [81-08, 81-09, 81-12]

actuals:
  tokens: 21000
  tasks: 2
  commits: 2

plan_head_before: cfdc741411c343dc57a9a3606e0369ef85f048b2
plan_head_after: fb93c117f9dc26664af965eeed7126163ea9c051
commits: 2

tech-stack:
  added: []
  patterns:
    - "Automatic executors branch to the gate at the top of each action (after the existing ValueError validation); the manual path below is untouched"
    - "One request builder shared by the playbook fence and both selectors; dedupe per tenant|xdr|command|agent|target, never per run"
    - "Selectors derive the first containment step and build a forced-Suggest request; no step or no host means no row"

key-files:
  created:
    - backend/tests/test_autonomous_ops_xdr_fence.py
  modified:
    - backend/playbook_engine_actions.py
    - backend/playbook_engine_execution.py
    - backend/correlation_engine_threat.py
    - backend/backend_safety.py

key-decisions:
  - "A step's gate_class key reaches the fence through context['_current_step'], set in _execute_action just before the handler runs (handlers only receive resolved params); the fence reads it before its first await, so parallel steps cannot interleave"
  - "Step outputs for automatic executors use messages.ACTION_LABELS wording (for example 'restore files from a snapshot'), so no raw command name containing the word rollback appears in output"
  - "evaluate_action keeps the low-confidence guard (below 0.8 needs a person): confidence can only make the result stricter, never approve; auto_approved is accepted and ignored"
  - "Duplicate and unticked-tenant outcomes return the gate's plain reason text as the step output and write nothing (the gate does not record them)"

patterns-established:
  - "Selector request: first top-level step whose action is one of the four containment verbs; unresolved $variable parameters fall back to the correlation's agent_id / source_ip / process.path"

requirements-completed: [GATE-05, GATE-03]

coverage:
  - id: D1
    description: "XDR auto block_ip at shipped defaults writes zero response tasks and one shadow row (origin xdr-auto, dispatcher response_task); with shadow off it writes one stamped task whose autonomy.actionId equals the row id"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_tracer_xdr_block_ip_at_defaults_is_a_simulation"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_xdr_block_ip_with_shadow_off_writes_one_stamped_task"
        status: pass
    human_judgment: false
  - id: D2
    description: "isolate_endpoint and rollback_ransomware from an automatic executor become awaiting_approval cards; the engine's own approval path is not entered; a gate_class approve step raises block_ip to a card"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_isolate_and_rollback_from_an_automatic_executor_become_approval_cards"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_a_playbook_step_with_gate_class_approve_raises_block_ip_to_an_approval_card"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unticked tenant leaves no task and no row; a repeat correlation for the same target adds no second row; a full execute_playbook run with xdr-auto at defaults writes no response task"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_unticked_tenant_leaves_no_task_and_no_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_a_full_xdr_playbook_run_at_defaults_writes_no_response_task"
        status: pass
    human_judgment: false
  - id: D4
    description: "Manual (human-started) block_ip keeps the PB-BLK- task shape with no autonomy key, the same dedupe, and writes no ledger row"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_manual_block_ip_keeps_the_unstamped_task_shape"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both selectors record only a suggestion (shadow with wouldHave suggest, or state suggested) and never call execute_playbook; notification-only playbooks and a correlation with no agent record nothing; an unticked tenant gets nothing; an AST scan finds no execute_playbook call in correlation_engine_threat"
    requirement: GATE-05
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_ai_selector_records_a_suggestion_and_never_runs_the_playbook"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_fallback_selector_records_a_suggestion_for_an_isolate_step"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_selectors_contain_no_playbook_run_call"
        status: pass
    human_judgment: false
  - id: D6
    description: "evaluate_action('isolate_host' / 'rollback_ransomware', confidence 0.99, auto_approved True) still requires approval; AUTO_APPROVE_CONFIDENCE_THRESHOLD is gone; playbook_engine_safety still imports"
    requirement: GATE-05
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_xdr_fence.py#test_the_confidence_auto_approve_is_gone"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 06: XDR auto-playbook fence, suggest-only selectors, confidence bypass removed Summary

**Automatic playbook runs (xdr-auto, ai-selector, fallback-selector) now pass `gate.decide` on every containment step, so at shipped defaults an XDR correlation is a simulation; the two selectors only record `gate.suggest` rows; the 0.90 confidence auto-approve is deleted; human-started runs are unchanged**

## Accomplishments

- An XDR-triggered `block_ip` step is decided by the gate. At defaults (master shadow on) it leaves one `shadow` row (origin `xdr-auto`, dispatcher `response_task`) and zero `response_tasks`. With shadow off it writes exactly one task through `gate.execute_response_task`, stamped `triggered_by: autonomous_ops` with `autonomy.actionId` linked to the row and `playbook_execution_id` carried over.
- `isolate_endpoint` and `rollback_ransomware` from an automatic executor become approval cards (`class_approve`) with dispatcher `response_task`; the engine's own `_gate_high_risk_action` is never entered. A step carrying `gate_class: approve` raises even `block_ip` to a card (`playbook_raised`).
- The AI selector and the rule-based fallback no longer call `execute_playbook` (an AST test enforces it). Each builds a request from the selected playbook's first containment step and calls `gate.suggest` (origin `ai-selector` / `fallback-selector`), so an LLM-chosen action can only ever wait as a suggestion or an approval card (PROH-81-02).
- `backend_safety.evaluate_action` no longer auto-approves on confidence: constant and branch deleted. Confidence 0.99 with `auto_approved=True` still requires approval.

## The four fenced actions

| Playbook action | Registry command | Registry class | Automatic-executor result |
|---|---|---|---|
| block_ip | block_ip | auto | allow_auto: shadow row at defaults, stamped response task when shadow is off |
| quarantine_file | quarantine_file | auto | same as block_ip |
| isolate_endpoint | isolate_host (alias) | approve | awaiting_approval card, never a task |
| rollback_ransomware | rollback_ransomware | approve | awaiting_approval card, never a task |

## Selector before / after

| | Before | After |
|---|---|---|
| `_ai_select_playbook` | `execute_playbook(... executed_by="ai-selector")` with `auto_approved: True` and the correlation's confidence in the trigger | `gate.suggest` for the first containment step (forced Suggest); notification-only playbook or missing agent id: nothing recorded, info log |
| `_fallback_select_playbook` | `execute_playbook(... executed_by="fallback-selector")` with `auto_approved: True` | same as above with origin `fallback-selector` |
| Exception chain | AI failure falls back to the rule-based selector | unchanged |

## Grandfathered correlation writers (left for 81-08's structural test)

Still outside the gate by design (A-81-XDR-GRANDFATHERED), all in `backend/correlation_engine_threat.py`:

- `trigger_threat_hunt` - `agent_instructions.insert_many` (hunt instructions)
- `prestage_kill_chain_defenses` - `agent_instructions.insert_many` (monitoring and snapshot verbs such as `create_vss_snapshot`, `run_vss_rollback_check`)
- `broadcast_ioc` (`threat_intel_broadcast`) and `_auto_create_security_case` (`security_cases`) write no agent instruction and no response task.

## Task Commits

1. **Task 1 (tracer): gate fence on the four containment actions** - `45045b8f7` (feat)
2. **Task 2: suggest-only selectors, confidence bypass removed** - `fb93c117f` (feat)

Each task has one commit (plan type is `execute`). RED was observed before each implementation: Task 1 failed at import (`AUTOMATIC_EXECUTORS` missing); Task 2 showed 6 failures before the selector and `backend_safety` changes.

## Files Created/Modified

- `backend/playbook_engine_actions.py` - `AUTOMATIC_EXECUTORS`, `CONTAINMENT_COMMANDS`, `gate_request`, `selector_request`, `_fence_automatic_step`, fence calls in the four actions
- `backend/playbook_engine_execution.py` - one line in `_execute_action`: `context["_current_step"] = step`
- `backend/correlation_engine_threat.py` - both selectors use `gate.suggest`
- `backend/backend_safety.py` - confidence bypass removed
- `backend/tests/test_autonomous_ops_xdr_fence.py` - 20 tests (358 lines)

## Decisions Made

See `key-decisions`. Dedupe follows A-81-XDR-DEDUPE: `tenantId|xdr|command|agentId|target`, so a repeat correlation (or the same target chosen by a selector after `xdr-auto`) does not open a second card or shadow row within the gate's windows.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `playbook_engine_execution.py` edited (not in files_modified)**
- **Found during:** Task 1
- **Issue:** The action handlers receive only resolved `params` and `context`, never the step, so `registry.playbook_raises([step])` (the GATE-04 `gate_class` raise the plan asks for) had no step to read.
- **Fix:** `_execute_action` stores the step in `context["_current_step"]` immediately before awaiting the handler (3 lines including a comment). The context is not persisted, and the manual path ignores the key.
- **Files modified:** `backend/playbook_engine_execution.py`
- **Commit:** `45045b8f7`

**2. [Judgement call] `confidence` is not fully ignored in `evaluate_action`**
- The plan says `auto_approved` and `confidence` are accepted and ignored. `confidence` still feeds the existing guard "below 0.8 needs a person". That guard only makes the result stricter and removing it would loosen a manual-path safety check, so it stays; confidence can never approve anything. `auto_approved` is fully ignored. The docstring says so.

**3. [Process] Task 1's fence code was refactored in Task 2**
- The request-building logic moved from `_fence_automatic_step` into the module-level `gate_request` so the selectors reuse the same rules (the plan's Task 2 `read_first` asks for this reuse). No behaviour change; Task 1's tests passed unchanged.

**Total deviations:** 3 (1 blocking-issue edit, 2 judgement calls). **Impact:** none on the plan's behaviour.

## Issues Encountered

- A verification run of the broad suite exceeds the default 2-minute tool timeout; run in the background.
- Selector requests for `block_ip` need an address; a playbook whose `block_ip` step takes its IP from an unresolved `$variable` falls back to the correlation's `source_ip`. If neither exists, nothing is recorded (info log).

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; T-81-24, T-81-25, T-81-26 and T-81-27 mitigations are implemented and tested.

## User Setup Required

None. Nothing was deployed, restarted or migrated, and no live database was touched (all tests use throwaway `omni_test_*` databases; the model call is replaced by a fake analyzer). The running backend picks this up on its next restart, which is the user's step; until then the live XDR path still runs the old code.

## Next Phase Readiness

- 81-08's structural test can list `trigger_threat_hunt` and `prestage_kill_chain_defenses` as grandfathered writers and assert that no other code in the repository writes a response task or an autonomous instruction outside `gate.py`.
- Cards created here use dispatcher `response_task`; the approval dispatch (81-04) must write them through `gate.execute_response_task`.
- Verification run: `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_xdr_fence.py backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_gate_order.py -q -p no:cacheprovider` -> 51 passed; `-k "playbook or correlation or soar"` -> 51 passed; `-k "playbook and not autonomous"` -> 26 passed. 0 skipped.

## Self-Check: PASSED

`backend/tests/test_autonomous_ops_xdr_fence.py` exists; commits `45045b8f7` and `fb93c117f` are ancestors of HEAD; acceptance greps re-run (`AUTOMATIC_EXECUTORS` 2, `execute_response_task(` 1, `gate.suggest(` 2, no `execute_playbook` call node in `correlation_engine_threat.py`, `AUTO_APPROVE_CONFIDENCE_THRESHOLD` absent, `backend_safety` and `playbook_engine_safety` import).

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
