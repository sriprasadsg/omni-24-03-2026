---
phase: 69
slug: user-management
status: validated
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-12
---

# Phase 69 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + asyncio.run() |
| **Config file** | none detected in auth modules |
| **Quick run command** | `pytest backend/tests/test_{module}.py -x -v` |
| **Full suite command** | `pytest backend/tests/ -x` |
| **Estimated runtime** | ~90 seconds (full suite, per 65-03's independent baseline this session) |

---

## Sampling Rate

- **After every task commit:** Run `pytest backend/tests/test_{module}.py -x -v` (focused on changed module)
- **After every plan wave:** Run `pytest backend/tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 64-01-01 | 01 | 1 | ITAM-USR-01 | T-64-01/02/03 | Admin gating + tenant isolation on User CRUD | unit | `pytest backend/tests/test_user_crud.py -x -v` | ❌ W0 (new file) | ⬜ pending |
| 64-01-02 | 01 | 1 | ITAM-USR-01 | T-64-01/02/03 | Paginated listing preserves tenant isolation | unit | `pytest backend/tests/test_user_crud.py::test_user_list_pagination -x -v` | ❌ W0 | ⬜ pending |
| 64-02-01 | 02 | 1 | ITAM-USR-02 | T-64-04/05/06 | RBAC permission checks enforce ITAM roles | unit | `pytest backend/tests/test_rbac.py -x -v` | ✅ (extends existing) | ⬜ pending |
| 64-02-02 | 02 | 1 | ITAM-USR-02 | T-64-06 | Role normalization single source of truth | unit | `pytest backend/tests/test_rbac.py::test_role_normalization -x -v` | ✅ | ⬜ pending |
| 64-03-01 | 03 | 2 | ITAM-USR-03 | T-64-07/09/11/12 | LDAP bind/auth/sync; source="ldap" blocks local password | integration | `pytest backend/tests/test_ldap_service.py -x -v` | ❌ W0 (new module) | ⬜ pending |
| 64-03-02 | 03 | 2 | ITAM-USR-03 | T-64-08/10 | Admin-only LDAP config; encrypted bind password | integration | `pytest backend/tests/test_ldap_service.py -x -v -k "endpoint or auth"` | ❌ W0 | ⬜ pending |
| 64-04-01 | 04 | 2 | ITAM-USR-04 | T-64-13/18 | SAML assertion signature/audience/replay validation | integration | `pytest backend/tests/test_sso_saml.py -x -v` | ❌ W0 (new saml_service.py) | ⬜ pending |
| 64-04-M | 04 | 2 | — (CLAUDE.md 500-line cap) | — | sso_service.py / saml_service.py stay under 500 lines | static | `bash -c 'for f in backend/sso_service.py backend/saml_service.py; do wc -l "$f"; done'` | N/A | ⬜ pending |
| 64-04-02 | 04 | 2 | ITAM-USR-04 | T-64-14/15/16/17 | Admin-only SAML config; encrypted SP key; role mapping | integration | `pytest backend/tests/test_sso_saml.py -x -v -k "endpoint or auth"` | ❌ W0 | ⬜ pending |
| 64-05-01 | 05 | 2 | ITAM-USR-05 | T-64-19/21 | Bcrypt token hash; prefix lookup; expiration | unit | `pytest backend/tests/test_api_key.py -x -v` | ❌ W0 (api_key_auth.py is a 32-line stub) | ⬜ pending |
| 64-05-02 | 05 | 2 | ITAM-USR-05 | T-64-22 | Rate limiting; scope-filtered endpoints | unit | `pytest backend/tests/test_api_key.py -x -v -k "endpoint"` | ❌ W0 | ⬜ pending |
| 64-05-03 | 05 | 2 | ITAM-USR-05 | T-64-20 | TokenData.scopes narrows role permissions (intersection, never widens) | unit | `pytest backend/tests/test_api_key.py -x -v -k "scope or TokenData"` | ❌ W0 (new field) | ⬜ pending |
| 64-05-R | 05 | 2 | ITAM-USR-02, ITAM-USR-01 | T-64-04/05 | Scope change doesn't regress existing RBAC/User-CRUD behavior | regression | `pytest backend/tests/test_rbac.py backend/tests/test_user_crud.py -x -q` | ✅ | ⬜ pending |
| 64-06-01 | 06 | 2 | ITAM-USR-06 | T-64-23/24 | MongoDB TTL MFA sessions; AES-256 secret/backup-code encryption, no base64 fallback | unit | `pytest backend/tests/test_mfa.py -x -v` | ✅ (fixes existing 260-line file) | ⬜ pending |
| 64-06-02 | 06 | 2 | ITAM-USR-06 | T-64-25/26 | Two-phase login integration; password-gated disable | unit | `pytest backend/tests/test_mfa.py -x -v -k "endpoint or login"` | ✅ | ⬜ pending |
| 64-06-F | 06 | 2 | — (frontend_scope) | — | `MFASetupWizard.tsx`/`MFAVerifyModal.tsx`/`UserProfilePage.tsx` route calls stay wired to real backend routes (route names frozen, not renamed) | integration | shell route-existence gate (grep frontend calls against `mfa_endpoints.py`, documented inline in 64-06) | ✅ (existing frontend) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_user_crud.py` — new file, stubs for ITAM-USR-01
- [ ] `backend/tests/test_ldap_service.py` — new file, stubs for ITAM-USR-03 (new module `ldap_service.py`)
- [ ] `backend/tests/test_sso_saml.py` — new file, stubs for ITAM-USR-04 (new module `saml_service.py`)
- [ ] `backend/tests/test_api_key.py` — new file, stubs for ITAM-USR-05 (api_key_auth.py is currently a 32-line stub)
- [ ] `ldap3==2.9.1` install — package-legitimacy checkpoint in 64-03 (python-ldap scoped out per resolved Open Question 4 — no post-install script needed for either)
- [ ] `python3-saml==1.16.0` install — package-legitimacy checkpoint in 64-04
- [ ] `backend/tests/test_rbac.py`, `backend/tests/test_mfa.py` — extend existing files (framework/fixtures already present, no Wave 0 gap)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LDAP end-to-end bind/sync against a real directory | ITAM-USR-03 | Mocked tests cover logic; a real AD/LDAP server is external infra not available in CI | Configure a test LDAP server per 64-03's `user_setup` env vars, run test-connection + sync, confirm user provisioned with correct role mapping |
| SAML SP-initiated and IdP-initiated SSO against a real IdP | ITAM-USR-04 | Mocked assertions cover validation logic; a real IdP (Okta/Azure AD/Keycloak) is external infra | Configure a test IdP per 64-04's `user_setup` env vars, verify both SSO flows end-to-end including SLO |
| LDAP package legitimacy (ldap3) | ITAM-USR-03 | Supply-chain trust judgment, not a runnable assertion | `checkpoint:human-verify` blocking task in 64-03 Task 0 — visit PyPI, confirm maintainer/downloads/GitHub link |
| SAML package legitimacy (python3-saml) | ITAM-USR-04 | Supply-chain trust judgment | `checkpoint:human-verify` blocking task in 64-04 Task 0 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING (❌ W0) references above
- [x] No watch-mode flags (all commands use `-x`, one-shot pytest)
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter — confirmed by gsd-plan-checker re-verification pass (iteration 2)

**Approval:** approved 2026-08-12
