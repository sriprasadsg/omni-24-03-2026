---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 03
subsystem: auth
tags: [rbac, custom-roles, role-api, tenant-isolation, audit]
requires:
  - phase: 77-01
    provides: permission_vocabulary.KNOWN_PERMISSIONS, closure in granted_permissions (edits reach /me)
provides:
  - role_contents (name rules, permission validation, editor ceiling, tenant targeting, usage)
  - POST/PUT/DELETE /api/roles, GET /api/roles/permission-catalogue, builtIn flag, GET /api/roles?tenantId=
affects: [77-09, 77-11, 77-12, role editor UI, user and directory role assignment]
status: complete
plan_head_before: e242097a38ef49a6fada81d69e62cdb454dd934e
plan_head_after: fdd0a28c2f8b5a2b29ea0ec5734a06cd8c9a2de0
actuals:
  tokens: 11000
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns:
    - "raw roles handle with an explicit, resolved tenantId for every role read and write"
    - "editor ceiling on the symmetric difference of old and new permissions (ceiling_allows)"
key-files:
  created:
    - backend/role_contents.py
    - backend/tests/test_role_write_api.py
  modified:
    - backend/role_endpoints.py
    - backend/tests/test_roles_endpoint.py
key-decisions:
  - "No unique index: duplicate names are refused by a check plus a read-after-write check that removes the losing insert (409)"
  - "Legacy tenant documents named like a built-in are not custom roles: the write API answers 404 for them"
  - "Super Admin listing without tenantId computes built-in permissions with no tenant (defaults plus shared documents)"
requirements-completed: []
---

# Phase 77 Plan 03: Custom role write API Summary

Tenant admins (anyone with manage:rbac) now create, edit and delete real custom role documents of their own tenant through `role_endpoints.router`, inside the editor's permission ceiling, and an edit reaches the holder's next `/api/auth/me` without a new login.

## Request and response shapes (consumed by 77-09, 77-11, 77-12)

All routes sit on `role_endpoints.router`, so they inherit `ROLE_MANAGEMENT_GUARD` (read manage:users or manage:rbac, write manage:rbac). Writes also require manage:rbac through `_require_role_write_access` (Super Admin passes).

| Route | Request | Success |
|-------|---------|---------|
| `GET /api/roles?tenantId=` | non-Super-Admin: tenantId absent or its own (else 403). Super Admin: tenantId optional | 200 list of Role. Super Admin without tenantId: built-in roles only; with it: built-ins plus that tenant's custom roles |
| `GET /api/roles/permission-catalogue` | none (manage:rbac) | `{"permissions": [sorted strings], "superAdmin": bool}` |
| `POST /api/roles` | `{name (2-64), description (<=500, default ""), permissions: [str], tenantId?}` extra fields are 422; tenantId is required for a Super Admin and refused (403) for anyone naming another tenant | 201 Role |
| `PUT /api/roles/{role_id}?tenantId=` | `{name?, description?, permissions?}` extra fields 422; a changed name is 400 | 200 Role |
| `DELETE /api/roles/{role_id}?tenantId=` | none | 204 |

Role response: `{id, name, description, permissions (sorted), isEditable, tenantId, builtIn}`. `builtIn` is true for the table roles and false for tenant documents. Stored documents carry `id` ("role-<uuid4>"), `name`, `nameKey` (normalize_role), `description`, `permissions`, `isEditable: true`, `tenantId`, `createdBy`, `createdAt`, `updatedBy`, `updatedAt`.

### Error copy
- Built-in collision (400): `That name matches the built-in role "{built-in display name or name}". Choose a different name.`
- Agent (400): `The name 'agent' is reserved.`; empty or bad characters (400); duplicate in the tenant (409): `A role with this name already exists.`
- Rename (400): `A role's name can't be changed. To rename, create a new role and reassign its users.`
- Banned or unknown permissions (400): `These permissions cannot be granted by a custom role: <strings>`
- Over the editor's ceiling (403): `You can only grant permissions you hold yourself`
- Store failure (503): `Role store unavailable` (reads and writes) or `Role store unavailable; role change refused` (ceiling lookup)
- Super Admin target: 400 when tenantId is missing, a sentinel (`platform-admin`, `all`, `platform`) or an unknown tenant; 404 `Role not found` for another tenant's id, a built-in id or a legacy built-in-named document.

### 409 on delete
`detail = {"code": "role_in_use", "holderCount": int, "holders": [{"name", "email"}] (max 50), "mappingCount": int, "mappings": [{"group", "source": "LDAP"|"SAML"}] (max 50)}`. Holder name falls back to the email. Users are compared after `normalize_role`; the tenant's `ldap_group_mappings` and `saml_group_mappings` are matched on `tenant_id`.

### Audit
`role.created`, `role.updated`, `role.deleted` through `get_audit_service().log_action_async` with `resource_type="role"`, the target `tenant_id` and `previous_state` (`{"permissions": []}` on create; `{"description", "permissions"}` on update and delete). A failing recorder is logged and never fails the write.

## Verification

- Task sets: Task 1 set 99 passed; Task 2 set 106 passed; Task 3 set 77 passed (test_role_write_api + test_roles_endpoint).
- Parity modules (test_catalogue_route_parity, test_route_auth_baseline, test_audit_parity): 73 passed; `shared/catalogue-gaps.json` and `backend/catalogue_mounts_billing_identity.py` unchanged.
- Wider role regression (every module naming role_endpoints or /api/roles, plus test_closure_delivery and test_role_assignment_ceiling): 409 passed. The full backend suite was not re-run for this plan.
- Tracer gate: the Task 1 verify command was re-run end to end and passed before Tasks 2-3.
- Acceptance greps: builtIn 5, `@router.post` 1, put+delete 2, `role_in_use` present, `/permission-catalogue` 1, `role_endpoints.py` 281 lines.

## Deviations from Plan

None - plan executed as written. `RBACService` import was dropped from role_endpoints.py because the list route now uses `role_contents.custom_role_docs` (same built-in-key skip rule).

## Requirements

ACC-08 and ACC-09 are not marked complete: `requirements.ready-ids` returned 0/2 ready because other Phase 77 plans still declare them. REQUIREMENTS.md untouched.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-77-05..T-77-12 are covered by tests (ceiling both ways, 404 across tenants, sentinel and unknown targets, reserved names in every spelling, extra="forbid", delete refusal, audit entries).

## Notes for later plans

- The Role response gains `builtIn`; the UI should key "Custom" labelling on it, not `isEditable` (five built-ins are seeded `isEditable: true`).
- Custom roles are not yet assignable to users or directory mappings (D-04) - that is a separate plan; the delete refusal already looks at users and mappings that name one.
- No migration or unique index was added (migration 023 deferred); two simultaneous creates of one name can both be refused, which is acceptable here.
- Pre-existing chmod-only mode changes in the working tree were not committed (`core.fileMode=false`).

## Self-Check: PASSED

- Files exist: backend/role_contents.py, backend/tests/test_role_write_api.py, this SUMMARY.
- Commits a82dd8e77, fb9a2d95d, fdd0a28c2 are ancestors of HEAD.
