---
phase: "77"
slug: "fail-closed-sidebar-view-gate-role-visibility"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
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

Filled by validate-phase 2026-10-19. Backend commands run as `backend/venv/bin/python -m pytest backend/tests/<file> -q -p no:cacheprovider`; vitest files live in `src/__tests__/`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 77-01-T1 | 77-01 | 1 | ACC-09 | — | itam_admin's /login and /me deliver Assets and Certificates; strict request:assets passes | backend unit | `pytest test_closure_delivery.py test_login_me_permissions.py test_rbac_defaults.py` | ✅ | ✅ green |
| 77-01-T2 | 77-01 | 1 | ACC-06 | — | screen-off:<view> markers for every switched-off nav screen through one apply_tenant step | backend unit | `pytest test_closure_delivery.py test_tenant_feature_switches.py test_effective_permissions.py test_platform_roles.py …` | ✅ | ✅ green |
| 77-02-T1 | 77-02 | 1 | ACC-06 | — | A denied view renders the in-place no-access panel via `evaluateViewAccess` | unit + component | `npx vitest run viewAccess.test.ts NoAccessScreens.test.tsx catalogueAccess.test.ts` | ✅ | ✅ green |
| 77-02-T2 | 77-02 | 1 | ACC-06 | — | Every navigation path and the post-login view go through the gate and landing rule | unit + build | `npx vitest run src/__tests__` + `npm run build` | ✅ | ✅ green |
| 77-03-T1 | 77-03 | 2 | ACC-09 | — | Tenant admin creates a custom role; listed as Custom; holder's /me carries it | backend unit | `pytest test_role_write_api.py test_roles_endpoint.py test_role_literal_guard.py` | ✅ | ✅ green |
| 77-03-T2 | 77-03 | 2 | ACC-08, ACC-09 | — | Edit with fixed name + symmetric ceiling; edit reaches next /me; delete refused while held | backend unit | `pytest test_role_write_api.py test_login_me_permissions.py` | ✅ | ✅ green |
| 77-03-T3 | 77-03 | 2 | ACC-09 | — | Super Admin tenant targeting; grantable-permission catalogue; route parity | backend unit + slow | `pytest test_role_write_api.py test_catalogue_route_parity.py` | ✅ | ✅ green |
| 77-04-T1 | 77-04 | 2 | ACC-09 | — | Custom admin-tier role held to MFA on protected routes; non-admin custom role is not | backend unit | `pytest test_custom_role_mfa.py test_admin_mfa_required.py test_platform_roles.py` | ✅ | ✅ green |
| 77-04-T2 | 77-04 | 2 | ACC-09 | — | Login and /me tell a custom admin-tier user to enroll or verify | backend unit | `pytest test_custom_role_mfa.py test_login_me_permissions.py test_session_revocation.py` | ✅ | ✅ green |
| 77-05-T1 | 77-05 | 2 | ACC-08 | — | A 403 re-reads permissions; open screen swaps to access-changed panel | unit + component | `npx vitest run permissionRefresh.test.ts NoAccessScreens.test.tsx viewAccess.test.ts` | ✅ | ✅ green |
| 77-05-T2 | 77-05 | 2 | ACC-06 | — | Full-page zero-access screen with Retry; Sign out cannot hang | component + build | `npx vitest run src/__tests__` + `npm run build` | ✅ | ✅ green |
| 77-06-T1 | 77-06 | 3 | ACC-09 | — | Users created/updated/moved with a tenant custom role; delivered permissions come from it | backend unit | `pytest test_custom_role_assignment.py test_user_crud.py test_user_endpoints_regression_*.py` | ✅ | ✅ green |
| 77-06-T2 | 77-06 | 3 | ACC-09 | — | LDAP/SAML group mappings accept tenant custom roles under the ceiling | backend unit | `pytest test_custom_role_assignment.py test_ldap_service.py test_sso_saml.py` | ✅ | ✅ green |
| 77-07-T1 | 77-07 | 3 | ACC-07 | — | Visibility of a built-in role equals its delivered permissions | backend unit | `pytest test_role_visibility.py test_roles_endpoint.py` | ✅ | ✅ green |
| 77-07-T2 | 77-07 | 3 | ACC-07 | — | Switched-off screens, platform roles, Super Admin tenants; equals backend enforcement | backend unit + slow | `pytest test_role_visibility.py test_tenant_feature_switches.py test_catalogue_route_parity.py` | ✅ | ✅ green |
| 77-08-T1 | 77-08 | 3 | ACC-06 | — | Restricted role's startup requests only catalogues it can read | unit + component | `npx vitest run HiddenWidgets.test.tsx viewAccess.test.ts permissions.test.ts` | ✅ | ✅ green |
| 77-08-T2 | 77-08 | 3 | ACC-06 | — | NotificationCenter and Dashboard widgets hidden when unreadable | component + build | `npx vitest run src/__tests__` + `npm run build` | ✅ | ✅ green |
| 77-09-T1 | 77-09 | 4 | ACC-07 | — | "What it can see" panel renders the role's screens by group (loading/empty/error states) | component | `npx vitest run RoleVisibilityPanel.test.tsx` | ✅ | ✅ green |
| 77-09-T2 | 77-09 | 4 | ACC-07 | — | Built-in/Custom chips, accessible actions, D-10 tab access, Super Admin tenant targeting | component + build | `npx vitest run src/__tests__` + `npm run build` | ✅ | ✅ green |
| 77-10-T1 | 77-10 | 4 | ACC-09 | — | Tenant A's role edit never changes tenant B's /me; super-admin spellings get `["*"]` | backend unit | `pytest test_role_tenant_isolation.py test_role_write_api.py test_role_visibility.py …` | ✅ | ✅ green |
| 77-10-T2 | 77-10 | 4 | ACC-09 | — | Real-app probe refuses viewer/itam_admin on role writes; full backend gate | backend slow | `pytest test_role_routes_real_app.py test_catalogue_route_parity.py test_audit_parity.py` + full suite | ✅ | ✅ green |
| 77-11-T1 | 77-11 | 5 | ACC-08 | — | Editor creates a custom role through POST /api/roles and it is listed | component | `npx vitest run RoleEditorModal.test.tsx SettingsRolesTab.test.tsx` | ✅ | ✅ green |
| 77-11-T2 | 77-11 | 5 | ACC-08 | — | Grouped list, implied Manage rows, locked rows, built-in name check, ceiling banner | unit + component | `npx vitest run rolePermissions.test.ts RoleEditorModal.test.tsx` + build | ✅ | ✅ green |
| 77-12-T1 | 77-12 | 6 | ACC-09 | — | Delete of a held role opens refusal dialog naming holders; unused role deleted | component | `npx vitest run RoleDeleteFlow.test.tsx SettingsRolesTab.test.tsx` | ✅ | ✅ green |
| 77-12-T2 | 77-12 | 6 | ACC-08 | — | Browser-memory role store removed; super-admin checks unified; frontend gate | source-grep + build | `npx vitest run src/__tests__` + `npm run build` | ✅ | ✅ green |
| 77-13-T1 | 77-13 | 2 | ACC-06 | — | Sidebar denies with no context, empty or unknown permissions; no item for an ungranted catalogue | component | `npx vitest run SidebarFailClosed.test.tsx SidebarTenantSwitches.test.tsx catalogueAccess.test.ts` | ✅ | ✅ green |
| 77-13-T2 | 77-13 | 2 | ACC-06 | — | Skeleton rows while permissions are unknown | component + build | `npx vitest run src/__tests__` + `npm run build` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Runs 2026-10-19:** vitest `src/__tests__` 413 passed; Phase 77 backend set 584 passed; supporting modules 388 passed; `test_catalogue_route_parity.py` 50 passed; `npm run build` OK.

---

## Wave 0 Requirements

- [x] Update exact-list assertions in `backend/tests/test_login_me_permissions.py` and `backend/tests/test_tenant_feature_switches.py` for the D-11 closure and D-16 markers (first backend task)
- [x] `backend/tests/test_closure_delivery.py`, `test_role_write_api.py`, `test_role_visibility.py`, `test_custom_role_assignment.py`, `test_role_tenant_isolation.py`, `test_role_routes_real_app.py`
- [x] `src/__tests__/viewAccess.test.ts`, `SidebarFailClosed.test.tsx`, `NoAccessScreens.test.tsx`, `RoleVisibilityPanel.test.tsx`, `permissionRefresh.test.ts`, role editor / roles tab tests
- [x] Framework install: none — pytest, vitest and testing-library already present

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-10-19 (validate-phase; 27/27 tasks automated and green, 4 manual-only visual/live checks remain for after deploy)

## Validation Audit 2026-10-19

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
