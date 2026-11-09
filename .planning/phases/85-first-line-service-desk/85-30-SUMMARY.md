---
phase: 85-first-line-service-desk
plan: 30
subsystem: service-desk-rbac
tags: [g-85-4, wr-502, manage-tickets, ticket-staff, role-editor, gap-closure]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: "85-UAT gap G-85-4 and its locked user decisions UD-1..UD-4"
provides:
  - "manage:tickets on tenant_admin (so also its alias admin), analyst, security_analyst and incident_responder only"
  - "backend/ticket_access.py: TICKET_STAFF, holds_ticket_staff(perms), async is_ticket_staff(user, perms=None), the one ticket-staff test"
  - "internalTickets catalogue write list [manage:tickets, view:dashboard]; the role editor offers and labels the permission"
  - "tests/service_desk_support.staff_user: the technician of the desk test world (built-in role analyst)"
affects: [85-31, 85-32, 85-33, 85-34, 85-35, 85-36]

actuals:
  tokens: 6000
  tasks: 3
  commits: 4
plan_head_before: f8335a1aec01dccecca1dececd093c3ba5b3725b
plan_head_after: 08467d9f1672d2bd23be8261bcec238b1607e5e5
commits: 4

tech-stack:
  added: []
  patterns:
    - "Ticket staff is a permission (manage:tickets), never 'not the reporter'; custom roles are requesters until their own role document lists it"
    - "is_ticket_staff makes the same two checks as rbac_service.has_permission: granted permissions first, API-key scopes second"

key-files:
  created:
    - backend/ticket_access.py
    - backend/tests/test_ticket_staff_access.py
  modified:
    - backend/rbac_defaults.py
    - backend/tests/test_rbac_defaults.py
    - shared/catalogue-access.json
    - types.ts
    - components/RoleEditorModal.tsx
    - src/__tests__/RoleEditorModal.test.tsx
    - backend/tests/service_desk_support.py
    - backend/tests/service_desk_portal_support.py
    - backend/tests/test_service_desk_comments.py
    - backend/tests/test_service_desk_tracer.py
    - backend/tests/test_service_desk_reporter_ticket.py

key-decisions:
  - "A-85-G18 kept: staff_user uses the built-in role analyst, so the desk tests keep their meaning and later plans start from a green world"
  - "A-85-G19 kept: internalTickets gets write [manage:tickets, view:dashboard]; no catalogue test refused it, so the permission is filed under the Tickets screen's group (Automation & Intelligence), not Other"
  - "A-85-G20 kept: no migration and no seed gives manage:tickets to any custom role or tenant override"

requirements-completed: [DESK-01]

coverage:
  - deliverable: "UD-1: manage:tickets on exactly the four staff roles; user, viewer, platform_support do not hold it; super_admin through *"
    verification:
      - kind: test
        ref: "backend/tests/test_rbac_defaults.py (golden sets and sizes 134/21/20/15)"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_only_the_four_staff_rows_name_the_permission"
        status: pass
    human_judgment: false
  - deliverable: "UD-3: custom role is staff only when its own document lists the permission; another tenant's document does not count"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_custom_role_without_the_permission_is_not_staff"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_a_custom_role_of_another_tenant_does_not_make_this_tenants_role_staff"
        status: pass
    human_judgment: false
  - deliverable: "The permission is known, grantable, validated and offered by GET /api/roles/permission-catalogue to a tenant administrator"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_the_role_catalogue_offers_it_to_a_tenant_administrator"
        status: pass
    human_judgment: false
  - deliverable: "ticket_access.is_ticket_staff: permissions then API-key scopes, built-in fallback when the role store is unreachable"
    verification:
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_api_key_scopes_can_only_narrow_staff"
        status: pass
      - kind: test
        ref: "backend/tests/test_ticket_staff_access.py#test_an_unreachable_role_store_falls_back_to_the_built_in_table"
        status: pass
    human_judgment: false
  - deliverable: "Role editor shows 'Handle tickets as IT staff' in the Tickets screen's group"
    verification:
      - kind: test
        ref: "src/__tests__/RoleEditorModal.test.tsx#RoleEditorModal ticket staff permission (G-85-4 UD-3)"
        status: pass
    human_judgment: false
  - deliverable: "Desk test world technicians hold a staff role; every desk suite unchanged and green"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_{comments,notification_audience,portal_routes,withdraw,write_order,reporter_ticket,tracer,lifecycle}.py (170 passed, 0 skipped)"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 30: Ticket-staff permission Summary

**manage:tickets marks IT ticket staff on four built-in roles and any custom role a tenant admin ticks it on, with one `ticket_access.is_ticket_staff` test and a role-editor label, and the desk test world's technicians moved onto a staff role before any route enforces it.**

Duration: about 20 minutes (2026-11-09). 3 tasks, 13 files, 4 commits.

## Accomplishments

- **Task 1 (tracer, 1a0a5d54b):** `rbac_defaults.ROLE_DEFAULTS` gives `manage:tickets` to tenant_admin, analyst, security_analyst and incident_responder (sorted position, no other row touched); the golden sets and sizes (134, 21, 20, 15) say the same. The `internalTickets` catalogue entry gets the write list `["manage:tickets", "view:dashboard"]`. `backend/ticket_access.py` is new, with module-level imports of `typing` and `rbac_service` only. `backend/tests/test_ticket_staff_access.py` (20 tests) pins built-in staff and requester roles, Super Admin through `*`, custom roles with and without the permission, another tenant's document, API-key scopes, explicit permissions without a role lookup and the unreachable-store fallback.
- **Task 2 (TDD, RED 021da7f31, GREEN aebf203a8):** the three new RoleEditorModal tests failed on the label lookup before the change. Then `'manage:tickets'` joined the `Permission` union and the editor label is `Handle tickets as IT staff`. The row sits in the manifest group of the Tickets screen; the test reads that group title from the manifest JSON, never typed in.
- **Task 3 (08467d9f1):** `staff_user(tenant, username)` in `tests/service_desk_support.py` (role analyst). BOB, CAROL, STAFF2, STAFF3, SHADOW_STAFF (portal support), BOB (comments, tracer, reporter_ticket) are technicians; every requester stays on `portal_user`. No assertion changed; 170 desk tests pass.

## TDD Gate Compliance

Task 2 ran RED (`test(85-30)` 021da7f31, 3 failed / 15 passed, failure at the `findByLabelText('Handle tickets as IT staff')` assertion because the editor rendered the raw string) then GREEN (`feat(85-30)` aebf203a8, 52 passed across the three planned files). No REFACTOR needed.

## Verification

- Task 1 command (15 files): 584 passed, 2 failed. The two failures (`test_catalogue_route_parity.py::test_unguarded_routers_are_ledgered`, `::test_ledger_ratchets`) are caused by the user's uncommitted `shared/catalogue-gaps.json`, which expects the user's own `backend/reporting_endpoints.py` edits that the orchestrator set aside for this run (see Deviations). The same three catalogue and role suites run in a clean checkout of my HEAD: 92 passed, 0 failed.
- Task 2 command: 3 files, 52 passed. `tsc` shows no error in `types.ts` or `RoleEditorModal.tsx`.
- Task 3 command: 170 passed, 0 skipped.
- Acceptance: the four-role print matches; `ticket_access.py` imports only `typing` and `rbac_service`; no file under `backend/migrations` was added or changed by this plan; `git diff -- shared/catalogue-access.json` after the commit is empty.

## Deviations from Plan

### Auto-fixed Issues

None.

### Environment note (not a code deviation)

**1. Two catalogue route-parity tests fail only against the user's working tree.** Task 1's verify lists `test_catalogue_route_parity.py`; with the user's WIP `shared/catalogue-gaps.json` (modified, not committed) and `reporting_endpoints.py` at HEAD, `reporting_endpoints` shows 5 unguarded routes the WIP ledger no longer allows. Proved unrelated by running the suites in a throwaway checkout of HEAD (all green, worktree removed). Not fixed, since both files are the user's WIP. The orchestrator restores the user's `reporting_endpoints.py` edits after the run, which closes the pairing.

- `shared/catalogue-access.json` carried no file-mode change at execution time (the orchestrator had already reset it), so it was staged normally by path and the index-blob method was not needed.

**Total deviations:** 0 auto-fixed. **Impact:** none on the plan.

## Notice for the user before deployment (A-85-G20, UD-3)

No migration and no seed gives `manage:tickets` to any custom role or tenant override. Once 85-32 onward start enforcing staff, users on a custom role lose access to colleagues' tickets until a tenant admin ticks "Handle tickets as IT staff" on that role in the role editor. The four built-in staff roles need nothing. The UI publish (the role editor label) stays the user's step; this plan changed no running service.

## Known Stubs

None.

## Threat Flags

None. T-85-105 and T-85-106 are mitigated as planned: the permission sits only on four built-in rows, no seed or migration widens custom roles, and the role-editor server ceiling is unchanged.

## Next

Ready for 85-31.

## Self-Check: PASSED

- FOUND: backend/ticket_access.py, backend/tests/test_ticket_staff_access.py
- FOUND commits: 1a0a5d54b, 021da7f31, aebf203a8, 08467d9f1
