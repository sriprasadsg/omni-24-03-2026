---
phase: 84
review: 84-REVIEW.md
titles: json
findings:
  - id: WR-25
    severity: warning
    disposition: open
    title: "A revert still re-installs a removed package that left its config behind (reopens WR-15)"
  - id: WR-26
    severity: warning
    disposition: fixed
    title: "An expired `sent` instruction is judged \"not delivered\" although the agent already fetched it"
  - id: WR-27
    severity: warning
    disposition: fixed
    title: "A queued revert that was never fetched is declared \"did not answer\" after 6 hours and the instruction is left live"
  - id: WR-28
    severity: warning
    disposition: fixed
    title: "A revert the agent answered FAILURE is reported as \"the computer did not answer\""
  - id: WR-29
    severity: warning
    disposition: fixed
    title: "Cancel closes unfetched instructions with the \"a check after the install did not pass\" text"
  - id: WR-30
    severity: warning
    disposition: fixed
    title: "A rollout whose Cancel is settling shows no sign of it"
  - id: WR-31
    severity: warning
    disposition: fixed
    title: "A controller pass that loaded the rollout before the Cancel stamp can still decide and send"
  - id: WR-32
    severity: warning
    disposition: open
    title: "The 409 for a manual rollback tells the user to \"Revert it from Rollouts\", which only works for a halted rollout"
  - id: IN-24
    severity: info
    disposition: open
    title: "`masked` and `not-found` units both read `absent`, including a running masked unit"
  - id: IN-25
    severity: info
    disposition: open
    title: "A watched name that is in neither baseline list keeps the services signal at \"no data\" for good"
  - id: IN-26
    severity: info
    disposition: open
    title: "`save_to` leaves a stale temporary file on failure and does not sync the directory"
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "[backend core] A canary install the gate did not dispatch (suggested, awaiting approval, or recorded refusal) wedges the computer permanently"
  - id: CR-02
    severity: critical
    disposition: fixed
    title: "[backend core] At the Suggest level (or with unreadable settings) no approval line is ever raised, so the rollout hangs silently"
  - id: CR-03
    severity: critical
    disposition: fixed
    title: "[agent] A watched service that is not installed on a Linux host reads as `stopped`, which fails the health gate and triggers a revert"
  - id: CR-04
    severity: critical
    disposition: fixed
    title: "[agent] Linux downgrade (every revert, manual or by job) runs `apt-get install -y` without `--no-remove`, so a revert can remove other packages"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "[backend core] A canary install that was not delivered counts against the tenant's circuit breaker"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "[backend core] Undelivered or abandoned installs leave a patch job \"In Progress\", so the computer reads busy for every later rollout"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "[backend core] Work in flight has no timeout or failure handling, and a running rollout cannot be cancelled"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "[backend core] A computer whose approval row was denied, expired or closed is shown as \"installed\""
  - id: WR-05
    severity: warning
    disposition: deferred
    title: "[backend core] A Reboot or Revert-restart card that expires during a stop halts the rollout and reverts the ring once the stop ends"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "[backend core] A row claimed as \"dispatching\" with no instruction is never recovered"
  - id: WR-07
    severity: warning
    disposition: deferred
    title: "[backend core] Start claims every computer before the rollout document exists"
  - id: WR-08
    severity: warning
    disposition: deferred
    title: "[backend core] Overlapping maintenance windows make `_reach` end the install window early and mark computers \"not reached\""
  - id: WR-09
    severity: warning
    disposition: deferred
    title: "[backend routes] The fenced legacy revert turns its own 403 into a 500"
  - id: WR-10
    severity: warning
    disposition: fixed
    title: "[backend routes] Manual job rollback still reverts a rollout's jobs outside the rollout gate"
  - id: WR-11
    severity: warning
    disposition: deferred
    title: "[backend routes] Rollout writes lose the platform tier in the audit chain"
  - id: WR-12
    severity: warning
    disposition: deferred
    title: "[backend routes] Per-tenant settings documents have no unique index, so an upsert race gives duplicates"
  - id: WR-13
    severity: warning
    disposition: fixed
    title: "[agent] `require_reversible` fails open when the value is not a JSON boolean"
  - id: WR-14
    severity: warning
    disposition: fixed
    title: "[agent] Job records are written once at the end of the job, and any unreadable shape silently wipes the whole state file"
  - id: WR-15
    severity: warning
    disposition: fixed
    title: "[agent] A revert re-installs a package that has since been removed"
  - id: WR-16
    severity: warning
    disposition: deferred
    title: "[agent] `service_state` is not gated by the capability, runs the service manager a second time every minute, and does it synchronously on the heartbeat task"
  - id: WR-17
    severity: warning
    disposition: deferred
    title: "[agent] The Windows reversibility check reads a metadata flag of an update that is not installed yet"
  - id: WR-18
    severity: warning
    disposition: deferred
    title: "[agent] The Linux reversibility check is necessary but not sufficient, and dnf/yum read a possibly stale cache"
  - id: WR-19
    severity: warning
    disposition: deferred
    title: "[frontend] During a stop the Start button is hidden and the viewer is told to \"ask someone with patching access\""
  - id: WR-20
    severity: warning
    disposition: deferred
    title: "[frontend] Approve overstates the outcome when some computers were refused or the answer is deferred"
  - id: WR-21
    severity: warning
    disposition: deferred
    title: "[frontend] Resume and Cancel dialogs say \"Try again\" on a permanent 409 or 404 and never refresh the card"
  - id: WR-22
    severity: warning
    disposition: deferred
    title: "[frontend] Settings time-zone field goes blank after the first window is saved"
  - id: WR-23
    severity: warning
    disposition: deferred
    title: "[frontend] The one-shot Draft a rollout intent can fire later than intended"
  - id: WR-24
    severity: warning
    disposition: deferred
    title: "[frontend] Focus-after-start request is never cleared when the new card is not in the first page"
  - id: IN-01
    severity: info
    disposition: deferred
    title: "[backend core] Non-finite ring numbers raise a plain error instead of a validation sentence"
  - id: IN-02
    severity: info
    disposition: deferred
    title: "[backend core] `messages.fill` substitutes sequentially, so a value can inject a later placeholder"
  - id: IN-03
    severity: info
    disposition: deferred
    title: "[backend routes] The mount guard authenticates with JWT only, so the documented and tested API-key read path never runs in production"
  - id: IN-04
    severity: info
    disposition: deferred
    title: "[backend routes] The time-zone allow-list accepts `localtime` and `Factory`, and a stored zone is not re-validated on use"
  - id: IN-05
    severity: info
    disposition: deferred
    title: "[backend routes] A `timeZone` sent with a window is silently dropped when the tenant already has a zone"
  - id: IN-06
    severity: info
    disposition: deferred
    title: "[backend routes] The legacy-fence swallow logs nothing"
  - id: IN-07
    severity: info
    disposition: deferred
    title: "[backend routes] `ROLLBACK_JOB_TYPE` is documented as shared, but the result route still uses a literal"
  - id: IN-08
    severity: info
    disposition: deferred
    title: "[backend routes] Unused import"
  - id: IN-09
    severity: info
    disposition: deferred
    title: "[backend routes] The chat `/maintenance` answer drops the zone and days, and lists paused windows"
  - id: IN-10
    severity: info
    disposition: deferred
    title: "[backend routes] The rings request body has no per-ring size caps"
  - id: IN-11
    severity: info
    disposition: deferred
    title: "[agent] `MAX_STATE_NAME` is dead code"
  - id: IN-12
    severity: info
    disposition: deferred
    title: "[agent] A revert by job leaves the old \"oldest version\" entry in `legacy`"
  - id: IN-13
    severity: info
    disposition: deferred
    title: "[agent] rpm `installed_version` is not safe for packages with several installed versions"
  - id: IN-14
    severity: info
    disposition: deferred
    title: "[agent] [user WIP, not Phase 84] per-capability collection intervals starve the rollout's inventory signal"
  - id: IN-15
    severity: info
    disposition: deferred
    title: "[frontend] Controls that appear without a flag, and a click that does nothing"
  - id: IN-16
    severity: info
    disposition: deferred
    title: "[frontend] \"Manage in Settings\" in Change Management can never be activated"
  - id: IN-17
    severity: info
    disposition: deferred
    title: "[frontend] Live-region structure announces too much"
  - id: IN-18
    severity: info
    disposition: deferred
    title: "[frontend] Start and preflight have no client cap on selected patches, and validation errors read as connection errors"
  - id: IN-19
    severity: info
    disposition: deferred
    title: "[frontend] Approval card keeps a stale local decision patch across polls"
  - id: IN-20
    severity: info
    disposition: deferred
    title: "[frontend] Rollouts-tab badge keeps another organization's count when it cannot be read"
  - id: IN-21
    severity: info
    disposition: deferred
    title: "[frontend] Decisions list: \"Show more\" reorders cards already on screen"
  - id: IN-22
    severity: info
    disposition: deferred
    title: "[frontend] Coupling to server display strings"
  - id: IN-23
    severity: info
    disposition: deferred
    title: "[frontend] Minor robustness points"
open: 5
total: 62
recorded: 2026-11-07T13:39:46.048Z
---

# Phase 84: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-25 | warning | open | - |
| WR-26 | warning | fixed | 84-REVIEW-FIX.md |
| WR-27 | warning | fixed | 84-REVIEW-FIX.md |
| WR-28 | warning | fixed | 84-REVIEW-FIX.md |
| WR-29 | warning | fixed | 84-REVIEW-FIX.md |
| WR-30 | warning | fixed | 84-REVIEW-FIX.md |
| WR-31 | warning | fixed | 84-REVIEW-FIX.md |
| WR-32 | warning | open | - |
| IN-24 | info | open | - |
| IN-25 | info | open | - |
| IN-26 | info | open | - |
| CR-01 | critical | fixed | 84-23 b4b12a817 (a refused canary row stores only the attempt, is retried, then fails the host with a reason) (not in the current review) |
| CR-02 | critical | fixed | 84-23 b4b12a817, 96f904ebb (a held or suggested canary row is the ring's Install line with Approve and Deny, shown on the card) (not in the current review) |
| CR-03 | critical | fixed | 84-25 8eff5e5ea, 39bd6c2b2, 03c9d443e (absent token, pre-change service baseline, Windows error 1060) (not in the current review) |
| CR-04 | critical | fixed | 84-26 4e4e6bacf (every apt downgrade passes --no-remove) (not in the current review) |
| WR-01 | warning | fixed | 84-23 d0f68b449 (rollout_not_delivered ignored by the circuit breaker; 84-27 910b6d309 adds rollout_no_result) (not in the current review) |
| WR-02 | warning | fixed | 84-27 910b6d309, c1e95941c, 6992b583f (inflight.close_job on every abandoned install path) (not in the current review) |
| WR-03 | warning | fixed | 84-27 910b6d309, c1e95941c (in-flight install and revert bounds); 84-28 41af2a7c8, f6d8e13f5 (Cancel of a running rollout) (not in the current review) |
| WR-04 | warning | fixed | 84-27 c1e95941c (a denied or expired computer stays waiting, not_approved) (not in the current review) |
| WR-05 | warning | deferred | A Reboot or Revert-restart card that expires during a stop later halts and reverts the ring; it is the reboots.py path, untouched by these fixes; next review round (most important open item). Owner: next Phase 84 review round. (not in the current review) |
| WR-06 | warning | fixed | 84-27 6992b583f (settle.recover_unsent, send exceptions end the row) (not in the current review) |
| WR-07 | warning | deferred | Claim-before-document needs a crash between two inserts; separate Start change with a startup sweep. (not in the current review) |
| WR-08 | warning | deferred | Only overlapping windows mis-mark not reached; windows.py maths change scheduled separately. (not in the current review) |
| WR-09 | warning | deferred | The legacy route still denies (500 instead of 403); fail-closed, different route. (not in the current review) |
| WR-10 | warning | fixed | 84-24 ca8a7fa74 (manual rollback refuses a rollout's own jobs with 409) (not in the current review) |
| WR-11 | warning | deferred | Audit role attribution, not a rollout safety truth. (not in the current review) |
| WR-12 | warning | deferred | A unique per-tenant settings index needs a duplicate-merging migration, which runs on live only by the user. (not in the current review) |
| WR-13 | warning | fixed | 84-26 f0697f33f (non-boolean require_reversible is an error) (not in the current review) |
| WR-14 | warning | fixed | 84-26 946ce3133 (per-package save, serde defaults, .bad copy, fsync before rename) (not in the current review) |
| WR-15 | warning | fixed | 84-26 4e4e6bacf (revert_precheck: a package that is gone installs nothing) (not in the current review) |
| WR-16 | warning | deferred | heartbeat.rs is the user's uncommitted work; a cost issue, not a safety one. (not in the current review) |
| WR-17 | warning | deferred | The vendor flag limit is documented; revert answers not_uninstallable honestly. (not in the current review) |
| WR-18 | warning | deferred | --no-remove (84-26) is the safety net; a dnf refresh needs a privileged-call change. (not in the current review) |
| WR-19 | warning | deferred | UI behaviour with no safety impact, UI unpublished and DEV-1..DEV-4 still await the user; next UI round. (not in the current review) |
| WR-20 | warning | deferred | UI behaviour with no safety impact, UI unpublished and DEV-1..DEV-4 still await the user; next UI round. (not in the current review) |
| WR-21 | warning | deferred | UI behaviour with no safety impact, UI unpublished and DEV-1..DEV-4 still await the user; next UI round. (not in the current review) |
| WR-22 | warning | deferred | UI behaviour with no safety impact, UI unpublished and DEV-1..DEV-4 still await the user; next UI round. (not in the current review) |
| WR-23 | warning | deferred | UI behaviour with no safety impact, UI unpublished and DEV-1..DEV-4 still await the user; next UI round. (not in the current review) |
| WR-24 | warning | deferred | UI behaviour with no safety impact, UI unpublished and DEV-1..DEV-4 still await the user; next UI round. (not in the current review) |
| IN-01 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-02 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-03 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-04 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-05 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-06 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-07 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-08 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-09 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-10 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-11 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-12 | info | deferred | Info level, triaged with the next review. IN-12 also touches legacy state in the agent job records. (not in the current review) |
| IN-13 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-14 | info | deferred | Info level, triaged with the next review. IN-14 is the user's uncommitted agent WIP, not Phase 84. (not in the current review) |
| IN-15 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-16 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-17 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-18 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-19 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-20 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-21 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-22 | info | deferred | Info level, triaged with the next review. (not in the current review) |
| IN-23 | info | deferred | Info level, triaged with the next review. (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
