---
status: testing
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-09T20:25:00Z
updated: 2026-11-09T20:25:00Z
---

## Current Test

number: 1
name: Install Ollama and pull llama3.2:3b, then run the 85-22 measurement/calibration script on the CPU-only server
expected: |
  Real generation times recorded; call timeouts and the retrieval cut-off hold; DESK-05 real response time is reported
awaiting: user response

## Tests

### 1. Install Ollama and pull llama3.2:3b, then run the 85-22 measurement/calibration script on the CPU-only server
expected: Real generation times recorded; call timeouts and the retrieval cut-off hold; DESK-05 real response time is reported
result: [pending]

### 2. Restart the backend (migration 032) with Ollama absent and open a new first-line portal ticket
expected: Ticket handed to a person (service_desk_offline); no placeholder answer is posted
result: [pending]

### 3. Portal round trip and Windows tray round trip (UI published, agent 2.1.18 published): requester sees the AI-assisted answer, confirms or says it did not help
expected: Confirm closes the ticket; did-not-help hands off to a person; the reporter never sees staff-only comments or drafts in the browser
result: [pending]

### 4. Decide on CR-501 / WR-502 before deployment
expected: Either the notice history route (GET /api/notifications/history, backend/reporting_endpoints.py) gets the shared audience filter (recommended, small) and the ticket-staff test is made explicit, or the residual exposure is accepted in writing
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
