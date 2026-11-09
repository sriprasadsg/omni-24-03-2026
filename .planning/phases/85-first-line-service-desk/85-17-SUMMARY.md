---
phase: 85-first-line-service-desk
plan: 17
subsystem: service-desk
tags: [service-desk, worker, queue, deadline, distributed-lock, returns, migration, startup]
status: complete

requires: [85-07, 85-12, 85-13, 85-14, 85-15]
provides:
  - "backend/service_desk/worker.py: run_once (single-runner lock, stale running recovery, prepare pass, caps, 10-minute limit, one generation per pass, offline hand-off in one pass) and desk_loop (a pass every 5 s, the return sweep at most once an hour)"
  - "backend/service_desk/returns.py: sweep_due, the three-working-day return of a silent requester's ticket to a person"
  - "backend/migrations/032_service_desk.py: indexes only, through service_desk.store.ensure_indexes"
  - "backend/app_startup.py: one service_desk_worker task after the patch rollout controller"
  - "tests/service_desk_worker_support.py: world, Clock, stand_in, queue (shared by the worker and return tests)"
affects: [85-18, 85-19, 85-20, 85-21, 85-22, 85-23]

actuals:
  tokens: 13600
  tasks: 3
  commits: 3
plan_head_before: 102eb9b53cdd3c395759dc075319face867e624d
plan_head_after: 85b31bcd3e0e914bfe7335e6aab34e6f86d54183

tech-stack:
  added: []
  patterns:
    - "Lock-held pass: lock_with_renewal around the whole pass, handle.lost checked between jobs, no job is ever held across a lost lock for a second generation"
    - "The queue limit lives in a thin client wrapper (_Bounded) around the one model call: the timeout is cut to the time left and a reply at or after the limit is refused as a ModelTimeout, so the unchanged pipeline turns it into the busy hand-off and never posts it"
    - "Injected clock (a function) everywhere in the worker: tests move time inside the stand-in's generate handler"
    - "The return due time is recomputed from desk.postedAt with workdays.add_working_days in the tenant's zone and never stored"

key-files:
  created:
    - backend/service_desk/returns.py
    - backend/migrations/032_service_desk.py
    - backend/tests/test_service_desk_returns.py
    - backend/tests/service_desk_worker_support.py
    - backend/tests/test_service_desk_worker.py
  modified:
    - backend/service_desk/worker.py
    - backend/app_startup.py
    - backend/tests/test_service_desk_tracer.py

key-decisions:
  - "run_once now returns the counts of the pass (None only when another runner holds the lock); the tracer tests read the first closed job from counts['jobs'] instead of the old return value"
  - "The queue limit is enforced around the model call by a client wrapper in worker.py, not by editing pipeline.answer; pipeline.py is unchanged"
  - "The caps (tenant 10, deployment 30) count the waiting jobs in arrival order before a job is prepared, so a flood costs one cheap hand-off per job and no retrieval"
  - "A stale running job is dropped with reason stale_running and its ticket handed off busy only if the desk had not already answered it (desk.phase still queued); an unexpected error on a job does the same with reason error"
  - "The return sweep walks tenants and queries each with its tenantId (the desk_return_due index leads with tenantId), prefilters at postedAt <= now - 2 days and decides the exact due time per ticket in Python"

requirements-completed: [DESK-01, DESK-05]

coverage:
  - id: D1
    description: "One runner and one generation at a time: a second run_once gets None under the renewed lock; a pass that loses the lock stops between jobs"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_a_second_runner_gets_none_and_only_one_generation_is_made"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_a_pass_stops_when_the_lock_is_lost"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cheap stages first in arrival order: security and fulfilment tickets are handed off without a generate request while the VPN ticket is answered in the same pass; one generation per pass for the oldest job"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_cheap_stages_run_for_every_job_before_the_one_generation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_jobs_are_taken_in_arrival_order_and_only_the_oldest_ready_one_is_generated"
        status: pass
    human_judgment: false
  - id: D3
    description: "The 10-minute limit: nothing is generated for a ticket that arrived 10 minutes ago, nothing that cannot finish in time is started, the call timeout is cut to the time left, a reply at the limit is never posted"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_a_ticket_that_arrived_ten_minutes_ago_is_never_generated_for"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_no_generation_starts_that_cannot_finish_in_time"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_the_call_timeout_is_cut_to_the_time_left"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_an_answer_that_comes_back_after_the_limit_is_never_posted"
        status: pass
    human_judgment: false
  - id: D4
    description: "Queue caps, crash recovery, desk off, stop and no model: the 11th job of a tenant and the 31st overall are handed off busy, a crashed running job is dropped to a person, an Off desk drops silently, a stop hands off quietly, a missing model hands off every waiting ticket in one pass"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_the_eleventh_ticket_of_a_tenant_is_handed_off_at_once"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_the_thirty_first_ticket_of_the_deployment_is_handed_off_at_once"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_a_running_job_older_than_a_crashed_call_could_last_is_dropped_to_a_person"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_with_no_model_every_waiting_ticket_is_handed_off_in_one_pass"
        status: pass
    human_judgment: false
  - id: D5
    description: "The three-working-day return to a person at the due time (not a minute before), in the tenant's zone across a daylight saving change, never resolving or closing, Undo untouched, idempotent, one failure does not stop the rest"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_returns.py#test_a_ticket_is_returned_at_the_due_time_and_not_a_minute_before"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_returns.py#test_the_tenants_own_time_zone_decides_the_hour_across_a_daylight_saving_change"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_returns.py#test_a_return_never_resolves_or_closes_a_ticket_and_leaves_undo_alone"
        status: pass
    human_judgment: false
  - id: D6
    description: "Migration 032 creates every desk index, twice, and changes no document; the backend source starts one service_desk_worker task after the patch rollout controller"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_migration_032_creates_every_desk_index_twice_and_changes_no_document"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_worker.py#test_the_backend_starts_one_service_desk_task_after_the_patch_rollout_controller"
        status: pass
    human_judgment: false
  - id: D7
    description: "Real speed of the worker on this CPU with a real Ollama, and the desk starting on the live backend after the user's restart"
    requirement: "DESK-05"
    human_judgment: true
    rationale: "Ollama is not installed on this VM and the restart (which runs migration 032 and starts the worker) is the user's step; tests used a stand-in model and an injected clock"
---

# Phase 85 Plan 17: The desk runs by itself Summary

The first-line desk now runs as a background worker under a renewed single-runner lock, one generation at a time: cheap rules first for every waiting ticket, nothing started that cannot finish within 10 minutes of the ticket's arrival, nothing late ever posted, caps of 10 per tenant and 30 overall, crash recovery, an hourly three-working-day return of silent tickets to a person, migration 032 for the indexes and the startup task.

Duration: about 17 minutes (02:25 to 02:42 UTC on 2026-11-09). Tasks: 3. Files: 8 (5 created, 3 modified).

## Accomplishments

- **Task 1 (4f1220eb6), the worker.** `run_once(db, client=, now=, clock=)` runs under `lock_with_renewal` (ttl 120 s, renew 30 s), makes the unique indexes again when missing (skips the pass and logs when it cannot), recovers stale `running` jobs, prepares every waiting job (pending or ready) in `createdAt, id` order, then answers the oldest ready job that can still finish. A job at or past arrival + 10 minutes, or for which `now + runtime.estimate_seconds` reaches it, is handed off `service_desk_busy` without a generate request. The model call goes through `_Bounded`: its timeout is `min(call_timeout, time left)` and a reply landing at or after the limit raises `ModelTimeout`, which the unchanged pipeline turns into the busy hand-off. With the model offline every ready job is handed off `service_desk_offline` in the same pass. The tenant's 11th and the deployment's 31st waiting job are handed off busy. An Off desk drops a job silently (`dropped`, reason `desk_off`), a stop hands off `desk_stopped` with no notice (through the pipeline). Each closed job keeps `finishedAt` (a datetime for the TTL), `waitSeconds` and `runSeconds`; the generation time itself is already on the desk row (`reason.inputs.genMs`, 85-13).
- **Task 2 (7f0c5f3da), the return.** `returns.sweep_due(db, now=)` walks the tenants, asks the tenant's zone from `workdays.tenant_zone`, finds `pending_customer` tickets whose answer (phase posted or sent) is old enough, works out `add_working_days(postedAt, 3, zone)` per ticket and, when due, moves the status to `open` by compare-and-set, hands off `no_reply_to_ai_answer` through the one hand-off (staff note and requester notice), sets `desk.phase returned` and `desk.returnedAt`, and records event `returned` on the answer's own row. It never touches `resolved`, `closed` or `undoable`. `desk_loop` calls it once per hour (first turn included).
- **Task 3 (85b31bcd3), migration 032 and startup.** `032_service_desk.py` calls `service_desk.store.ensure_indexes` and nothing else; run twice on the private mongod it created every desk index (`one_attempt_per_ticket`, `state_created`, `finished_ttl`, `tenant_status_created`, `created_ttl`, `tenant_helpdesk`, `one_starter_copy`, `tray_list`, `desk_return_due`) and changed no document. `app_startup.py` gains one comment and one `create_task` for `service_desk_worker` after the patch rollout controller (6 lines).
- **Mutation checks by hand (each restored).** Worker: removing the late-reply check failed the late-answer test; using the deadline alone instead of `now + estimate` failed the feasibility test; removing the tenant cap failed the 11th-ticket test; not cutting the timeout failed the time-left test; skipping stale recovery failed 2 tests. Returns: setting `resolved` instead of `open` failed 3 tests; counting calendar days failed 2; ignoring the tenant's zone failed the DST test.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 4f1220eb6 | feat | One desk worker under a renewed lock with the 10-minute queue limit and the queue caps |
| 2 | 7f0c5f3da | feat | A silent requester's ticket goes back to a person after three working days |
| 3 | 85b31bcd3 | feat | Migration 032 makes the desk indexes and the backend starts the desk worker |

Plan type `execute` with `tdd="true"` tasks: as in 85-01 to 85-16, tests and implementation were written together and committed together per task. The first Task 1 test run against the old worker failed on the planned missing behaviour (`run_once() got an unexpected keyword argument 'clock'`) before any implementation was written, which is the only RED evidence taken; no separate `test(...)` commits exist.

## Verification

- Task 1 command (worker, pipeline, tracer): 73 passed before the tracer helper change was committed, all green after; Task 2 command (returns, workdays): 22 passed; Task 3 command (worker with migration and startup cases, `test_database_migrations_lock.py`): 29 passed.
- Final run on 27998: every `test_service_desk_*.py`, `test_autonomous_ops_copy.py`, `test_autonomous_ops_structural.py`, `test_autonomous_ops_migration.py` and `test_database_migrations_lock.py`: **758 passed, 0 skipped, 0 failed** (3 min 49 s). No test left a background task running (the pytest session ended normally); the loop tests end by raising `CancelledError` from the injected sleep.
- Acceptance greps: `lock_with_renewal` in worker.py 2, `estimate_seconds` 2, `async def sweep_due` 1, `no_reply_to_ai_answer` in returns.py 2, `ensure_indexes` in the migration 2, `service_desk_worker` lines in app_startup.py 2. Sizes: worker.py 302 lines, returns.py 100, the largest test file 323 (all under 500). `ruff --select F` is clean on every file touched.
- Every test used the private mongod on 27998 and `httpx.MockTransport` stand-ins with an injected clock. Nothing touched 27017, migration 032 was never run on the live database, and nothing was started, restarted, pushed or published.

## Hand-overs from earlier plans

| From | Item | Status |
| ---- | ---- | ------ |
| 85-15 | Migration 032 / `store.ensure_indexes` creates `one_starter_copy` | done (asserted unique by the migration test); the worker also remakes it before a pass when missing. Until the user's restart runs 032 the live starter copy is not race-safe |
| 85-01 | `tray_list` and `desk_return_due` indexes | done, asserted by the migration test |
| 85-07 | Feasibility with `estimate_seconds`, `load_measurement`, `recent_gen_ms` | done (`_answer_oldest`), mutation-checked |
| 85-14 | Return sweep from `postedAt` with `add_working_days` and `tenant_zone`; never stores returnAt; never closes | done, mutation-checked |
| 85-13 | A job picked up during a stop is handed off `desk_stopped` with no notice | done through `pipeline.prepare`, tested |
| plan / VALIDATION DESK-05 | Stale `running` recovery and per-row timing | done (`stale_running`, `waitSeconds`, `runSeconds` on the job; `genMs` on the row) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `run_once` return shape changed, tracer tests follow**
- **Found during:** Task 1
- **Issue:** The plan makes `run_once` return per-pass counts (`Optional[Dict]`); 85-01's tracer tests read the job id from its old return value.
- **Fix:** counts carry `jobs` (the ids closed, in order); `test_service_desk_tracer.py` gets a three-line `_first_job` helper and two call sites changed. Portal and pipeline support ignore the return value and needed nothing.
- **Files modified:** backend/tests/test_service_desk_tracer.py. **Commit:** 4f1220eb6.

**2. [Rule 3 - Blocking] A shared test support module**
- **Issue:** the worker and return tests need the same world (tenant in Post mode with the four starters, a stand-in that records read timeouts, a movable clock, tickets queued at a chosen arrival).
- **Fix:** `tests/service_desk_worker_support.py` (not in the plan's list), as 85-14 did for its portal tests.
- **Commit:** 4f1220eb6.

**3. [Rule 2 - Missing critical functionality] An unexpected error on a job also reaches a person**
- **Found during:** Task 1
- **Issue:** the 85-01 worker dropped a job on an unexpected error and left the ticket in phase `queued` with no hand-off, which is the "queued forever" state DESK-05 forbids.
- **Fix:** `_fail` hands the ticket off busy when the desk had not yet answered it (phase still `queued`), then drops the job with reason `error`. A failing hand-off is logged and the pass goes on.
- **Commit:** 4f1220eb6.

**Total deviations:** 3 (2 Rule 3, 1 Rule 2). **Impact:** none on scope; no architectural change. `pipeline.py` is unchanged.

## Authentication Gates

None.

## Known Stubs

None.

## Issues and Limits for the Next Plans

- **A job waiting behind a generation is closed late.** While one generation runs (up to its sized timeout, at most 5 minutes) the pass cannot look at the other waiting jobs, so one whose 10 minutes run out meanwhile is handed off busy only when that pass ends, not at the 10-minute mark. No generation is ever started late, and nothing late is posted; only the busy hand-off of a waiting ticket can be up to a call timeout behind the limit. Closing that gap needs the prepare pass to run beside the generation (a second task under the same lock); not done here.
- **A ready job is prepared again on the next pass** (pass-local memory, as planned). Cheap and deterministic, bounded by the caps.
- **An Off desk leaves the ticket's `desk.phase` at `queued`** (`desk_off` writes nothing by design, 85-13). The requester panel then shows no answer; this is the planned behaviour, noted for the UI plans.
- **`worker.py` calls `pipeline._stopped` and `pipeline._handoff`** (underscore names) so a busy hand-off during a stop or with the desk Off follows the same rules as the pipeline; if 85-18+ renames them, `_to_a_person` in worker.py follows.
- **The return sweep is not under the worker lock.** Two runners are harmless: the status change is a compare-and-set, so a ticket is returned once.
- **The desk needs the user's restart.** The restart runs migration 032 and starts `service_desk_worker`; with Ollama not installed every queued ticket is handed off `service_desk_offline` within one pass (5 s), and the first loop turn also runs the return sweep over existing tickets (none have a desk answer yet). The worker's real speed on this CPU is an operator measurement (85-22), not tested here.

## Threat Flags

None. The worker and the sweep add no network endpoint, no auth path and no new file access: both read and write only the desk's own collections and tickets through the raw handle with an explicit tenantId. Plan threats: T-85-64 (queue starvation) mitigated by the caps (tests), T-85-65 (crash or hang) by stale recovery, the lock TTL and renewal and the sized timeouts (tests), T-85-66 (late answers) by the deadline checks before and after the call (test), T-85-67 (returns) by the ledger hand-off row and the row's `returned` event (test).

## Self-Check: PASSED

- Files exist: worker.py, returns.py, 032_service_desk.py, test_service_desk_worker.py, test_service_desk_returns.py, service_desk_worker_support.py (checked with `[ -f ]`).
- Commits found in history: 4f1220eb6, 7f0c5f3da, 85b31bcd3.
- The user's uncommitted work (tickets_endpoints.py, InternalTicketsDashboard.tsx, catalogue-gaps.json, Cargo files, App.tsx, requirements.txt, router-registry test, Rust sources, stray root files, the deleted `ruflo-test-report-*` and `test_app_startup_cargo_resolution.py`) is still present and unstaged.
