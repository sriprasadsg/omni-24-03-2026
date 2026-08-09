---
phase: 34
slug: passkey-and-webauthn-authentication
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-08
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_passkey_auth.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Frontend framework** | Vitest (`npm test`) |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_passkey_auth.py -x`
- **After every plan wave:** `cd backend && python -m pytest tests/ -q` — MUST include `test_authentication.py` and `test_auth_mfa.py` passing unmodified (the literal verification of AUTH-01's "no regression" clause)
- **Before `/gsd-verify-work`:** Full suite green, plus a real `TestClient` HTTP call through both new rate-limited routes (the `response: Response` slowapi pitfall, Phase 25 precedent)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; rows below are the contract to map tasks onto (per `34-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 1 | AUTH-01 | — | Full registration ceremony end-to-end via `soft-webauthn`'s `SoftWebauthnDevice` — options generated, verified, credential persisted to `users.webauthn_credentials` | integration | `pytest tests/test_passkey_auth.py -k registration -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | AUTH-01 | — | Full login ceremony end-to-end, minting a JWT identical in shape (`sub`, `role`, `tenant_id`, `jti`, `exp`) to password-login JWT | integration | `pytest tests/test_passkey_auth.py -k login_verify -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | AUTH-01 | T-34-REPLAY | Challenge is single-use — replaying a `session_id` after successful verification fails | unit | `pytest tests/test_passkey_auth.py -k challenge_replay -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | AUTH-01 | T-34-REPLAY | Expired challenge (past TTL) is rejected | unit | `pytest tests/test_passkey_auth.py -k challenge_expiry -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | AUTH-01 | T-34-CLONE | Sign-count regression detected (decrease from a previously non-zero value); `0→0` is NOT flagged (platform-authenticator caveat) | unit | `pytest tests/test_passkey_auth.py -k sign_count -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1-2 | AUTH-01 (regression) | — | Existing password login tests pass unmodified | regression | `pytest tests/test_authentication.py -x` | ✅ | ⬜ pending |
| TBD | TBD | 1-2 | AUTH-01 (regression) | — | Existing TOTP MFA tests pass unmodified | regression | `pytest tests/test_auth_mfa.py -x` | ✅ | ⬜ pending |
| TBD | TBD | 1-2 | AUTH-01 (regression) | — | SSO coverage: locate SSO tests at plan time (`find backend/tests -iname "*sso*"`); if none exist, add a minimal smoke test rather than leaving uncovered | regression | `pytest backend/tests/ -k sso -x` (verify at plan time) | ⚠ | ⬜ pending |
| TBD | TBD | 1 | AUTH-01 | — | `authentication_endpoints.py` stays ≤500 lines (new code goes in new `passkey_*` files) | lint | `wc -l backend/authentication_endpoints.py` | ✅ | ⬜ pending |
| TBD | TBD | 2 | AUTH-01 | — | Frontend passkey enrollment (profile page) + login button build clean and are reachable | build + manual | `npm run build` | ✅ (existing files) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_passkey_auth.py` — new file; clone `test_auth_mfa.py`'s helper block, extended with `SoftWebauthnDevice` for full-ceremony simulation
- [ ] Framework install: `pip install "webauthn>=3.0.0,<4.0.0" "soft-webauthn>=0.1.4,<0.2.0"` — both behind `checkpoint:human-verify` (Package Legitimacy Audit SUS flags)
- [ ] `npm install @simplewebauthn/browser@^13.3.0` — frontend companion

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Real-browser passkey registration + login round-trip | AUTH-01 | `soft-webauthn` simulates the authenticator, but the browser `navigator.credentials` plumbing + base64url conversions can only be proven in a real browser | With a platform authenticator available (or Chrome DevTools' virtual authenticator), enroll a passkey from the profile page, log out, log in with the passkey, confirm a working session |
| Lost-passkey messaging | AUTH-01 | UI copy check | Confirm the passkey-management UI states the original login method remains valid (per resolved Open Question 3) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-08)
