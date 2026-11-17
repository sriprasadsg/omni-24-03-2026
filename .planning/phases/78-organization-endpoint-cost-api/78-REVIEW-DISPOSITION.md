---
phase: 78
review: 78-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "ReportsPanel `runPrebuilt` has no stale-response guard; the tenant-switch reset does not clear `running` (confirms the 78-UI-REVIEW lead)"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Custom report routes are not tenant-resolved, so an Owner gets cross-tenant book values while the cost surfaces return 400"
  - id: WR-03
    severity: warning
    disposition: open
    title: "The cost detail route does not return \"the list row\"; its duplicate markers differ when the partner asset is disposed or retired"
  - id: IN-01
    severity: info
    disposition: open
    title: "A fabricated `X-Tenant-ID` from an Owner is accepted and used for writes"
  - id: IN-02
    severity: info
    disposition: open
    title: "Asset value report population filter does not normalize `lifecycleStatus` the way `compute_asset_cost` does"
  - id: IN-03
    severity: info
    disposition: open
    title: "A salvage value above the purchase cost produces a book value above the purchase cost"
  - id: IN-04
    severity: info
    disposition: open
    title: "The Run button gate depends only on `isSuperAdminRoleName`; other platform tiers fall through to a toast"
open: 7
total: 7
recorded: 2026-11-17T01:12:05.058Z
---

# Phase 78: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
