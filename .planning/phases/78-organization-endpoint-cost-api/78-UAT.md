---
status: testing
phase: 78-organization-endpoint-cost-api
source: [78-VERIFICATION.md]
started: 2026-11-17T05:32:00Z
updated: 2026-11-17T05:32:00Z
---

## Current Test

number: 1
name: After the user deploys (backend restart + UI publish), a Platform Owner opens ITAM with a tenant selected, then with none selected.
expected: |
  KPI tile shows 'Not tracked' for a tenant with no cost data and a dollar value otherwise, 'Valued X of Y', the Select-a-tenant state when no tenant is chosen, and the Reports tab Run buttons are disabled with the note until a tenant is selected; switching tenants mid-run leaves no previous-tenant table.
awaiting: user response

## Tests

### 1. After the user deploys (backend restart + UI publish), a Platform Owner opens ITAM with a tenant selected, then with none selected.
expected: KPI tile shows 'Not tracked' for a tenant with no cost data and a dollar value otherwise, 'Valued X of Y', the Select-a-tenant state when no tenant is chosen, and the Reports tab Run buttons are disabled with the note until a tenant is selected; switching tenants mid-run leaves no previous-tenant table.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
