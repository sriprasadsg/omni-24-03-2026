---
phase: 82
review: 82-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "\"adopt\" auto-deletes a tenant or type that the first count pass never reached"
  - id: WR-01
    severity: warning
    disposition: open
    title: "One confirmation covers every waiting row, but only the first 25 are shown, and the reviewer attests to \"every organization listed\""
  - id: WR-02
    severity: warning
    disposition: open
    title: "Certificate rule id is off by one rung for 14d, 7d and 1d"
  - id: WR-03
    severity: warning
    disposition: open
    title: "A single un-renderable event wedges the whole watchdog sync permanently"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Un-gated platform-wide delete paths remain in `retention_service.py`"
  - id: WR-05
    severity: warning
    disposition: open
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
open: 11
total: 11
recorded: 2026-10-30T23:52:31.862Z
---

# Phase 82: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
