---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 12
subsystem: frontend-settings
tags: [rbac, role-delete, settings, roles-api, super-admin-unification]
requires: [77-03, 77-09, 77-11, 77-13]
provides: [deleteRole/RoleInUseError, RoleDeleteRefusalModal, delete flow in SettingsRolesTab, fake role store removed, super-admin source guard]
affects: [services/roleApi.ts, components/SettingsRolesTab.tsx, components/SettingsDashboard.tsx, App.tsx, services/apiService.ts]
key-files:
  created: [components/RoleDeleteRefusalModal.tsx, src/__tests__/RoleDeleteFlow.test.tsx]
  modified: [services/roleApi.ts, components/SettingsRolesTab.tsx, components/SettingsDashboard.tsx, App.tsx, services/apiService.ts, src/__tests__/catalogueAccess.test.ts]
decisions:
  - "Roles tab owns the delete: it calls DELETE /api/roles/{id}, removes the row and then tells the parent via onDelete(id); App.handleDeleteRole only refetches the role list"
  - "RoleDeleteRefusalModal puts the dialog title in a focusable span inside Modal's h2 and focuses it on a 20ms timer so it wins over Modal's own first-control focus"
  - "Super-admin source guard flags comparisons against Super Admin / superadmin / super_admin / Platform Owner anywhere, and 'platform-admin' only when compared with a role identifier (it is also the platform tenant id)"
status: complete
metrics:
  completed: 2026-10-19
  tasks: 2
actuals:
  tokens: 30000
  tasks: 2
  commits: 3
plan_head_before: a843db7c81839ea8fe34c9c6d583418406c24747
plan_head_after: de5ed346f9e5c564ce7ad0b4de7140e01f354e4a
---

# Phase 77 Plan 12: Role delete flow, fake store removal, phase gate Summary

Deleting a custom role in Settings > Roles now goes to the real API with a destructive confirmation; a role that users or SAML/LDAP mappings still hold is refused with a dialog naming who holds it, and the browser-memory role store is gone.

## What was built

- `services/roleApi.ts`: `deleteRole(id, tenantId?)` (204 resolves, 409 with `detail.code === "role_in_use"` throws `RoleInUseError(detail)`, anything else throws `RoleApiError` with the server detail) and the `RoleInUseDetail`, `RoleHolder`, `RoleMapping` types.
- `components/RoleDeleteRefusalModal.tsx`: Modal md titled `Can't delete "{name}" yet`; singular/plural holder and mapping sentences, the reassign hint, `role="list"` scroll lists (`max-h-48`), name over email (email as the bold line when the name is missing), `and {N-50} more` from count minus listed, Sign-in mappings sub-list (group over SAML/LDAP), footer Close / Go to User Management, heading focus.
- `components/SettingsRolesTab.tsx`: trash opens `ConfirmationModal` (destructive, `Delete role` / `Keep role`); confirmed delete shows the row at `opacity-60 pointer-events-none` with a 14px spinner on the trash button, then removes the row + success toast + `onDelete(id)`; `RoleInUseError` opens the refusal dialog; other errors toast `Couldn't delete the role: {message}. Try again.`; new `onGoToUsers` prop wired in `SettingsDashboard` to `setActiveView('users')`.
- `services/apiService.ts`: browser-memory `saveRole`/`deleteRole` removed (the `ROLES` cache that `fetchRoles` writes and the session reset clears stays).
- `App.tsx`: `handleDeleteRole` refetches `api.fetchRoles().then(setRoles)`; the five literal super-admin comparisons (login, session restore, finops, settings users filter, itam) now use `isSuperAdminRoleName`.
- `src/__tests__/catalogueAccess.test.ts`: guards that apiService exports no saveRole/deleteRole and App calls neither, plus a per-file literal super-admin spelling guard across the 11 phase surfaces.

## Verification

- `npx vitest run src/__tests__`: 44 files, 413 tests passed (baseline 266 at plan time, 390 after 77-11; +23 here: 10 in RoleDeleteFlow.test.tsx, 13 in catalogueAccess.test.ts).
- `npm run build`: exit 0.
- Acceptance: `RoleInUseError` in roleApi.ts 4 hits, `deleteRole(` in SettingsRolesTab.tsx 1, `onGoToUsers` in SettingsDashboard.tsx 1, saveRole/deleteRole exports in apiService.ts 0, `isSuperAdminRoleName(` in App.tsx 6.
- TDD: RED commit 7c6a027e4 (10 failing), GREEN e4542ead5. Super-admin and fake-store guards went red (App.tsx literals) before the fix in de5ed346f.
- Tracer gate: Task 1 verify (RoleDeleteFlow + SettingsRolesTab, 20 tests) re-run green before expanding.

## Commits

- 7c6a027e4 test(77-12): failing role delete flow tests
- e4542ead5 feat(77-12): server-backed role delete with confirmation and in-use refusal dialog
- de5ed346f refactor(77-12): drop the browser-memory role store and unify super-admin checks

## Deviations from Plan

None - plan executed as written. The test file's `exact: true` getByRole option was removed after a tsc error (string names already match exactly).

## Known Stubs

None.

## Deferred / scope notes

- Literal super-admin checks remain in SettingsUsersTab, AgentDetailModal, AgentsDashboard, ComplianceFrameworksDashboard, AgentInstallation, SupportChatPanel, AgentChatPanel (assumption SUPERADMIN-UNIFICATION-SCOPE, outside the gate surfaces).
- `src/__tests__/catalogueAccess.test.ts` shows a pre-existing chmod-only mode change in the working tree; not committed.
- Phase 76 is committed but not deployed; nothing here was deployed or restarted.

## Human checks for post-deploy UAT (user-owned)

1. As a tenant admin create a custom role, assign it to a test user, try to delete it: the refusal dialog lists the user; Go to User Management switches to the users tab; reassign the user; delete again: succeeds with the toast.
2. With the test user's tab open, edit their role, then refocus their tab: the sidebar updates without re-login.
3. Add a SAML/LDAP group mapping to a custom role and try to delete it: the Sign-in mappings list appears.
4. The 76-UAT restricted-role walk-through (restricted role sees only its screens; direct hash to a hidden screen shows No access; zero-access role sees the zero-access screen).

## Self-Check: PASSED

Files found: components/RoleDeleteRefusalModal.tsx, src/__tests__/RoleDeleteFlow.test.tsx; commits 7c6a027e4, e4542ead5, de5ed346f are ancestors of HEAD.
