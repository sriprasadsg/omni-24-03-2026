# Deferred Items — Phase 64

## 1. `tests/integration.rs` capability-count assertions are stale (7 pre-existing failures)

**Found during:** 64-03 Task 1 (`cargo test` baseline check).

**Detail:** `agent-install/omni-agent-rs/tests/integration.rs::test_capability_manager_has_15_capabilities`
asserts `CapabilityManager` registers exactly 15 capabilities; the real count is
18 (`ebpf_tracing`, `system_patching`, `remote_access`, `network_discovery`, and
others were added by later phases without updating this test). Six more tests
in the same file (`test_capability_statuses_structure`,
`test_collect_all_no_panics`, `test_fim_collect_schema`,
`test_heartbeat_payload_capabilities_present`,
`test_heartbeat_payload_top_level_fields`, `test_predictive_health_schema`)
fail as a downstream consequence of the same stale count/shape assumption.

**Why not fixed here:** `ssh_key_rotation.rs` is not a `Capability` trait
implementor and is never registered in `CapabilityManager` — it has no
relationship to this test file. Confirmed reproducing identically on the
parent commit (`218ba8d8`'s parent, before any Phase 64 plan-03 change) via
`git stash` + re-run. Out of this plan's `files_modified` scope
(`ssh_key_rotation.rs`, `ssh_key_rotation_tests.rs`, `mod.rs`,
`remediation_actions.rs`).

**Recommended follow-up:** A small housekeeping plan should update
`tests/integration.rs`'s expected capability count and any shape assertions
to match the current `CapabilityManager::new()` registration list.

## 2. `naughtyfy` crate does not cross-compile for `x86_64-pc-windows-gnu` — RESOLVED 2026-08-17

Fixed (commit 661c8390): `naughtyfy` moved to
`[target.'cfg(target_os = "linux")'.dependencies]` in `Cargo.toml`
(not `cfg(unix)` — fanotify has no macOS equivalent either, so that
would still fail there). `fim.rs`'s `fanotify_watcher` import,
`handle_fanotify_event`, and `map_fanotify_mask_to_change_type` are now
`#[cfg(target_os = "linux")]`-gated, and `start_watcher()` got a
non-Linux stub returning an "unsupported on this platform" error
(mirroring `remediation_actions.rs`'s existing per-OS pattern). Along
the way, found and removed a dead branch that called a commented-out
`process_info()` function — `fim.rs` would not actually have compiled
on non-Linux even with the dependency fixed. `cargo check --target
x86_64-pc-windows-gnu` now passes with 0 errors; `cargo test` unchanged
from baseline (14 passed / 7 failed, all pre-existing per item 1 below).

Original report, preserved for context:

**Found during:** 64-03 Task 1/2 (`cargo check --target x86_64-pc-windows-gnu`
acceptance criterion).

**Detail:** `naughtyfy = "0.2.1"` (used by the Linux-only `fanotify_watcher.rs`
capability added in the root track's Phase 65) fails ~20 type errors
(`E0308`/`E0425`/`E0432`/`E0433`/`E0531`/`E0599`) when the crate graph is
compiled for the Windows target — it is unconditionally listed in
`Cargo.toml` (`[dependencies]`, not `[target.'cfg(unix)'.dependencies]`)
even though the module that uses it is `#[cfg(target_os = "linux")]`-gated
in `mod.rs`.

**Why not fixed here:** Confirmed reproducing identically on the parent
commit via `git stash` (root-caused to Phase 65's `fanotify_watcher.rs`
addition, not this plan's files). The `x86_64-pc-windows-gnu` rustup target
itself also wasn't installed in this sandbox and was added
(`rustup target add x86_64-pc-windows-gnu`) purely to be able to run this
plan's own cross-compile acceptance check.

**Recommended follow-up:** Move `naughtyfy` into a `[target.'cfg(unix)'.dependencies]`
(or `cfg(target_os = "linux")`-scoped) section in `Cargo.toml` so it is never
pulled into the Windows dependency graph at all.
