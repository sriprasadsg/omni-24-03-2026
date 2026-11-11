---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 08
subsystem: licensing
tags: [plans, super-admin, catalogue, seats, api, mongodb]
status: complete

requires:
  - phase: 88-02
    provides: licensing.apply_plan_seats / _check_seats, plan_notices.announce
  - phase: 88-03
    provides: screen_ceiling.seed_screens / plan_allowed
  - phase: 88-04
    provides: plan_service (plans, normalize_plan, PlanError, new_tenant_terms)
provides:
  - plan_service.list_plans and plan_service.update_plan (refusal codes unknown_plan, custom_is_per_tenant, nothing_to_update, trial_only_on_free, invalid_seats, invalid_trial_days, invalid_screen)
  - audit event plan.updated (platform-admin ledger, before/after of the changed fields, tenantsUpdated)
  - GET /api/platform/plans and PUT /api/platform/plans/{plan_key} (Super Admin only), owned by the tenantManagement catalogue
  - backend/tests/test_plan_endpoints.py (17 tests, real MongoDB)
affects: [88-12, 88-16]

requirements-completed: [LIC-07]

actuals:
  tokens: 22000
  tasks: 2
  commits: 4
plan_head_before: d30ee14b91f79cbb70227ebcbc346b03cdac1615
plan_head_after: b89193f1257eeb46ce0a3312c88b81cb38921326

coverage:
  - id: D1
    description: "list_plans: Free, Pro, Enterprise, Custom in order with seats, trialDays, screens (stored list, the seed, or 'all' for Custom), tenantCount (missing plan counts as Free; platform and partner organizations excluded), updatedAt, updatedBy"
    requirement: LIC-07
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_endpoints.py (test_an_empty_collection_lists_*, test_tenant_count_reads_*) against the private mongod"
        status: pass
    human_judgment: false
  - id: D2
    description: "update_plan seats: stored, applied at once through licensing.apply_plan_seats to direct tenants without an override (override, partner customer and platform untouched), one seats.changed notice per changed tenant via plan_edit, one plan.updated ledger entry with before and after; the same edit again writes, notifies and records nothing; bounds 0 and 1,000,000 accepted, -1, 1,000,001, float, bool, string refused with nothing stored"
    requirement: LIC-07
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_endpoints.py (test_a_seats_edit_reaches_*, test_the_same_edit_again_*, test_seats_accept_the_bounds_*, test_a_plan_with_no_stored_document_*)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Screens and trial days shape only the future: a trialDays edit leaves a running trial's endsAt and applies to the next new_tenant_terms; screens are stored in submitted order de-duplicated, an empty list is kept, 'all' and unknown keys refused, no tenant's enabledFeatures changes; Custom 422 custom_is_per_tenant, trialDays outside Free 422, empty body 422 nothing_to_update"
    requirement: LIC-07
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_endpoints.py (test_trial_days_*, test_screens_are_stored_*, test_an_empty_screen_list_*, test_custom_unknown_and_empty_*)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Plans API: only the Super Admin reads or edits (platform support and tenant admin get 403 in the handler); the body refuses unknown fields and non-integer or out-of-range numbers; PlanError becomes a JSON body with the status; the real mounted app lists both routes tagged tenantManagement, authenticated as user"
    requirement: LIC-07
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_endpoints.py (route tests and test_the_real_app_mounts_*); test_catalogue_route_parity, test_catalogue_manifest, test_catalogue_slice_billing_identity, test_route_auth_baseline: 113 passed in total; npx vitest run src/__tests__/catalogueAccess.test.ts 44 passed"
        status: pass
    human_judgment: false
---

# Phase 88 Plan 08: Super Admin plan table API Summary

**The Super Admin can now read the four plans and edit each plan's seats, Free trial days and screen list through a guarded, manifest-owned API; a seats edit reaches every direct tenant on the plan without an override at once and is announced and audited, while screen and trial edits only change what comes next.**

## Performance

- **Duration:** about 20 min (2026-11-11 02:01 to 02:21 UTC), most of it the 4m20s real-app route walk
- **Tasks:** 2 (both TDD: RED commit, then GREEN commit)
- **Files:** 6 (2 created: plan_endpoints.py, test_plan_endpoints.py; 4 modified: plan_service.py, catalogue_mounts_billing_identity.py, router_registry.py, shared/catalogue-access.json)

## Accomplishments

- `plan_service.list_plans(db)` answers the four plans in order; `tenantCount` comes from one aggregation on the raw tenants collection (a missing or unknown plan reads as Free, as `plan_key_of` does).
- `plan_service.update_plan(db, key, changes, *, actor)` validates first (nothing is stored on a refusal), computes before and after for the changed fields only, returns early with `tenantsUpdated: 0` and no write, notice or audit when nothing differs, then upserts the plans document, applies seats through `licensing.apply_plan_seats` (its filter excludes partner customers, the platform organization and overrides), announces `seats.changed` to each changed tenant's admins and records `plan.updated`. plan_service.py is now 300 lines.
- `backend/plan_endpoints.py` (53 lines): `PlanUpdate` (extra forbid, `StrictInt` with bounds, screens at most 300), `get_plans`, `put_plan`, `_require_super_admin`. Mounted with `TENANT_MANAGEMENT_GUARD`, loaded in `router_registry.py`, and `/api/platform/plans` added to the tenantManagement manifest routes.

## Task Commits

| Step | Commit | Message |
| ---- | ------ | ------- |
| 1 RED | f61f77089 | test(88-08): add failing tests for listing and editing the plan table with seat edits applied at once |
| 1 GREEN | 470c934bb | feat(88-08): list and edit the plan table; a seats edit reaches direct tenants without an override at once |
| 2 RED | 31853bfee | test(88-08): add failing tests for the Super Admin Plans API and its catalogue mount |
| 2 GREEN | b89193f12 | feat(88-08): the Super Admin Plans API, mounted under the Tenant Management catalogue |

## Decisions Made

- The `plan.updated` ledger write is wrapped (a failure is logged, not raised) like `plan_notices.announce`: the plan is already changed, and a 500 after the change would report a made edit as failed.
- The `seats.changed` notice carries the plan's old and new seat number (the plan-level before and after), not each tenant's previous stored number; `apply_plan_seats` returns ids only.
- Screens are compared as ordered lists, so the same set in a different order counts as an edit (the stored order is the submitted order).
- When the plans collection has no document for the plan, the upsert stores `key` plus the D-03 defaults for the fields not being edited, matching `ensure_plans`.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0.

## Notes

- `shared/catalogue-access.json` had an uncommitted file-mode change (644 to 755) from the user's tree before this plan. The commit stores the file at the HEAD mode (644, `git update-index --chmod=-x`); the working-tree mode change is left as it was and remains the user's.
- PROH-88-06: seats edits go only through `licensing.apply_plan_seats`, whose filter excludes partner customers and the platform organization; asserted by `test_a_seats_edit_reaches_direct_tenants_without_an_override_and_nobody_else`.
- Nothing was restarted, published or pushed; the Plans screen is 88-12.

## Known Stubs

None.

## Threat Flags

None. The new endpoints are the plan's own T-88-23 / T-88-24 surface (guard plus handler role check, strict bounds, audited).

## Self-Check: PASSED

- backend/plan_endpoints.py, backend/tests/test_plan_endpoints.py, backend/plan_service.py exist; commits f61f77089, 470c934bb, 31853bfee, b89193f12 are ancestors of HEAD.
- Verify commands: task 1 suite 56 passed; task 2 suite 113 passed (no skipped test); vitest catalogueAccess 44 passed.
