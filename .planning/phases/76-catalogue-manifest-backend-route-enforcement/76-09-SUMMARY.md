---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 09
subsystem: api
tags: [rbac, catalogue-manifest, billing, finops, identity, tenants, sso, ldap, d-08, d-09]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / catalogue_exempt / MOUNTS convention / parity helpers (76-01), full manifest (76-02)
provides:
  - backend/catalogue_mounts_billing_identity.py (named guards, exempt markers, 4 MOUNTS entries)
  - backend/tests/test_catalogue_slice_billing_identity.py (9 tests: parity, manifest drift, D-08, D-09, identity administration, exempt reachability, public routes)
  - route-level guards in billing, payment gateway, payment billing, user, api-key, tenant, tenant enrollment, bundle, SSO and LDAP endpoints
affects: [76-11, 76-12, 77]

requirements-completed: [ACC-04]

actuals:
  tokens: 14800
  tasks: 3
  commits: 3
plan_head_before: 308ed08bdc80bce2f0311e3dac90098ce3c91b58
plan_head_after: 521dc792caa36a78883c5d2ba7a7f7509ea8849a

tech-stack:
  added: []
  patterns:
    - "Mixed routers get per-route dependencies=[Depends(NAMED_GUARD)] from one slice file; pure routers get a MOUNTS entry"
    - "Exempt markers carry the reason: self-service, own-tenant scope, app-shell feature list, platform staff"

key-files:
  created:
    - backend/catalogue_mounts_billing_identity.py
    - backend/tests/test_catalogue_slice_billing_identity.py
  modified:
    - backend/billing_endpoints.py
    - backend/payment_gateway_endpoints.py
    - backend/payment_billing_endpoints.py
    - backend/user_endpoints.py
    - backend/api_key_endpoints.py
    - backend/tenant_endpoints.py
    - backend/tenant_enrollment_endpoints.py
    - backend/bundle_endpoints.py
    - backend/sso_endpoints.py
    - backend/ldap_endpoints.py
    - backend/tests/test_bundles_and_reports.py
    - backend/tests/test_session_revocation.py

key-decisions:
  - "finops_endpoints.py needed no edit: it had no view:dashboard read guard (existing strings are view:reporting/view:system/view:settings), so the additive mount-level FinOps guard (view:finops) is what removes the every-role read path (D-08)"
  - "Platform-staff tenant routes (GET /api/tenants, PATCH /license, allowlist and enrollment-key writes) are catalogue_exempt: manage:tenants is Super Admin only, so the manifest guard would lock Platform Support/Billing out of spec C1-C4 features. Their own has_platform_permission checks stay"
  - "Tenant writes are guarded with tenantManagement (write list includes manage:settings, so a tenant admin still edits their own tenant); own-tenant reads are exempt"
  - "SSO/LDAP admin routes use the userManagement guard (the manifest owner of /api/admin/sso and /api/admin/ldap) and keep _require_itam_admin_session_only"

coverage:
  - id: D1
    description: "parity_offenders over slice_modules('billing_identity') is empty (13 modules)"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_billing_identity_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every named guard and mount entry equals the manifest's resolved read/write"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_billing_identity_guards_match_manifest"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-08: billing, payments, knowledge base need manage:settings (viewer refused, tenant_admin allowed); FinOps reads need view:finops (analyst refused)"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_d08_billing_requires_manage_settings"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_d08_finops_requires_view_finops"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-09: itam_admin and tenant_admin list users and roles, roles without manage:users/manage:rbac get 403, self-service reachable by every role, Phase 75 ceiling tests unchanged"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_d09_user_and_role_admin"
        status: pass
      - kind: unit
        ref: "backend/tests/test_role_assignment_ceiling.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Tenant, bundle, SSO and LDAP administration enforced from the manifest's resolved read strings; tenant admin write path and exempt own-tenant routes preserved"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_identity_admin_enforced"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_identity_admin_writes_use_tenant_settings"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_tenant_exempt_routes_reachable_by_every_role"
        status: pass
    human_judgment: false
  - id: D6
    description: "Public sign-in, tenant lookup-key and Stripe webhook routes carry no tag"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_billing_identity.py#test_public_identity_routes_untouched"
        status: pass
    human_judgment: false

duration: 75min
completed: 2026-10-15
status: complete
---

# Phase 76 Plan 09: Billing and Identity Slice Summary

**Payments, billing, knowledge base and FinOps reads now refuse roles without manage:settings / view:finops; user, role, API-key, tenant, bundle and SSO/LDAP administration carry the manifest tag on top of their existing guards, with self-service, own-tenant, app-shell and platform-staff routes explicitly exempt and public sign-in untouched.**

## Accomplishments
- `catalogue_mounts_billing_identity.py`: named guards (finops, invoices, paymentSettings, subscriptionManagement, knowledgeBase, userManagement, roleManagement, apiKeys, tenantManagement, bundleManagement), 5 exempt markers, MOUNTS for finops, knowledge, roles and the API-key admin router.
- Per-route guards added (dependencies only, no guard removed) in billing, payment gateway/billing, user, tenant, tenant enrollment, bundle, SSO and LDAP routers.
- Slice test file: 9 tests; slice file plus `test_route_auth_baseline` and `test_catalogue_route_parity`, then full backend suite: 3692 passed, 47 skipped, 0 failed (baseline 3683 + 9 new).

## slice_modules("billing_identity") vs expected
Actual (13): api_key_endpoints, billing_endpoints, bundle_endpoints, finops_endpoints, knowledge_endpoints, ldap_endpoints, payment_billing_endpoints, payment_gateway_endpoints, role_endpoints, sso_endpoints, tenant_endpoints, tenant_enrollment_endpoints, user_endpoints.
- `payment_endpoints` (plan) is an aggregator that includes the gateway and billing routers; `slice_modules` and `router_registry` see its sub-modules, so guards are per route in `payment_gateway_endpoints` / `payment_billing_endpoints`. Mounting `payment_endpoints` would have guarded the public Stripe webhook.
- `tenant_enrollment_endpoints` (spec C4, not in the plan) is in the slice; guarded/exempted like the tenant routes.

## Task Commits
1. Task 1: `d970ab8bd` feat(76-09): guard billing, payments, FinOps and knowledge base with the manifest (D-08)
2. Task 2: `32e585992` feat(76-09): tag user, role and API-key administration with the manifest (D-09)
3. Task 3: `521dc792c` feat(76-09): guard tenant, bundle, SSO and LDAP administration with the manifest

## Exempt routes and reasons
| Route(s) | Reason |
|---|---|
| GET /api/users/me, GET+PUT /api/users/me/notification-preferences | self-service: caller's own profile and notification preferences |
| POST/GET /api/api-keys, GET /api/api-keys/scopes, DELETE /api/api-keys/{key_id} | self-service: caller's own API keys |
| GET /api/tenants/{id}/branding, /email/config, /email/preferences, /license; GET /api/tenants/{id}/allowlist, /enrollment-keys | own-tenant scope pinned by `_assert_tenant_access` / `_assert_tenant_read` (platform staff read any tenant) |
| GET /api/bundles/tenant/{id}/features | app-shell: FeaturesContext loads it for every signed-in user |
| GET /api/tenants, PATCH /api/tenants/{id}/license, POST/DELETE allowlist routes, POST enrollment-keys and revoke | platform staff, gated by `has_platform_permission` (view:tenants / manage:tenant_license, spec C1-C4) |

Not tagged and not exempt (public, untouched): /api/sso/*, /api/auth/saml/*, /api/auth/ldap/login, POST /api/tenants/lookup-key, POST /api/payments/webhook/stripe.

## Which default roles can read what after the change
- FinOps reads (view:finops): tenant_admin, user, viewer, platform_support, super_admin. analyst (had view:reporting only) loses FinOps reads.
- Billing, payments, invoices, knowledge base (manage:settings): tenant_admin and super_admin only. viewer, user and every other role lose reads that were previously open to any signed-in user.
- GET /api/users and GET /api/roles: tenant_admin and itam_admin (manage:users) unchanged; no default role loses them. Super admin passes.
- GET /api/admin/api-keys (manage:api_keys): itam_admin loses it (it holds manage:assets, which the old check wanted, but not manage:api_keys). tenant_admin keeps it.
- GET /api/bundles, /catalog, /{key}: manage:tenants, so Super Admin only (these feed only the Bundle Management screen).

## Deviations from Plan

**1. [Rule 3 - Blocking] finops_endpoints.py not edited.** The plan expected a view:dashboard read guard to replace. None exists (`grep -v '^#' backend/finops_endpoints.py | grep -c view:dashboard` is 0 before and after); the additive FinOps mount guard alone yields D-08. Files in plan `files_modified` not touched: finops_endpoints, role_endpoints.

**2. [Rule 3 - Blocking] Stale plan details corrected.** `payment_endpoints` is an aggregator (see above); user/api-key/SSO/LDAP routes use `get_current_user` (session only, `_require_itam_admin_session_only`), so the guards keep the default `auth=get_current_user` rather than `get_current_user_or_api_key`; the plan's `git diff 6b1972be9` check is replaced by the commit diff, which shows only added `dependencies=` and imports (decorator lines change only by that addition).

**3. [Rule 1 - Bug avoided] Platform-staff exemptions.** Following the manifest literally (manage:tenants, Super Admin only) would 403 Platform Support/Billing on GET /api/tenants, license PATCH and enrollment writes that spec C1-C4 shipped. Those routes are exempted with a platform-staff reason instead; `test_identity_admin_enforced` asserts platform_support/billing still list tenants and every tenant role is refused.

**4. [Rule 3 - Blocking] Tests whose principal lacked the new permission (slice rule 6).**
- `tests/test_bundles_and_reports.py`: five `TestBundleEndpoints` list/detail/catalog tests used a Viewer; they now build their client with `super_admin_user` (holds manage:tenants).
- `tests/test_session_revocation.py::_users_client` (helper shared by seven user-CRUD tests): also overrides `USER_MANAGEMENT_GUARD` with the fake admin, as it already did for `_require_itam_admin_session_only`.

**5. [Process]** Test file `test_billing_identity_slice_parity` was written in Task 1 over modules guarded so far and widened to the whole slice in Task 3.

**Total deviations:** 5 (3 plan corrections, 1 design call, 1 process). **Impact:** none on scope; every acceptance criterion met.

## Manifest corrections for 76-11
- `tenantManagement` / `bundleManagement` read `manage:tenants` is Super Admin only, but platform roles list tenants through `view:tenants` and change licenses through `manage:tenant_license`. Consider adding those strings (read: view:tenants; write: manage:tenant_license) so those routes can be guarded instead of exempt.
- `tenantManagement` write includes `manage:settings`, so any tenant admin passes the tag on POST/PATCH/DELETE `/api/tenants...`; the routes' own Super Admin checks still refuse create and delete. Consider whether create/delete should drop manage:settings.
- `apiKeys` read `manage:api_keys` removes `/api/admin/api-keys` from itam_admin, whose old guard was manage:assets; the write list still includes manage:assets. Align or accept.
- `knowledgeBase` read `manage:settings` removes Knowledge Base query/list from viewer/user (the old query guard was view:ai_governance); confirm D-08 intent for queries versus ingest/delete.
- `finops` write list `manage:settings, view:reporting` lets any view:reporting holder pass the tag on FinOps writes; the routes' own manage:system / super-admin guards still decide.
- `userManagement` owns `/api/admin/sso` and `/api/admin/ldap` with write `manage:assets`; fine today, listed for completeness.

## Phase 77 UX notes
- Subscription, Invoices, Payment Settings and Knowledge Base nav items must hide for roles without manage:settings (viewer, user, analyst, security roles, itam_*); the FinOps item must hide without view:finops.
- Data reused by another view is not an exemption: any widget that calls /api/billing, /api/payments, /api/knowledge or /api/finops for a role without the permission now gets 403 and must degrade quietly.
- Tenant email config/preferences GET and enrollment-key GET have no permission check beyond tenant ownership (any signed-in user of the tenant can read); pre-existing, exempt here, worth tightening in a later plan.

## Issues Encountered
None blocking. Initial full-suite run showed the 12 failures described in Deviation 4; fixed and re-run green. No services restarted, nothing deployed, live database untouched.

## Self-Check: PASSED
- backend/catalogue_mounts_billing_identity.py and backend/tests/test_catalogue_slice_billing_identity.py exist.
- Commits d970ab8bd, 32e585992, 521dc792c are ancestors of HEAD.
- parity_offenders over slice_modules("billing_identity") is empty; full suite 3692 passed, 0 failed.
