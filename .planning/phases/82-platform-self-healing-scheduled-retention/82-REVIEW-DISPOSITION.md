---
phase: 82
review: 82-REVIEW.md
titles: json
findings:
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "A tenant admin's \"Run Cleanup Now\" re-stamps `countedAt` and so invalidates the Super Admin's review token on demand"
  - id: IN-06
    severity: info
    disposition: open
    title: "`gate_state` parameter shadows the module function `tenant_created_at`"
  - id: IN-07
    severity: info
    disposition: open
    title: "Adoption now rests on a mutable `createdAt`, and the demo seed script rewrites it for existing tenants"
  - id: IN-08
    severity: info
    disposition: open
    title: "The \"run document without `finishedAt`\" branch of `run_in_progress` can never match"
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "\"adopt\" auto-deletes a tenant or type that the first count pass never reached"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "One confirmation covers every waiting row, but only the first 25 are shown, and the reviewer attests to \"every organization listed\""
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Certificate rule id is off by one rung for 14d, 7d and 1d"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "A single un-renderable event wedges the whole watchdog sync permanently"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Un-gated platform-wide delete paths remain in `retention_service.py`"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "\"Run Cleanup Now\" reports \"Cleanup completed\" for 409, 403 and 400 answers"
  - id: IN-01
    severity: info
    disposition: open
    title: "Outbox pages are trigger-only, so each Autonomous Ops notice leaves an open on-call incident"
  - id: IN-02
    severity: info
    disposition: open
    title: "`testAlert.error` and the Activity `error` params are not URL-scrubbed, unlike the channel status path"
  - id: IN-03
    severity: info
    disposition: open
    title: "Loopback test compares literal strings"
  - id: IN-04
    severity: info
    disposition: open
    title: "INSTALL.md section 12 names a control that does not exist there"
  - id: IN-05
    severity: info
    disposition: open
    title: "Service state from the snapshot is not validated server-side"
open: 9
total: 15
recorded: 2026-10-31T10:22:43.312Z
---

# Phase 82: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-06 | warning | fixed | 79191ef5e (a manual run keeps a usable stored count, plus a rate limit; deliberately not the review's fix, reasons in the commit) |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| CR-01 | critical | fixed | 82-15 afd90e532, 0a4de3acd, 642624ac4, confirmed by the gap-round review |
| WR-01 | warning | fixed | 82-17 c157feb10, confirmed by the gap-round review |
| WR-02 | warning | fixed | 82-16 14d343740, confirmed by the gap-round review |
| WR-03 | warning | fixed | 82-16 ab2907a7c, cbdb97708, confirmed by the gap-round review |
| WR-04 | warning | open | - (not in the current review) |
| WR-05 | warning | fixed | 82-17 57705c85a, confirmed by the gap-round review |
| IN-01 | info | open | - (not in the current review) |
| IN-02 | info | open | - (not in the current review) |
| IN-03 | info | open | - (not in the current review) |
| IN-04 | info | open | - (not in the current review) |
| IN-05 | info | open | - (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
