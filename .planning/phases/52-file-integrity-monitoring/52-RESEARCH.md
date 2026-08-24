# Phase 52 — File Integrity Monitoring — RESEARCH

Codebase-grounded. Refs verified 2026-07-30.

## 1. Existing-surface audit

| Surface | State | Use in 52 |
|---------|-------|-----------|
| `capabilities/fim.rs` (84 lines) | `collect(&sys)` hashes a fixed path list (sha256 + size + modified) each heartbeat — **poll-and-hash, no events, no before/after, no baseline, no process/user** | Rewrite: background `notify` watcher; `collect()` becomes a status/summary reporter. |
| `Cargo.toml` | `rusqlite` (bundled), `sha2`, `hex`, `tokio`, `chrono`. No `notify`. `ed25519-dalek` added in Phase 50. | Add `notify`; reuse rusqlite (queue), sha2 (hashing), ed25519-dalek (baseline sig). |
| `src/main.rs` / `src/service.rs` | Entry → `omni_agent::agent_loop(stop_rx)` (async). `stop_rx` is the shutdown signal. | Spawn the watcher at the top of `agent_loop`; tie shutdown to `stop_rx` (D-01). |
| `src/config.rs` | `load()`/`save()` YAML config; no FIM paths | Add a `fim_paths: Vec<String>` field with defaults + optional backend override (D-05). |
| `backend/agent_security_endpoints.py` `POST /{agent_id}/fim-events` | Ingests events, VT-enriches hashes, `insert_one` to `fim_events`, raises malware alert on VT-malicious; `GET` lists | Extend to accept/persist `change_type/hash_before/hash_after/process/user`; keep VT + list (D-04). |
| `capabilities/security_scan.rs` (Phase 50) | `scan_file(path)` | A FIM create/modify event MAY trigger `scan_file` on the changed path (native reputation) — optional link, not required by FIM-02. |

**Net:** the FIM capability + backend endpoint + agent loop all exist. Phase 52 swaps poll-and-hash for an event-driven `notify` watcher, adds a local sqlite queue + rich events, and adds signed baselines + restart drift.

## 2. Detection (FIM-01) — D-01

`notify` crate: `RecommendedWatcher` (inotify / ReadDirectoryChangesW) with a channel of `Event`s. Map `EventKind` → `create|modify|delete|rename`; permission changes surface as modify on most platforms (best-effort). Watcher runs on a background task spawned in `agent_loop`, shutdown via `stop_rx`. On each event: read the changed file, compute `hash_after` (sha2), look up `hash_before` from the baseline / last-known map, gather best-effort `process`/`user` (OS context; `notify` gives none → `unknown` where unavailable), assemble the event doc, enqueue + POST.

## 3. Local queue (FIM-02) — D-02

sqlite `fim_queue(rowid INTEGER PRIMARY KEY, path, change_type, hash_before, hash_after, process_json, user, ts, posted INTEGER DEFAULT 0)` (rusqlite, at the agent data dir). FIM writes rows; 52-04 drains unposted rows → `POST /fim-events`, marks `posted=1`. Phase 53's remediation engine will read this same queue. Ordering/dedup by rowid.

## 4. Baseline + drift (FIM-03) — D-03

`fim_baseline` = a signed snapshot file: `{version, created_at, entries: [{path, sha256}]}` + a detached ed25519 signature using an **agent-local** keypair (generated + persisted at first run, private key local-only). On restart: load baseline, verify sig with the local public key; if invalid/missing → recompute + flag `baseline_reset`. Then diff current file hashes vs baseline entries → emit drift events (added/removed/changed) into `fim_queue`. Re-sign + persist an updated baseline after reconciliation.

## 5. Backend event shape (FIM-02) — D-04

Extend `ingest_fim_event` to accept `{changes: [{path, change_type, hash_before, hash_after, process, user, ts}]}`, persist all fields to `fim_events`, keep the existing VT enrichment on `hash_after`/`new_hash` and the malware-alert-on-malicious path, and keep the `GET` list contract. Additive only.

## 6. Risk

- **Watcher lifecycle/overhead** — bound watched paths; recursive watch on huge trees is costly. Cap + document.
- **Process/user** — best-effort; Linux `fanotify` would give PID but D-01 chose `notify` (no PID). Report `unknown` honestly.
- **Windows** — `notify` uses ReadDirectoryChangesW (not USN). Re-check `x86_64-pc-windows-gnu` after adding the crate.
- **Baseline key** — agent-generated, never shipped; fail-closed on bad signature.
- **No new C deps** (`notify` pure Rust). No new backend pip dep.
