---
phase: "75"
slug: "permission-resolver-single-source-of-truth"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-12"
---

# Phase 75 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `75-RESEARCH.md` § Validation Architecture. Task IDs are assigned by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`). Frontend: vitest 5.0.0 + jsdom + @testing-library/react |
| **Config file** | root `pytest.ini`; `backend/pyproject.toml` (rootdir); `backend/tests/conftest.py` (pins a throwaway `omni_test_<pid>` DB); `src/__tests__/setup.ts` |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_rbac_defaults.py backend/tests/test_effective_permissions.py backend/tests/test_login_me_permissions.py backend/tests/test_role_seeding.py backend/tests/test_roles_endpoint.py backend/tests/test_role_assignment_ceiling.py backend/tests/test_rbac.py backend/tests/test_find_role_doc.py -q -p no:cacheprovider` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` and `npx vitest run src/__tests__` and `npm run build` |
| **Estimated runtime** | quick ~30 s; phase-affected suite ~28 s; full backend ~142 s; vitest ~60 s |

**Baselines (recorded 2026-10-12 by the researcher):** full backend 2878 passed / 47 skipped / 0 failed; phase-affected suites 435 passed; frontend 26 files / 186 tests.

---

## Sampling Rate

- **After every task commit:** Run the quick run command (restricted to the task's test files)
- **After every plan wave:** Run the phase-affected suite (see 75-RESEARCH.md) + `npx vitest run src/__tests__` + `npm run build` after any frontend change
- **Before `/gsd-verify-work`:** Full backend suite and full vitest suite must be green, compared against the baselines above
- **Max feedback latency:** 30 seconds (quick run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 75-01-T1 | 75-01 | 1 | ACC-01 (SC1) | — | each ITAM role gets a non-empty list from BOTH `/login` and `/me` | integration | `backend/venv/bin/python -m pytest backend/tests/test_login_me_permissions.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-01-T1 | 75-01 | 1 | ACC-01 (SC2) | — | `/login` == `/me` for every built-in role, with and without a tenant-scoped doc; super-admin → `["*"]` | integration | same file | ✅ | ✅ green |
| 75-01-T2 | 75-01 | 1 | ACC-01 | role-store outage | resolver: union, normalization, unknown role → `[]` + warning, role-store error → deny in `verify_permission` / defaults-only at login, custom doc passthrough | unit | `backend/venv/bin/python -m pytest backend/tests/test_effective_permissions.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-02-T2 | 75-02 | 2 | ACC-01 (D-24, D-07) | — | MFA verify-login and signup responses carry resolver permissions; signup no longer stores `permissions` | integration | `backend/venv/bin/python -m pytest backend/tests/test_login_me_permissions.py -k "mfa or signup" -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-01-T3, 75-05-T3 | 75-01, 75-05 | 1, 3 | ACC-02 (SC3) | — | exactly one table (AST drift test); `control:remote_access` ≠ `view:remote_access`; D-03 six absent from tenant roles; `manage:tenants` super-only; `admin` == `Tenant Admin` | unit | `backend/venv/bin/python -m pytest backend/tests/test_rbac_defaults.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-02-T1, 75-03-T1 | 75-02, 75-03 | 2 | ACC-02 (SC4) | seed clobber | after seeding: 11 shared docs (Super Admin at `"platform"`), idempotent, tenant same-name doc untouched; admin's role list includes ITAM roles | integration | `backend/venv/bin/python -m pytest backend/tests/test_role_seeding.py backend/tests/test_roles_endpoint.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-04-T1 | 75-04 | 2 | D-06 | cross-tenant bundle write | Tenant Admin 403 on PUT/PATCH/DELETE `/api/bundles/tenant/{other}/assign`; Super Admin 200 | integration | `backend/venv/bin/python -m pytest backend/tests/test_bundles_and_reports.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-04-T2, 75-05-T1, 75-05-T2 | 75-04, 75-05 | 2, 3 | D-18/D-20/D-21/D-22 | privilege escalation | caller × target matrix; itam_admin 403 assigning admin/Tenant Admin; self role change 403; LDAP/SAML mapping writes obey ceiling; super-admin mapping refused at write and apply | integration | `backend/venv/bin/python -m pytest backend/tests/test_role_assignment_ceiling.py backend/tests/test_user_crud.py backend/tests/test_ldap_service.py backend/tests/test_sso_saml.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-03-T1 | 75-03 | 2 | D-15/D-16 | info disclosure | `GET /api/roles`: built-ins + own-tenant docs, effective perms == `/me`, Super Admin hidden from non-super, 403 without `manage:users`/`manage:rbac` | integration | `backend/venv/bin/python -m pytest backend/tests/test_roles_endpoint.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 75-03-T2 | 75-03 | 2 | D-17/D-26 | fail-open UI | empty permissions → every non-super `hasPermission` false; cached role list cleared on logout | unit + build | `npx vitest run src/__tests__/permissions.test.ts` ; `npm run build` | ✅ | ✅ green |
| 75-05-T3 | 75-05 | 3 | regression | — | route auth baseline still green with the real `/api/roles` | integration | `backend/venv/bin/python -m pytest backend/tests/test_route_auth_baseline.py -q -p no:cacheprovider` | ✅ | ✅ green |

*Status: ✅ green · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/rbac_test_support.py` — in-memory roles/users/tenants store (with `update_one` upsert + `$set`), `/login` + `/me` app builder, token factory (reuse the hand-rolled fake pattern from `test_sso_config_without_tenant_context.py`; `mongomock_motor` is not installed)
- [x] `backend/tests/test_rbac_defaults.py` — AST drift test, invariants, golden per-role sets
- [x] `backend/tests/test_effective_permissions.py` — resolver unit tests
- [x] `backend/tests/test_login_me_permissions.py` — SC1/SC2, MFA verify-login, signup
- [x] `backend/tests/test_role_seeding.py` — SC4 seeding; edit `test_seed_database_step_isolation.py` to the raw handle + 11 names
- [x] `backend/tests/test_roles_endpoint.py` — D-15/D-16
- [x] `backend/tests/test_role_assignment_ceiling.py` — D-18/D-20/D-22 matrix
- [x] Edits to existing tests that encode the old behaviour: `test_rbac.py` (ITAM set equality, `manage:tenants` for tenant_admin, `can_assign_role`), `test_seed_database_step_isolation.py`, `test_prod_hardening.py:159`, `test_bundles_and_reports.py`, `test_user_crud.py`
- [x] Optional: `utils/permissions.ts` pure-function extraction + `src/__tests__/permissions.test.ts`
- Framework install: none.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live login as an ITAM-role user shows a non-empty sidebar (pre-Phase-77 fallback removed) | ACC-01 | needs a real browser session against the deployed app; no live ITAM users exist today | Create a test `itam_viewer` user in a QA tenant, log in, confirm the ITAM console + Profile are reachable and `/api/auth/me` returns the effective list |
| Backend restart re-seeds 11 shared role docs without touching tenant docs | ACC-02 | deploy/restart is user-owned (restarts are the user's per project memory) | After deploy, read-only query `roles` collection: 10 docs at `tenantId:"all"` + Super Admin at `"platform"`; tenant-scoped docs unchanged |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-12 (all requirement rows automated and green; live-only checks tracked in the Manual-Only table and 75-UAT.md)

## Validation Audit 2026-10-12

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
