---
phase: 76
review: 76-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "`GET /api/tenants/me` returns the whole tenant document to every signed-in role, bypassing the WR-05 gating and leaking the tenant registration key"
  - id: WR-01
    severity: warning
    disposition: open
    title: "The new self-service exemption rule (PROH-76-08) is lexical and does not catch the case it was written for"
  - id: WR-02
    severity: warning
    disposition: open
    title: "`agent_tolerant()` silently drops `platform_read`"
  - id: IN-01
    severity: info
    disposition: open
    title: "New real-app probes assert only `not in (401, 403)` for the allowed case (inherits old WR-06)"
  - id: IN-02
    severity: info
    disposition: open
    title: "`_listed` has an unused parameter, and `TENANT_CONTROLS_READ_GUARD` restates the `settings` read/write strings"
  - id: IN-03
    severity: info
    disposition: open
    title: "The `agentCapableRoutes` and `exemptRoutes` reasons are prose that nothing verifies"
  - id: WR-03
    severity: warning
    disposition: open
    title: "ITAM guard read rule drops the `manage:assets` read compatibility that the handlers and the scope check keep"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Secrets catalogue is internally incoherent (read needs `manage:settings`, write accepts the read permission)"
  - id: WR-05
    severity: warning
    disposition: open
    title: "`catalogue_exempt` on tenant GET routes lets any tenant role read the hardware allowlist, install-key list, SMTP config and license"
  - id: WR-06
    severity: warning
    disposition: open
    title: "`test_tracer_mdm_enforced_on_real_app` and several slice probes assert only `!= 403` for the allowed case"
  - id: IN-04
    severity: info
    disposition: open
    title: "`viewPermission(view) as Permission` can pass `undefined` into `hasPermission`"
open: 11
total: 11
recorded: 2026-10-18T17:19:38.535Z
---

# Phase 76: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| WR-03 | warning | open | - (not in the current review) |
| WR-04 | warning | open | - (not in the current review) |
| WR-05 | warning | open | - (not in the current review) |
| WR-06 | warning | open | - (not in the current review) |
| IN-04 | info | open | - (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
