# Phase 50 — Native Security Scanning — EXECUTION SUMMARY

**Status:** Executed 2026-07-30. 5 plans, commits `bc3b319..3fcaeb7`. NSCAN-01/02/03.

## Per-plan

- **50-01** (`bc3b319`/`1ccc380`) — `agent_security_feed_service.py` builds a SQLite feed bundle (hash_sigs incl. EICAR, yara_rules, url_feed, ip_feed, manifest) + ed25519 detached signature (private key generated once, 0600, gitignored, never returned); `GET /api/agents/security/feed-bundle` (`verify_agent_key` auth, `?have=` no-op). 4 tests.
- **50-02** (`a8a3a07`) — added `ed25519-dalek` (pure Rust; linux + windows-gnu clean). `capabilities/feed_bundle.rs`: fetch + verify-before-load (fail-closed) + sqlite cache + `lookup_hash/url/ip` + graceful degrade. **Real feed public key embedded** (folded 50-05's key step forward). 5 unit tests.
- **50-03** (`861d2d6`) — **yara-x REJECTED at the spike** (pulls wasmtime + cranelift JIT — bloat/cross-compile risk). Took the documented fallback: `capabilities/security_scan.rs` = SHA256 hash-sig lookup + `aho-corasick` literal-pattern matching over the feed's rule string literals; `scan_hash/url/ip` via feed lookups. Bounded scan size, graceful degrade. windows-gnu builds in 4.6s. 4 unit tests. → **backlog 999.4** for full YARA.
- **50-04** (`5876207`/`3ef9dc8`) — `agent_security_scan_endpoints.py` `POST /security/scan-result` (`verify_agent_key`): persist to `security_scan_results` + raise a critical `source:native` alert on Malicious (clones the malware-alert shape, no VT). VT fim-events path untouched. 3 tests.
- **50-05** (`3fcaeb7`) — `instructions.rs` four scan command arms (refresh feed + scan in `spawn_blocking`, enrich verdict with type/target, POST to scan-result). Builds linux + windows-gnu.

## Verification

- Backend `tests/`: **1453 passed** (+7 new), 35 skipped, 6 pre-existing fails (3 known + 3 support-pollution) — **no new regressions**.
- Agent: `cargo test --lib` **9/9** (feed_bundle 5 + security_scan 4); `cargo build` + `cargo check --target x86_64-pc-windows-gnu` both clean.
- 6 `integration.rs` failures are **pre-existing stale tests** (capability count hardcoded 15, actual 20 — drifted before phase 50; unrelated to the new free-fn modules).

## Deviations

1. **yara-x → aho-corasick fallback** (D-01 fallback path taken). Full YARA rules deferred → backlog 999.4. Reason: yara-x pulls wasmtime (JIT), unacceptable for a lean cross-compiled agent.
2. **Feed public key embedded in 50-02** (not 50-05) — done early since the backend key was available; 50-05 reduced to build-gate + dispatch.

## Pending (UAT)

Real end-to-end EICAR scan (write EICAR file → `scan_file` command → Malicious verdict ingested + native alert) needs a running agent + feed cache — deferred to UAT. Logic unit-tested; not yet exercised against a live feed cache on disk.
