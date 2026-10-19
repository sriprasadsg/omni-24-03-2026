---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 09
subsystem: frontend-settings
tags: [rbac, role-visibility, settings, roles-tab]
requires: [77-03, 77-07, 77-08]
provides: [roleApi, RoleVisibilityPanel, tenant-aware SettingsRolesTab]
affects: [components/SettingsRolesTab.tsx, components/SettingsDashboard.tsx, App.tsx]
key-files:
  created: [services/roleApi.ts, components/RoleVisibilityPanel.tsx, src/__tests__/RoleVisibilityPanel.test.tsx, src/__tests__/SettingsRolesTab.test.tsx]
  modified: [components/SettingsRolesTab.tsx, components/SettingsDashboard.tsx, App.tsx]
decisions:
  - "Group count '{x} of {y}' uses the payload's visibleCount, never screens.length (SC3: no client recomputation)"
  - "Switched-off section renders only for a tenant basis, so platform_role and no_tenant payloads never show it even if the server sent entries"
  - "Edit on a built-in role uses aria-disabled (stays focusable) and its click handler is a no-op"
  - "manage:users is cast to Permission in SettingsDashboard because types.ts (uncommitted unrelated edits) does not list it"
status: complete
metrics:
  completed: 2026-10-19
  tasks: 2
actuals:
  tokens: 26000
  tasks: 2
  commits: 2
plan_head_before: 998d104663ac75adc726c1f92910f2a5869e809d
plan_head_after: e36bb9345330c4c3ae12a349d5dc54202f7529a8
---

# Phase 77 Plan 09: What it can see role visibility view Summary

Settings > Roles now has a per-role "What it can see" panel that renders the server's `/api/roles/{id}/visibility` payload as delivered, a Built-in/Custom chip from the server `builtIn` flag, aria-labelled actions, a Roles tab open to anyone who can list roles, and Super Admin tenant targeting.

## Tasks

| Task | Commit | Result |
| ---- | ------ | ------ |
| 1 tracer | e8e316ab4 | roleApi (ApiRole, isBuiltInRole, types, fetchRoleVisibility), RoleVisibilityPanel (loading, error, empty, populated), row toggle opening one panel at a time; 10 tests |
| 2 | e36bb9345 | fetchRoles, chips, aria-labels, C25 helper, tenant-aware list, New Custom Role gating, canListRoles tab access, viewingTenantId from App; 10 tests |

## SettingsRolesTab props

`roles` (seed), `tenantId?`, `canManageSettings?` (kept, unused), `canManageRBAC?`, `isSuperAdmin?`, `onEdit`, `onDelete`, `onNew`. The list is seeded from `roles`, refreshed with `fetchRoles(tenantId ?? undefined)` on mount and when `tenantId` or `roles` change; a failed fetch keeps the seed.

## Metrics

- vitest: `npx vitest run src/__tests__` 41 files, 367 passed (347 before; +20 new). `npm run build` exit 0.
- components/SettingsDashboard.tsx: 547 lines (543 before, net +4, within the 6-line allowance; already over the 500 cap before this plan).

## D-10 reachability limit

The Roles tab lives inside Settings, whose manifest permission is manage:settings. A role with manage:users but not manage:settings (for example built-in itam_admin) has no UI entry to the panel; it still reaches `GET /api/roles/{role_id}/visibility`. canListRoles only adds the tab for roles that also hold manage:settings (tenant_admin, or a custom role with manage:settings and manage:users). Another entry point (ITAM console tabs) is ACC-F1, deferred.

## Deviations from Plan

None - plan executed as written. Notes:
- TDD: tests and implementation for each task were committed together (single feat commit per task) rather than separate RED/GREEN commits; the Task 2 dashboard test was observed failing before the SettingsDashboard edit. Task 1 tests were written before the modules existed.
- A platform_role/no_tenant guard on the switched-off sub-list was added (UI-SPEC section 6 says no such section renders for those bases).

## Verification

- C51 (375px/768px light and dark layout) is a backstop truth: no browser check was run here; the human-check in the plan remains for after the user deploys (user-owned).

## Known Stubs

None.

## Threat Flags

None (T-77-26: text-only rendering, no dangerouslySetInnerHTML; T-77-27: tenantId sent only for a Super Admin viewing a non-platform tenant).

## Self-Check: PASSED

Files and commits e8e316ab4, e36bb9345 exist; vitest and build green.
