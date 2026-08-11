---
phase: 64
slug: rotate-key-autonomous-remediation-action
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-11
---

# Phase 64 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (Rust)** | `cargo test` — built-in, `#[cfg(test)] mod tests` inline, matching `remediation_actions.rs`/`vulnerability_scan.rs` convention |
| **Framework (Python)** | `pytest` via `backend/venv/bin/python -m pytest` |
| **Config file** | none dedicated — project-wide defaults |
| **Quick run command (Rust)** | `cd agent-install/omni-agent-rs && cargo test rotate_key` / `cargo test ssh_key` |
| **Quick run command (Python)** | `backend/venv/bin/python -m pytest backend/tests/test_remediation_playbook.py -k rotate_key -q` |
| **Full suite command (Rust)** | `cd agent-install/omni-agent-rs && cargo test` |
| **Full suite command (Python)** | `backend/venv/bin/python -m pytest backend -q` |
| **Estimated runtime** | ~30-60s Rust, ~2-3min full Python backend suite |

---

## Sampling Rate

- **After every task commit:** Run the relevant quick command (Rust module or `pytest -k <keyword>`) above
- **After every plan wave:** Run both full suite commands (Rust + Python)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60s (Rust quick), ~10s (Python `-k` quick)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 64-0N-0M | TBD | TBD | AUTO-02 (rotate_key arm) | D-05, D-09 | Refuses empty/malformed fingerprint; refuses sole-entry authorized_keys; succeeds on temp fixture with 2+ entries; never emits private key in return value | unit (Rust, hermetic) | `cargo test rotate_key` | ❌ Wave 0 | ⬜ pending |
| 64-0N-0M | TBD | TBD | AUTO-02 (weak-key VULN check) | D-02 | Flags RSA<2048 and DSA; does not flag Ed25519/RSA≥2048; missing/unreadable authorized_keys degrades gracefully (no panic, no false finding) | unit (Rust) | `cargo test ssh_key_checks` | ❌ Wave 0 | ⬜ pending |
| 64-0N-0M | TBD | TBD | AUTO-02 (playbook selection) | D-02 | `select_playbook()` routes a `vuln` finding with `playbook_ref: "rotate_key"` to the `rotate_key` playbook, not `disable_service`/`patch_package` | unit (Python) | `pytest backend/tests/test_remediation_playbook.py -k rotate_key -q` | ❌ Wave 0 | ⬜ pending |
| 64-0N-0M | TBD | TBD | AUTO-02 (YAML validity) | — | `rotate_key.yaml` validates against `ACTION_MAP`, loads via `load_default_playbooks()` | unit (Python) | existing generic vendored-file test — confirm coverage during Wave 0 | ✅ (confirm) | ⬜ pending |
| 64-0N-0M | TBD | TBD | D-09 (no key material leak) | T-64 (see SECURITY gate) | Agent's success JSON for `rotate_key` never contains a `-----BEGIN` PEM marker substring | unit (Rust) — mirrors existing `aws_key_shaped_token_flagged_without_leaking_value` pattern | `cargo test rotate_key` (same target, added assertion) | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Task IDs are TBD — the planner fills in exact plan/wave/task numbers when PLAN.md files are written; this map's rows are the required coverage, not yet bound to specific task IDs.*

---

## Wave 0 Requirements

- [ ] New Rust test module(s) for `ssh_key_checks.rs`/`ssh_key_rotation.rs`/`rotate_key` action — greenfield, no existing tests
- [ ] Extend `backend/tests/test_remediation_playbook.py` with a `rotate_key` selection case — existing file, existing pattern to follow
- [ ] Framework install: none needed — `cargo test`/`pytest` already fully set up project-wide

---

## Manual-Only Verifications

*All phase behaviors have automated verification — no manual-only items identified. (Real host SSH login with a rotated key is possible to test in CI/dev via a disposable container, not flagged as human-only.)*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
