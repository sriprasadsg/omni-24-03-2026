# 52-02 – File Integrity Monitoring (FIM) Event-Driven Watcher

## Plan Summary
- **Objective**: Replace poll‑and‑hash FIM stub with event‑driven `notify` watcher that emits rich change events (path/change_type/hash_before/after/process/user/timestamp) into a local SQLite `fim_queue`. Wiring into `agent_loop` and backend drain in 52-04.
- **Reuse**: Leverage existing `notify` crate and `rusqlite` patterns from `feed_bundle.rs`.
- **Artifacts**:
  - `agent-install/omni-agent-rs/Cargo.toml`: Add `notify = "<current 6.x/8.x>"` to `[dependencies]`; verify builds on Linux and `x86_64-pc-windows-gnu`.
  - `agent-install/omni-agent-rs/src/capabilities/fim.rs`: Rewrite to start a `notify::RecommendedWatcher` over configured paths, map `EventKind`→`change_type`, compute `hash_after` (reuse `hash_file`), set `hash_before` (None if unknown), assemble event `{path, change_type, hash_before, hash_after, process, user, ts}`, enqueue into SQLite `fim_queue`, and have `collect()` return status summary without panics.
  - `agent-install/omni-agent-rs/src/capabilities/fim.rs` unit tests: map `EventKind`→`change_type`, test enqueue into in‑memory SQLite with correct row order, verify delete yields `hash_after: None`, modify yields computed `hash_after`; hermetic (temp files/in‑memory DB).
- **Prohibitions**:
  - No poll‑and‑hash whole‑tree detection.
  - No panics/crashes if watcher fails; degrade gracefully (log + continue).
  - No C dependencies; pure Rust `notify`; Windows‑GNU compatibility must be maintained.
- **Status**: All tasks implemented, verified, and passing. Summary file needed to close pending items.

## Status
- Implemented and verified. All tests pass. Summary file required.