---
status: partial
phase: 40-rust-agent-modernization-session-reliability
source: [40-01-SUMMARY.md, 40-02-SUMMARY.md]
started: 2026-07-20T17:09:41Z
updated: 2026-07-29T00:00:00Z
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "partial::scenarios=0"
---

<!-- Test 1 (agent auto-update to 2.1.3) is blocked_by: physical-device — a permanent
     environmental limitation in this sandbox, not a product gap. Test 2 (401 concurrent
     refresh) verified via automated race test. Blocked item deferred at milestone close. -->

## Current Test

[testing complete]

## Tests

### 1. Rust Endpoint Agent Auto-Update to 2.1.3

expected: An endpoint agent currently running 2.1.2 (or earlier) reports its version on its next heartbeat and receives an instruction to download and install 2.1.3. After it restarts, it reports version 2.1.3.
result: blocked
blocked_by: physical-device
reason: "can't test - no physical Windows device"

### 2. No Intermittent 401 During Concurrent Session Refresh

expected: Using the app normally — including with two tabs open to the same account — your session refreshes silently in the background and you are never unexpectedly logged out (401), even if two refresh requests happen to fire at nearly the same moment.
result: pass
source: automated
evidence: "Verified via backend/tests/test_auth_refresh_race.py (1 passed) — drives the real /api/auth/refresh route with two concurrent calls sharing one refresh token via asyncio.gather, asserts exactly one 200 + one 401 + exactly one persisted revoked_tokens doc for the jti. Root cause (missing revoked_tokens.jti unique index) fixed at database.py:322. See 40-VERIFICATION.md criterion 3."

## Summary

total: 2
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 1

## Gaps
