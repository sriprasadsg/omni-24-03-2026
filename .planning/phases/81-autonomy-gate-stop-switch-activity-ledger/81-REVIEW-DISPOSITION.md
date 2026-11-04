---
phase: 81
review: 81-REVIEW.md
titles: json
findings:
  - id: WR-10
    severity: warning
    disposition: fixed
    title: "An approval card for a multi-step playbook shows only the first step"
  - id: WR-11
    severity: warning
    disposition: fixed
    title: "A multi-step playbook that fails part-way leaves the earlier steps applied with no put-back and no escalation"
  - id: WR-12
    severity: warning
    disposition: fixed
    title: "The reconciler can complete a ledger row in the middle of a multi-step remediation, and step 2 is then refused"
  - id: WR-13
    severity: warning
    disposition: fixed
    title: "`_escalate` can raise, which skips the breaker evaluation and leaves the request row stuck in \"dispatching\""
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "The tenant never-touch list shows platform-wide stored entries to every tenant viewer (carried forward, unchanged)"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "Approving a remediation card runs the whole dispatch, poll and verify cycle inside the HTTP request (carried forward, unchanged)"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "`monitor_agent_status` can mark an agent that just checked in as Offline (carried forward, unchanged)"
  - id: WR-07
    severity: warning
    disposition: fixed
    title: "The UEBA containment path defeats the gate's own dedupe, so a repeated anomaly opens a new approval card every second (carried forward, unchanged)"
  - id: WR-08
    severity: warning
    disposition: fixed
    title: "Fenced automatic playbook steps lose the old 10-minute duplicate guard, and nothing replaces it once an automatic row finishes (carried forward, unchanged)"
  - id: WR-09
    severity: warning
    disposition: fixed
    title: "The remediation deny route stores an unvalidated, unbounded reason (carried forward, unchanged)"
  - id: IN-01
    severity: info
    disposition: open
    title: "Dead code left behind by the removal of the scheduled cycle (carried forward; still applies)"
  - id: IN-02
    severity: info
    disposition: open
    title: "Mislabelled and fragile reason handling (carried forward; still applies)"
  - id: IN-03
    severity: info
    disposition: open
    title: "Superseded"
  - id: IN-04
    severity: info
    disposition: open
    title: "Core safety tests skip silently when no MongoDB is reachable (carried forward; still applies)"
  - id: IN-05
    severity: info
    disposition: open
    title: "`step_count` treats a legacy row with several `actions` as one step"
  - id: IN-06
    severity: info
    disposition: open
    title: "Tests patch a module attribute that no longer exists"
  - id: IN-07
    severity: info
    disposition: open
    title: "`load_playbooks` truncates silently and relies on database order for overrides"
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Gate evaluates only the first playbook step; later steps and rollback steps run with parameters the gate never checked"
  - id: CR-02
    severity: critical
    disposition: fixed
    title: "Rollback is recorded as \"rolled_back\" (shown to the person as \"Undone.\") without checking that any compensation happened"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "A dispatched instruction that is picked up but never reports leaves its row in \"dispatching\" forever"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Setting the level by hand while the breaker is tripped silently disables the breaker for that tenant"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "The shadow-mode master switch fails open on an unrecognised value, and the remediation path reads it only once at import"
open: 22
total: 22
recorded: 2026-10-26T19:54:59.616Z
---

# Phase 81: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-10 | warning | fixed | 7efd04f32 |
| WR-11 | warning | fixed | 7efd04f32 |
| WR-12 | warning | fixed | 7efd04f32 |
| WR-13 | warning | fixed | 7efd04f32 |
| WR-04 | warning | fixed | 7efd04f32 |
| WR-05 | warning | fixed | 7efd04f32 |
| WR-06 | warning | fixed | 7efd04f32 |
| WR-07 | warning | fixed | 7efd04f32 |
| WR-08 | warning | fixed | 7efd04f32 (not reproducible since 83-06: the fence only suggests; pinned by test_a_repeat_right_after_a_finished_action_is_never_automatic) |
| WR-09 | warning | fixed | 7efd04f32 |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| CR-01 | critical | fixed | resolved in the gap round 81-13..18 (81-REVIEW.md disposition table) (not in the current review) |
| CR-02 | critical | fixed | resolved in the gap round 81-13..18 (81-REVIEW.md disposition table) (not in the current review) |
| WR-01 | warning | fixed | resolved in the gap round 81-13..18 (81-REVIEW.md disposition table) (not in the current review) |
| WR-02 | warning | fixed | resolved in the gap round 81-13..18 (81-REVIEW.md disposition table) (not in the current review) |
| WR-03 | warning | fixed | resolved in the gap round 81-13..18 (81-REVIEW.md disposition table) (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
