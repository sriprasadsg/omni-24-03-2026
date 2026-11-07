---
phase: 84-staged-patch-rollouts
plan: 25
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, health-gate, service-watch, rust-agent, contract, gap-closure, cr-03]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-08 services signal, 84-11 service_state heartbeat block, 84-23 held canary lines, 84-27 in-flight send paths
provides:
  - Health::Absent and the token "absent" in meta.service_state (Linux LoadState not-found or masked, Windows sc error 1060)
  - signals.service_baseline / read_service_baseline / record_service_baseline
  - host fields servicesPresentBefore / servicesAbsentBefore (pre-change baseline, merged with $addToSet)
  - signals._from_block absent rule: absent before and after leaves the host's wanted list; present before fails; no record is no data
affects: [84-26, 84-28, 84-29]

requirements-completed: [PTCH-02, PTCH-04]

actuals:
  tokens: 5200
  tasks: 3
  commits: 3
commits: 3
plan_head_before: c34c9360ca21708824e2833b5e86377da68f50df
plan_head_after: 03c9d443e0bfc661a4faed29c6e3ca4e61677cf9

tech-stack:
  added: []
  patterns:
    - "an additive heartbeat token the platform judges against a baseline recorded at dispatch, instead of the agent guessing what the host should have"
    - "a best-effort write on a send path: read before the send, write only after a queued result, errors logged once and never ending the send"

key-files:
  created:
    - backend/tests/test_patch_rollout_baseline.py
  modified:
    - agent-install/omni-agent-rs/src/capabilities/service_watch.rs
    - agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
    - shared/agent-response-contract.json
    - backend/autonomous_ops/rollout/signals.py
    - backend/autonomous_ops/rollout/dispatcher.py
    - backend/autonomous_ops/rollout/installs.py
    - backend/tests/test_patch_rollout_health.py
    - backend/tests/test_patch_rollout_contract.py

key-decisions:
  - "KD-84-G2: a unit the computer does not have is reported with the new additive token `absent` (not `unknown`, which would read as no data and halt then revert a healthy ring) and is judged by the backend against the host's pre-change baseline: absent before and after leaves that host's wanted list, present before and absent after fails the services signal, no record is no data. Reversibility: costly once agent 2.1.17 is published; free until then."
  - "The pre-change baseline is the agent's last service_state block read just before gate.execute and written to the rollout host row only when the send is queued; the write merges ($addToSet) so a later attempt cannot hide an earlier presence; read and write errors are logged and read as no baseline (fail closed)."
  - "Windows sc query now goes through privileged::run_status so the exit code is visible; only exit 1060 is absent, every other non-zero exit stays unknown."

coverage:
  - id: D1
    description: "A systemd unit that is not found or masked is reported absent, never stopped; a loaded stopped or failed unit is judged as before"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "service_watch.rs#a_not_found_or_masked_unit_is_absent_and_a_loaded_one_is_judged_as_before"
        status: pass
      - kind: unit
        ref: "service_watch.rs#an_absent_service_is_never_a_failure_and_is_reported_absent_in_the_state"
        status: pass
    human_judgment: false
  - id: D2
    description: "A Windows service that does not exist (sc error 1060) is absent; any other sc failure stays unknown; the contract lists the token"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "service_watch.rs#windows_error_1060_is_absent_and_any_other_sc_failure_is_unknown"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_contract.py#test_the_service_state_heartbeat_shape"
        status: pass
    human_judgment: false
  - id: D3
    description: "The health gate drops a service absent before and after, fails one the change removed, reads no record as no data, and reads all-dropped as agent-only"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_a_service_absent_before_and_after_the_change_leaves_the_wanted_list"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_a_service_the_change_removed_fails_and_a_name_in_both_baseline_lists_counts_as_present"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_when_every_watched_service_was_absent_before_and_after_only_the_agent_is_checked"
        status: pass
    human_judgment: false
  - id: D4
    description: "A queued install (automatic canary or approved line) records the baseline on the host row, merged across attempts, never on a refused send, never able to fail the send"
    requirement: PTCH-02
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_baseline.py#test_a_queued_install_records_the_services_the_computer_had_before"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_baseline.py#test_a_send_that_is_not_queued_writes_no_baseline"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_baseline.py#test_a_later_attempt_never_hides_an_earlier_presence"
        status: pass
    human_judgment: false

duration: 30 min
completed: 2026-11-07
---

# Phase 84 Plan 25: absent services and the pre-change baseline Summary

**A unit the computer does not have reads `absent` (systemd LoadState, Windows error 1060) and the rollout health gate judges it against the services the host showed when its install was queued, so a missing service can no longer fail or starve the gate and a service the patch removed still fails it (CR-03).**

## Accomplishments

- Agent: `Health::Absent` / token `absent`. `classify_systemd` reads `LoadState` first (`status_of` now asks for it); `not-found` and `masked` are absent, a loaded unit is classified exactly as before. Absent is never a failure in `report_with`.
- Agent (Windows): `sc query` goes through `privileged::run_status`; exit code 1060 is absent (the number, not localised text), every other non-zero exit stays unknown.
- Contract: `absent` appended to the `service_state` states in `shared/agent-response-contract.json` (additive, `version` unchanged); the Rust and Python contract tests pin it.
- Backend: `signals._from_block` applies the baseline rule, `signals.read` passes `servicesPresentBefore` / `servicesAbsentBefore` through `_services`; read() still does no database access.
- Backend: `dispatcher.send` (COMMAND_INSTALL rows) and `installs._send` read the baseline just before the send and record it on the rollout host row only on a queued result, after the existing `set_host`. The 84-27 try/except paths are untouched.

## Task Commits

1. Task 1 (tracer): `8eff5e5ea` - Health::Absent for Linux, `_from_block` baseline rule, tests. Tracer verified end to end (Rust `service_` 47 pass, `test_patch_rollout_health.py` 49 pass) before expanding.
2. Task 2: `39bd6c2b2` - baseline helpers, dispatcher and installs wiring, `test_patch_rollout_baseline.py`.
3. Task 3: `03c9d443e` - Windows 1060, contract token, contract tests.

## Verification

- RUST `service_` 48 pass, `response_` 92 pass; windows-gnu `cargo check --lib` finishes with no warning from service_watch.rs.
- Backend: test_patch_rollout_health (49), test_patch_rollout_baseline (10), test_patch_rollout_dispatcher, test_patch_rollout_tracer, test_patch_rollout_gap_lines, test_patch_rollout_gap_inflight (126 passed together before Task 3), test_patch_rollout_contract (30).
- Acceptance greps: LoadState, `"absent"`, `1060`, `servicesPresentBefore`, `servicesAbsentBefore`, `record_service_baseline` in dispatcher.py and installs.py, `addToSet` in signals.py all match; signals.py 199, dispatcher.py 213, installs.py 237 lines.
- RED (Python): the three health tests and four of the baseline tests failed on the planned assertions (`None is True`, missing attribute) before the implementation. Rust tests do not compile before `Health::Absent` exists, so no separate Rust RED run was made.

## Deviations from Plan

**1. [Rule 3 - Blocking/convention] Task 2 tests in a new file**
- **Found during:** Task 2
- **Issue:** `test_patch_rollout_health.py` was 420 lines and Task 1 plus Task 2 tests would pass the 500-line project limit (CLAUDE.md).
- **Fix:** Task 1 unit tests stay in `test_patch_rollout_health.py` (now 461 lines); Task 2 integration tests are in the new `backend/tests/test_patch_rollout_baseline.py`.
- **Commit:** 39bd6c2b2

**2. [Rule 2 - Missing coverage] Windows 1060 uses run_status, not run_output**
- **Found during:** Task 3
- **Issue:** `run_output` drops the exit code on failure (it only keeps stderr text), so error 1060 could not be read as a number.
- **Fix:** the Windows query uses `privileged::run_status`, which the test seam already supports (`fail_exit`).
- **Commit:** 03c9d443e

**3. [Ordering] The working-tree edit to service_watch.rs covered Tasks 1 and 3 at once**
- The Windows hunks were held back from the Task 1 commit and committed with Task 3 (the full file was restored from a copy), so each commit is green on its own.

**Total deviations:** 3 (1 convention, 1 implementation detail, 1 ordering). **Impact:** none on behavior.

## Working-tree notes

- No user-dirty agent file was edited or staged (mod.rs, screen_capture.rs and the others in the context list are untouched by these commits; `git show --name-only` of the three commits lists none of them).
- No version bump, no publish, no restart, no migration, no push. No `Co-Authored-By` trailer.
- `requirements.mark-complete` was not run (84 stays Gaps Found until re-verification; 84-28 and 84-29 still declare PTCH-02 and PTCH-04).

## Known Stubs

None.

## Threat Flags

None. The new fields are written only by the backend on a queued send, and the `absent` token can only remove a name for a host that also reported it absent before the change (T-84-70).

## Self-Check: PASSED

- Files exist: service_watch.rs, service_watch_tests.rs, response_contract_tests.rs, shared/agent-response-contract.json, signals.py, dispatcher.py, installs.py, test_patch_rollout_health.py, test_patch_rollout_baseline.py, test_patch_rollout_contract.py.
- Commits found in history: 8eff5e5ea, 39bd6c2b2, 03c9d443e.
