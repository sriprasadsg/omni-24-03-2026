---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 04
subsystem: api
tags: [rbac, catalogue-manifest, assets, itam, api-keys, finance-fields]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / MOUNTS convention / parity helpers (76-01), full manifest (76-02)
provides:
  - backend/catalogue_mounts_assets.py (assets slice MOUNTS + named guards reused route-level)
  - route-level guards on asset routes in compliance_status, compliance_evidence and security_scans modules
  - backend/asset_finance_fields.py (ASSET_FINANCE_FIELDS, can_view_finance, strip_finance, strip_finance_many, finance_filtered)
  - catalogue_guard honours a write scope on safe methods for API keys (D-02 compatibility)
affects: [76-05, 76-06, 76-07, 76-08, 76-09, 76-10, 76-11, 77]

actuals:
  tokens: 60000
  tasks: 3
  commits: 6
plan_head_before: e4fe774cc
plan_head_after: a04d6be86

tech-stack:
  added: []
  patterns:
    - "Slice mount map exports named guards; modules that mix catalogues on one router import them as route-level dependencies"
    - "Response transform decorator sits outside @cached so the per-request permission check is never cached"

key-files:
  created:
    - backend/catalogue_mounts_assets.py
    - backend/asset_finance_fields.py
    - backend/tests/test_catalogue_slice_assets.py
    - backend/tests/test_asset_finance_fields.py
  modified:
    - backend/catalogue_guards.py
    - backend/asset_endpoints.py
    - backend/itam_label_endpoints.py
    - backend/itam_lifecycle_endpoints.py
    - backend/compliance_status_endpoints.py
    - backend/compliance_evidence_endpoints.py
    - backend/security_scans_endpoints.py
    - backend/tests/test_catalogue_guards.py
    - backend/tests/test_itam_asset_request_endpoints.py
    - backend/tests/test_catalogue_route_parity.py

key-decisions:
  - "ITAM routers whose routes live under /api/assets/{id}/... (itam_asset, itam_finance, asset_components_router) take the assetManagement guard, because the manifest owns /api/assets; their handler-level _require_itam_* still demands view:itam"
  - "itam_lifecycle and itam_label mix /api/assets/{id}/... and ITAM-owned report/sheet paths on one router, so they get route-level guards instead of a MOUNTS entry"
  - "An API key scoped to a catalogue write permission may also read it (safe methods only); the role check stays read-only (D-03). Needed because _require_itam_viewer always accepted manage:assets keys"
  - "finance_filtered wraps the handler outside @cached: the cache keeps the full document and the strip runs per request, so a role edit takes effect immediately (resolves EDGE-ACC-04-concurrency for finance visibility)"

requirements-completed: [ACC-04]

coverage:
  - id: D1
    description: "Every user route of slice_modules('assets') carries the manifest guard; parity_offenders empty"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_assets.py#test_assets_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Real app: denying role 403 on /api/assets and an ITAM GET; view:assets, itam_admin (D-03) and itam_viewer not refused"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_assets.py#test_assets_real_app_enforced, #test_itam_reads_follow_view_itam_on_real_app, #test_compliance_and_scan_asset_routes_enforced_on_real_app"
        status: pass
    human_judgment: false
  - id: D3
    description: "ITAM API keys behave as before: view:itam scope reads, view:assets scope refused, role checked first (D-02)"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_assets.py#test_itam_api_key_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_guards.py#test_write_scope_also_authorises_a_read_but_never_the_reverse"
        status: pass
    human_judgment: false
  - id: D4
    description: "List, search and detail omit finance keys without view:itam/manage:itam; ITAM callers and super-admin keep them; no mutation; cache does not cross callers; role edit immediate (D-04, D-10)"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_asset_finance_fields.py (11 tests)"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-10-13
status: complete
---

# Phase 76 Plan 04: Assets, ITAM and Certificates Slice Summary

**Assets, ITAM and Certificates now refuse callers without the catalogue permission on the real app, ITAM API keys behave as before, and /api/assets list/search/detail drop purchase, warranty and depreciation fields for callers without view:itam.**

## Accomplishments
- `catalogue_mounts_assets.py`: 17 MOUNTS entries (assets 2, ITAM-under-/api/assets 3, ITAM API-key 8, ITAM session-only 3, certificates 1) plus named guards `ASSETS_GUARD`, `ASSETS_API_KEY_GUARD`, `ITAM_GUARD`, `ITAM_API_KEY_GUARD`, `CERTIFICATES_GUARD`, `VULNERABILITY_GUARD`. `itam_component_endpoints` is mounted twice (`router` -> ITAM, `asset_components_router` -> assetManagement).
- Route-level guards: `itam_lifecycle_endpoints` (checkout, checkin, history, audit -> assetManagement; overdue-audit report -> ITAM), `itam_label_endpoints` (QR/barcode -> assetManagement; label sheet -> ITAM), `compliance_status_endpoints` (PATCH status), `compliance_evidence_endpoints` (POST/GET/DELETE under /api/assets), `security_scans_endpoints` (POST /assets/{id}/scan -> assetManagement; POST /vulnerability-scans/schedule -> vulnerabilityManagement). `/api/compliance/...` governance routes untouched.
- `asset_finance_fields.py` (67 lines) and three `@finance_filtered` lines in `asset_endpoints.py` (now 515 lines; it was already over 500).
- Existing `_require_itam_*` and handler checks are unchanged (PROH-76-01, D-02).

## slice_modules("assets") vs expected
Identical to the plan's expected list (21 modules): asset_endpoints, asset_metrics_endpoints, certificate_endpoints, compliance_evidence_endpoints, compliance_status_endpoints, itam_asset_endpoints, itam_asset_request_endpoints, itam_catalog_endpoints, itam_component_endpoints, itam_consumable_endpoints, itam_customization_endpoints, itam_data_endpoints, itam_finance_endpoints, itam_kpi_endpoints, itam_label_endpoints, itam_license_endpoints, itam_lifecycle_endpoints, itam_procurement_endpoints, itam_reporting_endpoints, itam_ticketing_endpoints, security_scans_endpoints.

## Final ASSET_FINANCE_FIELDS
`purchaseCostCents`, `purchaseDate`, `poNumber`, `purchase_order_id`, `supplierId`, `warrantyMonths`, `warranty_expiry_date`, `warrantyAlertSentAt`, `warrantyExpiresAt`, `warrantyStatus`, `salvage_value`, `salvageValueCents`, `useful_life_years`, `usefulLifeYears`, `bookValueCents`, `currentBookValueCents`. The four beyond the plan's list are names the finance and reporting services compute, stripped in case a stored document carries them.

## Task Commits
1. `55bc4e35a` (feat): assets slice mounts, ITAM route-level guards, write-scope read rule, slice/real-app/API-key tests
2. `f46c376bf` (feat): asset routes in compliance and scan modules
3. RED `38d7a1731` (test): finance strip tests
4. GREEN `8293d879b` (feat): `asset_finance_fields.py` + handler wiring
5. `e8b97d934` (test): asset-request test principal given a role holding the ITAM permissions
6. `a04d6be86` (fix, 76-03 follow-up): slice partition test reads views from `sidebarPresentation.tsx`

## TDD Gate Compliance
RED `38d7a1731` precedes GREEN `8293d879b`. The RED run output was not captured in the session that wrote this summary; the RED file exercises the real handlers through HTTP, so before GREEN it fails on the finance keys being present (behaviour), not on imports. No REFACTOR commit.

## Numbers
- Plan verification: `test_catalogue_slice_assets.py` 5, `test_asset_finance_fields.py` 11, `test_catalogue_guards.py` 18, `test_route_auth_baseline.py` 20, `test_itam_asset_request_endpoints.py` 10 -> 64 passed.
- Full backend suite: 3331 passed, 1 failed, 47 skipped (5m39s). The failure was `test_catalogue_route_parity.py::test_slices_partition_every_in_scope_catalogue_once` (see deviation 2); after the fix the file passes 7/7, giving 3332 passed / 47 skipped (76-02 baseline 3315 / 47; +17 tests from 76-04, no regressions).

## Deviations from Plan

**1. [Rule 2 - Compatibility] Write scope authorises a read for API keys**
- **Found during:** Task 1 (test_itam_api_key_unchanged)
- **Issue:** `_require_itam_viewer` has always accepted keys scoped `manage:assets`; the catalogue guard checked only the read list for safe methods, so those keys would have started getting 403 on ITAM reads (breaks D-02).
- **Fix:** `check_catalogue_access` also accepts the write scopes on safe methods for API keys; the role check is unchanged and the reverse (read scope on a write) is still refused. Negative control added to `test_catalogue_guards.py`.
- **Files modified:** backend/catalogue_guards.py, backend/tests/test_catalogue_guards.py
- **Commit:** 55bc4e35a

**2. [Rule 3 - Blocking] 76-03 left a backend parity test reading the old Sidebar literal**
- **Found during:** full-suite run
- **Issue:** 76-03 moved the per-view entries into `components/sidebarPresentation.tsx`; the partition test still regex-scanned `Sidebar.tsx`, parsed zero views and failed. 76-03 did not run the backend suite.
- **Fix:** test reads view keys from the presentation map (checked mechanically: same 188 views as the pre-76-03 `Sidebar.tsx`), plus an assertion that the parse is non-empty. Test-only.
- **Files modified:** backend/tests/test_catalogue_route_parity.py
- **Commit:** a04d6be86

**3. [Design] Strip placed outside @cached, as a decorator**
- The plan asked to keep `@cached` and return stripped copies; `finance_filtered` does that from outside the cache, so the cache stores full documents and the permission check runs per request. This removes the up-to-60 s stale window RESEARCH A5 predicted for finance visibility (test_role_edit_takes_effect_before_the_cache_expires).

**Total deviations:** 2 auto-fixed, 1 design choice. **Impact:** none on scope.

## Tests changed to fix 403s
- `test_itam_asset_request_endpoints.py`: three principals moved from role `user` to `admin` (holds view:itam, request:assets, manage:procurement). Role `user` never held `request:assets`, so the handlers would have refused it anyway; the only roles holding `request:assets` (`admin`, `itam_user`) also hold `view:itam`, so no real requester loses access.

## Manifest corrections for 76-11 (not applied)
- `/api/assets/{id}/purchase`, `/book-value`, `/warranty`, `/components`, and the lifecycle routes (`checkout`, `checkin`, `history`, `audit`) are ITAM features under the assetManagement prefix. The guard follows the manifest (view:assets) and the handlers still demand view:itam, so nothing leaks, but the manifest could own these sub-paths under `itam` so the catalogue guard and the handler agree.

## Phase 77 UX notes
- A view:assets holder without view:itam now gets asset rows with no purchase/warranty keys; any asset UI that renders those columns should hide them rather than show blanks.
- Certificates read with view:assets but write with manage:settings (manifest as written); a role with view:assets but not manage:settings can open Certificates but every change returns 403.

## Known Stubs
None.

## Threat Flags
None new. T-76-28 (guards + parity + real-app probe), T-76-29 (API-key regression), T-76-03 and T-76-11 (strip, no-mutation and cache-order tests) mitigated. PROH-76-02: other asset read paths that return finance keys (`itam_finance_endpoints`, ITAM reporting/data) keep handler-level view:itam checks; verified by reading their dependencies, not by a dedicated test.

## Self-Check: PASSED
- backend/catalogue_mounts_assets.py, backend/asset_finance_fields.py, both new test files exist; commits 55bc4e35a, f46c376bf, 38d7a1731, 8293d879b, e8b97d934, a04d6be86 are on HEAD.
- No service restarts, deploys or writes to the live database.

---
*Phase: 76-catalogue-manifest-backend-route-enforcement*
*Completed: 2026-10-13*
