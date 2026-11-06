---
phase: 84-staged-patch-rollouts
plan: 07
subsystem: agent
tags: [rust-agent, patch-reversibility, revert-by-job, agent-contract, wua, apt, dnf]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-02 agent contract names (rolloutTokens, rolloutParams, patchStatuses, patchCodes, patchExamples)
provides:
  - reversibility pre-check on Linux (package source still offers the installed version) and Windows (IsUninstallable read before the update joins the install collection), switched on by require_reversible
  - per-job revert state and rollback_patches with revert_of (reverted, version_not_offered, not_uninstallable, not_changed_by_job, not_applicable)
  - tokens patch_reversible_check and patch_revert_by_job in SUPPORTED_TOKENS and in the contract (12 tokens)
affects: [84-08, 84-09, 84-10, 84-11, 84-12, 84-13, 84-21]

requirements-completed: [PTCH-06, PTCH-04]

actuals:
  tokens: 13500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "pure parsers, decisions and state transforms tested directly; no package manager or Windows Update runs in a test"
    - "the Windows install script stays the 2.1.16 const; install_script(true) derives the reversible variant by four anchored replacements, and a test checks every anchor exists once"
    - "result helpers coded_result / deferred_result live in patch_reversible and are re-exported by patch_installer (keeps patch_installer.rs under 500 lines)"

key-files:
  created:
    - agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs
    - agent-install/omni-agent-rs/src/capabilities/patch_state.rs
  modified:
    - agent-install/omni-agent-rs/src/capabilities/patch_installer.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/capabilities/response_actions.rs
    - agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs
    - shared/agent-response-contract.json
    - backend/tests/test_autonomous_ops_block_contract.py

key-decisions:
  - "parse_dnf_list and parse_madison return only what the package SOURCE offers: dnf 'Installed Packages' rows and apt's /var/lib/dpkg/status entry are left out. After an upgrade the old version has to come from the source, so counting the local copy would make every package look reversible"
  - "a source that cannot be read offers nothing, so the package is deferred (not_reversible), never installed on a guess"
  - "a revert_of that is present but malformed is an error, not a fallback to the oldest-version rollback; revert_of on install_patches is also an error"
  - "no record of the job on this host (never installed here, pruned after 90 days, unreadable state) is failed with code not_applicable and nothing is reverted"
  - "patch_state.json keeps its name; the new format is {legacy, jobs} and the 2.1.16 flat map loads as legacy. A 2.1.16 agent reading the new file sees no legacy map (accepted: agent only moves forward)"
  - "Windows revert codes are read from the uninstall script's own sentences (constants pinned by a test) so the script and the legacy rollback output stay byte-identical to 2.1.16"

patterns-established:
  - "Later plans read the codes and statuses from patch_reversible's constants; the contract test pins them against patchCodes"

coverage:
  - id: D1
    description: "With require_reversible, Linux installs a package only when the source still offers the installed version, else the package is deferred with code not_reversible and nothing is installed; unreadable source defers"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs#patch_reversible_linux_needs_the_installed_version_to_be_offered"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs#patch_reversible_madison_ignores_the_local_status_file_entry"
        status: pass
    human_judgment: true
    rationale: "The parsers and the decision are tested on real-shaped output; the call to apt-cache / dnf just before the upgrade needs a real host (live-only list, assumption A-84-A2)"
  - id: D2
    description: "With require_reversible, the Windows install script reads IsUninstallable before adding an update and defers the rest; without the flag it is the 2.1.16 script byte for byte"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs#patch_reversible_windows_install_script_checks_is_uninstallable_before_adding_an_update"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs#patch_reversible_windows_install_script_without_the_flag_is_the_2_1_16_script"
        status: pass
    human_judgment: true
    rationale: "The script text is checked and the Windows target compiles (cargo check x86_64-pc-windows-gnu); running it against Windows Update needs a real Windows host (live-only list)"
  - id: D3
    description: "A revert by job puts back exactly what that job changed (invariant: package upgraded by jobs N-1 and N, revert_of N goes back to the version before N); ids the job did not change are skipped, an unknown job reverts nothing"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_state.rs#patch_state_revert_of_restores_version_before_that_job"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_state.rs#patch_state_an_id_the_job_did_not_change_is_skipped_with_its_code"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/patch_state.rs#patch_state_a_job_the_host_has_no_record_of_reverts_nothing"
        status: pass
    human_judgment: true
    rationale: "State transforms are tested; the downgrade itself (apt-get install pkg=version, dnf downgrade pkg-version, WUA uninstall) can only be proven on a real host. Success is reported only after the manager confirms the installed version, by construction (downgrade returns Ok only on a matching installed_version)"
  - id: D4
    description: "The agent advertises patch_reversible_check and patch_revert_by_job on Windows and Linux; the contract token list equals SUPPORTED_TOKENS; every patchExamples result body is produced by the installer helpers"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs#every_patch_example_is_produced_by_the_patch_installer_helpers"
        status: pass
      - kind: unit
        ref: "agent-install/omni-agent-rs/src/capabilities/response_contract_tests.rs#the_reported_tokens_equal_the_contract_exactly"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_contract.py"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-11-06
status: complete
plan_head_before: d2ceeb50e622698226b7be1ddee873820a06eec9
commits: 3
plan_head_after: 9718f59deabb083d6907466f8294486ae4f1e357
---

# Phase 84 Plan 07: Reversibility Check and Revert by Job Summary

**The 2.1.17 agent defers any patch it cannot put back on its own host (apt/dnf source still offers the installed version, Windows marks the update uninstallable), reverts exactly what one install job changed via per-job state and `revert_of`, and advertises both abilities by token.**

## Performance

- **Duration:** about 25 min (start time was not captured at the very start; estimated from file timestamps)
- **Completed:** 2026-11-06
- **Tasks:** 3
- **Files:** 8 in commits (2 created, 6 modified)

## Accomplishments

- `patch_reversible.rs`: `parse_madison`, `parse_dnf_list`, `reversible_linux`, `offered_versions_command` (argv lists), the async `offered_versions`, `code_revert_rows`, the six code constants, and `coded_result` / `deferred_result`. `install_script(require_reversible)` in `patch_installer.rs` inserts the `IsUninstallable` gate before `$coll.Add($u)` and reports a deferred row once per KB (never also "not offered").
- `PatchJob` gained `require_reversible` and `revert_of`; `summarize` is unchanged, so a job of one deferred patch is `completed`, successful 0, failed 0 (matches `patchExamples.install_deferred_not_reversible`).
- `patch_state.rs`: `JobsState {legacy, jobs}`, `record_install`, `revert_targets`, `plan_revert`, `record_kb_successes`, 90-day prune; the flat 2.1.16 map loads as `legacy`. Linux install records the version before each job; Windows records the KBs that job installed. `rollback_patches` without `revert_of` uses the legacy map exactly as before (the downgrade command moved into one shared `downgrade` helper, same argv and messages).
- Tokens: `SUPPORTED_TOKENS`, the contract `tokens` (12), the pinned lists in `response_contract_tests.rs`, plus tests that build every `patchExamples` result with the helpers and compare status, code, summary counts and body keys.

## Task Commits

1. **Task 1: Reversibility pre-check on Linux and Windows** - `f43776619` (feat)
2. **Task 2: Per-job revert state** - `245834601` (feat)
3. **Task 3: The agent advertises both tokens and matches the contract examples** - `9718f59de` (feat)

`patch_installer.rs` ends at 498 lines (limit 500). `mod.rs` carries the user's uncommitted `collect_due` work; only the `pub mod` lines were staged (via `git apply --cached`), the user's hunks are still present unstaged.

## Decisions Made

See `key-decisions`. TDD note: the plan is `type: execute` with `tdd="true"` tasks; tests and code were written together per task (Rust tests live inline, and a compile error is not a valid RED), one commit per task, as in 84-01 and 84-02. No separate RED commit exists.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] parse_dnf_list must not count the "Installed Packages" rows**
- **Found during:** Task 1
- **Issue:** the plan text says the parser keeps versions "from Installed Packages and Available Packages". Counting the installed copy would make `reversible_linux(installed, offered)` true for every dnf package, defeating D-05 (the old version has to come from the source after the upgrade). The same holds for `apt-cache madison`, which can list the dpkg status file.
- **Fix:** only "Available Packages" rows are returned; madison entries whose source is `/var/lib/dpkg/status` are skipped. Tests pin both.
- **Files modified:** `patch_reversible.rs`
- **Commit:** `f43776619`

**2. [Rule 3 - Blocking] The untracked integration test `tests/patch_dispatch_test.rs` no longer compiled**
- **Found during:** Task 3 (full `cargo test`)
- **Issue:** it builds `PatchJob { .. }` with a struct literal; the two new fields broke it.
- **Fix:** added `require_reversible: false, revert_of: None` to that one literal. The file is the user's untracked file, so the edit is in the working tree and NOT in any commit. Its 10 tests pass (they exercise the unchanged 2.1.16 paths).
- **Files modified:** `agent-install/omni-agent-rs/tests/patch_dispatch_test.rs` (uncommitted)

**3. [Rule 2 - Missing critical] A malformed `revert_of` must never become a legacy rollback**
- **Found during:** Task 2 (T-84-23)
- **Issue:** reading `revert_of` with the same filter as `job_id` would turn a bad value into `None`, i.e. the oldest-version rollback, which reverts more than the job changed.
- **Fix:** present-but-invalid `revert_of` is an error from `parse_job`; `revert_of` on an install is an error too. Test covers `../x`, empty, number, space, 81 chars.
- **Commit:** `245834601`

**4. [Rule 2 - Design gap] "No record of the job" has no code in the plan**
- **Issue:** the plan gives codes for four revert outcomes but not for a host that has no record of the job (unreadable or pruned state, T-84-25).
- **Fix:** failed with the contract's existing `not_applicable`. The backend's `not_reverted(code)` (messages.py) raises KeyError for codes outside its reason table, which does not list `not_applicable` or `not_changed_by_job`; whichever plan maps agent results to Not reverted texts must handle these two codes.

---

**Total deviations:** 4 auto-fixed (1 bug, 1 blocking, 2 missing-critical). **Impact on plan:** none on the plan's truths.

## Issues Encountered

None blocking. The Windows build check belongs to 84-21; `cargo check --target x86_64-pc-windows-gnu --lib` was run anyway and is clean for the patch files (no warnings there).

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-84-23: ids and `revert_of` pass the existing shape rules, every command is an argv list. T-84-24: success is returned only after `installed_version` equals the target (Linux) or WUA reports result code 2/3 (Windows); everything else is a coded failure. T-84-25: unreadable or missing state means no target and a `not_applicable` failure.

## User Setup Required

None. Nothing was deployed, restarted or published; the agent version is still 2.1.16 (84-21 bumps it). The private test mongod on port 27998 was stopped.

## Next Phase Readiness

- Live-only (assumption A-84-A2): apt often no longer offers an older installed version after a security update, so many Linux canary installs will defer to approval; dnf/yum downgrade uses name-version-release; Windows `IsUninstallable` is read before install and may differ after. None can be proven without a real host.
- 84-08 onward can read the six code constants from `patch_reversible` and the example bodies from the contract. `service_state` is still to be added to `tokens` by 84-11.

## Self-Check: PASSED

- Files exist: `patch_reversible.rs`, `patch_state.rs`; commits `f43776619`, `245834601`, `9718f59de` are ancestors of HEAD.
- Acceptance criteria re-run: `IsUninstallable` count in `patch_installer.rs` is 2; `patch_installer.rs` is 498 lines; `fn parse_madison|parse_dnf_list|reversible_linux` count is 3; `revert_of` appears 12 times in `patch_state.rs`; the invariant test is `patch_state_revert_of_restores_version_before_that_job`; contract tokens print 12; `patch_revert_by_job` appears in `response_actions.rs`.
- Verification: `cargo test --lib patch_` 29 passed; `--lib response_` all passed; whole `--lib` 468 passed, 0 failed; `--test patch_dispatch_test` 10 passed; `cargo check` clean on x86_64-unknown-linux-gnu and x86_64-pc-windows-gnu for the patch files; backend `test_patch_rollout_contract`, `test_autonomous_ops_block_contract`, `test_autonomous_ops_followups`, `test_watchdog_contract` 97 passed, 0 skipped.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
