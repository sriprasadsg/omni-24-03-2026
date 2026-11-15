---
phase: 86
review: 86-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Export DLP scan fails open on large exports, non-ASCII content and tenants with many policies"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Export allowance and bulk-export detection are bypassed by API keys"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "`PageSizeCapMiddleware` raises ValueError (500) on a crafted page-size value, before authentication"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "`regex` is not a declared dependency, so the admin-pattern timeout silently disappears"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "The test-organization exemption is documented as refusing customer organizations, but any ticked organization can be marked"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "A marked test organization that is no longer ticked can neither be cleared in the UI nor replaced"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "Digest \"ran\" and \"undone\" groups key on `finishedAt`, which is rewritten by later transitions"
  - id: IN-01
    severity: info
    disposition: fixed
    title: "Digest is recorded as \"sent\" even when both the notice and every email failed"
  - id: IN-02
    severity: info
    disposition: fixed
    title: "Confirm-name comparison trims the typed value but not the stored name"
  - id: IN-03
    severity: info
    disposition: fixed
    title: "Empty exports (204) are counted as exports by the export middleware"
  - id: IN-04
    severity: info
    disposition: fixed
    title: "`email_utils.send_email_async` guard is dead and a bad header raises instead of returning False"
  - id: IN-05
    severity: info
    disposition: fixed
    title: "The in-app digest reaches `manage:agents` holders regardless of `view:autonomous_ops`"
  - id: WR-07
    severity: warning
    disposition: fixed
    title: "The off-screen Action / Refused / simulation columns have no visual scroll cue"
  - id: IN-06
    severity: info
    disposition: fixed
    title: "The region wrapper is an unconditional tab stop and a duplicate-named landmark, even when nothing overflows"
  - id: IN-07
    severity: info
    disposition: fixed
    title: "Measured pixel widths are written into JSDoc and will go stale"
open: 0
total: 15
recorded: 2026-11-14T11:43:50.673Z
---

# Phase 86: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | fixed | ee1de03ca (branch 86-review-fixes, 2026-11-15) |
| WR-01 | warning | fixed | 9b7582624 (branch 86-review-fixes, 2026-11-15) |
| WR-02 | warning | fixed | fa79383ba (branch 86-review-fixes, 2026-11-15) |
| WR-03 | warning | fixed | 0f3ec2dbf (branch 86-review-fixes, 2026-11-15) |
| WR-04 | warning | fixed | def48b5e7 (branch 86-review-fixes, 2026-11-15) |
| WR-05 | warning | fixed | e395fc1c3 (branch 86-review-fixes, 2026-11-15) |
| WR-06 | warning | fixed | d7bfec611 (branch 86-review-fixes, 2026-11-15) |
| IN-01 | info | fixed | e78489c58 (branch 86-review-fixes, 2026-11-15) |
| IN-02 | info | fixed | 9c9ae8262 (branch 86-review-fixes, 2026-11-15) |
| IN-03 | info | fixed | 9c9ae8262 (branch 86-review-fixes, 2026-11-15) |
| IN-04 | info | fixed | 94674a142 (branch 86-review-fixes, 2026-11-15) |
| IN-05 | info | fixed | e78489c58 (branch 86-review-fixes, 2026-11-15) |
| WR-07 | warning | fixed | 76f79528d (branch 86-review-fixes, 2026-11-15) |
| IN-06 | info | fixed | 76f79528d (branch 86-review-fixes, 2026-11-15) |
| IN-07 | info | fixed | 1a505c34b (branch 86-review-fixes, 2026-11-15) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
