---
phase: 83-autonomous-security-response
plan: 02
subsystem: autonomous-ops
tags: [rust-agent, block-ip, firewall, iptables, netsh, response-state, agent-contract, tdd]
status: complete

requires:
  - phase: 83-01
    provides: shared/agent-response-contract.json and the backend path proven with a stand-in agent
provides:
  - capabilities/privileged.rs, the one place the agent spawns a privileged command, with a recording seam under cfg(test)
  - capabilities/response_state.rs, response_state.json (versioned, atomic writes, claims, room for isolation and quarantine index)
  - capabilities/firewall.rs, rule plans for Linux (OMNI_BLOCK chain) and Windows (two named rules), apply, remove, check
  - capabilities/response_actions.rs, block_ip with ttl_seconds and unblock_ip that removes one claim, plus support_report
  - capabilities/response_contract_tests.rs, result bodies compared key for key with the shared contract
  - meta.response_actions {v, platform, tokens} in every heartbeat
affects: [83-04, 83-05, 83-09, 83-12, 83-16, 83-17]

requirements-completed: []
requirements-partial: [RESP-02, RESP-06, RESP-10]

actuals:
  tokens: 16000
  tasks: 2
  commits: 2
plan_head_before: ed06f179413bc3a2698f9d503ba01d5389f7c144
plan_head_after: 41ae56df8ec409b76bc0a940ba88cc4cde0a8a89

tech-stack:
  added: []
  patterns:
    - "One spawn helper (privileged::run / run_output) with argv elements only; under cfg(test) a thread-local recorder with a scripted result queue replaces the spawn"
    - "Firewall plans are plain data (Ensure {check, add}, Remove {check, delete}) compiled on every OS; cfg picks the OS at one call site (Os::current)"
    - "State file: version field, flatten extra map so unknown fields survive a rewrite, temp file + rename in the same directory, corrupt file is an error never an empty state"
    - "Contract test reads ../../shared/agent-response-contract.json at run time and returns early when absent"

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/privileged.rs
    - agent-install/omni-agent-rs/src/capabilities/response_state.rs
    - agent-install/omni-agent-rs/src/capabilities/firewall.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/heartbeat.rs
    - agent-install/omni-agent-rs/src/instructions.rs

key-decisions:
  - "Claim written to disk before the firewall changes; a failed apply drops the claim (and the part-added rule when no other live claim needs it); a rule the check cannot find keeps the claim and answers verify.ok false so the expiry still removes whatever was added."
  - "Unblock keeps the claims when the rule removal fails (the state change is applied only after remove_block succeeds)."
  - "When other live claims still hold the address, unblock answers verify check firewall_rule_present with ok = rule still there; when the last claim goes it answers firewall_rule_absent."
  - "The agent refuses addresses it must never block: unspecified, loopback, multicast, broadcast, link-local, and the platform's own address when api_base_url is an IP literal. RFC 1918 ranges are not refused."

duration: stopped-executor resume, about 1 h of review, mutation checks and commits
completed: 2026-11-01
---

# Phase 83 Plan 02: The agent speaks the response contract Summary

The real Rust agent now answers `block_ip` / `unblock_ip` with the exact result bodies the backend path was proven against: a time-limited block held as a claim on disk, applied idempotently on Linux and Windows through one privileged-command seam, verified by a firewall check, undone one claim at a time, and reported as a support token in every heartbeat.

## What was built

- **privileged.rs** (119 lines): `run` and `run_output` are the only `Command::new` in the response code. Under `cfg(test)` a thread-local `Recorder` keeps every call (program, then one argv element per parameter) and hands out scripted results, so no unit test touches a real firewall. `remediation_actions.rs` now calls `privileged::run` for service control; its old `run_privileged_command` and its no-op test stub are gone.
- **response_state.rs** (358): `STATE_VERSION 1`; `ResponseState {v, claims, isolation, quarantine_index, extra}` with serde defaults and a flattened `extra` map (fields a newer agent wrote are kept on rewrite); `Store` with `load()` and `update(|state| ..)` under a process-wide mutex, temp file in the same directory, `sync_all`, rename; mode 0600 on Unix; a corrupt or newer-version file is an error and is left untouched. `Store::default()` is `config_path().with_file_name("response_state.json")`, with a thread-local override under `cfg(test)`.
- **firewall.rs** (457): `Os`, `Cmd`, `Ensure`, `Remove`; `block_plan`, `present_plan`, `unblock_plan`; `apply_block`, `remove_block`, `rule_present`. IPv4-mapped IPv6 is treated as IPv4. Windows treats netsh's "No rules match" as absent even on exit 0.
- **response_actions.rs** (485): `SUPPORTED_TOKENS = ["block_ip_ttl"]`, TTL 3600 / 604800 / default 86400, `handles`, `handle` (and `handle_at` with platform, store and time injected), `support_report`.
- **instructions.rs**: old `block_ip` / `unblock_ip` arms removed, one guard arm added (684 lines, down from 696). **heartbeat.rs**: one line, `meta["response_actions"]`. **mod.rs**: module registrations.

## Recorded command lists

Linux block of 45.33.32.156 on an empty firewall (test `linux_block_creates_the_chain_hooks_and_both_directions_with_wait_flag`), then the post-add check (`the_final_check_asks_for_both_hooks_and_both_rules`):

```
iptables -w -n -L OMNI_BLOCK
iptables -w -N OMNI_BLOCK
iptables -w -C INPUT -j OMNI_BLOCK
iptables -w -I INPUT 1 -j OMNI_BLOCK
iptables -w -C OUTPUT -j OMNI_BLOCK
iptables -w -I OUTPUT 1 -j OMNI_BLOCK
iptables -w -C OMNI_BLOCK -s 45.33.32.156 -j DROP
iptables -w -A OMNI_BLOCK -s 45.33.32.156 -j DROP
iptables -w -C OMNI_BLOCK -d 45.33.32.156 -j DROP
iptables -w -A OMNI_BLOCK -d 45.33.32.156 -j DROP
-- post-add check --
iptables -w -C INPUT -j OMNI_BLOCK
iptables -w -C OUTPUT -j OMNI_BLOCK
iptables -w -C OMNI_BLOCK -s 45.33.32.156 -j DROP
iptables -w -C OMNI_BLOCK -d 45.33.32.156 -j DROP
```

A second apply issues only the five `-n -L` / `-C` checks and no `-N`, `-I` or `-A`. An IPv6 address uses `ip6tables` for every call.

Windows block of the same address (test `windows_block_adds_one_inbound_and_one_outbound_rule`); the post-add check shows both rules again:

```
netsh advfirewall firewall show rule name=OmniAgent_Block_45.33.32.156_in
netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.156_in dir=in action=block remoteip=45.33.32.156
netsh advfirewall firewall show rule name=OmniAgent_Block_45.33.32.156_out
netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.156_out dir=out action=block remoteip=45.33.32.156
```

Windows removal deletes `_in`, `_out` and, best effort, the legacy single rule `OmniAgent_Block_45.33.32.156`.

## Behaviour change to publish knowingly: block_ip with no ttl_seconds now lasts 24 hours

A `block_ip` with no `ttl_seconds` now lasts 24 hours on the agent. The old Rust arm left the rule in place until someone removed it. Nothing unstamped sends `ttl_seconds` today (`backend/playbooks/block_ip.yaml` has no such parameter), so a person's block that reaches a Rust agent this way ends after 24 hours instead of staying permanently. A `ttl_seconds` below 3600 or above 604800 is refused (status error, outcome refused, nothing touched). Know this before publishing 2.1.16. Not for 83-02 to fix, but 83-04 (expiry) is what actually removes the rule when the 24 hours are up: until it lands, a claim whose time has passed is only cleaned up when someone sends an `unblock_ip` for that address.

## Verification

Recipe used for every cargo run: the run notes' recipe (`CARGO_BUILD_JOBS=1`, `CARGO_TARGET_DIR=$PWD/agent-install/omni-agent-rs/target/nodebug`, `CARGO_PROFILE_DEV_DEBUG=0`, `CARGO_PROFILE_TEST_DEBUG=0`, `--offline`), not the plan's bare commands. No link stall.

- `--lib firewall`: 20 passed (includes response_actions tests whose names contain "firewall").
- `--lib response_state`: 12 passed. `--lib response_`: 40 passed at first run (41 after the heartbeat test was added, see Deviations).
- Final working-tree run: `--lib -- response_ firewall privileged remediation_actions selection_tests`: 78 passed. `--lib interval_tests` (the user's 2.1.15 hunks beside this work): 5 passed.
- `--test remediation_dispatch_test`: 5 passed (this builds the library without cfg(test), which proves the real `run_output` compiles and no integration test reaches a firewall arm).
- Each commit was also built and tested on its own in a throwaway copy of HEAD plus only the files staged for that commit (so the committed tree makes sense without the user's uncommitted 2.1.15 hunks): Task 1 tree `cargo check --lib` clean and 46 tests passed; Task 2 tree 75 lib tests plus `remediation_dispatch_test` 5 passed.
- No new compiler warnings from any file of this plan (the 15 existing warnings are in other files).
- Acceptance counts: `Command::new` in privileged.rs 1, in firewall.rs 0; `OmniAgent_Block_` in firewall.rs at least 2; `pub async fn block_ip` in remediation_actions.rs 0; `response_actions::handle` in instructions.rs 1 line; heartbeat.rs mentions response_actions; instructions.rs 684 lines (< 696); every new file under 500 lines (119, 358, 457, 485, 182).

## Deviations from Plan

### No RED commit (TDD honesty)

An earlier executor wrote tests and implementation together (2026-10-31 20:06 to 20:10), started its first cargo test and stalled at the link for 2.5 hours until a usage limit ended it. It committed nothing and no test of this code had ever run. A true RED commit cannot be recovered and none was faked: "no RED commit, tests and code written together by the stopped executor". This run read every file against the plan as someone else's code, ran the tests (all green first time) and then proved the tests can fail by breaking behaviour briefly (mutate, run, see failure, revert; every mutated file was restored byte for byte and `git status` on the shared contract was clean):

| # | Task | Mutation | Tests that failed |
|---|------|----------|-------------------|
| M1 | 1 | `-w` dropped from the rule commands | 3 firewall tests (`..._with_wait_flag`, `ipv6_uses_ip6tables_for_every_call`, `the_final_check_asks_for_both_hooks_and_both_rules`) |
| M2 | 1 | OUTPUT hook removed from the block plan | 3 (`a_second_apply_adds_nothing...`, `ipv6...`, `..._with_wait_flag`) |
| M3 | 1 | `remove_claims` ignores `block_id` | `undo_removes_one_claim_and_the_rule_only_with_the_last`, `removing_one_claim_leaves_the_others_and_none_means_all` |
| M4 | 1 | state written in place (copy instead of rename) | `a_write_leaves_no_temp_file_behind` |
| M5 | 2 | `expires_in` dropped from the block body | 6 (three contract tests, `a_changed_example_body_is_noticed`, TTL tests) |
| M6 | 2 | `BLOCK_TTL_MIN` 3000 | `a_ttl_outside_the_range_is_refused...`, `the_shared_limits_and_tokens_match_the_agent` |
| M7 | 2 | plan's contract mutation: `expires_in` removed from the contract's `block_applied` example | `block_applied_and_already_applied_equal_the_examples`, `the_real_dispatch_answers_a_block_with_the_contract_example` |
| M8 | 2 | a token not in the contract added to `SUPPORTED_TOKENS` | `the_shared_limits_and_tokens_match_the_agent`, `support_names_the_platform_and_holds_the_ttl_token` |
| M9 | 2 | heartbeat meta line deleted | `every_heartbeat_carries_the_support_report` (added this run) |
| M10 | 2 | guard arm in `instructions.rs` disabled | `the_real_dispatch_answers_a_block_with_the_contract_example` |

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Old `block_ip` / `unblock_ip` arms removed from instructions.rs in the Task 1 commit, not Task 2**
- **Found during:** commit preparation
- **Issue:** the plan assigns instructions.rs to Task 2, but Task 1 deletes `remediation_actions::block_ip` / `unblock_ip`, so a Task 1 commit that left the old arms would not compile.
- **Fix:** the Task 1 commit carries the arm removals only; Task 2's commit adds the `use` line and the guard arm. Between the two commits `block_ip` falls to the unknown-instruction arm; no build ships from between them.
- **Files:** `src/instructions.rs`. **Commit:** 07b2cc9d9.

**2. [Rule 1 - Bug against acceptance] response_actions.rs was 509 lines and the guard arm spanned two matching lines**
- **Found during:** review against the acceptance list
- **Issue:** `wc -l` must be below 500 and `grep -c "response_actions::handle"` must print 1; the stopped executor's file was 509 lines and the arm was written on three lines with `crate::capabilities::` paths (two matching lines).
- **Fix:** the three `support_*` tests moved to `response_contract_tests.rs` (now 485 lines); `use crate::capabilities::response_actions;` added to instructions.rs and the arm is one line.
- **Commit:** 41ae56df8.

**3. [Rule 2 - Missing critical] Heartbeat support report had no test**
- **Fix:** `every_heartbeat_carries_the_support_report` calls the real `build_payload` (with an empty enabled list so no collector runs) and compares `meta.response_actions` to `support_report()`. Mutation M9 proves it fails without the heartbeat line.
- **Commit:** 41ae56df8.

**4. [Rule 2 - Missing critical, T-83-06] Agent-side refusal of addresses that must never be blocked**
- The stopped executor added, and this run kept, a refusal of unspecified, loopback, multicast, broadcast, link-local and the platform's own address (api_base_url as an IP literal). The plan says every parameter is validated by the agent itself; the old arm accepted any parseable address. Private (RFC 1918) addresses are deliberately still blockable.

### Other notes

- The stopped executor's `Store::update` rolls back to the old claims when a rule removal fails, and an unblock whose claim is absent but whose rule exists still answers `removed`. Reviewed and kept.
- `requirements-completed` is empty: see below.

## Requirements

Left unticked in REQUIREMENTS.md: RESP-02 (needs 83-04 for the expiry), RESP-06 and RESP-10 (the agent half is done here but the plan-level backend and UI half belong to other plans of the phase). Nothing was ticked by this run.

## State position

STATE.md reads Plan 3 of 20 because 83-03 landed first; this run records 83-02 as complete without moving that line backwards. The orchestrator reconciles position after the wave.

## Known Stubs

None. The `isolation` and `quarantine_index` fields of `response_state.json` are declared and round-trip but nothing writes them yet; that is intended (83-09 and 83-12 use them) and keeps the file format stable.

## Threat Flags

None beyond the plan's register. T-83-06 (one spawn helper, argv only, agent-side validation) and T-83-07 (claim keyed by task id, a repeat returns already_applied) are mitigated and tested; T-83-08 accepted as planned. The state file is created mode 0600 on Unix.

## Open items for the user

- Not run here, as instructed: the live Linux round trip (flagged assumption A-83-A12, chain at position 1 of INPUT and OUTPUT beside ufw/firewalld under iptables-nft) and the Windows `dir=out` assumption (A-83-A4). Both are for the human check after publish, not for any unit test.
- The agent was not built for Windows, published or version-bumped; the 2.1.15 hunks in mod.rs and heartbeat.rs, and lib.rs, config.rs, Cargo.toml and others, were left uncommitted as found.

## Self-Check: PASSED

All five new source files exist; commits 07b2cc9d9 and 41ae56df8 are ancestors of HEAD; `git show --stat` of both shows no gzip, post_json, collect_due, collection_intervals or flate2 hunk.
