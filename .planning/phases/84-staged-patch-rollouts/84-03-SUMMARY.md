---
phase: 84-staged-patch-rollouts
plan: 03
subsystem: autonomous-ops
tags: [patch-rollout, approvals, approval-lines, dispatcher, halt, maintenance-windows, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-01 controller, canary install, settle, windows, store; 84-02 rollout/messages.py and the payload types
  - phase: 81-autonomous-ops-safety-core
    provides: approvals.approve / deny, gate.decide / gate.execute, decision ledger
provides:
  - lines.py - one approval row per computer, grouped as a line; approve_line and deny_line (one approvals.approve / deny per row); closed_line for the halt
  - dispatcher.py - the patch_rollout approvals dispatcher: sends inside the window only, host re-checked at dispatch, dispatch_approved for the controller
  - lifecycle.halt - R11 halt (status CAS, rollout_closed for open rows, rollout_halted for unfetched instructions)
  - canary split (D-05, D-06) and approval-only later rings in installs.py; settle.py settles automatic and approval rows into one host state
affects: [84-04, 84-08, 84-10, 84-13, 84-22]

requirements-completed: [PTCH-06, PTCH-05, PTCH-01]

actuals:
  tokens: 23000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "a line = one ring's approval rows sharing reason.inputs {rolloutId, ring, line}; one ledger row per computer (OQ2)"
    - "an approved row is claimed with one compare-and-set to dispatching before gate.execute, so a click and a tick that meet write one instruction"
    - "the job document of an approved install is created at dispatch (ensure_job upsert), so a card nobody approves leaves no In Progress job"

key-files:
  created:
    - backend/autonomous_ops/rollout/lines.py
    - backend/autonomous_ops/rollout/dispatcher.py
    - backend/tests/test_patch_rollout_lines.py
    - backend/tests/test_patch_rollout_dispatcher.py
  modified:
    - backend/autonomous_ops/rollout/installs.py
    - backend/autonomous_ops/rollout/settle.py
    - backend/autonomous_ops/rollout/lifecycle.py
    - backend/autonomous_ops/rollout/controller.py
    - backend/autonomous_ops/rollout/messages.py
    - backend/autonomous_ops/decision_row.py
    - backend/autonomous_ops_endpoints.py
    - backend/tests/test_patch_rollout_tracer.py

key-decisions:
  - "OQ2 (planner decision, recorded): every install, restart and revert is one ledger row per host, never one anchor row for many hosts. Reasons: each host keeps its own patch list and job, so 2.1.16 agents (which fail ids of another OS) can take approved installs without a new rollout mode; each host's revert is the plain undo of its own row (84-13); Activity shows one row per computer as 81 D-17 does. The cost is a line-level approve that runs approvals.approve once per row (route in 84-10); single-use, expiry, re-validation and permission rules are unchanged. UI-SPEC deviation DEV-1 is recorded in 84-10 and 84-15; the governing records are 84-RESEARCH.md 'Open Questions (RESOLVED)' item 2 and 84-UI-SPEC.md 'Planning Deviations (pending user review)'. The user has not reviewed either yet."
  - "Cards are raised only while a window is open (as the plan words it); an approved row waits for the window and is sent by dispatch_approved. A click that meets a closed window answers when 'window' with windowOpensAt"
  - "A not_reversible deferral ends the automatic row executed with reasonCode rollout_not_reversible (nothing installed, not a failure, so it never feeds the circuit breaker); the host remembers the ids in deferredIds and the controller raises the approval row (attempt + 1)"
  - "An approval row that never reached its computer (instruction refused or cancelled by a stop) is failed rollout_not_delivered and asked for again as a new card, at most MAX_ATTEMPTS in all, then the host reads failed"
  - "Host fields added: lineActionIds, linePatchIds (ids an approval row exists for), deferredIds, installedIds, lineSettled, autoSettled, waitReason; ring states waiting_for_approval and waiting_for_window are now set by the controller from the host states"

patterns-established:
  - "Settling reads each row by its own ledger state and its own job; the host state is derived from all of them (installing, waiting + approval, installed, failed), written only when it changed"
  - "A halted rollout still settles: a result for an instruction already sent is recorded on the host and its row"

coverage:
  - id: D1
    description: "Every install after the canary waits for approval: one awaiting_approval row per computer (playbook_raised), nothing sent, no job created, ring waiting_for_approval"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_after_the_canary_passes_ring_one_gets_one_approval_row_per_computer_and_nothing_is_sent"
        status: pass
    human_judgment: false
  - id: D2
    description: "Canary split: a host without patch_reversible_check, a restart-needing name and a not_reversible deferral each become an approval row; only the rest installs on its own; a host is installed only when both rows settled"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_a_canary_host_splits_into_one_automatic_row_and_one_approval_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_a_not_reversible_deferral_ends_the_automatic_row_and_raises_an_approval_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_the_host_is_installed_only_when_the_automatic_and_the_approval_row_have_both_settled"
        status: pass
    human_judgment: false
  - id: D3
    description: "The hourly limit decides at most the remaining automatic budget per tick in (hostname, agent id) order and never makes a rate_limit card; shadow tenants record simulations and no card"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_the_hourly_limit_decides_one_canary_install_and_never_makes_a_rate_limit_card"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_a_shadow_tenant_records_simulations_and_no_card"
        status: pass
    human_judgment: false
  - id: D4
    description: "One approve_line click approves each awaiting row once (a second click is already_handled), sends inside the window with expiresAt at the occurrence end, and with the window closed leaves rows approved until the first open tick sends them once"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_dispatcher.py#test_one_click_approves_the_whole_line_and_each_row_is_sent_once_inside_the_window"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_dispatcher.py#test_with_the_window_closed_the_rows_stay_approved_and_the_first_open_tick_sends_them_once"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_dispatcher.py#test_a_click_and_a_tick_that_meet_on_one_row_write_one_instruction"
        status: pass
    human_judgment: false
  - id: D5
    description: "At dispatch time a released, unticked, offline, busy or unsupported computer is left approved and never sent; one line's approval never reaches another line or tenant; deny writes nothing; a stop changes nothing"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_dispatcher.py#test_a_computer_that_cannot_take_an_approved_row_at_dispatch_time_is_never_sent_anything"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_dispatcher.py#test_a_restart_row_for_a_computer_without_the_restart_token_is_never_sent"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_dispatcher.py#test_one_lines_approval_never_approves_another_line_or_another_tenants_row"
        status: pass
    human_judgment: false
  - id: D6
    description: "A denied or expired line halts the rollout at that ring (install_denied, restart_denied, approval_expired), closes every other open row (rollout_closed), fails still-pending instructions (rollout_halted) so delivery refuses them, keeps a sent instruction's row and records its late result, and nothing of a halted rollout can be approved"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_a_denied_install_line_halts_the_rollout_at_that_ring_and_closes_every_other_open_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_a_halt_ends_a_row_whose_instruction_nobody_fetched_and_delivery_refuses_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lines.py#test_nothing_of_a_halted_rollout_can_be_approved_any_more"
        status: pass
    human_judgment: false

duration: 31min
completed: 2026-11-06
status: complete
plan_head_before: 21c4072e53c7d17911ec9838d0634146e872521f
commits: 3
plan_head_after: 5b8ce82e73acee757733fb3d781797ec839115ee
---

# Phase 84 Plan 03: Approval Lines Summary

**Every rollout step that is not an automatic canary install is now one approval row per computer, approved with one click per line per ring through the existing approvals path, sent only inside the window after the computer is checked again, and a deny or an unanswered 24 hours halts the rollout at that ring and closes everything still open.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-11-06T14:20Z
- **Completed:** 2026-11-06T14:51Z
- **Tasks:** 3
- **Files:** 12 (4 created, 8 modified)

## Accomplishments

- `lines.raise_line` asks the gate for one `playbook_raise` row per computer, so each is a card (`playbook_raised`) in `awaiting_approval`, and a shadow tenant records a simulation and no card. `approve_line` and `deny_line` loop `approvals.approve` / `approvals.deny` over the awaiting rows of one rollout, ring and line and answer the `LineDecisionResult` shape of `services/patchRollouts/types.ts`.
- The canary ring splits each computer's patches: no `patch_reversible_check` token means all of them need a person; a name from the restart-needing list (D-06) or a patch the agent deferred as `not_reversible` (D-05) becomes an approval row; the rest installs on its own. The hourly limit bounds the automatic installs of a pass (computers in (hostname, agent id) order), and never makes a rate-limit card.
- `dispatcher.send` is the approvals dispatcher for `patch_rollout`: window closed answers `deferred` with `windowOpensAt` and leaves the row `approved`; open re-checks rollout running, claim, capability, online, token and no other In Progress patch job, then claims the row with one compare-and-set and calls `gate.execute` with `expires_at` at the occurrence end. The controller sends approved rows when the window opens.
- `lifecycle.halt` (status compare-and-set, `rollout_closed` for open rows, `rollout_halted` for rows whose instruction nobody fetched) replaces the inline halt; the controller halts on a denied or expired line of the current ring.
- `settle.py` derives one state per computer from its automatic row and every approval row: installing, waiting with `waitReason` approval, installed only when all have settled, or failed.
- All 1024 `test_autonomous_ops_*.py` tests and all 137 `test_patch_*.py` tests pass on a private mongod with no skips.

## Task Commits

1. **Task 1: Approval line rows; canary installs that are not reversible or not checkable become lines** - `86f72a147` (feat). The dispatcher, `lifecycle.halt` and the controller wiring are in this commit too, because `lines`, `settle` and `controller` import them; their own tests are the next two commits.
2. **Task 2: Window-deferred dispatcher and line approve and deny (tests, endpoints import)** - `36d094077` (test)
3. **Task 3: A denied or expired line halts the rollout (tests)** - `5b8ce82e7` (test)

**Plan metadata:** the docs commit following this summary.

## Decisions Made

See `key-decisions`. The OQ2 decision (one row per computer, line-level approve) is recorded there in full as the plan asks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] The approving process registers the dispatcher**
- **Found during:** Task 2
- **Issue:** the plan wants `approvals.approve` on a rollout row to find the dispatcher in a fresh process that imports `autonomous_ops_response_endpoints`; a fresh import of that module registered neither `patch_rollout` nor `security_response` (those are registered by the sweep modules the server imports), so a process that only served approvals would answer `no_dispatcher`.
- **Fix:** `autonomous_ops_endpoints.py` (the module that calls `approvals.approve`, imported by the response endpoints) imports `rollout.dispatcher`; a subprocess test pins it.
- **Files modified:** `backend/autonomous_ops_endpoints.py`
- **Commit:** `36d094077`

**2. [Rule 1 - Ordering] The job document is created when the row is sent, not when the card is raised**
- **Found during:** Task 1
- **Issue:** the plan's `raise_line` inserts the host's patch job first. A card nobody approves (denied, expired, closed by a halt) would leave an In Progress job that marks the computer busy for every other patch job. Same reasoning as the 84-01 deviation for the canary.
- **Fix:** the card's params carry the new job id; `dispatcher.ensure_job` upserts the job document just before `gate.execute`.
- **Commit:** `86f72a147`

**3. [Rule 2 - Missing critical functionality] The dispatcher claims the row before it writes the instruction**
- **Found during:** Task 2
- **Issue:** `gate.execute` accepts both `approved` and `dispatching` rows, so an approval click and a controller tick that meet on one approved row could write two instructions.
- **Fix:** `send` moves the row `approved` to `dispatching` with one compare-and-set first; the loser answers `deferred` / `already_sent`. Pinned by a test.
- **Commit:** `86f72a147`

**4. [Rule 2 - Missing critical functionality] A refused or never-delivered approval row asks again, bounded**
- **Found during:** Task 1
- **Issue:** an approval row whose instruction was refused at delivery or cancelled by a stop would leave its computer waiting forever (the old retry only covered the automatic row).
- **Fix:** such a row is failed `rollout_not_delivered` and its ids go back to unresolved so a new card is raised, at most `MAX_ATTEMPTS` in all, then the host reads failed. A row refused at approval time marks the host failed with the refusal text.
- **Commit:** `86f72a147`

**5. [Rule 1 - Test change] Two 84-01 tracer tests changed**
- **Found during:** Task 1
- **Issue:** `test_a_host_that_cannot_check_reversibility_is_never_installed_automatically` and `test_a_package_that_usually_needs_a_restart_is_not_installed_automatically` asserted no ledger row at all; this plan's behaviour is exactly one `awaiting_approval` row there.
- **Fix:** both now assert that one card exists and that no instruction was written (the safety property they protected). No other 81, 83 or 84 test changed.
- **Commit:** `86f72a147`

**6. [Rule 2 - Copy] Four sentences added to `rollout/messages.py`**
- `LINE_RESULT` (not_running, not_found, stopped, already_handled, nothing_open, waiting_computer) so no rollout module holds a sentence of its own. The `rollout_not_reversible` reason code reuses `ACTIVITY.not_reversible_why` as its text and has no `REASON_TEXT` entry (the row carries `reasonText` directly).

---

**Total deviations:** 6 (4 missing critical, 1 ordering, 1 test change). **Impact on plan:** none on the plan's truths; all tighten failure behaviour.

## Issues Encountered

- `tests/conftest.py` turns every agent capability on for every test; the capability_off dispatch test carries the `real_agent_capabilities` marker.
- The reconciler still does not skip `dispatcher == "patch_rollout"` rows and delivery does not yet enforce `expiresAt` (both assigned to 84-04). Until then a rollout row left `dispatching` past the reconciler's stuck bound could be ended by it, and a stale instruction is not yet refused at the agent poll. Not deployed (the controller has no background loop until 84-22).
- `approvals.expire_due` is what expires an unanswered card; it runs in the reconciler's pass, and the controller halts when it sees the expired row. The controller does not call it itself.

## Known Stubs

- Restart (`reboot`) and revert-restart lines: `raise_line`, `approve_line`, `deny_line`, `closed_line` and the dispatcher handle them (tested with a `reboot_host` card), but nothing yet raises them or settles their results; 84-08 and 84-13 do. `settle._settle_lines` settles the `install` line only.

None of these prevent this plan's goal.

## Threat Flags

None beyond the plan's threat model. T-84-08 (approve per row through `approvals.approve`, scope fixed to rollout, ring and line, other tenant refused), T-84-09 (dispatch-time re-check, halt expires every open row), T-84-10 (pending install rows of a halted ring fail so delivery refuses them) and T-84-11 (canary budget from `count_auto_since`) are implemented as planned. PROH-84-04b holds: there is no approve-all; rows are always found by rollout, ring and line together.

## User Setup Required

None. Nothing was deployed, restarted, published or migrated; the private test mongod (port 27998) was stopped.

## Next Phase Readiness

- 84-04 must enforce `expiresAt` in `delivery.hold_back_autonomous` and make the reconciler skip the rollout dispatcher.
- 84-10 can call `lines.approve_line` / `lines.deny_line` directly; the answer is the `LineDecisionResult` shape.
- 84-08 and 84-13 reuse `lines.raise_line` with `line` `reboot` / `revert_reboot` and extend `settle._settle_lines`.

## Self-Check: PASSED

- Created files exist: `lines.py`, `dispatcher.py`, `test_patch_rollout_lines.py`, `test_patch_rollout_dispatcher.py`; commits `86f72a147`, `36d094077`, `5b8ce82e7` are ancestors of HEAD.
- Acceptance criteria re-run: `playbook_raise=True` in lines.py (1), `count_auto_since` in installs.py (2), no `rate_limit` row in the rate-cap test; `register_dispatcher` in dispatcher.py (1), `expires_at` (2), the closed-window test asserts 0, 3, 3 ring-one instructions; `def halt` (1), `rollout_closed` (3); every rollout module under 500 lines (largest: messages.py 321).
- Plan verification: lines + tracer + gate + response_rows (89 passed), dispatcher + lines + approvals + dispatch_binding (96 passed), lines + tracer + structural + stop (103 passed); all `test_autonomous_ops_*.py` 1024 passed; all `test_patch_*.py` 137 passed; 0 skipped.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
