---
status: partial
phase: 06-asset-compliance-status-ui-fix
source: [06-VERIFICATION.md]
started: 2026-06-21T00:00:00Z
updated: 2026-06-21T16:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Toast error renders when PATCH /compliance/status fails
expected: |
  Run the app. Navigate to a framework detail view with asset compliance
  controls visible. Stop/block the backend server (or force a 500). Click
  "Mark Non-Compliant" on any control. Confirm a toast error appears:
  "Failed to update compliance status — please try again"
result: skipped

## Summary

total: 1
passed: 0
issues: 0
pending: 0
skipped: 1
blocked: 0

## Gaps
