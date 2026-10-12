---
phase: 75
review: 75-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Ceiling is not applied to the target account, so a lower admin can take over a higher-privileged user"
  - id: WR-01
    severity: warning
    disposition: open
    title: "Resolver honours `*` and super-admin-only permissions from non-super role documents"
  - id: WR-02
    severity: warning
    disposition: open
    title: "`GET /api/bundles/tenant/{tenant_id}/features` lets any authenticated user read any tenant's entitlements"
  - id: WR-03
    severity: warning
    disposition: open
    title: "PATCH bundle assignment skips the validation PUT performs"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Role-mapping ceiling is write-time only; apply time checks nothing but the super-admin tier"
  - id: WR-05
    severity: warning
    disposition: open
    title: "Session revocation after a role change runs after the write and can fail open"
  - id: WR-06
    severity: warning
    disposition: open
    title: "Role documents are matched by exact spelling, so tenant overrides and the ceiling are spelling-dependent"
  - id: WR-07
    severity: warning
    disposition: open
    title: "Frontend super-admin detection disagrees with the backend and ignores `*`"
  - id: WR-08
    severity: warning
    disposition: open
    title: "D-26 cache hygiene covers only `omni_cache_roles`"
  - id: IN-01
    severity: info
    disposition: open
    title: "`rbac_utils.require_role` and the `Permission` enum are dead and inconsistent"
  - id: IN-02
    severity: info
    disposition: open
    title: "Code placed between import blocks in `authentication_endpoints.py`"
  - id: IN-03
    severity: info
    disposition: open
    title: "`session_permissions` swallows all exceptions and delivers defaults"
  - id: IN-04
    severity: info
    disposition: open
    title: "Archived `reset_db_fresh.py` is still a destructive, runnable script"
  - id: IN-05
    severity: info
    disposition: open
    title: "`can_assign_role` table-only helper has no production caller"
open: 14
total: 14
recorded: 2026-10-12T23:03:37.207Z
---

# Phase 75: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| WR-08 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
