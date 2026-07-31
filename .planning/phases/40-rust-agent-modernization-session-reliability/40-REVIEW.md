---
phase: 40-rust-agent-modernization-session-reliability
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - agent-install/omni-agent-rs/Cargo.toml
  - backend/agent_heartbeat_endpoints.py
  - backend/database.py
  - backend/tests/test_auth_refresh_race.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: issues_found
---

# Phase 40: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found (info only)

## Summary

Rust agent 2.1.3 release, `revoked_tokens.jti` unique index, concurrent-refresh
regression test. Reviewed for memory safety, TLS, credential handling.

- `Cargo.toml`: reqwest pins `native-tls` explicitly (`["json","blocking","native-tls"]`),
  matching tokio-tungstenite. Correct; no TLS/memory-safety concern here (default-features
  hardening lands in phase 45).
- `database.py:322`: `revoked_tokens.create_index("jti", unique=True, background=True)`
  present adjacent to the TTL index — closes the atomicity gap `refresh_access_token`
  already assumed. Correct.
- Heartbeat auto-push gate correctly bounds self-update to Windows + `>= 2.0.5` via a
  regex version parse; dedups against `pending`+`sent`. Sound.

No Critical or Warning findings. Two Info items.

## Info

### IN-01: Concurrent-refresh regression test is probabilistic

**File:** `backend/tests/test_auth_refresh_race.py:124-134`
**Issue:** The two-request HTTP-level race is inherently non-deterministic. Without
the index, MongoDB duplicate-upsert only occurs on ~10% of races (per the summary's
own scratch measurement), so this test can pass vacuously even with the fix removed.
The summary acknowledges this. It is deterministically green *with* the fix.
**Fix:** Acceptable as-is for a minimal repro. If stronger regression protection is
wanted, keep the committed driver-level loop (N=200) as a separate slow/opt-in test
so absence of the index reliably fails.

### IN-02: Version parse silently ignores malformed version strings

**File:** `backend/agent_heartbeat_endpoints.py:136-143`
**Issue:** `_parse_ver` returns `None` on any non-`X.Y.Z` string; such agents are
never auto-pushed an update and never logged. A corrupted `version` field means an
agent silently stops receiving updates.
**Fix:** Optional — log at debug when a heartbeat reports an unparseable version so
stuck agents are discoverable.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
