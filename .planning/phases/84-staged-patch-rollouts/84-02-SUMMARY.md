---
phase: 84-staged-patch-rollouts
plan: 02
subsystem: autonomous-ops
tags: [patch-rollout, agent-contract, copy-gate, server-copy, payload-types]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-01 rollout package (RING_STATES, HOST_STATES, rollout/__init__.py), install_patches dispatcher allow-list
provides:
  - rollout names in the agent contract (rolloutTokens, rolloutParams, patchStatuses incl. deferred, patchCodes, serviceState shape) plus eight full patch result bodies
  - backend/autonomous_ops/rollout/messages.py, the one home of every rollout server sentence
  - copy-gate "directories" list walked recursively on the pytest and vitest sides (missing or empty directory fails)
  - components/patchRollouts/rolloutCopy.ts (assurance line, chip maps, link labels) and services/patchRollouts/types.ts (payload contract)
affects: [84-03, 84-05, 84-06, 84-07, 84-08, 84-09, 84-10, 84-11, 84-12, 84-13, 84-14, 84-15, 84-16, 84-17, 84-18, 84-19]

requirements-completed: [PTCH-04, PTCH-06]

actuals:
  tokens: 18000
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "contract keys added under new names; existing keys pinned by per-key digests, tokens pinned by prefix only"
    - "count-bearing templates take a pre-pluralised phrase ({computers} = '3 computers'); shape changes at one use a one/many pair picked by forms()"
    - "copy gate covers whole directories; a listed directory that is missing or empty fails"

key-files:
  created:
    - backend/autonomous_ops/rollout/messages.py
    - backend/tests/test_patch_rollout_contract.py
    - backend/tests/test_patch_rollout_messages.py
    - components/patchRollouts/rolloutCopy.ts
    - services/patchRollouts/types.ts
    - src/__tests__/rolloutCopy.test.ts
  modified:
    - shared/agent-response-contract.json
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "Not reverted sentences are built from one reason table (NOT_REVERTED_REASON) so every text ends 'The patch is still installed.'; not_reverted(code) raises KeyError for an unknown code instead of guessing a reason"
  - "count-bearing templates take {computers}/{patches}/{hours} phrases built by plural(), so no sentence reads '1 computers'; the Reboot and revert-restart Why lines are worded 'A restart is needed on {computers} ...' to read correctly at one and many"
  - "helper semantics fixed here: plural(n, one, many) returns the number and noun; count(n, one, many) returns only the agreeing noun"
  - "the PREFLIGHT title key and the PreflightCheck type use 'autonomous_ops', not 'autonomy', because the structural stamp scanner treats any dict key named autonomy as an autonomy stamp write"

patterns-established:
  - "Later plans read sentences by key from rollout/messages.py and shapes by name from services/patchRollouts/types.ts; neither holds logic beyond fill/plural/forms and four small builders"

coverage:
  - id: D1
    description: "The agent contract names the rollout tokens, params, patch statuses and codes, the service_state shape and one full result body per patch outcome; the ten 2.1.16 tokens and every pre-existing key are unchanged"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "backend/tests/test_patch_rollout_contract.py#test_every_pre_existing_key_other_than_tokens_is_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_contract.py#test_the_examples_say_what_each_outcome_is"
        status: pass
    human_judgment: false
  - id: D2
    description: "A deferred not_reversible result posted through record_agent_patch_result leaves the package pending; a success clears it"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_contract.py#test_a_not_reversible_deferral_leaves_the_package_pending"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_contract.py#test_a_successful_install_removes_the_package_from_the_pending_list"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every server sentence a rollout shows lives in rollout/messages.py; the assurance line is exact and no text claims a revert (each Not reverted text ends 'The patch is still installed.')"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "backend/tests/test_patch_rollout_messages.py#test_every_not_reverted_text_ends_with_the_patch_is_still_installed"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_messages.py#test_the_assurance_line_and_the_halt_second_line_are_verbatim"
        status: pass
    human_judgment: false
  - id: D4
    description: "The copy gate scans every file under the three rollout directories through a pinned list; a missing or empty directory fails and a planted violation is reported on both the pytest and vitest sides"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py#test_a_banned_term_in_a_scanned_directory_is_reported"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts#ACTV-08 directories"
        status: pass
    human_judgment: false
  - id: D5
    description: "services/patchRollouts/types.ts is the single payload contract and rolloutCopy.ts the single UI copy module for the rollout screens"
    requirement: PTCH-04
    verification:
      - kind: unit
        ref: "src/__tests__/rolloutCopy.test.ts"
        status: pass
    human_judgment: true
    rationale: "The types are checked by tsc (clean) and the chip maps by test, but whether the field set is what the backend views (84-09, 84-10) and screens need is only proven when those plans consume it"

duration: 14min
completed: 2026-11-06
status: complete
plan_head_before: 98c2c48500fac56b4d74b2323f9b39fc4b4168d9
commits: 4
plan_head_after: 34cec947df05960a1d35b6f4673cfca3aa95c214
---

# Phase 84 Plan 02: Rollout Contracts Summary

**Agent contract names for rollouts (with eight full patch result bodies), one tested module for every rollout server sentence, a directory-level copy gate on both test sides, and the UI copy module and payload types the screens share.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-11-06T14:00Z
- **Completed:** 2026-11-06T14:17Z
- **Tasks:** 3 (plus one fix commit)
- **Files:** 10 (6 created, 4 modified)

## Accomplishments

- `shared/agent-response-contract.json` gained `rolloutTokens`, `rolloutParams`, `patchStatuses` (adds `deferred`), `patchCodes`, `serviceState` and `patchExamples` (install ok, ok with restart, deferred not reversible, failed; revert ok, not uninstallable, version not offered, not changed by job). The ten 2.1.16 tokens and every other pre-existing key are untouched; tests pin the token prefix and a digest of each old key.
- A `deferred` / `not_reversible` result through the real `record_agent_patch_result` leaves the package in the host's pending list (`deferred` is not in `_CLEARED_STATUSES`), so a not-reversible patch never looks installed.
- `rollout/messages.py` (about 310 lines, stdlib only) holds the assurance and halt lines, ring and computer states, health check, failure rate, soak, halt reasons, Not reverted texts, revert summary, preflight, `CANNOT_TAKE`, validation, approval card and Activity shapes, and `API_DETAIL`, with `fill`, `plural`, `count`, `forms` and four builders.
- The copy gate gained `directories` (rollout backend, `components/patchRollouts`, `services/patchRollouts`): recursive walk, `__pycache__` skipped, a missing or empty directory fails, negative controls on both sides. The `files` list and its pins are unchanged.
- `rolloutCopy.ts` (assurance line, `ROLLOUT_STATUS_CHIP`, `RING_STATE_CHIP`, `HOST_STATE_CHIP`, `SIGNAL_CHIP` incl. DEV-2 `not_checked`, `LINK_LABELS`, `plural`) and `types.ts` (every payload type in the plan) exist; icon names are checked against `components/icons.tsx` by a test.

## Task Commits

1. **Task 1: Agent contract for rollouts, one example per patch outcome** - `18d3f19c0` (feat)
2. **Task 2: Every rollout server sentence in one module** - `22e8cf14e` (feat)
3. **Task 3: Copy gate scans rollout directories; UI copy module and payload types** - `4fa878450` (feat)
4. **Fix: autonomy preflight key renamed (Rule 1)** - `34cec947d` (fix)

**Plan metadata:** the docs commit following this summary.

## Decisions Made

See `key-decisions`. DEV-2, DEV-3 and DEV-4 are UI-SPEC deviations pending the user's review (governing record: `84-UI-SPEC.md` "Planning Deviations (pending user review)"); this plan implements the copy side of each and does not mark any accepted: DEV-2 (`NOT_CHECKED`, `SIGNAL_CHIP.not_checked`), DEV-3 (`CANNOT_TAKE`, the autonomy-off and cap blockers), DEV-4 (the `directories` copy gate and the `components/patchRollouts` / `services/patchRollouts` placement).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A dict key named `autonomy` tripped the structural stamp scanner**
- **Found during:** plan-level regression run (`test_autonomous_ops_*.py`)
- **Issue:** `PREFLIGHT["titles"]` had a key `autonomy`; `test_only_the_gate_writes_the_autonomy_stamp` treats any dict key named `autonomy` as a stamp write and failed on `rollout/messages.py`.
- **Fix:** key (and the `PreflightCheck` TypeScript union member) renamed to `autonomous_ops`; a test now pins that no dict key in the module is `autonomy` or `autonomy.*`.
- **Files modified:** `backend/autonomous_ops/rollout/messages.py`, `services/patchRollouts/types.ts`, `backend/tests/test_patch_rollout_messages.py`
- **Commit:** `34cec947d`

**2. [Rule 2 - Wording] Count-bearing Why lines reworded to read correctly at one and many**
- **Found during:** Task 2
- **Issue:** UI-SPEC Reboot Why `{n} computers need a restart to finish installing.` and revert Why `Removing the update on {n} computers needs a restart.` read wrongly at one computer.
- **Fix:** `A restart is needed on {computers} to finish installing.` and `Removing the update needs a restart on {computers}.` (same meaning, correct at any count). The same approach is used for the revert summary's restart line.
- **Commit:** `22e8cf14e`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 wording). **Impact on plan:** none on the plan's truths. Later plans that key `PREFLIGHT["titles"]` or `PreflightCheck` by autonomy must use `autonomous_ops`.

## Issues Encountered

None. TDD note: the plan is `type: execute` with `tdd="true"` tasks; RED was observed for Task 1 (KeyError on the new keys, 14 failures) and Task 3 (missing `directories`, empty frontend directories); Task 2's module and tests were written together and its behaviours are covered by the banned-term and fill tests rather than a separate RED run. One commit per task, as in 84-01.

## Known Stubs

None. `rolloutCopy.ts` and `types.ts` are complete contracts; no screen consumes them yet (84-14 onward), by design.

## Threat Flags

None. T-84-05 (one module, a test requires 'The patch is still installed.' on each Not reverted text), T-84-06 (existing keys digest-pinned, new names under new keys) and T-84-07 (directories must exist and be non-empty, negative controls both sides) are implemented as planned. PROH-84-02 holds: no sentence claims a revert; `not_reverted()` raises on an unknown code.

## User Setup Required

None. Nothing was deployed, restarted, published or migrated; the private test mongod (port 27998) was stopped.

## Next Phase Readiness

- 84-07 and 84-11 append the three rollout names to `tokens` when the agent implements each one (the contract test pins only the first ten).
- UI-SPEC DEV-1..DEV-4 remain pending the user's review; DEV-2, DEV-3 and DEV-4 copy is in place here.
- Plans 84-03 onward import sentences by key from `rollout/messages.py` and shapes from `services/patchRollouts/types.ts`.

## Self-Check: PASSED

- Created files exist: messages.py, test_patch_rollout_contract.py, test_patch_rollout_messages.py, rolloutCopy.ts, types.ts, rolloutCopy.test.ts; commits `18d3f19c0`, `22e8cf14e`, `4fa878450`, `34cec947d` are ancestors of HEAD.
- Acceptance criteria re-run: contract prints `10 [...]` and 8 examples; `reverts where supported` count 2, `The patch is still installed` count 3, messages.py 311 lines; `directories` prints the three folders; `EXPECTED_DIRECTORIES` count 2; `RolloutCard` count 1.
- Verification: contract + block_contract + patch_deployment_flow 101 passed; copy gate + messages + contract 81 passed; vitest autonomousOpsCopy + rolloutCopy 33 passed; `npx tsc --noEmit` clean; all `test_autonomous_ops_*.py` and `test_patch_*.py` green (818 + structural 26 after the fix + 287), 0 skipped.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
