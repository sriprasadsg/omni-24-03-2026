---
phase: 84-staged-patch-rollouts
reviewed: 2026-11-07T00:00:00Z
depth: standard
files_reviewed: 42
files_reviewed_list:
  - agent-install/omni-agent-rs/src/capabilities/patch_installer.rs
  - agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs
  - agent-install/omni-agent-rs/src/capabilities/patch_state.rs
  - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
  - agent-install/omni-agent-rs/src/capabilities/service_watch.rs
  - agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs
  - backend/autonomous_ops/ledger.py
  - backend/autonomous_ops/messages.py
  - backend/autonomous_ops/rollout/cancelling.py
  - backend/autonomous_ops/rollout/cards.py
  - backend/autonomous_ops/rollout/controller.py
  - backend/autonomous_ops/rollout/dispatcher.py
  - backend/autonomous_ops/rollout/inflight.py
  - backend/autonomous_ops/rollout/installs.py
  - backend/autonomous_ops/rollout/lifecycle.py
  - backend/autonomous_ops/rollout/lines.py
  - backend/autonomous_ops/rollout/messages.py
  - backend/autonomous_ops/rollout/revert.py
  - backend/autonomous_ops/rollout/settle.py
  - backend/autonomous_ops/rollout/signals.py
  - backend/autonomous_ops/rollout/views.py
  - backend/patch_core_endpoints.py
  - backend/patch_rollout_endpoints.py
  - backend/tests/test_patch_rollout_baseline.py
  - backend/tests/test_patch_rollout_cancel_running.py
  - backend/tests/test_patch_rollout_contract.py
  - backend/tests/test_patch_rollout_gap_inflight.py
  - backend/tests/test_patch_rollout_gap_lines.py
  - backend/tests/test_patch_rollout_health.py
  - backend/tests/test_patch_rollout_legacy_fence.py
  - backend/tests/test_patch_rollout_lifecycle.py
  - backend/tests/test_patch_rollout_messages.py
  - backend/tests/test_patch_rollout_views.py
  - backend/tests/test_patch_rollout_views_cancel.py
  - components/patchRollouts/RolloutCard.tsx
  - components/patchRollouts/RolloutDialogs.tsx
  - services/patchRollouts/lifecycle.ts
  - services/patchRollouts/types.ts
  - shared/agent-response-contract.json
  - src/__tests__/PatchRolloutCancelRunning.test.tsx
  - src/__tests__/PatchRolloutDialogs.test.tsx
  - src/__tests__/_patchRolloutFixtures.ts
findings:
  critical: 0
  warning: 8
  info: 3
  total: 11
status: issues_found
---

# Phase 84: Code Review Report (incremental, gap-closure round 84-23..84-29)

**Reviewed:** 2026-11-07
**Depth:** standard (incremental against diff base 817979a18)
**Files Reviewed:** 42
**Status:** issues_found

## Summary

Reviewed the gap round's changes in full and the surrounding files for context. The fixes for CR-01..CR-04 hold up: the held canary row now carries a real approval line (`track_line`), the `absent` service token is judged against a baseline merged with `$addToSet`, `--no-remove` is in the apt argv, and a manual rollback of a rollout job is refused with 409 after the tenant check. The Cancel-of-a-running-rollout path (compare-and-set stamp, `halt` guarded by `cancelRequested`, `finish_cancel` shared with the halted path) is consistent, and I found no way for it to revert or halt anything.

No new BLOCKER was found. One candidate was traced and rejected: the `sent` plus `expiresAt` rule in `inflight.instruction_outcome` does not misjudge a running install in the normal case, because the Rust agent answers `accepted` for `install_patches` straight after the poll (instructions.rs:542), so a running install reads ACCEPTED. It stays a WARNING (WR-26) because that `accepted` post is sent with a single attempt.

The warnings below are one incomplete prior fix (WR-25 reopens WR-15), three in-flight settle defects (WR-26..WR-28), three Cancel gaps (WR-29..WR-31), and one wrong promise in the 409 text (WR-32).

Known deferred items were not re-raised: WR-05, reboot rows stuck dispatching, a `not_approved` host staying waiting after Resume, and the "This rollout is not halted." sentence for Cancel of a finished rollout.

## Warnings

### WR-25: A revert still re-installs a removed package that left its config behind (reopens WR-15)

**File:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs:379-392` (`installed_version`), used by the new `revert_precheck` at `:479-482` and the legacy check at `:513-516`
**Issue:** The WR-15 fix treats `installed_version(...) == None` as "package is gone". On apt, `dpkg-query -W -f=${Version} <pkg>` also succeeds for a package in the `rc` state (removed, config files kept), which is the state `apt remove` leaves. So `installed_version` returns the old version, `revert_precheck` returns None, and the code goes on to `apt-get install pkg=<previous>`. That reinstalls software the administrator removed, which is exactly what WR-15 said must never happen ("a revert never adds software"). The new unit test only covers the `None` input, so it cannot catch this. `rpm -q` is not affected.
**Fix:** Make the installed check status-aware on apt, for example `dpkg-query -W -f=${db:Status-Status}\t${Version} <pkg>`, and return `Some(version)` only when the status is `installed`. Add a test with an `rc` line fed to the parser. Keep `installed_version` for the pre-upgrade read, but use the status-aware helper in `revert_precheck` and the legacy path.

### WR-26: An expired `sent` instruction is judged "not delivered" although the agent already fetched it

**File:** `backend/autonomous_ops/rollout/inflight.py:63-65`, consumed at `settle.py:128-137` and `settle.py:184-192`
**Issue:** `_UNSTARTED_STATES = ("pending", "sent")` with `expires <= now` returns `not_delivered`. The poll route sets `sent` when the agent fetches the instruction (`agent_tasks_endpoints.py:61`), so `sent` means the agent has it. The agent reports `accepted` with `attempts = 1` (`instruction_report.rs:59`), so one lost post leaves a running install at `sent`. When the install window closes (`expiresAt` is the window close), settle then:
- fails the ledger row `rollout_not_delivered`,
- closes the job as Failed (the computer reads free and can be claimed by another rollout),
- resets the host to `waiting`, so the next window installs again.

The first install keeps running. The second job then reports "already newest", so the per-job revert record (keyed by the first job id) is not used by the job the platform follows, and a later revert answers "no record". Only `pending` is provably undelivered. The module docstring ("still pending/sent after its own expiresAt... never had the step") states this wrongly.
**Fix:** Treat only `pending` as undelivered after `expiresAt`. Treat `sent` as in flight and let `RESULT_DEADLINE` (measured from `sent_at`) decide. Update the docstring and add a `sent`-after-expiry test case.

### WR-27: A queued revert that was never fetched is declared "did not answer" after 6 hours and the instruction is left live

**File:** `backend/autonomous_ops/rollout/inflight.py:66-69` and `:39`, `backend/autonomous_ops/rollout/revert.py:236-253`
**Issue:** Undo instructions carry no `expiresAt` (revert.py module docstring). For a revert that is still `pending` because the agent is offline, `instruction_outcome` falls through to `began + RESULT_DEADLINE <= now` and returns `no_result`. `_row_outcome` then marks the host `not_reverted` ("the computer did not answer. The patch is still installed"), closes the revert job, and unblocks Resume. The `agent_instructions` document stays `pending`. When the laptop comes back it fetches and executes the revert, so the patch is removed silently after the platform said it was not reverted and possibly after the rollout was resumed. Two related defects make this worse:
- `delivered_at` is read, but the live poll route that the Rust agent uses writes `sent_at` (`agent_tasks_endpoints.py:61`). `delivered_at` is only written by `deployment_result_endpoints.py`, which this agent does not use. The 6 hours therefore run from `created_at` or the dispatch time, not from delivery.
- `test_patch_rollout_gap_inflight.py` models delivery with `delivered_at`, so it does not exercise the production field.

**Fix:** Do not count the deadline for a `pending` instruction. Read `sent_at` (and the ACCEPTED time) as the start of the clock. When `_row_outcome`, `cancelling._abandon` or the install settle abandon an instruction, set its status to `cancelled` so a late fetch cannot run it. Change the tests to use `sent_at`.

### WR-28: A revert the agent answered FAILURE is reported as "the computer did not answer"

**File:** `backend/autonomous_ops/rollout/revert.py:244-253`
**Issue:** `_row_outcome` sends `failed` and `no_result` through one branch. Only statuses in `NOT_DELIVERED_STATES` get `not_delivered`; both of the others get `reason: "no_answer"`. For an instruction the agent answered with FAILURE or error, the card reads "Not reverted: the computer did not answer. The patch is still installed." The install settle path keeps the agent's own words for a failure (`inflight.failure_words`); the revert path discards them.
**Fix:** Map `failed` to its own reason code (for example `agent_failed`, with a `NOT_REVERTED_REASON` entry), or carry `failure_words(task, ...)` into the recorded reason. Keep `no_answer` for `no_result` only.

### WR-29: Cancel closes unfetched instructions with the "a check after the install did not pass" text

**File:** `backend/autonomous_ops/rollout/lifecycle.py:123-138` (called from `_request_running` at `:613-614`)
**Issue:** `_end_unfetched` hard-codes `reasonCode="rollout_halted"` and the text "The rollout stopped here because a check after the install did not pass." (`messages.REASON_TEXT`). It is now also run for a person's Cancel of a running rollout, where no check failed. Those Activity rows then give a false reason. The code also feeds `BREAKER_IGNORED` and `cards._ENDED_BY_ROLLOUT` keyed on `rollout_halted`, so a different code needs entries in both.
**Fix:** Give `_end_unfetched` a `code` argument. Cancel passes `rollout_closed` (already ignored by cards and the breaker, and its text says "closed before this step ran"), halt keeps `rollout_halted`.

### WR-30: A rollout whose Cancel is settling shows no sign of it

**File:** `backend/autonomous_ops/rollout/views.py:340-364`, `components/patchRollouts/RolloutCard.tsx:151-153`, `services/patchRollouts/types.ts`
**Issue:** `rollout_card` uses `cancelRequested` only to switch `canCancel` and `canResume` to false and `cancelNote` to null. The payload carries no cancelling flag and no "who/when". After the user confirms Cancel, the toast says "Cancelling...", but the card refreshes as an ordinary running rollout with no buttons and no explanation, for up to `RESULT_DEADLINE` (6 hours). A second person sees a running rollout with the action missing. A second Cancel by API gets 409, but the UI cannot explain it.
**Fix:** Add `cancelling: bool` (and the requester and time) to the card payload and type. Render a notice in `RolloutCard` ("Cancel requested by X. It ends when the installs in progress finish."). Show it in the status chip too.

### WR-31: A controller pass that loaded the rollout before the Cancel stamp can still decide and send

**File:** `backend/autonomous_ops/rollout/controller.py:300-330` (the rollout document is read once by `active_rollouts`; `cancelRequested` is checked once at `:306`), `installs.py:127-170`, `installs.py:217-235`
**Issue:** The Cancel stamp is a compare-and-set in Mongo, but the controller works from the document it loaded at the top of `_tenant`. `settle.settle`, `reboots.settle` and then `dispatch_approved` plus `_ring` (canary decide and send, raise_ring) run on that stale copy. A Cancel that lands after the load and before `_ring` still gets new canary installs sent, because `canary_auto` and `_send` never re-check the stamp. (Approved rows are protected: `_close_open_rows` expires them and the claim is a compare-and-set on the row.) This contradicts "Cancelling stops new installs now" (the dialog text) and D-16. The window is a tick's duration, which is long when a tenant has many hosts.
**Fix:** Before creating a row or an instruction in `canary_auto`/`_send`/`raise_ring`, re-read `cancelRequested` (a cheap projection of the rollout document) and return without side effects when it is set. Alternatively add a `cancelRequested: {$exists: False}` condition to the update that marks a host `installing`, and abandon the row when that matches nothing.

### WR-32: The 409 for a manual rollback tells the user to "Revert it from Rollouts", which only works for a halted rollout

**File:** `backend/patch_core_endpoints.py:254` (`ROLLOUT_OWNED_JOB_DETAIL`) and `:278-282`
**Issue:** `revert.tick` runs only while the rollout is `halted`, and `settle_cancelled` only settles a revert that was already running. For a rollout that completed or was cancelled, no screen can revert its jobs, and the new guard also blocks the Patch Jobs rollback. The message promises an action that does not exist for these states. The refusal is deliberate (WR-10), so only the wording and the dead end are at fault.
**Fix:** Say what is true, for example "This job belongs to a rollout. A rollout's patches are put back only while the rollout is halted." Decide whether a finished rollout needs a supported way back and record it as a decision. If not, keep the wording honest.

## Info

### IN-24: `masked` and `not-found` units both read `absent`, including a running masked unit

**File:** `agent-install/omni-agent-rs/src/capabilities/service_watch.rs:68-71`
**Issue:** `classify_systemd` returns `Absent` for any `LoadState=masked` before reading `ActiveState`. A unit masked at runtime (`systemctl mask --runtime`) can still be `active`. It would read "absent", and if the baseline also read absent it would be dropped from the checked list although it is running (and a crash of it would not be caught).
**Fix:** Return `Absent` for `not-found` always, and for `masked` only when `ActiveState` is `inactive`. Add a test line with `LoadState=masked` and `ActiveState=active`.

### IN-25: A watched name that is in neither baseline list keeps the services signal at "no data" for good

**File:** `backend/autonomous_ops/rollout/signals.py:88-100`
**Issue:** The baseline holds only the services the agent reported at send time. If the tenant adds a service to the watched list after that, and the service is reported `absent` at the check, the name is in neither `servicesPresentBefore` nor `servicesAbsentBefore` and `missing_baseline` forces `None`. Nothing can ever fill the baseline for that host and rollout. The same result follows when `record_service_baseline` fails (logged only). Whether this stalls the ring depends on how the gate treats no-data after the soak, which was not traced here.
**Fix:** After the soak, treat a name that is absent now and was never present in any recorded baseline as "not installed" only when the baseline was recorded at all. Otherwise surface a distinct "baseline missing" note instead of a silent no-data state.

### IN-26: `save_to` leaves a stale temporary file on failure and does not sync the directory

**File:** `agent-install/omni-agent-rs/src/capabilities/patch_state.rs:141-151`
**Issue:** A failed `write_all`, `sync_all` or `rename` leaves `patch_state.json.tmp` behind, and the rename is not followed by a directory sync, so a power loss right after the first per-package save can still lose the record WR-14 meant to protect. The risk is small but real now that the file is saved per package.
**Fix:** Remove the temporary file on error, and on Unix open the parent directory and call `sync_all` after the rename.

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
