---
phase: 87-partner-and-reseller-channel
plan: 15
subsystem: testing
tags: [rbac, catalogue-guard, drift-tests, typescript, sidebar]

requires:
  - phase: 87-01
    provides: partners and partnerPortal catalogues, partner_admin and partner_viewer roles, manage:partners super-admin-only permission
provides:
  - AppView partners and partnerPortal, three partner Permission members, Tenant type and partnerId in types.ts
  - sidebar icons for the two partner catalogues
  - partners slice in the catalogue parity helper
  - pinned drift counts moved on purpose (206 views, 192 nav, 112 sliced, 13 role keys, 11 super-admin-only, 15 seed documents)
affects: [87-02, 87-03, 87-04, 87-05, 87-10]

actuals:
  tokens: 3200
  tasks: 2
  commits: 2
plan_head_before: 3b44e90d9f9498ad013a11971d4aad81435ebc4c
plan_head_after: 825499c5d5816fbcd7569e8d9ddf603c5e705ac4

tech-stack:
  added: []
  patterns:
    - "Partner roles are excluded from TENANT_PERMS by role key (PARTNER_ROLE_KEYS), never by permission string"

key-files:
  created: []
  modified:
    - types.ts
    - components/sidebarPresentation.tsx
    - src/__tests__/catalogueAccess.test.ts
    - backend/tests/_catalogue_parity.py
    - backend/tests/test_catalogue_manifest.py
    - backend/tests/test_catalogue_route_parity.py
    - backend/tests/test_rbac_defaults.py
    - backend/tests/test_sidebar_screen_switches.py

key-decisions:
  - "Partner role seed documents are tenantId platform and non-editable (as rbac_defaults.BUILTIN_ROLES already defines), so the seed-document test adds Partner Admin and Partner Viewer to both the platform-name and non-editable sets"

requirements-completed: [PART-01, PART-05]

coverage:
  - id: D1
    description: "AppView carries partners and partnerPortal; sidebar presentation has an icon for each; manifest, union and sidebar agree on 206 views and 192 nav entries"
    requirement: PART-01
    verification:
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts (npx vitest run src/__tests__: 76 files, 938 tests pass)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_views_equal_appview_union"
        status: pass
    human_judgment: false
  - id: D2
    description: "GOLDEN pins partner_admin to manage:partner_customers + view:partner_portal and partner_viewer to view:partner_portal; manage:partners is super-admin-only (11)"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac_defaults.py (46 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Partner roles are left out of TENANT_PERMS by role key, so the Partner portal is never a customer-tenant screen"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "backend/tests/test_sidebar_screen_switches.py"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 15: Registration Drift Tests Summary

**Frontend AppView/Permission/Tenant unions and sidebar icons now know both partner catalogues, and every pinned drift suite (206 views, 192 nav, 112 sliced, 13 role keys, 11 super-admin-only, 15 seed documents) is moved on purpose and green apart from the two baseline failures.**

## Performance

- **Duration:** about 14 min
- **Started:** 2026-11-02T17:36Z (approx), **Completed:** 2026-11-02T17:51Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- types.ts: `partners`, `partnerPortal` in AppView; `manage:partners`, `view:partner_portal`, `manage:partner_customers` in Permission; Tenant `type?: 'partner'` and `partnerId?: string` (8 added lines, nothing else).
- sidebarPresentation.tsx: BuildingIcon entries for both catalogues right after tenantManagement; catalogueAccess.test.ts nav count 190 to 192.
- Backend: partners slice (100 sidebar catalogues), 204 to 206 views, 190 to 192 nav entries (test renamed), 110 to 112 sliced views, GOLDEN rows and sizes for the two partner roles, thirteen-key test renamed, super-admin-only 10 to 11, seed documents 13 to 15, builtin_role_keys, and TENANT_PERMS excludes `PARTNER_ROLE_KEYS`.

## Task Commits

1. **Task 1: Frontend registration** - `46ec24fc1` (feat)
2. **Task 2: Backend pinned counts** - `825499c5d` (test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Seed-document test did not know the partner roles' document shape**
- **Found during:** Task 2 verify
- **Issue:** `test_seed_role_documents_mirror_the_table` asserts tenantId `all` and isEditable true for any role not in its two name sets; the partner roles are tenantId `platform` and non-editable in `BUILTIN_ROLES`.
- **Fix:** added "Partner Admin" and "Partner Viewer" to `platform_names` and `non_editable` in the test (the plan listed only the count and key changes).
- **Files modified:** backend/tests/test_rbac_defaults.py
- **Verification:** test_rbac_defaults.py 46 passed.
- **Commit:** 825499c5d

**Total deviations:** 1 auto-fixed (1 bug in test expectations). **Impact:** none on production code.

## Verification

- `npx vitest run src/__tests__`: 76 files, 938 tests pass (the five catalogueAccess failures from wave 1 are gone).
- Backend command from Task 2 on a private mongod (27998): 165 passed, failures only `test_catalogue_route_parity::test_ledger_ratchets` and `test_catalogue_manifest::test_sidebar_and_app_agree_with_manifest`, the two baseline names. The seed-document failure was fixed afterwards and test_rbac_defaults re-run green (46 passed).
- All acceptance greps pass (partnerPortal in types.ts, 1 manage:partner_customers, 2 sidebar entries, 192 in the vitest file, partners slice 1, PARTNER_ROLE_KEYS 1, partner_viewer 3).

## Known Stubs

None.

## Threat Flags

None. T-87-44 and T-87-45 mitigations are in place: GOLDEN names the exact partner permissions and TENANT_PERMS excludes the partner roles by key only.

## Issues Encountered

None beyond the deviation above. Staged only this plan's hunks with mode lines stripped; the working tree's other changes (mode flips, stray files) were left alone.

## Next Phase Readiness

Wave 3 plans can rely on the drift suites failing only on the two baseline names.

## Self-Check: PASSED

- Commits `46ec24fc1` and `825499c5d` are ancestors of HEAD.
- Modified files exist and carry the edits above.
