---
status: diagnosed
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-09T20:25:00Z
updated: 2026-11-09T20:20:51Z
---

## Current Test

[testing complete]

## Tests

### 1. Install Ollama and pull llama3.2:3b, then run the 85-22 measurement/calibration script on the CPU-only server
expected: Real generation times recorded; call timeouts and the retrieval cut-off hold; DESK-05 real response time is reported
result: pass

### 2. Restart the backend (migration 032) with Ollama absent and open a new first-line portal ticket
expected: Ticket handed to a person (service_desk_offline); no placeholder answer is posted
result: pass

### 3. Portal round trip and Windows tray round trip (UI published, agent 2.1.18 published): requester sees the AI-assisted answer, confirms or says it did not help
expected: Confirm closes the ticket; did-not-help hands off to a person; the reporter never sees staff-only comments or drafts in the browser
result: pass

### 4. Decide on CR-501 / WR-502 before deployment
expected: Either the notice history route (GET /api/notifications/history, backend/reporting_endpoints.py) gets the shared audience filter (recommended, small) and the ticket-staff test is made explicit, or the residual exposure is accepted in writing
result: issue
reported: "Fix both (Recommended) — fix CR-501 and WR-502 before deployment instead of accepting the exposure"
severity: major

## Summary

total: 4
passed: 3
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-85-4
  truth: "GET /api/notifications/history applies the same audience filter as the other notice routes (tenant-admin audience, per-person recipient, excludeRecipients; no tenant-less match for non-super roles), and staff-only ticket text (hidden comments, desk state, AI drafts) is hidden from every viewer without the ticket-staff permission, not only from the reporter"
  status: failed
  reason: "User reported: Fix both (Recommended) — fix CR-501 and WR-502 before deployment instead of accepting the exposure"
  severity: major
  test: 4
  root_cause: "CR-501: GET /api/notifications/history (backend/reporting_endpoints.py:202-221) is a second reader of db.notifications that builds its own query ({tenant_id} or {} for super roles, plus severity) instead of the audience filter _reader_filter, which is private to notification_endpoints.py and used only by its four routes; the structural test inspects only those four functions, so the bypass is untested. Within a tenant every view:dashboard user reads admins-only, other people's per-person and excluded staff notices; Super Admin also reads other tenants' per-person notices; snake tenant_id misses tenantId-only notices. WR-502: the platform has no ticket-staff test at all (no manage:tickets permission, no technician role, _require_ticket_access is view:dashboard); the projection (_shown/_shown_history, projection.for_viewer/history_for_viewer) and the desk guard (service_desk_endpoints._staff_only) are keyed on is_reporter, so every non-reporter view:dashboard user (roles user, viewer included) gets staff-only comments, desk state and AI drafts, lists every tenant ticket, and can send/edit/discard another person's AI draft. Reverses the earlier acceptance D-10/D-11, AR-85-01/-04/-09, T-85-93."
  artifacts:
    - path: "backend/reporting_endpoints.py"
      issue: "get_notification_history has its own query with no audience filter and uses snake tenant_id; file carries user WIP on the /api/reports/* decorators — edit and stage only the history hunk"
    - path: "backend/notification_endpoints.py"
      issue: "_reader_filter/_reader_names (lines 64-90) are private; the one audience filter cannot be reused; ticket_staff audience tag is not enforced"
    - path: "backend/tests/test_service_desk_notification_audience.py"
      issue: "structural test (223-230) covers four functions of one module only"
    - path: "backend/tickets_endpoints.py"
      issue: "every route is view:dashboard; _shown/_shown_history project only for the reporter; list_tickets/get_stats list every tenant ticket for any viewer"
    - path: "backend/service_desk_endpoints.py"
      issue: "_staff_only (82-85) refuses only the reporter; get_service_desk and cited-article reader treat every non-reporter as staff"
    - path: "backend/service_desk/projection.py"
      issue: "for_viewer/history_for_viewer/staff_view have no staff input"
    - path: "backend/rbac_defaults.py, shared/catalogue-access.json, backend/permission_vocabulary.py"
      issue: "no ticket-staff permission exists"
    - path: "backend/tests/service_desk_support.py"
      issue: "test world's reporter, technician and colleague are all role user, so tests treat user as staff"
  missing:
    - "Shared notice audience module (e.g. backend/notification_audience.py) used by notification_endpoints and get_notification_history; history keys on tenantId, 403 for a non-super caller with no tenant"
    - "Repo-wide structural test: every route that reads db.notifications for a user calls the shared filter (allow-list for system writers/jobs)"
    - "History route behaviour tests (view:dashboard user, excluded reporter, tenant admin, Super Admin, tenantId-only notice, severity/limit)"
    - "Explicit ticket-staff permission and one is_ticket_staff(user) helper; default holders and custom-role handling per user decision"
    - "Non-staff non-reporter gets 404 on ticket get/history/service-desk; list_tickets/get_stats restricted at query level to the viewer's own tickets for non-staff"
    - "Draft send/edit/discard and cited-article reader require staff instead of 'not the reporter'; ticket_staff-audience notices hidden from non-staff"
    - "Test world: technician becomes a staff role; non-staff non-reporter cases added; AR-85-01/-04/-09 re-recorded as superseded"
  debug_session: ".planning/debug/85-notice-history-and-ticket-staff-audience.md"
