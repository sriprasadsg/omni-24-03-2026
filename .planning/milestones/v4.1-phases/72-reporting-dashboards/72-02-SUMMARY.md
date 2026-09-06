---
phase: 72-reporting-dashboards
plan: 02
subsystem: api
tags: [fastapi, mongodb, itam, reporting]

# Dependency graph
requires:
  - phase: 72-reporting-dashboards
    plan: 01
    provides: PREBUILT_REPORTS registry shape, RENDERERS format registry, build_report_rows aggregator, tenant-safe download route — this plan adds five entries into the same registry without touching any of that shape
  - phase: 59-procurement-finance
    provides: itam_finance_service.compute_book_value / REASON_NO_DEPRECIATION_POLICY (reused verbatim, no re-derivation)
  - phase: 57-lifecycle-checkin-checkout
    provides: itam_lifecycle_service.write_history's assignment_history ledger, itam_lifecycle_endpoints.AUDIT_INTERVAL_DAYS/_audit_cutoff_iso/_overdue_query/_overdue_row (imported and used unchanged)
  - phase: 60-licenses-consumables
    provides: itam_license_endpoints._enrich_license_seats_and_expiry (reused verbatim), Consumable/ConsumableCreate/ConsumableUpdate models this plan extends with reorderThreshold
provides:
  - Five new PREBUILT_REPORTS entries (asset_value, checkout_activity, overdue_audits, license_utilization, low_stock_consumables) — all six D-08 pre-built reports now registered
  - reorderThreshold optional field on ConsumableCreate/ConsumableUpdate/Consumable (D-19)
  - DEFAULT_LOW_STOCK_QUANTITY=5 module constant (the D-19 fallback heuristic)
affects: [72-03, 72-04, 72-05, 72-06, 72-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Batched cross-collection lookup: one db.X.find({\"id\": {\"$in\": [...]}}) call to resolve referenced ids in a report builder, never a per-row query or an aggregation $lookup (asset_value's asset_models batch, checkout_activity's assets batch)"
    - "Report builders import and reuse the owning surface's existing computation functions verbatim (compute_book_value, _overdue_query/_overdue_row, _enrich_license_seats_and_expiry) rather than re-deriving figures — the anti-fabrication guarantee this phase's threat model requires"

key-files:
  created: []
  modified:
    - backend/itam_reporting_prebuilt.py
    - backend/itam_models.py
    - backend/tests/test_itam_reporting_prebuilt.py

key-decisions:
  - "license_utilization's 'Manufacturer' column displays the raw manufacturerId as-is rather than resolving a manufacturer name — the plan's action text didn't specify a batched manufacturers lookup (unlike asset_value's explicit asset_models batch instruction), so no lookup was added to avoid overreaching scope."
  - "Split Task 1 and Task 2's itam_reporting_prebuilt.py/test file edits into two atomic commits despite both tasks touching the same files, by building the full Task-1+Task-2 implementation first, then temporarily reverting the Task-2-only hunks (via backup + restore) to produce a clean Task-1-only commit before reapplying Task 2 — preserves the plan's per-task commit contract without redoing work."

patterns-established: []

requirements-completed: [ITAM-REP-02]

coverage:
  - id: D1
    description: "Asset Value & Depreciation report: one row per asset with a purchase record, book value computed via compute_book_value (byte-equal to a direct call with the same inputs), em-dash + REASON_NO_DEPRECIATION_POLICY for assets with no/partial model depreciation policy, sorted descending by book value"
    requirement: "ITAM-REP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestAssetValueReport::test_returns_rows_sorted_desc_by_book_value"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestAssetValueReport::test_book_value_equals_direct_compute_book_value_call"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestAssetValueReport::test_missing_depreciation_policy_yields_dash_and_reason"
        status: pass
    human_judgment: false
  - id: D2
    description: "Check-Out / Check-In Activity report: fleet-wide assignment_history events newest-first, with asset tag/name resolved via a batched lookup"
    requirement: "ITAM-REP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestCheckoutActivityReport::test_returns_events_newest_first_with_resolved_asset"
        status: pass
    human_judgment: false
  - id: D3
    description: "Overdue Physical Audits report: returns exactly the assets itam_lifecycle_endpoints._overdue_query matches, using _overdue_row unchanged, sorted ascending by days overdue with unknown-basis rows last"
    requirement: "ITAM-REP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestOverdueAuditsReport::test_returns_exactly_the_assets_overdue_query_matches"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestOverdueAuditsReport::test_sorted_ascending_by_days_overdue_with_unknown_basis_last"
        status: pass
    human_judgment: false
  - id: D4
    description: "License Seat Utilization report: seatsAssigned/seatsAvailable/utilisation percent computed by _enrich_license_seats_and_expiry, sorted descending by utilisation, zero-seatCount licences report 0% without a division error"
    requirement: "ITAM-REP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestLicenseUtilizationReport::test_returns_rows_sorted_desc_by_utilization"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestLicenseUtilizationReport::test_zero_seat_count_reports_zero_percent_not_division_error"
        status: pass
    human_judgment: false
  - id: D5
    description: "Low-Stock Consumables report: flags a consumable at/below its set reorderThreshold, falls back to the DEFAULT_LOW_STOCK_QUANTITY=5 heuristic when unset, absent when above both"
    requirement: "ITAM-REP-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestLowStockConsumablesReport::test_flags_at_or_below_configured_threshold"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestLowStockConsumablesReport::test_no_threshold_uses_default_fallback_of_five"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestLowStockConsumablesReport::test_above_threshold_and_fallback_is_absent"
        status: pass
    human_judgment: false
  - id: D6
    description: "reorderThreshold is optional on ConsumableCreate/ConsumableUpdate/Consumable with a null default; an existing payload omitting it still validates"
    requirement: "ITAM-REP-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestReorderThresholdField::test_consumable_create_validates_with_field_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_reporting_prebuilt.py#TestReorderThresholdField::test_consumable_create_validates_with_field_set"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-08-17
status: complete
---

# Phase 72 Plan 02: Five Pre-Built Reports + reorderThreshold Summary

**Five new PREBUILT_REPORTS entries (asset_value, checkout_activity, overdue_audits, license_utilization, low_stock_consumables) completing D-08's six-report set, plus an optional per-consumable reorderThreshold field (D-19) — every report reuses its owning surface's existing computation function verbatim rather than re-deriving figures.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-08-17T07:38:00Z (approx.)
- **Completed:** 2026-08-17T08:06:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `asset_value`: one row per asset with a purchase record; book value computed via `itam_finance_service.compute_book_value` with the exact same depreciation-input resolution `get_asset_book_value` uses (batched `asset_models` lookup, never per-asset); assets with no/partial model policy get an em-dash and `REASON_NO_DEPRECIATION_POLICY`.
- `checkout_activity`: fleet-wide `assignment_history` read, newest-first, with a single batched `assets` lookup adding tag/name to each row.
- `overdue_audits`: delegates entirely to `itam_lifecycle_endpoints._overdue_query`/`_overdue_row`, imported and used unchanged — only new work is the display-row mapping and export wrapper.
- `license_utilization`: reuses `itam_license_endpoints._enrich_license_seats_and_expiry` verbatim so the report and the Licences tab can never disagree; zero-`seatCount` licences report 0% rather than raising.
- `low_stock_consumables`: flags a consumable at/below its own `reorderThreshold` when set, otherwise at/below the new `DEFAULT_LOW_STOCK_QUANTITY=5` module constant — the D-19 add-alongside fallback, no data migration required.
- `backend/itam_models.py`: `reorderThreshold: Optional[int] = Field(None, ge=0)` added to `ConsumableCreate` and `ConsumableUpdate`; `Consumable` inherits it with no separate declaration.
- All six D-08 pre-built reports now registered in `PREBUILT_REPORTS`; 19 new tests, full backend suite shows no new failures (11 pre-existing unrelated failures, identical before/after).

## Task Commits

Each task was committed atomically:

1. **Task 1: Asset value, check-out/in activity, and overdue-audit reports** - `2b8409fb` (feat)
2. **Task 2: Licence utilisation and low-stock consumables reports, with the reorderThreshold field** - `c192573d` (feat)

**Plan metadata:** _pending — this commit_

## Files Created/Modified
- `backend/itam_reporting_prebuilt.py` - added `asset_value`, `checkout_activity`, `overdue_audits` (Task 1) and `license_utilization`, `low_stock_consumables` (Task 2) builders + `PREBUILT_REPORTS` entries; `DEFAULT_LOW_STOCK_QUANTITY` constant; new imports from `itam_finance_service`, `itam_lifecycle_endpoints`, `itam_license_endpoints`
- `backend/itam_models.py` - `reorderThreshold: Optional[int] = Field(None, ge=0)` on `ConsumableCreate`/`ConsumableUpdate`
- `backend/tests/test_itam_reporting_prebuilt.py` - new file (created in Task 1, extended in Task 2): 19 tests across `TestRegistry`, `TestAssetValueReport`, `TestCheckoutActivityReport`, `TestOverdueAuditsReport`, `TestLicenseUtilizationReport`, `TestLowStockConsumablesReport`, `TestReorderThresholdField`

## Decisions Made
- `license_utilization`'s "Manufacturer" column displays the raw `manufacturerId` as-is (not a resolved manufacturer name) — the plan's action text specified a batched lookup for `asset_value`'s model resolution but not for a manufacturer-name join here, so none was added, avoiding scope creep beyond what was asked.
- Split each task's `itam_reporting_prebuilt.py`/test-file edits into two atomic commits (matching the plan's two `<task>` blocks) even though both tasks touch the same two files: built the full combined implementation first, verified it end-to-end, then temporarily reverted the Task-2-only hunks (backed up via `cp`, restored after the Task 1 commit) to produce a clean, independently-reviewable Task 1 commit before reapplying and committing Task 2. `itam_models.py` (Task-2-only) was reverted via `git checkout --` for the Task 1 commit and restored from backup afterward.

## Deviations from Plan

None (Rule 1-4) — the plan's code design worked as specified against the real codebase. One test-infrastructure fix was needed but is not a plan deviation: `checkout_activity`'s test needed a self-referencing `MagicMock` cursor (`.sort()`/`.limit()` returning itself, `.to_list()` the only async leaf) rather than the shared `itam_reporting_test_support.mock_db` fixture's default `_make_col()` chain, because an `AsyncMock`'s auto-created child attributes (like `.sort`) default to `AsyncMock` too — calling `.sort([...])` synchronously (as the real Motor cursor API does) then returns an unawaited coroutine rather than a chainable cursor. This exact fix is precedented in `itam_lifecycle_test_support.py`'s own `_history_cursor`; applied locally inside the new test file (which is not itself in the shared `itam_reporting_test_support.py` fixture module, so the shared fixture file was left untouched, matching this plan's `files_modified` scope).

## Issues Encountered
None beyond the test-infrastructure note above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All six D-08 pre-built reports are now registered in `PREBUILT_REPORTS` and reachable through the existing `list_prebuilt_reports`/`run_prebuilt_report`/CSV-export/download path 72-01 built — no endpoint or route changes were needed, confirming that plan's registry-seam design.
- `reorderThreshold` is live on the consumable models; a future admin-UI plan (72-03/72-04) can surface it as a form field with no backend change.
- `license_utilization`'s manufacturer-name-resolution gap (see Decisions Made) is a candidate follow-up if a later phase's UI review flags the raw id as confusing — not blocking, not tracked as a stub (the column renders correctly, just with an id instead of a name).

---
*Phase: 72-reporting-dashboards*
*Completed: 2026-08-17*

## Self-Check: PASSED

Both task commits (`2b8409fb`, `c192573d`) found in git history; all 3 modified files confirmed present on disk with expected content (`PREBUILT_REPORTS` has 6 keys, `reorderThreshold` present on all three consumable models, 19/19 tests in `test_itam_reporting_prebuilt.py` passing).
