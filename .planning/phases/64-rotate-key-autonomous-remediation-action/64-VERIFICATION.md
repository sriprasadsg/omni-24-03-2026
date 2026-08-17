---
phase: 64-rotate-key-autonomous-remediation-action
verified: 2026-08-17T20:45:00Z
status: gaps_found
score: 19/25 must-haves verified
behavior_unverified: 2
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 0/4
  gaps_closed:
    - "ssh_key_rotation.rs created — full rotation mechanics (target selection, lockout refusal, snapshot/rollback, atomic write, Ed25519 keygen, grounded re-verify), 29/29 tests passing"
    - "remediation_actions.rs rotate_key()/rotate_key_rollback() implemented — the 'deferred to backlog' comment is gone"
    - "instructions.rs 'rotate_key'/'rotate_key_rollback' dispatch arms added and reachable through the real match statement (5/5 integration tests passing)"
    - "rotate_key.yaml rollback step corrected from restore_file/backup_path (which could never resolve — rotate_key_backup_path is never written by the ingest pipeline) to rotate_key_rollback/authorized_keys_path"
    - "backend/tests/test_rotate_key_wiring.py now passes in full (previously failed with KeyError on the rollback params)"
  gaps_remaining:
    - "ssh_key_checks.rs has zero unit tests — plan 64-02's own acceptance criteria required 8; none exist (no #[cfg(test)] module in the file at all)"
    - "vulnerability_scan.rs was never integrated with ssh_key_checks — check_authorized_keys()/weak_key_finding() do not exist anywhere in the codebase, and scan_misconfigurations() never calls into the weak-key parser. The agent scanner cannot detect a weak SSH key or emit a rotate_key finding."
  regressions: []
gaps:
  - truth: "The scanner emits one finding per weak key carrying playbook_ref rotate_key, a SHA256-format fingerprint, and the exact authorized_keys file path it was found in (D-03, D-04) [64-02 must_haves.truths]"
    status: failed
    reason: "check_authorized_keys() and weak_key_finding() — the two functions plan 64-02 Task 2 specified — do not exist anywhere in agent-install/omni-agent-rs/src/. scan_misconfigurations() only calls check_sshd() and check_listening_ports(); it never calls into ssh_key_checks. grep across the whole src/ tree for 'check_authorized_keys' and 'weak_key_finding' returns zero hits. 64-02-SUMMARY.md's claim ('Modified vulnerability_scan.rs to include check_authorized_keys and emit weak_key_finding. All tests for ssh_key_checks and vulnerability_scan passed.') does not match the codebase — no such modification exists, and `cargo test vulnerability_scan` runs the same 11 pre-existing tests with none related to weak-key detection."
    artifacts:
      - path: "agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs"
        issue: "No check_authorized_keys() function, no weak_key_finding() function, no call site inside scan_misconfigurations(). The module has no reference to ssh_key_checks at all."
    missing:
      - "fn check_authorized_keys() -> Vec<Value> in vulnerability_scan.rs, calling ssh_key_checks::authorized_keys_paths() + parse_authorized_keys() and emitting one finding per weak entry"
      - "fn weak_key_finding(...) -> Value emitting {type: misconfig, cve_id: null, severity: HIGH, affected_path, fingerprint, remediation_hint, playbook_ref: rotate_key, detail} with no key body/private material"
      - "A call to check_authorized_keys() inside scan_misconfigurations(), alongside check_sshd/check_listening_ports"
      - "The 5 behavior tests plan 64-02 Task 2 specified (single finding + fingerprint match, playbook_ref/type/affected_path/cve_id shape, two distinct-detail findings for two weak keys, no key-body leak in serialized finding, no findings for strong-only or unreadable input)"
  - truth: "Malformed/weak-key classification logic in ssh_key_checks.rs is validated by its own dedicated unit tests (RSA<2048 weak, DSA weak-by-type, Ed25519/strong-RSA not weak, malformed lines skipped, options-prefix preserved, path guard correctness, empty-input handling) [64-02 must_haves + Task 1 acceptance criteria]"
    status: partial
    reason: "ssh_key_checks.rs has zero tests (no #[cfg(test)] module at all — `cargo test ssh_key_checks` selects 0 tests). The underlying weak_reason_for() DSA-detection path is exercised indirectly and passes through plan 64-03's ssh_key_rotation_tests.rs (rotate_key_verify_rotation_grounded_fails_when_new_entry_is_weak uses a real DSA fixture), which gives real behavioral evidence for the DSA branch specifically. The RSA-bit-threshold branch, the malformed/truncated-line skip behavior, the options-prefix parsing, and is_authorized_keys_path's guard logic have no test coverage anywhere, direct or indirect. Also missing: the module doc comment plan 64-02 Task 1 required (module state, scope boundaries, shared-predicate warning)."
    artifacts:
      - path: "agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs"
        issue: "No #[cfg(test)] mod tests block; no module-level doc comment. 132 lines, all production code, 0 test lines."
    missing:
      - "8 unit tests per plan 64-02 Task 1's <behavior> block: RSA-1024-weak/RSA-2048-not-weak, DSA-weak-by-type, Ed25519-not-weak, malformed-line-skip, options-prefix-preserved, fingerprint-stability, is_authorized_keys_path accept/reject matrix, empty-input-returns-empty-vec"
      - "Module doc comment stating the shared-predicate contract and v1 scope boundaries"
deferred: []
---

# Phase 64: rotate_key autonomous-remediation action Verification Report

**Phase Goal:** Add a `rotate_key` autonomous-remediation action (agent command + playbook) with a concrete, tested, reversible allowlisted target set. (extends AUTO-02)
**Verified:** 2026-08-17T20:45:00Z
**Status:** gaps_found
**Re-verification:** Yes — after gap closure (previous VERIFICATION.md dated 2026-08-14, status gaps_found, score 0/4)

## Important note on this session's bookkeeping fix

Before this verification, the phase had a dual-track collision: a superseded, unshipped-tree planning attempt (`.planning/phases/_superseded-64-vault-legacy-rust-track/`, targets legacy `agent-rust/`) had contaminated ROADMAP.md's completion evidence for the canonical track under verification here. That collision has been corrected (see ROADMAP.md's 2026-08-17 correction note and `SUPERSEDED.md`). This verification evaluates ONLY the canonical `64-rotate-key-autonomous-remediation-action/` track against the shipped `agent-install/omni-agent-rs/` tree, independent of the superseded track's contents, per the task's explicit instruction.

Independent of that dual-track confusion, this verification found a **second, previously undocumented gap** unrelated to the plan-03 bookkeeping issue: **plan 64-02's Task 2 (scanner integration) was never implemented**, despite 64-02-SUMMARY.md and ROADMAP.md's plan list both claiming it was. This gap was flagged once already, in this same directory's prior 2026-08-14 VERIFICATION.md, and was never closed — the plans executed this session (03, 04) closed the rotation-mechanics and dispatch-wiring gaps but did not touch `vulnerability_scan.rs` or add tests to `ssh_key_checks.rs`, so this specific gap survived unchanged from 2026-08-14 to today.

## Goal Achievement

### Observable Truths

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| 1 | 64-01 | Weak-SSH-key vuln finding (playbook_ref rotate_key + fingerprint) routes to rotate_key playbook | ✓ VERIFIED | `test_select_playbook_for_rotate_key_with_fingerprint` passes |
| 2 | 64-01 | fingerprint field survives agent_vuln_ingest_service ingestion | ✓ VERIFIED | `test_rotate_key_wiring` asserts `doc.get("fingerprint")` |
| 3 | 64-01 | Rendering rotate_key.yaml's step params yields non-null fingerprint AND authorized_keys_path | ✓ VERIFIED | `test_rotate_key_wiring` Task 4 assertions pass |
| 4 | 64-01 | playbook_ref rotate_key without fingerprint is NOT routed to rotate_key (mis-routing guard, T-64-04) | ✓ VERIFIED | `test_select_playbook_for_preexisting_secret_finding_without_fingerprint_is_unchanged` + empty-fingerprint variant both pass |
| 5 | 64-01 | rotate_key.yaml declares finding_class vuln, a destructive step, non-empty rollback | ✓ VERIFIED | YAML content confirmed by direct read; `test_destructive_flag_preserved` passes |
| 6 | 64-02 | RSA<2048/DSA classified weak; Ed25519/ECDSA/strong-RSA not weak | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `weak_reason_for()` code present and DSA branch is exercised (and passes) indirectly via `ssh_key_rotation_tests.rs`; no direct test in `ssh_key_checks.rs` (0 tests exist) and RSA-threshold branch has no test evidence at all |
| 7 | 64-02 | Malformed/blank/comment/truncated lines never produce an entry | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `parse_authorized_keys()` code matches the described skip-on-error behavior by inspection; no test exercises it |
| 8 | 64-02 | Scanner emits one finding per weak key with playbook_ref rotate_key, SHA256 fingerprint, exact path | ✗ FAILED | `check_authorized_keys()`/`weak_key_finding()` do not exist; not called from `scan_misconfigurations()`; zero related tests |
| 9 | 64-02 | Two weak keys in one file produce two findings with differing detail strings | ✗ FAILED | No finding-emission code exists to produce any findings at all |
| 10 | 64-02 | No emitted finding contains base64 key body or private key material | ✗ FAILED | Nothing is ever emitted by the scanner — the artifact this truth depends on doesn't exist |
| 11 | 64-02 | Non-Linux/macOS platform: check returns no findings | ✗ FAILED | `authorized_keys_paths()` correctly gates on `#[cfg(unix)]`, but "the check" (`check_authorized_keys`) that this truth is about was never built |
| 12-20 | 64-03 | Fingerprint-exact targeting, lockout refusal, snapshot/rollback byte-for-byte, grounded re-verify, no key material leak, options-prefix preservation, atomic write, comment sanitization (9 truths) | ✓ VERIFIED | All independently re-run: `cargo test ssh_key_rotation` → 29/29 passing; `cargo test --lib` → 83/83 passing |
| 21-25 | 64-04 | rotate_key/rotate_key_rollback dispatch arms reach real mechanics and report structured success/error; rollback playbook step fixed to resolve its only parameter (5 truths) | ✓ VERIFIED | `remediation_dispatch_test.rs` → 5/5 passing; playbook YAML confirmed corrected; `test_rotate_key_wiring.py` Task 6 assertion passes |

**Score:** 19/25 truths verified (2 present, behavior-unverified; 4 failed)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/playbooks/rotate_key.yaml` | rotate_key playbook, rollback resolvable | ✓ VERIFIED | Rollback step is `rotate_key_rollback`/`authorized_keys_path` (fixed by 64-04) |
| `backend/remediation_playbook_service.py` | ACTION_MAP + select_playbook routing | ✓ VERIFIED | Both entries present, fingerprint-conjunct routing confirmed by code read + tests |
| `backend/agent_vuln_ingest_service.py` | fingerprint in set_fields | ✓ VERIFIED | `"fingerprint": f.get("fingerprint"),` present |
| `backend/tests/test_rotate_key_wiring.py` | hermetic wiring test incl. rollback shape | ✓ VERIFIED | Passes (1/1), including Task 6 rollback-shape assertion |
| `backend/tests/test_remediation_playbook.py` | routing + mis-routing regression tests | ✓ VERIFIED | 19/19 passing, mis-routing guard cases present |
| `agent-install/omni-agent-rs/Cargo.toml` | `ssh-key = "0.6.7"` pinned, no `-rc` | ✓ VERIFIED | Confirmed by direct read |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` | weak-key parser + predicate + 8 tests | ⚠️ STUB (tests missing) | All functions present and used downstream by ssh_key_rotation; 0 unit tests; no module doc comment |
| `agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs` | check_authorized_keys/weak_key_finding + integration | ✗ MISSING | Neither function exists; no call site; `scan_misconfigurations()` unchanged from before Phase 64 |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs` | rotation mechanics | ✓ VERIFIED | 397 lines, 29 tests, all passing, independently re-run |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs` | rotation test suite | ✓ VERIFIED | 461 lines, split per plan's own 500-line fallback |
| `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` | rotate_key()/rotate_key_rollback() wrappers | ✓ VERIFIED | Both present; "deferred to backlog" comment removed |
| `agent-install/omni-agent-rs/src/instructions.rs` | rotate_key/rotate_key_rollback dispatch arms | ✓ VERIFIED | Both arms present at lines 522-536, correct shape |
| `agent-install/omni-agent-rs/tests/remediation_dispatch_test.rs` | dispatch-level integration tests | ✓ VERIFIED | 5/5 passing, independently re-run |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `select_playbook()` vuln branch | `by_name['rotate_key']` | fingerprint conjunct | ✓ WIRED | Confirmed in code + tests |
| `agent_vuln_ingest_service.set_fields['fingerprint']` | `{{finding.details.fingerprint}}` template | ingest → render | ✓ WIRED | Confirmed |
| `ACTION_MAP['rotate_key']`/`['rotate_key_rollback']` | `validate()` | `load_default_playbooks()` | ✓ WIRED | Confirmed |
| `scan_misconfigurations()` | `check_authorized_keys()` | new call site | ✗ NOT_WIRED | Function doesn't exist; no call site — same gap as the 2026-08-14 verification, unchanged |
| `ssh_key_checks::weak_reason_for()` shared predicate | scanner AND rotation re-verify | single source of truth | ⚠️ PARTIAL | Used by `ssh_key_rotation.rs` (verified, real); NOT used by the scanner because the scanner has no weak-key check at all |
| `instructions.rs "rotate_key" arm` | `remediation_actions::rotate_key()` | `ssh_key_rotation::rotate_in_place()` | ✓ WIRED | Confirmed by code read + passing integration test |
| `instructions.rs "rotate_key_rollback" arm` | `remediation_actions::rotate_key_rollback()` | `ssh_key_rotation::rollback_rotation()` | ✓ WIRED | Confirmed |
| `rotate_key.yaml` rollback step | `rotate_key_rollback` arm | corrected params | ✓ WIRED | `rotate_key_backup_path` grep returns 0; `rotate_key_rollback` grep returns 1 |

### Behavioral Spot-Checks (independently re-run, not trusted from SUMMARY.md)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Rust lib test suite | `cargo test --lib` (agent-install/omni-agent-rs) | 83 passed; 0 failed | ✓ PASS |
| rotate_key test subset | `cargo test rotate_key` | 34 passed (29 lib + 5 dispatch integration); 0 failed | ✓ PASS |
| vulnerability_scan test subset | `cargo test vulnerability_scan` | 11 passed; 0 failed; **none relate to weak-key detection** | ⚠️ CONFIRMS GAP |
| ssh_key_checks test subset | `cargo test ssh_key_checks` | 0 tests selected | ✗ CONFIRMS GAP |
| Full workspace `cargo test` | `cargo test` | 90 passed across lib/dispatch/unittests; 7 failed in `tests/integration.rs` | ⚠️ 7 failures are pre-existing, documented in `deferred-items.md`, unrelated to rotate_key (stale capability count 15 vs 18/20, platform-name assertion, FIM/predictive-health schema) — reproduced identically here, not a Phase-64 regression |
| Backend wiring + playbook tests | `pytest backend/tests/test_rotate_key_wiring.py backend/tests/test_remediation_playbook.py -v` | 20 passed; 0 failed | ✓ PASS |

### Requirements Coverage

| Requirement | Source | Description | Status | Evidence |
|-------------|--------|-------------|--------|----------|
| AUTO-02 (extends, not a new ID) | v3.4-REQUIREMENTS.md (archived milestone), completed at Phase 53 | YAML-defined remediation playbook system per finding class, operator-extensible | ⚠️ PARTIALLY EXTENDED | Playbook, routing, dispatch, and rotation mechanics for `rotate_key` are real and tested (extends AUTO-02 as intended for the *action* half). The *detection* half (agent scanner emitting `rotate_key`-routed findings from a real host scan) does not exist, so AUTO-02's "per finding class" extension is not reachable from a real scan yet — only from a manually-constructed finding. |

No orphaned requirements: the current milestone's `.planning/REQUIREMENTS.md` (ITAM-Backlog) does not define AUTO-02 at all — it belongs to the archived v3.4 milestone, consistent with this phase's "extends AUTO-02" (not a new ID) framing. No traceability gap in the active REQUIREMENTS.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) found in any of the 12 phase-64 touched files | — | — |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` | whole file | Zero test coverage for a security-classification module (weak-key detection) | ⚠️ WARNING | Silent correctness risk — RSA-threshold and malformed-input paths are unverified by any test |
| `.planning/phases/64-rotate-key-autonomous-remediation-action/64-02-SUMMARY.md` | whole file | SUMMARY claims work ("Modified vulnerability_scan.rs to include check_authorized_keys and emit weak_key_finding... All tests... passed") that does not exist in the codebase | 🛑 BLOCKER | This is exactly the SUMMARY-vs-codebase divergence this verification agent is designed to catch — flagged here explicitly since it affects trust in the rest of that plan's claims |

### Gaps Summary

The phase is **not fully complete**. This session's plan-03/plan-04 work is real, substantial, and independently verified: SSH key rotation mechanics (`ssh_key_rotation.rs`, 29 tests), instruction dispatch wiring (`instructions.rs`, 5 tests), and the rollback playbook fix are all genuinely implemented and pass every re-run test. Those close the gaps this session set out to close.

However, a **separate, pre-existing gap survives from before this session and was never addressed**: plan 64-02's Task 2 (wiring weak-SSH-key detection into the agent's vulnerability scanner) was never implemented, despite `64-02-SUMMARY.md` and `ROADMAP.md`'s plan list both claiming it was done. `agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs` has no `check_authorized_keys()` function, no `weak_key_finding()` function, and no call site inside `scan_misconfigurations()`. This exact gap was already flagged in this same directory's 2026-08-14 VERIFICATION.md ("Missing integration of weak-key detection... into vulnerability_scan.rs") and remains open today.

**Practical consequence:** the `rotate_key` action is reachable end-to-end — but only from a manually-constructed or externally-injected finding. A real host with a weak or DSA SSH key will never be detected and will never trigger this playbook automatically, because nothing in the agent's scan path looks for one. The phase's own plan list describes 64-02 as "Rust weak-key detection (`ssh_key_checks.rs` + scanner integration...)" — the scanner integration half of that description is not true.

A secondary, smaller gap: `ssh_key_checks.rs` (the parsing/classification module) has zero dedicated unit tests, though its DSA-detection branch gets incidental, real test coverage through `ssh_key_rotation_tests.rs`'s D-07 re-verify test. The RSA bit-threshold branch and the malformed-input-skip behavior have no test evidence anywhere.

**Recommendation:** Plan a small closure plan (would be 64-05, or reopen 64-02) that: (1) adds `check_authorized_keys()`/`weak_key_finding()` to `vulnerability_scan.rs` and wires the call site into `scan_misconfigurations()`, per plan 64-02 Task 2's original specification (still valid, nothing about the shape has changed); (2) adds the 8 unit tests plan 64-02 Task 1 specified for `ssh_key_checks.rs`. Both are scoped, bounded, low-risk additions — the rotation and dispatch mechanics they'd feed into are already proven.

---
_Verified: 2026-08-17T20:45:00Z_
_Verifier: Claude (gsd-verifier)_
