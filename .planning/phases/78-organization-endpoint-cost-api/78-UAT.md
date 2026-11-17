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

<!-- Recorded 2026-11-17 from the user's "please research and fix it" with all four review findings selected. Sources: 78-REVIEW.md (c16cdf34c, incremental) for WR-04/IN-04/IN-05 and the full-phase review (2a58a89a5) for WR-02. Not observed on the live site; test 1 stays pending. -->
- gap_id: G-78-WR04
  truth: "In the Reports tab the shown result, its title, the export buttons and pagination always belong to the same report: a failed or superseded run, or a builder preview that replaces an in-flight run, never leaves one report's rows on screen under another report's export target"
  status: failed
  reason: "User requested fix of code-review finding WR-04: result is written separately from activeKind/activeKey, so run A succeeds then run B fails leaves A's rows with B's export buttons; a preview that supersedes an in-flight run leaves the abandoned run's key set"
  severity: major
  source: code-review WR-04 (78-REVIEW.md, c16cdf34c)
  artifacts: []
  missing: []
- gap_id: G-78-IN05
  truth: "An export started for one tenant does not download, and does not keep the export buttons disabled, after the Platform Owner switches tenant"
  status: failed
  reason: "User requested fix of code-review finding IN-05: an export started before a tenant switch still completes and downloads the previous tenant's file, and exportingFormat is not reset on the switch"
  severity: minor
  source: code-review IN-05 (78-REVIEW.md, c16cdf34c)
  artifacts: []
  missing: []
- gap_id: G-78-WR02
  truth: "Custom report run, preview and export resolve the tenant the same way as the cost, KPI and pre-built report routes: a Platform Owner gets 400 'Select a tenant' with no tenant and only the selected tenant's data with one; custom report figures never blend tenants"
  status: failed
  reason: "User requested fix of code-review finding WR-02 on 2026-11-17, reversing plan assumption A-78-17 (custom report routes keep today's tenant handling): custom report routes use current_user.tenant_id, so an Owner session blends tenants (incl. the shared Book Value column) while the cost/KPI/pre-built routes return 400"
  severity: major
  source: code-review WR-02 (full-phase review, 2a58a89a5); user decision 2026-11-17
  artifacts: []
  missing: []
- gap_id: G-78-IN04
  truth: "Platform Support and Platform Billing see the same 'Select a tenant' panel (or the no-access panel where they lack the permission) instead of an error toast when no tenant is selected on the ITAM tile and Reports tab"
  status: failed
  reason: "User requested fix of code-review finding IN-04: ITAMConsole needsTenant = isSuperAdminView && !tenantId, so other platform tiers fall through to a toast"
  severity: minor
  source: code-review IN-04 (78-REVIEW.md, c16cdf34c)
  artifacts: []
  missing: []
