---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 07
subsystem: auth
tags: [rbac, role-visibility, sidebar, tenant-feature-switches, catalogue-guards]
requires:
  - phase: 77-01
    provides: NAV_SCREENS, NAV_GROUPS, apply_tenant, deliverable_closure, KNOWN_PERMISSIONS
  - phase: 77-03
    provides: role_endpoints router, role_contents.find_custom_role, _require_role_list_access
provides:
  - role_visibility.delivered_for / build_visibility (pure)
  - GET /api/roles/{role_id}/visibility?tenantId=
affects: [77-09 role visibility panel]
status: complete
plan_head_before: 53ae4a4160105a48f64d56cbbfc39d6e1cc9cdcb
plan_head_after: 321e9c3c9bc51e4e1b82fcfa331dfe05ce0c9037
actuals:
  tokens: 14000
  tasks: 2
  commits: 3
tech-stack:
  added: []
  patterns:
    - "visibility computed by the delivery pipeline itself (effective_permissions -> deliverable_closure -> apply_tenant), never by a second rule"
key-files:
  created:
    - backend/role_visibility.py
    - backend/tests/test_role_visibility.py
  modified:
    - backend/role_endpoints.py
key-decisions:
  - "The whole route (including Task 2's Super Admin, platform-role and no_tenant handling) was written with Task 1, so the Task 2 tests passed on first run (characterization, no separate RED)"
  - "A non-Super-Admin caller with no tenant gets 403 'No tenant for this account' rather than an unnarrowed view"
requirements-completed: []
---

# Phase 77 Plan 07: Role visibility view Summary

Admins can ask the server which sidebar screens a role reaches; the answer is built from the same pipeline `/login` and `/me` use, so it equals delivery for every built-in role and the backend guard for the enforced catalogue groups.

## Payload contract (consumed by 77-09)

`GET /api/roles/{role_id}/visibility?tenantId=` on `role_endpoints.router` (guard: manage:users or manage:rbac).

```
{ roleId, roleName, builtIn,
  basis: { kind: "tenant" | "no_tenant" | "platform_role", tenantId, tenantName },
  visibleCount, totalCount,
  groups: [ { id, title, total, visibleCount,
              screens: [ { view, label, access: "view" | "manage" } ],
              switchedOff: [ { view, label } ] } ] }
```

Errors: 403 foreign tenantId from a non-Super-Admin (and no-tenant accounts); 404 unknown role, another tenant's custom role id, platform roles for anyone but a Super Admin; 400 `Select a tenant to see a custom role` (Super Admin, custom role, no tenantId); 503 `Role store unavailable`. Groups follow NAV_GROUPS, screens follow NAV_SCREENS; all 8 groups are always returned (totalCount 188).

### Sample (viewer, tenant-a, all switches on, trimmed to two groups and two screens)

```json
{"roleId": "role-viewer", "roleName": "viewer", "builtIn": true,
 "basis": {"kind": "tenant", "tenantId": "tenant-a", "tenantName": "Tenant A"},
 "visibleCount": 44, "totalCount": 188,
 "groups": [
  {"id": "dashboards", "title": "Dashboards & Insights", "total": 13, "visibleCount": 5,
   "screens": [{"view": "dashboard", "label": "Overview", "access": "view"},
               {"view": "executiveSummary", "label": "Executive Summary", "access": "view"}],
   "switchedOff": []},
  {"id": "observability", "title": "Observability", "total": 9, "visibleCount": 0,
   "screens": [], "switchedOff": []}]}
```

## Property-test coverage (SC3)

`test_visible_equals_the_backend_guard_for_enforced_groups`: every built-in tenant role (parametrized over `rbac_defaults.BUILTIN_ROLES` minus platform roles) x 3 switch configurations (all on, `["view:agents"]`, `["view:security","screen:edr"]`). For each nav screen of the enforce:true groups (infra, security, mgmt) that has routes, no explicit read list and is not hide-only, `visible` equals `catalogue_guards.check_catalogue_access(GET, permission)` passing and, where `screen_of(first route)` names the screen, its `screen:<view>` switch being on. `test_visible_equals_delivered_permissions_for_every_builtin` compares the visible set to `rbac_service.session_permissions` per built-in role. Assumptions SC3-ENFORCED-GROUPS-ONLY and D10-MANIFEST-POLICY-OPEN are as planned: for the five non-enforced groups "matches the backend" means the delivered-permission rule.

## Verification

- `test_role_visibility.py` + `test_role_write_api.py` + `test_tenant_feature_switches.py`: 173 passed. Task 1 set (visibility, write API, roles endpoint): 91 passed.
- `test_catalogue_route_parity.py` + `test_route_auth_baseline.py`: 70 passed.
- Full backend suite: 4027 passed, 47 skipped (3938 passed before this plan; +89 new tests).

## Deviations from Plan

**1. [Plan example vs data] `["view:agents"]` alone does not make the `agents` screen visible.** `agents` shares `view:agents` with Agent Approvals and so has its own `screen:agents` switch; with only the feature switch it is listed in `switchedOff`. The pipeline is the truth (the property test agrees), so the test uses `["view:agents","screen:agents"]` for the "agents is visible" case and asserts the switched-off case separately. No code change.

**2. [Rule 2] No-tenant non-Super-Admin account** gets 403 instead of an unnarrowed view (fail closed).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-77-22, T-77-23, T-77-24 mitigated: tenant-scoped lookup, platform roles Super-Admin only, property test against the guard).

## Self-Check: PASSED
