---
phase: 10-scheduled-reports
fixed_at: 2026-06-23T00:00:00Z
review_path: .planning/phases/10-scheduled-reports/10-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 7
skipped: 1
status: partial
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-06-23T00:00:00Z
**Source review:** .planning/phases/10-scheduled-reports/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (4 Critical, 4 Warning)
- Fixed: 7
- Skipped: 1

## Fixed Issues

### CR-01: Background Scheduler Silently Delivers Zero Reports (Tenant Isolation Bypass)

**Files modified:** `backend/scheduled_reports_service.py`
**Commit:** 392894f
**Applied fix:** Added `set_tenant_id("platform-admin")` at the top of the scheduler loop body, before the database query, so `TenantIsolatedCollection` bypasses the per-tenant filter when querying for due schedules across all tenants. The per-schedule `set_tenant_id(sched_tenant_id)` call in `_generate_report` still re-scopes each delivery to the correct tenant.

---

### CR-04: Unvalidated `send_at_hour` Causes Unhandled TypeError (Server 500)

**Files modified:** `backend/scheduled_reports_service.py`
**Commit:** 5526cfd
**Applied fix:** In `create_schedule`, added a `try/except (TypeError, ValueError)` block to cast `send_at_hour` to `int` early (before `_calculate_next_run`), raising a descriptive `ValueError` on failure. Added a `0 <= send_at_hour <= 23` range check. The schedule document now stores the already-cast value. Applied the same guard inside `update_schedule` when `frequency` is being updated (which triggers a `_calculate_next_run` call).

---

### CR-03: Stored XSS in HTML Report Attachment

**Files modified:** `backend/scheduled_reports_service.py`
**Commit:** be293f0
**Applied fix:** Added `import html as _html` at the top of the module. In `_build_html`, wrapped all user-controlled values (`report_name`, `generated_at`, `period_start`, `period_end`, and all table key/value pairs) with `_html.escape()` before interpolation into the f-string. Keys are escaped after the `replace`/`title` transforms; values are escaped after `str()` conversion.

---

### CR-02: Frontend Default Report Type Is Rejected by Backend — 6 of 9 Types Are Invalid

**Files modified:** `components/ScheduledReportsDashboard.tsx`
**Commit:** 45382ec
**Applied fix:** Replaced the hardcoded `REPORT_TYPES` array with the seven backend-canonical keys: `compliance_summary`, `security_posture`, `executive_dashboard`, `incident_summary`, `agent_health`, `vendor_risk_summary`, `custom_framework`. Updated the `form` initial state default from `'security_summary'` to `'compliance_summary'`, and updated the post-create reset to the same value.

---

### WR-01: History "Retry" Button Closes the Panel Instead of Re-Fetching

**Files modified:** `components/ScheduledReportsDashboard.tsx`
**Commit:** 7527040
**Applied fix:** Extracted the history fetch logic into a dedicated `fetchHistory(id)` function that clears the error state and re-fetches unconditionally. `toggleHistory` now calls `fetchHistory(id)` instead of the inline block. The Retry button now calls `fetchHistory(rep.id)` directly, bypassing the toggle logic entirely.

---

### WR-02: `runNow`, `deleteReport`, and `toggleReport` Swallow Errors Silently

**Files modified:** `components/ScheduledReportsDashboard.tsx`
**Commit:** d172411
**Applied fix:** Added `try/catch` blocks to all three functions. Each now checks `response.ok` and calls `showToast(d.detail || '<action> failed', 'error')` on non-OK responses. Network/fetch failures are caught and surfaced via `showToast('Network error', 'error')`. `loadReports()` is only called on success paths.

---

### WR-04: Email Recipients Are Not Validated — Arbitrary Strings Stored and Sent

**Files modified:** `backend/scheduled_reports_service.py`
**Commit:** 8e14646
**Applied fix:** Added `import re` and a module-level `_EMAIL_RE` regex pattern (`^[^\s@]+@[^\s@]+\.[^\s@]+$`). Added `_validate_recipients(recipients)` helper that raises `ValueError` for any non-string or non-matching entry. Called in `create_schedule` immediately after the non-empty check, and in `update_schedule` before the update dict is assembled.

---

## Skipped Issues

### WR-03: Dual `tenant_id`/`tenantId` Field Schema Fragility

**File:** `backend/scheduled_reports_service.py`, `backend/database.py`
**Reason:** skipped: requires project-wide design decision — cannot be fixed safely with a local code change. The reviewer correctly identifies redundancy but the fix requires choosing a canonical field name and updating `TenantIsolatedCollection` in `database.py`, all service layers, existing documents, and any indexes. A partial fix risks introducing silent data loss for in-flight queries. This should be addressed as a dedicated migration task.
**Original issue:** Documents are stored with `tenant_id` (snake_case) by the service layer but `TenantIsolatedCollection` additionally stamps `tenantId` (camelCase) on insert and injects both into filters, creating a dual-field schema that is fragile under partial migrations or direct DB operations.

---

_Fixed: 2026-06-23T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
