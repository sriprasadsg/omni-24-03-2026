---
phase: 87-partner-and-reseller-channel
plan: 02
subsystem: auth
tags: [rbac, mfa, multi-tenant, partner-roles, role-assignment]

requires:
  - phase: 87-01
    provides: partner_admin and partner_viewer role rows, is_partner_role, partner organization shape (tenants.type partner)
  - phase: 87-15
    provides: pinned drift counts and frontend registration for the partner catalogues and roles
provides:
  - rbac_defaults.PARTNER_ONLY_PERMISSIONS and the admin-tier entry manage:partner_customers
  - effective_permissions fence for partner roles (table row only, no role document read)
  - role_assignment.assert_role_fits_tenant_type and Super-Admin-only partner role assignment
  - backend/tests/test_partner_roles.py role-matrix and assignment tests
affects: [87-03, 87-04, 87-05, 87-10]

actuals:
  tokens: 9500
  tasks: 2
  commits: 2
plan_head_before: cb2eb5254d4fee06b9b23fe6f6d8c1e16db327d6
plan_head_after: c3a2817a080a7b3e70c112242d3584b44d9f823c

tech-stack:
  added: []
  patterns:
    - "A partner role resolves to its rbac_defaults row alone: effective_permissions returns before reading any role document"
    - "PARTNER_ONLY_PERMISSIONS joins the banned set of every other role, so no document under any spelling can carry a partner permission"
    - "Tenant type is read from the raw tenants collection with a type-only projection; an unknown tenant passes through (callers refuse it)"

key-files:
  created:
    - backend/tests/test_partner_roles.py
  modified:
    - backend/rbac_defaults.py
    - backend/rbac_service.py
    - backend/role_assignment.py
    - backend/user_endpoints.py
    - backend/tests/test_custom_role_mfa.py

key-decisions:
  - "Partner roles are never added to SUPER_ROLES, platform_scope_roles(), platform_owner_roles(), tenant_admin_roles() or PLATFORM_ROLE_KEYS; auth_roles.py is untouched"
  - "manage:partner_customers is admin-tier (partner admins enroll MFA, D-20); partner_viewer is not"
  - "assert_role_fits_tenant_type lets an unknown tenant pass: create_user and update_user already refuse unknown tenants, so no gap opens"

requirements-completed: [PART-05, PART-01]

coverage:
  - id: D1
    description: "Partner roles pass no platform check (can_read_all_tenants, has_platform_permission) in any tenant including platform-admin, and are in no super/platform/tenant-admin role set"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_a_partner_role_passes_no_platform_check"
        status: pass
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_partner_roles_are_in_no_role_set"
        status: pass
    human_judgment: false
  - id: D2
    description: "A partner role's effective permissions equal its table row whatever role documents say; the two partner permissions are dropped from every other role's documents"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_a_partner_role_holds_only_its_table_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_partner_permissions_are_dropped_from_every_other_role"
        status: pass
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_a_custom_role_cannot_carry_a_partner_permission"
        status: pass
    human_judgment: false
  - id: D3
    description: "partner_admin requires MFA enrollment (first session mfa_action enroll) and partner_viewer does not (D-20)"
    requirement: PART-01
    verification:
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_resolve_mfa_required_follows_the_partner_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_custom_role_mfa.py#test_admin_tier_selects_exactly_the_builtin_admin_roles"
        status: pass
    human_judgment: false
  - id: D4
    description: "A partner role can be held only in a type partner organization and no other role there; create_user and update_user answer 400 and store nothing"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_roles.py#test_a_partner_role_fits_only_a_partner_organization"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_roles.py#test_create_user_refuses_a_partner_role_in_a_customer_and_stores_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_roles.py#test_update_user_refuses_moving_a_role_across_organization_types"
        status: pass
    human_judgment: false
  - id: D5
    description: "Only the Super Admin assigns or manages a partner role through /api/users; an LDAP or SAML mapping to a partner role is refused with 400"
    requirement: PART-05
    verification:
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_only_the_super_admin_assigns_a_partner_role"
        status: pass
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_a_tenant_admin_cannot_manage_a_partner_account"
        status: pass
      - kind: unit
        ref: "backend/tests/test_partner_roles.py#test_a_directory_mapping_to_a_partner_role_is_refused"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 02: Partner Role Fence Summary

**Partner roles resolve to their two-permission table row alone (no role document can widen them), partner admins are admin-tier for MFA, and a partner role exists only inside a partner organization and is handed out only by the Super Admin.**

## Performance

- **Duration:** about 20 min (the plan-level 6-minute catalogue test dominated wall time)
- **Started:** 2026-11-02T18:00Z (approx)
- **Completed:** 2026-11-02T18:20Z
- **Tasks:** 2
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments

- `PARTNER_ONLY_PERMISSIONS` added; `effective_permissions` returns `defaults_for` for partner roles without reading any document, and bans the two partner permissions from every other role's documents (T-87-04).
- `manage:partner_customers` joins `ADMIN_TIER_PERMISSIONS` so `partner_admin` selects as MFA-required while `partner_viewer` does not (D-20); `test_custom_role_mfa.py` pins updated.
- `assert_role_fits_tenant_type` wired after `assert_role_fits_tenant` in `create_user` and `update_user` (T-87-05); partner roles are Super-Admin-only in `assert_can_assign_role` and `assert_can_manage_account`; `refuse_directory_platform_role` refuses partner roles so LDAP/SAML mappings fail with 400 without touching `ldap_endpoints.py` or `sso_endpoints.py` (T-87-06).
- `test_partner_roles.py`: 44 tests including assignment on a private real MongoDB and the full create and update endpoint paths.

## Task Commits

1. **Task 1: Partner roles hold only their own permissions and partner admins enroll MFA** - `a84ecc363` (feat)
2. **Task 2: A partner role lives only in a partner organization and only the Super Admin hands it out** - `c3a2817a0` (feat)

**Plan metadata:** recorded in the following docs commit.

## RED evidence (TDD tasks)

Plan type is `execute` and `workflow.tdd_mode` is false, so each task is one commit (tests and implementation together) per the plan, not the separate test/feat pair. The tests were still run against unchanged production code first:

- Task 1 RED: 14 of 34 tests failed on the planned assertions (`AttributeError ... PARTNER_ONLY_PERMISSIONS`, `requires_mfa(...) is True` got False, `resolve_mfa_required` False for partner_admin); semantic assessment: the target tests executed and failed for the intended reasons, not import or fixture faults. Not machine-classified with `check tdd-red-evidence` (no record file written).
- Task 2 RED: 10 failed (directory mapping did not raise, `create_user` did not raise, `update_user` reached session revocation instead of refusing, platform-admin message mismatch); same assessment.

## Files Created/Modified

- `backend/rbac_defaults.py` - PARTNER_ONLY_PERMISSIONS, admin-tier entry and comments
- `backend/rbac_service.py` - partner branch and extended banned set in `effective_permissions`
- `backend/role_assignment.py` - `assert_role_fits_tenant_type`, partner rules in assign/manage/directory refusal
- `backend/user_endpoints.py` - import plus two awaited calls (only these lines committed)
- `backend/tests/test_custom_role_mfa.py` - BUILTIN_ADMIN_TIER gains partner_admin, non-admin loop gains partner_viewer
- `backend/tests/test_partner_roles.py` - role matrix and assignment tests

## Decisions Made

- The `update_user` call is two lines (a wrapped call) inside the existing `if "role" in update_data or "tenantId" in update_data` block rather than one line; the import line was extended in place, so `grep -c assert_role_fits_tenant_type backend/user_endpoints.py` prints 3 as required.
- Partner roles are refused as `assert_can_assign_role` targets for any non-Super-Admin with the "Only a platform super-admin can assign role" message (before the ceiling comparison, which would have refused them anyway with a less specific message).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `test_catalogue_slice_billing_identity.py` takes about 6 minutes (it iterates the whole role matrix); passes (11 tests).
- `user_endpoints.py` carries a user-side uncommitted hunk (the `user.password_reset` audit entry). Not committed; staged only this plan's lines through a filtered patch. `role_assignment.py` carried a file-mode flip (100644 to 100755); stripped from the staged patch, so no mode change was committed.

## Verification

- Task 1 command: 213 passed (test_partner_roles, test_custom_role_mfa, test_rbac_defaults, test_platform_roles).
- Task 2 command on private mongod 27998: 321 passed, 0 skipped (test_partner_roles, test_role_assignment_ceiling, test_custom_role_assignment, test_user_crud).
- Plan verification: `test_catalogue_slice_billing_identity.py` 11 passed. Regression: `test_partner_tracer.py` + `test_route_auth_baseline.py` 31 passed.
- Acceptance greps: `PARTNER_ONLY_PERMISSIONS` in rbac_service 2, `is_partner_role` 1, `partner` in auth_roles 0, `assert_role_fits_tenant_type` in user_endpoints 3, no diff in ldap_endpoints.py or sso_endpoints.py.
- Private mongod stopped before return. Backend not restarted, nothing published or pushed.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-87-04, T-87-05, T-87-06 mitigated as tested above).

## Next Phase Readiness

- Partner roles are fenced, so the invite flow (87-03 and later) can create partner users by calling the existing role machinery; invited partner admins will land in `mfa_action` enroll.
- Assumption A-87-A6 (partner role documents seeded with tenantId platform) no longer matters for resolution: partner roles read no document.

---
*Phase: 87-partner-and-reseller-channel*
*Completed: 2026-11-02*

## Self-Check: PASSED

- Created file present: backend/tests/test_partner_roles.py
- Commits `a84ecc363` and `c3a2817a0` are ancestors of HEAD
