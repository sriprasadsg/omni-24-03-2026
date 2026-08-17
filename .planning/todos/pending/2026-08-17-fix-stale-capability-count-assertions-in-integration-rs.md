---
created: 2026-08-17T18:14:26.749Z
title: Fix stale capability-count assertions in integration.rs
area: testing
severity: minor
files:
  - agent-install/omni-agent-rs/tests/integration.rs:81
  - agent-install/omni-agent-rs/tests/integration.rs:105
  - agent-install/omni-agent-rs/tests/integration.rs:116
  - agent-install/omni-agent-rs/tests/integration.rs:210
  - agent-install/omni-agent-rs/tests/integration.rs:220
  - agent-install/omni-agent-rs/tests/integration.rs:254
  - agent-install/omni-agent-rs/tests/integration.rs:265
---

## Problem

`agent-install/omni-agent-rs/tests/integration.rs` hardcodes an expected
`CapabilityManager` capability count of 15
(`test_capability_manager_has_15_capabilities`, plus 6 tests that fail as a
downstream consequence: `test_capability_statuses_structure`,
`test_collect_all_no_panics`, `test_fim_collect_schema`,
`test_heartbeat_payload_capabilities_present`,
`test_heartbeat_payload_top_level_fields`, `test_predictive_health_schema`).
`CapabilityManager::new()` now registers 18–20 capabilities — the count grew
across phases 50–66 (`ebpf_tracing`, `system_patching`, `remote_access`,
`network_discovery`, fanotify FIM, etc.) without this test file being
updated. `test_heartbeat_payload_top_level_fields` separately asserts
`platform == "Windows"` but fails when the suite runs on Linux.

Confirmed pre-existing, not caused by any of this session's work: reproduces
identically with the phase 64 (`ssh_key_checks`/`vulnerability_scan`) and
phase 65 (`naughtyfy`/`fim.rs` Windows cross-compile) changes stashed out.
Documented in
`.planning/phases/64-rotate-key-autonomous-remediation-action/deferred-items.md`
item 1. Not fixed as part of either phase since it's cross-cutting test
debt spanning many capabilities' `files_modified`, not scoped to one plan.

## Solution

Update `tests/integration.rs`'s expected capability count (and the
`test_fim_collect_schema`/`test_predictive_health_schema` shape assertions,
and the `test_heartbeat_payload_top_level_fields` platform-string check) to
match the current `CapabilityManager::new()` registration list in
`agent-install/omni-agent-rs/src/capabilities/mod.rs`. Run
`cargo test --test integration` on the actual current registration list to
derive the correct expected values rather than guessing.
