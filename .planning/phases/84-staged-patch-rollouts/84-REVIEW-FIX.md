---
phase: 84-staged-patch-rollouts
fixed_at: 2026-11-07T13:10:00Z
review_path: .planning/phases/84-staged-patch-rollouts/84-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 84: Code Review Fix Report

**Fixed at:** 2026-11-07
**Source review:** .planning/phases/84-staged-patch-rollouts/84-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (WR-25..WR-32; 0 critical; IN-24..IN-26 out of scope)
- Fixed: 8
- Skipped: 0

No push, deploy, restart, UI publish, agent publish or version bump was done. Edits and commits were made in the main checkout (`workflow.use_worktrees` is `false`), staged by explicit path only. The user's other uncommitted work was not touched.

WR-26 and WR-27 share one commit because both rewrite `instruction_outcome` in `inflight.py`.

## Fixed Issues

### WR-25: A revert still re-installs a removed package that left its config behind

**Files modified:** `agent-install/omni-agent-rs/src/capabilities/patch_installer.rs`, `agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs`
**Commit:** ca22a0dfb
**Applied fix:** The apt branch of `installed_version` now runs `dpkg-query -W -f='${db:Status-Status}\t${Version}'`. The new `parse_dpkg_installed` in `patch_reversible.rs` returns a version only for the `installed` state, so `rc` / `config-files` reads as not installed. `revert_precheck` and the legacy rollback path both go through `installed_version`, so both are covered. rpm is unchanged. A new parser test feeds `config-files`, `not-installed`, empty and mixed-architecture lines.
**Deviation from the note:** I made `installed_version` itself status-aware instead of adding a second helper. The pre-upgrade read in `install` uses it too, so a package in `rc` is now reported "not installed" there, which is correct. `patch_installer.rs` stays at 538 lines, no growth.
**Orchestrator follow-up (b01a8aee2):** the format had no trailing newline, so dpkg ran a package installed for two architectures together on one line and the mixed-architecture case in the new test could not happen for real. The format now ends with `\n`. Checked against the real `dpkg-query` on this VM; `cargo test --lib patch_` 39 passed after the change.

### WR-26: An expired `sent` instruction is judged "not delivered" although the agent already fetched it

**Files modified:** `backend/autonomous_ops/rollout/inflight.py` (with WR-27)
**Commit:** a616babe1
**Applied fix:** After `expiresAt`, only a `pending` instruction is `not_delivered`. A `sent` or `accepted` one stays in flight and `RESULT_DEADLINE` decides. The module docstring is corrected. Both callers in `settle.py` (`_settle_auto` and the approval-line path in `_settle_lines`) take the outcome from `instruction_outcome`, so both get the new rule with no further change. New tests: `sent` after expiry keeps the host installing and the job In Progress, then fails `rollout_no_result` six hours after `sent_at`; a pure unit test covers the outcome table.
**Status:** fixed: requires human verification (logic change in the settle rule).

### WR-27: A queued revert that was never fetched is declared "did not answer" after 6 hours and the instruction is left live

**Files modified:** `backend/autonomous_ops/rollout/inflight.py`, `revert.py`, `settle.py`, `cancelling.py`, `backend/tests/test_patch_rollout_gap_inflight.py`, `backend/tests/test_patch_rollout_cancel_running.py`
**Commit:** a616babe1
**Applied fix:**
- Checked against the source first. The poll route (`agent_tasks_endpoints.py`) selects only `status: "pending"` and writes `sent_at` (not `delivered_at`) when it marks `sent`. The result route writes `updated_at` on an ACCEPTED post. `cancelled` is already in `NOT_DELIVERED_STATES` and in the reboots vocabulary.
- The deadline clock no longer runs for `pending` (an undo has no `expiresAt`, so an offline computer keeps waiting). The clock starts at the accept time (`updated_at`, when status is accepted), else `sent_at`, else the dispatch time, else `created_at`. `delivered_at` is no longer read.
- New `inflight.cancel_unfetched`: a compare-and-set that turns `pending` into `cancelled` (an instruction fetched in the meantime is left alone). It is called by `revert._row_outcome`, `cancelling._abandon` and both install-settle `not_delivered` paths. Module docstrings that said "never writes the queue" now name this one write.
- Tests moved from `delivered_at` to `sent_at`. New tests: a never-fetched revert still reads reverting a day later and stays `pending`; a fetched revert is timed from the poll; only a `pending` instruction is cancelled (also across tenants); an expired unread install instruction ends up `cancelled`.
**Status:** fixed: requires human verification.
**Orchestrator follow-up (5a429902f):** the wider backend run caught a GATE-03 regression: `test_autonomous_ops_structural.py::test_queue_writers_are_grandfathered` refused `rollout/inflight.py` as a new agent-queue writer. `cancel_unfetched` moved to `autonomous_ops/delivery.py` (a package queue module, beside the other hold-backs), the four callers and the test now use `delivery.cancel_unfetched`, and `inflight.py` is read-only on the queue again. No allowlist was widened. The Phase 81 re-verification found the same failure.
**Behaviour to know:** a revert queued for a computer that stays offline now keeps the host in `reverting` and Resume blocked until the computer returns or a person cancels the rollout. This is what the review asked for, and it is more honest than "did not answer".

### WR-31: A controller pass that loaded the rollout before the Cancel stamp can still decide and send

**Files modified:** `backend/autonomous_ops/rollout/installs.py`, `backend/tests/test_patch_rollout_gap_inflight.py`
**Commit:** bcc21ac71
**Applied fix:** New `installs.cancel_stamped` re-reads only `cancelRequested` from the rollout document (a read fault reads as not stamped, and `halt` stays a compare-and-set). It is checked per host before any row is created in `canary_auto`, once before `raise_line` in `raise_ring`, and in `_send` after the row is claimed and before the job and instruction are written. In `_send` a stamped rollout fails the row `rollout_closed` and sends nothing. Three tests load a stale copy of the rollout, stamp the Cancel afterwards and check no row, instruction or job appears (canary, a later ring, and a Cancel between claim and send). The first and third were confirmed to fail with the check disabled.
**Status:** fixed: requires human verification.
**Residual:** the window between the last check and `gate.execute` inside `_send` is not zero; closing it fully would need a transaction. It is a few milliseconds instead of a whole tick.

### WR-28: A revert the agent answered FAILURE is reported as "the computer did not answer"

**Files modified:** `backend/autonomous_ops/rollout/messages.py`, `backend/autonomous_ops/rollout/revert.py`, `backend/tests/test_patch_rollout_gap_inflight.py`, `backend/tests/test_patch_rollout_messages.py`
**Commit:** a886c0012
**Applied fix:** New reason code `agent_failed` ("the computer reported an error") in `NOT_REVERTED_REASON`, so the card reads "Not reverted: the computer reported an error. The patch is still installed." `no_answer` is kept for `no_result` (and an expired pending). The closed revert job's status line now uses the matching sentence. The existing parametrised test now expects `agent_failed` for the FAILURE case and the pin test lists the new code.

### WR-29: Cancel closes unfetched instructions with the "a check after the install did not pass" text

**Files modified:** `backend/autonomous_ops/rollout/lifecycle.py`, `backend/autonomous_ops/ledger.py`, `backend/tests/test_patch_rollout_cancel_running.py`
**Commit:** 44b6e65cc
**Applied fix:** `_end_unfetched` takes a `code` argument (default `rollout_halted`); `_request_running` passes `rollout_closed`. The job-closing text follows the code too.
**Extra change beyond the note:** the review said `rollout_closed` is "already ignored by the breaker". It was not: `ledger.BREAKER_IGNORED` lacked it, so a row ended by a Cancel would have counted toward the circuit breaker. I added `rollout_closed` to `BREAKER_IGNORED` (with a comment). The same fix covers the `rollout_closed` rows `cancelling._end_unsent` and the WR-31 guard already write. `cards._ENDED_BY_ROLLOUT` already had it. The Cancel test now asserts the code, the text and the breaker entry.

### WR-30: A rollout whose Cancel is settling shows no sign of it

**Files modified:** `backend/autonomous_ops/rollout/views.py`, `backend/autonomous_ops/rollout/messages.py`, `services/patchRollouts/types.ts`, `components/patchRollouts/RolloutCard.tsx`, `components/patchRollouts/rolloutCopy.ts`, `src/__tests__/_patchRolloutFixtures.ts`, `src/__tests__/PatchRolloutCancelRunning.test.tsx`, `backend/tests/test_patch_rollout_views_cancel.py`
**Commit:** 58a1fcf25
**Applied fix:** The card payload gains `cancelling`, `cancelRequestedBy`, `cancelRequestedAt` and a server-written `cancellingNote` ("Cancel requested by Ann. It ends when the installs in progress finish."; without a recorded name: "Cancel requested. It ends ..."). `RolloutCard` renders the note (role status) and swaps the Running chip for a Cancelling chip. Fixtures, types, a backend view test (named, nameless, plain) and two vitest cases were added. The stored `status` is unchanged (still `running`), so listing and sorting are not affected.

### WR-32: The 409 for a manual rollback tells the user to "Revert it from Rollouts"

**Files modified:** `backend/patch_core_endpoints.py`, `backend/tests/test_patch_rollout_legacy_fence.py`
**Commit:** f8ffdd7d5
**Applied fix:** Wording only. The 409 now reads "This job belongs to a rollout. A rollout's patches are put back only while the rollout is halted." The pinned test string was updated and a code comment points at the open decision below. No new revert path was built.

## Open decisions for the user

- **WR-32: a finished rollout has no way back.** Once a rollout is completed or cancelled, no screen can revert its jobs, and the legacy Patch Jobs rollback is blocked for them too. The message is now honest about it. Whether a completed or cancelled rollout needs a supported "put these patches back" path is a product decision and was not built.
- **WR-27 side effect:** a halted rollout whose revert target is offline stays in `reverting` (Resume blocked) until the computer comes back or the rollout is cancelled. If you would rather end it after some long bound, that bound needs a value; the old 6 hours from row creation was wrong because it ran while the computer had not been asked yet.

## Verification

All Python and UI runs were in the main checkout. The backend runs used the private test mongod on 127.0.0.1:27998; the live MongoDB was not touched. The Rust runs used the nodebug recipe in the main checkout, which stays on disk under `agent-install/omni-agent-rs/target/nodebug`.

| Gate | Result |
|------|--------|
| `pytest backend/tests/test_patch_rollout_*.py test_autonomous_ops_copy.py test_autonomous_ops_breaker.py` (final run, after all commits) | 515 passed |
| Earlier `test_patch_rollout_*.py` alone (after WR-26/27) | 443 passed (the set grew by tests added later) |
| `test_patch_rollout_gap_inflight.py` (baseline 15) | 24 passed (included in the 515 run) |
| Copy tests: `test_autonomous_ops_copy.py`; `rolloutCopy.test.ts`, `autonomousOpsCopy.test.ts` | 41 passed; included in the vitest count below |
| `npx vitest run src/__tests__/PatchRollout` + the two copy tests | 10 files, 307 tests passed |
| `npx tsc --noEmit` | clean |
| `cargo test --lib patch_` (nodebug recipe), after WR-25 | 39 passed (baseline 38, plus the new parser test) |
| `cargo check --target x86_64-pc-windows-gnu --lib` | finished, no new warning for the new function |

The fixer did not re-run the full vitest suite or the wider backend set. The orchestrator ran them afterwards:

| Gate (orchestrator, final code 661a767f3) | Result |
|------|--------|
| `npx vitest run src/__tests__` | 108 files, 1,606 passed (baseline 1,604, plus the two WR-30 cases) |
| `cargo test --lib patch_` after b01a8aee2 | 39 passed |
| `pytest test_autonomous_ops_*.py test_patch_*.py test_maintenance_windows.py`, private mongod | 1,531 passed, 0 failed (9 min 26 s) |

The first wider run, on the fixer's code, failed 3 of 1,531:
- `test_queue_writers_are_grandfathered` was a real GATE-03 regression from WR-27. It was fixed in 5a429902f; see WR-27.
- Two approve-line tests, in `test_patch_rollout_gap_lines.py` and `test_patch_rollout_revert.py`, read "window" instead of "now". The approval dispatcher (`fn(db, row, approver)`) sends on the wall clock, while these tests seed the agent's `lastSeen` at the import-time `NOW`. With the autonomous_ops files running first, they ran more than five minutes after collection, so the computer read offline.
  - This predates this fix round: 84-29 ran the rollout files first.
  - It was reproduced with `NOW` ten minutes old and fixed in the tests (661a767f3) by refreshing `lastSeen` before the approve.

File sizes: `patch_installer.rs` 538 (unchanged), `test_patch_rollout_gap_inflight.py` 497, `lifecycle.py` 452, `views.py` 451, `installs.py` 258.

---

_Fixed: 2026-11-07_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
