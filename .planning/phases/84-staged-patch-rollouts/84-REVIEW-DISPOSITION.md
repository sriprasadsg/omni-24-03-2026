---
phase: 84
review: 84-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "[backend core] A canary install the gate did not dispatch (suggested, awaiting approval, or recorded refusal) wedges the computer permanently"
  - id: CR-02
    severity: critical
    disposition: open
    title: "[backend core] At the Suggest level (or with unreadable settings) no approval line is ever raised, so the rollout hangs silently"
  - id: CR-03
    severity: critical
    disposition: open
    title: "[agent] A watched service that is not installed on a Linux host reads as `stopped`, which fails the health gate and triggers a revert"
  - id: CR-04
    severity: critical
    disposition: open
    title: "[agent] Linux downgrade (every revert, manual or by job) runs `apt-get install -y` without `--no-remove`, so a revert can remove other packages"
  - id: WR-01
    severity: warning
    disposition: open
    title: "[backend core] A canary install that was not delivered counts against the tenant's circuit breaker"
  - id: WR-02
    severity: warning
    disposition: open
    title: "[backend core] Undelivered or abandoned installs leave a patch job \"In Progress\", so the computer reads busy for every later rollout"
  - id: WR-03
    severity: warning
    disposition: open
    title: "[backend core] Work in flight has no timeout or failure handling, and a running rollout cannot be cancelled"
  - id: WR-04
    severity: warning
    disposition: open
    title: "[backend core] A computer whose approval row was denied, expired or closed is shown as \"installed\""
  - id: WR-05
    severity: warning
    disposition: open
    title: "[backend core] A Reboot or Revert-restart card that expires during a stop halts the rollout and reverts the ring once the stop ends"
  - id: WR-06
    severity: warning
    disposition: open
    title: "[backend core] A row claimed as \"dispatching\" with no instruction is never recovered"
  - id: WR-07
    severity: warning
    disposition: open
    title: "[backend core] Start claims every computer before the rollout document exists"
  - id: WR-08
    severity: warning
    disposition: open
    title: "[backend core] Overlapping maintenance windows make `_reach` end the install window early and mark computers \"not reached\""
  - id: WR-09
    severity: warning
    disposition: open
    title: "[backend routes] The fenced legacy revert turns its own 403 into a 500"
  - id: WR-10
    severity: warning
    disposition: open
    title: "[backend routes] Manual job rollback still reverts a rollout's jobs outside the rollout gate"
  - id: WR-11
    severity: warning
    disposition: open
    title: "[backend routes] Rollout writes lose the platform tier in the audit chain"
  - id: WR-12
    severity: warning
    disposition: open
    title: "[backend routes] Per-tenant settings documents have no unique index, so an upsert race gives duplicates"
  - id: WR-13
    severity: warning
    disposition: open
    title: "[agent] `require_reversible` fails open when the value is not a JSON boolean"
  - id: WR-14
    severity: warning
    disposition: open
    title: "[agent] Job records are written once at the end of the job, and any unreadable shape silently wipes the whole state file"
  - id: WR-15
    severity: warning
    disposition: open
    title: "[agent] A revert re-installs a package that has since been removed"
  - id: WR-16
    severity: warning
    disposition: open
    title: "[agent] `service_state` is not gated by the capability, runs the service manager a second time every minute, and does it synchronously on the heartbeat task"
  - id: WR-17
    severity: warning
    disposition: open
    title: "[agent] The Windows reversibility check reads a metadata flag of an update that is not installed yet"
  - id: WR-18
    severity: warning
    disposition: open
    title: "[agent] The Linux reversibility check is necessary but not sufficient, and dnf/yum read a possibly stale cache"
  - id: WR-19
    severity: warning
    disposition: open
    title: "[frontend] During a stop the Start button is hidden and the viewer is told to \"ask someone with patching access\""
  - id: WR-20
    severity: warning
    disposition: open
    title: "[frontend] Approve overstates the outcome when some computers were refused or the answer is deferred"
  - id: WR-21
    severity: warning
    disposition: open
    title: "[frontend] Resume and Cancel dialogs say \"Try again\" on a permanent 409 or 404 and never refresh the card"
  - id: WR-22
    severity: warning
    disposition: open
    title: "[frontend] Settings time-zone field goes blank after the first window is saved"
  - id: WR-23
    severity: warning
    disposition: open
    title: "[frontend] The one-shot Draft a rollout intent can fire later than intended"
  - id: WR-24
    severity: warning
    disposition: open
    title: "[frontend] Focus-after-start request is never cleared when the new card is not in the first page"
  - id: IN-01
    severity: info
    disposition: open
    title: "[backend core] Non-finite ring numbers raise a plain error instead of a validation sentence"
  - id: IN-02
    severity: info
    disposition: open
    title: "[backend core] `messages.fill` substitutes sequentially, so a value can inject a later placeholder"
  - id: IN-03
    severity: info
    disposition: open
    title: "[backend routes] The mount guard authenticates with JWT only, so the documented and tested API-key read path never runs in production"
  - id: IN-04
    severity: info
    disposition: open
    title: "[backend routes] The time-zone allow-list accepts `localtime` and `Factory`, and a stored zone is not re-validated on use"
  - id: IN-05
    severity: info
    disposition: open
    title: "[backend routes] A `timeZone` sent with a window is silently dropped when the tenant already has a zone"
  - id: IN-06
    severity: info
    disposition: open
    title: "[backend routes] The legacy-fence swallow logs nothing"
  - id: IN-07
    severity: info
    disposition: open
    title: "[backend routes] `ROLLBACK_JOB_TYPE` is documented as shared, but the result route still uses a literal"
  - id: IN-08
    severity: info
    disposition: open
    title: "[backend routes] Unused import"
  - id: IN-09
    severity: info
    disposition: open
    title: "[backend routes] The chat `/maintenance` answer drops the zone and days, and lists paused windows"
  - id: IN-10
    severity: info
    disposition: open
    title: "[backend routes] The rings request body has no per-ring size caps"
  - id: IN-11
    severity: info
    disposition: open
    title: "[agent] `MAX_STATE_NAME` is dead code"
  - id: IN-12
    severity: info
    disposition: open
    title: "[agent] A revert by job leaves the old \"oldest version\" entry in `legacy`"
  - id: IN-13
    severity: info
    disposition: open
    title: "[agent] rpm `installed_version` is not safe for packages with several installed versions"
  - id: IN-14
    severity: info
    disposition: open
    title: "[agent] [user WIP, not Phase 84] per-capability collection intervals starve the rollout's inventory signal"
  - id: IN-15
    severity: info
    disposition: open
    title: "[frontend] Controls that appear without a flag, and a click that does nothing"
  - id: IN-16
    severity: info
    disposition: open
    title: "[frontend] \"Manage in Settings\" in Change Management can never be activated"
  - id: IN-17
    severity: info
    disposition: open
    title: "[frontend] Live-region structure announces too much"
  - id: IN-18
    severity: info
    disposition: open
    title: "[frontend] Start and preflight have no client cap on selected patches, and validation errors read as connection errors"
  - id: IN-19
    severity: info
    disposition: open
    title: "[frontend] Approval card keeps a stale local decision patch across polls"
  - id: IN-20
    severity: info
    disposition: open
    title: "[frontend] Rollouts-tab badge keeps another organization's count when it cannot be read"
  - id: IN-21
    severity: info
    disposition: open
    title: "[frontend] Decisions list: \"Show more\" reorders cards already on screen"
  - id: IN-22
    severity: info
    disposition: open
    title: "[frontend] Coupling to server display strings"
  - id: IN-23
    severity: info
    disposition: open
    title: "[frontend] Minor robustness points"
open: 51
total: 51
recorded: 2026-11-07T01:13:55.165Z
---

# Phase 84: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| CR-02 | critical | open | - |
| CR-03 | critical | open | - |
| CR-04 | critical | open | - |
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
