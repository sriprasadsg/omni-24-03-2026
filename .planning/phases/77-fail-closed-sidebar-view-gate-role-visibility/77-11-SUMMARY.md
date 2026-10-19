---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 11
subsystem: frontend-settings
tags: [rbac, role-editor, settings, roles-api]
requires: [77-03, 77-09]
provides: [server-backed RoleEditorModal, rolePermissions helpers, roleApi write calls]
affects: [components/RoleEditorModal.tsx, components/SettingsDashboard.tsx, App.tsx, services/roleApi.ts]
key-files:
  created: [utils/rolePermissions.ts, src/__tests__/RoleEditorModal.test.tsx, src/__tests__/rolePermissions.test.ts]
  modified: [services/roleApi.ts, components/RoleEditorModal.tsx, components/SettingsDashboard.tsx, App.tsx, utils/permissions.ts]
decisions:
  - "Editor submit = effectiveSelection(manual, catalogue) plus locked rows, so it equals the visibly checked set (PROH-77-09)"
  - "Submit is disabled until the permission catalogue has loaded; a failed load shows an inline alert instead of an empty list"
  - "A 409 from the server is shown inline under the name field; every other failure uses the red error block above the footer"
  - "Name checks (duplicate, built-in collision) run live on create only; an edit never sends a name"
  - "SettingsDashboard hoists the roles tenant id into rolesTenantId and passes it to both the tab and the editor"
status: complete
metrics:
  completed: 2026-10-19
  tasks: 2
actuals:
  tokens: 30000
  tasks: 2
  commits: 2
plan_head_before: 2fbd023e6caafdd82e773049d290209fcd54608f
plan_head_after: 1b1cd46a6b8c0dabeaea25eb3d5fb93294b81968
---

# Phase 77 Plan 11: Server-backed custom role editor Summary

The Settings > Roles editor now creates and edits custom roles through the real API (POST/PUT /api/roles), lists only the permissions the server says the editor may grant, and shows implied (Manage) and locked permissions honestly before submit.

## What was built

- `services/roleApi.ts`: `RoleApiError(status, message)`, `fetchPermissionCatalogue(tenantId?)`, `createRole(body)`, `updateRole(id, body, tenantId?)`. Non-OK responses throw `RoleApiError` carrying the server `detail` (empty string when none).
- `components/RoleEditorModal.tsx` props: `{isOpen, onClose, onSave(saved: ApiRole), role: ApiRole | null, allRoles: ApiRole[], tenantId?: string | null}`. Loads the catalogue on open, groups it by catalogue group, handles pending ("Saving..."), success (onSave + toast `Role "{name}" saved.`) and errors per the UI spec. Name is disabled on edit with the D-13 helper and no name is sent. The built-in banner, the literal permission groups, the `enabledFeatures` filter and the literal Super Admin compare are gone.
- `utils/rolePermissions.ts`: `groupPermissions`, `impliedBy`, `effectiveSelection`, `lockedPermissions`, `builtInNameCollision`, all derived from the catalogue manifest and `normalizeRoleName` (now exported from `utils/permissions.ts`, rule unchanged).
- `App.tsx` `handleSaveRole` refetches with `api.fetchRoles().then(setRoles)` and no longer calls `api.saveRole`; `SettingsRolesTab` re-reads when its seed changes, so the list refreshes. Deletion wiring is unchanged (plan 77-12).

## Verification

- `npx vitest run src/__tests__`: 43 files, 390 tests passed (367 before; +23: 15 in RoleEditorModal.test.tsx, 8 in rolePermissions.test.ts).
- `npm run build`: exit 0.
- Acceptance greps: createRole/updateRole 2, fetchPermissionCatalogue 1, "Included with Manage" 1, ceiling banner text 1, `export function normalizeRoleName` 1, `api.fetchRoles().then(setRoles)` 1, RoleEditorModal.tsx 230 lines.
- Tracer gate: Task 1 verify re-run end to end after commit (18 tests across RoleEditorModal and SettingsRolesTab plus build) before expanding.

## Commits

- 1ed63ca9b feat(77-11): server-backed custom role editor (tracer)
- 1b1cd46a6 feat(77-11): grouped list, implied Manage rows, locked rows, built-in name check, ceiling banner

## Deviations from Plan

None - plan executed as written. One process note: in Task 2 the `utils/rolePermissions.ts` implementation was written in the same step as its test file, so the RED run for those 8 helper tests was not observed separately (the modal tests for Task 2 were added after the implementation as well). All tests pass and cover each behavior bullet.

## Requirements

ACC-08 was NOT marked complete: `requirements.ready-ids` returned 0/1 ready (other plans share the ID), so REQUIREMENTS.md was left untouched.

## Known Stubs

None.

## Threat Flags

None. Mitigations T-77-30 (list comes from the server catalogue) and T-77-31 (submit equals the visible checked set plus locked rows) are implemented and tested.

## Notes for the orchestrator

- Nothing deployed, no services restarted, no live database touched. `dist-new/` was rebuilt by `npm run build` only.
- `utils/permissions.ts` and `utils/catalogueAccess.ts` showed as modified in `git status` only from mode changes; the staged diff for permissions.ts is the single `export` keyword. No pre-existing content hunks had to be separated in any committed file.

## Self-Check: PASSED

Created files exist (utils/rolePermissions.ts, both test files); commits 1ed63ca9b and 1b1cd46a6 are in the history.
