---
phase: 72-reporting-dashboards
plan: 04
subsystem: api
tags: [fastapi, react, mongodb, itam, kpi, dashboard]

# Dependency graph
requires:
  - phase: 72-01
    provides: itam_reporting_prebuilt.PREBUILT_REPORTS registry (drilldownReportKey targets) and the tenant-safe ITAM reporting router pattern this plan's route mirrors
  - phase: 59-procurement-finance
    provides: itam_finance_service.compute_book_value / compute_warranty_status / get_warranty_alert_window (reused verbatim, no re-derivation)
  - phase: 57-lifecycle-checkin-checkout
    provides: itam_lifecycle_endpoints._overdue_query / _audit_cutoff_iso (reused verbatim, no re-derivation)
provides:
  - The compute_itam_kpis(db, tenant_id) service (backend/itam_reporting_kpis.py) — the four D-16 KPI aggregates every dashboard tile in Plan 72-07 reads
  - GET /api/itam/kpis (backend/itam_kpi_endpoints.py) — one tenant-scoped, admin-gated route returning all four KPIs
  - fetchItamKpis() in services/apiService.ts — the single client entry point Plan 72-07's KPI tile grid consumes
affects: [72-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "KPI aggregation calls the existing Finance/Licence/Lifecycle logic verbatim (compute_book_value, compute_warranty_status, get_warranty_alert_window, _overdue_query) rather than re-deriving it, so a dashboard tile can never disagree with its source tab"
    - "hasData boolean + drilldownReportKey on every KPI object — when hasData is false every numeric field is None, never a fabricated 0 or 100% presented as a real measurement (ITAM-REP-04 prohibition)"
    - "One batched db.assets.find() per compute_itam_kpis call, fanned out in Python to the assetValue/warrantyExpirations/overdue KPIs — never a per-KPI re-query or an aggregation join"

key-files:
  created:
    - backend/itam_reporting_kpis.py
    - backend/itam_kpi_endpoints.py
    - backend/tests/test_itam_reporting_kpis.py
  modified:
    - backend/router_registry.py
    - services/apiService.ts

key-decisions:
  - "assetCount/statusBreakdown in the assetValue KPI cover every tenant asset (not only those with a purchase record) so hasData correctly reflects 'zero assets in the tenant' and the status breakdown is a true fleet-wide picture — the drilldown report (asset_value prebuilt) still shows only assets with a purchase record, which is fine since the tile and its drilldown answer different questions (fleet composition vs. depreciation detail)"
  - "An asset with no purchase record at all (not just a missing depreciation policy) is folded into withoutPolicyCount rather than a separate counter, since the KPI's declared field set (totalBookValueCents/assetCount/withoutPolicyCount/statusBreakdown) has no slot for a fourth reason and both cases equally contribute nothing to the value sum"
  - "overdueAuditCount/overdueCheckinCount are computed with db.assets.count_documents rather than fetching full documents, since only counts are needed and this avoids a second full-fleet round trip on top of the already-fetched asset list"
  - "Warranty timeline buckets only active/expiring (not-yet-expired) assets into the next-12-months window — an already-expired warranty is reported in expiredCount but never occupies a timeline slot, since the timeline's purpose is 'what's coming', not a historical record"

patterns-established:
  - "Cross-tenant isolation for a pure aggregation service is tested with a lightweight real-filtering fake db (not the shared fixed-return mock_db), wrapped by the existing MockTenantIsolatedDatabase so tenantId auto-injection is exercised for real — reusable for any future KPI/aggregate plan needing a genuine two-tenant proof"

requirements-completed: [ITAM-REP-04]

coverage:
  - id: D1
    description: "GET /api/itam/kpis returns all four D-16 KPIs (asset value + status breakdown, licence seat utilisation, warranty expirations + 12-month timeline, overdue check-in/audit counts) for the caller's tenant in one call, each carrying hasData and a drilldownReportKey"
    requirement: "ITAM-REP-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_reporting_kpis.py#TestAssetValueKpi/TestLicenseUtilizationKpi/TestWarrantyExpirationsKpi/TestOverdueKpi"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_kpis.py#TestItamKpiRoute::test_get_kpis_returns_200_with_four_kpi_keys"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every KPI reports an explicit no-data signal (hasData=false, every numeric field None) instead of a fabricated zero or 100% when its underlying collection is empty"
    requirement: "ITAM-REP-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_reporting_kpis.py#TestNoDataAndDrilldownKeys::test_every_kpi_reports_no_data_on_empty_tenant_never_a_fabricated_number"
        status: pass
    human_judgment: false
  - id: D3
    description: "The warranty-expiring alert-window boundary is inherited verbatim from itam_finance_service (inclusive at the exact window edge), and the overdue-audit count reuses itam_lifecycle_endpoints._overdue_query unchanged"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_reporting_kpis.py#TestWarrantyExpirationsKpi::test_expiring_soon_boundary_is_inclusive"
        status: pass
    human_judgment: false
  - id: D4
    description: "KPI aggregates are tenant-scoped — a second tenant's assets, licences and overdue rows never contribute to the first tenant's numbers"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_reporting_kpis.py#TestTenantIsolation::test_seeding_a_second_tenant_does_not_change_the_first_tenants_kpis"
        status: pass
    human_judgment: false
  - id: D5
    description: "The KPI route is gated by the same _require_itam_admin dependency as every other ITAM management route, returns 403 with no tenant id, and converts a backend exception into a generic 500 (never leaking internals)"
    requirement: "ITAM-REP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_kpis.py#TestItamKpiRoute::test_get_kpis_returns_403_when_permission_check_fails / test_get_kpis_returns_403_when_no_tenant_id / test_get_kpis_returns_500_with_generic_detail_on_backend_exception"
        status: pass
    human_judgment: false
  - id: D6
    description: "fetchItamKpis() in services/apiService.ts is reachable as the KPI panel's single client entry point"
    verification:
      - kind: other
        ref: "grep -c fetchItamKpis services/apiService.ts (>=1); npm run build exits 0"
        status: pass
    human_judgment: false

# Metrics
duration: 46min
completed: 2026-08-17
status: complete
---

# Phase 72 Plan 04: ITAM Dashboard KPIs Summary

**Server-side computation of the four D-16 ITAM dashboard KPIs (asset value + lifecycle breakdown, licence utilisation, warranty expirations + 12-month timeline, overdue audits/check-ins) from the existing Finance/Licence/Lifecycle logic verbatim, exposed on one tenant-scoped `/api/itam/kpis` route.**

## Performance

- **Duration:** 46 min
- **Started:** 2026-08-17T07:59:00Z (approx.)
- **Completed:** 2026-08-17T08:45:00Z
- **Tasks:** 2
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- `backend/itam_reporting_kpis.py::compute_itam_kpis(db, tenant_id)` computes all four KPIs from one batched `db.assets.find()` call fanned out in Python, calling `itam_finance_service.compute_book_value`/`compute_warranty_status`/`get_warranty_alert_window` and `itam_lifecycle_endpoints._overdue_query` verbatim rather than re-deriving any of that logic.
- Every KPI carries `hasData` and `drilldownReportKey` (verified to match real `itam_reporting_prebuilt.PREBUILT_REPORTS` keys); when `hasData` is false every numeric field is `None` — no fabricated zero or 100% is ever emitted.
- `backend/itam_kpi_endpoints.py` mounts `GET /api/itam/kpis` at a router prefix distinct from `/api/itam/reports` (never a sub-path, so no shadowing risk under any registration order), gated by the real `_require_itam_admin` import and registered in `router_registry.py` directly after `itam_reporting_endpoints`.
- `services/apiService.ts` gained `fetchItamKpis()` and the five `ItamKpis`/`ItamAssetValueKpi`/`ItamLicenseUtilizationKpi`/`ItamWarrantyExpirationsKpi`/`ItamOverdueKpi` interfaces Plan 72-07's KPI tile grid will consume.
- 15 new tests (11 service-level, 4 route-level) all green, including a real cross-tenant isolation proof built on a lightweight filtering fake db (not the shared fixed-return mock) and a direct `compute_book_value` equality assertion.

## Task Commits

Each task was committed as a RED/GREEN pair (both tasks are `tdd="true"`):

1. **Task 1: compute_itam_kpis — the four tenant-scoped aggregates**
   - `87f98507` (test) — RED: failing tests, no `itam_reporting_kpis` module yet
   - `682810c4` (feat) — GREEN: `compute_itam_kpis` implementation, 11/11 pass
2. **Task 2: The /api/itam/kpis route and its client function**
   - `88aaf5a8` (test) — RED: failing route tests, no `itam_kpi_endpoints` module yet
   - `fd633aea` (feat) — GREEN: route + router registration + `fetchItamKpis`, 15/15 pass

**Plan metadata:** _pending — this commit_

## Files Created/Modified
- `backend/itam_reporting_kpis.py` - `compute_itam_kpis` + four `_compute_*_kpi` helpers, `_status_breakdown`, `_next_twelve_month_keys`
- `backend/itam_kpi_endpoints.py` - `GET /api/itam/kpis` route, admin-gated, 403 on missing tenant id, generic 500 on backend exception
- `backend/router_registry.py` - registers `itam_kpi_endpoints.router` directly after `itam_reporting_endpoints`
- `backend/tests/test_itam_reporting_kpis.py` - 15 tests: per-KPI behavior (status breakdown order, book-value equality, ValueError handling, seat math, zero-seat no-data, boundary-inclusive expiring, 12-month timeline, overdue counts), cross-cutting no-data assertion, tenant-isolation proof, and 4 route-level tests
- `services/apiService.ts` - `fetchItamKpis()` + 5 exported KPI interfaces

## Decisions Made
- `assetValue`'s `assetCount`/`statusBreakdown` cover every tenant asset (not only those with a purchase record), so `hasData` correctly reflects "zero assets in the tenant" as a fleet-wide statement, distinct from the `asset_value` drilldown report which (by design, from Plan 72-01) only lists assets with a purchase record.
- An asset with no purchase record at all is folded into `withoutPolicyCount` alongside assets that do have a purchase record but no matching depreciation policy — the KPI's declared field set has no separate slot for that distinction, and both cases equally contribute nothing to `totalBookValueCents`.
- Overdue counts use `db.assets.count_documents` rather than fetching full documents, since only the counts are needed.
- The warranty timeline only buckets active/expiring assets into the next-12-months window; an already-expired warranty is counted in `expiredCount` but never occupies a timeline slot.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' `<behavior>`/`<action>`/`<verify>`/`<acceptance_criteria>` sections were implemented as specified; the field-set ambiguities noted above (assetCount scope, without-policy bucketing) were resolved by inference from the plan's own wording and documented as decisions rather than deviations, since no rule (1-4) was triggered — nothing was broken, missing-critical, blocking, or architectural.

## Issues Encountered
- `backend/tests/conftest.py`'s shared `_make_col()` helper does not configure `count_documents` (only `find`/`find_one`/`update_one`/`delete_one`/`find`/`distinct`/`aggregate`), so every test touching `license_assignments.count_documents` or `assets.count_documents` needed an explicit `AsyncMock` — added a `_seed_defaults()` helper in the test file that sets safe defaults (`return_value=0`) so individual tests only override what they need. Not a code bug — a pre-existing test-infra gap, worked around locally within the new test file per its file-scope restriction (this plan's `<files>` list did not include `itam_reporting_test_support.py`).
- Full backend suite run (2275 passed / 34 skipped / 13 failed) — all 13 failures confirmed pre-existing and unrelated to this plan's 5 files (`test_webhook_logic.py`, `test_agentic_ai.py`, `test_e2e_integration.py`, `test_itam_audit.py`, `test_powershell_evidence.py`, `test_rotate_key_wiring.py`, `test_rust_heartbeat_parity.py`, `test_secret_manager_service.py`): confirmed by isolated re-runs and by checking that the touched source files (`itam_finance_endpoints.py`, webhook/powershell/vault/rotate-key modules) were last modified by unrelated prior-phase commits, none of which this plan touches. No regression introduced by this plan.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `fetchItamKpis()` and the `ItamKpis`/`ItamAssetValueKpi`/`ItamLicenseUtilizationKpi`/`ItamWarrantyExpirationsKpi`/`ItamOverdueKpi` interfaces are in place and unchanged in shape — Plan 72-07's KPI tile grid can consume them directly, using each KPI's `drilldownReportKey` to drive `ReportsPanel.tsx`'s existing `focusReportKey` seam from Plan 72-01.
- No manual/UAT verification item is outstanding for this plan — every must-have truth and prohibition is covered by an automated test (see `coverage:` block above).

---
*Phase: 72-reporting-dashboards*
*Completed: 2026-08-17*

## Self-Check: PASSED

All 4 created/modified files (`backend/itam_reporting_kpis.py`, `backend/itam_kpi_endpoints.py`, `backend/tests/test_itam_reporting_kpis.py`, this SUMMARY.md) found on disk; all 4 task commits (`87f98507`, `682810c4`, `88aaf5a8`, `fd633aea`) found in git history.
