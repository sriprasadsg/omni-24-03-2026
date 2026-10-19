---
phase: 77
review: 77-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "Permission refresh reloads app data with the OLD permissions"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Sync `mfa_required_for` fails closed for every non-admin custom role (WebSocket rejects)"
  - id: WR-03
    severity: warning
    disposition: open
    title: "MFA role cache is never invalidated; the 60s promotion window is per worker, and the helper is dead code"
  - id: WR-04
    severity: warning
    disposition: open
    title: "A role holding any now-unknown or banned permission string can never be edited"
  - id: WR-05
    severity: warning
    disposition: open
    title: "`role_usage` caps the holder and mapping scan at 5000, so a role in use can be deleted"
  - id: WR-06
    severity: warning
    disposition: open
    title: "`resolveHashView` returns inherited `Object.prototype` members for `#constructor` and `#__proto__`"
  - id: WR-07
    severity: warning
    disposition: open
    title: "A Super Admin cannot pick a tenant's custom roles when creating or editing a user"
  - id: IN-01
    severity: info
    disposition: open
    title: "Role names that differ only by repeated whitespace render like a built-in role"
  - id: IN-02
    severity: info
    disposition: open
    title: "No unique index backs the role-name uniqueness rule"
  - id: IN-03
    severity: info
    disposition: open
    title: "`isEditable` is ignored by PUT and DELETE"
  - id: IN-04
    severity: info
    disposition: open
    title: "A role change is committed even if its audit entry cannot be written"
  - id: IN-05
    severity: info
    disposition: open
    title: "Smaller correctness and consistency points"
  - id: IN-06
    severity: info
    disposition: open
    title: "Test coverage relies on source-text matching"
open: 13
total: 13
recorded: 2026-10-19T16:38:34.382Z
---

# Phase 77: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
