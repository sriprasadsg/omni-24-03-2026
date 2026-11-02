---
phase: 83-autonomous-security-response
plan: 16
subsystem: autonomous-ops-followups
tags: [autonomous-ops, quarantine, kill-process, follow-ups, undo, verify, reconciler, mongo]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-11 automatic quarantine rows, incidentId on acting rows, the sweep's signal memory"
  - phase: 83-autonomous-security-response
    provides: "83-09 kill_process / quarantine_file agent contract (processes, expected_exe, quarantine_id, still_running)"
provides:
  - autonomous_ops/followups.py (after)
  - one kill_process approval line for a locked file (mode retry) or a moved file whose process runs (mode kill_only)
  - one automatic quarantine retry after an approved kill, with parentActionId, then a stop
  - verify.settle_undo and row field undoFailed; row field stillRunning
  - reconciler scan of recently undone security_response rows
affects: [83-17, 83-18, 83-19, 83-20]

actuals:
  tokens: 11700
  tasks: 2
  commits: 4
plan_head_before: 128b4eb8d4ef989db8c7666784d25e3056fcd5ac
plan_head_after: 237ccb21d779348c7fbef73084446607d14fdff1

tech-stack:
  added: []
  patterns:
    - "The chain is two ledger rows linked by reason.inputs.chain and reason.inputs.parentActionId, never one multi-step row"
    - "A follow-up is decided through gate.decide only; the kill line is an approval card the module never sends"
    - "A person's undo is provisional: the row is marked undone at click time and given back its Done state if the host's answer says it failed"

key-files:
  created:
    - backend/autonomous_ops/followups.py
    - backend/tests/test_autonomous_ops_followups.py
    - backend/tests/test_autonomous_ops_verify.py
  modified:
    - backend/autonomous_ops/verify.py
    - backend/autonomous_ops/reconciler.py
    - backend/autonomous_ops/response_views.py

key-decisions:
  - "A kill row's reason text reuses existing sentences: REASON_TEXT['locked'] for mode retry, NOTICES['kill_only'] for mode kill_only. No new sentence was written."
  - "A retry never opens a card, whatever it reports, and its settling writes a hold into the sweep's signal memory (outcome blocked for a finished retry, failed with holdUntil of 24 h otherwise) so the sweep does not restart the chain an hour later."
  - "A kill card a person denied or let expire is not raised again for 24 hours (the sweep retries a failed quarantine hourly, which would otherwise ask again every hour)."
  - "The retry carries allow_protected only when the original quarantine row held it; a tenant playbook that raised the original to a card does not raise the retry, because approving the kill line is the approval for the retry."
  - "A failed undo returns the row to verified (executed when it has no verifiedAt) with the undo block reset; reasonText is left alone and the Result column leads with the undo_failed sentence."

patterns-established:
  - "Row field stillRunning (list of {pid, name, start_time}) is what the Activity row words; result.still_running keeps what the host reported. Views prefer stillRunning when the key exists."

requirements-completed: []

coverage:
  - id: D1
    description: "A quarantine that failed locked with listed processes ends failed/locked and adds exactly one kill_process card (mode retry) in the same incident; params are {target, expected_exe, processes[{pid,start_time}]} with the contract's pid and start_time unchanged and no quarantine_id; no kill instruction is written"
    requirement: "RESP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_followups.py#test_a_locked_file_becomes_one_kill_card_and_nothing_is_ended"
        status: pass
    human_judgment: false
  - id: D2
    description: "Approving the retry card and replaying kill_done or kill_gone leaves the kill verified and adds one automatic quarantine_file row with parentActionId, dedupe suffix |retry and one instruction; a retry locked again, or moved with the process still running, adds no card and no third try, and the sweep holds the finding"
    requirement: "RESP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_followups.py#test_approving_the_kill_then_retries_the_quarantine_once"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_followups.py#test_a_retry_that_is_locked_again_stops_with_no_second_card_and_no_third_try"
        status: pass
    human_judgment: false
  - id: D3
    description: "A moved file whose process runs leaves the quarantine Done with stillRunning, adds one kill-only card whose params also hold the quarantine's first instruction id as quarantine_id; the Done row's result ends with the still-running sentence; the kill reaching verified clears stillRunning and the sentence; kill_survived and kill_refused leave it and add no retry"
    requirement: "RESP-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_followups.py#test_a_moved_file_whose_process_runs_stays_done_and_adds_a_kill_only_card"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_followups.py#test_a_kill_only_card_that_failed_leaves_the_quarantine_saying_it_runs"
        status: pass
    human_judgment: false
  - id: D4
    description: "A kill row reaches verified only when the agent reports the named processes gone: kill_survived ends failed/verify_failed and kill_refused ends refused/agent_refused, neither adds a retry (PROH-83-15: no process is ended without a person, the module sends no kill)"
    requirement: "RESP-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_followups.py#test_a_kill_that_did_not_end_the_process_adds_no_retry"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_followups.py#test_the_follow_up_module_writes_no_instruction_and_never_sends_a_kill"
        status: pass
    human_judgment: false
  - id: D5
    description: "An undo instruction that failed (error or refused answer) or never answered within the no-result bound returns the row to Done with undoFailed {at, reason}, the undo block reset and Undo offered again; a confirmed undo stays Undone; a failed undo sends no further instruction and writes no row (RESP-06)"
    requirement: "RESP-06"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_verify.py#test_an_undo_the_host_could_not_do_returns_the_row_to_done_with_the_failure"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_verify.py#test_resp_06_a_failed_verify_writes_no_compensation_row_or_instruction"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-11-02
status: complete
---

# Phase 83 Plan 16: Kill cards for a running file, one bounded retry, and honest undo

**A quarantine that fails because the file is in use, or that moves a file whose process keeps running, gives a person one kill card on the same incident; approving it ends only the listed processes and retries the quarantine once, and an undo the host did not confirm no longer reads as done. Nothing here ends a process by itself.**

## Performance

- **Duration:** about 12 min
- **Tasks:** 2 (both TDD)
- **Commits:** 4 (2 test, 2 feat), measured from `128b4eb8d` to `237ccb21d`
- **Line counts:** `followups.py` 196, `reconciler.py` 237, `verify.py` 194, `response_views.py` 247 (limit 500)
- **Used the cargo recipe:** no, this plan touches no Rust.

## Task Commits

| Task | Commit | Type |
|------|--------|------|
| 1 RED: 20 follow-up tests | `9a3665fd1` | test |
| 1 followups.py, stillRunning in settle, reconciler hook, still-running wording | `295584ed8` | feat |
| 2 RED: 11 undo and verify tests | `769b2bef0` | test |
| 2 settle_undo, reconciler undo scan, undo-failed wording | `237ccb21d` | feat |

## Chain row states, for 83-18 to fold

Locked (D-06):

| Row | Command | Fields to read | State path |
|---|---|---|---|
| Q (original quarantine) | `quarantine_file` | `state failed`, `reasonCode locked` | dispatching -> failed |
| K (kill card) | `kill_process` | `reason.inputs.chain {mode: "retry", quarantineActionId, path, sha256, process {pid, name, start_time}}`, same `reason.inputs.incidentId` as Q, `params {target, expected_exe, processes [{pid, start_time}]}`, no `quarantine_id` | awaiting_approval -> approved -> dispatching -> verified (kill_done, kill_gone), failed/verify_failed (kill_survived), refused/agent_refused (kill_refused), denied/expired |
| R (retry) | `quarantine_file` | `reason.inputs.parentActionId` = K id, `dedupeKey` ends `|retry`, `autoDispatched true`, `params {path, sha256[, allow_protected]}` | dispatching -> verified, or failed (even locked again: no card follows) |

Moved but running (D-27): Q stays `verified` with `stillRunning` (list); K has `chain.mode "kill_only"`, `params.quarantine_id` = Q's first instruction id; no R. K verified sets Q's `stillRunning` to `[]`.

Step list for the fold: step 1 is K's state, step 2 is the row with `parentActionId == K.id` (absent until K executed). If R is failed, the UI-SPEC wording applies ("The process was ended but the file is still in place"). K's own `target` column holds the agent id (`display_target` finds no path or address in its params), so the card should show `chain.process.name` and `chain.path`.

## What was built

- **followups.after(db, tenant, row, doc, now=None).** For a `security_response` quarantine row without `parentActionId`: failed `locked` with a non-empty `still_running` in the instruction's stored result, or verified with `stillRunning`, calls `gate.decide` for one `kill_process` (dedupe key `{tenant}|sweep|kill_process|{agent}|{sha256}`, so the two modes in one pass stay one card). For a kill row at executed or verified in mode retry it decides `quarantine_file` again (key `...|{sha256}|retry`, `parentActionId` set) and sends it when the gate returns dispatching. A kill row at failed or refused does nothing.
- **verify.settle** stores `stillRunning` (and `result.still_running`) when the host's body carries the list; `process_entries` is the shared bounded reader.
- **reconciler** calls `_follow_up` after each settled `security_response` row (success branch after `settle`, failure branch after the transition), in its own try.
- **verify.settle_undo** and the reconciler's `_reconcile_undos`: rows `undone` by a person (undo scan window = the no-result bound plus one hour) whose last instruction failed, or got no answer by the bound, go back to `verified` (`executed` when no `verifiedAt`) with `undoFailed {at, reason}` and `undo {available true, undoneAt null, undoneBy null}`.
- **response_views**: the still-running sentence follows `stillRunning`; a row with `undoFailed` leads its Result with the existing `undo_failed` sentence.

## Deviations from Plan

**1. [Rule 2 - Missing] A denied or expired kill card is not raised again for 24 hours**
- **Found during:** Task 1. The sweep retries a failed quarantine after 1 hour (83-05), so each hour a locked file would produce a fresh kill card after a person said no.
- **Fix:** `_declined_recently` in `followups.py` skips a card whose key was denied or expired in the last 24 hours. Test: `test_a_denied_kill_card_adds_nothing_and_is_not_asked_again`.
- **Commit:** `295584ed8`

**2. [Rule 2 - Missing] The sweep is told to hold the finding after a retry settles**
- **Found during:** Task 1. The plan says a second failure stops with "no further automatic try", but the sweep would decide the same file again an hour after the failed retry (its signal memory pointed at the first failed row).
- **Fix:** `_hold_finding` writes the sweep's signal memory for the retry row: outcome `blocked` when it finished, outcome `failed` with `holdUntil` 24 hours out otherwise. After 24 hours the sweep may try again, as after any failed quarantine. Mutation-checked: without it `test_a_retry_that_is_locked_again_stops_...` fails.
- **Commit:** `295584ed8`

**3. [Rule 3 - Scope note] `backend/tests/test_autonomous_ops_verify.py` did not exist**; the plan listed it under files_modified. It is new in this plan (11 tests). The 83-01 verify cases (ok true and false) are tested in `test_autonomous_ops_block_contract.py`, which still passes.

**4. [Choice] The undo-failed row keeps its `reasonText`.** Action step 1 of Task 2 says "the original undo block and reasonText"; keeping the original why-sentence matters more than replacing it, so the failure is worded in the Result column instead (see below).

## RED runs, stated honestly

- **Task 1:** all 20 tests failed at collection with `ImportError: cannot import name 'followups'`. That is an import error, not a behaviour assertion. Two mutation runs afterwards (guard on `parentActionId` removed; hold removed) failed the tests that should fail.
- **Task 2:** 4 of 11 failed on assertions (the row stayed `undone`). The other 7 (confirmed undo, other dispatchers, RESP-06, no-compensation cases) passed before the change, so they guard the new code and did not drive it.

## Verification

- Task 1 verify command, widened: `test_autonomous_ops_followups.py`, `_reconciler.py`, `_block_contract.py`, `_response_rows.py`, `_copy.py`, `_structural.py`: 169 passed.
- Task 2 verify files (`_verify.py`, `_reconciler.py`, `_breaker.py`) pass inside the full run below.
- All of `backend/tests/test_autonomous_ops_*.py` plus `test_catalogue_slice_autonomous_ops.py`, `test_remediation_playbook.py` and `test_autonomous_remediation_loop.py` on the private mongod (27998): **950 passed**, none skipped, 350 s. `test_ledger_ratchets` was not in this run.
- Acceptance greps: `kill_only` 3, `quarantine_id` 4, `start_time` 3, `agent_instructions` 0 in `followups.py`; `undoFailed` 2 in `verify.py`.

## Not read, or read in part

- `83-RESEARCH.md`: only Pattern 4 and the incident paragraph, by grep. `83-UI-SPEC.md`: the kill-then-quarantine and kill-only card paragraphs and the copy table by grep, not section 2a or section 3 in full.
- `83-CONTEXT.md`: the decisions section (D-01 to D-28 and the research defaults) in full; canonical references and code insights not read.
- `STATE.md`: frontmatter and from line 745. `83-11-SUMMARY.md` read in full; other plan summaries not read.
- `agent-install/omni-agent-rs`: read only `quarantine.rs` `locked_body` (it carries `still_running`) and the head of `process_kill.rs` (parameter names).

## User-visible sentences

No new sentence was written. Reused unchanged: `REASON_TEXT["locked"]` ("The file is in use and could not be moved, so a person has to decide.") is the kill-then-quarantine card's reason; `NOTICES["kill_only"]` ("The file was moved to quarantine, but its process is still running. Approving ends the process.") is the kill-only card's reason (it also reads as an instruction, so check the card); `REASON_TEXT["undo_failed"]` now leads the Result of a row with `undoFailed`, followed by the usual result, e.g. "The host did not confirm the undo, so the action may still be in place. Moved /tmp/x to quarantine. ...". The user should read how that pair reads.

## Facts for later plans

- **83-17 and 83-18:** `verify.settle` still stores nothing from the body except `still_running` (and `stillRunning`); `healthy_after` is not stored yet, 83-17 must copy it. The Q row's `result` after a locked failure is only `{instructionId, instructionStatus}`: the process list is in K's `params.processes`, not on Q.
- **83-18:** an `undone` row can come back to `verified`/`executed` with `undoFailed`; the list route should show it as Done with Undo available. `canUndo` already works from the state.
- **Dormant host:** if the host cannot carry `kill_process` (capability or `kill_process_exe` token missing), `gate.decide` refuses unrecorded and no kill card exists, yet a Done quarantine with `stillRunning` still says "See Needs your decision". Not handled here.
- **Lost follow-up:** `followups.after` runs once, right after the row settles; there is no catch-up scan, so a crash between the transition and the follow-up loses the card (the dedupe key makes a manual rerun safe).
- **Host cap:** the retry is decided through the gate (rate limit, breaker, level) but the sweep's per-host cap of 3 does not apply to it.
- **Retry with moved-but-running:** a retry that moves the file while a process still runs adds no card (the chain is over) and its Done row does not carry the still-running sentence (it would point at a card that does not exist).
- **Requirements** RESP-03, RESP-05 and RESP-06 are not ticked: each spans plans still to come (the cards, restart, isolation).

## Threat Flags

None. No new endpoint or file access. T-83-59 (a forged locked result can only open a card, bound by the listed pid and start_time, `expected_exe` and the stored image, list capped by `bounded_result`), T-83-60 (one retry, `parentActionId` stops it, plus the day-long hold) and T-83-61 (undo returns to its real state) are implemented as the threat model describes.

## Known Stubs

None.

## Self-Check: PASSED

Files exist (`followups.py`, `test_autonomous_ops_followups.py`, `test_autonomous_ops_verify.py`); commits `9a3665fd1`, `295584ed8`, `769b2bef0`, `237ccb21d` are ancestors of HEAD.
