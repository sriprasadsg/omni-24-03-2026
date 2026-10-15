---
phase: 76
review: 76-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "Agent-capable routes in enforced catalogues give any signed-in user a catalogue-free path"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Webhook guard bypass is keyed on a role string any custom role can carry"
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
  - id: IN-01
    severity: info
    disposition: open
    title: "Write lists carry read-grade `view:` strings, so the guard is a no-op for writes in those catalogues"
  - id: IN-02
    severity: info
    disposition: open
    title: "Unused imports in new modules"
  - id: IN-03
    severity: info
    disposition: open
    title: "Duplicate guard definitions drift silently"
  - id: IN-04
    severity: info
    disposition: open
    title: "`viewPermission(view) as Permission` can pass `undefined` into `hasPermission`"
open: 10
total: 10
recorded: 2026-10-15T21:03:45.669Z
---

# Phase 76: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
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

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
