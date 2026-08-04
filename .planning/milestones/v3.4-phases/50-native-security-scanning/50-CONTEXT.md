# Phase 50 — Native Security Scanning — CONTEXT

**Milestone:** v3.4 (Native Security Scanning & Autonomous Remediation) — first phase (50→51→52→53→54)
**Requirements:** NSCAN-01, NSCAN-02, NSCAN-03
**Depends on:** none (foundational — defines the signed-feed-bundle mechanism reused by Phase 51 VULN and Phase 52 FIM)

## Goal

Give the OmniAgent an offline scan engine: file scanning (bundled YARA rules + a hash-signature DB), URL/IP/domain/hash reputation from signed bundled threat-intel feeds (no live lookup), exposed as a `scan_file`/`scan_url`/`scan_hash`/`scan_ip` capability callable by an operator or triggered by events — replacing the external VirusTotal dependency with native, air-gapped capability.

## Success criteria (what must be TRUE)

1. The agent scans a file fully offline and returns Clean/Suspicious/Malicious + a confidence score, matching a bundled signature + YARA set (NSCAN-01).
2. The agent returns a reputation verdict for a URL/IP/domain/hash from bundled feeds updated only via signed bundle — no network call at scan time (NSCAN-02).
3. `scan_file`/`scan_url`/`scan_hash`/`scan_ip` are invokable by operator and internal event, with verdicts ingested per-tenant on the backend (NSCAN-03).

## Locked decisions

- **D-01 — Scan engine: `yara-x` + hash-signature DB, pure Rust (NSCAN-01).** File scanning uses `yara-x` (VirusTotal's pure-Rust YARA engine, BSD-3) for rule matching plus a bundled hash-signature table (SHA256/MD5 known-bad) queried via the existing `rusqlite` dep. **No C libraries** (no `libclamav`, no `libyara`). Verdict derivation: a hash hit → Malicious (high confidence); a YARA rule match → Suspicious/Malicious by the rule's declared severity; neither → Clean. The agent cross-compiles to Windows — `yara-x`'s Windows cross-build MUST be verified early (`cargo check --target x86_64-pc-windows-gnu`, see [[agent-rust-windows-crosscheck]]).
- **D-02 — Reputation: native bundled feeds only, no VirusTotal (NSCAN-02).** `scan_url`/`scan_ip`/`scan_hash` resolve against signed, bundled feeds cached locally — **zero network at scan time**. The existing VirusTotal-based `fim-events` path in `agent_security_endpoints.py` is left **untouched** (Phase 52 owns FIM); the new scan API is native-only.
- **D-03 — Feed distribution: signed bundle (the milestone foundation).** The backend builds a SQLite feed DB — tables `hash_sigs`, `yara_rules`, `url_feed`, `ip_feed`, and a `manifest` (version, created_at) — plus a **detached ed25519 signature** over the bytes. Served at `GET /api/agents/security/feed-bundle` (versioned; the agent sends its current version and gets a no-op when current). The agent verifies the signature with an **embedded ed25519 public key** before loading, caches locally, and **graceful-degrades** (missing/invalid bundle → scans return an `unknown`/degraded verdict, never crash — mirrors the `agent_asn_service` lazy graceful-degrade). This mechanism is reused by Phase 51 (vuln feed) and Phase 52 (FIM baselines).
- **D-04 — Code lands in `agent-install/omni-agent-rs` only.** Confirmed the shipped tree (`agent_rust_builder.py`: the legacy `agent-rust` tree is "no longer shipped by any installer"). Add a new `capabilities::security_scan` module; dispatch via `instructions.rs` command strings `scan_file`/`scan_url`/`scan_hash`/`scan_ip`, mirroring the existing `"network_scan"` case (capability fn → POST verdict → status JSON).
- **D-05 — Backend ingestion clones the existing malware-alert pattern.** Native verdict ingestion mirrors `agent_security_endpoints.py::_raise_malware_alert` — tenant-scoped, persists the verdict, raises a critical security alert on Malicious via the existing alert path — but tagged `source: "native"` (not `virustotal`).

## Scope fences (MUST NOT)

- MUST NOT link `libclamav` or `libyara` C libraries — pure-Rust `yara-x` only (D-01).
- MUST NOT make any external/live network lookup at scan time (VirusTotal, NVD, any API) — bundled feeds only (D-02).
- MUST NOT modify or break the existing VirusTotal-based `fim-events` path in `agent_security_endpoints.py`.
- MUST NOT place code in the legacy `agent-rust/` tree (not shipped).
- MUST NOT load a feed bundle whose ed25519 signature fails verification — fail-closed to degraded, never load unverified data.
- MUST NOT crash or block the agent when the feed bundle is absent/corrupt — graceful-degrade to `unknown` verdicts.

## Pitfalls

- **Windows cross-compile of `yara-x`** — verify at the start of the engine plan (`cargo check --target x86_64-pc-windows-gnu`; target + mingw installed per [[agent-rust-windows-crosscheck]]). If a `yara-x` feature pulls a C accelerator, disable it (`default-features = false`).
- **ed25519 key management** — public key embedded in the agent (const/config); the private signing key stays backend-side, never shipped in any installer.
- **Stale-cache rebuild** ([[two-rust-agent-trees]]): `agent_rust_builder.py` rebuilds the exe when any `.rs`/`Cargo.toml` is newer — the new module + Cargo deps will trigger it; confirm the rebuilt exe actually contains the scan capability.
- **Binary size** — `yara-x` adds weight; acceptable for the endpoint agent, note in the summary.

## Plan breakdown

| Plan | Wave | Scope | Requirements |
|------|------|-------|--------------|
| 50-01 | 1 | Backend signed feed-bundle build/sign/serve — SQLite bundle + ed25519 detached sig + `GET /api/agents/security/feed-bundle` (versioned) + tests | NSCAN-02/03 (foundation) |
| 50-02 | 1 | Agent feed-bundle client (Rust) — fetch + ed25519 verify + local sqlite cache + graceful-degrade | NSCAN foundation |
| 50-03 | 2 | Agent scan engine `capabilities::security_scan` — `scan_file` (yara-x + hash-sig DB), `scan_url/ip/hash` (feed lookup) → verdict JSON | NSCAN-01/02 |
| 50-04 | 2 | Backend native-verdict ingestion endpoint + capability registration + Malicious alert + tests | NSCAN-03 |
| 50-05 | 3 | Agent `instructions.rs` dispatch (`scan_file/url/hash/ip` → capability → POST verdict) + `yara-x`/`ed25519-dalek` Cargo deps + Windows cross-check | NSCAN-03 |
