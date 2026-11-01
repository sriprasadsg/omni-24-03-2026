---
phase: 83-autonomous-security-response
plan: 09
subsystem: agent
tags: [rust, quarantine, process-kill, autonomous-ops, agent-contract]
status: complete

requires:
  - phase: 83-autonomous-security-response
    provides: "83-02 response_state.rs Store (lock, quarantine_index) and the shared contract; 83-04 response_actions dispatch and support report"
provides:
  - "capabilities/quarantine.rs, quarantine_paths.rs: hash-bound move with manifest, restore from the manifest only, protected-path lists equal to the contract's, same_exe, stored_path, running_now"
  - "capabilities/process_kill.rs: plan_kill, survivors, kill_body, kill_by_exe, parse_request, same_process"
  - "Instructions quarantine_file, unquarantine_file and kill_process (with expected_exe, processes and optional quarantine_id) answered by response_actions::handle"
  - "Heartbeat tokens quarantine_file, unquarantine_file, kill_process_exe on Windows and Linux"
affects: [83-10, 83-11, 83-12, 83-13, 83-14]

actuals:
  tokens: 24700
  tasks: 2
  commits: 2
plan_head_before: 6eaf5ab2049b452058f316318fd20e31dec56926
plan_head_after: 72f529b2246dd7048ddd7290f420bbff110758ca

tech-stack:
  added: []
  patterns:
    - "Pure planning functions (plan_kill, survivors, kill_body) fed scripted process lists; the only signal in any test goes to a child the test started"
    - "File operations that can lose data are values (FileOps) so a test can make the second half of a cross-volume move fail"
    - "Whole quarantine and restore operations run inside Store::update, so the response-state lock serialises them"

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/quarantine.rs
    - agent-install/omni-agent-rs/src/capabilities/quarantine_paths.rs
    - agent-install/omni-agent-rs/src/capabilities/quarantine_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/process_kill_tests.rs
    - agent-install/omni-agent-rs/tests/quarantine_dispatch_test.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/process_kill.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/instructions.rs

key-decisions:
  - "A missing file at quarantine time answers outcome refused, not a failure: the backend then records agent_refused and the breaker ignores it"
  - "A restore of an unknown or already restored id answers status error, outcome not_found, verify ok false"
  - "The manifest is written before the move and removed if the move fails; a repeat counts as already_applied only when both the manifest and the stored file exist"
  - "restore places the file with a hard link first (never replaces a file that appeared meanwhile), and copies to a create_new file only where links are impossible"
  - "kill_by_exe counts any other process still running the approved image as a survivor, so a restarted copy keeps the answer from saying gone"

patterns-established:
  - "valid_id (instruction task id rule) is now pub(crate) in response_actions and shared by quarantine"
  - "Agent state that must outlive a move is written before the move (manifest) and verified after (hash of the stored file)"

requirements-completed: []

coverage:
  - id: D1
    description: "quarantine_file moves a hash-matching file into the quarantine folder with a manifest and never deletes it"
    requirement: RESP-03
    verification:
      - kind: unit
        ref: "cargo test --lib quarantine (22 passed)"
        status: pass
      - kind: integration
        ref: "cargo test --test quarantine_dispatch_test a_real_file_is_moved_out_and_restored_byte_for_byte"
        status: pass
  - id: D2
    description: "unquarantine_file restores from the manifest only and refuses an existing target, a linked folder and a changed stored file"
    requirement: RESP-03
    verification:
      - kind: unit
        ref: "quarantine::tests::a_restore_refuses_an_existing_destination_and_a_changed_stored_file and a_restore_refuses_a_destination_folder_that_is_a_link"
        status: pass
  - id: D3
    description: "protected-path outcome, with the prefix lists equal to the contract's"
    requirement: RESP-05
    verification:
      - kind: unit
        ref: "quarantine::tests::the_protected_lists_equal_the_contracts"
        status: pass
  - id: D4
    description: "kill_process with expected_exe, processes and quarantine_id reaches only the approved image, leaves a reused pid alone, and answers verify ok only when nothing named is left"
    requirement: RESP-06
    verification:
      - kind: unit
        ref: "cargo test --lib process_kill (20 passed)"
        status: pass
      - kind: integration
        ref: "cargo test --test quarantine_dispatch_test a_kill_after_a_move_ends_the_child_that_runs_the_stored_image and a_kill_ends_only_the_approved_program_and_leaves_a_reused_pid_alone"
        status: pass
  - id: D5
    description: "tokens quarantine_file, unquarantine_file, kill_process_exe reported and the contract examples equal the real bodies"
    requirement: RESP-10
    verification:
      - kind: unit
        ref: "cargo test --lib response_ (74 passed)"
        status: pass
---

# Phase 83 Plan 09: Quarantine, restore and a kill that tells the truth Summary

The Rust agent can now move a flagged file out of reach and put it back with one instruction, and it can end a process that a person approved without ever hitting a reused PID or reporting a live process as gone. Nothing is published, version-bumped or deployed.

## What was built

**Task 1, commit fb9f87c39.** `quarantine.rs` (485 lines) and `quarantine_paths.rs` (244 lines).

- A move checks the instruction id, a full path with no `..`, the agent's own files, the protected prefixes, then refuses a folder, a link or anything that is not a regular file, hashes the file and compares it with the flagged sha256 (`hash_mismatch` leaves it untouched). It then writes the manifest and renames the file into the quarantine folder (mode 000 on Linux, `<id>.q` on Windows).
- Across two volumes it copies to a `create_new` file, flushes, hashes the copy again, and only then removes the original. If the original cannot be removed it removes only its own copy and answers `locked`.
- A restore reads the manifest only. It refuses an existing destination, a destination folder that is a link or reparse point, a missing folder, and a stored file whose hash no longer matches. On Linux it sets the original mode back and tries to chown the original owner (ignored without root). It places the file with a hard link first, so a file that appeared meanwhile is never replaced.
- Both operations run inside `Store::update`, so the response-state lock serialises them and `quarantine_index` records each entry.
- The dispatch arms read the process list just before the move, keep the entries whose executable is the path, and after the move report those that are still the same process (`still_running`: pid, name, start_time, at most 128).

**Task 2, commit 72f529b22.** `process_kill.rs` (247 lines).

- `plan_kill` sorts a process list into `kill`, `unconfirmed` and left alone. `kill_by_exe` signals each `kill` entry (re-checking its start time just before), then reads the list up to 10 times 500 ms apart until none of the named processes remains. `kill_body` builds the contract bodies.
- The `kill_process` arm moved from `instructions.rs` into `response_actions::handle`. With `expected_exe` it runs the new path; with `quarantine_id` it resolves the stored image through `quarantine::stored_path`; with only `target` it calls the Phase 53 `remediation_actions::kill_process` and returns the old body shape. The Phase 53 unit tests and `remediation_dispatch_test` pass unedited.

## Manifest format (ships in the published agent; later agents must read it)

`<quarantine dir>/<id>.json`, pretty JSON, version 1, camelCase keys:

| Key | Meaning |
|---|---|
| `v` | 1 |
| `id` | the instruction task id |
| `originalPath` | full path the file came from; restore goes here and nowhere else |
| `sha256` | lower-case hex of the file at move time |
| `size` | bytes |
| `quarantinedAt` | epoch seconds |
| `mode`, `uid`, `gid` | Linux only; absent on Windows |

Beside it: the stored file `<id>` (Linux, mode 000) or `<id>.q` (Windows). `response_state.json` `quarantine_index` also holds `{id, originalPath, sha256, quarantinedAt}`, but the manifest is the source of truth. Folder: Linux `/var/lib/omni-agent/quarantine` (0700); Windows `quarantine` beside the agent executable.

## Outcome table

| Situation | status | outcome | verify |
|---|---|---|---|
| Moved | success | quarantined (+ still_running when processes survive) | in_quarantine, ok true when manifest, stored hash and absent original all hold |
| Same id repeated, same file | success | already_applied | in_quarantine |
| Same id, other file | error | refused | none |
| Hash differs | error | hash_mismatch | in_quarantine false |
| Protected prefix, own file, own exe | error | protected_path | in_quarantine false |
| In use, no access, or original cannot be removed after a copy | error | locked (+ still_running) | in_quarantine false |
| Bad id, bad hash, relative or `..` path, folder, link, missing file | error | refused | none |
| Other I/O failure | error | none (counts as agent_failed) | none |
| Restored | success | restored | restored_to_path |
| Restore: unknown or already restored id | error | not_found | restored_to_path false |
| Restore: destination exists, folder is a link or gone, stored file changed | error | refused | restored_to_path false |

## Kill decision table (`plan_kill`)

"Moved" means the instruction carried `quarantine_id`. A start time within 2 seconds is the same process.

| Process | Moved | Nothing moved |
|---|---|---|
| Reports the stored path (listed or not) | kill | n/a |
| Listed, same start, reports original path | kill | kill |
| Listed, other start, reports original path | unconfirmed | kill |
| Unlisted, reports original path | left alone | kill |
| Listed, same start, another or unreadable program | unconfirmed | unconfirmed |
| Listed, other start, another readable program | left alone, counts as gone | left alone, counts as gone |
| Listed, other start, unreadable program | unconfirmed | unconfirmed |
| Kill-bound but pid <= 1, the agent's own pid or a critical name | unconfirmed | unconfirmed |

`kill_body` order: nothing planned gives `process_gone` ok; no kill but something unconfirmed gives `refused` (nothing was signalled); a kill with no survivor and nothing unconfirmed gives `killed` ok; anything else gives `killed` with verify false and every survivor and unconfirmed entry in `still_running`. Survivors are matched by pid and start time, and any other process still running the approved image also counts.

## What the real-process test saw on this VM

Linux, same volume, a copy of `sleep` running from a temp directory then moved: after the move `running_now` reported that pid's executable as the **stored path** (`/tmp/.tmpAkPHvV/quarantine/task-1`), not the original, so `same_exe(reported, original)` is false. That is why the plan accepts the stored path. The kill by `expected_exe` = original, `moved_exe` = stored, child listed, answered `killed`, verify ok, and the pid left the list. A decoy `sleep` from another directory, and a pid listed with a wrong start time (a simulated reuse), were left alive. Windows behaviour (A-83-EXE-REPORT, A-83-A3, A-83-A10) is not observed: it is for the live test on EILT0197.

## Verification

Cargo recipe from the run notes was used for every run (CARGO_BUILD_JOBS=1, nodebug target dir, debug off, `--offline`).

- `--lib quarantine`: 22 passed. `--lib process_kill`: 20 passed. `--lib response_`: 74 passed. `--lib remediation_actions`: 16 passed (Phase 53 kill tests unedited). `--test quarantine_dispatch_test`: 6 passed. `--test remediation_dispatch_test`: 5 passed.
- Acceptance greps: `symlink_metadata` 9 in quarantine.rs; `"kill_process" =>` 0 in instructions.rs; `start_time` and `stored_path` present; quarantine.rs 485, process_kill.rs 247, response_actions.rs 320 lines.

## Deviations from Plan

**1. [Rule 3 - blocking, file size] Extra files.** The 500-line limit needed the path policy and the test code split out: `quarantine_paths.rs`, `quarantine_tests.rs` and `process_kill_tests.rs` are not in the plan's file list. `quarantine.rs` re-exports the plan's names (`stored_path`, `same_exe`, `running_now`, `QuarantinePaths`, `RunningProcess`, `STILL_RUNNING_CAP`) so callers and the integration test use `capabilities::quarantine::*`.

**2. [Rule 3 - ordering] Task 1 commit holds a minimal `process_kill.rs`.** `quarantine.rs` needs `same_process`, so the Task 1 commit carries the tolerance constant and `same_process` only; Task 2 replaces it with the full module.

**3. [Rule 1] Existing 83-04 tests updated.** `response_contract_tests.rs` asserted the exact token lists and `response_actions_tests.rs` asserted `!handles("kill_process")`. Both changed for the new tokens and handler. `response_actions::valid_id` became `pub(crate)`, and `CRITICAL_PROCESS_NAMES` in `remediation_actions.rs` became `pub(crate)` (one-word changes).

**4. `QuarantinePaths` has two more fields than the plan names** (`protected`, `windows_style`) plus the response-state `store`, so the injected protected list and the lock are explicit.

**5. Contract JSON not extended.** The plan says to add the restore example; the contract has no unquarantine example (its `restore_done` belongs to `restore_host`), and adding one would change the file the backend also reads. The restore body is asserted in the agent tests only.

**6. TDD order.** The implementation was written before its tests ran, so there is no RED commit and no RED run for either task. After the fact I mutated two lines of `plan_kill` (kill an unlisted process on the original path after a move; kill a reused pid with an unrelated program) and the tests failed (1 and 2 failures) before I restored the file. Other tests were not mutation-checked.

## Not verified

- Every `cfg(windows)` branch (`is_link_like` reparse check, error codes 17, 32, 33) and the Windows-style path rules on a real Windows host. The path rules are tested as text on Linux; the Windows target was not compiled.
- Cross-volume copy on a real second volume: simulated with `FileOps` (rename forced to fail with CrossesDevices).
- The chown on restore (needs root) and quarantine folder ACLs on Windows (A-83-A10).
- Large files: the whole move runs inside the state lock, so a very large cross-volume copy blocks claim updates and the 15-second sweeper for its duration.

## Read and not read

Read in full: run notes, the plan, 83-CONTEXT.md decisions (lines 1-100), the contract JSON, `response_actions.rs`, `response_state.rs`, `remediation_actions.rs`, `process_kill`/`quarantine` sibling code, `verify.py` lines 1-140, RESEARCH Q6, Q7-Q11, Q12-Q13 and Pitfalls 1-8 (lines 375-503) plus the R3/R5/R10 table rows. Not read: 83-04-SUMMARY.md, 83-UI-SPEC.md (this plan names no section), 83-PATTERNS.md, 83-VALIDATION.md, PROJECT.md, config.json, the rest of RESEARCH (lines 1-374 and 504+, beyond the grep hits), CONTEXT lines 100+, the `.claude/skills/` directory and CLAUDE.md beyond the system-supplied copy.

## User-visible sentences the UI-SPEC does not word

These strings are in agent results and reach the backend's stored result; the backend shows its own wording, but a person could see them in a raw result:

- "The file no longer matches the hash that was flagged." and "The file is in use and could not be moved." (both taken verbatim from the contract examples)
- "The file is a protected system file or belongs to this agent."
- "The file is no longer at that path." / "Only a regular file can be quarantined, not a folder or a link." / "The path must be a full path with no '..' part." / "sha256 must be 64 hexadecimal characters." / "The instruction id is missing or not valid." / "This instruction id already holds a different file." / "The quarantine folder already holds a file for this instruction id."
- Restore: "Nothing is quarantined under that id." / "The stored file is not in the quarantine folder." / "A file is already at the original path, so nothing was restored." / "The original folder is a link, so nothing was restored." / "The original folder is gone, so nothing was restored." / "The stored file has changed since it was quarantined." / "The restored copy did not match, so it was taken out again."
- Kill: "The process does not match the expected program." (verbatim from the contract) and the request refusals "expected_exe is required.", "processes must name at least one process.", "Each process needs a pid above 1 and a start_time above 0."

## Facts for later plans

- The backend must send `kill_process` with `expected_exe`, `processes` (`[{pid, start_time}]`, 1 to 128 entries, pid above 1) and, after a quarantine, `quarantine_id` (the quarantine instruction's task id). The agent derives the stored path itself. The backend should also send `quarantine_file` with `path`, `sha256`, and `allow_protected` only for an approved card. `unquarantine_file` takes `quarantine_id` only.
- `kill_process` rows now answer `refused` (plus `still_running: []`) for bad input, and `killed` with verify false when a named process is unconfirmed or survives. `verify.settle` turns that into `verify_failed`; `failure_outcome` turns `refused` into `agent_refused`. A `killed` body can carry `still_running` entries that are unconfirmed rather than known alive.
- 83-03's `row_extras` reading `row.result.still_running` is fed by both quarantine and kill bodies; the entries share one shape.
- A restore of an unknown id is a non-success status, so it lands as `failed`/`agent_failed` in `failure_outcome` (outcome `not_found` is not special-cased there).
- The existing UEBA path sends `kill_process` with `target` only and is unchanged.
- Nothing in this plan deletes a quarantined file; retention is open (A-83-RETENTION).

## Threat Flags

None beyond the plan's threat register (T-83-34 to T-83-38, T-83-74 mitigated in code and tests; T-83-75 accepted).

## Self-Check: PASSED

Created files exist (quarantine.rs, quarantine_paths.rs, quarantine_tests.rs, process_kill.rs, process_kill_tests.rs, tests/quarantine_dispatch_test.rs); commits fb9f87c39 and 72f529b22 are in HEAD's history; the user's uncommitted hunks in `capabilities/mod.rs` stayed uncommitted (the commit added only the three `pub mod` lines).
