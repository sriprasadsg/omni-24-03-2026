---
phase: "77"
slug: "fail-closed-sidebar-view-gate-role-visibility"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-18"
---

# Phase 77 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `77-RESEARCH.md` § Validation Architecture. Task IDs are assigned by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Frontend: vitest ^5.0.0 + @testing-library/react (jsdom). Backend: pytest 9.1.1 + pytest-asyncio 1.4.0 |
| **Config file** | `vite.config.ts` (`test:` block, include `src/**/*.{test,spec}`); `backend/tests/conftest.py` |
| **Quick run command** | `npx vitest run src/__tests__/<file>` and `backend/venv/bin/python -m pytest backend/tests/<file> -q -p no:cacheprovider` |
| **Full suite command** | `npx vitest run src/__tests__`, `npm run build`, and `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` |
| **Estimated runtime** | quick: seconds per file (function-level backend tests, ~16 s for the role test set); full backend ~11 min (real-app probe modules spawn child processes) |

**Baselines (measured 2026-10-18):** full backend 3780 passed / 47 skipped; vitest `src/__tests__` 266 passed; role test set (`test_roles_endpoint`, `test_login_me_permissions`, `test_role_assignment_ceiling`) 230 passed in 15.9 s.

**Constraints:** hermetic only; never point a test at the live `omni_platform` database (use the in-memory `role_store` and `_route_walk.throwaway_env()`); no service restart, deploy or UI publish; tests never write shared files (PROH-76-03).

---

## Sampling Rate

- **After every task commit:** the new or changed test file plus any exact-list tests it touches
- **After every plan wave:** `npx vitest run src/__tests__` and `backend/venv/bin/python -m pytest backend/tests/test_role*.py backend/tests/test_login_me_permissions.py backend/tests/test_tenant_feature_switches.py backend/tests/test_rbac_defaults.py backend/tests/test_role_assignment_ceiling.py backend/tests/test_catalogue_guards.py -q -p no:cacheprovider`
- **Before `/gsd-verify-work`:** full suite green, including `npm run build` and the slow parity modules (`test_catalogue_route_parity.py`, `test_catalogue_slice_billing_identity.py`, `test_audit_parity.py`)
- **Max feedback latency:** 30 seconds (quick); the full backend suite is ~11 minutes

---

## Per-Task Verification Map

Seeded from the research requirement map; the planner assigns task IDs and validate-phase fills statuses.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ACC-06 | — | Sidebar denies with no context, empty or unknown permissions; no item for an ungranted catalogue | unit (jsdom) | `npx vitest run src/__tests__/SidebarFailClosed.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-06 | — | `evaluateViewAccess` (role / switched_off / unmapped) and `landingView` (dashboard, ITAM roles → itam, zero → null) | unit | `npx vitest run src/__tests__/viewAccess.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-06 | — | No-access panel variants and focus; zero-access Retry states; Sign out works while Retry is pending | component | `npx vitest run src/__tests__/NoAccessScreens.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-06 | — | No `default:` Dashboard fallback, no navigation bypass, no literal super-admin comparison outside `utils/permissions.ts` | source-grep | `npx vitest run src/__tests__/catalogueAccess.test.ts` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | ACC-07 | — | Visibility payload equals the session permission result per role and switch config; other tenant's role 404; platform roles hidden from non-super | backend unit | `backend/venv/bin/python -m pytest backend/tests/test_role_visibility.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-07 | — | Role panel states (loading, empty, error, groups, switched-off sub-list) | component | `npx vitest run src/__tests__/RoleVisibilityPanel.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-08 | — | `authFetch` signals a 403 once per window (not `/auth/`, not MFA); refresh result switches the gate | unit | `npx vitest run src/__tests__/permissionRefresh.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-08 | — | A role edit is visible in the next `/me` without re-login | backend unit | `backend/venv/bin/python -m pytest backend/tests/test_role_write_api.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-09 | — | Closure delivery: `itam_admin` gains Assets/Certificates (+ `request:assets`, `view:assets`, `view:licenses`); tenant admin unchanged; screen-off markers | backend unit | `backend/venv/bin/python -m pytest backend/tests/test_closure_delivery.py backend/tests/test_login_me_permissions.py -q -p no:cacheprovider` | ❌ W0 + update | ⬜ pending |
| TBD | TBD | TBD | ACC-09 | — | Role-write API: ceiling, banned and platform permissions, reserved and built-in names, `agent`, caps, fixed name, 409 holders + mappings, platform tenant refused, audit | backend unit | `backend/venv/bin/python -m pytest backend/tests/test_role_write_api.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-09 | — | Custom-role assignment: users, other tenant's role rejected, tenant move, SAML/LDAP mappings with the ceiling; permission-based MFA | backend unit | `backend/venv/bin/python -m pytest backend/tests/test_custom_role_assignment.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-09 | — | Tenant A's role edit never changes tenant B's `/me`; sentinels unreachable; super-admin spellings get `["*"]` | backend unit | `backend/venv/bin/python -m pytest backend/tests/test_role_tenant_isolation.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACC-09 | — | Route parity stays green with the new role routes; real-app sample refuses viewer/itam_admin on writes | backend, slow | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_route_parity.py backend/tests/test_role_routes_real_app.py -q -p no:cacheprovider` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update exact-list assertions in `backend/tests/test_login_me_permissions.py` and `backend/tests/test_tenant_feature_switches.py` for the D-11 closure and D-16 markers (first backend task)
- [ ] `backend/tests/test_closure_delivery.py`, `test_role_write_api.py`, `test_role_visibility.py`, `test_custom_role_assignment.py`, `test_role_tenant_isolation.py`, `test_role_routes_real_app.py`
- [ ] `src/__tests__/viewAccess.test.ts`, `SidebarFailClosed.test.tsx`, `NoAccessScreens.test.tsx`, `RoleVisibilityPanel.test.tsx`, `permissionRefresh.test.ts`, role editor / roles tab tests
- [ ] Framework install: none — pytest, vitest and testing-library already present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Role panel grid and legend fit at 375px and 768px, light and dark (UI-SPEC C51) | ACC-07 | Visual layout | After deploy, open Settings > Roles > What it can see at both widths and both themes |
| Zero-access page fits at 320px with a long email (UI-SPEC C15) | ACC-06 | Visual layout | Sign in as a role with no screens on a 320px viewport |
| Sidebar updates after an admin edits a role, on next window focus, without re-login | ACC-08 | Needs two live sessions and a deployed backend | After deploy: user A open; admin edits A's custom role; refocus A's tab |
| Restricted roles meet no raw 403s, toasts or offline banner (with Phase 76's guards live) | ACC-06 | Needs the deployed backend | Sign in as viewer, itam_viewer and analyst and click through every visible screen |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (quick)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
