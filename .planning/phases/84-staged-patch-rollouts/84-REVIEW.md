---
phase: 84-staged-patch-rollouts
reviewed: 2026-11-07T01:13:41Z
depth: standard
files_reviewed: 89
files_reviewed_list:
  - App.tsx
  - agent-install/omni-agent-rs/Cargo.lock
  - agent-install/omni-agent-rs/Cargo.toml
  - agent-install/omni-agent-rs/src/capabilities/mod.rs
  - agent-install/omni-agent-rs/src/capabilities/patch_installer.rs
  - agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs
  - agent-install/omni-agent-rs/src/capabilities/patch_state.rs
  - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
  - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
  - agent-install/omni-agent-rs/src/capabilities/service_watch.rs
  - agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs
  - agent-install/omni-agent-rs/src/heartbeat.rs
  - backend/agent_group_endpoints.py
  - backend/app_startup.py
  - backend/autonomous_ops/approvals.py
  - backend/autonomous_ops/decision_row.py
  - backend/autonomous_ops/delivery.py
  - backend/autonomous_ops/dispatch_check.py
  - backend/autonomous_ops/gate.py
  - backend/autonomous_ops/ledger.py
  - backend/autonomous_ops/messages.py
  - backend/autonomous_ops/reconciler.py
  - backend/autonomous_ops/registry.py
  - backend/autonomous_ops/response_views.py
  - backend/autonomous_ops/rollout/__init__.py
  - backend/autonomous_ops/rollout/cards.py
  - backend/autonomous_ops/rollout/controller.py
  - backend/autonomous_ops/rollout/dispatcher.py
  - backend/autonomous_ops/rollout/health.py
  - backend/autonomous_ops/rollout/installs.py
  - backend/autonomous_ops/rollout/lifecycle.py
  - backend/autonomous_ops/rollout/lines.py
  - backend/autonomous_ops/rollout/loop.py
  - backend/autonomous_ops/rollout/messages.py
  - backend/autonomous_ops/rollout/picker.py
  - backend/autonomous_ops/rollout/reboots.py
  - backend/autonomous_ops/rollout/revert.py
  - backend/autonomous_ops/rollout/rings.py
  - backend/autonomous_ops/rollout/settle.py
  - backend/autonomous_ops/rollout/signals.py
  - backend/autonomous_ops/rollout/start.py
  - backend/autonomous_ops/rollout/store.py
  - backend/autonomous_ops/rollout/views.py
  - backend/autonomous_ops/rollout/windows.py
  - backend/autonomous_ops_endpoints.py
  - backend/autonomous_ops_response_endpoints.py
  - backend/catalogue_mounts_devices.py
  - backend/change_management_endpoints.py
  - backend/deployment_endpoints.py
  - backend/deployment_service.py
  - backend/maintenance_endpoints.py
  - backend/maintenance_service.py
  - backend/migrations/031_patch_rollouts.py
  - backend/patch_core_endpoints.py
  - backend/patch_rollout_endpoints.py
  - backend/router_registry.py
  - backend/skill_handlers_queries.py
  - components/AgentGroupsDashboard.tsx
  - components/AutonomousOpsActivity.tsx
  - components/AutonomousOpsDecisions.tsx
  - components/AutonomousOpsRowActions.tsx
  - components/ChangeManagementDashboard.tsx
  - components/MaintenanceWindowConfig.tsx
  - components/OsPatchesTab.tsx
  - components/PatchManagementDashboard.tsx
  - components/patchRollouts/ChangeManagementWindows.tsx
  - components/patchRollouts/MaintenanceWindowDialog.tsx
  - components/patchRollouts/RingDetail.tsx
  - components/patchRollouts/RingsSettings.tsx
  - components/patchRollouts/RolloutApprovalCard.tsx
  - components/patchRollouts/RolloutCard.tsx
  - components/patchRollouts/RolloutChip.tsx
  - components/patchRollouts/RolloutDialogs.tsx
  - components/patchRollouts/RolloutsTab.tsx
  - components/patchRollouts/StartDialog.tsx
  - components/patchRollouts/StartPatchPicker.tsx
  - components/patchRollouts/StartPreflight.tsx
  - components/patchRollouts/ringsForm.ts
  - components/patchRollouts/rolloutCopy.ts
  - services/patchRollouts/approvals.ts
  - services/patchRollouts/lifecycle.ts
  - services/patchRollouts/rings.ts
  - services/patchRollouts/rollouts.ts
  - services/patchRollouts/start.ts
  - services/patchRollouts/types.ts
  - services/patchRollouts/windows.ts
  - shared/agent-response-contract.json
  - shared/autonomous-ops-banned-terms.json
  - shared/catalogue-access.json
findings:
  critical: 4
  warning: 24
  info: 23
  total: 51
status: issues_found
---

## Summary

Four gsd-code-reviewer passes ran in parallel at standard depth over the Phase 84 source files (backend core, backend routes and contracts, Rust agent, frontend), scoped from the SUMMARY key-files and the phase's task commits (base 8c2e89397). Tests were reference only. The orchestrator merged and renumbered the parts (map below); each finding names its source part. The orchestrator checked all four Critical findings against the code: CR-01 (`installs.py:167-170` stores a non-dispatched decision as `installActionId` and nothing settles it), CR-02 (`start.py:293` blocks only `off`; `lines.py:121-123` skips every non-`awaiting_approval` decision, so Suggest raises nothing), CR-03 (`service_watch.rs` `classify_systemd` never reads `LoadState`; on this VM `systemctl show` of a missing unit returns `LoadState=not-found ActiveState=inactive Result=success`, exit 0, which maps to Stopped) and CR-04 (`patch_installer.rs:429-430` apt downgrade without `--no-remove`). CR-03, CR-04 and WR-13..WR-18 are in the unpublished agent 2.1.17 and must be fixed before it is published.

**4 critical, 24 warning, 23 info.**

**backend core:** Reviewed the rollout controller, its collaborators and the changes to gate, delivery, reconciler, dispatch_check,
approvals, ledger, response_views and registry. Tenant isolation is solid: every read and write is filtered by
tenantId, the dispatcher allow-list is enforced at decide time and at delivery, the unique partial claim index and
the approved-to-dispatching compare-and-set are used correctly, and windows and times fail closed. The main defects
are in how the controller reacts to a gate decision that is not a plain "dispatching" or "awaiting_approval" row, and
in the lack of any timeout or failure handling for work in flight. Because the reconciler now deliberately skips
`patch_rollout` rows and a running rollout cannot be cancelled (only a halted one can), each of these leaves a
rollout stuck forever with its claims held.

Not re-reported (already recorded by the executors): 25 hosts per ring in views, a denied/expired halt can only be
cancelled, a reverted ring reads red on resume, a refused revert restart is not re-asked, a live rollout under
shadow still sends rows approved earlier, three stop cancellations consume MAX_ATTEMPTS.

**backend routes:** Area: /api/patch-rollouts, rollout-cards and rollout-lines, maintenance windows (IANA zones), the Change Management windows list, the fenced legacy revert, `installed_ids_for`, `ringName`, registration and the three shared JSON contracts.

The authz model is sound. Every write route stacks `_require_manage_patches` (which refuses Platform Support) and `_require_interactive_session` (which refuses API keys), and the mount guard adds `manage:patches`. The tenant is derived by `_tenant_for`, so a non-staff `tenantId` is refused with 403. Rollout, suggestion and line lookups are filtered by `{id, tenantId}` and answer 404 for another tenant. Route ordering is correct (`/draft`, `/window`, `/rings` and the others are declared before `/{rollout_id}`). The Change Management `/maintenance-windows` route is declared before `/{change_id}`. All three JSON files parse. The contract change is additive, with `version` unchanged. The new tokens are read from the heartbeat, never from a version number, so 2.1.16 and older agents keep working. Examples, counts and codes in the contract are internally consistent, and the copy test (33 tests) passes. I confirmed the router modules import and register the expected routes.

I found no critical defects. There are four warnings: a pre-existing 403-to-500 conversion inside the fenced revert route, a manual rollback route that still bypasses the rollout gate for rollout jobs, lost platform-tier attribution in the audit chain for rollout writes, and missing uniqueness on the per-tenant settings documents. The info items are doc/test drift, small validation gaps and dead code.

**agent:** Reviewed the committed Phase 84 diff (`8c2e8939..HEAD`) of the agent plus the code it calls (`privileged.rs`, `remediation_actions.rs`, `instructions.rs`, `lib.rs`) and how the backend reads the reports (`rollout/signals.py`, `rollout/revert.py`).

What holds up: all child processes are argv only (no shell, no interpolation); patch ids and `revert_of`/`job_id` are validated (`PKG_RE`, `safe_id`) and every package argument follows `--` or begins with an alphanumeric; every child process has a timeout (`output()`, 120 s for the source query, 20 s `COMMAND_DEADLINE` for `privileged`); patch jobs are serialized by `PATCH_JOBS`, so two jobs never write `patch_state.json` at once; the 2.1.16 flat map loads as `legacy`; `revert_of` malformed is an error and never falls back; the tokens and codes match `shared/agent-response-contract.json`.

Two things must be fixed before 2.1.17 ships: a Linux service that is not installed reads `stopped` and fails the health gate (which halts the ring and reverts healthy hosts), and the Linux downgrade used by every revert runs `apt-get install -y` with no `--no-remove`, so a revert can remove other packages. Details and six warnings follow. I did not run cargo.

**frontend:** All new rollout components, services and types were read in full. The Phase 84 hunks of the edited files were reviewed through `git diff 8c2e893977f987a6be1e508a76a8bc48b485bd51..HEAD`. The payload types were checked against `backend/autonomous_ops/rollout/views.py`, `cards.py`, `lines.py`, `patch_rollout_endpoints.py` and `autonomous_ops_response_endpoints.py`.

The code is careful. Every async call has an `alive` or `seq` guard, and every mutating button has an in-flight guard. Controls come from server flags, and server strings are rendered as React text. The payload types match what the server builds. I found no security defect and no data-loss defect, so there are no blockers.

The real defects are these:

- A flag contradiction. The server sets `canStart` to false during a stop, but the UI treats `stopped` and `canStart` as independent.
- The Approve success path ignores the partial and deferred answers the server really sends.
- The Resume and Cancel dialogs give wrong advice on a permanent 409 or 404 and leave the card stale.
- The Settings time-zone field goes blank after the first window is saved.
- Two one-shot "remembered request" mechanisms (the draft intent and focus-after-start) can fire later than intended.

The RolloutsTab stop tests (`PatchRolloutsTab.test.tsx:401` and `:410`) use the flag combination `canStart: true` with `stopped: true`, which the server cannot send. That is why WR-01 passed the tests.

## Critical Issues

### CR-01: [backend core] A canary install the gate did not dispatch (suggested, awaiting approval, or recorded refusal) wedges the computer permanently

_Source: backend core CR-01_


**File:** `backend/autonomous_ops/rollout/installs.py:157-171` (also `installs.py:66-76`, `settle.py:209,263`, `lines.py:151`, `dispatcher.py:148-149`)
**Issue:** In `canary_auto`, every recorded decision that is neither shadow nor `dispatching` goes to the `else`
branch, which assumes "the gate wants a person" and stores `installActionId` on the host. Nothing ever settles
that state:
- `needs_decision` returns False for a ring-0 host with `installActionId` (line 73), so the controller never decides
  for it again.
- `settle.settle` only visits hosts that are `installing`, or `waiting` with `lineActionIds` (settle.py:263). This host
  is `waiting` with neither, so it is never read.
- `lines.closed_line` only watches `rollout:install|reboot|revert_reboot` (lines.py:151). A denied or expired
  `rollout:canary_install` row never halts the rollout.
- `_ring_state` keeps the ring at "installing" while the host sits at `waiting`.

The `else` branch also catches a **recorded refusal** (`decision.state == "refused"` with an action id), for example
a platform or tenant stop pressed between `_may_decide` at the top of the tick and this call, or a never-touch entry
added meanwhile. That host never installs and is never retried.

If a person does approve the held row (a `suggested` or `awaiting_approval` card, ruleId `rollout:canary_install`),
`dispatcher.send` sets the host to `installing` but never stores `installJobId` or `installInstructionId`
(dispatcher.py:148-149). `_settle_auto` then looks up the result with job id `None`, finds no entry, finds no
instruction status, and reports `inflight` forever. The real result is posted to the job and nobody reads it.

Failure scenario: a tenant at the Suggest level (see CR-02), or one whose settings are momentarily unreadable
(`settings_unreadable` escalates to suggest), starts a rollout. The canary host's automatic row is recorded as
`suggested`, the host is parked with `installActionId`, and the ring stays at "installing" for good. The rollout is
`running`, so Cancel is not offered, and the host claim is held forever.

**Fix:** Only treat `decision.state == "dispatching"` and the shadow case as handled. For a recorded refusal, do not
store `installActionId`. Leave the host `waiting` so the next pass retries with a new attempt, or fail it with the
reason. For `awaiting_approval` or `suggested`, track the row like an approval line: push it to
`lineActionIds.install` and `linePatchIds` (as `raise_line` does) so `_settle_lines` and the halt-on-denial path see
it, and use rule id `rollout:install` or add `rollout:canary_install` to `closed_line`. Make `dispatcher.send` also
store `installJobId` and `installInstructionId` from the row's `params.job_id` and the queued task id.

### CR-02: [backend core] At the Suggest level (or with unreadable settings) no approval line is ever raised, so the rollout hangs silently

_Source: backend core CR-02_


**File:** `backend/autonomous_ops/rollout/lines.py:122-124` (and `start.py:293`, `controller.py:42`)
**Issue:** `gate.decide` escalates a `level == suggest` tenant to `suggested`, and `suggest` is the strongest
escalation (`gate.py:43,176-181`). `raise_line` only counts `awaiting_approval` as a raised card. Any other state is
counted `skipped` and nothing is pushed to `lineActionIds` (lines.py:122-124). Start refuses only `off`
(start.py:293), and `_may_decide` only blocks `off` (controller.py:42), so a Suggest-level tenant, or one whose settings
read as unreadable, can start a rollout.

Failure scenario: the first pass records one stray `suggested` row per host (a suggestion in Activity). Every later
pass is refused as `duplicate` by the open-dedupe check. No Install line appears on Needs your decision, the hosts
stay `waiting`, `_ring_state` reports the ring "installing", and nothing ever advances or fails. The rollout is
`running`, so it cannot be cancelled. If someone approves the stray suggested row from the generic Suggestions path,
the install is sent for a host that has no `lineActionIds`, and its result is never read (the host flips back to
waiting at settle.py:243-248 and the dedupe key is now held by the dispatching row).

**Fix:** Refuse Start and the controller's decide path when `settings.effective_level(tenant)` is not above `suggest`
or `tenant.readable` is False (add a blocker row in `_assess`). Or have `raise_line` accept `suggested` as an
open approval row (push it to `lineActionIds`, and make `cards._is_open` and `_pairs` include `suggested`) since a
person has to approve it either way.

### CR-03: [agent] A watched service that is not installed on a Linux host reads as `stopped`, which fails the health gate and triggers a revert

_Source: agent CR-01_


**File:** `agent-install/omni-agent-rs/src/capabilities/service_watch.rs:61-73` and `:108-109`
**Issue:** `status_of` asks `systemctl show -p ActiveState,SubState,Result,ExecMainStatus <name>` and `classify_systemd` maps `ActiveState=inactive` with `Result=success` to `Health::Stopped`. For a unit that does not exist, `systemctl show` exits 0 and prints exactly that. I ran it here:

```
$ systemctl show -p ActiveState,SubState,Result,ExecMainStatus nosuchsvc
Result=success
ExecMainStatus=0
ActiveState=inactive
SubState=dead
```
The `LoadState=not-found` line is never requested. `service_state` therefore reports `{"name":"nosuchsvc","state":"stopped"}`. The failure report was safe with this (a clean stop is never reported); the new state report is not, because `backend/autonomous_ops/rollout/signals.py:_from_block` turns any `stopped` or `failed` entry into `False`. The tenant's watched list is tenant-wide, so a list such as `[sshd, nginx]` fails the `services` signal of every host that has no nginx. `health.ring_verdict` then halts the ring (`canary_failed` / `host_failed` / `failure_share`) and `revert.start_ring_revert` downgrades packages on every computer of the ring, "healthy-looking ones included" (revert.py docstring). Windows does not have this problem: `sc query` of a missing service exits non-zero, which gives `Unknown`.
**Failure scenario:** tenant watches `nginx`; ring 1 has 10 hosts, 4 without nginx; the canary host is one of those. After the install the canary reports `nginx: stopped` (it never ran). The rollout halts with `canary_failed` and the revert downgrades packages on the canary, a patch that did nothing wrong.
**Fix:** request `LoadState` and treat anything not loaded as unknown:
```rust
privileged::run_output("systemctl", &["show", "-p", "LoadState,ActiveState,SubState,Result,ExecMainStatus", name])
// in classify_systemd, first thing:
if property(output, "LoadState").is_some_and(|l| l == "not-found" || l == "masked") { return Health::Unknown; }
```
Add a test with the `not-found` output. Make the same decision for `masked`.

### CR-04: [agent] Linux downgrade (every revert, manual or by job) runs `apt-get install -y` without `--no-remove`, so a revert can remove other packages

_Source: agent CR-02_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:429-430` (called from `rollback_job` at `:451` and from `rollback` at `:477`)
**Issue:** `downgrade` runs `apt-get install -y -q --allow-downgrades ... -- pkg=oldversion`. When the old version conflicts with something installed (the usual case is a library whose `-dev` or sibling package depends on `libfoo (= version)`), apt resolves it by removing the dependants, and `-y` accepts the removal. `--no-remove` is not passed. Phase 84 makes this automatic: a halt reverts every host in the ring that installed anything, without a person looking at the apt plan. The `reversible_linux` pre-check does not protect against it (see WR-06): it only proves the old version is listed.
**Failure scenario:** `libssl3` upgraded by job N; `libssl-dev` is installed and requires `libssl3 (= new)`. The ring halts; `apt-get install -y libssl3=old` removes `libssl-dev` (and with it whatever build tooling depends on it) on every host of the ring, and still reports `reverted` if libssl3 ends up at the old version.
**Fix:** add `"--no-remove"` to the argv; a plan that needs a removal then fails with the apt message and the row reads Not reverted instead of damaging the host:
```rust
privileged(&["apt-get", "install", "-y", "-q", "--no-remove", "--allow-downgrades", ...])
```
The dnf path (`dnf downgrade`) does not erase without `--allowerasing`, so it is fine as it is.

## Warnings

### WR-01: [backend core] A canary install that was not delivered counts against the tenant's circuit breaker

_Source: backend core WR-01_


**File:** `backend/autonomous_ops/ledger.py:268-270` (producers: `settle.py:138-141`, `installs.py:102`)
**Issue:** An automatic canary row whose instruction expired or was cancelled ends `failed` with reasonCode
`rollout_not_delivered`. This is the expected outcome of D-04 (the agent polled after the window closed).
`BREAKER_IGNORED` lists `not_delivered` but not `rollout_not_delivered`, and `recent_finished_auto` filters with
`reasonCode $nin BREAKER_IGNORED`. These rows are `autoDispatched` and `failed`, so they count. The ledger comment says
"an instruction that was never delivered must never lower a level".

Failure scenario: three canary hosts (or three attempts on one host, since each retry is a new automatic row) are offline
when the window ends. Three `rollout_not_delivered` rows finish within 24 hours and the breaker drops the tenant from
Undoable-auto to Suggest. That also switches off the tenant's unrelated automatic security responses, and (see CR-02)
wedges the rollout.
**Fix:** Add `"rollout_not_delivered"` to `BREAKER_IGNORED` (and check `rollout_no_new_boot` the same way if such a row
can be automatic).

### WR-02: [backend core] Undelivered or abandoned installs leave a patch job "In Progress", so the computer reads busy for every later rollout

_Source: backend core WR-02_


**File:** `backend/autonomous_ops/rollout/installs.py:100-105,198-208`, `settle.py:136-142`, `dispatcher.py:56-64`, `lifecycle.py:119-133`
**Issue:** The install job is inserted as `In Progress` before the instruction is sent (installs.py:198-201, and by
`ensure_job` for approved rows). When the instruction is refused at delivery (expired), cancelled by a stop, never
delivered, or ended by `_end_unfetched` at a halt, the ledger row is failed and the host goes back to waiting, but the
job is never closed. No sweeper touches `patch_deployment_jobs`; a job only completes from an agent result
(`deployment_result_endpoints`, `agent_instruction_endpoints.py:130`). `start._busy_agents` treats any `In Progress` job
whose agent has no result as busy, and the patch screen uses the same rule. The own-rollout exemption in
`dispatcher._busy` hides this while the rollout is active.

Failure scenario: the canary instruction expires at the end of a window (the normal D-04 path). The host retries with a
new job; the first one stays `In Progress`. After the rollout completes or is cancelled, that host is listed as
"busy" for every future rollout and for manual patching, until someone edits the database.
**Fix:** On each not-delivered path (`_fail_undelivered`, `settle._settle_auto` and `_settle_lines` not-delivered,
`_end_unfetched`, and the `else` of `dispatcher.send`), mark the job `Failed` or `Cancelled` with a status log line (a
helper in `settle.py` is enough). Better, create the canary job only after `gate.execute` queued, as the approved path
does.

### WR-03: [backend core] Work in flight has no timeout or failure handling, and a running rollout cannot be cancelled

_Source: backend core WR-03_


**File:** `backend/autonomous_ops/rollout/settle.py:32,135-143,178-186`, `revert.py:36,253-255`, `lifecycle.py:287-293`
**Issue:** `_settle_auto`, `_settle_lines` and the revert settle read "not delivered" from the instruction status in
`("refused", "cancelled_by_stop", "cancelled")` only. Statuses seen in the instruction route are `pending`, `sent` or
`delivered`, then `ACCEPTED`, `SUCCESS`, `FAILURE`, `REFUSED` (`agent_tasks_endpoints.py:111-123`). An instruction the
agent answers `FAILURE` (an agent that rejects `install_patches` or `rollback_patches`) never posts a deployment result:
the rejected-patch fail-over there only covers `os_patch_install` and `os_patch_rollback`. Likewise `expiresAt` is only
enforced when an agent polls, so an instruction that stays `pending` because the computer went offline is never treated
as expired. In every case the host stays `installing` (or `reverting`) with `inflight=True` and no timer (the only
timeout is the reboot one, `NEW_BOOT_WAIT`). A reverting host also blocks Resume (`RevertRunning`).

Failure scenario: a canary computer is online when its install is sent, then is powered off for good. The ring
waits forever, the claim is held forever, and because `cancel` requires `halted`, an operator has no way to stop or
free a `running` rollout.
**Fix:** Treat instruction status `failure` and `error` as not delivered/failed. In the controller, treat a `pending`
instruction whose own `expiresAt` has passed as not delivered, and give an `installing` or `reverting` host a deadline
(for example, report time or dispatch time plus a bound) after which it is failed with a clear message so the ring can
halt. Consider allowing Cancel on a `running` rollout.

### WR-04: [backend core] A computer whose approval row was denied, expired or closed is shown as "installed"

_Source: backend core WR-04_


**File:** `backend/autonomous_ops/rollout/settle.py:187-198,242-250`
**Issue:** In `_settle_lines`, a row in state `denied` or `expired` (not in a stop) sets nothing. In `_settle_host` the
final `else` then finds no outstanding row, no unresolved patch (the ids are still in `linePatchIds`), and flips the
host to `installed` with `waitReason` cleared. This runs before `_halt_on_lines` in the same tick, and again on every
pass for a halted rollout (the halt closes open rows as `expired` with `rollout_closed`).

Failure scenario: a person denies the Install card for ring 1. In the same tick the controller settles first and sets
that host to `installed`; the ring card then shows "Installed 2 patches" for a computer that was never touched. After
any halt, every other computer of the ring with an open card gets the same label, and `installedIds` stays empty so
nothing is reverted either. The views report a state that is not true.
**Fix:** In `_settle_lines`, record `prog.closed = True` for `denied`/`expired` rows that are not stop-handled, and in
`_settle_host` keep such a host `waiting` (waitReason None or a "not approved" reason) instead of `installed`.

### WR-05: [backend core] A Reboot or Revert-restart card that expires during a stop halts the rollout and reverts the ring once the stop ends

_Source: backend core WR-05_


**File:** `backend/autonomous_ops/rollout/lines.py:154-156`, `controller.py:259,310-311`
**Issue:** The stop exemption in `closed_line` relies on `rollout.stoppedSince`. Install rows that expired in a stop
are re-offered because `settle._settle_lines` records them in `lineSettled`; the `handled` list then excludes them.
No such handling exists for `reboot` rows (`reboots._settle_host` ignores an `expired` row) and none for
`revert_reboot`. The controller clears `stoppedSince` at the end of the first tick after the stop (controller.py:310-311).
On the next tick `closed_line` runs with `since=None`, finds the Reboot row that expired during the stop, and halts with
`approval_expired`, which also starts `start_ring_revert`.

Failure scenario: a ring's installs finish, a Reboot card is raised, a platform stop is pressed and runs past the 24-hour
expiry. The stop is released, and one tick later the rollout halts and the ring's patches are reverted, although nobody
could answer the card. This contradicts the documented intent (module docstring and `closed_line` docstring).
**Fix:** In `reboots._settle_host`, handle an `expired` row inside `stoppedSince` like the install line does: add the id
to `rebootSettled`, bump `rebootAttempts` and put the host back to `installed` so `needs_line` raises a new card. Add the
id to a `handled` source for `closed_line` (read `rebootSettled` as well as `lineSettled`).

### WR-06: [backend core] A row claimed as "dispatching" with no instruction is never recovered

_Source: backend core WR-06_


**File:** `backend/autonomous_ops/rollout/dispatcher.py:139-146`, `installs.py:156-166,197-211`, `settle.py:178-186`, `reconciler.py:131-132`
**Issue:** The reconciler used to fail rows stuck in `approved`/`dispatching` after a bound; for `patch_rollout` rows it
now skips them (reconciler.py:131). In the rollout code the window between claiming a row and writing the instruction is
unprotected. In `dispatcher.send` the CAS to `dispatching` happens before `ensure_job` and `gate.execute`, and
`dispatch_approved` only logs an exception. In `canary_auto`, `gate.decide` records a `dispatching` row and
`_send` then inserts the job and calls `gate.execute`, and an exception there propagates. If the process dies or one of
those awaits raises, the row stays `dispatching` with no instruction id. `_settle_lines` then reads
`instructionIds[-1]` as None, which is not "not delivered", so the host reads `inflight` forever. In the canary path the
next pass re-decides with the same dedupe key and is refused as `duplicate`, so the host never installs.
`gate._link` failing (logged only) has the same effect for delivery-time refusals.

**Fix:** Settle a `dispatching` rollout row that has no instruction (or whose instruction status is unknown) and is older
than a short bound as failed `rollout_not_delivered` (the same retry path), in `settle` for installs and in
`reboots._settle_host` for reboots. Wrap `ensure_job`/`gate.execute` in `send` so a raise ends the row.

### WR-07: [backend core] Start claims every computer before the rollout document exists

_Source: backend core WR-07_


**File:** `backend/autonomous_ops/rollout/start.py:368-379`
**Issue:** `start_rollout` inserts the host claims one by one and only then inserts the rollout document. A crash or
restart in between (or between `claim_hosts` calls with an uncaught `BaseException`) leaves active claims with no rollout.
The unique index then holds those computers forever, `classify_hosts` lists them as "in another rollout" with the
fallback name, and the controller never sees them because it scans rollouts. `store.discard` only runs on an exception.
**Fix:** Insert the rollout document first (status `running`, with `rings`), then claim; on any failure delete both.
The controller already tolerates a rollout with no claims (it advances an empty ring). Alternatively add a startup
sweep that releases claims whose rollout does not exist.

### WR-08: [backend core] Overlapping maintenance windows make `_reach` end the install window early and mark computers "not reached"

_Source: backend core WR-08_


**File:** `backend/autonomous_ops/rollout/controller.py:165-177`, `windows.py:175-186`
**Issue:** `is_open` returns the occurrence that closes last when windows overlap, so the `(open, close)` pair changes
while the window stays continuously open (window A 01:00-03:00, window B 02:00-05:00: at 02:00 the pair becomes B).
`_reach` compares `open_now[0] != begin` and concludes the stored install window ended, then marks every waiting computer
whose `lastOnlineInWindowAt` is before the old `begin` as `not_reached` and clears `installWindow`. A computer that is only
online from 02:00 onward is still shown and kept as not reached, although the window never closed. In a later ring that is
permanent for the rollout (until `offer_returning` after completion). The instruction `expiresAt` is unaffected.
**Fix:** Build the continuous span first (merge overlapping or touching occurrences in `is_open`, returning the first
open and the last close of the union), or in `_reach` treat the window as ended only when `now >= end` of the span and no
window is open at `now`.

### WR-09: [backend routes] The fenced legacy revert turns its own 403 into a 500

_Source: backend routes WR-01_


**File:** `backend/deployment_endpoints.py:289` (raise) and `:318` (catch)
**Issue:** `rollback_deployment` raises `HTTPException(403, "Unauthorized")` inside the `try` when the deployment is missing or belongs to another tenant. Only `except LegacyRevertRetired` and the blanket `except Exception` follow. `HTTPException` is an `Exception`, so the 403 is caught and logged at ERROR as "Error triggering rollback". The client then gets 500 "Internal server error".
**Failure scenario:** Tenant B calls `POST /api/deployments/<tenant A id>/rollback`. It is denied, but with a 500 and an ERROR log line. The new fence's own test only expects 409 for the same-tenant case. Because the route now always ends in the 409 fence once ownership passes, this 403 path is the only branch that does real work.
**Fix:**
```python
    except HTTPException:
        raise
    except LegacyRevertRetired:
        raise HTTPException(status_code=409, detail="...")
    except Exception as e:
        ...
```

### WR-10: [backend routes] Manual job rollback still reverts a rollout's jobs outside the rollout gate

_Source: backend routes WR-02_


**File:** `backend/patch_core_endpoints.py:262-307`
**Issue:** `rollback_patch_job` accepts any finished `patch_deployment_jobs` document of the tenant. Rollout install jobs and rollout revert jobs both carry `rolloutId` (`autonomous_ops/rollout/installs.py:200`, `revert.py:122`). The route queues `rollback_patches` instructions straight into `agent_instructions`, with no stop check, no window and no ledger row. The rollout controller is not told. T-84-13 fenced the legacy staged-deployment revert for exactly this reason, but this route stays open for rollout jobs. Running it against a rollout's own revert job also re-queues a revert of patches that are already reverted: `installed_ids_for` returns the `success` results with code `reverted`.
**Failure scenario:** A user holding `manage:patches` presses the old per-job Rollback on a rollout install job while the rollout is mid-ring. The agents uninstall the patches and the rollout still shows those computers as `installed`. The controller's own revert then races with this one, and the ring's health verdict is judged on a state nobody recorded.
**Fix:** after the job lookup, refuse rollout-owned jobs:
```python
    if job.get("rolloutId"):
        raise HTTPException(status_code=409, detail="This job belongs to a rollout. Revert it from Rollouts on the Patching screen.")
```

### WR-11: [backend routes] Rollout writes lose the platform tier in the audit chain

_Source: backend routes WR-03_


**File:** `backend/patch_rollout_endpoints.py:83-93` (`_actor`; used at lines 168, 205, 276 and 293)
**Issue:** `_actor` returns `{id, name, username, display}` and omits `tier`. The sibling helper `autonomous_ops.views.actor_for` (`views.py:94-104`) adds `tier` (`platform` or `tenant`). `ledger._audit_actor` (`ledger.py:69`) builds the audit role from `actor.get("tier") or "user"`. `rings.save` and `lifecycle.resume/cancel` pass the actor straight through (`_recorded_actor` and `_who` only fill name fields). `stop.py:96` also reads `actor.tier`.
**Failure scenario:** A platform owner names a tenant with `tenantId` and saves its rollout rings, or resumes or cancels one of its rollouts. The audit event records the role as `user`, the same as a tenant admin. The ledger and audit entry cannot show that platform staff changed a tenant's safeguard.
**Fix:** reuse the shared helper instead of a second copy:
```python
async def _actor(db, user):
    caller = await ops_views.build_caller(user)
    return await ops_views.actor_for(db, caller)   # adds "tier"
```
The extra keys `id` and `name` that the rollout code reads can be added to the result.

### WR-12: [backend routes] Per-tenant settings documents have no unique index, so an upsert race gives duplicates

_Source: backend routes WR-04_


**File:** `backend/maintenance_service.py:199-206` (`set_time_zone` upsert); `backend/autonomous_ops/rollout/rings.py:248` (`patch_rollout_settings` upsert); `backend/autonomous_ops/rollout/store.py:83-90` (`ensure_indexes`)
**Issue:** Both collections hold one document per tenant and are written with `update_one(..., upsert=True)` keyed on `tenantId`. `ensure_indexes` and migration 031 create no unique index on either, and `maintenance_windows` has no `tenantId` index. Two concurrent first saves (a double-click, or two admins) each miss and both insert.
**Failure scenario:** Two `maintenance_settings` documents exist for one tenant. `find_one` returns an arbitrary one on every read. The window maths in `windows.load` and the text shown in the UI can then use different zones, and an `update_one` changes only one of them, so a corrected zone appears to revert. The same applies to ring settings, so a rollout can start on the old rings.
**Fix:** add `create_index("tenantId", unique=True)` for `maintenance_settings` and `patch_rollout_settings`, and `create_index([("tenantId", 1), ("id", 1)])` for `maintenance_windows`, in `store.ensure_indexes` (called by migration 031). The migration should merge any existing duplicates first.

### WR-13: [agent] `require_reversible` fails open when the value is not a JSON boolean

_Source: agent WR-01_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:75` (the test that locks it in is `patch_reversible.rs:199`)
**Issue:** `field("require_reversible").and_then(Value::as_bool).unwrap_or(false)`: a present but malformed value (`"true"`, `1`, `"yes"`) silently becomes `false`, and the job installs everything without the reversibility check. The same function treats a malformed `revert_of` as an error precisely so it never degrades to the weaker behaviour (comment on line 69); `require_reversible` is the opposite direction (weaker = installs a patch that cannot be put back) and gets the opposite treatment. The test `patch_reversible_job_reads_require_reversible_...` asserts the fail-open behaviour for `"yes"`.
**Failure scenario:** a backend refactor or a proxy that serialises booleans as strings sends `"require_reversible": "true"`; every host installs irreversible patches with no error, and the rollout later cannot be reverted.
**Fix:**
```rust
let require_reversible = match field("require_reversible") {
    None => false,
    Some(Value::Bool(b)) => *b,
    Some(_) => return Err("The patch instruction carried an invalid require_reversible".to_string()),
};
```
Change the test to expect `is_err()` for `"yes"`.

### WR-14: [agent] Job records are written once at the end of the job, and any unreadable shape silently wipes the whole state file

_Source: agent WR-02_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:387` and `:421` (install), `patch_state.rs:58-64` and `:116-118`
**Issue:** (a) The Linux install loads the state at the start and saves only after the last package; one package can run up to `LINUX_TIMEOUT` (30 min) so a job of N packages holds its records in memory for up to N x 30 min. If the agent is stopped in the meantime (the apt run may restart the agent's own service, the host reboots, the process is killed) the packages that were already upgraded have no record, and the later revert by job answers `not_applicable` ("no record of that job") or `not_changed_by_job` for them: the patch is still installed and cannot be reverted. (b) `from_bytes` calls `serde_json::from_value(...).unwrap_or_default()` when the file has a `jobs`/`legacy` object, and `load_from` returns the default on any read or parse error. A single entry with a missing field (`JobEntry` has no `#[serde(default)]` on `at`, `os`, `changes`), a truncated file, or a read error makes the whole state default, and the next `save` overwrites the file with the empty state, losing every other job's record and the whole `legacy` map. `save_to` also does not `sync_all` before the rename.
**Fix:** call `patch_state::save(&mut state)` after each package that changed (cheap, small file); give the `JobEntry` fields `#[serde(default)]`; on a parse failure of an existing non-empty file, keep it as `patch_state.json.bad` before returning the default, and let `save_to` `File::sync_all` the temporary file before `rename`.

### WR-15: [agent] A revert re-installs a package that has since been removed

_Source: agent WR-03_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:442-455`
**Issue:** `rollback_job` only compares `installed_version(...)` to the recorded version. When the package is no longer installed (`None`, for example an admin removed it after the patch) the code falls through to `reversible_linux` and then `downgrade`, and `apt-get install pkg=old` / `dnf downgrade pkg-old` installs it: a revert adds software. The install path guards this ("Package is not installed; patching only upgrades installed packages", line 390), the revert path does not. The legacy `rollback` (line 473) has the same hole.
**Fix:** read `installed_version` once; when it is `None` return `coded_result(&pkg, "failed", NOT_APPLICABLE, "The package is not installed any more, so nothing was reverted", false)`.

### WR-16: [agent] `service_state` is not gated by the capability, runs the service manager a second time every minute, and does it synchronously on the heartbeat task

_Source: agent WR-04_


**File:** `agent-install/omni-agent-rs/src/capabilities/service_watch.rs:238-250`, `agent-install/omni-agent-rs/src/heartbeat.rs:542-543`
**Issue:** `service_failures` returns nothing unless `remediation_executor` is enabled (`report_with`, line 174). `state_report` ignores `enabled`, so a tenant that switched the capability off but still has a watched list gets every listed service queried and reported. Both reports have their own 60 s cache and each calls `status_of` for every watched name, so a host now spawns two `systemctl` (Windows: two or three `sc`) processes per watched service per minute instead of one. `privileged::run_output` is a blocking call with a 20 s deadline, and `build_payload` is called straight from the async loop (`lib.rs:208`), so a hung `systemctl` (dbus stuck) with the maximum 50 watched services stalls the heartbeat for up to 50 x 20 s = 1000 s per report, 2000 s for the two. The host drops off the platform while that happens.
**Fix:** share one status read per pass (compute `Health` for each name once and derive both reports from it), skip the state report when the capability is off, and run `build_payload`'s service queries with `tokio::task::spawn_blocking` or a total budget (stop after about 10 s and report the rest as `unknown`).

### WR-17: [agent] The Windows reversibility check reads a metadata flag of an update that is not installed yet

_Source: agent WR-05_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:236`
**Issue:** The install script defers an update when `-not $u.IsUninstallable` on the offered (`IsInstalled=0`) update. For an update that is not installed, WUA reports only what the update package declares; it cannot know whether the later uninstall will be allowed (a combined servicing-stack plus cumulative update, an update later superseded, an update that other installed updates depend on). `WUA_UNINSTALL` re-checks the flag on the installed update (line 204), so the revert honestly says `not_uninstallable` afterwards, but by then the patch is installed on the whole ring. The check therefore proves nothing stronger than "the vendor claims it is removable".
**Fix:** keep the check (it is the best available) but state this limit in the module doc and the user-facing words ("reversible" must read "expected to be reversible"), and make the backend not treat `not_uninstallable` at revert time as unexpected. If a stronger guarantee is wanted, restrict canary rings to KBs that were already uninstalled once on a reference machine.

### WR-18: [agent] The Linux reversibility check is necessary but not sufficient, and dnf/yum read a possibly stale cache

_Source: agent WR-06_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs:89-104`
**Issue:** "reversible" means "the version installed now is still listed for this one package name". (a) `apt-get install --only-upgrade pkg` also upgrades dependencies, but only `pkg` is recorded and reverted; the dependencies stay at the new version, so the host is not put back as it was. (b) The old `pkg` may need an exact-version dependency (see CR-02), in which case the downgrade fails or removes packages even though the check said reversible. (c) The apt branch runs `apt-get update` before the check (`patch_installer.rs:383`), but the dnf/yum branch never refreshes metadata (`dnf list` honours `metadata_expire`, 48 h by default, and when the agent is not root it runs unprivileged and may not be able to refresh at all), so a version the repository dropped a day ago can still be listed as offered.
**Failure scenario:** `dnf list --showduplicates openssl` served from a 30-hour-old cache lists `1.1.1k-6`; the repo already removed it; the install proceeds; the revert answers `version_not_offered` for a patch that was declared reversible.
**Fix:** for dnf/yum run the query through `privileged` with `--refresh`; record the dependency changes if they can be known (`apt-get -s install --only-upgrade pkg` lists them) or document that revert covers the named package only; keep CR-02's `--no-remove` as the safety net.

### WR-19: [frontend] During a stop the Start button is hidden and the viewer is told to "ask someone with patching access"

_Source: frontend WR-01_


**File:** `components/patchRollouts/RolloutsTab.tsx:294-324` and `:379-391`; `components/patchRollouts/StartDialog.tsx:443-466`
**Server reference:** `backend/autonomous_ops/rollout/views.py:67`, which has `"canStart": can_act and not stopped`.

**Issue:** The server folds the stop into `canStart`. While automatic actions are stopped, a person who holds `manage:patches` gets `flags.canStart === false` and `flags.stopped === true`. The tab handles this in three wrong ways:

1. `canStart && startButton(...)` (line 321) does not render the Start button at all.
2. `{!flags.canStart && <p>{NO_START}</p>}` (line 324) shows "Ask someone with patching access to start a rollout." to someone who has that access.
3. The `blocked = flags.stopped ? STOP_BLOCKED : ...` branch (line 294) is only reachable when `canStart && stopped`. The server never sends that combination, so the designed disabled-button-with-reason state is dead code.

The same flag gates the dialog: `{flags.canStart && <StartDialog .../>}` (line 379).

**Failure scenario:** The operator opens Start a rollout, ticks patches and presses Start. A stop begins (someone else presses stop all). The next 30 s poll flips `canStart` to false and `StartDialog` unmounts. The selection and name are gone. If `startRollout` was already in flight, `submit` sees `alive.current === false` and returns at line 449. Neither `onStarted` nor the success toast runs. The rollout may have started, but the list never refreshes and focus never moves.

The tests do not catch this. `PatchRolloutsTab.test.tsx:401` and `:410` use `canStart: true, stopped: true`, which the server cannot produce.

**Fix:** Gate on a flag the server really sends. Show the disabled-with-reason state when stopped for anyone who is not otherwise blocked. Keep the dialog mounted while it is open.

```tsx
// RolloutsTab.tsx
// canStart is false during a stop, so "may start" is canStart || (stopped && canManageRings).
const mayStart = flags.canStart || (flags.stopped && flags.canManageRings);
const blocked = flags.stopped ? STOP_BLOCKED : strip.state === 'none' ? NO_WINDOW : null;
...
{mayStart && startButton('rollouts-start-reason')}
{!mayStart && <p className={MUTED}>{NO_START}</p>}
...
{(mayStart || startOpen) && <StartDialog open={startOpen} stopped={flags.stopped} ... />}
```

Also make `StartDialog.submit` call `onStarted(result.id)` before the `alive` check, or keep the callback in a ref. Fix the fixtures so a stop test sets `canStart: false, canManageRings: true`.

### WR-20: [frontend] Approve overstates the outcome when some computers were refused or the answer is deferred

_Source: frontend WR-02_


**File:** `components/patchRollouts/RolloutApprovalCard.tsx:122-133`
**Server reference:** `backend/autonomous_ops/rollout/lines.py:213-246`.

**Issue:** `approve_line` returns HTTP 200 with `status: "approved"` for a partial success. `approved` can be less than the line's computer count, and `refused` can list hosts with a reason. When the window is closed it returns `when: "window"`, and `windowOpensAt` can be null (the "waiting computer" message). The browser ignores `out.approved`, `out.refused` and the null-`windowOpensAt` case:

- The toast is `Approved. N patches will install on ${line.computerTotal} computers ${when}.` The count is always the full line total.
- `when` is "now" whenever `windowOpensAt` is null, even when the server said `when: "window"`.
- The local patch always says approved. The refused hosts are never shown anywhere.

**Failure scenario:** Three computers are on the line and one is refused (for example, no longer eligible). The operator sees "will install on 3 computers now". Only 2 are approved, and they may be deferred to a window that is closed. The server's `out.message` is used for the line text, but the toast and the settled card state contradict it. This is the "overstates what happened" defect the phase set out to avoid.

**Fix:** Build the toast from the answer.

```ts
const approved = Number.isFinite(out.approved) && out.approved > 0 ? out.approved : n;
const refused = Array.isArray(out.refused) ? out.refused.length : 0;
const deferred = out.when === 'window';
const when = deferred ? (out.windowOpensAt ? `when your window opens at ${clockText(out.windowOpensAt)}` : 'when the computer can take it') : 'now';
...
`Approved for ${plural(approved,'computer','computers')}${refused ? `, ${refused} refused` : ''}. ${when}.`
```

When `refused.length > 0`, show the refused host and reason list in the line result, and use `showToast(..., 'info')`.

### WR-21: [frontend] Resume and Cancel dialogs say "Try again" on a permanent 409 or 404 and never refresh the card

_Source: frontend WR-03_


**File:** `components/patchRollouts/RolloutDialogs.tsx:91-100` (Resume) and `:175-184` (Cancel)

**Issue:** `lifecycle.ts` documents 404 and 409 (`not halted`) as permanent states. The dialogs treat every non-403 error as retryable. They set `Couldn't ...: not halted. Try again.`, keep the dialog open, and never call `onDone`. The card behind the dialog, and its Resume and Cancel buttons, stays stale until the next 30 s poll. The sibling approval card already handles this case by telling the user it will not change and calling `onStale()`. Only 403 calls `onDone`.

**Failure scenario:** Two admins look at the same halted rollout. One presses Cancel. The other presses Resume and gets `Couldn't resume the rollout: This rollout is not halted. Try again.` Retrying always returns 409. The card keeps showing Halted with live buttons until the poll.

**Fix:** Treat 404 and 409 like the approval card does.

```ts
const lasting = status === 404 || status === 409;
setError(detail ? `Couldn't resume the rollout: ${plain(detail)}.${lasting ? '' : ' Try again.'}` : RESUME_FALLBACK);
if (lasting) onDone();   // re-read the card; keep the dialog open so the sentence can be read
```

Close the dialog on the next read, or switch the footer to a single "Close" button for a lasting error.

### WR-22: [frontend] Settings time-zone field goes blank after the first window is saved

_Source: frontend WR-04_


**File:** `components/MaintenanceWindowConfig.tsx:76-98` and `:120`

**Issue:** `load(first)` only fills `zoneInput` when `first` is true. Saving the first window from the dialog stores the organization's time zone, because the dialog's `body.timeZone` is sent when no zone is stored. `reload()` then calls `load(false)`. That call sets `zone` to the new value but leaves `zoneInput` as `''`.

Result:

- `dirty` is true.
- `zoneValid` is false, because `''` fails `isKnownTimeZone`.
- The input shows only the placeholder.
- The "Save time zone" button reads as the accent style but is disabled.
- No error text appears.

The person has just chosen a zone and the field shows none. The window cards and the Rollouts strip show it, so the screen contradicts itself.

**Fix:** Sync the input when it had not been edited.

```ts
if (first) setZoneInput(storedZone ?? '');
else setZoneInput(prev => (prev === (zoneRef.current ?? '') ? (storedZone ?? '') : prev));
```

Keep `zoneRef.current = zone` in a ref so the comparison uses the previous stored value.

### WR-23: [frontend] The one-shot Draft a rollout intent can fire later than intended

_Source: frontend WR-05_


**File:** `components/patchRollouts/RolloutsTab.tsx:211-218`; `components/PatchManagementDashboard.tsx:54-62` and `:467`; `App.tsx` (`handleOpenFromAutonomousOps`, `patchingIntent`)

**Issue:** The intent is only consumed after `state` has loaded, because the effect needs the first read to learn `canStart`. Two paths leave it pending:

1. **The first read fails.** `state` stays null and `onIntentConsumed` is never called. `rolloutIntent` stays in the dashboard. The user clicks Try again a minute later (or leaves the tab and comes back, which remounts `RolloutsTab` with the intent still set). When the read succeeds, the Start dialog pops open. The comment in `PatchManagementDashboard` says a later visit never reopens the dialog, but the failure path breaks that.
2. **App level.** `setPatchingIntent(payload)` happens before `handleSetCurrentView`. If the view gate refuses `patchManagement` (the viewer lost access, or the permission refresh moved them to the landing view), the dashboard never mounts and nobody clears the intent. It then opens the Start dialog on the next unrelated visit to Patching.

**Fix:** Clear the intent when the read fails as well (drop it with the first `failed`), and clear it in App when the view is not `patchManagement`.

```tsx
// RolloutsTab: also consume on a failed first read
useEffect(() => { if (intent && state === null && failed) callbacks.current.onIntentConsumed?.(); }, [intent, state, failed]);
// App: expire the intent on any navigation away
useEffect(() => { if (currentView !== 'patchManagement') setPatchingIntent(null); }, [currentView]);
```

Note that App's dashboard clears the intent as soon as the dashboard mounts, so the second change must not clear it before the dashboard has read it. Order the effect after the mount, or tie it to `currentView` changes only.

### WR-24: [frontend] Focus-after-start request is never cleared when the new card is not in the first page

_Source: frontend WR-06_


**File:** `components/patchRollouts/RolloutsTab.tsx:221-229` and `:386`

**Issue:** `onStarted` stores `focusAfterLoad.current = id` and the effect focuses `#rollout-{id}` once the card is in the DOM. If the card never appears in the page the list reads, the ref is never cleared. This happens in these cases:

- The list read fails.
- The new rollout sorts after the first page. The order puts halted, waiting-for-approval and running rollouts first, and the page is 10 cards.
- The new card is hidden because a refresh returned an older page.

Any later `setState` (the next poll, or "Show more rollouts" bringing the card in) then runs `card.focus()` and moves keyboard focus away from whatever the person is doing, for example a text field in the Rings card.

**Fix:** Make the request one-shot with an expiry. Clear it after the first read that follows the start, whether or not the card was found.

```ts
useEffect(() => {
  const id = focusAfterLoad.current;
  if (!id || !state) return;
  focusAfterLoad.current = null;                 // always one-shot
  document.getElementById(`rollout-${id}`)?.focus();
}, [state]);
```

## Info

### IN-01: [backend core] Non-finite ring numbers raise a plain error instead of a validation sentence

_Source: backend core IN-01_


**File:** `backend/autonomous_ops/rollout/rings.py:124-129`
**Issue:** `_whole` calls `int(value)` on any int or float. A JSON body with `NaN` or `Infinity` (accepted by Python's
`json`) makes `int()` raise `ValueError` or `OverflowError`, not `RingsError`, so a route that catches `RingsError` returns
500 rather than 422.
**Fix:** In `_whole` and `_soak` check `math.isfinite(value)` first and return None (then `RingsError` is raised).

### IN-02: [backend core] `messages.fill` substitutes sequentially, so a value can inject a later placeholder

_Source: backend core IN-02_


**File:** `backend/autonomous_ops/rollout/messages.py:23-27`
**Issue:** Each key is replaced in turn on the already-substituted string. A rollout name or hostname containing
`{patch}` or `{host}` is replaced by the following key's value (for example in `installs.install_request` and
`lines._why`). No security impact (the content is the caller's own and displayed as text), but the sentence can be
garbled.
**Fix:** Substitute in one pass (for example `re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template)`).

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### IN-03: [backend routes] The mount guard authenticates with JWT only, so the documented and tested API-key read path never runs in production

_Source: backend routes IN-01_


**File:** `backend/catalogue_mounts_devices.py:19-23` and `:36`; `backend/patch_rollout_endpoints.py:1-8`
**Issue:** `PATCH_GUARD` uses the default `auth=get_current_user` (bearer JWT). `/api/patch-rollouts` is mounted under it. A request that carries only `X-API-Key` is rejected with 401 before the route dependency `get_current_user_or_api_key` runs. The module docstring ("reads ... an API key is refused only for Start/rings") and `test_patch_rollout_endpoints.py:274-283` assert an API key can GET rings. The test overrides the route dependency and never mounts the guard. Behaviour is fail-closed and matches the rest of `/api/patches`, but the docs and the test describe something production never does. This is the same drift risk the autonomous-ops guard avoids by passing `auth=get_current_user_or_api_key`.
**Fix:** either state in the docstring that API keys are refused at the mount, or give the guard `auth=get_current_user_or_api_key` if key reads are intended. Add one mounted-app test.

### IN-04: [backend routes] The time-zone allow-list accepts `localtime` and `Factory`, and a stored zone is not re-validated on use

_Source: backend routes IN-02_


**File:** `backend/maintenance_service.py:61-67` and `:174`
**Issue:** `available_timezones()` on this host contains `localtime` (resolves to the server's `/etc/localtime`) and `Factory`. `valid_zone("localtime")` is true, so a tenant's windows then follow the host clock zone. Separately, `_zone_for_save` returns the stored zone without validating it, and `_checked` calls `ZoneInfo(zone_name)` directly. A stored name that no longer resolves raises `ZoneInfoNotFoundError`, which the route does not catch, so a one-time window save answers 500.
**Fix:** reject `localtime`, `Factory` and any name without `/` other than `UTC` and `GMT` in `valid_zone`. In `_zone_for_save`, treat an unresolvable stored zone as a `WindowError(VALIDATION["time_zone"])`.

### IN-05: [backend routes] A `timeZone` sent with a window is silently dropped when the tenant already has a zone

_Source: backend routes IN-03_


**File:** `backend/maintenance_service.py:208-215`
**Issue:** If a zone is stored, `_zone_for_save` returns `(stored, None)` and ignores a different valid `body.timeZone`. The save succeeds in the stored zone, with no signal that the request's zone was not used.
**Fix:** return a `WindowError` (or a warning field) when `body.timeZone` is valid but differs from the stored zone, and point to `PUT /api/maintenance/time-zone`.

### IN-06: [backend routes] The legacy-fence swallow logs nothing

_Source: backend routes IN-04_


**File:** `backend/deployment_service.py:213-218`
**Issue:** When a staged stage fails with `rollback_on_failure` true, `trigger_rollback` raises `LegacyRevertRetired` and the handler is a bare `pass`. The deployment stays `failed`, the config still says `rollback_on_failure: True`, and nothing records that the requested revert did not happen.
**Fix:** `logger.warning("staged deployment %s failed; legacy revert is retired, use a rollout", deployment_id)`, or store a `rollback_skipped` note on the deployment.

### IN-07: [backend routes] `ROLLBACK_JOB_TYPE` is documented as shared, but the result route still uses a literal

_Source: backend routes IN-05_


**File:** `backend/patch_core_endpoints.py:253` and `backend/deployment_result_endpoints.py:225`
**Issue:** The comment says the constant is "the job type the result route reads". The result route compares `job.get("type") != "Patch Rollback"` against a literal, so renaming the constant would silently break the pending-list guard.
**Fix:** import `ROLLBACK_JOB_TYPE` into `deployment_result_endpoints.py` (or move it to a small shared module).

### IN-08: [backend routes] Unused import

_Source: backend routes IN-06_


**File:** `backend/patch_rollout_endpoints.py:32`
**Issue:** `MIN_RINGS` is imported and never used (ruff F401).
**Fix:** drop it from the import.

### IN-09: [backend routes] The chat `/maintenance` answer drops the zone and days, and lists paused windows

_Source: backend routes IN-07_


**File:** `backend/skill_handlers_queries.py:195-212`
**Issue:** The rows read `start → end` with no time zone and no weekdays, so for `Asia/Kolkata` a tenant sees `22:00 → 02:00` with no zone. A weekly window reads as `[weekly]`. One-time windows print `2026-11-08T01:30`. `isActive` is not read, so a switched-off window shows as scheduled.
**Fix:** project `isActive` and `daysOfWeek`, read the tenant's zone from `maintenance_settings`, skip inactive rows, and format as `Mon, Wed 22:00-02:00 (Asia/Kolkata)`.

### IN-10: [backend routes] The rings request body has no per-ring size caps

_Source: backend routes IN-08_


**File:** `backend/patch_rollout_endpoints.py:62-65`
**Issue:** `RingsBody.rings` is `List[Dict[str, Any]]` with at most 50 items. `rings.validate` then bounds the ring count (2 to 4), but `groupIds` and any extra nested value are unbounded. `validate` builds `$in: sorted(seen_groups)` from the whole list. Only the proxy body limit bounds it.
**Fix:** use a typed `RingIn` model with `name: StrictStr (max_length 60)`, `groupIds: List[StrictStr] (max_length 200)`, and numeric fields. Keep `rings.validate` for the sentences.

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### IN-11: [agent] `MAX_STATE_NAME` is dead code

_Source: agent IN-01_


**File:** `agent-install/omni-agent-rs/src/capabilities/service_watch.rs:40` and `:229`
**Issue:** `remediation_actions::is_valid_service_name` already rejects names over `MAX_SERVICE_NAME` (also 128), so the added `name.len() <= MAX_STATE_NAME` filter can never reject anything the second filter would accept. The test `state_report_lists_a_duplicate_name_once_and_drops_a_name_over_128_characters` passes through the existing rule and would not notice if the constant were deleted.
**Fix:** delete the constant and the clause (or reuse `MAX_SERVICE_NAME`), and keep the test.

### IN-12: [agent] A revert by job leaves the old "oldest version" entry in `legacy`

_Source: agent IN-02_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:442-458` (compare `:479`)
**Issue:** only the manual rollback removes `state.legacy[pkg]`. After a successful revert by job the legacy entry stays, so a later manual `rollback_patches` without `revert_of` downgrades the package to the version recorded before the first patch ever applied, which may be much older than what the revert by job restored.
**Fix:** on a successful by-job revert, set `legacy[pkg]` to the version now installed or remove it, and save the state in `rollback_job` too (it does not save anything today, so the by-job revert is never written to disk; harmless now but it blocks fixing this).

### IN-13: [agent] rpm `installed_version` is not safe for packages with several installed versions

_Source: agent IN-03_


**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:353-354`
**Issue:** `rpm -q --qf "%{VERSION}-%{RELEASE}" pkg` prints one record per installed copy with no separator (kernel, multilib). The value becomes `1.0-1.el81.0-2.el8`, which is recorded as `before`, compared with the offered list (never equal, so the package is deferred), and passed to `dnf downgrade pkg-<that>` (fails). Safe, but the result text and the stored record are garbage. dpkg has the same problem for multi-arch packages.
**Fix:** add `\n` to the query format and refuse (`None`/failed with a clear message) when more than one line comes back.

### IN-14: [agent] [user WIP, not Phase 84] per-capability collection intervals starve the rollout's inventory signal

_Source: agent IN-04_


**File:** `agent-install/omni-agent-rs/src/capabilities/mod.rs` (`DEFAULT_INTERVALS`, `("system_patching", 3600)`, uncommitted)
**Issue:** `signals._inventory` needs a `meta.system_patching.timestamp` more than 5 minutes after the install to decide anything (`INVENTORY_FRESH_AFTER`). With `collect_due` the patch scan now runs once an hour, so after an install the inventory signal stays `None` ("no data") for up to an hour on every host unless the agent rescans after an install. A rollout soak shorter than the scan interval therefore ends `no_data` instead of passing. Not a phase defect, but 2.1.17 would ship both together. Also in the same uncommitted hunks: `prune(&conn)` in `buffer.rs` ignores the `Result` of `DELETE` (`unwrap_or(0)`), so a failing prune is silent, and `last_run` in `collect_due_at` records a collector as having run even when it was only skipped by `catch_unwind` returning an error value.
**Fix:** make a completed patch job reset `last_run["system_patching"]` (or run the scan once right after the job), and note the interval for the soak in the rollout docs.

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

### IN-15: [frontend] Controls that appear without a flag, and a click that does nothing

_Source: frontend IN-01_


**File:** `components/OsPatchesTab.tsx:44-49`; `components/PatchManagementDashboard.tsx:460`; `components/patchRollouts/RolloutsTab.tsx:211-218`

**Issue:** The Roll out in rings button renders for every viewer of OS Patches, because the dashboard always passes `onRollOut`. The intent effect drops the request silently when `flags.canStart` is false. A view-only user, or anyone during a stop (see WR-01), clicks the button and lands on the Rollouts tab with no dialog and no explanation. The project rule is that every control comes from a server flag.

**Fix:** Pass `onRollOut` only when the last read says the viewer may start (lift `flags.canStart` into the dashboard through `onAttentionCount`'s sibling callback), or show a one-line "You can't start rollouts here" status when an intent is dropped.

### IN-16: [frontend] "Manage in Settings" in Change Management can never be activated

_Source: frontend IN-02_


**File:** `components/ChangeManagementDashboard.tsx:190`; `App.tsx:1960`

**Issue:** `ChangeManagementWindows` takes `onOpenSettings`, and its documentation says it is a button when the viewer can open Settings. `ChangeManagementDashboard` renders `<ChangeManagementWindows />` with no prop and has no navigation prop of its own. App renders it without one. The link therefore always shows as plain text, and the UI-SPEC section 9 affordance is never reachable.

**Fix:** Add `onOpenView?: (view: AppView) => void` to `ChangeManagementDashboard`, pass `handleSetCurrentView` from App, and give `ChangeManagementWindows` `onOpenSettings` when `isSuperAdminRoleName(role) || hasPermission('manage:settings')`, as `RolloutsTab.canOpenSettings` does.

### IN-17: [frontend] Live-region structure announces too much

_Source: frontend IN-03_


**File:** `components/patchRollouts/StartPreflight.tsx:562`; `components/patchRollouts/RolloutApprovalCard.tsx:163`; `components/patchRollouts/RolloutsTab.tsx:153` and `:393`

**Issue:**

- The whole "Check before starting" section is `role="status" aria-live="polite"`, with a nested `role="alert"`. Every preflight re-read re-announces all rows, and the failure text is announced twice.
- A settled approval line is `<li role="status">` inside a `<ul>`. That removes the listitem role, and the list then contains non-list children.
- The "N rollouts need your attention" live region is only updated when the number grows. If it goes 2, 1, 2 the text is identical to the previous one and React does not change the DOM, so nothing is announced.

**Fix:** Put `aria-live` only on the `Checking...` and error lines. Put the status on an inner `<p>` in the line, not on the `li`. Reset the announcement to `''` before setting it again.

### IN-18: [frontend] Start and preflight have no client cap on selected patches, and validation errors read as connection errors

_Source: frontend IN-04_


**File:** `components/patchRollouts/StartDialog.tsx:395-412` and `:456-462`; `services/patchRollouts/start.ts:28-39`
**Server reference:** `StartBody.patchIds` and `PreflightBody.patchIds` are capped at 200 in `patch_rollout_endpoints.py:42` and `:51`.

**Issue:** The picker lets a person tick without limit, and a draft can add more. At 201 the server answers 422 with a Pydantic array `detail`. `startFailure` keeps only string details, so `detail` is empty. `submit` then shows "Couldn't start the rollout. Check your connection and try again." The preflight shows its connection error, and neither can ever succeed.

**Fix:** Cap ticks at 200 in `toggle` with a one-line "You can select up to 200 patches" message. Map a 422 with an empty detail to "Check the name and the patches you picked."

### IN-19: [frontend] Approval card keeps a stale local decision patch across polls

_Source: frontend IN-05_


**File:** `components/patchRollouts/RolloutApprovalCard.tsx:263` and `:93`

**Issue:** The card's `patches` map is never cleared. `AutonomousOpsDecisions` clears its own incident patches on every poll (`setPatches({})`), but the rollout card keeps its map for as long as the card stays on screen. A patch is only ignored while the server's line is non-pending. If the same line becomes pending again while the card is still shown (an `install` offered again for a computer that came back, a second `revert_reboot`), the stale `approved` patch hides the new Approve and Deny buttons and shows the old result.

**Fix:** Drop a patch when the server's line leaves `pending`: in `RolloutApprovalCard`, remove `patches[kind]` when `line.state !== 'pending'`, or clear all patches in `onPoll`.

### IN-20: [frontend] Rollouts-tab badge keeps another organization's count when it cannot be read

_Source: frontend IN-06_


**File:** `components/PatchManagementDashboard.tsx:75-86`

**Issue:** The badge read swallows failures (`/* no badge when the read fails */`) but does not reset `rolloutAttention`. After switching tenant (`tenantId` changes) the old tenant's count stays on the tab until a read succeeds, and forever if the read always fails (for example a 403 on the new organization).

**Fix:** Call `setRolloutAttention(0)` at the top of the effect and in the `catch`.

### IN-21: [frontend] Decisions list: "Show more" reorders cards already on screen

_Source: frontend IN-07_


**File:** `components/AutonomousOpsDecisions.tsx:156-185` and `mergeByDeadline` (`:57-67`)

**Issue:** Incidents and rollout rings are paged by independent offsets, and the merged list is re-sorted by deadline each render. A "Show more" that fetches two pages inserts cards among the cards already shown, so the card the person was reading can move down.

**Fix:** This is the accepted trade-off of the merge design, but it is worth noting. If it matters, append "more" results after the existing entries and leave the sort to the poll.

### IN-22: [frontend] Coupling to server display strings

_Source: frontend IN-08_


**File:** `components/patchRollouts/RolloutApprovalCard.tsx:53-56`, `:101-105`, `:128-131`

**Issue:** `ringNameOf(subtitle)` and `patchCountOf(label)` parse server sentences with regular expressions. `messages.py`'s `ring_subtitle` is `Ring {i} of {r}: {ring} · {computers}` and `labels.install` is `Install {patches} on {computers}`. If the copy changes, the ring name silently drops out of the aria labels and the "halts at" sentence, and the Approve toast says "0 patches will install". The payload has the real values (`card.ring`, ring name in the cards builder); ring name and patch count should be fields.

**Fix:** Add `ringName` and `patchCount` to `ApprovalCard` and `ApprovalLine` in `cards.py` and `types.ts`, and drop the regular expressions.

### IN-23: [frontend] Minor robustness points

_Source: frontend IN-09_


**Files and issues:**

- `components/patchRollouts/StartDialog.tsx:443-446`: Start double-submit protection relies on `disabled` after a re-render. The Resume, Cancel and approval buttons use an `inFlight` or `sent` ref. Add one here for consistency.
- `components/MaintenanceWindowConfig.tsx:79-92`: a failed background reload (`load(false)`) sets `loadFailed`, which hides the whole panel and disables Add window, although the save or delete that triggered the reload succeeded. Keep the last data on a background failure.
- `services/patchRollouts/types.ts:265-267`: `startsAt` and `endsAt` are documented as "ISO times". The server sends local `YYYY-MM-DDTHH:MM` strings (`maintenance_service.py:125`), which is what the `datetime-local` input needs. Fix the comment so nobody adds a `Z` conversion.
- `components/patchRollouts/RingDetail.tsx:610-611`: "Showing N of M computers" has no way to load the rest. The first page of hosts is all the browser can ever show.
- **[user WIP, not Phase 84]** `components/AgentGroupsDashboard.tsx` (uncommitted hunk): `error` is shared with the create form. A successful reload calls `setError('')` and can erase a create-form error shown just before. A failed load leaves the previous list in place with the error text.

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

## Finding map

| ID | Part | Part ID |
|----|------|---------|
| CR-01 | backend core | CR-01 |
| CR-02 | backend core | CR-02 |
| CR-03 | agent | CR-01 |
| CR-04 | agent | CR-02 |
| WR-01 | backend core | WR-01 |
| WR-02 | backend core | WR-02 |
| WR-03 | backend core | WR-03 |
| WR-04 | backend core | WR-04 |
| WR-05 | backend core | WR-05 |
| WR-06 | backend core | WR-06 |
| WR-07 | backend core | WR-07 |
| WR-08 | backend core | WR-08 |
| WR-09 | backend routes | WR-01 |
| WR-10 | backend routes | WR-02 |
| WR-11 | backend routes | WR-03 |
| WR-12 | backend routes | WR-04 |
| WR-13 | agent | WR-01 |
| WR-14 | agent | WR-02 |
| WR-15 | agent | WR-03 |
| WR-16 | agent | WR-04 |
| WR-17 | agent | WR-05 |
| WR-18 | agent | WR-06 |
| WR-19 | frontend | WR-01 |
| WR-20 | frontend | WR-02 |
| WR-21 | frontend | WR-03 |
| WR-22 | frontend | WR-04 |
| WR-23 | frontend | WR-05 |
| WR-24 | frontend | WR-06 |
| IN-01 | backend core | IN-01 |
| IN-02 | backend core | IN-02 |
| IN-03 | backend routes | IN-01 |
| IN-04 | backend routes | IN-02 |
| IN-05 | backend routes | IN-03 |
| IN-06 | backend routes | IN-04 |
| IN-07 | backend routes | IN-05 |
| IN-08 | backend routes | IN-06 |
| IN-09 | backend routes | IN-07 |
| IN-10 | backend routes | IN-08 |
| IN-11 | agent | IN-01 |
| IN-12 | agent | IN-02 |
| IN-13 | agent | IN-03 |
| IN-14 | agent | IN-04 |
| IN-15 | frontend | IN-01 |
| IN-16 | frontend | IN-02 |
| IN-17 | frontend | IN-03 |
| IN-18 | frontend | IN-04 |
| IN-19 | frontend | IN-05 |
| IN-20 | frontend | IN-06 |
| IN-21 | frontend | IN-07 |
| IN-22 | frontend | IN-08 |
| IN-23 | frontend | IN-09 |
