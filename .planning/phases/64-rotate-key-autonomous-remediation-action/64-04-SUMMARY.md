---
phase: 64-rotate-key-autonomous-remediation-action
plan: 04
subsystem: agent
tags: [rust, ssh-key, remediation, dispatch, agent-install/omni-agent-rs, python, playbook]

# Dependency graph
requires:
  - phase: 64-01
    provides: rotate_key.yaml playbook + ACTION_MAP routing (fingerprint added to ingest set_fields)
  - phase: 64-03
    provides: ssh_key_rotation::rotate_in_place/rollback_rotation — the destructive rotation mechanics this plan wires up
provides:
  - "rotate_key"/"rotate_key_rollback" dispatch arms in instructions.rs, reachable from a real backend instruction
  - remediation_actions::rotate_key()/rotate_key_rollback() thin async wrappers
  - corrected rotate_key.yaml rollback step (rotate_key_rollback / authorized_keys_path, no longer restore_file / rotate_key_backup_path)
  - compute_instruction_result() — testable pure-dispatch extraction from execute_instruction
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dispatch arm shape: extract from item.get(\"parameters\"), call the remediation_actions wrapper, map Ok/Err to {status: success/error, ...} JSON — identical to every sibling arm (kill_process/restore_file/block_ip/etc.)"
    - "compute_instruction_result(action, raw_action, item, cfg, client) -> Option<Value>: pure dispatch extracted from execute_instruction so arms are testable without a live instructions-result endpoint; None preserves the one legacy early-return case (malformed start-remote-session/desktop-stream strings)"

key-files:
  created:
    - agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
    - agent-install/omni-agent-rs/src/instructions.rs
    - backend/playbooks/rotate_key.yaml
    - backend/tests/test_rotate_key_wiring.py

key-decisions:
  - "Extracted compute_instruction_result (returns Option<Value>) out of the private execute_instruction so the real match-arm dispatcher is directly testable with a constructed instruction item, a fixture authorized_keys file, and no mock HTTP server — execute_instruction was not pub, took cfg/client, and posted its result over the network as a side effect with no return value, none of which the plan's own test approach (\"dispatch through the real dispatcher\") could work around without either a new mock-server dependency or this extraction."
  - "Option<Value> (not Value) preserves the exact pre-refactor behavior for the one arm (legacy \"start remote session\"/\"start desktop stream\" string parsing) that used a bare `return;` to skip both further dispatch and the result-report POST entirely on malformed input — a straight Value-returning refactor would have silently started reporting a synthetic status for that case, a behavior change out of this plan's scope."

requirements-completed: [AUTO-02]

coverage:
  - id: D1
    description: "rotate_key dispatch arm reaches ssh_key_rotation::rotate_in_place and returns {status: success, new_fingerprint, new_comment} with no path/key material in the response"
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: "agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs#dispatch_rotate_key_success_returns_no_path_or_key_material"
        status: pass
    human_judgment: false
  - id: D2
    description: "rotate_key dispatch arm reports a structured error (never a panic) on an unknown fingerprint, and leaves the fixture untouched"
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: "agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs#dispatch_rotate_key_unknown_fingerprint_errors_and_leaves_file_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "rotate_key dispatch arm handles missing parameters ({}) with a structured error, never a panic"
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: "agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs#dispatch_rotate_key_missing_parameters_errors_not_panics"
        status: pass
    human_judgment: false
  - id: D4
    description: "rotate_key_rollback dispatch arm restores a prior rotation byte-for-byte and reports {status: success}"
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: "agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs#dispatch_rotate_key_rollback_restores_byte_for_byte"
        status: pass
    human_judgment: false
  - id: D5
    description: "rotate_key_rollback dispatch arm reports a structured error when there is no prior rotation/snapshot, and leaves the target file untouched"
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: "agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs#dispatch_rotate_key_rollback_without_prior_rotation_errors_and_leaves_file_untouched"
        status: pass
    human_judgment: false
  - id: D6
    description: "rotate_key.yaml's rollback step dispatches action: rotate_key_rollback with only authorized_keys_path (no rotate_key_backup_path reference) — fixes a shipped step that could never resolve its parameters"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "backend/tests/test_rotate_key_wiring.py::test_rotate_key_wiring (Task 6 assertions)"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-08-17
status: complete
---

# Phase 64 Plan 04: Rotate-Key Dispatch Wiring + Rollback Playbook Fix Summary

**Two new instruction-dispatch arms (`rotate_key`/`rotate_key_rollback`) wired straight into `instructions.rs`'s real match statement, backed by thin `remediation_actions.rs` wrappers over plan 64-03's `ssh_key_rotation` mechanics, plus a fix to the already-shipped `rotate_key.yaml` rollback step that referenced a finding field (`rotate_key_backup_path`) nothing in the ingest pipeline ever writes.**

## Performance

- **Duration:** 40 min
- **Completed:** 2026-08-17
- **Tasks:** 1
- **Files modified:** 4 modified, 1 created

## Accomplishments
- `"rotate_key"` and `"rotate_key_rollback"` match arms added to `instructions.rs`, positioned immediately before the `_` fallback, following the exact shape of every sibling arm (`kill_process`/`restore_file`/`block_ip`/`disable_service`/`enable_service`) — extract from `item.get("parameters")`, call the wrapper, map `Ok`/`Err` to `{status, ...}` JSON.
- `remediation_actions::rotate_key(authorized_keys_path, fingerprint)` and `remediation_actions::rotate_key_rollback(authorized_keys_path)` — thin async wrappers over `ssh_key_rotation::rotate_in_place`/`rollback_rotation`, mirroring `restore_file`'s pattern (no `spawn_blocking`, no added validation — the underlying functions already refuse every invalid case).
- The stale `// rotate_key is deferred to backlog (999.2)...` comment removed — replaced with real doc comments on the two new wrapper functions.
- `backend/playbooks/rotate_key.yaml`'s rollback step corrected from `action: restore_file` / `params: {path, backup_path: "{{finding.details.rotate_key_backup_path}}"}` to `action: rotate_key_rollback` / `params: {authorized_keys_path: "{{finding.details.affected_path}}"}` — the field it used to reference is never written anywhere in the ingest pipeline, confirmed directly: the pre-existing `test_rotate_key_wiring.py`'s own Task 5 assertion (`rendered_rollback["authorized_keys_path"]`) was failing with `KeyError` before this fix, contradicting 64-01-SUMMARY.md's claim that "all 5 tests passed."
- `compute_instruction_result()` extracted from `execute_instruction()` as a `pub async fn` returning `Option<Value>` — the real dispatch match statement, now directly callable from a test with a constructed instruction `item` and no live instructions-result HTTP endpoint.
- 5 new integration tests in `agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs` drive the real dispatcher end-to-end against fixture `authorized_keys` files (real freshly-generated Ed25519 keys, never hardcoded): successful rotation with no path/key-material leakage, unknown-fingerprint structured error with untouched fixture, missing-parameters structured error (no panic), rollback byte-for-byte restore after a real rotation, and rollback-without-snapshot structured error with untouched fixture.
- 1 new assertion block (Task 6) added to the existing `backend/tests/test_rotate_key_wiring.py`, confirming the corrected playbook's rollback step shape via the real `remediation_playbook_service`/`_render_step_params` path.

## Task Commits

1. **Task 1: Dispatch arms, wrapper functions, and rollback playbook fix** - `4605df7f` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` - added `rotate_key`/`rotate_key_rollback` wrappers, removed stale deferred comment
- `agent-install/omni-agent-rs/src/instructions.rs` - added the two new dispatch arms; extracted `compute_instruction_result` for testability
- `backend/playbooks/rotate_key.yaml` - rollback step corrected to `rotate_key_rollback`/`authorized_keys_path`
- `backend/tests/test_rotate_key_wiring.py` - added Task 6 rollback-shape assertions
- `agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs` - new, 5 dispatch-level integration tests

## Decisions Made
- Extracted `compute_instruction_result` (see key-decisions above) rather than adding a mock-HTTP-server dev-dependency to test `execute_instruction` directly — a pure, behavior-preserving refactor of existing logic, not a new pattern or architectural change.
- `Option<Value>` return type (not `Value`) to exactly preserve the one pre-existing early-return case (malformed "start remote session"/"start desktop stream" legacy string parsing) rather than changing its reporting behavior as an incidental side effect of the extraction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extracted `compute_instruction_result` from `execute_instruction` to make the dispatch arms testable**
- **Found during:** Task 1, writing the integration tests
- **Issue:** The plan's own test approach ("dispatching through instructions.rs's top-level handler") required calling the real match statement, but `execute_instruction` was private, required `Config`/`reqwest::Client`, returned `()` (no way to inspect the computed result), and posted its result over the network as its only observable side effect — none of which is testable without either a new mock-HTTP-server dev-dependency (out of scope, would need a package-install checkpoint) or extracting the pure computation.
- **Fix:** Split `execute_instruction` into `compute_instruction_result` (the match statement, `pub`, returns `Option<Value>`) and a thinner `execute_instruction` that calls it and does the report POST. Also fixed the resulting `E0069` compile error (a `return;` inside a match arm whose enclosing function now returns `Option<Value>`, not `()`) by converting to `return None;`, matched by an `Option<Value>` return type on `compute_instruction_result` so the one legacy early-return case (malformed remote-session strings) keeps its exact original silent-skip behavior rather than incidentally starting to report a synthetic status.
- **Files modified:** `agent-install/omni-agent-rs/src/instructions.rs`
- **Verification:** `cargo check --lib` clean; `cargo test --lib` 83/83; `cargo test rotate_key` 34/34 (29 from plan 64-03 + 5 new dispatch tests); full `cargo test` shows the identical 7 pre-existing `tests/integration.rs` failures documented in `deferred-items.md` item 1, no new failures.
- **Committed in:** `4605df7f` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking)
**Impact on plan:** Necessary to make the plan's own test approach viable without adding a new test dependency or changing unrelated arm behavior. No scope creep — every other arm's match logic is byte-for-byte unchanged, only relocated.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `rotate_key`/`rotate_key_rollback` are now fully reachable end-to-end: vulnerability finding → `select_playbook` → `rotate_key.yaml` → instruction dispatch → `instructions.rs`'s real match arm → `remediation_actions::rotate_key`/`rotate_key_rollback` → `ssh_key_rotation::rotate_in_place`/`rollback_rotation`, and (on failure) the corrected rollback step can now actually resolve its one parameter from the finding document.
- Two pre-existing, unrelated conditions remain tracked in `deferred-items.md` (stale `CapabilityManager` count test in `tests/integration.rs`; `naughtyfy` Windows cross-compile scoping) — neither touched by this plan, confirmed via grep/error-diff against the documented baseline.
- This closes out Phase 64's Wave 3 (plan 64-04, `depends_on: ["64-01", "64-03"]`) — AUTO-02 is now fully delivered across ingestion, routing, agent-side mechanics, and dispatch wiring.

---
*Phase: 64-rotate-key-autonomous-remediation-action*
*Completed: 2026-08-17*

## Self-Check: PASSED
- FOUND: agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs
- FOUND: .planning/phases/64-rotate-key-autonomous-remediation-action/64-04-SUMMARY.md
- FOUND commit: 4605df7f (Task 1)
- FOUND commit: 110507b2 (SUMMARY)
