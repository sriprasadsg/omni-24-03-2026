---
status: complete
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-09T20:25:00Z
updated: 2026-11-09T20:12:15.846Z
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
  artifacts: []  # Filled by diagnosis
  missing: []    # Filled by diagnosis
