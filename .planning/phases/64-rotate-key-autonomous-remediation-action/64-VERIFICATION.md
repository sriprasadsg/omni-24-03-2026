---
phase: 64-rotate-key-autonomous-remediation-action
verified: 2026-08-14T20:45:00Z
status: gaps_found
score: 0/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A weak-SSH-key vuln finding (playbook_ref rotate_key AND a non-empty fingerprint) is routed by select_playbook() to the rotate_key playbook"
    status: partial
    reason: "Backend routing logic is present, but the agent-side scanner does not generate weak-key findings. Additionally, the test for backend wiring (test_rotate_key_wiring.py) fails."
    artifacts:
      - path: "backend/tests/test_rotate_key_wiring.py"
        issue: "Test fails with KeyError for 'authorized_keys_path' in rollback params. The playbook's rollback action uses 'restore_file' with 'backup_path', while the test expects 'authorized_keys_path' which is not rendered."
      - path: "agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs"
        issue: "Missing integration of weak-key detection from ssh_key_checks.rs. 'check_authorized_keys' and 'weak_key_finding' functions are absent."
  - truth: "The fingerprint field the agent scanner emits survives agent_vuln_ingest_service ingestion onto the db.vulnerabilities document"
    status: partial
    reason: "Ingestion service correctly handles 'fingerprint', but the agent scanner does not emit findings with this field because the integration is missing."
    artifacts:
      - path: "agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs"
        issue: "Missing integration of weak-key detection, thus no findings with fingerprint are emitted."
  - truth: "Rendering rotate_key.yaml's step params against that persisted finding yields a non-null fingerprint AND a non-null authorized_keys_path"
    status: partial
    reason: "Main step params render correctly. Rollback step params fail to render 'authorized_keys_path' due to mismatch between playbook and test expectation regarding 'restore_file' action and its parameters."
    artifacts:
      - path: "backend/tests/test_rotate_key_wiring.py"
        issue: "Test fails for rollback params."
      - path: "backend/playbooks/rotate_key.yaml"
        issue: "Rollback action is 'restore_file' with 'backup_path', which differs from 'rotate_key_rollback' action mentioned in the plan and expected by the test."
  - truth: "rotate_key.yaml declares finding_class vuln, a destructive step, and a non-empty rollback list"
    status: partial
    reason: "The playbook declares 'vuln' and a destructive step. It has a non-empty rollback list using 'restore_file', but this is inconsistent with the 'rotate_key_rollback' action expected by the plan and tests."
    artifacts:
      - path: "backend/playbooks/rotate_key.yaml"
        issue: "Rollback action 'restore_file' used instead of 'rotate_key_rollback' as implicitly expected by the plan/tests."
      - path: "backend/remediation_playbook_service.py"
        issue: "'rotate_key_rollback' is defined in ACTION_MAP but not used in the playbook's rollback."
missing:
  - "Implement unit tests for `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs`."
  - "Integrate weak-key detection (calling `ssh_key_checks` functions) into `agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs`."
  - "Create `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs`."
  - "Implement `rotate_key` action in `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` and remove the deferred comment."
  - "Fix `backend/tests/test_rotate_key_wiring.py` failure, aligning playbook rollback parameters and action with test expectations and planned `rotate_key_rollback` action."
---

# Phase 64: rotate_key autonomous-remediation action Verification Report

**Phase Goal:** [Promoted from backlog 999.2, deferred from Phase 53 by review] Add a `rotate_key` autonomous-remediation action (agent command + playbook) with a concrete, tested, reversible allowlisted target set. Original scope was under-specified + dangerous + hard to make reversible — the four reversible actions (kill/restore/block/disable) are now proven in production, so this is ready to plan properly.
**Verified:** 2026-08-14T20:45:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | A weak-SSH-key vuln finding is routed by select_playbook() to the rotate_key playbook | ✗ FAILED   | Backend routing exists, but agent scanner doesn't generate findings. Wiring test fails for rollback. |
| 2   | The fingerprint field the agent scanner emits survives agent_vuln_ingest_service ingestion | ✗ FAILED   | Ingestion handles fingerprint, but scanner doesn't emit it. |
| 3   | Rendering rotate_key.yaml's step params yields a non-null fingerprint AND a non-null authorized_keys_path | ✗ FAILED   | Main step renders, but rollback params fail due to playbook/test mismatch. |
| 4   | rotate_key.yaml declares finding_class vuln, a destructive step, and a non-empty rollback list | ✗ FAILED   | Playbook declares vuln/destructive. Rollback uses 'restore_file', not planned 'rotate_key_rollback'. |

**Score:** 0/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/playbooks/rotate_key.yaml` | New playbook for key rotation | ✓ VERIFIED | File exists with expected structure, but rollback action is `restore_file` not `rotate_key_rollback`. |
| `backend/remediation_playbook_service.py` | Updates for `ACTION_MAP` and `select_playbook` | ✓ VERIFIED | `ACTION_MAP` contains `rotate_key` and `rotate_key_rollback`. `select_playbook` includes fingerprint check. |
| `backend/agent_vuln_ingest_service.py` | `fingerprint` added to `set_fields` | ✓ VERIFIED | `fingerprint` added to `set_fields`. |
| `backend/tests/test_rotate_key_wiring.py` | Hermetic wiring test | ✗ FAILED | Test fails with `KeyError: 'authorized_keys_path'` on rollback params. |
| `agent-install/omni-agent-rs/Cargo.toml` | `ssh-key` dependency | ✓ VERIFIED | `ssh-key` 0.6.7 added. |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` | Weak-key parsing and predicate | ✓ VERIFIED | File exists with expected logic, but missing unit tests. |
| `agent-install/omni-agent-rs/src/capabilities/mod.rs` | Module declaration for `ssh_key_checks` | ✓ VERIFIED | `ssh_key_checks` module declared. |
| `agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs` | Integration of weak-key check | ✗ MISSING | `check_authorized_keys` and `weak_key_finding` functions are missing. No call in `scan_misconfigurations`. |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs` | Key rotation mechanics | ✗ MISSING | File does not exist. |
| `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` | `rotate_key` action implementation | ✗ STUB | `rotate_key` action is still commented as deferred. |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `select_playbook()` vuln branch | `by_name['rotate_key']` | Python if/elif chain | ✓ WIRED | Logic present in `remediation_playbook_service.py`. |
| `agent_vuln_ingest_service set_fields['fingerprint']` | `{{finding.details.fingerprint}}` template | Ingestion -> Playbook | ✓ WIRED | Ingestion field and template exist, but agent doesn't emit. |
| `ACTION_MAP['rotate_key']` | `validate()` acceptance | `load_default_playbooks()` | ✓ WIRED | `ACTION_MAP` entries exist, but `rotate_key_rollback` in playbook rollback is inconsistent. |
| `scan_misconfigurations()` | `check_authorized_keys()` | New call site | ✗ NOT_WIRED | `check_authorized_keys` is not implemented/called. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` | 292 | `// rotate_key is deferred to backlog` | 🛑 BLOCKER | Indicates `rotate_key` is not implemented. |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` | - | Missing unit tests | ⚠️ WARNING | Code exists but lacks direct validation as per plan. |

### Gaps Summary

Phase 64 is **not complete**. The core goal of adding a `rotate_key` autonomous-remediation action is not achieved. While some backend plumbing for routing `rotate_key` playbook exists and `rotate_key.yaml` has been created, critical agent-side components are missing or incomplete.

Specifically:
1.  **Backend Wiring Test Failure**: The `test_rotate_key_wiring.py` test fails. This is due to an inconsistency between the `rotate_key.yaml` playbook's rollback step (which uses `restore_file` with `backup_path`) and the test's expectation of `authorized_keys_path`. Furthermore, the plan implies `rotate_key_rollback` action should be used for rollback, which is not the case in the playbook.
2.  **Missing Agent-Side Detection Integration**: The `ssh_key_checks.rs` module exists but lacks its dedicated unit tests. More critically, the weak-key detection logic implemented in `ssh_key_checks.rs` has not been integrated into `vulnerability_scan.rs`, meaning the agent will not generate `rotate_key` findings.
3.  **Missing Agent-Side Rotation Mechanics**: The `ssh_key_rotation.rs` file, which should contain the actual key rotation logic, is entirely missing. The `remediation_actions.rs` file still shows `rotate_key` as deferred, indicating the action itself is not implemented in the agent.

These gaps indicate that the phase is far from complete and cannot be considered passed.

---
_Verified: 2026-08-14T20:45:00Z_
_Verifier: Claude (gsd-verifier)_
