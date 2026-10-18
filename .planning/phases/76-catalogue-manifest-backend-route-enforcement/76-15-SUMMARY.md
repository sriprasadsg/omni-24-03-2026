---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 15
subsystem: rbac
tags: [rbac, catalogue-guard, tenant-controls, exemption-review, wr-05, proh-76-08, gap-closure]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard platform_read (76-13), reviewed exemptRoutes ledger list (76-14)
provides:
  - TENANT_CONTROLS_READ_GUARD and TENANT_BRANDING_DISPLAY in backend/catalogue_mounts_billing_identity.py
  - settings catalogue ownership of /api/tenants/{tenant_id}/email, /license, /allowlist, /enrollment-keys
  - test_tenant_settings_reads_are_role_gated (real-app role matrix, 14 roles x 5 paths)
  - self-service path rule in ledger_offenders
affects: [76-verification, 77]

actuals:
  tasks: 3
  commits: 6
plan_head_before: fc744bca6
plan_head_after: 8d1280bbe

key-files:
  created: []
  modified:
    - shared/catalogue-access.json
    - shared/catalogue-gaps.json
    - backend/catalogue_mounts_billing_identity.py
    - backend/tenant_endpoints.py
    - backend/tenant_enrollment_endpoints.py
    - backend/tests/test_catalogue_slice_billing_identity.py
    - backend/tests/_catalogue_parity.py
    - backend/tests/test_catalogue_route_parity.py

key-decisions:
  - "Email config/preferences reads use SETTINGS_GUARD (no platform_read): platform staff were already refused by _assert_tenant_access, now the guard refuses them"
  - "License, allowlist and install-key reads use TENANT_CONTROLS_READ_GUARD: manage:settings for tenant roles, view:tenants on safe methods for platform staff (spec C1-C4)"
  - "Email writes keep TENANT_MANAGEMENT_GUARD and gain SETTINGS_GUARD (new owner's tag); platform-staff writes keep their TENANT_PLATFORM_STAFF exemption (PROH-76-01)"
  - "TENANT_OWN_SCOPE deleted; no module uses it"

requirements-completed: []

coverage:
  - id: D1
    description: "Every tenant role without manage:settings gets 403 on the five tenant admin reads; tenant_admin, admin, super_admin pass; platform staff pass on license/allowlist/install keys only"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_tenant_settings_reads_are_role_gated"
        status: pass
    human_judgment: true
  - id: D2
    description: "Only branding and the app-shell feature list remain exempt among tenant GETs, reachable by every non-platform role"
    requirement: ACC-05
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_tenant_exempt_routes_reachable_by_every_role"
        status: pass
    human_judgment: false
  - id: D3
    description: "A self-service exemption on a {tenant_id}/{tenantId}/{user_id}/{userId} path is a ledger offender"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_self_service_exemption_on_a_tenant_path_is_an_offender"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_self_service_exemption_on_a_user_id_path_is_an_offender"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_self_service_exemption_on_a_path_without_ids_is_clean"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_platform_staff_exemption_on_a_tenant_path_is_not_flagged_by_the_self_service_rule"
        status: pass
    human_judgment: false

completed: 2026-10-18
status: complete
---

# Phase 76 Plan 15: Tenant admin reads role-gated and the self-service exemption rule Summary

**The five tenant GETs exempted as "self-service" (email config, email preferences, seat license, hardware allowlist, install keys) are role-gated; only tenant administrators, the Super Admin and (for license, allowlist and install keys) platform staff read them. The gate now rejects a self-service exemption on any route whose path names a tenant or user.**

## Accomplishments

- Manifest: the settings entry owns `/api/tenants/{tenant_id}/email`, `/license`, `/allowlist` and `/enrollment-keys` (longest segment-boundary match beats tenantManagement's `/api/tenants`). No permission strings changed.
- `TENANT_CONTROLS_READ_GUARD = catalogue_guard("settings", read=manage:settings, write=manage:settings, platform_read=("view:tenants",))` on GET license, allowlist and enrollment-keys.
- `SETTINGS_GUARD` on GET email/config and email/preferences; POST email/config, POST email/test and PUT email/preferences carry `TENANT_MANAGEMENT_GUARD, SETTINGS_GUARD`. Handler bodies and `require_permission("manage:settings")` parameters unchanged.
- GET branding is exempt through `TENANT_BRANDING_DISPLAY` with an honest display-data reason; `TENANT_OWN_SCOPE` deleted.
- Ledger: `maxExemptRoutes` 34 -> 31 -> 29, `exemptRoutes` has the 29 remaining exemptions with exact reasons.
- `ledger_offenders`: a reason starting with "self-service" (case-insensitive) on a path containing `{tenant_id}`, `{tenantId}`, `{user_id}` or `{userId}` emits "METHOD path: catalogue_exempt claims self-service but the path names a tenant or user; role-gate it or state the real reason (WR-05)".

### Role matrix (real app, tenant-a)

| Role | email/config, email/preferences | license, allowlist, enrollment-keys |
|------|------|------|
| nobody, viewer, itam_viewer, itam_user, itam_admin, user, analyst, security_analyst, incident_responder | 403 | 403 |
| tenant_admin, admin | pass | pass |
| super_admin (platform-admin) | pass | pass |
| platform_support, platform_billing (platform-admin) | 403 | pass (view:tenants) |

### Remaining tenant exemptions (29 exemptRoutes total)

- GET /api/tenants/{tenant_id}/branding: tenant display data
- GET /api/bundles/tenant/{tenant_id}/features: app-shell feature list
- GET /api/tenants/me: self-service (no id parameter, passes the new rule)
- GET /api/tenants and every allowlist/install-key/license write: platform staff, gated by has_platform_permission
- D-12 kept: the four `/api/api-keys` self-service routes stay exempt through `SELF_SERVICE_API_KEYS` (4 `Depends`), no id parameter, no offender.

## TDD Gate Compliance

- Task 1 RED `078ba9fad`, GREEN `eba652996`.
- Task 2 RED `85fa61e07`, GREEN `683e6fc0c`.
- Task 3 RED `654fda73c`, GREEN `8d1280bbe`. The executor died after writing the Task 3 GREEN change but before committing it; the change was reviewed against the plan, the parity suite rerun (50 passed) and committed on resume (2026-10-18).

## Verification

- `test_catalogue_route_parity.py`: 50 passed.
- Full backend suite: 3779 passed, 47 skipped, 0 failed in 11m36s (baseline after 76-14: 3774 passed, 47 skipped; +5 new tests: the role matrix and four self-service controls).
- `npx vitest run src/__tests__`: 266 passed (baseline 266). `npm run build`: exit 0. The bundle hash changed (`index-ChNDobM9.js`) because the UI bundles `shared/catalogue-access.json`; `dist-new` is a build folder, nothing was published.
- Acceptance: `names a tenant or user` count 1; `Depends(SELF_SERVICE_API_KEYS)` count 4; D-12 ledger assertion ok; `maxExemptRoutes == 29 == len(exemptRoutes)`; `TENANT_OWN_SCOPE` absent from backend.

## Deviations from Plan

None in scope. Test and source files carry a pre-existing chmod-only change (644 -> 755); commits were staged with `core.fileMode=false`, so no mode change entered any commit.

## Human verification (post-deploy, user-owned)

- Sign in as a tenant admin, open Settings > Email: config and preferences load.
- As Super Admin and as Platform Billing, open Manage Tenant for a customer tenant: license, install keys and hardware allowlist load.
- As a viewer, `GET /api/tenants/<own tenant id>/allowlist` returns 403.

## Next

REQUIREMENTS.md status for ACC-03/04/05 is left to the re-verification run (validate, secure, ui-review, code-review, regression, gsd-verifier).

## Self-Check: PASSED
