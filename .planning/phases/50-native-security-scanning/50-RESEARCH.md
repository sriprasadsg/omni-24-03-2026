# Phase 50 — Native Security Scanning — RESEARCH

Codebase-grounded. Refs verified against the tree on 2026-07-30.

## 1. Existing-surface audit

| Surface | State | Use |
|---------|-------|-----|
| `agent-install/omni-agent-rs/src/capabilities/` | Trait-based capability modules: `fim.rs`, `vulnerability_scan.rs`, `pii_scanner.rs`, `runtime_security.rs`, `network_discovery.rs`, `ueba.rs`, `sbom.rs`, … **No malware/reputation scanner.** | Add `security_scan.rs` mirroring the module + `pub fn` pattern (`network_discovery::scan_now() -> Value`). `fim.rs`/`vulnerability_scan.rs` are Phase 52/51's extension targets, not this phase's. |
| `src/instructions.rs` | Command dispatcher: `match item.command { "network_scan" => { let scan = capabilities::network_discovery::scan_now(); … POST to /api/agents/{host}/discovery/results; return status json } … }` | Clone the `network_scan` arm for `scan_file`/`scan_url`/`scan_hash`/`scan_ip`. |
| `backend/agent_security_endpoints.py` | `POST /{agent_id}/fim-events` ingests FIM hashes and enriches via **VirusTotal** (`virustotal_client.enrich_file_hashes`); `_raise_malware_alert(...)` inserts a critical alert on a malicious hash. | The external dep this milestone replaces. **Leave the VT/FIM path intact** (D-02); clone `_raise_malware_alert` for native verdicts (D-05). |
| `backend/agent_rust_builder.py` | Builds + serves `omni-agent-rs`; rebuilds exe when any `.rs`/`Cargo.toml` is newer. States the legacy `agent-rust` tree is "no longer shipped by any installer." | Distribution tree = `omni-agent-rs` (D-04). New files trigger rebuild. |
| `omni-agent-rs/Cargo.toml` deps | `reqwest` (native-tls, blocking+async), `serde`/`serde_json`, `rusqlite` (bundled), `sha2`, `hex`, `regex`, `tokio`, `chrono`. No YARA/crypto-sig crate. | Reuse `rusqlite` for the feed DB, `sha2`/`hex` for file hashing. Add `yara-x` + `ed25519-dalek` (50-05). |
| `backend/agent_asn_service.py` (Phase 46) | Lazy load of a vendored data file with graceful-degrade when absent. | Pattern for the agent's feed-bundle graceful-degrade (D-03). |

**Net:** the capability + dispatch + verdict-POST + malware-alert scaffolding all exist. Phase 50 adds (a) a signed-feed-bundle mechanism (backend build/serve + agent fetch/verify/cache) and (b) a `security_scan` capability (yara-x + hash DB + feed lookups) wired through the existing dispatcher.

## 2. Scan engine (NSCAN-01) — D-01

- **`yara-x`** (crates.io, VirusTotal, BSD-3-Clause): pure-Rust YARA implementation. `yara_x::compile(rules_src)` → `Rules`; `Scanner::new(&rules).scan(&bytes)` → matching rules. No `libyara` C dep. **Windows cross-compile risk:** some optional features use C accelerators — build with `default-features = false` and verify `cargo check --target x86_64-pc-windows-gnu` before committing to the engine (50-03 Task 0 gate).
- **Hash-signature DB:** SHA256 (and MD5 for ClamAV-`.hdb` compatibility) of the file, looked up in the bundled `hash_sigs` table via `rusqlite`. A hit → Malicious. File hashing via existing `sha2`.
- **Verdict + confidence:** `Malicious` (hash hit, or YARA rule tagged `severity=critical/high`, confidence ~0.9–1.0); `Suspicious` (YARA rule `severity=medium/low`, confidence ~0.5–0.7); `Clean` (no match, confidence 1.0). Returned as `{verdict, confidence, matched: [rule/hash names], engine: "native"}`.

## 3. Reputation (NSCAN-02) — D-02

`scan_hash` → `hash_sigs` lookup. `scan_url`/`scan_ip` → `url_feed` (exact/domain match) / `ip_feed` (CIDR containment). All from the locally-cached signed feed DB. No network at scan time. Unknown → `{verdict: "unknown", reason: "not in feed"}` (an explicit not-in-feed answer, not an error).

## 4. Signed feed bundle (NSCAN foundation) — D-03

- **Backend build:** assemble a SQLite file with `hash_sigs(sha256, md5, verdict, name)`, `yara_rules(name, severity, source)`, `url_feed(pattern, kind, verdict)`, `ip_feed(cidr, verdict)`, `manifest(version, created_at)`. Sign the file bytes with an ed25519 private key (`cryptography`/`PyNaCl` server-side) → detached `.sig`. Serve `GET /api/agents/security/feed-bundle` returning bundle + version headers; accept `?have=<version>` to no-op when current.
- **Agent side:** on startup / periodic, GET the bundle, verify the detached sig with an **embedded ed25519 public key** (`ed25519-dalek`, pure Rust), and only then write it to the local cache path (`rusqlite` open). Verify-fail or absent → keep the previous good cache, else degrade to `unknown` verdicts. Never load unverified bytes (fail-closed).
- **Key mgmt:** public key is a `const`/config value compiled into the agent; the private key lives backend-side only, never in any installer artifact.

## 5. Dispatch + ingestion (NSCAN-03) — D-04/D-05

- **Agent:** `instructions.rs` arms `scan_file`/`scan_url`/`scan_hash`/`scan_ip` → `capabilities::security_scan::{scan_file,scan_url,scan_hash,scan_ip}(param)` → POST verdict to `POST /api/agents/{agent_id}/security/scan-result` → return status JSON (mirrors `network_scan`).
- **Backend:** `scan-result` ingestion is tenant-scoped, persists the verdict, and on `Malicious` raises a critical alert via the existing path (clone `_raise_malware_alert`, `source: "native"`). Capability registered so the operator/console can trigger scans (surfaced fully in Phase 54).

## 6. Deps & risk

- **New crates:** `yara-x` (BSD), `ed25519-dalek` (pure Rust). No new C libs. **New pip:** none (backend signing via existing `cryptography`; confirm it's installed — it is, per webauthn/crypto usage).
- **Top risk:** `yara-x` Windows cross-build — gated first in 50-03. Fallback if it can't cross-build: ship the hash-sig + regex/aho-corasick matcher for NSCAN-01's signature half and defer YARA-rule support to a follow-up (keeps the phase moving; documented, not silent).
- **Air-gap/fail-closed:** no scan-time network; unverified bundles never loaded; absent bundle → degraded, agent stays up.
