---
phase: "10-scheduled-reports"
plan: "02"
subsystem: "frontend"
status: complete
tags: [frontend, scheduled-reports, react, typescript, compliance]
dependency_graph:
  requires:
    - 10-01
  provides:
    - "ScheduledReportsDashboard.tsx: framework picker, run-now URL fix, history panel"
  affects:
    - "components/ScheduledReportsDashboard.tsx"
tech_stack:
  added: []
  patterns:
    - "Record<string, T> for per-card toggle/log state"
    - "Conditional framework select picker driven by report_type"
    - "Collapsible inline history panel with lazy fetch"
key_files:
  created: []
  modified:
    - "components/ScheduledReportsDashboard.tsx"
decisions:
  - "Inline approach (no split to ScheduleHistoryPanel.tsx): post-Task-1 line count was 342; adding history (~67 lines) landed at 409, well under 500"
  - "DeliveryLog interface defined inline in ScheduledReportsDashboard.tsx (not in types.ts) — local to this component"
  - "compliance_summary and custom_framework added to REPORT_TYPES constant so they appear in the dropdown"
  - "historyLogs keyed by schedule id to avoid re-fetching on every toggle — cache cleared only by page reload"
  - "History button toggles between 'History' and 'Hide' text based on historyOpen[rep.id]"
metrics:
  duration: "~4m"
  completed: "2026-06-22"
  tasks: 2
  files_modified: 1
---

# Phase 10 Plan 02: Scheduled Reports Frontend Summary

**One-liner:** Fixed runNow 404 bug (/run → /run-now), wired framework picker for compliance/custom report types, and added per-card delivery history panel fetching GET /history with green/red status badges.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix runNow URL + add framework picker | c53d615 | components/ScheduledReportsDashboard.tsx |
| 2 | Add delivery history panel per card | efe7ffa | components/ScheduledReportsDashboard.tsx |

## What Was Built

### Task 1: runNow URL Fix + Framework Picker

- **Bug fixed:** `runNow()` was calling `POST /api/reports/scheduled/${id}/run` (returns 404). Changed to `/run-now` matching the backend route registered in Plan 01.
- **ScheduledReport interface:** Added `framework_id?: string | null` and `framework_name?: string | null` fields.
- **Imports:** Added `fetchComplianceFrameworks` from apiService and `ComplianceFramework` type from types.
- **State:** Added `frameworks: ComplianceFramework[]` state, loaded on mount alongside `loadReports()`.
- **Form state:** Added `framework_id: ''` to initial and reset form state.
- **POST body:** When `form.framework_id` is non-empty, `framework_id` and `framework_name` (resolved from frameworks list) are included in the POST body.
- **Modal UI:** Framework select dropdown appears conditionally when `form.report_type === 'compliance_summary'` or `'custom_framework'`. First option is a disabled placeholder "Select framework...".
- **Card display:** `{rep.framework_name && <p className="text-xs text-gray-500 mt-0.5">{rep.framework_name}</p>}` shown below report_type line.
- **REPORT_TYPES constant:** Added `'compliance_summary'` and `'custom_framework'` so they appear in the Report Type dropdown.

### Task 2: Per-Card Delivery History Panel

- **DeliveryLog interface:** `{ id, run_at, status: 'success'|'failure', recipients, error: string|null, format, filename }` defined inline.
- **State:** `historyOpen: Record<string, boolean>`, `historyLogs: Record<string, DeliveryLog[]>`, `historyLoading: Record<string, boolean>` — all keyed by schedule id.
- **toggleHistory(id):** Async function. On open, if logs not yet cached, fetches `GET /api/reports/scheduled/${id}/history`, stores result in `historyLogs[id]`. Subsequent toggles reuse cached data.
- **History button:** Added to action row between Run Now and Delete. Text shows 'History' when closed, 'Hide' when open.
- **Panel rendering:**
  - Loading state: "Loading..." text
  - Empty state: "No delivery history yet"
  - Table with columns: Date/Time, Status, Recipients, Error
  - Status badge: `text-green-400` "Success" or `text-red-400` "Failed"
  - Error column: truncated to 60 chars with `title` tooltip for full text; "—" when null
- **Inline approach:** ScheduledReportsDashboard.tsx lands at 409 lines (under 500). No ScheduleHistoryPanel.tsx split required.

## Deviations from Plan

None — plan executed exactly as written. Inline approach was confirmed correct (342 lines after Task 1 < 380 threshold).

## Threat Surface Scan

No new network endpoints or auth paths introduced. The `fetchComplianceFrameworks` call reuses the existing `/api/compliance` endpoint also used by ReportingDashboard. The `/api/reports/scheduled/${id}/history` call uses the same `authFetch` JWT attachment as all other API calls in this component. No new threat surface identified beyond what the plan's threat model covers.

## Known Stubs

None. Framework picker uses live data from `fetchComplianceFrameworks()`. History panel fetches live delivery logs from the backend endpoint added in Plan 01.

## Self-Check: PASSED

- FOUND: components/ScheduledReportsDashboard.tsx (409 lines)
- FOUND: .planning/phases/10-scheduled-reports/10-02-SUMMARY.md
- FOUND: commit c53d615 (Task 1)
- FOUND: commit efe7ffa (Task 2)
- TypeScript: no errors in changed files (npx tsc --noEmit)
