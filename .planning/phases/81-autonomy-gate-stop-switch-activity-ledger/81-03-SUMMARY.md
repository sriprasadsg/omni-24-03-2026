---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 03
subsystem: background-tasks
tags: [distributed-lock, lock-renewal, tenant-isolation, agent-status, mongo, pytest, gate]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger
    provides: plans 81-01 and 81-02 (autonomous_ops package, permissions); independent of both at the code level
provides:
  - "distributed_lock.renew_lock and lock_with_renewal (handle.token, acquired, lost) for single-runner sweeps"
  - "ResponseOrchestrator.is_duplicate_task scoped to one tenant on both queries, fail closed on empty tenant"
  - "monitor_agent_status with id-first selection, AGENT_STATUS_POLL_SEC and AGENT_OFFLINE_AFTER constants, exact-agents notification"
  - "scheduled legacy remediation loop and its startup registration removed"
affects: [81-04, 81-05, 81-06]

actuals:
  tokens: 11000
  tasks: 3
  commits: 3

plan_head_before: be342411a28d4708257aea19ab9e412534e5551f
plan_head_after: bafe9a519e349d9e42fcbb529075448b497b8154
commits: 3

tech-stack:
  added: []
  patterns:
    - "Long sweeps hold a short-TTL lock via lock_with_renewal and stop when handle.lost flips"
    - "Select-then-update-by-id so notifications name exactly the rows a pass changed"

key-files:
  created:
    - backend/tests/test_monitor_agent_status.py
    - backend/tests/test_response_orchestrator_tenant.py
    - .planning/todos/completed/2026-08-17-fix-stale-capability-count-assertions-in-integration-rs.md
  modified:
    - backend/app_background_tasks.py
    - backend/app_startup.py
    - backend/distributed_lock.py
    - backend/response_orchestrator.py
    - backend/tests/test_distributed_lock.py

key-decisions:
  - "GATE-12 premise did not hold: monitor_agent_status already slept 30 s, not 3600 s; GATE-12 is met by pinning the cadence with constants and a frozen-clock test and by fixing the wrong-agent notification"
  - "Update filter follows the plan ({id in ids, status Online}) without a second lastSeen guard; a heartbeat landing between select and update is the accepted race"
  - "lock_with_renewal treats repeated renew errors as lost once a full TTL passes without a successful renewal"

requirements-completed: [GATE-11, GATE-12, GATE-05]

coverage:
  - id: D1
    description: "Stale Online agents flip Offline and exactly those agents are broadcast and notified; exact 5-minute boundary stays Online; empty pass does nothing"
    requirement: GATE-12
    verification:
      - kind: integration
        ref: "backend/tests/test_monitor_agent_status.py (real Mongo: right-agents, empty, exact-threshold)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cadence pinned: 30 s poll, 5 minute offline threshold, pass runs every iteration, no sleep over 300 s"
    requirement: GATE-12
    verification:
      - kind: unit
        ref: "backend/tests/test_monitor_agent_status.py::test_cadence_constants_and_every_iteration_runs_the_offline_pass"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live cadence on the real fleet (stop an agent, see it Offline within about 5 minutes with a notification naming it)"
    requirement: GATE-12
    verification: []
    human_judgment: true
    rationale: "Needs the user to restart the backend and stop a real agent; not testable here (A-81-LIVE-CADENCE)"
  - id: D4
    description: "renew_lock / lock_with_renewal hold a 1 s lock for 3 s, report loss, release by token; crashed holder expires"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_distributed_lock.py (renew, expired, held-past-ttl, busy, vanished-document tests, real Mongo)"
        status: pass
    human_judgment: false
  - id: D5
    description: "is_duplicate_task is tenant-scoped on both queries and fails closed on an empty tenant"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_response_orchestrator_tenant.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "Nothing scheduled can start the legacy remediation cycle"
    requirement: GATE-05
    verification:
      - kind: unit
        ref: "backend/tests/test_monitor_agent_status.py::test_legacy_remediation_loop_is_not_scheduled"
        status: pass
    human_judgment: false
  - id: D7
    description: "Folded Rust todo closed: integration suite green, todo moved to completed, no Rust source change"
    verification:
      - kind: other
        ref: "cd agent-install/omni-agent-rs && cargo test --offline --test integration"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 03: Background-task hardening Summary

**Mongo lock renewal for single-runner sweeps, tenant-scoped duplicate-task checks, an agent offline monitor that notifies exactly the agents it flipped on a pinned 30 s / 5 min cadence, and the scheduled legacy remediation loop removed.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-10-26T07:50:00Z (approximate)
- **Completed:** 2026-10-26T08:05:00Z
- **Tasks:** 3
- **Files modified:** 9 (5 modified, 3 created, 1 moved todo)

## Accomplishments

- `monitor_agent_status` now selects the stale Online agents first, updates them by id, and broadcasts and notifies that list only. Before, the notified list came from a second query for every Offline agent older than the threshold, so already-Offline stale agents were re-announced on every flip. `AGENT_STATUS_POLL_SEC = 30` and `AGENT_OFFLINE_AFTER = 5 min` are named constants, the sleep moved to the end of the pass so the first pass runs at startup, and the tenant ContextVar reset per iteration is kept.
- `distributed_lock.renew_lock` (token + unexpired only, never resurrects an expired lock) and `lock_with_renewal` (background renewal, `handle.lost`, release by token). Proven on a real MongoDB: a 1 s TTL held for 3 s under renewal blocks a second acquire; without renewal it is reacquirable after expiry.
- `ResponseOrchestrator.is_duplicate_task` filters both queries by `tenantId` and returns True for an empty tenant (fail closed).
- `autonomous_remediation_loop`, its import and its `app_startup` registration are deleted; an AST test proves nothing schedules it.
- Folded Rust todo closed (D-24 (e)): no source change.

**Cargo result:** `test result: ok. 21 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 9.45s`

**GATE-12 premise did not hold (D-24 (d)):** the plan's originating claim of a 3600 s sleep in `monitor_agent_status` was wrong; the loop already slept 30 s with a 5 minute threshold. GATE-12 was satisfied by pinning that cadence in a test and fixing the wrong-agent notification, which was the real defect. The user should be told.

## Task Commits

1. **Task 1 (tracer): offline sweep notifies exactly the agents it flipped, pinned cadence** - `c0d038976` (feat)
2. **Task 2: lock renewal and tenant-filtered is_duplicate_task** - `1ea81c460` (feat)
3. **Task 3: remove legacy remediation loop, close folded Rust todo** - `bafe9a519` (feat)

**Plan metadata:** committed separately (docs: complete plan).

Tests were written and run red before each implementation, then committed together with it (one commit per task rather than separate test/feat commits).

## Files Created/Modified

- `backend/app_background_tasks.py` - monitor rewrite and constants; legacy loop and import removed
- `backend/app_startup.py` - legacy loop registration removed
- `backend/distributed_lock.py` - `renew_lock`, `LockHandle`, `lock_with_renewal`
- `backend/response_orchestrator.py` - tenant filter and fail-closed guard in `is_duplicate_task`
- `backend/tests/test_monitor_agent_status.py` - 6 tests (right agents, empty, exact threshold, cadence, tenant reset, legacy loop absent)
- `backend/tests/test_response_orchestrator_tenant.py` - 4 tests on real Mongo
- `backend/tests/test_distributed_lock.py` - 6 real-Mongo renewal tests appended after the last test
- `.planning/todos/completed/2026-08-17-fix-stale-capability-count-assertions-in-integration-rs.md` - moved from pending, resolution note appended

## Decisions Made

- Followed the plan's update filter exactly (`id in ids`, `status Online`). A heartbeat landing between the select and the update could still be flipped; the next heartbeat restores it. Not worth a second guard that would break "notified = flipped".
- `lock_with_renewal` marks the lock lost on a definitive failed renewal immediately, and on repeated renewal errors once a full TTL passes without a success.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test fixture import path**
- **Found during:** Task 1
- **Issue:** `from _mongo_test_db import mongo_db` fails; the project imports it as `tests._mongo_test_db`
- **Fix:** used `from tests._mongo_test_db import mongo_db` in the new test modules
- **Files modified:** backend/tests/test_monitor_agent_status.py
- **Committed in:** c0d038976

**2. [Process] Tracer gate with a human-check**
- The tracer's `<verify>` carries a `<human-check>` (live cadence), which under the executor rules would STOP for a checkpoint. The plan marks it `autonomous: true` and assumption A-81-LIVE-CADENCE defers the live check to the user after a backend restart, which the shared-tree rules forbid doing here. I re-ran the automated verify (10 passed) and continued; the live check stays a user step below.

**3. [Process] Plan commit ledger written late**
- The `gsd-plan-head-before-81-03` ledger was created after the first commit by taking its parent (`be342411a`), the true pre-plan HEAD. The measured commit count (3) is correct.

---

**Total deviations:** 1 auto-fixed (1 blocking) plus 2 process notes
**Impact on plan:** None on scope or behavior.

## Issues Encountered

- `backend/tests/test_distributed_lock.py`: the four older tests in the COMMITTED file (HEAD) fail against HEAD's `distributed_lock.py` because they mock `db._db._distributed_locks` while the source uses `db._db["_distributed_locks"]`. The user's uncommitted rewrite of that file (with `_mock_db_with_coll`) fixes them; I did not touch or stage it. My six new tests are self-contained and pass against the committed content. Not caused by this plan.
- `python -c "import app_startup, app_background_tasks"` needs `ENVIRONMENT=development JWT_SECRET_KEY=...` in this shell (production-mode fail-closed check); with those set it prints ok.

## Known Stubs

None.

## Threat Flags

None. No new endpoints or trust boundaries; T-81-10 through T-81-13 mitigated as planned.

## User Setup Required

None for code. Steps left for the user (not run here, per shared-tree rules):
- Restart `omni-backend.service` to load the new monitor, lock and orchestrator code (the backend runs from this checkout without auto-reload).
- Live GATE-12 check after the restart: stop one agent, confirm it shows Offline within about 5 minutes and the notification names that agent only.
- Uncommitted user work in `backend/app_background_tasks.py` (telemetry retention loop), `backend/app_startup.py` (its registration) and `backend/tests/test_distributed_lock.py` (mock rewrite) was left unstaged and uncommitted, confirmed by `git diff` after each commit.

## Next Phase Readiness

- 81-04 can register its reconciler in the area where the legacy loop registration was; `lock_with_renewal` is ready for it.
- No blockers.

## Self-Check: PASSED

- Files exist: test_monitor_agent_status.py, test_response_orchestrator_tenant.py, completed todo (pending copy absent).
- Commits found in HEAD ancestry: c0d038976, 1ea81c460, bafe9a519.
- Acceptance greps: constants count 5 (>= 3); `renew_lock`/`lock_with_renewal` count 2; `"tenantId": tenant_id` count 3; no file under agent-install/ staged.
- Plan verification: 33 passed across monitor, lock, scheduler-lock, finops-lock, orchestrator-tenant and fleet-observability tests; cargo 21 passed.

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
