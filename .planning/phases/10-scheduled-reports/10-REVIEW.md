---
phase: 10-scheduled-reports
reviewed: 2026-06-23T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/tests/test_scheduled_reports.py
  - backend/scheduled_reports_service.py
  - backend/scheduled_reports_endpoints.py
  - backend/database.py
  - components/ScheduledReportsDashboard.tsx
findings:
  critical: 4
  warning: 4
  info: 2
  total: 10
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The scheduled-reports feature covers the full stack: a Python service, FastAPI endpoints, a React dashboard, and test coverage. The implementation is structurally sound and the test harness is well-constructed. However, four blockers prevent the feature from working correctly in production and must be fixed before shipping:

1. The background scheduler loop can never find any due schedules because it runs without a tenant context, causing `TenantIsolatedCollection` to inject a dummy tenant filter that matches nothing.
2. The frontend `REPORT_TYPES` list is entirely mismatched with the backend — six of nine values the UI can submit will always be rejected with a 422, including the default selection.
3. HTML email report attachments interpolate unescaped user-controlled strings into the HTML body, creating a stored XSS vector.
4. `send_at_hour` is passed directly to `datetime.replace(hour=...)` before it is validated or cast to int, causing an unhandled `TypeError` (not caught by the `ValueError` handler in the endpoint) when a non-integer value is supplied.

---

## Critical Issues

### CR-01: Background Scheduler Silently Delivers Zero Reports (Tenant Isolation Bypass)

**File:** `backend/scheduled_reports_service.py:468-509`

**Issue:** `start_report_scheduler()` is launched at startup as an `asyncio.create_task()` (confirmed in `app_startup.py:618`) with no tenant context set. `tenant_context.py` uses a `ContextVar`, so the scheduler inherits `tenant_id=None` for its entire lifetime. When the loop calls `db.report_schedules.find({"enabled": True, "next_run": {"$lte": now}})`, `TenantIsolatedCollection._inject_tenant_id()` sees `tenant_id=None` and rewrites the filter to add `"tenantId": "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"`. No schedule document will ever match this filter. The scheduler runs every five minutes, logs no warning, and silently delivers nothing. `run_report_now` (the on-demand path) works because each request first calls `set_tenant_id(tenant_id)`.

**Fix:** Add `set_tenant_id("platform-admin")` inside the scheduler loop before the database query so that `TenantIsolatedCollection` bypasses isolation and returns all tenants' due schedules. The per-schedule `set_tenant_id(sched_tenant_id)` call in `_generate_report` already re-scopes each delivery to the correct tenant.

```python
async def start_report_scheduler():
    logger.info("[Reports] Scheduler loop started")
    while True:
        try:
            await asyncio.sleep(300)
            set_tenant_id("platform-admin")   # allow cross-tenant query
            db = get_database()
            now = datetime.now(timezone.utc).isoformat()
            due_schedules = await db.report_schedules.find(
                {"enabled": True, "next_run": {"$lte": now}}
            ).to_list(length=50)
            # ... rest unchanged
```

---

### CR-02: Frontend Default Report Type Is Rejected by Backend — 6 of 9 Types Are Invalid

**File:** `components/ScheduledReportsDashboard.tsx:53-57` / `backend/scheduled_reports_service.py:26-62`

**Issue:** The frontend `REPORT_TYPES` array and the backend `REPORT_TYPES` dict are completely out of sync. The frontend exposes nine types; six are not present in the backend's validation allowlist and will always be rejected with HTTP 422. The form's default value is `'security_summary'` (line 82), which is one of the invalid six, meaning every first submission without changing the dropdown fails.

Frontend types not in backend (rejected with 422):
- `security_summary` (default)
- `vulnerability_report`
- `compliance_status`
- `incident_report`
- `executive_summary`
- `threat_intelligence`

Backend types not reachable from the UI:
- `security_posture`
- `executive_dashboard`
- `incident_summary`
- `vendor_risk_summary`

**Fix:** Align the frontend dropdown values with the backend's canonical keys. The simplest approach is to drive the frontend list from the `/api/reports/scheduled/types` endpoint that is already implemented. Alternatively, replace the hardcoded array with the backend keys and update the form default:

```tsx
// Replace the hardcoded REPORT_TYPES array with backend-aligned values:
const REPORT_TYPES = [
  'compliance_summary', 'security_posture', 'executive_dashboard',
  'incident_summary', 'agent_health', 'vendor_risk_summary', 'custom_framework',
];

// And update the default form state:
const [form, setForm] = useState({
  // ...
  report_type: 'compliance_summary',  // was 'security_summary'
  // ...
});
```

---

### CR-03: Stored XSS in HTML Report Attachment

**File:** `backend/scheduled_reports_service.py:376-409`

**Issue:** `_build_html()` constructs an HTML document by directly interpolating `report_data` values into an f-string without HTML-escaping. `report_data["report_name"]` originates from `schedule["name"]`, which is user-supplied input stored verbatim at create time. A malicious actor with schedule-creation access can set the name to `<script>alert(document.cookie)</script>`, which will be rendered unescaped in the `<title>` tag (line 391), the `<h1>` tag (line 402), and metadata (line 403). Table cell values at line 384 have the same issue. If the HTML is opened in a browser (as an email attachment or via any preview), the script executes.

```python
# VULNERABLE — line 391:
return f"""...<title>{title}</title>...<h1>{title}</h1>..."""
# If title = '<script>alert(1)</script>' -> script executes in browser
```

**Fix:** HTML-escape all user-controlled values using `html.escape()` before interpolation:

```python
import html as _html

def _build_html(report_data: Dict[str, Any]) -> str:
    title = _html.escape(report_data.get("report_name", "Security Report"))
    generated_at = _html.escape(report_data.get("generated_at", ""))
    period_start = _html.escape(report_data.get("period_start", ""))
    period_end = _html.escape(report_data.get("period_end", ""))
    rows_html = "".join(
        f"<tr><td>{_html.escape(k.replace('_', ' ').title())}</td><td>{_html.escape(str(v))}</td></tr>"
        for k, v in report_data.items() if k not in skip
    )
    # ... rest unchanged
```

---

### CR-04: Unvalidated `send_at_hour` Causes Unhandled TypeError (Server 500)

**File:** `backend/scheduled_reports_service.py:94`

**Issue:** `create_schedule()` calls `_calculate_next_run(frequency, data.get("send_at_hour", 8))` at line 94 before casting `send_at_hour` to `int` (the `int()` cast only happens at line 104 when storing the value). If the caller passes a string like `"8"`, `_calculate_next_run` will call `base.replace(hour="8")` which raises `TypeError: an integer is required`. The endpoint's `except ValueError` handler at line 63 does not catch `TypeError`, so the request returns HTTP 500 instead of 422. Out-of-range values like `25` also pass through both lines and produce an unhandled `ValueError` from `datetime.replace()` at a different call stack level than the endpoint's try/except.

**Fix:** Validate and cast `send_at_hour` before any use, raising `ValueError` on failure so the endpoint's existing handler can catch it:

```python
async def create_schedule(tenant_id: str, created_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing validation ...
    try:
        send_at_hour = int(data.get("send_at_hour", 8))
    except (TypeError, ValueError):
        raise ValueError("send_at_hour must be an integer")
    if not 0 <= send_at_hour <= 23:
        raise ValueError("send_at_hour must be 0-23")

    next_run = _calculate_next_run(frequency, send_at_hour)
    # ...
    schedule = {
        # ...
        "send_at_hour": send_at_hour,  # already cast
        # ...
    }
```

Apply the same guard in `update_schedule()` before calling `_calculate_next_run` at line 236.

---

## Warnings

### WR-01: History "Retry" Button Closes the Panel Instead of Re-Fetching

**File:** `components/ScheduledReportsDashboard.tsx:297`

**Issue:** When history loading fails, the "Retry" button calls `toggleHistory(id)`. At that point `historyOpen[id]` is `true` (the panel is open in error state). `toggleHistory` computes `opening = !historyOpen[id]` which evaluates to `false`, sets the panel to closed, and the `if (opening && ...)` guard prevents any re-fetch. The panel closes silently with no indication of retry being attempted.

**Fix:** Extract the fetch logic into a separate function and call it directly from the retry handler, bypassing `toggleHistory`:

```tsx
async function fetchHistory(id: string) {
  setHistoryLoading(prev => ({ ...prev, [id]: true }));
  setHistoryError(prev => ({ ...prev, [id]: false }));
  try {
    const r = await authFetch(`/api/reports/scheduled/${id}/history`);
    const d = await r.json();
    setHistoryLogs(prev => ({ ...prev, [id]: d.logs || [] }));
  } catch {
    setHistoryError(prev => ({ ...prev, [id]: true }));
  } finally {
    setHistoryLoading(prev => ({ ...prev, [id]: false }));
  }
}

// In toggleHistory, call fetchHistory(id) instead of the inline fetch block.
// In the retry button, call fetchHistory(rep.id) directly.
```

---

### WR-02: `runNow`, `deleteReport`, and `toggleReport` Swallow Errors Silently

**File:** `components/ScheduledReportsDashboard.tsx:140-160`

**Issue:** `toggleReport` and `deleteReport` have no `try/catch` at all. `runNow` has a `try/finally` that does not check `response.ok` and calls `loadReports()` even on a 404 or 500 response. All three provide no user feedback on failure. A failed deletion leaves the item in the list looking like it still exists; a failed toggle appears to succeed (the UI re-fetches the old state). `runNow` doesn't surface SMTP errors to the user.

**Fix:** Add `try/catch` with `showToast` calls for each operation:

```tsx
async function runNow(id: string) {
  setRunning(id);
  try {
    const r = await authFetch(`/api/reports/scheduled/${id}/run-now`, { method: 'POST' });
    if (!r.ok) { const d = await r.json(); showToast(d.detail || 'Run failed', 'error'); return; }
    loadReports();
  } catch { showToast('Network error', 'error'); }
  finally { setRunning(null); }
}
```

---

### WR-03: `schema` Field Inconsistency — Documents Written with `tenant_id` but Filtered with Both `tenant_id` and `tenantId`

**File:** `backend/scheduled_reports_service.py:98,183,204,214,247,258` / `backend/database.py:33,50`

**Issue:** `report_schedules` and `report_delivery_logs` documents are stored with the snake_case field `"tenant_id"` (e.g., line 98 in `scheduled_reports_service.py`). When a service function also passes `{"tenant_id": tenant_id}` as a filter to a `TenantIsolatedCollection`-wrapped collection, the wrapper additionally injects `"tenantId": tenant_id` (camelCase) into the same filter. The `insert_one` wrapper also stamps `"tenantId"` onto each inserted document. Documents therefore carry both fields, and queries filter on both. This redundancy works today but creates a fragile schema where partial migrations or direct DB operations could leave documents that match one field but not the other, causing silent data loss in queries.

**Fix:** Pick one canonical field name (`tenant_id` snake_case to match the existing service layer) and remove the `tenantId` injection from `TenantIsolatedCollection` for these collections, OR store `tenantId` everywhere and update the service queries. The choice should be made project-wide and documented.

---

### WR-04: Email Recipients Are Not Validated — Arbitrary Strings Stored and Sent

**File:** `backend/scheduled_reports_service.py:85-86,108`

**Issue:** The only recipient validation is `if not data.get("recipients")` (line 85), which checks that the list is non-empty. There is no format validation; any arbitrary string is accepted, stored, and passed to `email_service.send_report`. A recipient value like `"; rm -rf /"` or an empty string after splitting is stored as-is. Depending on `email_service` implementation, malformed addresses may cause SMTP errors only at delivery time rather than at schedule creation.

**Fix:** Validate each recipient as a valid email address at create and update time. A simple regex check is sufficient; a library like `email-validator` provides better coverage:

```python
import re
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def _validate_recipients(recipients: list) -> None:
    for r in recipients:
        if not isinstance(r, str) or not _EMAIL_RE.match(r):
            raise ValueError(f"Invalid email recipient: {r!r}")
```

---

## Info

### IN-01: `_generate_pdf_for_schedule` Leaves a File-Not-Found Error Unaddled with No User Context

**File:** `backend/scheduled_reports_service.py:157-169`

**Issue:** If `compliance_reporting_pdf._generate_pdf` returns a filename that does not exist on disk (e.g., the PDF generation itself failed and returned a non-existent path), `open(filepath, "rb")` raises `FileNotFoundError`. The `finally` block attempts `os.remove(filepath)` (which will also fail and be swallowed), and then the `FileNotFoundError` propagates to `run_report_now`'s outer try/except, which logs it as a delivery failure with only the generic exception message. The log entry gives no indication that the PDF file was missing rather than that email delivery failed, making diagnosis harder.

**Fix:** Check for file existence before opening and raise a more descriptive error:

```python
if not os.path.exists(filepath):
    raise FileNotFoundError(f"PDF generation did not produce expected file: {filepath}")
```

---

### IN-02: `confirm()` Used for Delete Confirmation

**File:** `components/ScheduledReportsDashboard.tsx:158`

**Issue:** `window.confirm()` is used for delete confirmation. Browser `confirm()` dialogs are blocked in some embedded contexts, cannot be styled, and are inaccessible to screen readers. All other confirmation UX in modern React uses in-line modal patterns.

**Fix:** Replace `confirm()` with an inline confirmation step within the card — e.g., showing a "Are you sure? [Yes] [No]" inline prompt on first click, consistent with the rest of the UI's modal approach already used for the "Schedule New Report" form.

---

_Reviewed: 2026-06-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
