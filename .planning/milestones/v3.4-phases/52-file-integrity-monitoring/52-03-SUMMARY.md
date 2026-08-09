---
plan: 52-03
phase: 52-file-integrity-monitoring
---

# Plan 52-03 Summary — FIM Baseline Snapshot + Drift Detection

## What landed

`agent-install/omni-agent-rs/src/capabilities/fim_baseline.rs` — signed baseline snapshot + restart drift detection (FIM-03).

### Capabilities

- `local_keypair_for_dir(dir)` — load-or-generate `ed25519_dalek::SigningKey`, persisted at `<dir>/signing_key.dat` with 0600 perms on Unix.
- `compute_baseline(paths)` — walks paths → `Baseline { version, created_at, entries: [{path, sha256, size_bytes, modified_at}] }`.
- `save_signed_to_dir(baseline, dir)` — `bincode::serialize` + ed25519 sign + atomic temp-then-rename writes of `baseline.bin` + `signature.sig`.
- `load_verified_from_dir(dir)` — verify signature before deserializing; returns `None` on tamper/missing/bad-sig (fail-closed).
- `check_drift_on_start(paths, dir)` — verifies baseline; if valid → diffs current vs baseline and enqueues `Added`/`Removed`/`Changed` drift events; if invalid/missing → enqueues `BaselineReset` event with reason and recomputes (never panics).
- `enqueue_drift(event, dir)` — writes to local `fim_queue.db` reusing the existing fim_queue schema (separate `event_json` table, drained by 52-04).

### Threat model mitigations

- **T-52-05 Tampering** — ed25519 signature over baseline; verify-fail → reset+flag, never silently trust.
- **T-52-06 Info Disclosure** — key agent-local, 0600 perms, never shipped/transmitted.
- **T-52-07 DoS** — corrupt/missing baseline triggers graceful recompute; no panic.

## Files

- `agent-install/omni-agent-rs/src/capabilities/fim_baseline.rs` (new)
- `agent-install/omni-agent-rs/src/capabilities/mod.rs` (already registered: `pub mod fim_baseline;`)

## Verification

```
cargo build              → clean (warnings only)
cargo test fim_baseline  → 5/5 pass
```

Tests cover: sign→verify roundtrip; tampered byte fails verification; drift diff add/remove/change logic; missing baseline → recompute; `check_drift_on_start` on missing baseline emits `BaselineReset` event with reason `missing_baseline` and persists new baseline.

## Notes / deviations

- `baseline_dir()` resolves via `OMNI_AGENT_BASELINE_DIR` env var (falls back to `dirs::data_dir()/omni-agent/baseline/`); tests use tempdir + `_for_dir` variants throughout to avoid touching the user's real data dir.
- `lib.rs` already calls `check_drift_on_start(&cfg.fim_paths, &baseline_dir())` on startup — wired in by 52-04; 52-03 just made the module compile + green.
- Drift queue uses a separate schema (`event_json TEXT`) from `fim.rs`'s typed `fim_queue` columns; 52-04 will drain both. This keeps `fim_baseline.rs` independent of `fim.rs` private API surface.

## Next

- 52-04 wires `agent_loop` to start the watcher + drain loop + queue POST to backend, adds `fim_paths` config (already present in `Config`) and windows cross-check.
