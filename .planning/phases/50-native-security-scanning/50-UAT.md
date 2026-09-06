---
status: passed
phase: 50-native-security-scanning
source: [50-SUMMARY.md]
started: 2026-07-30T21:00:00Z
updated: 2026-07-30T21:15:00Z
method: CLI — real security_scan engine driven against an actual EICAR file + a seeded on-disk feed cache (throwaway integration test, run then removed); backend endpoints via hermetic + code evidence. No browser needed (no UI in this phase).
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "passed::scenarios=0"
---

## Tests

### 1. NSCAN-01 — offline file scan (Clean/Suspicious/Malicious + confidence)

result: [pass — CLI, end-to-end]
evidence: Drove the REAL `capabilities::security_scan::scan_file` against an actual EICAR file with a seeded on-disk feed at the path `feed_bundle` reads. Results:

  - EICAR file → `{verdict: Malicious, confidence: 0.95, matched: [hash], sha256: 275a021b…}` (hash-sig hit; the computed SHA256 matched the seeded signature).
  - Benign file → `{verdict: Clean, confidence: 1.0}`.
  - File containing the EICAR literal but a DIFFERENT hash → `{verdict: Malicious, confidence: 0.9, matched: [Eicar]}` (aho-corasick literal match, severity high) — proves the YARA-fallback pattern path.
  Fully offline, no network at scan time.

### 2. NSCAN-02 — URL/IP/hash reputation from the bundled feed (no live lookup)

result: [pass — CLI]
evidence: `scan_hash(EICAR)` → Malicious; `scan_ip("198.51.100.9")` (in a seeded /24) → Malicious; `scan_url("http://malware.example.test/x")` (seeded domain) → Malicious — all from the local cached feed, zero scan-time network. `feed_bundle` verifies the ed25519 signature before loading (fail-closed) and degrades to `unknown` when absent (unit-tested).

### 3. NSCAN-03 — scan API + verdict ingestion

result: [pass — code + hermetic; live-route restart pending]
evidence: `instructions.rs` dispatches `scan_file/url/hash/ip` → engine → POST to `/api/agents/{id}/security/scan-result`. Backend ingestion tested: Clean persists (no alert), Malicious raises a `source:native` critical alert, tenant-scoped — 3 hermetic tests. `GET /api/agents/security/feed-bundle` serves the signed bundle (4 tests; signature verifies with the public key). Both routers registered in router_registry. NOTE: the long-running dev backend predates these routers (404) — a **restart** is needed to exercise the routes on the LIVE server; the routes + logic are proven by the registered-router + hermetic tests.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
caveat: the live dev backend needs a restart to serve the new routes (predates phase 50); NSCAN-03 verified by registration + hermetic tests, not yet by a live HTTP round-trip. yara-x full-rule engine deferred (backlog 999.4) — the shipped hash-sig + aho-corasick fallback is what was verified.

## Gaps

None in delivered scope. Deferred: full YARA-rule engine (999.4); live-route HTTP round-trip after a backend restart.
