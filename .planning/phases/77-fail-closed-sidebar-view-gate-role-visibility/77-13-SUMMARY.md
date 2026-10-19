---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 13
subsystem: ui
tags: [rbac, sidebar, fail-closed, skeleton, evaluateViewAccess]
requires:
  - phase: 77-02
    provides: evaluateViewAccess, permissionsKnown
provides:
  - fail-closed components/Sidebar.tsx filtering on evaluateViewAccess
  - 6-row skeleton state while permissions are unknown
  - src/__tests__/SidebarFailClosed.test.tsx
affects: [sidebar]
status: complete
commits: 3
plan_head_before: 63914f6c9bef24d23bdbf731c043865dd33ba91e
plan_head_after: c565fa34858cba58c6571330df51b4dcb1bcd28c
actuals:
  tokens: 9000
  tasks: 2
  commits: 3
requirements-completed: [ACC-06]
tech-stack:
  added: []
  patterns:
    - "menu and gate share one rule (evaluateViewAccess)"
    - "skeleton placeholders instead of a guessed menu"
key-files:
  created:
    - src/__tests__/SidebarFailClosed.test.tsx
  modified:
    - components/Sidebar.tsx
    - src/__tests__/SidebarTenantSwitches.test.tsx
key-decisions:
  - "A null user returns no groups before evaluateViewAccess runs, because evaluateViewAccess honours a '*' grant even without a user"
  - "evaluateViewAccess runs first in the item filter (after the isViewingTenant manage:tenants filter), so unmapped views are denied for the Super Admin too"
duration: 10 min
completed: 2026-10-19
---

# Phase 77 Plan 13: Fail-closed sidebar Summary

Sidebar menu now built on the same evaluateViewAccess rule as the render-time gate, with a deny-by-default permission fallback, isSuperAdminRoleName bypass for a resolved user only, and 6 skeleton rows while permissions are unknown.

## Accomplishments

- hasPermission fallback is `() => false`; no user means no menu; both literal super-admin role comparisons replaced by `isSuperAdminRoleName` (platform-admin spelling recognised, Back to Tenants included).
- Item filter uses `evaluateViewAccess(item.view, currentUser, hasPermission).allowed`; the separate permission and screenAllowed checks are gone. Bundle-mode and tier-lock filters unchanged.
- `!permissionsKnown(currentUser)` renders 6 `sidebar-skeleton-row` placeholders (circles when collapsed) in the existing nav, no group header.
- SidebarTenantSwitches fixture now carries a delivered permission list.

## Task Commits

1. Task 1 (tracer) RED: f83574c5b `test(77-13)`; GREEN: eb28483fd `feat(77-13)`
2. Task 2: c565fa348 `feat(77-13)` (skeleton tests, fixture, implementation)

## Verification

- `npx vitest run src/__tests__`: 38 files, 331 tests passed.
- `npm run build`: succeeded.
- Sidebar.tsx is 351 lines (under 500); acceptance greps pass (evaluateViewAccess( 1, isSuperAdminRoleName( 2, `(() => false)` 1, sidebar-skeleton-row 1, permissionsKnown( 2).

## Deviations from Plan

**1. [Rule 1 - Bug] Null user with a '*' grant opened the menu.** Found during Task 1: evaluateViewAccess returns allowed for `has('*')` even when user is null. Fix: `if (!currentUser) return []` at the top of visibleGroups. Commit eb28483fd.

Total deviations: 1 auto-fixed. Impact: none on scope. The no-hasPermission test passes against the old code only incidentally (the old always-grant fallback is blocked by screen-off checks being granted); the `(() => false)` grep criterion covers it.

## Notes

- src/__tests__/SidebarAuditFixes.test.tsx shows a pre-existing mode-only change; not touched or staged.
- Nothing deployed or restarted.

## Known Stubs

None.

## Self-Check: PASSED
