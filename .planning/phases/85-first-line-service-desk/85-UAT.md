---
status: testing
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-09T23:35:31Z
updated: 2026-11-09T23:35:31Z
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

### 2. Restart the backend (migration 032 and the new manage:tickets role defaults) with Ollama absent and open a new first-line portal ticket
expected: Ticket handed to a person (service_desk_offline); no placeholder answer is posted; a user-role account sees only its own tickets, an analyst sees all
result: [pending]

### 3. Portal round trip and Windows tray round trip (agent 2.1.18 published): requester sees the AI-assisted answer, confirms or says it did not help
expected: Confirm closes the ticket; did-not-help hands off to a person; the reporter never sees staff-only comments or drafts in the browser
result: [pending]

### 4. Sign in as a requester (role user) on the published Tickets screen
expected: Only own tickets listed; staff actions that now answer 403 (assign, merge, bulk, watchers) are either hidden or fail with a clear message (IN-604: no frontend code reads manage:tickets)
result: [pending]

### 5. Decide on WR-603 (requester-set staff fields at ticket creation) and WR-602 (WebSocket push of audience-tagged notices) before deployment
expected: Either the fix (drop staff-only keys for non-staff in create_ticket; skip the tenant broadcast when metadata.audience is set) or a written acceptance
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
