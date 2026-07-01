# Phase 10: Scheduled Compliance Reports — Research

**Researched:** 2026-06-22
**Domain:** Scheduled report delivery, delivery history, per-framework compliance PDF generation
**Confidence:** HIGH — all findings are based on direct codebase inspection

---

## Summary

Most of the Phase 10 infrastructure already exists in the codebase. The backend has a
complete scheduling service (`scheduled_reports_service.py`) with CRUD operations, a
background asyncio loop that fires every 5 minutes, and a running `send_report` path via
`email_service.py`. The frontend has a `ScheduledReportsDashboard` component that is
already lazy-loaded in `App.tsx`.

**What is missing or incomplete** for the phase requirements:

1. **Per-framework scoping (SCHED-01 gap):** The existing `report_type` field is a generic
   category string (e.g., `"compliance_summary"`). There is no `framework_id` field in the
   schedule data model. The phase requires the tenant to target a *specific* compliance
   framework (e.g., SOC 2, ISO 27001). The existing `compliance_reporting_pdf._generate_pdf()`
   function already takes `framework_id` explicitly, but the scheduler service has its own
   `_build_pdf()` that does not call it.

2. **Delivery history (SCHED-02 gap):** The current service only updates `last_run`,
   `last_error`, and `run_count` on the schedule document itself. There is no separate
   `report_delivery_logs` collection and no endpoint to retrieve a per-schedule delivery
   history. The frontend `ScheduledReportsDashboard` shows `last_run` and `last_error` on
   the card, but there is no delivery history table.

3. **Run-now URL mismatch:** The frontend calls `POST /api/reports/scheduled/{id}/run` but
   the backend registers the route as `/{schedule_id}/run-now`. One of these must be fixed
   so the "Run Now" button works.

4. **PDF attachment uses wrong generator:** `_deliver_report()` in the service calls the
   service-local `_build_pdf()` (a generic reportlab table). For compliance schedules the
   correct generator is `compliance_reporting_pdf._generate_pdf()`, which produces the
   full framework-scoped PDF with asset summary and control details. Wiring this in requires
   the schedule document to carry a `framework_id`.

**Primary recommendation:** Add `framework_id` to the schedule schema, wire the scheduler
to call `_generate_pdf()` when `report_type == "compliance_summary"` and `framework_id` is
set, write delivery log records on each run, expose a delivery history endpoint, and extend
the frontend to show the history table and a framework picker in the create form.

---

## Scheduling Infrastructure

**What exists:** [VERIFIED: direct file inspection]

- `backend/scheduled_reports_service.py` (406 lines) — complete async service with
  `create_schedule`, `list_schedules`, `update_schedule`, `delete_schedule`,
  `run_report_now`, `_generate_report`, `_deliver_report`, `_build_pdf`, `_build_html`,
  and `start_report_scheduler`.

- `start_report_scheduler()` is a plain `asyncio` while-loop that sleeps 300 s between
  polls. It queries `db.report_schedules` for documents where `enabled=True` and
  `next_run <= now`, then calls `_generate_report` + `_deliver_report` per document.

- The loop is started in `backend/app_startup.py` line 587 via
  `asyncio.create_task(start_report_scheduler())`, consistent with how the XDR scanner
  and MITRE heatmap refresher are started.

- Celery is configured (`celery_app.py`) and has a beat schedule for a daily patch scan,
  but the report scheduler does **not** use Celery — it uses the same asyncio pattern as
  all other background workers in this codebase.

**Conclusion:** No new scheduler technology is needed. Phase 10 adds records to the
existing `report_schedules` collection and extends the `start_report_scheduler` loop logic.

**Supported frequencies:** `daily`, `weekly`, `monthly`, `quarterly`.
The phase requires daily/weekly/monthly — all already supported.

---

## Email Infrastructure

**What exists:** [VERIFIED: direct file inspection]

- `backend/email_service.py` (475 lines) — a synchronous `smtplib`-based `EmailService`
  class, loaded as a module-level singleton `email_service`. SMTP I/O is run in a thread
  pool via `asyncio.to_thread(_send_sync)` so it does not block the event loop.

- `email_service.send_report(recipient, report_name, report_data, attachments=None)` is an
  `async` method that:
  1. Reads SMTP config from `db.smtp_config.find_one({})` (no tenant filter — uses
     the first document in the collection, which is the platform SMTP config).
  2. Builds plain-text + HTML bodies from `report_data`.
  3. Accepts optional `attachments` (list of `{"filename": str, "data": bytes}`).
  4. Calls `self.send_email(smtp_config, ...)`.

- This method is already called by `scheduled_reports_service._deliver_report()` when
  `delivery_channel == "email"`.

- SMTP config is stored in `db.smtp_config` (MongoDB collection). It is configured
  through the existing EmailSettings UI (`components/EmailSettings.tsx`).

**Gaps for Phase 10:**

- `send_report()` does a bare `db.smtp_config.find_one({})` — no tenant scoping. This
  is consistent with how `siem_engine.py` does it (it passes `tenant_id` but `send_report`
  does not). For Phase 10 this is acceptable: SMTP is a platform-level setting.

- No `aiosmtplib`, no SendGrid, no Mailgun — just stdlib `smtplib`. No additional
  packages are needed.

**Conclusion:** Email infrastructure is complete. No new packages required.

---

## Existing Report Generation

**`_generate_pdf()` in `compliance_reporting_pdf.py`:** [VERIFIED: direct file inspection]

```python
async def _generate_pdf(framework_id: str, reports_dir: str, tenant_id: str = None) -> dict:
```

- Fully async.
- Takes `framework_id` and `tenant_id` as explicit arguments — no HTTP request context
  dependency whatsoever.
- Calls `_build_report_data(framework_id, tenant_id)` from `compliance_reporting_data.py`,
  which queries MongoDB directly.
- Writes the PDF to disk at `reports_dir/<filename>` using `reportlab`.
- Returns `{"filename": ..., "url": ..., "generatedAt": ..., "rowCount": ...}`.

**Can it be called from a background job?** Yes, unconditionally. The function only needs
`framework_id`, `reports_dir`, and `tenant_id`. The scheduler already has all three.

**`_build_pdf()` in `scheduled_reports_service.py`:** This is a separate, simpler
reportlab function that renders a generic key-value table. It returns `bytes` (not a file
path). It does not know about frameworks or controls.

**Resolution for Phase 10:** When `framework_id` is set on a schedule, the scheduler's
`_deliver_report` path should call `_generate_pdf(framework_id, reports_dir, tenant_id)`
to get the authoritative PDF, then attach the resulting file bytes. When `framework_id` is
absent (non-compliance report types), the existing `_build_pdf()` can remain as the
fallback.

**`_build_report_data()` in `compliance_reporting_data.py`:** Queries
`db.compliance_frameworks`, `db.asset_compliance`, `db.compliance_evidence`. Requires the
framework document to exist in MongoDB. If the framework has no data the PDF will show
empty tables — this is acceptable behavior, not an error.

---

## Data Model

### Existing: `report_schedules` collection

Current schema (from `create_schedule`):

```
id, tenant_id, created_by, name, report_type, report_type_name,
frequency, send_at_hour, day_of_week, day_of_month,
delivery_channel, recipients, webhook_url, slack_webhook, teams_webhook,
include_charts, format, filters, enabled,
created_at, updated_at, last_run, next_run, run_count, last_error
```

**Fields to add for Phase 10:**

| Field | Type | Purpose |
|-------|------|---------|
| `framework_id` | `str \| None` | Target framework for compliance PDF generation |
| `framework_name` | `str \| None` | Denormalised display name (avoids extra lookups in list view) |

These are additive — existing documents without `framework_id` continue to work.

### New: `report_delivery_logs` collection (SCHED-02)

One document per delivery attempt:

```json
{
  "id":           "uuid4",
  "schedule_id":  "ref to report_schedules.id",
  "tenant_id":    "string",
  "framework_id": "string | null",
  "run_at":       "ISO-8601 UTC",
  "recipients":   ["email@example.com"],
  "status":       "success | failure",
  "error":        "string | null",
  "format":       "pdf | html | json",
  "filename":     "string | null"
}
```

**Index needed:** `{schedule_id: 1, run_at: -1}` for efficient history queries.

**Collection name:** `report_delivery_logs` (follows the `_logs` suffix pattern used
elsewhere in the codebase for audit trails).

---

## Frontend Patterns

**Existing component:** `components/ScheduledReportsDashboard.tsx` (312 lines)

- Already lazy-loaded and routed at `case 'scheduledReports'` in `App.tsx`.
- Fetches `GET /api/reports/scheduled` and renders schedule cards.
- Has a create modal (name, report_type, frequency, delivery_channel, recipients,
  webhook_url fields).
- Has Run Now / Delete actions per card.
- Missing: framework picker in the create modal; delivery history view.

**ReportingDashboard.tsx** (601 lines) — the main Reporting & Analytics page. Imports from
`apiService.ts` and renders SLA/vuln/change tabs plus a Data Export Center. The
`FrameworkExportCard` inside it shows how framework selection + format buttons work — this
is the direct pattern to replicate for the schedule create form's framework picker.

**API calls pattern (from ScheduledReportsDashboard.tsx):**

```typescript
// List schedules
GET /api/reports/scheduled          → { schedules: [...], total: N }

// Create
POST /api/reports/scheduled         body: { name, report_type, frequency, delivery_channel, recipients, framework_id? }

// Toggle enable/disable
PUT  /api/reports/scheduled/{id}    body: { enabled: bool }

// Run now (BUG: frontend calls /run, backend serves /run-now — must align)
POST /api/reports/scheduled/{id}/run-now

// Delete
DELETE /api/reports/scheduled/{id}
```

**New endpoints needed for SCHED-02:**

```
GET /api/reports/scheduled/{id}/history   → { logs: [...], total: N }
```

**Where to add delivery history UI:** Add a "History" button to each schedule card in
`ScheduledReportsDashboard.tsx` that opens an inline expandable panel (or a modal) showing
the `report_delivery_logs` rows for that schedule. This keeps everything in one component
and avoids creating a new file. If the component grows past 500 lines after the addition,
split out a `ScheduleHistoryPanel.tsx`.

**Framework picker pattern:** A `<select>` populated from `GET /api/compliance/frameworks`
(already called in `FrameworkExportCard` via `fetchComplianceFrameworks()`). Show only
when `report_type === "compliance_summary"` or `"custom_framework"` (same gating logic as
the existing PDF button in `FrameworkExportCard`).

---

## File Size Inventory

| File | Lines | Role in Phase 10 | Action |
|------|-------|-----------------|--------|
| `backend/scheduled_reports_service.py` | 406 | Core scheduler — add `framework_id` field, delivery log writes, call `_generate_pdf` | Edit — will grow; keep under 500 |
| `backend/scheduled_reports_endpoints.py` | 96 | REST API — add `/history` endpoint, fix `/run-now` route | Edit |
| `backend/compliance_reports_endpoints.py` | 161 | Existing PDF/CSV endpoints — no changes needed | Read-only reference |
| `backend/compliance_reporting_pdf.py` | 151 | `_generate_pdf()` — called from scheduler; no changes needed | Read-only reference |
| `backend/email_service.py` | 475 | `send_report()` — no changes needed | Read-only reference |
| `backend/settings_endpoints.py` | 328 | Settings pattern reference only | Read-only reference |
| `components/ScheduledReportsDashboard.tsx` | 312 | Main UI — add framework picker, history view, fix run-now URL | Edit — may need split if > 500 |
| `components/ReportingDashboard.tsx` | 601 | Already over 500 lines — do NOT add to this file | Read-only reference |

**Split trigger:** If `ScheduledReportsDashboard.tsx` exceeds 500 lines after Phase 10
additions, extract `ScheduleHistoryPanel.tsx` (the history table) as a separate component.

---

## Recommended Wave Structure

### Wave 1: Backend — schema extension + delivery history (TDD)

**Tests first (`backend/tests/test_scheduled_reports.py`):**
- `test_create_schedule_with_framework_id` — POST creates doc with `framework_id`
- `test_list_schedules_returns_framework_id` — GET includes `framework_id`
- `test_run_now_writes_delivery_log_success` — delivery log document written on success
- `test_run_now_writes_delivery_log_failure` — delivery log written on SMTP failure
- `test_delivery_history_endpoint` — GET `/history` returns logs for schedule

**Implementation:**
1. Add `framework_id` and `framework_name` fields to `create_schedule()` in
   `scheduled_reports_service.py`.
2. Update `_generate_report()` to pass `framework_id` through; update `_deliver_report()`
   to call `compliance_reporting_pdf._generate_pdf()` when `framework_id` is set.
3. Add `_write_delivery_log()` helper that inserts to `report_delivery_logs`.
4. Call `_write_delivery_log()` after each delivery attempt (success and failure) in both
   `run_report_now()` and the background `start_report_scheduler()` loop.
5. Add `GET /{schedule_id}/history` endpoint in `scheduled_reports_endpoints.py`.
6. Fix the `/run-now` vs `/run` URL mismatch — change frontend to use `/run-now` (backend
   is the authoritative contract).

### Wave 2: Frontend — framework picker + delivery history UI

**Implementation:**
1. In `ScheduledReportsDashboard.tsx`, fetch compliance frameworks on mount
   (`GET /api/compliance/frameworks`) and store in state.
2. Add `framework_id` + `framework_name` fields to the `ScheduledReport` TypeScript
   interface.
3. In the create modal, add a `<select>` for framework (visible when
   `report_type === "compliance_summary"`).
4. Fix `runNow()` to call `/run-now` (not `/run`).
5. Add a "History" toggle per card; on expand, fetch `GET /api/reports/scheduled/{id}/history`
   and render a compact table: run timestamp, status (green/red badge), recipient(s), error.
6. Display `framework_name` on the schedule card when present.

---

## Open Questions

1. **SMTP not configured = silent failure or surfaced error?**
   Currently `send_report()` returns `{"success": False, "message": "SMTP not configured"}`
   if `db.smtp_config` is empty. The delivery log will capture this as a failure, but the
   tenant sees no real-time error. The planner should decide whether to show a warning
   banner on `ScheduledReportsDashboard` if SMTP is unconfigured.

2. **`reports_dir` for background job PDF writes:**
   `_generate_pdf()` needs a `reports_dir` path. The `compliance_reports_endpoints.py`
   uses `_REPORTS_DIR = "static/reports"`. The scheduler needs to use the same directory.
   This should be imported as a constant — not hardcoded twice.

3. **Tenant-scoped SMTP:**
   `email_service.send_report()` does `db.smtp_config.find_one({})` with no tenant filter.
   For multi-tenant deployments where different tenants have different SMTP configs, this
   will always use the first document. Accepted as a known limitation for this phase
   (platform-level SMTP only).

4. **Frequency "quarterly" in scope?**
   The phase requirements list daily/weekly/monthly. The existing backend supports quarterly.
   The frontend create form lists all four. Recommend keeping quarterly in the backend but
   not adding it to the primary UI flow unless explicitly requested.

5. **`fetchComplianceFrameworks` in apiService.ts:**
   The existing function is imported in `ReportingDashboard.tsx`. Confirm it returns
   `{ id, name }` objects that can be used to populate the framework picker. If it returns
   a different shape, the component needs a local adapter.

---

## Pitfalls

### 1. `/run` vs `/run-now` URL mismatch is a live bug
The frontend `ScheduledReportsDashboard.tsx:119` calls
`/api/reports/scheduled/${id}/run`. The backend registers
`@router.post("/{schedule_id}/run-now")`. The "Run Now" button is currently broken.
Fix: change the frontend to call `/run-now` (not the backend, because the backend URL
is more conventional REST). Do not add a second route that aliases one to the other —
that creates silent divergence.

### 2. Using the wrong PDF generator
`scheduled_reports_service._build_pdf()` generates a generic summary table.
`compliance_reporting_pdf._generate_pdf()` generates the full controls+evidence PDF.
For compliance schedules, the wrong one is wired. Wiring the correct one requires
`framework_id` to be present on the schedule document. Gate the call:
```python
if schedule.get("framework_id") and report_type in ("compliance_summary", "custom_framework"):
    result = await _generate_pdf(schedule["framework_id"], _REPORTS_DIR, tenant_id)
    pdf_bytes = open(os.path.join(_REPORTS_DIR, result["filename"]), "rb").read()
```
Avoid leaving the old `_build_pdf()` call as a silent fallback for compliance types —
recipients would receive a nearly-empty report.

### 3. `_generate_pdf()` writes to disk; background job must clean up or the disk fills
`_generate_pdf()` writes a file to `static/reports/`. The existing
`/api/compliance/reports` endpoint lists these files. For background-generated PDFs, the
planner should decide whether to add the filename to `db.compliance_reports` (so it
appears in the download list) or keep it ephemeral (attach and delete). Attaching and
deleting is simpler — avoids polluting the reports list with automated outputs. But
if the tenant wants to re-download, it must remain on disk. Recommend: write to
`db.report_delivery_logs.filename`, keep the file, do not insert into
`db.compliance_reports`.

### 4. Delivery log without index = full-collection scan on history query
`db.report_delivery_logs.find({"schedule_id": ...})` without an index degrades as
log volume grows. Wave 1 must include:
```python
await db.report_delivery_logs.create_index([("schedule_id", 1), ("run_at", -1)])
```
Place this in startup or in a migration step (consistent with how other collections
in this codebase add indexes).

### 5. `scheduled_reports_service.py` is already at 406 lines
Adding delivery log writes, `_write_delivery_log()`, and the `framework_id` generation
path will push it close to the 500-line CLAUDE.md limit. If it exceeds 500 lines, split
out the delivery logging into `report_delivery_log_service.py`.

### 6. `email_service.send_report()` is sync-inside-async via `self.send_email()`
`send_report()` is `async` but calls `self.send_email()` which itself is `async`
(uses `asyncio.to_thread`). This chain is correct. However, `send_report()` calls
`self.send_email()` with `return self.send_email(...)` — it is missing `await`. Confirm
at implementation time that the call is `return await self.send_email(...)`. If `await`
is missing, the scheduler receives a coroutine object, not a dict, and the delivery
silently fails without raising.

---

## Sources

All findings are [VERIFIED: direct file inspection] against the codebase at
`/home/user/enterprise-omni-agent-ai-platform`. No external lookups were required —
the relevant infrastructure is entirely implemented in existing files.

| File inspected | Finding |
|----------------|---------|
| `backend/scheduled_reports_service.py` | Scheduler loop, CRUD, `_build_pdf`, `_deliver_report` |
| `backend/scheduled_reports_endpoints.py` | REST routes, `/run-now` route name, `auth_utils` import |
| `backend/compliance_reporting_pdf.py` | `_generate_pdf(framework_id, reports_dir, tenant_id)` signature |
| `backend/email_service.py` | `send_report()`, `smtp_config` DB lookup, `asyncio.to_thread` pattern |
| `backend/app_startup.py` | `create_task(start_report_scheduler())` — scheduler start |
| `backend/celery_app.py` | Celery present but not used for report scheduling |
| `backend/app_background_tasks.py` | asyncio loop pattern used by all background workers |
| `backend/settings_endpoints.py` | Settings CRUD pattern (tenant-scoped upsert) |
| `components/ScheduledReportsDashboard.tsx` | Frontend state, form fields, API calls, `/run` URL bug |
| `components/ReportingDashboard.tsx` | `FrameworkExportCard` pattern for framework picker |
| `services/apiService.ts` | `fetchComplianceFrameworks` presence, `fetchComplianceScore` |
| `backend/router_registry.py` | `scheduled_reports_endpoints` registered at line 257 |
