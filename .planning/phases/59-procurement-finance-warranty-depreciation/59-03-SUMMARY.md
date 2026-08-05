---
phase: 59-procurement-finance-warranty-depreciation
plan: 03
subsystem: api
tags: [fastapi, itam, finance, warranty, notifications-prep]

# Dependency graph
requires:
  - phase: 59-procurement-finance-warranty-depreciation
    provides: "59-01's itam_finance_service.py/itam_finance_endpoints.py pair, AssetPurchaseUpdate, purchaseDate/warrantyMonths persisted fields, and the warrantyAlertSentAt reset contract; 59-02's itam.warranty_expiring notification vocabulary"
provides:
  - "GET /api/assets/{asset_id}/warranty — RBAC-gated, tenant-scoped, read-only warranty status/expiry/days-remaining/alert-window report"
  - "itam_finance_service.compute_warranty_status — the single definition of warranty status this plan's route and Plan 59-04's background sweep both call"
  - "itam_finance_service.get_warranty_alert_window — per-tenant configurable alert window (system_settings doc, tenant->global->30-day-default lookup), callable from either a raw or wrapped db handle"
  - "itam_finance_service._add_months — calendar-safe month arithmetic (Avery-clamp-shaped day handling) other date math in this phase can reuse"
affects: [59-04-warranty-alert-sweep, 61-frontend-itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure status-computation function shared verbatim between a read route and a background sweep, so on-screen status and alert-trigger condition can never drift apart"
    - "Dual-call-site db unwrap guard (`db._db if hasattr(db, '_db') else db`) cloned from get_sla_at_risk_window, proven with a plain-class (non-MagicMock) raw-db stub"
    - "Calendar-safe month addition via calendar.monthrange day-clamp instead of a date library"

key-files:
  created: []
  modified:
    - backend/itam_finance_service.py
    - backend/itam_finance_endpoints.py
    - backend/tests/test_itam_finance_warranty.py (new file, created by Task 1, extended by Task 2)

key-decisions:
  - "_add_months implemented with plain calendar.monthrange arithmetic (6 lines) rather than dateutil/arrow/pendulum, per RESEARCH's Don't-Hand-Roll table and the plan's explicit instruction"
  - "compute_warranty_status degrades every unparseable/missing input to status none with a null expiry rather than raising, matching compute_book_value's ValueError convention but returning a benign result instead of propagating — required because this function will also be called from Plan 59-04's background sweep, where a raised exception is silently swallowed by the outer handler and would stop all alerting"
  - "get_warranty_alert_window cloned field-for-field from get_sla_at_risk_window (setting type/default renamed only) rather than generalized into a shared helper — matches the plan's explicit instruction and the codebase's existing precedent of parallel, not-DRY'd, per-feature window lookups (evidence_staleness, remediation_sla)"

requirements-completed: []

coverage:
  - id: D1
    description: "An operator with manage:assets can call GET /api/assets/{asset_id}/warranty for an asset in their own tenant and see warranty expiry, status, and days remaining (ITAM-FIN-02, ROADMAP success criterion 2 first half)"
    requirement: "ITAM-FIN-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_finance_warranty.py::TestWarrantyRouteEndToEnd"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_finance_warranty.py::TestWarrantyRouteAccess"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_warranty.py::TestWarrantyStatusCompute"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_warranty.py::TestAddMonths"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_warranty.py::TestWarrantyAlertWindow"
        status: pass
    human_judgment: false

# Metrics
duration: 30min
completed: 2026-08-05
status: complete
---

# Phase 59 Plan 03: Warranty Status Computation + Read Route Summary

**Warranty expiry/status computed at read time from purchaseDate+warrantyMonths via one pure function (`compute_warranty_status`), classified against a per-tenant configurable alert window (`get_warranty_alert_window`), both exposed read-only through `GET /api/assets/{asset_id}/warranty` — the exact two functions Plan 59-04's background sweep will call, so an operator's on-screen status and their alert condition can never disagree.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-08-05
- **Tasks:** 2
- **Files modified:** 3 (2 modified, 1 new test file)

## Accomplishments
- `_add_months`, `compute_warranty_status`, and `get_warranty_alert_window` added to `itam_finance_service.py` — all pure/DB-parameter-only, no FastAPI or database import added to the module
- `GET /api/assets/{asset_id}/warranty` added to `itam_finance_endpoints.py`: RBAC-gated (`manage:assets`), tenant-scoped (cross-tenant id returns the same 404 as an unknown id), read-only (no write assertion pinned by test), and a provable pass-through onto the two service-layer functions — the route never re-classifies or recomputes
- 58 new automated tests in `backend/tests/test_itam_finance_warranty.py` (25 from Task 1, 33 cumulative through Task 2) pin: calendar-safe month arithmetic including leap-year and Avery-style day-clamp cases, every warranty-status row (active/expiring/expired/none) including both sides of the alert-window boundary, the full alert-window lookup order with the dual raw/wrapped-db call-site guard proven via a plain-class stub (not a `MagicMock`, which would auto-create `_db` and make the raw-handle case vacuous), and the route's RBAC/tenant-isolation/degraded-input/no-write contract
- ITAM-FIN-02's status-visibility half (ROADMAP success criterion 2, first half) is now delivered; the alert-delivery half remains Plan 59-04's scope

## Task Commits

Each task was committed atomically:

1. **Task 1: Warranty status computation and the per-tenant alert window** — `8cbf9eb` (feat)
2. **Task 2: The warranty read route, end to end** — `bbc78fa` (feat)

**Plan metadata:** (this commit, following SUMMARY write)

## Files Created/Modified
- `backend/itam_finance_service.py` - Added `WARRANTY_STATUS_NONE`/`ACTIVE`/`EXPIRING`/`EXPIRED` constants, `WARRANTY_ALERT_WINDOW_SETTING_TYPE`/`_DEFAULT_WARRANTY_ALERT_WINDOW_DAYS`, `_add_months`, `compute_warranty_status`, `get_warranty_alert_window`. Now 184 lines (was 63). Still imports no FastAPI/database symbol.
- `backend/itam_finance_endpoints.py` - Added `GET /{asset_id}/warranty` route + import of `compute_warranty_status`/`get_warranty_alert_window`; updated module docstring's route ownership list. Now 209 lines (was 163).
- `backend/tests/test_itam_finance_warranty.py` - New file. `TestAddMonths` (7), `TestWarrantyStatusCompute` (10), `TestWarrantyAlertWindow` (8), `TestWarrantyRouteEndToEnd` (6), `TestWarrantyRouteAccess` (2) — 33 tests total, 392 lines.

## Decisions Made
- `_add_months` uses the exact `total = dt.month - 1 + months; year = dt.year + total // 12; month = total % 12 + 1` formula from the plan, with `min(dt.day, calendar.monthrange(year, month)[1])` day-clamp — pinned by leap/non-leap February and the 31st-plus-N-months cases.
- `compute_warranty_status` classification boundary: `days_to_expiry <= alert_window_days` is `expiring` (not `<`), so a caller at exactly the window boundary sees `expiring` — pinned by `test_warranty_status_compute_boundary_exactly_at_window_is_expiring`/`..._one_day_further_is_active`.
- `get_warranty_alert_window` accepts only `isinstance(doc.get("windowDays"), int)` — a stored string like `"60"` is treated as absent and the lookup continues to the next step, matching `get_sla_at_risk_window`'s own contract exactly (not loosened for warranty).
- Route response merges the three `compute_warranty_status` keys directly (`**status_result`) rather than renaming/reshaping them, so the route is provably a pass-through — a direct unit-test call to `compute_warranty_status` with the same inputs is asserted equal to the route's JSON body in `test_warranty_route_status_matches_direct_compute_call`.

## Deviations from Plan

None — plan executed exactly as written. All two tasks' automated `<verify>` commands and acceptance criteria pass as specified.

## Issues Encountered

None. `backend/tests/test_graphql.py` continues to fail collection in this environment due to the pre-existing `strawberry`/`pydantic` version incompatibility documented in prior phase summaries — excluded from full-suite runs, unrelated to this plan's files.

## User Setup Required

None — no external service configuration required. This plan adds no new dependency and no new persisted field (warranty expiry is derived, never stored, per PD-04).

## Next Phase Readiness
- Plan 59-04 (background warranty-alert sweep) can now import `compute_warranty_status` and `get_warranty_alert_window` directly — both take `db` as a plain parameter and the alert-window function's dual-call-site guard is already proven against a raw handle with no `_db` attribute, exactly the shape the sweep will use.
- No blockers. Full backend suite: 1786 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity`) — identical failure set to the documented baseline, no regressions. `test_graphql.py` excluded per the documented pre-existing collection error.
- Per this plan's own success_criteria: ITAM-FIN-02 is NOT marked fully complete in REQUIREMENTS.md by this plan alone — 59-02 delivered the notification-vocabulary half, this plan (59-03) delivers the status-visibility half, and 59-04 (the actual alert sweep/delivery) remains outstanding. This SUMMARY's `requirements-completed:` frontmatter is left empty for that reason; the plan's contribution is tracked via the `coverage:` block instead.

---
*Phase: 59-procurement-finance-warranty-depreciation*
*Completed: 2026-08-05*

## Self-Check: PASSED

- FOUND: backend/itam_finance_service.py
- FOUND: backend/itam_finance_endpoints.py
- FOUND: backend/tests/test_itam_finance_warranty.py
- FOUND: .planning/phases/59-procurement-finance-warranty-depreciation/59-03-SUMMARY.md
- FOUND commit: 8cbf9eb
- FOUND commit: bbc78fa
