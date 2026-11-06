---
phase: 84-staged-patch-rollouts
plan: 06
subsystem: autonomous-ops
tags: [patch-rollout, rings, preflight, claims, agent-groups, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-01 rollout package (store.claim_hosts and the unique partial index, windows, rings.load/membership, controller); 84-02 messages (PREFLIGHT, CANNOT_TAKE, LEFT_OUT, CANARY_OS_GAP, VALIDATION)"
provides:
  - "rings.validate / rings.save / rings.RingsError / rings.PlatformRingsError / rings.ring_names_by_group / rings.resolve"
  - "start.preflight, start.classify_hosts, start.PreflightBlocked, start.AlreadyInRollout; start_rollout runs the check and claims atomically"
  - "rollout field leftOut [{agentId, hostname, reason, rolloutName}]"
  - "ringName on every row of GET /api/agent-groups"
  - "store.discard (a Start that fails leaves no rollout and no claim)"
affects: [84-07, 84-09, 84-12, 84-17, 84-18]

actuals:
  tokens: 18800
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "claims taken one computer at a time in agent id order, so two overlapping Starts can never both lose"
    - "a classifier that sorts every computer with a chosen patch pending into eligible or one reason, so nothing is dropped without being listed"

key-files:
  created:
    - backend/tests/test_patch_rollout_rings.py
    - backend/tests/test_patch_rollout_claims.py
  modified:
    - backend/autonomous_ops/rollout/rings.py
    - backend/autonomous_ops/rollout/start.py
    - backend/autonomous_ops/rollout/store.py
    - backend/autonomous_ops/rollout/messages.py
    - backend/autonomous_ops/messages.py
    - backend/agent_group_endpoints.py
    - backend/tests/test_patch_rollout_tracer.py

key-decisions:
  - "start_rollout raises PreflightBlocked(rows) and AlreadyInRollout; only the platform organization and non-installable ids still return a refused dict (the 84-09 route maps the exceptions to 422 and 409)"
  - "Claims are made one at a time in agent id order instead of one unordered insert_many: with an unordered batch two overlapping Starts could each take half the computers and both lose"
  - "The canary-per-operating-system check counts only canary computers that would really be claimed (pending one of the chosen patches, not left out), so a canary computer that is already patched is not a canary for that patch"
  - "A group deleted after the rings were saved is dropped (rings.resolve) before placement, so deleting the canary group reads as 'The canary ring has no computers' and members left behind never place anyone"
  - "A middle ring with no group is refused (UI-SPEC: only the last ring may have none); the ring keys are generated, canary is always 'canary'"
  - "Next window shows 'now' when a window is open, otherwise the next opening within 8 days; no coming window at all reads as the same blocker as no window"

patterns-established:
  - "Preflight rows are produced once (Assessment) and both preflight() and start_rollout() read it, so the dialog and the real Start can never disagree"

requirements-completed: [PTCH-01, PTCH-07, PTCH-05]

coverage:
  - id: D1
    description: "A tenant saves 2 to 4 rings from its own groups; Canary fixed with a group; ranges enforced; another tenant's or a deleted group refused; platform tenant refused; one ledger row and one audit event naming the person per save"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_a_valid_save_is_stored_loaded_and_recorded_once_with_the_person"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_a_group_belongs_to_one_ring_and_must_be_the_tenants_own"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_the_checks_stay_inside_their_ranges"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_the_platform_tenant_cannot_save_rings"
        status: pass
    human_judgment: false
  - id: D2
    description: "The agent group list carries ringName for a group a ring uses"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_the_agent_group_list_carries_the_ring_name"
        status: pass
    human_judgment: false
  - id: D3
    description: "Preflight blocks (window, rings, canary per operating system, Autonomous Ops off, stop, nothing pending, 500-computer cap) with the UI-SPEC sentences; start_rollout refuses with the rows and claims nothing"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_no_window_blocks_with_the_window_sentence_and_start_claims_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_the_canary_needs_a_computer_for_each_operating_system_in_the_selection"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_autonomous_ops_off_or_not_ticked_blocks"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_more_computers_than_the_cap_block"
        status: pass
    human_judgment: false
  - id: D4
    description: "Computers in another rollout and computers that cannot take one are listed with a reason and recorded on the rollout (leftOut); never silently dropped; offline computers stay in and are counted"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_a_computer_in_another_active_rollout_is_left_out_with_that_rollouts_name"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_computers_that_cannot_take_a_rollout_are_listed_with_their_reason_and_never_claimed"
        status: pass
    human_judgment: false
  - id: D5
    description: "Two concurrent Starts claim each computer once; the loser raises AlreadyInRollout and holds nothing; the platform's computers and never-touch computers are never claimed"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_two_starts_at_once_claim_each_computer_once_and_the_loser_holds_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_a_start_that_loses_a_race_midway_releases_what_it_claimed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_claims.py#test_a_platform_computer_under_a_customer_group_is_never_claimed"
        status: pass
    human_judgment: false
  - id: D6
    description: "Ring membership is snapshotted at Start; later group moves or deletions never move a computer of a running rollout"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_moving_a_group_to_another_ring_later_does_not_move_a_computer_of_the_running_rollout"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_rings.py#test_deleting_the_canary_group_later_leaves_the_running_rollout_alone_and_blocks_a_new_one"
        status: pass
    human_judgment: false

duration: 34min
completed: 2026-11-06
status: complete
plan_head_before: 3ff1532c894d16e4b34e14abeac5823b69d60bcd
commits: 5
plan_head_after: a4b676191129b976231098b1d0c748f5d97fc81e
---

# Phase 84 Plan 06: Rings and the Check Before Start Summary

**Tenant rings built from the tenant's own agent groups (validated, audited, shown as a ring name on the group list) and a Start that checks window, rings, a canary computer per operating system, Autonomous Ops, stops and size, lists every left-out computer with a reason, and claims computers one at a time in a fixed order so concurrent Starts never double-claim.**

## Performance

- **Duration:** 34 min
- **Started:** 2026-11-06T15:16Z
- **Completed:** 2026-11-06T15:50Z
- **Tasks:** 3
- **Files modified:** 9 (2 created, 7 modified)

## Accomplishments

- `rings.validate` / `rings.save` enforce R12 exactly: 2 to 4 rings, the first always Canary with at least one group, unique names of 1 to 40 characters, soak 1 to 168 hours, failure limit 1 to 50 percent, minimum sample 1 to 100, a group in one ring only, every group the tenant's own (another tenant's id and a deleted group are refused alike). A save writes the rings, one control ledger row (`rollout_rings_saved`) and one audit event naming the person; the platform organization raises `PlatformTenantError`.
- `start.preflight` returns the rows in the documented order and `start.start_rollout` refuses with `PreflightBlocked(rows)` when any blocker shows. Blockers: no maintenance window (D-03), rings not set or canary empty, no canary computer for an operating system in the selection (D-12, naming the Canary group), Autonomous Ops off, a stop (tenant or platform), more than 500 computers, nothing selected or pending.
- Every computer with a chosen patch pending is either in the rollout or listed with one reason: another rollout (named, D-13), agent too old, patch installs not switched on, unsupported system, busy with a patch job, never-touch. The list is stored on the rollout as `leftOut`. Offline computers stay in and are counted in the Offline row.
- Concurrent Starts: claims in agent id order, one computer per insert; the loser deletes its rollout and claims and raises `AlreadyInRollout`. A platform-tenant computer listed in a customer's group is never read, so never claimed.
- `GET /api/agent-groups/` carries `ringName` (null for a group no ring uses).

## Task Commits

TDD plan; each task has a failing-test commit and an implementation commit (Task 3 passed on arrival, see below).

1. **Task 1 RED** - `5b8d09d4e` (test) - rings validation, save, membership, ringName
2. **Task 1 GREEN** - `59e4a4b7f` (feat)
3. **Task 2 RED** - `64d5d72d4` (test) - 23 preflight and claim tests, all failing (`preflight` missing)
4. **Task 2 GREEN** - `edd6cb176` (feat)
5. **Task 3** - `a4b676191` (test) - snapshot survives later edits

## Decisions Made

See `key-decisions` above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Race] Claims one at a time in a fixed order**
- **Found during:** Task 2 (design of the concurrency test)
- **Issue:** The plan says to claim with `claim_hosts` and release on failure. With the 84-01 unordered `insert_many`, two overlapping Starts can each win half the computers, both see a duplicate, both release: neither starts. The plan's own truth says exactly one succeeds.
- **Fix:** `start_rollout` calls `claim_hosts` for one computer at a time, sorted by agent id (a global lock order), so at least one Start always wins. On any duplicate it deletes its host documents and rollout (`store.discard`) and raises `AlreadyInRollout`. The rollout document is inserted after the claims, so a failed Start leaves nothing visible to the controller.
- **Files modified:** `backend/autonomous_ops/rollout/start.py`, `backend/autonomous_ops/rollout/store.py`
- **Committed in:** edd6cb176

**2. [Rule 2 - Missing critical functionality] A deleted group never places a computer**
- **Found during:** Task 3 design
- **Issue:** Deleting a group removes its members through the route, but data left behind by any other path would still place computers (and the canary check would pass on a ghost group).
- **Fix:** `rings.resolve` drops groups that no longer exist before placement and before the Start snapshot.
- **Files modified:** `backend/autonomous_ops/rollout/rings.py`
- **Committed in:** 59e4a4b7f

**3. [Rule 2 - Missing critical functionality] Sentences the server must own for ring checks the screen cannot do alone**
- **Found during:** Task 1
- **Issue:** `messages.VALIDATION` had no sentence for the ring count, a repeated group, an unknown group, a long name, a renamed Canary or a middle ring with no group; a control label for the new ledger event was missing (it would read "Control event" in Activity).
- **Fix:** Added six VALIDATION sentences and `RINGS_SAVED` to the rollout messages and `rollout_rings_saved` to `CONTROL_LABELS`. The copy gate still passes.
- **Files modified:** `backend/autonomous_ops/rollout/messages.py`, `backend/autonomous_ops/messages.py`
- **Committed in:** 59e4a4b7f

**4. [Plan contract change] Two 84-01 tracer tests changed**
- `test_start_refuses_without_a_window_or_rings_or_for_the_platform_tenant` and `test_a_second_start_leaves_out_a_computer_another_rollout_holds` asserted the old refusal codes (`no_rings`, `no_window`, `no_hosts`). The plan makes a blocker raise `PreflightBlocked`; the tests now assert the rows (comment cites 84-06). The platform and invalid-ids refusals are unchanged. No other existing test changed.
- **Committed in:** edd6cb176

---

**Total deviations:** 3 auto-fixed (1 race, 2 missing critical) plus 1 deliberate contract change. **Impact:** none on the plan's truths; the concurrency fix is what makes the "exactly one succeeds" truth hold.

## DEV-3 and the Autonomous Ops blocker

Computers that cannot take a rollout are listed in the Left out area (rows with `check: left_out`, one per reason, using `CANNOT_TAKE`; there is no separate preflight check name for them). Two blockers beyond the UI-SPEC check list are in place as recorded in DEV-3: Autonomous Ops off or not ticked for the organization (`messages.PREFLIGHT["autonomy_off"]`, row `autonomous_ops`; assumption A-84-AO-OFF) and the 500-computer cap (row `cap`). A stop adds a row `stopped`. The platform organization's check shows `messages.API_DETAIL["platform_tenant"]` on the `autonomous_ops` row. The preflight key is `autonomous_ops`, not `autonomy` (84-02).

## TDD Gate Compliance

RED commit `5b8d09d4e` / GREEN `59e4a4b7f` (Task 1) and RED `64d5d72d4` / GREEN `edd6cb176` (Task 2). RED evidence: the target tests failed on the planned reason (`rings.save` and `start.preflight` did not exist; Task 2 showed 23 failed before any code). Task 3 has only a test commit: its behaviors (a stored per-computer ring index and a ring snapshot, nothing in the controller re-reading rings or groups) were already delivered by Task 2 and 84-01, so the tests passed on arrival; the acceptance grep (`rings.load|rings.membership` in controller.py) prints nothing.

## Issues Encountered

- `tests/conftest.py` turns every agent capability on for every test; the one test that needs patch installs switched off carries the `real_agent_capabilities` marker.
- The seeded agents share the IP 10.9.9.9, so a seeded platform computer with the same address made every customer computer "never-touch" (the built-in list holds platform addresses, working as designed); the platform test gives its computer a different address.

## Known Stubs

None. The platform route, the Rollouts tab and the Start dialog that call these functions are plans 84-09, 84-17 and 84-18.

## Threat Flags

None. T-84-19 (group ids resolved inside the tenant, foreign or deleted refused), T-84-20 (ordered claims, loser releases and answers already_in_rollout), T-84-21 (platform tenant refused, never-touch listed and never claimed, only the tenant's own agents read) and T-84-22 (500-computer cap) are implemented and tested.

## User Setup Required

None. Nothing was deployed, restarted or migrated; the private test mongod was stopped.

## Next Phase Readiness

- 84-09 maps `PreflightBlocked` to 422 `{rows}`, `AlreadyInRollout` to 409 `already_in_rollout`, `RingsError` to 422 with `.detail`, and calls `rings.save(db, tenant, items, actor=...)` with an actor like `{username, display}` (a `{id, name}` actor also works).
- `leftOut` entries have reason codes `agent_too_old | capability_off | unsupported_os | busy | never_touch | in_rollout` plus `rolloutName`; the card (84-12) maps them to `CANNOT_TAKE` / `HOST_RESULT["left_out"]`.
- `rings.resolve` is also available to any reader that must show only live groups.

## Self-Check: PASSED

- Created files exist (`test_patch_rollout_rings.py`, `test_patch_rollout_claims.py`); commits 5b8d09d4e, 59e4a4b7f, 64d5d72d4, edd6cb176, a4b676191 are ancestors of HEAD.
- Acceptance criteria re-run: `def save|def validate` in rings.py = 2; `ringName` in agent_group_endpoints.py >= 1; `def preflight` = 1; `protected.check` >= 1; no `rings.load|rings.membership` in controller.py; the concurrency test asserts one active claim per agent.
- Verification: rings, claims and tracer tests pass on a private mongod; all `test_autonomous_ops_*.py` and `test_patch_rollout_*.py` together: 1200 passed, 0 skipped (6 min 58 s); ruff clean; every touched file under 500 lines (start.py 387, tracer test 497).

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
