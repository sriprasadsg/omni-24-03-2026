---
phase: 40
slug: rust-agent-modernization-session-reliability
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-20
---

# Phase 40 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest 9.1.0 + pytest-asyncio (`asyncio_mode = auto`) |
| **Framework (Rust)** | None exists — no `#[test]`/`#[cfg(test)]` in `agent-install/omni-agent-rs/src/*.rs`. `cargo check`/`cargo build --release` are the only automated gates for the Rust side. Not a gap this phase needs to close (RUST-01 is a pure dependency/build task, no new logic to unit-test). |
| **Config file** | `pytest.ini` (repo root) |
| **Quick run command (backend)** | `cd backend && venv/bin/python -m pytest tests/test_authentication.py -q` |
| **Quick run command (Rust)** | `cd agent-install/omni-agent-rs && cargo check --offline` |
| **Full suite command (backend)** | `cd backend && venv/bin/python -m pytest -q` |
| **Full suite command (Rust)** | `cd agent-install/omni-agent-rs && cargo build --release --target x86_64-pc-windows-gnu` |
| **Estimated runtime** | ~30-60s (backend quick), full backend suite per STATE.md baseline; Rust cross-compile build ~1-3 min |

---

## Sampling Rate

- **After every task commit:** `cargo check --offline` (Rust track) / `pytest backend/tests/test_authentication.py -q` (auth track)
- **After every plan wave:** `cargo build --release --target x86_64-pc-windows-gnu` (Rust) / full backend suite (auth)
- **Before `/gsd-verify-work`:** Both full suites green (or only the 2 pre-existing, documented-unrelated backend failures: `test_e2e_integration` golden path, `test_rust_heartbeat_parity`)
- **Max feedback latency:** ~60s

---

## Per-Task Verification Map

*Task IDs are assigned during planning — this table is filled in by the planner against the requirement→test map below. Requirement-level mapping (pre-planning):*

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| RUST-01 | Crate bumps compile clean with TLS feature pinned | build/smoke | `cargo check --offline` | ✅ no new file needed |
| RUST-01 | Cross-compiled Windows binary produces a valid PE, correct version string | build/smoke | `cargo build --release --target x86_64-pc-windows-gnu` + inspect `CARGO_PKG_VERSION` embed | ✅ no new file needed |
| RUST-01 | Heartbeat auto-push fires for an agent reporting the old version | integration, manual-only | No automated harness exists (requires a running Windows endpoint) | ❌ Wave 0 gap — manual-only, see below |
| SESS-01 | Concurrent refresh: exactly one of two simultaneous `/refresh` calls with the same token succeeds | unit/integration | `pytest backend/tests/test_authentication.py -k concurrent_refresh -x` (new test) | ❌ Wave 0 gap |
| SESS-01 | `revoked_tokens.jti` unique index actually exists and rejects duplicate inserts | integration | Same new test area, or a dedicated index-assertion test against real Mongo | ❌ Wave 0 gap |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New test case for concurrent `/refresh` race — add to `backend/tests/test_authentication.py` (currently well under the 500-line CLAUDE.md limit) or a new `test_auth_refresh_race.py` if live-Mongo fixture scaffolding needed isn't already present there
- [ ] No Rust unit-test framework needed — `cargo check`/`cargo build` remain the correct automated gate for RUST-01 (pure dependency/build task)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Heartbeat auto-push actually fires for an agent reporting the old version | RUST-01 | No automated harness for live heartbeat→instruction→self-update round-trip; requires a running Windows endpoint, which this Linux sandbox cannot provide | Deploy the 2.1.3 build behind a real/test tenant, confirm an existing 2.1.2 (or earlier) agent receives and applies the `agent_update` instruction via its normal heartbeat cycle |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
