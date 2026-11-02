---
phase: 87-partner-and-reseller-channel
plan: 01
subsystem: api
tags: [fastapi, mongodb, multi-tenant, rbac, seat-pool, catalogue-guard]

requires:
  - phase: 76
    provides: catalogue_guard, shared/catalogue-access.json manifest and mount registry
  - phase: 75
    provides: rbac_defaults role table
provides:
  - partner_admin and partner_viewer roles (permissions view:partner_portal, manage:partner_customers, manage:partners)
  - partners and partnerPortal catalogue entries with mounted guards
  - partner_pool atomic claim/release on the partner sub-document (tenants.partner.allocated)
  - tenant_docs.build_tenant_doc, the shared organization document builder
  - POST/GET /api/platform/partners and GET /api/partner/overview, POST /api/partner/customers
affects: [87-02, 87-03, 87-04, 87-05, 87-10, 87-15]

actuals:
  tokens: 10900
  tasks: 1
  commits: 1
plan_head_before: 8b96030db3733edbefba54709ec5838721fa3b64
plan_head_after: 00d2644376b35f1eb0b376a06445c3a4f2eaeebb

tech-stack:
  added: []
  patterns:
    - "Partner pool: single conditional $expr update on tenants.partner.allocated; increases claim the pool first, decreases write the customer first"
    - "Partner scoping only from the verified token tenant, confirmed type partner and active, on the raw handle with an explicit filter"
    - "Partner-facing rows rebuilt key by key from the D-01 CUSTOMER_FIELDS allowlist"

key-files:
  created:
    - backend/partner_pool.py
    - backend/partner_store.py
    - backend/partner_platform_service.py
    - backend/partner_portal_service.py
    - backend/partner_platform_endpoints.py
    - backend/partner_endpoints.py
    - backend/catalogue_mounts_partners.py
    - backend/tenant_docs.py
    - backend/tests/test_partner_tracer.py
  modified:
    - backend/rbac_defaults.py
    - backend/router_registry.py
    - shared/catalogue-access.json

key-decisions:
  - "Task 1: option-a selected by the user (partner sub-document on tenants, conditional-update counter)"
  - "Partner and portal handlers return error_response(PartnerError) bodies instead of raising, so the UI gets {error, code, status_code, ...numbers}"
  - "Concurrent creation proven: 12 parallel 10-seat requests on a 50-seat pool create exactly 5 customers and allocated ends at 50"

patterns-established:
  - "PartnerError(status, code, message, **numbers) is the one partner refusal type"
  - "Tests wire both endpoint modules to the private mongod with SimpleNamespace(db=mongo_db) and AsyncMock audit_ledger.event"

requirements-completed: [PART-01, PART-02, PART-03, PART-05, PART-08]

coverage:
  - id: D1
    description: "Super Admin appoints a partner: tenants document type partner with pool, ceiling, no registrationKey, no seats of its own"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_appoint_stores_the_partner_shape"
        status: pass
    human_judgment: false
  - id: D2
    description: "Partner admin creates a customer with seats drawn from the pool (partnerId, license.maxAgents N, allocated grows by N)"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_customer_creation_draws_from_the_pool"
        status: pass
    human_judgment: false
  - id: D3
    description: "A creation past the pool answers 409 pool_full with the free count and leaves no document and an unchanged counter; concurrent creations never exceed the pool"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_a_full_pool_refuses_with_the_free_count"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_concurrent_creations_never_exceed_the_pool"
        status: pass
    human_judgment: false
  - id: D4
    description: "Overview carries the pool view and customer rows with exactly the D-01 keys; other partners' and direct customers never appear"
    requirement: PART-08
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_overview_carries_only_the_d01_fields"
        status: pass
    human_judgment: false
  - id: D5
    description: "Partner identity comes only from the token tenant confirmed type partner and active; Super Admin, non-partner roles, non-partner orgs, missing and suspended partners get 403"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_current_partner_refuses_everyone_else"
        status: pass
    human_judgment: false
  - id: D6
    description: "Mounted app: every /api/platform/partners route carries the partners guard and every /api/partner route the partnerPortal guard"
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_tracer.py#test_the_mounted_routes_carry_their_catalogue_guards"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 01: Partner Channel Tracer Summary

**Partner sub-document on the tenants collection with an atomic `$expr` conditional-update seat pool: Super Admin appoints a partner, a partner admin creates a customer from its pool, and the overview returns only the D-01 fields, all through catalogue-guarded routes proven on real MongoDB.**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-11-02T17:31:39Z
- **Completed:** 2026-11-02T17:36:00Z
- **Tasks:** 2 (Task 1 decision resolved by the user before dispatch, Task 2 executed)
- **Files modified:** 12 (9 created, 3 modified)

## Accomplishments

- Role table: `partner_admin` and `partner_viewer` (no tenant, no platform permission), `manage:partners` Super Admin only, `is_partner_role`; platform role sets and MFA table untouched.
- Manifest and mounts: `partners` and `partnerPortal` entries after `tenantManagement`; `catalogue_mounts_partners.py` mounts the two guards; both routers registered in `router_registry`.
- Pool: `partner_pool.claim` is one conditional `$expr` update (`allocated + n <= poolSize`, partner active); `release` never goes below zero; insert failure releases the claim.
- Tracer proof: 11 tests pass on a private mongod including 12 concurrent hand-outs against a 50-seat pool (exactly 5 succeed) and the real-app walk.
- `tenant_docs.build_tenant_doc` extracts the `create_tenant` document so direct and partner creation can share one builder (switch-over is 87-10).

## Task Commits

1. **Task 1: Confirm the stored shape of partners, pools and allotments** - no commit (decision checkpoint; user chose option-a, see Decisions)
2. **Task 2: Tracer - appoint one partner, create one customer from its pool, read the overview** - `00d264437` (feat)

**Plan metadata:** recorded in the following docs commit.

## Files Created/Modified

- `backend/partner_pool.py` - PartnerError and the atomic claim/release/free_seats
- `backend/partner_store.py` - find_partner, pool_view, partner_summary, customer_rows (D-01 allowlist), name_taken, error_response, audit
- `backend/partner_platform_service.py` - validate_ceiling, appoint, list_partners
- `backend/partner_portal_service.py` - create_customer, overview
- `backend/partner_platform_endpoints.py` - `/api/platform/partners` router, PartnerCreate
- `backend/partner_endpoints.py` - `/api/partner` router, current_partner, CustomerCreate
- `backend/catalogue_mounts_partners.py` - PARTNERS_GUARD, PARTNER_PORTAL_GUARD, MOUNTS
- `backend/tenant_docs.py` - build_tenant_doc, ensure_tenant_extras
- `backend/rbac_defaults.py`, `shared/catalogue-access.json`, `backend/router_registry.py` - role rows, manifest entries, router registration
- `backend/tests/test_partner_tracer.py` - end-to-end tracer plus mounted-guard walk

## Decisions Made

- **Task 1: option-a selected by the user (partner sub-document on tenants, conditional-update counter).** Stored contract: partner org `type: "partner"`, `partner {poolSize, allocated, expiresAt, screenCeiling, status}`, `license.maxAgents 0`; customer carries `partnerId` and its allotment is `license.maxAgents`.
- Refusals are returned as JSON bodies built by `error_response` (contract `{error, code, status_code, ...numbers}`) rather than raised as HTTPException; authorization failures (403) still raise.
- `create_customer` returns the customer's row via `customer_rows`; acceptable for the tracer, a single-customer read can replace it if the list grows large.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- First test run: the overview test reused a partner document loaded before the customer was created (stale pool numbers). Fixed in the test by loading the partner afresh per request, as the real dependency does. No production change.

## Verification

- `pytest backend/tests/test_partner_tracer.py` on private mongod 27998: 11 passed, 0 skipped.
- `pytest backend/tests/test_route_auth_baseline.py backend/tests/test_custom_role_mfa.py`: 58 passed.
- Acceptance greps: `def is_partner_role` 1, `partner_admin` 4 hits, manifest entries 1 each, no `set_tenant_id` in any partner module, no header reads in `partner_endpoints.py`, all new modules under 500 lines.
- The pinned drift suites (test_rbac_defaults, test_catalogue_manifest, test_catalogue_route_parity, test_sidebar_screen_switches, catalogueAccess.test.ts) were not run as a gate; they fail on the new counts until 87-15, as the plan states.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-87-01 raw handle plus token partner filter and allowlisted rows, T-87-02 single conditional update with release on insert failure, T-87-03 current_partner pins to the token tenant).

## User Setup Required

None - no external service configuration required. The backend was not restarted and nothing was published or pushed (user-owned).

## Next Phase Readiness

- Ready for the rest of wave 1 and 87-15 (wave 2), which registers the frontend unions, sidebar presentation and the pinned drift counts.
- Assumption A-87-A6 (partner role documents seeded with tenantId platform) is unverified for customer role lists; assignment is refused either way in 87-02.

---
*Phase: 87-partner-and-reseller-channel*
*Completed: 2026-11-02*

## Self-Check: PASSED

- Created files present: partner_pool.py, partner_store.py, partner_platform_service.py, partner_portal_service.py, partner_platform_endpoints.py, partner_endpoints.py, catalogue_mounts_partners.py, tenant_docs.py, tests/test_partner_tracer.py
- Commit `00d264437` is an ancestor of HEAD
