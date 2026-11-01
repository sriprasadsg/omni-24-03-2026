---
phase: 83-autonomous-security-response
plan: 08
subsystem: autonomous-ops
tags: [autonomous-ops, dormancy, circuit-breaker, range-block, agent-support, pytest]
status: complete

requires:
  - phase: 83-autonomous-security-response
    provides: "83-01 agent_support.check and the shared contract; 83-05 sweep_security and signals (range candidates); 83-06 gate-only delivery"
provides:
  - "agent_support.gate_step: the gate's dormancy step (capability, then online, then token) for security_response requests"
  - "agent_support.token_for(command, params) and check(..., params=): a network needs block_ip_range"
  - "gate.REASON_CODES agent_unsupported, capability_off, agent_offline, range_block"
  - "approvals: _revalidate re-runs the support check for security_response cards; approve refuses suggestionOnly rows (suggestion_only)"
  - "ledger.BREAKER_FAILURES, BREAKER_IGNORED; recent_finished_auto skips ignored rows"
  - "verify.failure_outcome(doc) -> (state, reason); reason agent_refused"
  - "registry.ActionSpec.cidr_params, protected.check_network, dispatch_check.has_range"
affects: [83-09, 83-10, 83-11, 83-12, 83-13, 83-16, 83-17]

actuals:
  tokens: 14100
  tasks: 3
  commits: 6
plan_head_before: 5c615e75ce7ecf36f301a8246f6e7d5b43f2f307
plan_head_after: 9ec92fca7815456aa3aac487f0d036eb6b6e91c7

tech-stack:
  added: []
  patterns:
    - "A dormant host is refused by the gate with an unrecorded reason, so it leaves no row and cannot reach the breaker"
    - "The breaker filters on reasonCode in the query, so an ignored row is transparent to a run of three"

key-files:
  created:
    - backend/tests/test_autonomous_ops_dormancy.py
    - backend/tests/test_autonomous_ops_range_block.py
  modified:
    - backend/autonomous_ops/agent_support.py
    - backend/autonomous_ops/gate.py
    - backend/autonomous_ops/approvals.py
    - backend/autonomous_ops/ledger.py
    - backend/autonomous_ops/breaker.py
    - backend/autonomous_ops/verify.py
    - backend/autonomous_ops/reconciler.py
    - backend/autonomous_ops/response_messages.py
    - backend/autonomous_ops/registry.py
    - backend/autonomous_ops/protected.py
    - backend/autonomous_ops/dispatch_check.py
    - backend/autonomous_ops/decision_row.py
    - backend/autonomous_ops/sweep_security.py
    - backend/tests/test_autonomous_ops_gate_order.py
    - backend/tests/test_autonomous_ops_breaker.py
    - backend/tests/test_autonomous_ops_reconciler.py

key-decisions:
  - "Final _STEPS order: _step_platform_stop, _step_eligibility, _step_tenant_stop, _step_level, _step_class, _step_protected_targets, agent_support.gate_step, _step_blast_radius, _step_dedupe, _step_shadow."
  - "Breaker counts: undone, rolled_back, a failed row with no reasonCode (Phase 81), and failed rows with verify_failed, agent_failed or blocked_by_local_security. Ignored (transparent): not_delivered, no_result, capability_off, agent_unsupported, agent_offline, hash_mismatch, protected_path, agent_refused, locked, dispatch_failed."
  - "A range escalates in _step_class after the other class checks, so a first-come needs_approval code (class_approve, playbook_raised) keeps its own reason and range_block applies when nothing else did."

requirements-completed: []

coverage:
  - id: D1
    description: "A security_response request for a host without the capability tick, the token, or online is refused by the gate with capability_off, agent_unsupported or agent_offline, records nothing, and the order of the reasons is stable; a 2.1.15 agent (no token) stays dormant; missing or malformed tokens read as no support; 5 minutes is online and 5 minutes 1 second is not"
    requirement: "RESP-10"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_dormant_host_is_refused_by_the_gate_and_leaves_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_missing_or_malformed_tokens_read_as_no_support"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_2_1_15_agent_stays_dormant_because_support_is_read_from_tokens_not_versions"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_five_minutes_is_online_and_one_second_more_is_offline"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_the_reason_shown_is_stable_capability_then_online_then_token"
        status: pass
  - id: D2
    description: "Phase 81 requests and suggestions skip the step; the step sits right after the protected-target step"
    requirement: "RESP-10"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_phase_81_request_is_decided_exactly_as_before"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate_order.py#test_the_steps_run_in_the_decision_order_with_agent_support_after_the_protected_targets"
        status: pass
  - id: D3
    description: "A card approved later is re-checked: lost token, offline, or a tick removed end refused with that reason and write no instruction; a suggestion-only row is refused before the compare-and-set and the route answers 409 with the API_DETAIL text; a Phase 81 suggestion still approves"
    requirement: "RESP-10"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_card_whose_agent_lost_its_token_before_approval_ends_refused"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_tick_removed_between_decision_and_approval_is_caught_at_approval"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_the_route_answers_409_with_the_api_text_for_a_suggestion_only_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_phase_81_suggestion_without_the_marker_can_still_be_approved"
        status: pass
  - id: D4
    description: "The breaker counts only real failures; plumbing and safeguard endings neither count nor break a run of three; three undone rows still trip; a failed row with no reason still counts"
    requirement: "RESP-10"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_breaker.py#test_plumbing_failures_never_trip_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_breaker.py#test_an_ignored_row_neither_counts_nor_breaks_a_run_of_three"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_breaker.py#test_three_real_failures_trip_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_three_dormant_endings_in_a_row_never_lower_the_level"
        status: pass
  - id: D5
    description: "Each ending has its own name: hash_mismatch, protected_path and a refused target end refused; blocked_by_local_security and locked end failed; a capability hold-back ends failed capability_off; everything else agent_failed; Phase 81 rows keep agent_failed"
    requirement: "RESP-10"
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_failure_outcome_names_each_ending"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_the_reconciler_names_each_ending_for_a_security_response_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_dormancy.py#test_a_phase_81_row_keeps_agent_failed_whatever_the_result_says"
        status: pass
  - id: D6
    description: "A request naming a cidr always needs approval at the gate (range_block) from any origin and with playbook_raise unset; a malformed network is invalid_target, an overlap with any never-touch IP or network is protected_target, at decide and at approval"
    requirement: "RESP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_range_block.py#test_a_range_needs_approval_from_any_origin_and_nothing_is_sent"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_range_block.py#test_a_network_overlapping_a_never_touch_entry_is_protected"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_range_block.py#test_a_card_is_refused_if_a_never_touch_entry_now_covers_the_network"
        status: pass
  - id: D7
    description: "The sweep turns a corroborated range into one card and no instruction, one origin into a suggestion, stays silent for a host without block_ip_range; approving sends block_ip with cidr and undo sends unblock_ip with cidr and the block's id"
    requirement: "RESP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_range_block.py#test_one_tick_turns_a_corroborated_range_into_one_card_and_sends_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_range_block.py#test_approving_sends_block_ip_with_the_network_and_undo_names_the_same_network_and_block"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_range_block.py#test_the_sweep_leaves_no_row_for_a_range_on_a_host_without_the_range_token"
        status: pass
---

# Phase 83 Plan 08: Dormancy, an honest breaker and range blocks Summary

**A host that cannot carry an action stays silent in the sweep, the gate and at approval; only real failures lower a tenant's level; a block of a whole network always waits for a person.**

## Commits

TDD, RED then GREEN per task: `8a829e077` / `d7d98d3dd` (dormancy and approval re-check), `8ded2f18f` / `c39607261` (breaker and failure names), `0b6aa03f1` / `9ec92fca7` (range blocks). `commits: 6` is measured from the ledger base `5c615e75c`.

## What each RED run was

- Task 1: 25 of 28 cases failed on behaviour (the gate decided and recorded a row for a dormant host). Not an ImportError.
- Task 2: 26 failed. Of those, the `failure_outcome` cases and the constants test failed on a missing name (AttributeError), because the names did not exist yet; the plumbing, ignored-run and reconciler cases failed on behaviour.
- Task 3: 27 of 30 failed. `check_network`, `cidr_params`, `has_range` and `BREAKER_*`-style cases failed on a missing name; the gate, approval and sweep cases failed on behaviour. The sweep cases were already observing the range (`observed: 1`) and deciding nothing.

## Final step order and breaker codes

`_STEPS`: platform stop, eligibility, tenant stop, level, class, protected targets, **agent support (`agent_support.gate_step`)**, blast radius, dedupe, shadow.

Counted: undone, rolled_back, failed with no reasonCode (Phase 81), failed with `verify_failed`, `agent_failed`, `blocked_by_local_security`.
Ignored: `not_delivered`, `no_result`, `capability_off`, `agent_unsupported`, `agent_offline`, `hash_mismatch`, `protected_path`, `agent_refused`, `locked`, `dispatch_failed`.

## Deviations from Plan

**1. [Rule 2 - Missing critical] `protected_path` and `agent_refused` added to the ignored list.** The plan's list had `hash_mismatch` but the same task makes `protected_path` and a host-refused target end `refused`. A refused row is not a bad state, so left in the query it would break a run of three, and it is the safeguard working. Both are transparent.
**2. [Rule 1 - Conflicting test] A Phase 81 reconciler test was edited.** `test_three_no_result_failures_trip_the_breaker` (test_autonomous_ops_reconciler.py) asserted the opposite of this plan's required behaviour (no_result is transparent). It now uses three host-reported failures to trip the breaker, and a new test asserts three no_result rows do not. The plan's "added cases only" rule was about the breaker tests file; none of its lines were edited.
**3. [Rule 3] `agent_support` imports `dispatch_check` and `registry`.** Needed for `gate_step` and `token_for`; no import cycle (checked by the full run).
**4. Range wording.** `display_target` and `undo_block` in `decision_row.py` also read `cidr_params`, so a range row shows its network as its target and its undo carries `{cidr, block_id}` (the plan named only `undo_block`).
**5. Approval check uses the first target only** (`targets[0]`, the one that is dispatched), not every target; all other targets are still protected-checked.
**6. `_step_class` restructured** from early returns to if/elif so the range escalation can follow. Behaviour for non-range requests is unchanged (the whole suite passes).
**7. The route needed no change.** `_decision_error` already maps a refused reason through `API_DETAIL`, so `suggestion_only` answers 409 with 83-03's sentence.

## Verification

Task commands all pass. The whole `backend/tests/test_autonomous_ops_*.py` set ran once on the private mongod at 127.0.0.1:27998 after the last commit: **773 passed, 0 skipped**. `test_catalogue_route_parity.py` and the other suites were not run (nothing in them depends on this plan; no route changed). No Rust and no cargo in this plan, so the cargo recipe was not used. No agent was run and nothing was deployed or published.

## Facts for later plans

- `gate.decide` now refuses `security_response` requests unrecorded for dormant hosts: `agent_unsupported`, `capability_off`, `agent_offline`. Any plan that calls the gate for a security action (83-09 restart, 83-10 isolation, 83-11 quarantine) gets the dormancy check for free; its test agents need `seed_response_agent` with the right token and a recent `lastSeen`, and the `security_response` dispatcher registered (import `response_dispatch`).
- `agent_support.token_for("block_ip", {"cidr": ...})` is `block_ip_range`; other commands ignore `cidr`.
- `ledger.recent_finished_auto` skips rows by reasonCode, so a plan that ends a row for a new plumbing reason must add the code to `BREAKER_IGNORED`.
- `verify.failure_outcome` reads the instruction's `status` and `result.outcome`; `healthy_after` and `still_running` are still not written into `row.result` (restart and kill plans must do that).
- A range card's reason text comes from `REASON_TEXT["range_block"]` (83-03) unless a plan adds `range_block` to `decision_row._OWN_WORDS`.

## User-visible sentences not worded by the UI-SPEC

- New: `The computer refused this target, so nothing was changed.` (`agent_refused`, in response_messages.py)
- Existing from 83-03, now shown on a real card, please read: `The request named a range of addresses. Only a single IP address is blocked automatically.` (`range_block`). It reads as a refusal although it now sits on an approval card; consider rewording.

## Not read / limits

Not read: 83-RESEARCH.md beyond the Pitfall 2, Open Question 7 and range lines found by search, 83-UI-SPEC.md beyond a search for range wording, 83-01-SUMMARY.md and 83-05-SUMMARY.md (relied on the run notes and the code), PROJECT.md, config.json, the skills directory. The CONTEXT decisions D-01..D-28 and the research defaults were read. The pre-existing `test_catalogue_route_parity.py::test_ledger_ratchets` failure was not touched or run.

## Self-Check: PASSED
