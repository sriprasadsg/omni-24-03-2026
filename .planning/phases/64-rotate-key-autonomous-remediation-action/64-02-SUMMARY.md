---
phase: 64-rotate-key-autonomous-remediation-action
plan: 02
subsystem: agent
tags: [rust, ssh-key, vulnerability-scan, agent-install/omni-agent-rs]

# Dependency graph
requires:
  - phase: 64-01
    provides: agent_vuln_ingest_service fingerprint set_field + rotate_key playbook dispatch param wiring
provides:
  - "ssh_key_checks::weak_reason_for() — the single shared weak-key predicate reused by plan 64-03's post-rotation re-verify"
  - "ssh_key_checks::parse_authorized_keys()/is_authorized_keys_path()/authorized_keys_paths()"
  - "vulnerability_scan::check_authorized_keys() wired into scan_misconfigurations(), emitting rotate_key-playbook findings"
affects: []

# Tech tracking
tech-stack:
  added:
    - "ssh-key 0.6.7 (default-features = false, features: alloc/std/rand_core/ed25519/rsa/dsa) — pure-Rust OpenSSH key parse/fingerprint/keygen, RustCrypto org, no C dependency"
  patterns:
    - "Test module split into a sibling *_tests.rs file (vulnerability_scan.rs -> vulnerability_scan_tests.rs via #[path]) once the host file crosses the project's 500-line convention, mirroring the existing ssh_key_rotation.rs/ssh_key_rotation_tests.rs split."
    - "Fingerprint embedded inside the finding's `detail` string (not just a separate field) because backend ingest dedups non-CVE findings on the (tenant, agent, cve_id, affected_path, detail) tuple — two weak keys in the same file need distinct detail strings or they collapse into one document."

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs
    - agent-install/omni-agent-rs/src/capabilities/vulnerability_scan_tests.rs
  modified:
    - agent-install/omni-agent-rs/Cargo.toml
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs

key-decisions:
  - "Enabled the crate's `rsa` and `dsa` features (RESEARCH Assumptions Log A1): RSA modulus bit length and DSA key data are not reachable from the parsed public key through the default-parse surface alone, so both features were turned on for structural inspection only — this phase performs no RSA/DSA crypto operations, just bit-length/type classification."
  - "check_authorized_keys() split into a thin path-enumerating outer function and a testable check_authorized_keys_text(path, text) inner function, so tests drive fixtures through temp files instead of real host paths."

requirements-completed: [AUTO-02]

# Verification
tests-written: 13
tests-total: "8 ssh_key_checks + 5 check_authorized_keys behaviors (16 vulnerability_scan tests total incl. pre-existing)"
build-status: "cargo test: all ssh_key_checks/vulnerability_scan tests green. cargo build: 0 unused-code warnings in either new file (4 pre-existing warnings elsewhere, unrelated). cargo check --target x86_64-pc-windows-gnu: fails — but confirmed pre-existing (reproduces identically with this plan's changes stashed out), caused by phase 65's `naughtyfy` crate (Linux-only fanotify binding, commit 6764a3c8), not by this plan. Full `cargo test` also has 7 pre-existing integration.rs failures (stale hardcoded capability count 15 vs actual 20, and two schema-drift asserts) — confirmed identical with this plan's changes stashed out, unrelated to phase 64."

deviations-from-plan:
  - "Task 1 was re-done in a prior session commit (d984fc5b) after re-verification found the module existed but its 8 required tests and module doc comment were missing. This session verified that fix and completed Task 2 (scanner wiring), which existed as uncommitted working-tree changes — committed as 3a930718."
  - "The plan's Windows cross-compile acceptance criterion could not be satisfied as an unqualified pass because an unrelated phase-65 dependency already breaks that target; recorded here rather than silently ignored, per project convention. Not fixed in this plan — out of scope."
---

# 64-02 Summary

Added `ssh_key_checks.rs`: weak-key classification (RSA < 2048 bits, any DSA) via `weak_reason_for()`, an `authorized_keys` parser that skips malformed/truncated lines without ever producing a false entry, a path guard, and Linux/macOS host enumeration capped at 64 files / 256 KiB per read. Wired `check_authorized_keys()` into `vulnerability_scan::scan_misconfigurations()`, emitting one `misconfig` finding per weak key with `playbook_ref: rotate_key`, a SHA256 fingerprint embedded in `detail` for dedup, and no key body or private material in the payload.

All plan acceptance criteria verified green except the Windows cross-compile check, which fails for an unrelated pre-existing reason (phase 65's `naughtyfy` crate) — confirmed by reproducing the same failure with this plan's diff stashed out.
