---
phase: 83
review: 83-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "[agent] No child-process timeout while process-wide locks are held: one hung firewall command stops the isolation revert, every block expiry and the agent loop"
  - id: CR-02
    severity: critical
    disposition: open
    title: "[agent] The agent's \"never block a non-public network\" guard only tests the CIDR's base address, so `172.0.0.0/8` or `192.0.0.0/8` passes and drops the LAN"
  - id: WR-01
    severity: warning
    disposition: open
    title: "[backend core] A persisted origin never goes stale, so one fresh signal can pair with an old one"
  - id: WR-02
    severity: warning
    disposition: open
    title: "[backend core] A file signal keeps the alphabetically first path, not the newest (A-83-ONE-PATH)"
  - id: WR-03
    severity: warning
    disposition: open
    title: "[backend core] An over-budget restart card stays approvable after the service has recovered (question 4)"
  - id: WR-04
    severity: warning
    disposition: open
    title: "[backend core] Restart budget (3) equals breaker threshold (3), so one dead watched service lowers the whole tenant to Suggest"
  - id: WR-05
    severity: warning
    disposition: open
    title: "[backend core] `_agreeing` includes origins that are not within 24 hours of the agreeing pair, so the recorded \"why\" can name the wrong sources"
  - id: WR-06
    severity: warning
    disposition: open
    title: "[backend core] Approving a card while the host is briefly offline burns the single-use decision"
  - id: WR-07
    severity: warning
    disposition: open
    title: "[backend core] One failing sweep stage skips every later stage for that tenant, including restarts and the isolation revert bookkeeping"
  - id: WR-08
    severity: warning
    disposition: open
    title: "[backend routes] The shipped `quarantine_file` playbook can never produce a working quarantine from the legacy remediation path"
  - id: WR-09
    severity: warning
    disposition: open
    title: "[backend routes] The feed upsert can match a tenant's own IOC row instead of the global row"
  - id: WR-10
    severity: warning
    disposition: open
    title: "[backend routes] The result route stores agent free text unbounded and crashes on a non-string status"
  - id: WR-11
    severity: warning
    disposition: open
    title: "[backend routes] A SOAR run with a fenced step still reports `status: completed`"
  - id: WR-12
    severity: warning
    disposition: open
    title: "[backend routes] A failed migration 028 is swallowed, and the sweep starts without the indexes it relies on"
  - id: WR-13
    severity: warning
    disposition: open
    title: "[agent] Protected-path and own-file checks compare text, confirmed bypasses on Linux and Windows (question 1)"
  - id: WR-14
    severity: warning
    disposition: open
    title: "[agent] Legacy `kill_process` path: PID kills skip the critical-process list, name kills hit every match, and a missing `expected_exe` silently selects it (question 2)"
  - id: WR-15
    severity: warning
    disposition: open
    title: "[agent] The `expected_exe` kill with no quarantine kills every process running the same image, listed or not"
  - id: WR-16
    severity: warning
    disposition: open
    title: "[agent] A second `isolate_host` while isolated answers `already_applied` / `verify.ok = true` without checking the rules or the id"
  - id: WR-17
    severity: warning
    disposition: open
    title: "[agent] `restore_host` with no record answers `not_found` / `network_restored ok` without looking at the firewall"
  - id: WR-18
    severity: warning
    disposition: open
    title: "[agent] A damaged or newer-version state file is a dead end: blocks never expire, cannot be unblocked, and nothing quarantines or restores"
  - id: WR-19
    severity: warning
    disposition: open
    title: "[agent] `Cmd::passes` turns every failure into \"not present\": a failed check can drop a live claim, or add a duplicate rule"
  - id: WR-20
    severity: warning
    disposition: open
    title: "[agent] Isolation \"verify\" is not an isolation test; on Windows only the default policy changes"
  - id: WR-21
    severity: warning
    disposition: open
    title: "[agent] `restart_service` checks the characters and the critical list only: unit type and the tenant's watched list are not enforced on the agent"
  - id: WR-22
    severity: warning
    disposition: open
    title: "[agent] Large quarantines hold the state lock and the agent loop; isolate/restart final result is ordered by a 2-second sleep and is never retried"
  - id: WR-23
    severity: warning
    disposition: open
    title: "[frontend] Activity list silently ignores Refresh, a decision and the stale-row reload once \"Load more\" was used"
  - id: WR-24
    severity: warning
    disposition: open
    title: "[frontend] A failing background read leaves stale cards with live Approve buttons and says nothing"
  - id: WR-25
    severity: warning
    disposition: open
    title: "[frontend] A decided line keeps its \"what happens\" sentence, which can contradict the result"
  - id: WR-26
    severity: warning
    disposition: open
    title: "[frontend] A decision that fails for any reason other than \"expired\" or \"already made\" does not re-read the card"
  - id: WR-27
    severity: warning
    disposition: open
    title: "[frontend] Approve, Deny and Confirm are disabled or hidden using the browser's clock"
  - id: WR-28
    severity: warning
    disposition: open
    title: "[frontend] The settings form discards edits made while saving, and a full-list save can overwrite another administrator's services"
  - id: WR-29
    severity: warning
    disposition: open
    title: "[frontend] Undo reports \"Couldn't undo\" after the undo was sent, when the answer carries no row"
  - id: WR-30
    severity: warning
    disposition: open
    title: "[frontend] A held card is a snapshot from the first decision, so lines resolved elsewhere still show Approve and Deny"
  - id: IN-01
    severity: info
    disposition: open
    title: "[backend core] Question 1 holds today, but the gate does not stop a future caller (`remediate()` and automatic `quarantine_file`)"
  - id: IN-02
    severity: info
    disposition: open
    title: "[backend core] Question 3 holds; the safety of `allow_protected` rests on three call sites"
  - id: IN-03
    severity: info
    disposition: open
    title: "[backend core] Question 5 holds; tenant isolation of the Phase 83 queries"
  - id: IN-04
    severity: info
    disposition: open
    title: "[backend core] `delivery.py` docstring claims the unstamped-command refusal covers response tasks; it does not"
  - id: IN-05
    severity: info
    disposition: open
    title: "[backend core] `protected_paths.kind_of` treats \"Darwin\" as Windows"
  - id: IN-06
    severity: info
    disposition: open
    title: "[backend core] Small correctness and clarity notes"
  - id: IN-07
    severity: info
    disposition: open
    title: "[backend core] Critical services are excluded only when the watched list is saved"
  - id: IN-08
    severity: info
    disposition: open
    title: "[backend routes] The swarm containment fence is a one-value denylist on `type`, while the agent acts on `instruction`"
  - id: IN-09
    severity: info
    disposition: open
    title: "[backend routes] The \"accepted never overwrites a final status\" guard uses upper-case names, but the capability hold-back writes lower-case `refused`"
  - id: IN-10
    severity: info
    disposition: open
    title: "[backend routes] `validate_intervals` has no caller (uncommitted hunk)"
  - id: IN-11
    severity: info
    disposition: open
    title: "[backend routes] Smaller robustness points in the new response routes and the swarm plan"
  - id: IN-12
    severity: info
    disposition: open
    title: "[backend routes] `playbook_engine_actions` fence reads `executed_by` as a free string"
  - id: IN-13
    severity: info
    disposition: open
    title: "[agent] Isolation revert uses the wall clock only; a backward step lengthens the isolation (question 3)"
  - id: IN-14
    severity: info
    disposition: open
    title: "[agent] A cross-volume quarantine can delete a file that changed after the copy was verified"
  - id: IN-15
    severity: info
    disposition: open
    title: "[agent] Process listing failure reports a kill as done"
  - id: IN-16
    severity: info
    disposition: open
    title: "[agent] gzip fallback sends every heartbeat twice when the platform rejects the payload for another reason (uncommitted hunk)"
  - id: IN-17
    severity: info
    disposition: open
    title: "[agent] Collection intervals: skipped collectors send nothing and last-run state is per process (uncommitted hunks)"
  - id: IN-18
    severity: info
    disposition: open
    title: "[agent] Other notes"
  - id: IN-19
    severity: info
    disposition: open
    title: "[frontend] Swarm antibody form: Enter bypasses the in-flight guard, and the error text can be wrong or crash the page"
  - id: IN-20
    severity: info
    disposition: open
    title: "[frontend] The decision result text is rebuilt in the browser, and the server's refreshed row is thrown away"
  - id: IN-21
    severity: info
    disposition: open
    title: "[frontend] `actionCount` is typed but never read, so a card with more than 50 lines hides the rest without saying so"
  - id: IN-22
    severity: info
    disposition: open
    title: "[frontend] Bulk apply does not check the shape of its answer, and the distribution summary leaves out unreadable organizations"
  - id: IN-23
    severity: info
    disposition: open
    title: "[frontend] Smaller race and robustness points"
open: 55
total: 55
recorded: 2026-11-02T11:53:11.579Z
---

# Phase 83: Code Review Disposition

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
| WR-10 | warning | open | - |
| WR-11 | warning | open | - |
| WR-12 | warning | open | - |
| WR-13 | warning | open | - |
| WR-14 | warning | open | - |
| WR-15 | warning | open | - |
| WR-16 | warning | open | - |
| WR-17 | warning | open | - |
| WR-18 | warning | open | - |
| WR-19 | warning | open | - |
| WR-20 | warning | open | - |
| WR-21 | warning | open | - |
| WR-22 | warning | open | - |
| WR-23 | warning | open | - |
| WR-24 | warning | open | - |
| WR-25 | warning | open | - |
| WR-26 | warning | open | - |
| WR-27 | warning | open | - |
| WR-28 | warning | open | - |
| WR-29 | warning | open | - |
| WR-30 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| IN-09 | info | open | - |
| IN-10 | info | open | - |
| IN-11 | info | open | - |
| IN-12 | info | open | - |
| IN-13 | info | open | - |
| IN-14 | info | open | - |
| IN-15 | info | open | - |
| IN-16 | info | open | - |
| IN-17 | info | open | - |
| IN-18 | info | open | - |
| IN-19 | info | open | - |
| IN-20 | info | open | - |
| IN-21 | info | open | - |
| IN-22 | info | open | - |
| IN-23 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
