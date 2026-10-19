---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 06
subsystem: auth
tags: [rbac, custom-roles, ldap, saml, fastapi, multi-tenant]

requires:
  - phase: 77-fail-closed-sidebar-view-gate-role-visibility
    provides: "77-03 role_contents.find_custom_role (tenant-scoped raw lookup, SENTINEL_TENANTS)"
provides:
  - "role_assignment.resolve_assignable_role(db, typed, tenant_id) -> canonical stored role name"
  - "POST/PUT /api/users accept the target tenant's custom roles under the unchanged ceiling"
  - "D-18 tenant-move role re-resolution against the destination tenant"
  - "LDAP and SAML group mappings accept the tenant's custom roles"
affects: [77-07, 77-08, 77-09, 77-10, 77-11, 77-12]

actuals:
  tokens: 31000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Canonicalise the typed role name before the ceiling check and before storage"
    - "Role resolved only inside the target tenant; sentinel or missing tenant fails closed"

key-files:
  created:
    - backend/tests/test_custom_role_assignment.py
  modified:
    - backend/role_assignment.py
    - backend/user_endpoints.py
    - backend/ldap_service.py
    - backend/saml_mapping.py
    - backend/ldap_endpoints.py
    - backend/sso_endpoints.py

key-decisions:
  - "Canonicalise the role name (resolve_assignable_role) before assert_can_assign_role and storage, so a spelling variant cannot skip the ceiling the stored role would fail"
  - "On a Super Admin tenant move the current role is re-resolved against the destination; a missing role is 400 and nothing is written"
  - "Mappers fail closed: a role-store exception during the custom-role lookup raises the mapper config error"

requirements-completed: []

plan_head_before: 9e2c20a0cc4a0de261c435492231e6a7fc4fd400
plan_head_after: 2e4e6c26dd5cfbcdcb479206af2e8293d9ae77c
commits: 4

coverage:
  - id: D1
    description: "Tenant admin creates and updates users holding the tenant's custom role, stored under the canonical name, under the unchanged ceiling"
    requirement: "ACC-09"
    verification:
      - kind: unit
        ref: "backend/tests/test_custom_role_assignment.py (user create/update cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Other tenant's custom role, unknown name, sentinel or missing tenant refused 400; role-store error 503"
    requirement: "ACC-09"
    verification:
      - kind: unit
        ref: "backend/tests/test_custom_role_assignment.py (cross-tenant / unknown / store-error cases)"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-18 Super Admin tenant move re-resolves the role against the destination; missing role is 400 with no write"
    requirement: "ACC-09"
    verification:
      - kind: unit
        ref: "backend/tests/test_custom_role_assignment.py (tenant-move cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "LDAP and SAML group mappings accept the tenant's custom roles (canonicalised, ceiling-checked); Super Admin platform scope maps built-in roles only"
    requirement: "ACC-09"
    verification:
      - kind: unit
        ref: "backend/tests/test_custom_role_assignment.py (mapping cases); test_ldap_service.py; test_sso_saml.py"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-10-19
status: complete
---

# Phase 77 Plan 06: Custom Role Assignment Summary

**Tenant custom roles are assignable to users (create, update, Super Admin tenant move) and to LDAP/SAML group mappings via `resolve_assignable_role`, which canonicalises the name inside the target tenant before the unchanged assignment ceiling.**

## Performance

- **Duration:** ~30 min (close-out continuation included)
- **Completed:** 2026-10-19
- **Tasks:** 2 (1 tracer, 1 auto; both TDD)
- **Files modified:** 7 (6 backend modules, 1 new test module)

## Accomplishments

- `resolve_assignable_role(db, typed, tenant_id)` returns the canonical stored name: a built-in key keeps `stored_role_name` with no lookup; otherwise the name must be a custom role of that tenant (`find_custom_role`) and the document's own name is returned. Other tenant's role, unknown name, empty name, empty or sentinel tenant -> 400 `Invalid role '<typed>'`; a lookup exception -> 503.
- `create_user`: target tenant, then role resolution, then `assert_can_assign_role`, then `assert_role_fits_tenant`, stores the canonical name. `update_user` settles the destination tenant before role handling; a role change is resolved against the destination; a move without a role change re-resolves the current role there and answers 400 `Role '<r>' does not exist in tenant '<dest>'; assign a role available there` with nothing written (D-18). `_VALID_ROLE_KEYS` removed.
- LDAP and SAML upsert handlers resolve first, then `assert_can_assign_role` and `refuse_directory_platform_role` on the canonical role. `LDAPGroupMapper.upsert_mapping` and `SAMLGroupMapper.upsert_mapping` accept a custom role only with `tenant_id` set and `find_custom_role` finding it; a missing tenant is refused before any DB access.

## Assignment Matrix

| Role supplied | Users (POST/PUT) | LDAP mapping | SAML mapping |
|---|---|---|---|
| Built-in key | Accepted, stored_role_name, ceiling applies | Accepted (unchanged) | Accepted (unchanged) |
| Own-tenant custom role (any case) | Accepted, canonical name stored, ceiling on canonical role (over-ceiling -> 403) | Accepted, canonical name stored, ceiling applies | Accepted, canonical name stored, ceiling applies |
| Other tenant's custom role | 400 `Invalid role` | 400 | 400 |
| Unknown / empty name | 400 | 400 | 400 |
| Platform role | Existing super-admin-only rule (unchanged) | 400 via `refuse_directory_platform_role` (unchanged) | 400 (unchanged) |
| Super Admin, tenant scope None | n/a (target tenant from user) | Built-in roles only; custom -> 400 | Built-in roles only; custom -> 400 |
| Role-store error | 503 | 503 | 503 |
| Super Admin tenant move | Role re-resolved in destination; missing -> 400, no write; present -> 200; move plus new role resolved in destination | n/a | n/a |

## Line Counts

| File | Lines | Limit |
|---|---|---|
| backend/user_endpoints.py | 487 | < 500 |
| backend/sso_endpoints.py | 492 | < 500 |
| backend/ldap_endpoints.py | 236 | |
| backend/role_assignment.py | 215 | |
| backend/ldap_service.py | 712 | pre-existing |
| backend/saml_mapping.py | 200 | |
| backend/tests/test_custom_role_assignment.py | 407 | |

Acceptance greps: `resolve_assignable_role(` appears 3x in user_endpoints.py and 2x across ldap_endpoints.py + sso_endpoints.py; `find_custom_role` present in ldap_service.py and saml_mapping.py.

## Task Commits

1. **Task 1 (tracer): resolve_assignable_role + create_user/update_user + D-18 check**
   - `6aa5854ee` test (RED: 8 of 15 failed on "Invalid role" / missing destination-tenant check)
   - `ea4b4e1f7` feat (GREEN)
2. **Task 2: LDAP/SAML mappings accept tenant custom roles**
   - `c2337fd69` test (RED: 6 of 30 failed on "not a valid ITAM role")
   - `2e4e6c26d` feat (GREEN)

The tracer verification set was re-run end to end before Task 2 and passed (357 passed).

## TDD Gate Compliance

RED commits (`6aa5854ee`, `c2337fd69`) each precede their GREEN commits (`ea4b4e1f7`, `2e4e6c26d`); each RED run showed failures for the missing behaviour, not for collection errors. No refactor commit was needed.

## Decisions Made

- Canonicalise before the ceiling (PROH-77-06): a stored `Helpdesk` typed as `helpdesk` is ceiling-checked and stored as `Helpdesk`.
- D-18: tenant moves re-resolve the role against the destination tenant, 400 and no write when it does not exist there.
- Mappers fail closed on lookup errors (see deviation).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Fail closed] Mappers convert a role-store lookup exception into their config error**
- **Found during:** Task 2
- **Issue:** The plan did not say what the mappers do if `find_custom_role` raises. Letting it propagate would break `test_sso_saml.py::TestSAMLGroupMapper::test_upsert_mapping_rejects_invalid_role` (empty roles collection / no DB patch) and could surface an unhandled 500.
- **Fix:** `LDAPGroupMapper.upsert_mapping` and `SAMLGroupMapper.upsert_mapping` catch the exception and raise their existing "'<role>' is not a valid ITAM role" config error (refusal). The endpoints still answer 503 because `resolve_assignable_role` runs first.
- **Files modified:** backend/ldap_service.py, backend/saml_mapping.py
- **Verification:** existing invalid-role tests green unedited; mapping cases in test_custom_role_assignment.py.
- **Committed in:** 2e4e6c26d

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Fail-closed hardening only; no scope creep.

## Test Results

- Task 1 verify set: 357 passed.
- Plan verification set (test_custom_role_assignment, test_ldap_service, test_sso_saml, test_role_assignment_ceiling, test_user_crud): 388 passed.
- Full backend suite: 3938 passed, 47 skipped, 0 failed (686.94s). Baseline after 77-04 was 3908 passed / 47 skipped; the +30 matches the 30 new tests.

## Issues Encountered

The original executor ran out of context after committing both tasks; this close-out was completed by a continuation agent without any code changes.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints, auth paths or schema changes; existing endpoints gain a tenant-scoped role lookup, covered by T-77-18 through T-77-21 (all mitigated).

## User Setup Required

None - no external service configuration required. Not deployed; backend change is committed only.

## Next Phase Readiness

- Custom roles from 77-03 are now usable for user and directory assignment; the UI plans can offer them in role pickers.
- ACC-09 is not marked complete here because sibling plans still declare it.

## Self-Check: PASSED

All seven files exist; commits 6aa5854ee, ea4b4e1f7, c2337fd69, 2e4e6c26d are ancestors of HEAD; `git rev-list --count 9e2c20a0c..HEAD` = 4.

---
*Phase: 77-fail-closed-sidebar-view-gate-role-visibility*
*Completed: 2026-10-19*
