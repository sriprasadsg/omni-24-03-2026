---
phase: 81
review: 81-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Gate evaluates only the first playbook step; later steps and rollback steps run with parameters the gate never checked"
  - id: CR-02
    severity: critical
    disposition: open
    title: "Rollback is recorded as \"rolled_back\" (shown to the person as \"Undone.\") without checking that any compensation happened"
  - id: WR-01
    severity: warning
    disposition: open
    title: "A dispatched instruction that is picked up but never reports leaves its row in \"dispatching\" forever"
  - id: WR-02
    severity: warning
    disposition: open
    title: "Setting the level by hand while the breaker is tripped silently disables the breaker for that tenant"
  - id: WR-03
    severity: warning
    disposition: open
    title: "The shadow-mode master switch fails open on an unrecognised value, and the remediation path reads it only once at import"
  - id: WR-04
    severity: warning
    disposition: open
    title: "The tenant never-touch list shows platform-wide stored entries to every tenant viewer"
  - id: WR-05
    severity: warning
    disposition: open
    title: "Approving a remediation card runs the whole dispatch, poll and verify cycle inside the HTTP request"
  - id: WR-06
    severity: warning
    disposition: open
    title: "`monitor_agent_status` can mark an agent that just checked in as Offline"
  - id: WR-07
    severity: warning
    disposition: open
    title: "The UEBA containment path defeats the gate's own dedupe, so a repeated anomaly opens a new approval card every second"
  - id: WR-08
    severity: warning
    disposition: open
    title: "Fenced automatic playbook steps lose the old 10-minute duplicate guard, and nothing replaces it once an automatic row finishes"
  - id: WR-09
    severity: warning
    disposition: open
    title: "The remediation deny route stores an unvalidated, unbounded reason"
  - id: IN-01
    severity: info
    disposition: open
    title: "Dead code left behind by the removal of the scheduled cycle"
  - id: IN-02
    severity: info
    disposition: open
    title: "Mislabelled and fragile reason handling"
  - id: IN-03
    severity: info
    disposition: open
    title: "`_step_class` accepts \"approve\" style classification by inspection of the first action only, leaving unreachable states in the trace"
  - id: IN-04
    severity: info
    disposition: open
    title: "Core safety tests skip silently when no MongoDB is reachable"
open: 15
total: 15
recorded: 2026-10-26T14:09:19.247Z
---

# Phase 81: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| CR-02 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| WR-08 | warning | open | - |
| WR-09 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
