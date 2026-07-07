---
phase: 29
slug: public-trust-center
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-07
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_trust_center.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Estimated runtime** | ~10-15 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_trust_center.py -x`
- **After every plan wave:** `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green, plus an actual `TestClient` HTTP call through both new public routes (not just an import check) per Pitfall 2's `response: Response` slowapi failure mode
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `29-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T-29-01 | 29-01 | 1 | TRUST-01 | — | Trust profile persists across a simulated restart (fresh `get_database()` call, not held in a process singleton) | unit | `pytest tests/test_trust_center.py -k persistence -x` | ❌ W0 | ⬜ pending |
| T-29-01 | 29-01 | 1 | TRUST-01 | T-29-01 | Tenant isolation — a trust profile/request in tenant A is invisible to tenant B via the admin routes | unit | `pytest tests/test_trust_center.py -k tenant -x` | ❌ W0 | ⬜ pending |
| T-29-02 | 29-02 | 2 | TRUST-02 | T-29-01 | Public `GET` route requires no `Authorization` header, resolves tenant via slug + `set_tenant_id`, returns 404 (not 500) for an unknown slug | integration | `pytest tests/test_trust_center.py -k public_get -x` | ❌ W0 | ⬜ pending |
| T-29-02 | 29-02 | 2 | TRUST-02 | T-29-03 | Public `GET` route never includes `private_documents[].url` in its response — only name + "NDA required" marker | unit | `pytest tests/test_trust_center.py -k private_doc_filter -x` | ❌ W0 | ⬜ pending |
| T-29-03 | 29-02 | 2 | TRUST-02 | T-29-04 | Public `POST` (access request) rejects missing consent, captures server-derived IP/UA, reachable via `TestClient` end-to-end (catches the `response: Response` slowapi pitfall) | integration | `pytest tests/test_trust_center.py -k public_post -x` | ❌ W0 | ⬜ pending |
| T-29-02/03 | 29-02 | 2 | TRUST-02 | T-29-02 | Rate limiting is enforced on both public routes (Nth request in a window returns 429) | integration | `pytest tests/test_trust_center.py -k rate_limit -x` | ❌ W0 | ⬜ pending |
| T-29-04 | 29-03 | 2 | TRUST-03 | — | Host-header resolution correctly maps a configured `trust_domain` to its tenant; unrecognized Host falls back to slug-based lookup | unit | `pytest tests/test_trust_center.py -k custom_domain -x` | ❌ W0 | ⬜ pending |
| T-29-01/02 | 29-01, 29-02 | 1, 2 | TRUST-01/02 | — | Admin routes (`/api/trust-center/...`) still require `get_current_user` + `manage:compliance`/`view:compliance` — no accidental broadening of the existing auth model | unit | `pytest tests/test_trust_center.py -k admin_auth -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_trust_center.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py` per this repo's per-file test-helper convention
- [ ] Framework install: none — pytest already present and configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Public trust page is reachable at `/trust/{slug}` and renders fetched profile data without requiring login | TRUST-02 | Static-file serving + browser rendering path is not covered by pytest; needs a real HTTP GET | Start the app, hit `/trust/{slug}` for a seeded tenant with no `Authorization` header, confirm the page loads and shows public profile data (no private document URLs) |
| Admin management view (`TrustCenter.tsx`) still functions for authenticated users after being repointed at DB-backed persistence | TRUST-01 | UI behavior/visual check | Log in as an admin, open the Trust Center dashboard, confirm profile edits and access-request approve/deny actions still work end-to-end |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (7 requirement rows across 3 plans; test scaffold created in Wave 0)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every row has an automated command)
- [x] Wave 0 covers all MISSING references (`test_trust_center.py` created before any TRUST-01/02/03 assertion runs)
- [x] No watch-mode flags (pytest `-x`, no `--watch`)
- [x] Feedback latency < 30s (backend suite ~10-15s; manual browser check is phase-gate only, not per-commit)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-07)
