---
phase: 74
slug: interactive-remote-desktop-control-for-tenant-admins-upgrade
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-26
---

# Phase 74 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

Multi-language phase — backend (Python/pytest), canonical agent (Rust/cargo test), legacy agent (Python, no harness yet), frontend (Vitest). Backend is the primary sampled suite; Rust/agent-side changes get `cargo check`/`cargo test` per commit where a Windows-cfg'd target is available.

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (backend) · `cargo test` inline `#[cfg(test)]` modules (Rust agent) · loose `test_*.py` files, no harness (Python agent) · Vitest (frontend) |
| **Config file** | `pytest.ini` (backend) — `testpaths = . backend`, `asyncio_mode = auto`; no config for the other three |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_remote_access.py -x` |
| **Full suite command** | `backend/venv/bin/python -m pytest` (must use `backend/venv/bin/python` — system Python has no pytest installed) + `npx vitest run src/__tests__` |
| **Estimated runtime** | ~90–120s full backend suite (estimated; v4.1 close session reported 2475 backend tests, no wall-clock recorded this session) |

---

## Sampling Rate

- **After every task commit:** `backend/venv/bin/python -m pytest backend/tests/test_remote_access.py -x` (+ `cargo check` for any Rust-side diff)
- **After every plan wave:** Full backend suite (`backend/venv/bin/python -m pytest`) + `npx vitest run src/__tests__`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

*Task IDs are assigned by `/gsd-plan-phase`'s planner step — this table seeds the decision→test mapping now; exact Task ID/Plan/Wave columns are filled in once PLAN.md files exist.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | D-06 (`control:remote_access` permission gate) | — | Request without `control:remote_access` is denied the way `view:remote_access` already denies unpermitted callers | unit | `pytest backend/tests/test_remote_access.py -k control_permission -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Protocol (control session uses `/user`, not `/viewer`) | — | Control-mode session relays input both directions; view-mode stays receive-discarding as today | integration | `pytest backend/tests/test_remote_access.py -k relay -x` | ✅ partial (underlying `/user` relay tests exist; control-frame-shape test is new) | ⬜ pending |
| TBD | TBD | TBD | D-02 (no interactive session → refusal) | T-74-01 | Agent refuses control request gracefully when Session-0/no interactive user, no hang | unit (Rust) | `cargo test --target x86_64-pc-windows-gnu` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-09 (persistent stop-control indicator) | — | Endpoint user sees on-screen indicator + can end session with one click | manual | N/A | ❌ W0 (manual-only) | ⬜ pending |
| TBD | TBD | TBD | D-12 (WS drop ends session, no silent resume) | T-74-02 | Reconnect after tunnel drop requires fresh consent, never auto-resumes control | integration | `pytest backend/tests/test_remote_access.py -k disconnect -x` | ❌ W0 (extend existing sentinel-propagation pattern) | ⬜ pending |
| TBD | TBD | TBD | Audit trail (session start/end/consent-decision) | T-74-03 | Every control session and consent decision writes an append-only audit record with no private/sensitive payload | unit | `pytest backend/tests/test_control_session_audit.py -x` | ❌ W0 (new file) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_remote_access.py` — extend with `control:remote_access` permission tests and control-mode frame-relay tests
- [ ] `backend/tests/test_control_session_audit.py` — new file for the new audit service (model on whatever test conventions the existing `remediation_audit_service.py` tests use, if any — check before writing from scratch)
- [ ] Rust `#[cfg(test)]` module inside the extended `remote_access.rs` (or a new `consent_ui.rs`) — unit-test frame-parsing logic (platform-independent parts) even though `SendInput`/`CreateProcessAsUserW` calls themselves are `checkpoint:human-verify` only
- [ ] Python agent — no `conftest.py`/test harness exists under `agent/` for capability-level tests today; the plan must decide whether to establish minimal test scaffolding now or treat new Python-agent code as `checkpoint:human-verify` only

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Consent dialog appears in the interactive user's session and blocks control until Accept | D-01, D-03 | Requires a real logged-in Windows desktop session; `CreateProcessAsUserW`/session injection cannot be exercised in CI | On a Windows VM with an active logged-in user, request a control session from the dashboard; confirm a dialog appears showing requester identity, and that mouse/keyboard input has no effect until Accept is clicked |
| Mouse/keyboard input actually moves the remote cursor / types on the remote desktop (`SendInput`) | D-05 | Requires a real Windows desktop and a human watching the screen react | After Accept, move the admin-side mouse over the stream and type; confirm the remote cursor and an open text field on the Windows box reflect it in real time |
| Endpoint-side persistent stop-control indicator and one-click disconnect | D-09 | Requires a real Windows desktop with a visible always-on-top overlay | During an active control session, confirm the overlay is visible and clicking it ends the session immediately on both sides |
| Platform-admin cross-tenant force-kill | D-11 | Requires two real tenants and a live session to kill | As a platform-admin, force-kill another tenant's active control session and confirm both parties are disconnected |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
