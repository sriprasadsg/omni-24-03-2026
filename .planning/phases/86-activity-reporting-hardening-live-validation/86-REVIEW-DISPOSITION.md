---
phase: 86
review: 86-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Export DLP scan fails open on large exports, non-ASCII content and tenants with many policies"
  - id: WR-01
    severity: warning
    disposition: open
    title: "Export allowance and bulk-export detection are bypassed by API keys"
  - id: WR-02
    severity: warning
    disposition: open
    title: "`PageSizeCapMiddleware` raises ValueError (500) on a crafted page-size value, before authentication"
  - id: WR-03
    severity: warning
    disposition: open
    title: "`regex` is not a declared dependency, so the admin-pattern timeout silently disappears"
  - id: WR-04
    severity: warning
    disposition: open
    title: "The test-organization exemption is documented as refusing customer organizations, but any ticked organization can be marked"
  - id: WR-05
    severity: warning
    disposition: open
    title: "A marked test organization that is no longer ticked can neither be cleared in the UI nor replaced"
  - id: WR-06
    severity: warning
    disposition: open
    title: "Digest \"ran\" and \"undone\" groups key on `finishedAt`, which is rewritten by later transitions"
  - id: IN-01
    severity: info
    disposition: open
    title: "Digest is recorded as \"sent\" even when both the notice and every email failed"
  - id: IN-02
    severity: info
    disposition: open
    title: "Confirm-name comparison trims the typed value but not the stored name"
  - id: IN-03
    severity: info
    disposition: open
    title: "Empty exports (204) are counted as exports by the export middleware"
  - id: IN-04
    severity: info
    disposition: open
    title: "`email_utils.send_email_async` guard is dead and a bad header raises instead of returning False"
  - id: IN-05
    severity: info
    disposition: open
    title: "The in-app digest reaches `manage:agents` holders regardless of `view:autonomous_ops`"
  - id: WR-07
    severity: warning
    disposition: open
    title: "The off-screen Action / Refused / simulation columns have no visual scroll cue"
  - id: IN-06
    severity: info
    disposition: open
    title: "The region wrapper is an unconditional tab stop and a duplicate-named landmark, even when nothing overflows"
  - id: IN-07
    severity: info
    disposition: open
    title: "Measured pixel widths are written into JSDoc and will go stale"
open: 15
total: 15
recorded: 2026-11-14T11:43:50.673Z
---

# Phase 86: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| WR-07 | warning | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
