---
phase: 75-permission-resolver-single-source-of-truth
plan: 03
subsystem: auth
tags: [rbac, permissions, fastapi, react, vitest, pytest, tenant-isolation]
status: complete

requires:
  - phase: 75-01
    provides: rbac_defaults.BUILTIN_ROLES, rbac_service.effective_permissions, tests/rbac_test_support
provides:
  - real GET /api/roles gated by manage:users or manage:rbac, built-ins plus own-tenant documents, resolver permissions
  - utils/permissions.ts (derivePermissionState, isSuperAdminRoleName) with no role-list fallback
  - role-list cache cleared on logout and session expiry; a 403 never serves a cached copy
affects: [75-04, 75-05, 76 route manifest, 77 /me consumer]

plan_head_before: 5864eb603a47570a6e28ded6f608a2b3793c3601
plan_head_after: 4bb71961f88564242572cc6de2e36ea69b694d09

actuals:
  tokens: 14000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Role list = BUILTIN_ROLES (skip Super Admin for non-super callers) + raw db._db.roles.find({tenantId: caller}) filtered to non-built-in names; every permissions list from effective_permissions"
    - "Pure frontend derivation in utils/ so the permission memo is unit-testable"

key-files:
  created:
    - backend/tests/test_roles_endpoint.py
    - utils/permissions.ts
    - src/__tests__/permissions.test.ts
  modified:
    - backend/role_endpoints.py
    - App.tsx
    - services/apiService.ts

key-decisions:
  - "Tenant documents that share a built-in's normalized name are not listed again; their permissions already appear in the built-in entry via effective_permissions"
  - "The 403 cache rule applies to every fetchWithCache key, not only roles, so users and tenants cannot leak either"
  - "The old memo's Super Admin early return and checkPermission super-admin set were merged into isSuperAdminRoleName (union of both name sets); Phase 77 unifies the rest"

requirements-completed: [ACC-01, ACC-02]

coverage:
  - id: D1
    description: "A tenant admin's GET /api/roles lists itam_admin, itam_user and itam_viewer with the other built-ins, with permissions equal to effective_permissions"
    requirement: "ACC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_roles_endpoint.py#test_tenant_admin_lists_every_builtin_role_including_itam"
        status: pass
      - kind: integration
        ref: "backend/tests/test_roles_endpoint.py#test_builtin_permissions_come_from_the_shared_resolver"
        status: pass
    human_judgment: false
  - id: D2
    description: "Only the caller's own tenant documents are listed; Super Admin only for super-admin callers; no duplicate built-in; 503 on role-store error"
    requirement: "ACC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_roles_endpoint.py#test_own_tenant_custom_role_listed_and_other_tenant_hidden"
        status: pass
      - kind: integration
        ref: "backend/tests/test_roles_endpoint.py#test_super_admin_sees_super_admin_entry"
        status: pass
      - kind: integration
        ref: "backend/tests/test_roles_endpoint.py#test_role_store_error_answers_503_not_a_partial_list"
        status: pass
    human_judgment: false
  - id: D3
    description: "manage:users or manage:rbac holders get 200; viewer, user, itam_viewer get 403"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_roles_endpoint.py#test_callers_without_manage_users_or_rbac_get_403"
        status: pass
    human_judgment: false
  - id: D4
    description: "Frontend grants nothing when the server permission list is empty; tier intersection and super-admin names unchanged"
    requirement: "ACC-01"
    verification:
      - kind: unit
        ref: "src/__tests__/permissions.test.ts#derivePermissionState (D-17)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Logout and session expiry clear the cached role list; a 403 drops the cached copy instead of serving it; offline keeps the cache"
    requirement: "ACC-01"
    verification:
      - kind: unit
        ref: "src/__tests__/permissions.test.ts#role-list cache hygiene (D-26)"
        status: pass
    human_judgment: false
  - id: D6
    description: "A QA-tenant itam_viewer can reach the ITAM console and Profile after the build is deployed (user-owned deploy and restart)"
    requirement: "ACC-01"
    verification: []
    human_judgment: true
    rationale: "Needs the deployed UI and a restarted backend, both user-owned; 75-VALIDATION.md Manual-Only"
---

# Phase 75 Plan 03: Real role list and fail-closed frontend Summary

**Real `GET /api/roles` (built-ins plus own-tenant roles, resolver permissions, manage:users or manage:rbac gate) and a frontend that grants only the server-delivered permission list, with the role-list cache cleared on logout and never served after a 403.**

## Performance

- **Tasks:** 2 (TDD, 4 commits), **Files:** 6 (3 created, 3 modified)
- Backend: `test_roles_endpoint.py` 12 passed; neighbours (`test_rbac`, `test_user_crud`, `test_route_auth_baseline`) 74 passed.
- Frontend: `permissions.test.ts` 15 passed; full `src/__tests__` 201 passed (baseline 186 + 15); `npm run build` exits 0 (writes `dist-new/`, nothing deployed); eslint clean on the two new frontend files.

## Accomplishments

- `GET /api/roles` now returns the 10 non-super built-ins (ITAM roles included) plus the caller's own tenant documents, each with `effective_permissions`, `isEditable` and `tenantId`; the stub's `all` entry is gone. The `_require_role_list_access` dependency keeps the route recognised by the route-auth baseline test.
- `derivePermissionState` replaces the 55-line memo in `App.tsx`; the role-list fallback (the fail-open path behind the empty-ITAM-permissions bug) is deleted. `Promise.allSettled` with `getResult(1, [])` is untouched, so a 403 from `/api/roles` leaves `roles` empty without breaking the load.
- `clearSessionCaches()` runs from `logoutSession()` and `_expireSession()`; `fetchWithCache` handles `403` before the generic throw.

## TDD Gate Compliance

- **RED (backend):** 1e403dc15, 10 of 12 tests failed on assertions against the old stub (`'Tenant Admin' in ['Admin','User','Viewer']`, `200 == 403`, missing `isEditable`, `200 == 503`); the 2 passing ones are cases the stub already satisfied. Fixture `monkeypatch.setattr` uses `raising=False` for the two names the stub lacks so the failure is on the planned assertion, not a setup error. Semantic assessment: target tests executed and failed for the intended reason.
- **RED (frontend):** afed250df, 10 of 15 failed on assertions. The functions did not exist yet, so the commit carries a placeholder `utils/permissions.ts` (always-false) to avoid an import-failure RED. Same semantic assessment.
- **GREEN:** 63af566ff (backend), 4bb71961f (frontend). No REFACTOR commit needed.
- `gsd_run check tdd-red-evidence` was not run (no persisted evidence record); the RED evidence above is from the real pytest/vitest output.

## Deviations from Plan

None - plan executed exactly as written. Two notes:

- The plan's working-tree note said `App.tsx` and `services/apiService.ts` carried about 47 unrelated uncommitted lines each. At execution both were clean in `git status`, so no pre-existing hunks rode along in the commit.
- The placeholder `utils/permissions.ts` in the frontend RED commit is a process choice, not a plan deviation.

## Pre-existing working-tree changes included

None.

## Issues Encountered

None. Importing the real `services/apiService.ts` under jsdom works, so the fallback helper in `utils/permissions.ts` was not needed.

## Known Stubs

None.

## Threat Flags

None. T-75-10 through T-75-14 are mitigated and covered by the tests listed above.

## Next Phase Readiness

Ready for 75-04. Live behaviour of the new endpoint and the fail-closed UI needs the user to deploy the build and restart the backend (not done here).

## Self-Check: PASSED

- Created files present: `backend/tests/test_roles_endpoint.py`, `utils/permissions.ts`, `src/__tests__/permissions.test.ts`.
- Commits 1e403dc15, 63af566ff, afed250df, 4bb71961f are ancestors of HEAD.
- Acceptance greps: no `"all"` in `role_endpoints.py`; `effective_permissions(` x2; `_require_role_list_access` x2; router registration x1; `roleLower` 0 in `App.tsx`; `derivePermissionState(currentUser, tenants)` x1; `omni_cache_roles` and `status === 403` present in `apiService.ts`.
