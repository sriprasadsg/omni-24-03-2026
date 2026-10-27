---
phase: 82-platform-self-healing-scheduled-retention
plan: 09
subsystem: infra
tags: [retention, mongodb, motor, distributed-lock, gate, batch-delete, scheduling]

requires:
  - phase: 81-autonomous-ops
    provides: distributed_lock.lock_with_renewal pattern, autonomous_ops.PROTECTED_COLLECTIONS, raw-handle helper, seed_tenant test helper
provides:
  - retention_gate.py: eight-type registry, NEVER_DELETED, gate_state, policy loader, review rows/token, confirm, tenant gate flags, indexes
  - retention_job.py: tenant-scoped count and bounded-batch delete, run_tenant/run_all/run_manual, 02:00 UTC schedule with catch-up, retention_loop
  - migration 027 (retention gate indexes)
  - retention_loop registered at startup in place of the removed agent_telemetry_retention_loop
affects: [82-10 retention endpoints and review/confirm API, 82 UI retention card, 82 platform-health Activity rows]

actuals:
  tokens: 14400
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Gate is a pure function over stored confirmedDays plus a global confirmedAt; shortening is detected by comparison at run time, no hook on the policy writers"
    - "Bounded delete: find at most N ascending _id values with the tenant filter, delete exactly those ids, pause, repeat; stop on short batch, lost lock or monotonic deadline"
    - "Review integrity by stateless sha256 token over the sorted waiting rows (StaleReview on mismatch)"

key-files:
  created:
    - backend/retention_gate.py
    - backend/retention_job.py
    - backend/migrations/027_retention_gate.py
    - backend/tests/test_retention_gate.py
    - backend/tests/test_retention_job.py
  modified:
    - backend/app_startup.py
    - backend/app_background_tasks.py

key-decisions:
  - "gate_state treats first_seen_at == global confirmedAt as first_run (strict >), so rows confirmed in the same pass never self-adopt"
  - "Count stored at a period other than the tenant's current policy is shown as count None and excluded from confirm (stale count), as is a failed count"
  - "Global confirmedAt is set only by a confirm that confirms at least one row, and is never moved by later confirms"
  - "delete_many also carries the tenant field next to the id list (defence in depth) and delete_type refuses any collection in NEVER_DELETED"
  - "A short batch (fewer than the batch size) ends the loop without an extra empty find or pause, so a 1200-document run is exactly 500/500/200 with two pauses"
  - "run_manual takes the same retention_job lock and returns None while a run is in progress; 82-10 must map None to a 409/busy answer"
  - "retention_loop waits 120 s after startup, then checks every 300 s"

patterns-established:
  - "RetentionType registry is the single source for count, delete, labels and gate flags; retention_service.py is not imported"

requirements-completed: [HEAL-06]

coverage:
  - id: D1
    description: "Registry of exactly eight data types with the stored tenant field and time kind, disjoint from NEVER_DELETED at import and in tests"
    requirement: HEAL-06
    verification:
      - kind: unit
        ref: "backend/tests/test_retention_job.py#test_registry_is_the_eight_types_and_disjoint_from_never_deleted"
        status: pass
    human_judgment: false
  - id: D2
    description: "First scheduled run only counts (retention_counts, retention_job_runs) and deletes nothing"
    requirement: HEAL-06
    verification:
      - kind: integration
        ref: "backend/tests/test_retention_job.py#test_first_run_counts_old_agent_metrics_and_deletes_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "Gate states first_run/adopt/shortened/confirmed, confirmation by review token, stale token rejected, failed and stale-period counts not confirmed"
    requirement: HEAL-06
    verification:
      - kind: unit
        ref: "backend/tests/test_retention_gate.py#test_gate_state_table"
        status: pass
      - kind: integration
        ref: "backend/tests/test_retention_gate.py#test_confirm_with_a_token_from_before_a_recount_raises_and_changes_nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "Bounded deletes in 500-id batches with pauses, lost-lock and wall-clock stops, protected collections untouched, tenant isolation, shortened/lengthened/adopted behaviour, strict boundary"
    requirement: HEAL-06
    verification:
      - kind: integration
        ref: "backend/tests/test_retention_job.py#test_batches_of_500_500_200_with_a_pause_between_them"
        status: pass
      - kind: integration
        ref: "backend/tests/test_retention_job.py#test_uptime_rollups_use_tenant_id_and_never_cross_tenants"
        status: pass
      - kind: integration
        ref: "backend/tests/test_retention_job.py#test_boundary_a_record_exactly_retention_days_old_is_kept"
        status: pass
    human_judgment: false
  - id: D5
    description: "02:00 UTC schedule with catch-up under the renewed distributed lock; telemetry loop removed and retention_loop registered"
    requirement: HEAL-06
    verification:
      - kind: unit
        ref: "backend/tests/test_retention_job.py#test_due"
        status: pass
      - kind: integration
        ref: "backend/tests/test_retention_job.py#test_a_second_runner_returns_none_while_the_lock_is_held"
        status: pass
      - kind: unit
        ref: "backend/tests/test_retention_job.py#test_the_telemetry_loop_is_gone_and_retention_loop_is_registered"
        status: pass
    human_judgment: false
  - id: D6
    description: "Real-time behaviour at 02:00 UTC on the live server (timing against the 02:30 backup, API latency during deletes)"
    verification: []
    human_judgment: true
    rationale: "Batch and pause values were measured only against a throwaway mongod; the live 2-vCPU server under API load cannot be exercised from a hermetic test (A-82-A5)"

duration: 35min
completed: 2026-10-27
status: complete
plan_head_before: fb6f6d3a0de3565732bf539acea67c07c5d4bb17
plan_head_after: 6c33d94a87f449186c1ee05daaca248baa56319a
commits: 3
---

# Phase 82 Plan 09: Scheduled Retention Job and Gate Summary

**One nightly 02:00 UTC retention job for eight routine data types that counts first, deletes only what a Super Admin confirmed, in bounded 500-id tenant-scoped batches under a renewed distributed lock, and replaces the separate agent-telemetry purge loop.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-10-27T08:40Z
- **Tasks:** 3 (1 tracer, 2 auto, all TDD)
- **Files:** 5 created, 2 modified (plus this SUMMARY)

## Accomplishments

- `retention_gate.py` (261 lines): `RetentionType` registry of metrics, notifications, agent_location_history, agent_uptime_rollups, agent_metrics, asset_metrics, persistence_results, logs with their stored tenant field (tenant_id for uptime rollups and agent/asset metrics) and time kind; `NEVER_DELETED` (audit_logs, audit_chain_heads, audit_chain_checkpoints, autonomy_actions, autonomy_settings, autonomy_never_touch, compliance_evidence plus `PROTECTED_COLLECTIONS`) asserted disjoint at import; `gate_state`; `load_policy_days` (integer 1..3650 only); review rows, token, `confirm`, `StaleReview`, `tenant_gate_flags`, `ensure_indexes`.
- `retention_job.py` (253 lines): `cutoff_filter` (strict less-than; ISO string via `isoformat()`, UTC datetime, `ObjectId.from_datetime`), `count_type` (maxTimeMS 30000, failure stored on that row), `delete_type`, `run_tenant`, `run_all`, `run_manual`, `next_scheduled`, `due`, `run_once`, `retention_loop`.
- Migration 027 creates unique (tenantId, type) indexes on `retention_gate` and `retention_counts` and a `startedAt` index on `retention_job_runs`; idempotent.
- `agent_telemetry_retention_loop` removed; `retention_loop` registered in `app_startup.py` as `retention_job`.
- 55 new tests (20 gate, 35 job) all pass against a private throwaway mongod; `test_distributed_lock.py` (10) and `test_watchdog_artifacts.py` (20 pass, 2 skip for files of later plans) also pass, including 82-06's installs-nothing checks for `retention_gate.py` / `retention_job.py`.

## Task Commits

1. **Task 1: Tracer - first run counts one tenant's old agent metrics, deletes nothing** - `f76241038` (feat)
2. **Task 2: Gate, confirmation and bounded deletes** - `68c47214e` (feat)
3. **Task 3: Nightly 02:00 UTC schedule with catch-up, telemetry loop folded in** - `6c33d94a8` (feat)

**Plan metadata:** committed after this SUMMARY (docs: complete plan)

## Measured batch timings (A-82-A5)

Against a private mongod on this VM (20,000 old `agent_metrics` documents of one tenant, no pause, 500-id batches): 40 batches, `delete_many` per batch min 3.5 ms, median 4.2 ms, max 8.0 ms, whole delete pass 0.34 s, one `count_documents` 1.4 ms. With the 0.5 s pause the same pass is about 20 s. Live volumes (121k agent_metrics, 105k asset_metrics) would take about 4 to 5 minutes of mostly pause time, far inside the 60-minute cap. This says nothing about contention with the API under real load; that stays a human check (coverage D6).

## Review row shape (82-10 serves it)

`retention_gate.review_rows(db)` returns waiting rows (reason `first_run` or `shortened`) sorted by count descending, then tenant name, then type:

```
{ tenantId, tenantName, type, label, collection, days, previousDays, count, countError, countedAt, reason }
```

- `days`: the tenant's current policy period; `previousDays`: last confirmed period (None on a first run; stays 90 when shortened 90 -> 60 -> 30 before confirming).
- `count` is None when there is no usable count: never counted, a failed count (`countError` set), or counted at a period different from the current policy. Such rows are shown but excluded from confirm.
- `review_token(rows)` = sha256 over sorted `tenantId|type|days|count|countedAt` lines; `confirm(db, token, actor, now)` raises `StaleReview` (map to HTTP 409) when it no longer matches and returns `{rows, records, tenants}`; it deletes nothing, the next run does.
- `tenant_gate_flags(db, tenant_id)` returns `{type id: {waiting, reason}}` for the `/policies` gate flags.
- `run_manual(db, tenant_id, now=)` returns the run summary dict (`trigger "manual"`, `tenantId`, `counted`, `deleted`, `tenants` 1, `stoppedEarly`) or None when a run holds the lock.

## User-side lines removed from the working tree (preserved for the user)

These lines existed only in the user's uncommitted working tree (never in any commit); a backup and full diff is at `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/d15ba10e-27f8-478c-80ee-57886a5d3671/scratchpad/user-backup-pre-82-09/`. Removed from `backend/app_background_tasks.py` (appended after `audit_maintenance_loop`):

```python
async def agent_telemetry_retention_loop():
    """Daily purge of agent telemetry past each tenant's retention policy (agent_metrics,
    asset_metrics, persistence_results, logs: see retention_service.AGENT_TELEMETRY). The first
    sweep runs 10 minutes after startup."""
    from database import get_database
    from retention_service import purge_agent_telemetry

    _log = logging.getLogger(__name__ + ".telemetry_retention")
    await asyncio.sleep(600)
    while True:
        try:
            deleted = await purge_agent_telemetry(get_database()._db)
            _log.info("Agent telemetry retention sweep deleted %d document(s)", deleted)
        except Exception as exc:
            _log.error("Agent telemetry retention sweep failed: %s", exc)
        await asyncio.sleep(86400)
```

Removed from `backend/app_startup.py`: the import entry `        agent_telemetry_retention_loop,` (inside the `from app_background_tasks import (...)` block) and the line `    asyncio.create_task(_safe_bg_task(agent_telemetry_retention_loop(), "agent_telemetry_retention"))`.

`backend/retention_service.py` (`AGENT_TELEMETRY`, `cleanup_agent_telemetry`, `purge_agent_telemetry`) and `backend/retention_endpoints.py` were not touched (82-10). Because the old loop is gone, `purge_agent_telemetry` currently has no caller from startup; 82-10 decides what happens to it and to the manual `/run` path.

## Decisions Made

See `key-decisions` above. Notable: strict `>` for adopt, stale-period counts excluded from confirm, short batch ends the loop, and `run_manual` shares the job lock.

## Deviations from Plan

None - plan executed exactly as written. Two behaviours worth knowing, both inside the plan's design:

- **Orphans are no longer purged.** The removed user loop also deleted documents whose tenant field was null once past the default period. The new job is strictly tenant-scoped (PROH-82-05 / T-82-32), so tenant-less telemetry now accumulates. Out of scope here; recorded for 82-10 / the operator.
- **Telemetry is not purged until the first confirmation.** Per D-15/D-18 this is the intended consequence: 121k `agent_metrics` and 105k `asset_metrics` stay until a Super Admin confirms the counts.

## Issues Encountered

- Test seeding used `ObjectId.from_datetime`, which yields identical ids within one second (duplicate key); tests now build unique ids from the timestamp bytes plus random bytes. The strict-boundary test deliberately keeps the zero-suffixed id.
- `stage_own.py` reported "no stageable change" for `app_background_tasks.py` (expected: after removing the user's uncommitted function the file equals HEAD) and staged only my five lines of `app_startup.py`.

## Pre-existing failures observed (not mine, not touched)

None encountered in the files run (retention, distributed lock, watchdog artifacts). The known failures listed for this phase were not exercised.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or schema at a trust boundary beyond the plan's threat model (T-82-30..33 mitigated: eight-type registry disjoint from NEVER_DELETED with `delete_type` refusing protected collections; 500-id batches, 0.5 s pauses, 60 min cap, 02:00 UTC; raw handle with stored tenant fields and two-tenant tests; gate plus review token).

## User Setup Required

None. The backend runs from the checkout without reload, so this ships only when the user restarts the backend; migration 027 (indexes only) then applies at startup. After deploy, confirm the first count soon, because telemetry is no longer purged until then.

## Next Phase Readiness

82-10 can build the review/confirm API, `/policies` gate flags, `/stats` `next_scheduled`, and the manual route on `retention_gate` and `retention_job`. Open question for 82-10: what `run_manual` returning None (busy) maps to.

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-27*

## Self-Check: PASSED

All created files exist (`retention_gate.py`, `retention_job.py`, `027_retention_gate.py`, both test modules) and commits `f76241038`, `68c47214e`, `6c33d94a8` are ancestors of HEAD.
