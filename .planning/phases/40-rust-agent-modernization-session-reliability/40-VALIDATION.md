---
phase: 40
slug: rust-agent-modernization-session-reliability
status: approved
nyquist_compliant: true
wave_0_complete: true
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

| Task ID | Plan | Wave | Requirement | Automated Command | File Exists | Status |
|---------|------|------|-------------|-------------------|-------------|--------|
| 40-01-01 | 01 | 1 | RUST-01 | `cargo check --offline && grep -E 'reqwest\s*=' Cargo.toml \| grep -q 'native-tls'` | ✅ | ⬜ pending |
| 40-01-02 | 01 | 1 | RUST-01 | `test -f backend/static/omni-agent-2.1.3-windows.exe && head -c 2 ... \| grep -q 'MZ' && ... && grep -q '_LATEST_AGENT_VERSION = "2.1.3"' backend/agent_heartbeat_endpoints.py && grep -qE '^version = "2.1.3"' agent-install/omni-agent-rs/Cargo.toml` | ✅ | ⬜ pending |
| 40-02-01 | 02 | 1 | SESS-01 | `grep -v '^#' backend/database.py \| grep -c 'revoked_tokens.create_index("jti", unique=True, background=True)' \| grep -qv '^0$'` | ✅ | ⬜ pending |
| 40-02-02 | 02 | 1 | SESS-01 | `cd backend && venv/bin/python -m pytest tests/test_auth_refresh_race.py -q` | ✅ new file (`test_auth_refresh_race.py`) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — updated by executor as tasks land.*

**Manual-only (not in table):** Heartbeat auto-push live round-trip (RUST-01) — see Manual-Only Verifications below, non-blocking per plan-checker.

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — 4/4 tasks carry `<automated>` commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — `test_auth_refresh_race.py` is the only new test file, created by task 40-02-02 itself
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-20 (plan-checker VERIFICATION PASSED)
