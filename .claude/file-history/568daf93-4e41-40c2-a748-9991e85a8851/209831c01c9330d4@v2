---
status: testing
phase: 06-asset-compliance-status-ui-fix
source: [06-VERIFICATION.md]
started: 2026-06-21T00:00:00Z
updated: 2026-06-21T00:00:00Z
---

## Current Test

number: 1
name: Toast error renders when PATCH /compliance/status fails
expected: |
  When the backend is unreachable or returns a non-2xx response,
  clicking "Mark Non-Compliant" (or "Mark Compliant") shows a visible
  toast error: "Failed to update compliance status — please try again"
awaiting: user response

## Tests

### 1. Toast error renders when PATCH /compliance/status fails
expected: |
  Run the app. Navigate to a framework detail view with asset compliance
  controls visible. Stop/block the backend server (or force a 500). Click
  "Mark Non-Compliant" on any control. Confirm a toast error appears:
  "Failed to update compliance status — please try again"
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
