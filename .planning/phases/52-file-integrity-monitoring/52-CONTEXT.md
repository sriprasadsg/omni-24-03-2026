# Phase 52 — File Integrity Monitoring — CONTEXT

**Milestone:** v3.4 (Native Security Scanning & Autonomous Remediation) — phase 3 of 5 (50→51→**52**→53→54)
**Requirements:** FIM-01, FIM-02, FIM-03
**Depends on:** Phase 50 (agent `feed_bundle` + the `ed25519-dalek` Cargo dep reused for baseline signing; the scan engine that a FIM event can trigger)

## Goal

Turn the agent's poll-and-hash FIM stub into a real event-driven integrity monitor: watch configured critical paths for create/modify/delete/permission changes at low overhead, capture rich change events (before/after hash, process, user) into a local queue for the remediation engine, and maintain signed baseline snapshots with drift detection on restart.

## Success criteria (what must be TRUE)

1. The agent detects create/modify/delete/permission changes on configured critical paths using native OS facilities, at low overhead (FIM-01).
2. Each change event includes before/after hash, process tree, and user context, routed to the local remediation queue (FIM-02).
3. Baseline snapshots are signed and drift against them is detected on agent restart (FIM-03).

## Locked decisions

- **D-01 — Detection: the `notify` crate, event-driven (FIM-01).** Replace the per-heartbeat poll-and-hash with a background watcher using `notify` (inotify on Linux, ReadDirectoryChangesW on Windows) — real create/modify/delete/rename events at low overhead, one pure-Rust cross-platform impl. The watcher runs as a background task started at the top of `agent_loop()` (a structural shift: the FIM `Capability::collect()` now reports watcher *status/summary*, while actual events flow via the queue + POST). Process-tree + user context are **best-effort** from OS/event context (`notify` events don't carry a PID; attribute where the platform allows, else `unknown`). *Deviation noted:* `notify` uses ReadDirectoryChangesW, not the USN Journal, on Windows — the standard file-change API, accepted in place of the literal "USN Journal."
- **D-02 — Local queue + backend report (FIM-02).** Change events are written to a local sqlite `fim_queue` table (reusing `rusqlite`) that Phase 53's remediation engine drains, **and** POSTed to the existing backend `POST /api/agents/{id}/security/fim-events`. Ordering/dedup by rowid. The local queue is the agent-side handoff to Phase 53; the backend keeps the audit/dashboard view (+ its existing VirusTotal hash enrichment).
- **D-03 — Signed baseline + drift (FIM-03).** At first run the agent computes a baseline snapshot (watched path → sha256), signs it with an **agent-local ed25519 key** (reuse `ed25519-dalek`; the agent generates + persists its own baseline-signing keypair, private key local-only), and stores it. On restart, the agent **verifies the baseline signature** (tamper-evidence) then diffs current state vs baseline → emits drift events into the queue. A missing/invalid-signature baseline is fail-closed: do not trust it — recompute and flag a baseline reset.
- **D-04 — Event shape (FIM-02).** `{path, change_type: create|modify|delete|permission|rename, hash_before, hash_after, process: {pid?, name?, tree?}, user, ts, source: "fim"}`. The backend `fim-events` endpoint is extended to accept/persist these fields; its existing VirusTotal hash enrichment + `GET` list path stay intact.
- **D-05 — Reuse, don't replace.** `ed25519-dalek` (Phase-50 dep) for baseline signing; the existing backend `fim-events` endpoint extended (not replaced); watched paths from a new `config.rs` `fim_paths` field with sane defaults + optional backend override.

## Scope fences (MUST NOT)

- MUST NOT poll-and-hash large trees for change detection (event-driven via `notify`; polling only for the restart baseline diff).
- MUST NOT block or crash the agent if the watcher fails to start — degrade (log + continue; FIM is best-effort, the heartbeat loop must keep running).
- MUST NOT break the existing backend `fim-events` VirusTotal-enrichment or `GET` list path.
- MUST NOT introduce a C dependency (`notify` is pure Rust); re-check `x86_64-pc-windows-gnu`.
- MUST NOT trust an unsigned or signature-failed baseline — fail-closed, recompute + flag reset.

## Pitfalls

- **Long-running watcher:** the `notify` watcher is threaded/long-lived — spawn it as a background task with graceful shutdown tied to the existing `stop_rx`; never block the heartbeat loop.
- **Process/user attribution:** `notify` events carry no PID — best-effort only; don't over-promise a full process tree where the OS doesn't provide it.
- **Watched-path config:** ship bounded defaults (system bins, `/etc`, key stores; Windows system dirs) + optional backend override; cap the watched set to keep overhead low.
- **Baseline key:** agent-generated, persisted locally, **never shipped** in an installer; rotate on baseline reset.
- **Windows cross-compile:** `cargo check --target x86_64-pc-windows-gnu` after adding `notify`.

## Plan breakdown

| Plan | Wave | Scope | Requirements |
|------|------|-------|--------------|
| 52-01 | 1 | Backend: extend `fim-events` ingestion to accept/persist the rich event shape (change_type/before-after/process/user) + tests; keep VT + list path | FIM-02 |
| 52-02 | 1 | Agent: `notify`-based FIM watcher module + local sqlite `fim_queue` + event assembly (best-effort process/user) + `notify` Cargo dep | FIM-01/02 |
| 52-03 | 2 | Agent: signed baseline snapshot (ed25519) + restart drift detection → queue | FIM-03 |
| 52-04 | 3 | Agent: start the watcher in `agent_loop()` (graceful shutdown) + drain `fim_queue` → POST `fim-events` + `config.rs` `fim_paths` + windows cross-check | FIM-01/02 |
