---
phase: 84-staged-patch-rollouts
plan: 01
subsystem: autonomous-ops
tags: [patch-rollout, gate, registry, maintenance-windows, mongodb, python]

requires:
  - phase: 81-autonomous-ops-safety-core
    provides: gate.decide / gate.execute, decision ledger, registry, dispatch binding
  - phase: 83-autonomous-response
    provides: sweep tenant-loop shape, agent_support token and online checks
provides:
  - install_patches as a fourth automatic action limited to the patch_rollout dispatcher (ActionSpec.dispatchers)
  - gate.execute(expires_at=) writing expiresAt on the stamped instruction
  - rollout package skeleton with real behaviour (windows, rings, start, canary install, settle, health, lifecycle, per-tenant tick)
  - unique partial index one_active_rollout_per_host (store.ensure_indexes, called by migration 031 in 84-22)
affects: [84-02, 84-03, 84-04, 84-05, 84-06, 84-07, 84-08, 84-16, 84-22]

actuals:
  tokens: 25000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "dispatcher allow-list on a registry spec, enforced at decide time (gate._step_class) and at delivery (dispatch_check.bind)"
    - "controller settles installs from patch_deployment_jobs.agentResults, not from the reconciler"
    - "health verdict as a pure function over plain per-host signal dicts"

key-files:
  created:
    - backend/autonomous_ops/rollout/__init__.py
    - backend/autonomous_ops/rollout/store.py
    - backend/autonomous_ops/rollout/windows.py
    - backend/autonomous_ops/rollout/rings.py
    - backend/autonomous_ops/rollout/start.py
    - backend/autonomous_ops/rollout/installs.py
    - backend/autonomous_ops/rollout/settle.py
    - backend/autonomous_ops/rollout/health.py
    - backend/autonomous_ops/rollout/lifecycle.py
    - backend/autonomous_ops/rollout/controller.py
    - backend/tests/rollout_support.py
    - backend/tests/test_patch_rollout_tracer.py
  modified:
    - backend/autonomous_ops/registry.py
    - backend/autonomous_ops/gate.py
    - backend/autonomous_ops/dispatch_check.py
    - backend/autonomous_ops/messages.py
    - backend/tests/test_autonomous_ops_registry.py

key-decisions:
  - "install_patches is a deliberate fourth automatic action (OQ1); the pinned AUTO test changed with a comment citing PTCH-06"
  - "A decide refusal for another dispatcher is unrecorded (record=False): it writes no ledger row, so a hostile or mistaken caller cannot flood the ledger"
  - "rollback_patches carries no dispatcher restriction (undo_only is already unreachable as a main step); only install_patches is limited"
  - "The per-host patch_deployment_jobs document is inserted after gate.decide returns dispatching (and before gate.execute), not before decide, so a refused, simulated or approval-held decision leaves no orphan In Progress job"
  - "Hosts whose decision is held by the gate (limits) keep the row id on the host and are not re-decided; an install that never reached the host is retried, at most MAX_ATTEMPTS (3) in all, then the host reads failed"
  - "Canary installs per tick are capped at 20 minus the automatic actions in the last hour (research Pitfall 6) so the 21st never becomes an approval card by accident"

patterns-established:
  - "Rollout modules never write an agent queue and never name the autonomy stamp: all agent work goes through gate.decide then gate.execute"
  - "Times are aware UTC at every comparison (store.aware / store.parse_time); the driver returns naive datetimes"

requirements-completed: [PTCH-01, PTCH-05, PTCH-06, PTCH-07]

coverage:
  - id: D1
    description: "A canary host installs one reversible patch on its own inside the open window through the gate; exactly one ledger row and one stamped instruction, none while the window is closed or the agent cannot check reversibility"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_canary_installs_on_its_own_inside_the_window_and_the_result_settles_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_a_host_that_cannot_check_reversibility_is_never_installed_automatically"
        status: pass
    human_judgment: false
  - id: D2
    description: "The instruction expires at the end of the window occurrence open at dispatch; a tick with no open window (or an unreadable window or unknown zone) writes nothing"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_nothing_is_written_while_no_window_is_open"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_an_unknown_time_zone_reads_closed_and_the_tick_writes_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "The agent's result (real record_agent_patch_result path) settles host and ledger row; the ring passes only after its soak on a scan newer than the install; the rollout completes and releases every claim; a stale scan halts it"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_the_ring_passes_on_a_fresh_scan_and_the_rollout_completes_and_releases_its_claims"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_a_scan_that_is_not_newer_than_the_install_halts_the_ring_with_no_data"
        status: pass
    human_judgment: false
  - id: D4
    description: "install_patches is refused unregistered_action (and records nothing) from any other dispatcher at decide time, and dispatch_check.bind refuses it at delivery for a row of another dispatcher"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_install_patches_from_any_other_dispatcher_is_refused_and_records_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_delivery_binds_install_patches_only_for_a_rollout_row"
        status: pass
    human_judgment: false
  - id: D5
    description: "Two active rollouts can never claim one computer (unique partial index, claim_hosts reports the duplicate as left out)"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_no_two_active_rollouts_can_hold_one_computer"
        status: pass
    human_judgment: false
  - id: D6
    description: "Legacy (old maintenance screen) and one-time windows read correctly; one tenant's fault or a lost() signal never touches the next tenant's rollout"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_an_old_screen_window_row_in_the_database_opens_the_tick"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_tracer.py#test_an_error_in_one_tenant_is_logged_and_the_next_tenant_still_runs"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-11-06
status: complete
plan_head_before: 915d8a21e34379da55e8ab0f3a74df2a69019090
commits: 3
plan_head_after: c37710f45448ff8ebde7bb852c9b0937bbb2d047
---

# Phase 84 Plan 01: Staged Patch Rollouts Tracer Summary

**install_patches as a fourth automatic action restricted to the rollout dispatcher, with a window-aware controller that installs one reversible patch on the canary host through the gate, settles it from the agent's own result, soaks it on a fresh scan, and completes the rollout.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-11-06T13:38:05Z
- **Completed:** 2026-11-06T14:00Z
- **Tasks:** 3
- **Files modified:** 17 (12 created, 5 modified)

## Accomplishments

- The whole backend path works on a real database: operator Start, one canary install decided by `gate.decide` and sent by `gate.execute` with `expiresAt` equal to the open window occurrence end, result settled from `patch_deployment_jobs.agentResults`, ring soak, fresh-scan health verdict, completion with every claim released.
- Fail-closed edges: no window, an unreadable window row, an unknown time zone, an agent without `patch_reversible_check`, a package from the usually-restart-needing families, a stop or Off tenant, and any other dispatcher all produce no row and no instruction.
- The unique partial index `one_active_rollout_per_host` makes the host claim a database guarantee; `store.ensure_indexes` is the single function migration 031 (84-22) will call.
- Phase 81 and 83 tests unchanged except the pinned AUTO tuple: all 1018 `test_autonomous_ops_*.py` tests pass (private mongod, no skips).

## Task Commits

1. **Task 1: Tracer - canary installs one reversible patch inside the window, result settles it** - `a8e4b7093` (feat)
2. **Task 2: Soak, fresh-scan health check and completion** - `eff4115cc` (feat)
3. **Task 3: Fail-closed edges (legacy/one-time windows, delivery-time dispatcher check, tenant isolation)** - `c37710f45` (feat)

**Plan metadata:** the docs commit following this summary.

## Files Created/Modified

- `backend/autonomous_ops/registry.py` - `ActionSpec.dispatchers`; `install_patches` (auto, undo `rollback_patches`, dispatcher patch_rollout) and `rollback_patches` (undo_only)
- `backend/autonomous_ops/gate.py` - `_step_class` refuses an action for a dispatcher outside its allow-list (unrecorded); `execute(expires_at=)`
- `backend/autonomous_ops/dispatch_check.py` - `bind` delivery-time half of the allow-list
- `backend/autonomous_ops/messages.py` - labels for both commands and 12 rollout reason texts (declared once so later plans never edit this file)
- `backend/autonomous_ops/rollout/` - constants, store/claim/indexes, windows (recurring, legacy, one-time, next_open), rings, start, installs, settle, health, lifecycle, controller
- `backend/tests/rollout_support.py`, `backend/tests/test_patch_rollout_tracer.py` (29 tests), `backend/tests/test_autonomous_ops_registry.py`

## Decisions Made

See `key-decisions` above. Phase 81 or 83 test expectations changed: only `test_autonomous_ops_registry.py` - the pinned `AUTO` tuple gained `install_patches` (PTCH-06 / OQ1, comment added) plus a new test for the dispatcher restriction. No other existing test needed a change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Retry cap and rate budget on the canary install**
- **Found during:** Task 1 (installs.py)
- **Issue:** The plan moved a refused `gate.execute` to failed and back to waiting with no bound, so a persistently refused dispatch would write a new failed ledger row every tick; and a canary above 20 hosts would let the 21st decision escalate to an approval card.
- **Fix:** `MAX_ATTEMPTS = 3` (then the host reads failed with the not-delivered text) and a per-tick budget of `20 - recent automatic actions` (research Pitfall 6). Added `MAX_ATTEMPTS` to `rollout/__init__.py`.
- **Files modified:** `backend/autonomous_ops/rollout/__init__.py`, `installs.py`
- **Committed in:** a8e4b7093

**2. [Rule 1 - Ordering] Job document inserted after the decision, not before**
- **Found during:** Task 1
- **Issue:** Inserting the `patch_deployment_jobs` document before `gate.decide` (as step 9 words it) would leave an "In Progress" job with no instruction whenever the decision is refused, simulated (shadow) or held for approval.
- **Fix:** The job id is generated first and carried in the decided params; the job document is inserted only when the decision is `dispatching`, immediately before `gate.execute`. Observable result is identical for the tracer.
- **Committed in:** a8e4b7093

**3. [Rule 2 - Missing critical functionality] Health verdict skips failed hosts in the no-data check**
- **Found during:** Task 2 (health.py)
- **Issue:** A failed host in a later ring (inside the allowed share) has no inventory or heartbeat signal and would otherwise mask the failure-share rule with a `no_data` halt.
- **Fix:** `ring_verdict` checks missing signals only on hosts that did not fail; failures are judged by the canary rule or the share rule.
- **Committed in:** eff4115cc

---

**Total deviations:** 3 auto-fixed (2 missing critical, 1 ordering). **Impact on plan:** none on the plan's truths; all three tighten failure behaviour. No scope creep.

## Issues Encountered

None. The reconciler does not yet skip `dispatcher == "patch_rollout"` rows (research C5, assigned to plan 84-04): until then a rollout row left `dispatching` past the reconciler's stuck bound could be ended `not_delivered` or `no_result` by the reconciler. The tracer settles rows itself on the tick, so it is unaffected. This is not deployed (the controller has no background loop until 84-22).

## Known Stubs

- `health.host_signals` reports `services` as `True` ("agent only"); the restart and watched-service checks arrive in 84-08 (stated in the plan).
- `controller._ring` only auto-installs ring 0; later rings wait for the approval line (84-03).
- `start.start_rollout` has the minimal refusals; 84-06 replaces them with the full preflight (stated in the plan).

None of these prevent this plan's goal. No UI exists in this plan.

## Threat Flags

None beyond the plan's threat model. T-84-01 (dispatcher allow-list at decide and delivery), T-84-02 (ids through `installable_patch_id` and intersected with the host's own pending list), T-84-03 (platform tenant refused at Start, `protected.check` per host) and T-84-04 (`expiresAt` set from the window end; enforcement at delivery is 84-04) are implemented as planned.

## User Setup Required

None - no external service configuration required. Nothing was deployed, restarted or migrated; the private test mongod was stopped.

## Next Phase Readiness

- 84-02..84-08 can build on `rollout/` by module name; `controller.tick(db, *, now, lost)` is the final signature 84-22 wraps in its locked loop.
- 84-04 must make `delivery.hold_back_autonomous` enforce `expiresAt` and make the reconciler skip the rollout dispatcher.

## Self-Check: PASSED

- Created files all exist (12 listed above); commits `a8e4b7093`, `eff4115cc`, `c37710f45` are ancestors of HEAD.
- Acceptance criteria re-run: registry/gate/dispatch_check greps, `one_active_rollout_per_host`, no `patch_instruction(` in rollout/, every touched file under 500 lines (largest: tracer test 489, gate.py 460).
- Plan verification: the Task 3 command (tracer, registry, gate, gate_order, dispatch_binding, approvals, structural) plus the copy gate - 211 passed, 0 skipped; all `test_autonomous_ops_*.py` - 1018 passed.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
