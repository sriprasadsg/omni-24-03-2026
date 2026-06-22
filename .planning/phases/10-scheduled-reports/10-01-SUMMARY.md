---
phase: 10-scheduled-reports
plan: "01"
subsystem: backend/scheduled-reports
tags: [tdd, scheduled-reports, compliance-pdf, delivery-logging, smtp-validation]
status: complete
completed: "2026-06-22T13:20:53Z"
duration: ~6m
tasks_completed: 3
files_modified: 5

dependency_graph:
  requires:
    - 03-audit-ready-export/03-02 (compliance_reporting_pdf._generate_pdf)
    - 09-compliance-score-dashboard/09-01 (compliance_reports_endpoints._REPORTS_DIR)
  provides:
    - report_delivery_logs collection with compound index
    - GET /api/reports/scheduled/{id}/history endpoint
    - framework_id field on schedule documents
    - _write_delivery_log helper for per-delivery audit records
  affects:
    - backend/scheduled_reports_service.py
    - backend/scheduled_reports_endpoints.py
    - backend/database.py
    - backend/tests/test_scheduled_reports.py

tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN with asyncio.run() + TestClient + MagicMock/AsyncMock
    - Module-level email_service import for testability (vs local import)
    - Ephemeral PDF: generate to disk → read bytes → delete file

key_files:
  created:
    - backend/tests/test_scheduled_reports.py (362 lines, 7 tests)
  modified:
    - backend/scheduled_reports_service.py (406 → 496 lines)
    - backend/scheduled_reports_endpoints.py (97 → 103 lines)
    - backend/database.py (added schedule_history_idx compound index)

decisions:
  - email_service imported at module level (not inside _deliver_report) so patch target
    "scheduled_reports_service.email_service" resolves correctly in tests
  - smtp_config mocked to return a valid config in framework_id tests (SMTP validation is
    orthogonal to framework_id persistence; separating concerns keeps tests focused)
  - schedule_history_idx added to database.py (not app_startup.py as the plan suggested)
    because all other collection indexes live there; app_startup.py has no create_index calls
  - 422 status code (not 400) for ValueError from SMTP validation — matches plan intent
    and frontend expectation (reads d.detail from non-ok responses)
---

# Phase 10 Plan 01: Scheduled Reports — PDF Wiring, Delivery Logging, History Endpoint Summary

**One-liner:** Wired compliance PDF generator into scheduled delivery, added per-delivery audit logging to `report_delivery_logs`, and exposed `GET /history` endpoint — all via TDD.

## What Was Built

### Task 1 (RED) — Failing tests
Created `backend/tests/test_scheduled_reports.py` with 7 tests covering:
- `framework_id`/`framework_name` persistence in `create_schedule()`
- `insert_one` doc contains framework fields (list_schedules verification via DB write)
- `_generate_pdf_for_schedule` called when `framework_id` set
- `report_delivery_logs.insert_one` called with `status="success"` on successful run
- `report_delivery_logs.insert_one` called with `status="failure"` and `error` on failure
- `GET /{id}/history` returns `{"logs": [...], "total": N}`
- `POST` to create email schedule returns 422 when SMTP not configured

All 7 tests confirmed failing before implementation.

### Task 2 (GREEN) — Service implementation (`scheduled_reports_service.py`)
- Added `from email_service import email_service` and `import compliance_reporting_pdf` at module level
- Added `from compliance_reports_endpoints import _REPORTS_DIR` (no hardcoded string duplication)
- `create_schedule()`: Added `framework_id`/`framework_name` fields; added SMTP validation (`db.smtp_config.find_one({})` → raises `ValueError("SMTP not configured")` if None)
- `update_schedule()`: Added `framework_id`/`framework_name` to the allowed-fields tuple
- Added `_generate_pdf_for_schedule()`: awaits `compliance_reporting_pdf._generate_pdf()`, reads bytes from disk, deletes ephemeral file in finally block
- Added `_write_delivery_log()`: inserts to `report_delivery_logs` with id, schedule_id, tenant_id, framework_id, run_at, recipients, status, error, format, filename
- `_deliver_report()`: Updated signature to accept `tenant_id`; PDF branch checks `framework_id` and `report_type` before calling `_generate_pdf_for_schedule` vs `_build_pdf`; returns `delivered_filename`
- `run_report_now()`: Wrapped delivery in try/except; calls `_write_delivery_log` on both success and failure paths
- `start_report_scheduler()`: Same try/except pattern; calls `_write_delivery_log` for each delivery attempt
- Added `get_delivery_history()`: Queries `report_delivery_logs` filtered by `schedule_id` (+ `tenant_id` for non-super_admin), sorted by `run_at` descending, strips `_id`

### Task 3 — Endpoint and index wiring
- `scheduled_reports_endpoints.py`: Added `GET /{schedule_id}/history` route; changed `ValueError` mapping from `400` to `422`; added canonical URL comment above `run-now` route
- `database.py`: Added compound index `[("schedule_id", 1), ("run_at", -1)]` named `schedule_history_idx` on `report_delivery_logs` collection

## Test Results

```
7/7 tests PASSED in backend/tests/test_scheduled_reports.py
28/28 tests PASSED (including smoke tests — no regressions)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] email_service local import prevented module-level patching**
- **Found during:** Task 2 (GREEN)
- **Issue:** `_deliver_report` imported `email_service` locally (`from email_service import email_service`), so `patch("scheduled_reports_service.email_service")` raised `AttributeError`
- **Fix:** Moved import to module level; removed local import inside `_deliver_report`
- **Files modified:** `backend/scheduled_reports_service.py`
- **Commit:** b2cc58a

**2. [Rule 3 - Blocking] SMTP validation blocked unrelated create_schedule tests**
- **Found during:** Task 2 (GREEN)
- **Issue:** Tests for `framework_id` persistence call `create_schedule()` with `delivery_channel="email"` but did not mock `smtp_config.find_one` — once SMTP validation was added, they failed for the wrong reason
- **Fix:** Added `db.smtp_config.find_one = AsyncMock(return_value={"host": "smtp.example.com"})` in those tests
- **Files modified:** `backend/tests/test_scheduled_reports.py`
- **Commit:** b2cc58a

**3. [Rule 3 - Blocking] schedule_history_idx added to database.py not app_startup.py**
- **Found during:** Task 3
- **Issue:** Plan directed adding the index in `app_startup.py`, but `grep -rn "create_index"` shows all collection indexes live in `database.py`; `app_startup.py` has zero `create_index` calls
- **Fix:** Added index to `database.py` alongside all other collection indexes
- **Files modified:** `backend/database.py`
- **Commit:** 13f838f

## Known Stubs

None — all new code has real implementations. `_generate_pdf_for_schedule` invokes the live `compliance_reporting_pdf._generate_pdf` function. Delivery logs write real documents to MongoDB.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. The `GET /history` route is protected by `get_current_user` JWT dependency per T-10-01 disposition.

## TDD Gate Compliance

- RED gate: `test(10-01)` commit c22b504 — all 7 tests failed before implementation
- GREEN gate: `feat(10-01)` commit b2cc58a — all 7 tests pass after service implementation
- Additional `feat(10-01)` commit 13f838f for endpoint/index wiring (Task 3 is `type="auto"`, not TDD)

## Self-Check: PASSED

- backend/tests/test_scheduled_reports.py: EXISTS (362 lines)
- backend/scheduled_reports_service.py: EXISTS (496 lines, under 500)
- backend/scheduled_reports_endpoints.py: EXISTS (103 lines, GET /history present)
- database.py schedule_history_idx: EXISTS
- Commits c22b504, b2cc58a, 13f838f: all present in git log
- 7/7 tests pass
