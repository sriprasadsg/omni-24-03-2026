---
phase: 83-autonomous-security-response
plan: 14
subsystem: agent
tags: [rust, service-watch, restart-service, reboot-host, autonomous-ops, agent-contract]
status: complete

requires:
  - phase: 83-autonomous-security-response
    provides: "83-12 report_result helper and the accepted-then-final posting pattern; 83-04 response_actions dispatch and token report; 83-02 privileged recorder seam"
provides:
  - "capabilities/service_watch.rs: classify_systemd, classify_sc, status_of, changed_watched, update_watched_from_heartbeat, report, restart, restart_arm"
  - "Config.watched_services (persisted in config.yaml) fed by the heartbeat reply key watchedServices"
  - "meta.service_failures in every heartbeat: [{name, failure_id, since, state, exit_code}]"
  - "restart_service instruction: answers accepted, posts the final body with the same task id"
  - "capabilities/host_power.rs: schedule_reboot, parse_delay, clean_reason; reboot_host instruction"
  - "SUPPORTED_TOKENS now equals the contract token set exactly; response_actions::HANDLED lists the commands and is tested against commandToken"
affects: [83-15, 83-16, 83-17, 83-18, 83-19, 83-20, 84]

actuals:
  tokens: 11600
  tasks: 2
  commits: 4
plan_head_before: 293659af7b9c6f006421afeda21ecbb5bf703a0b
plan_head_after: 17669ad0b00db1f8e2be9fbc5a3e7bd31d3fa108

tech-stack:
  added: []
  patterns:
    - "Parsers are plain string functions over captured command output, so Windows output is tested on Linux"
    - "Health is an enum (Running, Pending, Stopped, Failed, Unknown); only Failed is ever reported, only Running verifies a restart"
    - "A report keeps its memory in a Watch value; the process-wide one is a OnceLock<Mutex<Watch>> and tests use their own"
    - "The restart waits through an injected pause, so tests never sleep"

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/service_watch.rs
    - agent-install/omni-agent-rs/src/capabilities/service_watch_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/host_power.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/config.rs
    - agent-install/omni-agent-rs/src/heartbeat.rs
    - agent-install/omni-agent-rs/src/lib.rs

key-decisions:
  - "A failed restart check answers status success, outcome not_running, verify.ok false (the same shape as block_verify_failed), so the backend's settle lands it as verify_failed and not as an agent error"
  - "since is Unix seconds of the first check that saw the failure, not the moment the service actually died; failure_id is the lower-case name, a hyphen and since"
  - "The agent refuses two extra own-service names that the contract does not list (omniagentrust, omni-agent-rs) and strips a .service suffix before comparing, so sshd.service cannot get past the critical list"
  - "update_watched_from_heartbeat is called after isolation::apply_body in lib.rs, not beside update_intervals_from_heartbeat, because that line is the user's uncommitted hunk"

patterns-established:
  - "HANDLED is the one list of commands response_actions answers; handles() reads it and a contract test compares it with commandToken"

requirements-completed: []

coverage:
  - id: D1
    description: "A failing watched service is reported only after 60 seconds with one failure_id across beats; an admin stop is never reported on Linux or Windows; recovery clears the failure"
    requirement: RESP-04
    verification:
      - kind: unit
        ref: "cargo test --lib service_watch (29 passed): a_failure_younger_than_sixty_seconds_..., the_same_failure_keeps_one_failure_id_..., a_service_an_admin_stopped_is_never_reported_on_either_system, a_windows_failure_is_reported_with_its_exit_code"
        status: pass
  - id: D2
    description: "restart_service refuses unsafe, critical and own names with no command recorded, uses fixed argv, and answers restarted with healthy_after or not_running with verify.ok false"
    requirement: RESP-04
    verification:
      - kind: unit
        ref: "service_watch::tests::restart_refuses_unsafe_names_and_records_no_command, restart_uses_fixed_argv_..., a_service_running_after_the_poll_..., a_service_that_never_runs_..., the_restart_done_example_has_a_real_producer"
        status: pass
  - id: D3
    description: "The watched list is adopted from the heartbeat reply only when well formed; an empty or absent list checks nothing; the capability off issues no command"
    requirement: RESP-04
    verification:
      - kind: unit
        ref: "service_watch::tests::a_new_well_formed_list_is_taken, an_unchanged_malformed_or_absent_list_gives_none, an_emptied_list_is_taken_..., with_the_capability_off_or_nothing_listed_no_command_runs, a_critical_or_invalid_name_on_the_list_is_never_asked_about"
        status: pass
  - id: D4
    description: "reboot_host schedules with fixed argv, delay 30 to 300 (default 60), a cleaned reason, and answers the contract's reboot_scheduled example on both systems"
    requirement: RESP-10
    verification:
      - kind: unit
        ref: "cargo test --lib host_power (11 passed) and response_contract_tests::the_reboot_scheduled_example_has_a_real_producer_on_both_systems"
        status: pass
  - id: D5
    description: "SUPPORTED_TOKENS as a set equals the contract's tokens; HANDLED equals commandToken's keys; every contract example name is known to the agent tests"
    requirement: RESP-10
    verification:
      - kind: unit
        ref: "cargo test --lib response_ (80 passed): the_reported_tokens_equal_the_contract_exactly, the_command_tokens_cover_every_command_the_agent_answers, every_example_in_the_contract_is_one_the_agent_tests_reproduce"
        status: pass
---

# Phase 83 Plan 14: Failed-service reporting, safe restart and scheduled reboot Summary

The Rust agent now reports a watched service that really failed (after a 60-second grace, never one an admin stopped), restarts it safely on request, and can schedule a reboot, and the tokens it reports equal the published contract. Nothing is published or version-bumped, and no real `systemctl`, `sc` or `shutdown` ran on this VM.

Cargo recipe from the run notes was used for every run (`CARGO_BUILD_JOBS=1`, nodebug target dir, debug off, `--offline`).

## What was built

**Task 1 (commits cb7e42cd9 RED, 3a24e8622 GREEN).**

- `service_watch.rs` (276 lines; tests in `service_watch_tests.rs`, 372 lines).
  - `classify_systemd` reads `ActiveState`, `Result` and `ExecMainStatus`. `failed` is a failure; `activating` or `deactivating` with a `Result` other than `success` is a failure; `inactive` with `success` is a stop; `active` is running.
  - `classify_sc` reads numbers only: `STATE`, `WIN32_EXIT_CODE`, `START_TYPE`. State 1 with a non-zero exit code is a failure unless the start type is 4 (disabled); state 1 with exit code 0 is a stop; 4 is running; 2, 3, 5, 6 and 7 are pending.
  - `status_of` asks with `systemctl show -p ActiveState,SubState,Result,ExecMainStatus <name>`, or `sc query <name>` (and `sc qc <name>` only for a stopped service that carries an error code, the one case where the start type decides).
  - `changed_watched` takes a well-formed list, gives `None` for an unchanged, malformed (not strings, a name `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$` fails, more than 50) or absent one. `update_watched_from_heartbeat` persists through `config::save`.
  - `report` / `report_with`: nothing runs unless `remediation_executor` is allowed and the list is not empty; the services are asked about at most once per 60 seconds (also re-asked when the list changes); a failure is reported once its age is at least 60 seconds; the first-seen time lives in a `Watch` (process-wide `OnceLock<Mutex<Watch>>`), recovery or removal from the list clears it. Critical or malformed names on the list are never asked about.
  - `restart(os, name, pause)`: validates again, runs `systemctl restart <name>` (Linux) or `sc stop`, a wait while the state is pending, `sc start` (Windows), then checks up to 10 times, one second apart.
  - `restart_arm`: refuses at once for a bad task id, missing or unsafe `service_name`; otherwise answers `{"status":"accepted"}` and runs the restart on a blocking thread after the 2-second head start, posting the final body with `instructions::report_result` under the same task id.
- `remediation_actions.rs`: `CRITICAL_SERVICE_NAMES` is now the contract's 18 names (a test compares them), `validate_service_name` and `is_valid_service_name` are `pub(crate)`.
- `config.rs` `watched_services`, `lib.rs` one call, `heartbeat.rs` one line for `meta["service_failures"]`.
- Tokens `restart_service` and `service_failures` added.

**Task 2 (commits 9cf770388 RED, 17669ad0b GREEN).**

- `host_power.rs` (203 lines with tests): `parse_delay` (missing is 60, a whole number 30..=300 else refused), `clean_reason`, `schedule_reboot`. Linux argv is `shutdown -r +N <reason>` with N the delay in whole minutes rounded up (30 and 60 give `+1`, 61 gives `+2`, 300 gives `+5`); Windows argv is `shutdown /r /t <seconds> /c <reason>`; one argv element each.
- `response_actions.rs`: `reboot_host` arm in `handle_at`, token added, `HANDLED` const behind `handles()`.
- `response_contract_tests.rs`: token set equals the contract, `HANDLED` equals `commandToken` keys, the `reboot_scheduled` example is produced on both systems, the rebootDelaySeconds limits match, and the contract's example names must all be known to the agent tests.

## Sample output each parser was tested against

`systemctl show -p ActiveState,SubState,Result,ExecMainStatus nginx`:

| Case | Output (one property per line) | Result |
|---|---|---|
| crashed | `Result=exit-code` `ExecMainStatus=1` `ActiveState=failed` `SubState=failed` | Failed {failed, exit 1} |
| admin `systemctl stop` | `Result=success` `ExecMainStatus=0` `ActiveState=inactive` `SubState=dead` | Stopped (never reported) |
| waiting for `Restart=` | `Result=exit-code` `ExecMainStatus=203` `ActiveState=activating` `SubState=auto-restart` | Failed {activating, exit 203} |
| starting normally | `Result=success` `ActiveState=activating` `SubState=start` | Pending |
| running | `Result=success` `ActiveState=active` `SubState=running` | Running |
| empty, or `Failed to get properties: Unit nginx.service not found.` | | Unknown |

`sc query nginx` (full sample text kept in the test file): stopped with error is `STATE : 1  STOPPED`, `WIN32_EXIT_CODE : 1066  (0x42a)`, `SERVICE_EXIT_CODE : 1  (0x1)`; admin stop is the same with `WIN32_EXIT_CODE : 0  (0x0)`; running is `STATE : 4  RUNNING`; starting is `STATE : 2  START_PENDING`.

`sc qc nginx`: `START_TYPE : 2   AUTO_START` (a failure stays a failure) and `START_TYPE : 4   DISABLED` (an error code on a disabled service is treated as a stop). All samples were written by hand from the documented shape of the output; none was captured from a real host.

## Verification

- RED 1: 29 failed, 28 of them `todo!()` stub panics; the one real assertion failure was `the_critical_service_list_equals_the_contract` (the list still had 6 of 18 names). It is not an ImportError.
- GREEN 1: `--lib service_watch` 29 passed; whole `--lib` 385 passed, 1 ignored; `--test remediation_dispatch_test` 5 passed and `--test quarantine_dispatch_test` 6 passed.
- RED 2: `--lib host_power` 11 failed on `todo!()` panics (stub panics, not assertions); `--lib response_` 4 contract tests failed on real assertions (missing `reboot_host` token, handler and example producer).
- GREEN 2: `--lib host_power` 11 passed; `--lib response_` 80 passed; whole `--lib` 400 passed, 1 ignored.
- Acceptance: `update_watched_from_heartbeat` appears once in lib.rs; `watched_services` once in config.rs; `reboot_host` 3 times in response_actions.rs; service_watch.rs 276 lines, response_actions.rs 387.
- No test ran a real `systemctl`, `sc` or `shutdown`: every call goes through `privileged`, whose recorder replaces the spawn under `cfg(test)`. The test that spawns the real `restart_arm` task runs on the recorder too (the spawned thread has its own recorder that answers success with no output) and its post goes to 127.0.0.1:1.
- Mutation testing of the implementation was not done.
- The user's uncommitted hunks stayed uncommitted. For `mod.rs`, `config.rs`, `lib.rs` and `heartbeat.rs` I staged blobs built from `git show HEAD:<file>` plus only my lines; `git show --stat` of each commit lists just my files, and `git show` of the four shared files shows only my lines. My lines depend on no uncommitted hunk (`enabled` and `cfg` already exist at HEAD).

## Deviations from Plan

**1. [Rule 3 - uncommitted dependency] lib.rs call site.** The plan says to call `update_watched_from_heartbeat` "beside update_intervals_from_heartbeat". That line is the user's uncommitted 2.1.15 hunk, so I put the call after the committed `isolation::apply_body(&body)` line. Behaviour is the same.

**2. [Rule 2 - correctness] Own-service and suffix handling.** `remediation_actions::validate_service_name` strips a `.service` suffix before the critical comparison (otherwise `sshd.service` passes), and refuses two more of the agent's own names, `omniagentrust` (the NSIS service name) and `omni-agent-rs`, in a separate `OWN_SERVICE_NAMES` list so the contract comparison on `CRITICAL_SERVICE_NAMES` stays exact. The platform's validator uses only the contract list, so `OmniAgentRust` passes the platform and the agent answers `refused` (which the breaker ignores). `disable_service` and `enable_service` share this validator, so they now also refuse the longer list and names over 128 characters.

**3. [Rule 2 - correctness] Reason cannot read as an option.** `clean_reason` also strips leading `-` and `/` characters (the plan asked for control-character removal and a 200-character cut). The reason is the last argv element of `shutdown`, where getopt-style parsing could otherwise take `--poweroff` as an option.

**4. [Rule 3 - structure] `HANDLED` constant and an extra test file.** `handles()` now reads a `HANDLED` list so a test can compare it with the contract's `commandToken` (the plan's "commandToken covers every command in handles()" cannot be checked against a `matches!`). `service_watch_tests.rs` is not in the plan's file list; it keeps `service_watch.rs` below 500 lines.

**5. [Plan choice] Not-running answer shape.** The plan says "not_running with verify ok false" without a status. I used `status: success` so the backend's `verify.settle` ends the row as `verify_failed` through the existing path (like `block_verify_failed`), not as an agent error. If the backend wants `status: error` the change is one line in `service_watch::restart`.

**6. [Not done] No direct test of `update_watched_from_heartbeat`.** It calls `config::save`, which writes the real config path; `changed_watched` (the decision) is tested, the persist call is not.

## Not verified

- Every `cfg(windows)` behaviour and `sc` output on a real Windows host, including that a real `sc stop` by an administrator leaves `WIN32_EXIT_CODE : 0` (A-83-A6), that `sc` output labels stay English on non-English Windows, and whether Defender stops `sc` or `shutdown` spawned by the agent service (A1). Real crash and stop tests on both systems are UAT items.
- Real systemd: that a unit the manager does not know answers `inactive` with `Result=success` (assumed from systemd behaviour; the code treats an empty answer and a `not found` message as unknown).
- A Linux unit named without `.service` works with `systemctl show/restart` (standard systemd behaviour, not run here).
- `healthy_after` is the number of one-second checks, 1 to 10, not the time the service took to start; the contract example shows 30, which this agent cannot produce (the test substitutes the example's value before comparing).
- A service that starts and crashes within the same second it is checked is reported as restarted.

## Read and not read

Read in full: run notes, the plan, 83-CONTEXT.md lines 1-100 (all decisions D-01..D-28), RESEARCH Q8 to Q11 (lines 395-434), 83-12-SUMMARY.md, `shared/agent-response-contract.json`, `privileged.rs`, `response_actions.rs`, `response_contract_tests.rs`, `remediation_actions.rs` (lines 1-215 and 230-340), `capabilities/mod.rs` lines 1-260, the `instructions.rs` result post and dispatch (lines 80-140 and 480-610), the diffs of `lib.rs`, `config.rs` and `heartbeat.rs` against HEAD, and the STATE.md frontmatter and tail. Not read: 83-UI-SPEC.md (the plan names no section), the rest of 83-RESEARCH.md, PROJECT.md, config.json, `.claude/skills/`, the `selection_tests` in `mod.rs`.

## User-visible sentences the UI-SPEC does not word

Agent result strings that land in the stored raw result (the backend shows its own wording):

- "delay_seconds must be a whole number from 30 to 300."
- "This platform does not support restarting a service." / "service_name is required." / "The instruction id is missing or not valid." / "The restart task stopped unexpectedly."
- Refusals reuse the existing validator wording: "Invalid target: Service name '<name>' contains invalid characters." and "Service not found: Refusing to touch OS-critical service '<name>'."
- The default reboot reason shown to people on the computer: "Restart requested by Omni Agent".

## Facts for later plans

- **Failure report** (83-17 reads it): `meta.service_failures` is always present, an empty list when nothing qualifies, the capability is off, nothing is listed or the platform is neither Windows nor Linux. Each entry is `{name, failure_id, since, state, exit_code}`; `name` is as the tenant listed it, `since` is Unix seconds, `failure_id` is `{lower-case name}-{since}`, `state` is `failed`, `activating` or `deactivating` on Linux and `stopped` on Windows, `exit_code` is the `ExecMainStatus` or `WIN32_EXIT_CODE` number or null. The backend still has to add `"service_failures": "remediation_executor"` to its `_DATA_KEYS` (research Q8) so an unticked tenant's data is dropped.
- **Watched list delivery:** the agent reads the heartbeat reply key `watchedServices` (a list of names). No backend code sends it yet, so a plan on the backend side must add it, only for tenants that hold `remediation_executor`. An empty list is taken and stops all checks; an absent key changes nothing.
- **restart_service instruction:** `parameters.service_name` plus the task id (1 to 64 letters, digits or hyphens). The poll answers `{"status":"accepted"}` (or an immediate `refused` body); the final body is posted later with the same task id: `restarted` (success, `verify {ok true, check service_running}`, `healthy_after` 1 to 10), `not_running` (success, `verify.ok` false), `refused` (error), `blocked_by_local_security` (error), or an error with no outcome. As with isolation, a late `accepted` must not overwrite a final status. `verify.settle` stores neither `healthy_after` nor anything else from the body: 83-17 must copy `healthy_after` into `row.result`, as the run notes already say.
- **reboot_host instruction:** `parameters.delay_seconds` (30 to 300, default 60) and `parameters.reason` (optional); the plan's research mentioned an `action_id` parameter, which the agent ignores. It answers directly (no `accepted` step) with `scheduled` or an error; a second schedule while one is pending is whatever `shutdown` answers (an error body with no outcome). There is no cancel.
- **Tokens:** the agent now reports all ten contract tokens on Windows and Linux; 83-15's gate checks (`agent_support.token_for`) have nothing left to wait for on the agent side. Nothing is published or version-bumped; 2.1.16 is the user's step.
- 83-14 finishes no requirement on its own: RESP-04 still needs the backend restart rule and budget (83-17), and RESP-10 spans every plan that adds a token. Neither is ticked.

## Threat Flags

None beyond the plan's register. T-83-50 (service name in argv) is mitigated by the character rule, the leading-hyphen refusal, the critical and own-name lists (case-insensitive, `.service` stripped), the 128-character cap, and one argv element per value, checked in `restart_arm`, `restart` and again for every watched name. T-83-51 by the 60-second grace and the 60-second report cache. T-83-53 by the reason cleaning (a hostile reason stays one argv element, tested). T-83-52 and T-83-SC accepted as planned.

## Self-Check: PASSED

Created files exist (`service_watch.rs`, `service_watch_tests.rs`, `host_power.rs`); commits cb7e42cd9, 3a24e8622, 9cf770388 and 17669ad0b are in HEAD's history; `commits:` above is the measured count from the plan ledger (4).
