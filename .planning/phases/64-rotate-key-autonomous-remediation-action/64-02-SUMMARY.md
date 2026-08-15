---
phase: 64-rotate-key-autonomous-remediation-action
plan: 02
summary: Added weak/compromised SSH key detection to the agent scanner. Implemented shared predicate and parser in `ssh_key_checks.rs`, integrated the check into `vulnerability_scan.rs`, and ensured proper error handling and finding emission.
---

## Achievements
- Added `ssh-key` dependency to `agent-install/omni-agent-rs/Cargo.toml`.
- Created `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` with `AuthorizedKeyEntry` struct, constants, and helper functions (`weak_reason_for`, `parse_authorized_keys`, `is_authorized_keys_path`, `authorized_keys_paths`).
- Updated `agent-install/omni-agent-rs/src/capabilities/mod.rs` to declare the new module.
- Modified `agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs` to include `check_authorized_keys` and emit `weak_key_finding`.
- All tests for `ssh_key_checks` and `vulnerability_scan` passed.

## Remaining Gaps
- None for this plan.

## Verification
- All acceptance criteria for Plan 64-02 met.