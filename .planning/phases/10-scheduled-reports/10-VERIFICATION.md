---
phase: 10-scheduled-reports
verified: 2026-06-22T14:00:00Z
status: passed
score: 10/10
behavior_unverified: 0
overrides_applied: 0
---

# Phase 10: Scheduled Compliance Reports — Verification Report

**Phase Goal:** Tenant admins can configure a recurring report schedule (daily/weekly/monthly) per framework; the backend generates and emails a PDF compliance report to configured recipients on each run; delivery history is viewable from the Reports page.

**Verified:** 2026-06-22T14:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | framework_id and framework_name are stored on schedule creation | VERIFIED | `backend/scheduled_reports_service.py` lines 110–111: `"framework_id": data.get("framework_id") or None, "framework_name": data.get("framework_name") or None` inserted into schedule dict and persisted via `db.report_schedules.insert_one` |
| 2 | PDF generation uses `compliance_reporting_pdf._generate_pdf()` (awaited), not `_build_pdf`, when framework_id is set | VERIFIED | `_generate_pdf_for_schedule()` at line 154 does `result = await compliance_reporting_pdf._generate_pdf(...)`. `_deliver_report()` at lines 415–417 conditionally calls `await _generate_pdf_for_schedule(...)` when `framework_id and report_type in ("compliance_summary", "custom_framework")` |
| 3 | Delivery log written after each run with run_at, status, recipients, error_message | VERIFIED | `_write_delivery_log()` at lines 167–186 inserts `{id, schedule_id, tenant_id, framework_id, run_at, recipients, status, error, format, filename}` to `db.report_delivery_logs`. Called in `run_report_now()` on both success (line 263) and failure (line 265) paths, and in `start_report_scheduler()` loop on both success (line 473) and failure (line 489) paths |
| 4 | `GET /{schedule_id}/history` endpoint returns delivery logs | VERIFIED | `backend/scheduled_reports_endpoints.py` lines 90–93: `@router.get("/{schedule_id}/history")` wired to `svc.get_delivery_history()` returning `{"logs": logs, "total": len(logs)}` |
| 5 | `report_delivery_logs` collection has compound index on (schedule_id, run_at) | VERIFIED | `backend/database.py` lines 299–302: `await mongodb.db.report_delivery_logs.create_index([("schedule_id", 1), ("run_at", -1)], name="schedule_history_idx")` |
| 6 | SMTP unconfigured returns 422 on schedule creation | VERIFIED | `create_schedule()` at lines 83–86 calls `await db.smtp_config.find_one({})` and raises `ValueError("SMTP not configured")` if None. Endpoints file line 63–64 maps `ValueError` to `HTTPException(status_code=422)` |
| 7 | Frontend shows framework picker for compliance_summary/custom_framework report types | VERIFIED | `ScheduledReportsDashboard.tsx` lines 345–354: conditional `(form.report_type === 'compliance_summary' \|\| form.report_type === 'custom_framework') && (...)` renders a select with options from `frameworks` state populated via `fetchComplianceFrameworks()` |
| 8 | runNow() calls `/run-now` (not `/run`) | VERIFIED | `ScheduledReportsDashboard.tsx` line 149: `await authFetch(\`/api/reports/scheduled/${id}/run-now\`, { method: 'POST' })` |
| 9 | Delivery history panel shows per-card history (toggleHistory, historyLogs) | VERIFIED | `toggleHistory()` function at lines 160–172 fetches `GET /api/reports/scheduled/${id}/history` on open. State variables `historyOpen`, `historyLogs`, `historyLoading` (lines 91–93) drive per-card expandable table with Date/Time, Status, Recipients, Error columns (lines 282–317) |
| 10 | 7/7 backend tests pass | VERIFIED | `backend/venv/bin/python -m pytest backend/tests/test_scheduled_reports.py -q` output: **7 passed** (1 warning — starlette deprecation notice, not a failure) |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/tests/test_scheduled_reports.py` | 7-test suite (min 80 lines) covering all SCHED-01/SCHED-02 changes | VERIFIED | 366 lines, 7 tests, all passing |
| `backend/scheduled_reports_service.py` | framework_id/framework_name fields, `_generate_pdf` wiring, `_write_delivery_log` helper, SMTP validation | VERIFIED | 496 lines (under 500), contains all required symbols |
| `backend/scheduled_reports_endpoints.py` | GET `/{schedule_id}/history` endpoint; create raises 422 on missing SMTP | VERIFIED | 103 lines; history route at line 90; 422 at line 64 |
| `backend/database.py` | `report_delivery_logs` compound index | VERIFIED | `schedule_history_idx` created at lines 299–302 |
| `components/ScheduledReportsDashboard.tsx` | framework picker, runNow URL fix, history panel | VERIFIED | 409 lines (under 500); all three features present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `scheduled_reports_service._deliver_report` | `compliance_reporting_pdf._generate_pdf` | conditional call when `framework_id` set and `report_type in ("compliance_summary", "custom_framework")` | WIRED | Lines 415–417: `pdf_bytes = await _generate_pdf_for_schedule(schedule, tenant_id, framework_id=framework_id)` |
| `run_report_now` / `start_report_scheduler` | `_write_delivery_log` | called in both success and exception paths | WIRED | Success: lines 263, 473; failure: lines 265, 489 |
| `scheduled_reports_endpoints.py` (history route) | `scheduled_reports_service.get_delivery_history` | `GET /api/reports/scheduled/{id}/history` | WIRED | Line 92: `logs = await svc.get_delivery_history(...)` |
| `ScheduledReportsDashboard.tsx` (`runNow`) | `backend/scheduled_reports_endpoints.py` (POST `/{id}/run-now`) | `authFetch(\`/api/reports/scheduled/${id}/run-now\`, ...)` | WIRED | Line 149 matches backend route at endpoints line 97 |
| `ScheduledReportsDashboard.tsx` (History button) | `backend/scheduled_reports_endpoints.py` (GET `/{id}/history`) | `authFetch(\`/api/reports/scheduled/${id}/history\`)` | WIRED | Line 166 matches backend route at endpoints line 90 |
| `ScheduledReportsDashboard.tsx` (create modal framework picker) | `services/apiService.ts` (`fetchComplianceFrameworks`) | import at line 2; called in `useEffect` at line 97 | WIRED | `fetchComplianceFrameworks` at apiService.ts line 540 fetches `/api/compliance` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ScheduledReportsDashboard.tsx` | `frameworks` | `fetchComplianceFrameworks()` → `GET /api/compliance` | Yes — real API call, result stored in `frameworks` state | FLOWING |
| `ScheduledReportsDashboard.tsx` | `historyLogs[id]` | `toggleHistory()` → `authFetch(/api/reports/scheduled/${id}/history)` → `svc.get_delivery_history()` → `db.report_delivery_logs.find()` | Yes — queries MongoDB `report_delivery_logs` collection sorted by `run_at` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 7 backend tests pass (framework_id, PDF wiring, delivery log success, delivery log failure, history endpoint, SMTP 422) | `backend/venv/bin/python -m pytest backend/tests/test_scheduled_reports.py -q` | `7 passed, 1 warning in 1.58s` | PASS |
| Test suite collects exactly 7 named tests | `pytest --collect-only -q` | 7 tests collected across 4 test classes | PASS |

---

### Probe Execution

No `probe-*.sh` files declared or present for this phase. Step skipped.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCHED-01 | 10-01-PLAN.md, 10-02-PLAN.md | Tenant admin configures report schedule per framework; backend generates and emails PDF on each run | SATISFIED | `create_schedule()` persists `framework_id`; `_deliver_report()` calls `_generate_pdf_for_schedule()` for compliance types; frontend framework picker sends `framework_id` in POST; 422 on missing SMTP |
| SCHED-02 | 10-01-PLAN.md, 10-02-PLAN.md | Delivery history (timestamp, framework, recipients, status, error) viewable from Reports page | SATISFIED | `_write_delivery_log()` writes every attempt; `GET /{id}/history` returns logs; frontend `toggleHistory()` fetches and renders history panel |

---

### Anti-Patterns Found

No `TBD`, `FIXME`, or `XXX` markers found in any files modified by this phase. No stub implementations detected. All return values in the delivery pipeline are real: `_generate_pdf_for_schedule` reads actual bytes from disk, `_write_delivery_log` inserts real documents, `get_delivery_history` queries real MongoDB collection.

---

### Human Verification Required

None. All observable truths are programmatically verifiable and confirmed by passing tests or static analysis. No visual-only, real-time, or external-service-only behaviors remain unverified.

---

## Summary

Phase 10 goal is fully achieved. All 10 observable truths are VERIFIED:

- **Backend (Plan 01):** `framework_id`/`framework_name` are stored on schedule creation; PDF delivery routes through `compliance_reporting_pdf._generate_pdf()` (awaited) when a framework is set; every delivery attempt writes a log entry to `report_delivery_logs` with status, error, and recipient fields; `GET /{id}/history` endpoint is wired to `get_delivery_history()`; compound index `schedule_history_idx` is created at startup; schedule creation with `delivery_channel=email` returns 422 when SMTP is unconfigured. 7/7 backend tests pass.

- **Frontend (Plan 02):** `runNow()` calls `/run-now` (404 bug fixed); framework picker renders conditionally for `compliance_summary`/`custom_framework` types using live data from `fetchComplianceFrameworks()`; framework name appears on the schedule card; each card has a `toggleHistory()` button that fetches and renders a history table with date, green/red status badges, recipients, and error text.

---

_Verified: 2026-06-22T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
