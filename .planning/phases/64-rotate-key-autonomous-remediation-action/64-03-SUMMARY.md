---
phase: 64-rotate-key-autonomous-remediation-action
plan: 03
subsystem: agent
tags: [rust, ssh-key, ed25519, remediation, security, agent-install/omni-agent-rs]

# Dependency graph
requires:
  - phase: 64-01
    provides: rotate_key.yaml playbook + rotate_key_rollback dispatch shape (backend routing, deterministic backup-path derivation contract)
  - phase: 64-02
    provides: ssh_key_checks.rs — AuthorizedKeyEntry, parse_authorized_keys, weak_reason_for, is_authorized_keys_path
provides:
  - ssh_key_rotation.rs — the destructive half of rotate_key (target selection, snapshot/rollback, atomic write, Ed25519 keygen, grounded re-verify)
  - RemediationError::LockoutRefused / KeyNotFound variants
affects: [64-04 (dispatch-arm wiring — not yet planned)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Whole-file snapshot-before-edit + byte-for-byte restore-on-failure (D-06/D-07), mirroring restore_file's backup/restore shape but with a self-derived backup path"
    - "Fingerprint-exact targeting with a hard refusal (not a fallback) when fewer than 2 parseable entries exist (D-04/D-05)"
    - "Grounded post-write re-verify: re-read from disk (never the in-memory pre-write string), re-parse, and delegate weak-key judgment entirely to ssh_key_checks (never re-implemented locally)"
    - "D-09 output boundary type with no Serialize derive — RotationOutcome{new_fingerprint, new_comment} only"
    - "Sibling test-file split (#[path = ...] mod tests;) to keep a heavily-tested module under the 500-line cap without trimming test coverage"

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs
    - agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs

key-decisions:
  - "Ed25519 chosen for the generated replacement key (OpenSSH's own default since 9.5), per CONTEXT.md's discretion grant"
  - "No Cargo.toml feature changes needed for keypair generation — ssh-key's existing rand_core+ed25519 features already satisfy CryptoRngCore via rand 0.8's blanket impl over rand::rngs::OsRng, confirmed by reading the vendored ssh-key 0.6.7 and rand_core 0.6.4 source directly rather than assuming"
  - "D-07's re-verify was proven end-to-end for real (not mocked): a fixture with the same underlying key listed twice makes the genuine post-rotation re-verify fail, because rotating only the first occurrence leaves the untouched duplicate line with the stale fingerprint"
  - "Split the #[cfg(test)] module into a sibling ssh_key_rotation_tests.rs via #[path = ...] once Task 2's tests pushed the file to 850 lines — the plan's own explicit fallback for the 500-line cap, applied rather than trimming test behavior"

requirements-completed: [AUTO-02]

coverage:
  - id: D1
    description: "select_target enforces D-04 (exact fingerprint match only) and D-05 (refuse rotation of the sole authorized_keys entry) before any keypair is generated or byte is written"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_select_target_* (6 tests)"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_sole_entry_refuses_lockout_untouched"
        status: pass
    human_judgment: false
  - id: D2
    description: "snapshot_backup / rollback_rotation provide a whole-file, byte-for-byte reversible backup taken before any edit (D-06)"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_snapshot_backup_byte_identical_owner_only"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rollback_restores_byte_for_byte_and_cleans_up"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rollback_without_snapshot_refuses_and_leaves_file_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "write_atomic replaces authorized_keys via same-directory temp-file + rename, preserving the original file's unix mode and leaving no leftover temp file on any failure"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_write_atomic_replaces_contents_no_leftover_temp"
        status: pass
    human_judgment: false
  - id: D4
    description: "rotate_in_place generates a fresh Ed25519 replacement (real CSPRNG), preserves the matched line's options prefix verbatim, and every other authorized_keys line is byte-for-byte identical and in the same order after rotation (D-04)"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_three_entry_success"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_untouched_lines_byte_identical_and_ordered"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_preserves_options_prefix"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_uses_real_csprng_not_fixed_seed"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-09: RotationOutcome and the new private key file never leak key material — new key written at 0600 with a .pub sibling, the debug-formatted outcome contains neither the OpenSSH private-key armor nor the private key file's own contents, and a pending prior rotated key blocks a second rotation rather than being silently overwritten (D-08)"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_outcome_never_leaks_private_key"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_writes_private_key_owner_only_and_pub_sibling"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_refuses_when_pending_rotated_key_exists"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-07 grounded post-write re-verify: re-reads and re-parses the file from disk, requires the old fingerprint absent AND the new entry's weak_reason (from ssh_key_checks) is None; a failure restores the file from the snapshot and rotate_in_place never reports success on an unverified file"
    requirement: AUTO-02
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_verify_rotation_grounded_fails_when_old_fingerprint_still_present"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_verify_rotation_grounded_fails_when_new_entry_is_weak"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs#rotate_key_rotate_in_place_duplicate_fingerprint_fails_reverify_and_rolls_back"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-08-17
status: complete
---

# Phase 64 Plan 03: SSH Key Rotation Mechanics Summary

**Ed25519 authorized_keys rotation in `ssh_key_rotation.rs` — exact-fingerprint targeting, sole-entry lockout refusal, whole-file snapshot/rollback, atomic temp+rename write, and a grounded (re-read from disk) post-write re-verify that delegates weak-key judgment to `ssh_key_checks` and rolls back rather than ever reporting an unverified success.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-08-17T13:35:00Z
- **Completed:** 2026-08-17T14:30:00Z
- **Tasks:** 2
- **Files modified:** 4 (2 new, 2 modified)

## Accomplishments
- `select_target`/`validate_target`: exact-fingerprint-only targeting (D-04), sole-entry lockout refusal before any match attempt or write (D-05), and the single shared path guard (`ssh_key_checks::is_authorized_keys_path`) between an untrusted instruction parameter and a privileged file write.
- `snapshot_backup`/`rollback_rotation`/`write_atomic`: whole-file snapshot taken before any edit (D-06), byte-for-byte restore, same-directory temp-file + rename so `authorized_keys` is never observed partially written, original unix mode preserved.
- `rotate_in_place`: generates a fresh Ed25519 keypair via a real CSPRNG (`rand::rngs::OsRng`), preserves the matched line's options prefix verbatim (forced command / source restriction / no-pty never silently dropped), rebuilds the file replacing only the matched line, then re-reads and re-parses the file from disk and requires both the old fingerprint's absence and the new entry's `weak_reason` (from `ssh_key_checks::weak_reason_for`, never re-implemented here) to be `None` — restoring from the snapshot and refusing on any failure (D-07).
- `RotationOutcome`: the D-09 boundary — exactly `new_fingerprint`/`new_comment`, no `Serialize` derive, no key material or filesystem path ever leaves the function; the module emits no diagnostic output at all.
- `sanitize_comment`: bounds the new key's comment to a fixed ASCII charset so a comment value can never inject a second `authorized_keys` line.

## Task Commits

Each task was committed atomically, test-first (RED) then implemented (GREEN):

1. **Task 1: target selection, lockout refusal, snapshot, atomic write, rollback**
   - `218ba8d8` (test) — 17 failing tests + `RemediationError::LockoutRefused`/`KeyNotFound` + `mod.rs` declaration
   - `dc9ea1f6` (feat) — implementation, all 17 tests green
2. **Task 2: Ed25519 replacement generation, in-place rotation, grounded re-verify**
   - `9a525118` (test) — 12 more failing tests
   - `be1dbde8` (feat) — implementation, all 29 tests green; split test module into a sibling file to stay under the 500-line cap

**Plan metadata:** (this commit)

## Files Created/Modified
- `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs` — the destructive half of `rotate_key` (397 lines)
- `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation_tests.rs` — 29 hermetic tests, split out per the plan's own 500-line-cap fallback
- `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` — added `RemediationError::LockoutRefused`/`KeyNotFound`
- `agent-install/omni-agent-rs/src/capabilities/mod.rs` — added `pub mod ssh_key_rotation;`

## Decisions Made
- Ed25519 for the generated replacement key (RESEARCH.md's State of the Art: OpenSSH's own default since 9.5); recorded in a code comment at the `generate_replacement` call site.
- No `Cargo.toml` feature changes: confirmed by reading the vendored `ssh-key` 0.6.7 and `rand_core` 0.6.4 crate sources directly that the existing `rand_core`+`ed25519` feature set already satisfies `PrivateKey::random`'s `CryptoRngCore` bound via `rand` 0.8's blanket impl over `rand::rngs::OsRng` — the plan's own speculative "extend the feature list if needed" branch did not apply.
- Test 9 (D-07 failure path) exercises the rollback branch of `rotate_in_place` end-to-end for real, with no test-only seam: a fixture listing the same underlying key twice makes the genuine post-rotation re-verify fail, because only the first occurrence gets replaced and the untouched duplicate line still carries the old fingerprint.
- Split the `#[cfg(test)]` module into a sibling `ssh_key_rotation_tests.rs` file via `#[path = ...]` once Task 2 pushed the single-file line count to 850 — the plan's own explicit acceptance-criterion fallback ("split the test module into a sibling file rather than trimming behavior"), applied verbatim.

## Deviations from Plan

None from the plan's own instructions — every `<action>` step, `<behavior>` test, and `must_haves.truths` line was implemented as specified. Two out-of-scope, pre-existing conditions were discovered and logged (not fixed, per the scope-boundary rule) rather than being deviations from this plan's own work:

### Pre-existing, unrelated (logged, not fixed)

**1. `tests/integration.rs` capability-count assertions are stale (7 failures)**
- **Found during:** Task 1 baseline `cargo test` run.
- **Issue:** `test_capability_manager_has_15_capabilities` and 6 dependent tests assert a 15-capability `CapabilityManager`; the real count is 18 (capabilities added by later phases without updating this test).
- **Why not fixed:** `ssh_key_rotation.rs` is not a `Capability` trait implementor and has no relationship to `CapabilityManager`. Confirmed reproducing identically on the pre-plan-03 parent commit via `git stash`.
- **Logged to:** `.planning/phases/64-rotate-key-autonomous-remediation-action/deferred-items.md` item 1.

**2. `naughtyfy` crate does not cross-compile for `x86_64-pc-windows-gnu`**
- **Found during:** the plan's own Windows cross-compile acceptance criterion.
- **Issue:** `naughtyfy` (used by Phase 65's Linux-only `fanotify_watcher.rs`) is listed unconditionally in `Cargo.toml` and fails ~20 type errors when compiled for the Windows target.
- **Why not fixed:** Root-caused to Phase 65's addition, not this plan's files; confirmed reproducing identically on the parent commit via `git stash`. The Windows rustup target itself also had to be installed in this sandbox (`rustup target add x86_64-pc-windows-gnu`) purely to run this plan's own check.
- **Logged to:** `.planning/phases/64-rotate-key-autonomous-remediation-action/deferred-items.md` item 2.

---

**Total deviations:** 0 from this plan's own scope; 2 pre-existing unrelated conditions logged for follow-up.
**Impact on plan:** None — `cargo test ssh_key_rotation` / `cargo test rotate_key` both report 29/29 passing with 0 failures, and the full workspace lib-test suite (83 tests) shows 0 regressions.

## Issues Encountered
None beyond the two logged pre-existing conditions above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `ssh_key_rotation::rotate_in_place`/`rollback_rotation` are fully proven under hermetic tests but are not yet reachable from any instruction — plan 64-04 (dispatch-arm wiring in `instructions.rs`, exposing `rotate_key`/`rotate_key_rollback` to the backend) is the deliberate next step, per this plan's own objective ("nothing in this plan is reachable from an instruction yet, which is deliberate").
- `RotationOutcome{new_fingerprint, new_comment}` is the exact shape plan 64-04's dispatch arm should surface in its `{status: "success", ...}` JSON, per `64-PATTERNS.md`'s documented dispatch-arm shape.
- Two pre-existing, unrelated issues are now tracked in `deferred-items.md` for a future housekeeping pass (stale capability-count test, `naughtyfy` Windows cross-compile scoping).

---
*Phase: 64-rotate-key-autonomous-remediation-action*
*Completed: 2026-08-17*
