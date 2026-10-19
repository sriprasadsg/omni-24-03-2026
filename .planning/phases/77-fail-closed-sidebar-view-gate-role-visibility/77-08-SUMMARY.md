---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 08
subsystem: frontend-access
tags: [rbac, fail-closed, hidden-widgets, app-shell]
requires: [77-02, 77-05]
provides: [canReadView, isHideOnlyScreen, AllPartsHiddenNotice]
affects: [App.tsx, components/Dashboard.tsx, components/NotificationCenter.tsx]
key-files:
  created: [src/__tests__/HiddenWidgets.test.tsx]
  modified: [utils/viewAccess.ts, utils/permissions.ts, App.tsx, services/apiService.ts, components/NotificationCenter.tsx, components/Dashboard.tsx, components/NoAccessPanel.tsx]
decisions:
  - "canReadView has no client-side closure: it trusts the delivered permission list and the manifest read list"
  - "ifOn fails closed (no user known -> nothing requested); sign-in paths set currentUserRef before loadAllData"
  - "Dashboard all-hidden notice shows Go to only when the landing view is another screen"
status: complete
metrics:
  completed: 2026-10-19
  tasks: 2
actuals:
  tokens: 14000
  tasks: 2
  commits: 3
plan_head_before: deadf70fb7a182292366942182016b76a7adcb77
plan_head_after: f55c607a011893d294ad89b9d029fc51c2e0169e
---

# Phase 77 Plan 08: Hidden widgets and gated startup fetches Summary

The app shell now requests, and renders, only what the signed-in role can read: `canReadView(view, user, has)` mirrors the backend read rule and drives the startup fetches, the dashboard alerts refresh, NotificationCenter and the Dashboard widgets.

## Tasks

| Task | Commit | Result |
| ---- | ------ | ------ |
| 1 RED | 28d32b916 | failing canReadView matrix, App.tsx source guard, fetchIntegrations case |
| 1 GREEN | 88ac67097 | canReadView, isHideOnlyScreen, gated loadAllData, alerts refresh, fetchIntegrations fix |
| 2 | f55c607a0 | NotificationCenter and Dashboard gating, AllPartsHiddenNotice, component tests |

## Gated fetches and widgets (owning catalogue)

- loadAllData `ifOn` now uses canReadView (fail closed without a user): fetchUsers -> userManagement, fetchRoles -> roleManagement (positions unchanged); fetchTenants stays Super Admin only via `isSuperAdminRoleName`.
- Dashboard alerts refresh (60 s) -> alertManagement.
- NotificationCenter poll, socket subscription and render -> notifications.
- Dashboard: ComplianceScorePanel and ComplianceStatus -> compliance; BusinessKpiChart -> cxo; AiInsights -> aiAssistantChat; AlertsPanel -> alertManagement; AiSystemHealth -> aiGovernance or agents. Metric cards and SystemHealthChart (/api/metrics) stay.
- Layout: the KPI/health row spans the full width (`lg:col-span-3`) when only one of its widgets shows; empty rows are not rendered; all-hidden dashboard with no metrics shows the header plus AllPartsHiddenNotice.
- fetchIntegrations returns [] on a non-OK response (Pitfall 10).

## Verification

- `npx vitest run src/__tests__`: 347 passed (331 before, +16 in HiddenWidgets.test.tsx).
- `npm run build`: exit 0.

## Deviations from Plan

**1. [Rule 1 - Bug] Alerts-refresh effect used hasPermission before its declaration.** `hasPermission` is a const declared at ~line 1036, after the effect at ~line 305, so putting it in the dependency array would hit the temporal dead zone. The effect derives it with `derivePermissionState(currentUser).hasPermission` and lists `currentUser` in its dependencies. Commit 88ac67097.

**2. Test adjustments.** The Dashboard child widgets are stubbed in the component tests (they are covered by their own suites), so "fetchBusinessKpis is never called" is asserted through "BusinessKpiChart is not rendered". The all-hidden test uses a user with no permissions at all, because a `view:profile` user legitimately has a landing screen (My Tasks) and so gets the Go to button.

Unused imports `isPlatformRoleName`, `switchedOnFor` and `viewPermission` were removed from App.tsx (no longer referenced).

## Known Stubs

None.

## Threat Flags

None. T-77-25 mitigated: gated fetches skipped by canReadView, fetchIntegrations no longer stores error bodies; server guards remain authoritative.

## Notes for follow-up

- Human check (user-owned, after deploy): viewer, itam_viewer and analyst sign-in: no 403 toast, no offline banner, no bell for ITAM roles. Nothing was deployed or restarted.
- Files edited were clean of unrelated working-tree changes; only the plan's files were staged.

## Self-Check: PASSED

Commits 28d32b916, 88ac67097, f55c607a0 exist; HiddenWidgets.test.tsx present.
