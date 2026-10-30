---
phase: 82-platform-self-healing-scheduled-retention
plan: 10
subsystem: api
tags: [retention, fastapi, mongodb, review-token, platform-health, tenant-isolation]

requires:
  - phase: 82-01
    provides: retention_run and retention_confirmed platform-health rows, ledger.record_platform_health
  - phase: 82-09
    provides: retention_gate (review_rows, review_token, confirm, tenant_gate_flags), retention_job (run_all, run_manual, next_scheduled)
provides:
  - GET /api/platform/autonomous-ops/retention/review and POST .../confirm (Super Admin, interactive session, stale-proof)
  - one retention_run Activity row per scheduled run, one retention_confirmed row per confirmation
  - POST /api/retention/run behind the same gate (counted or deleted per type), 409 while busy, 400 without a tenant
  - /stats next_scheduled, /policies gate flags and audit_logs managedBy/editable, POST /policies countOnlyUntilConfirmed and the audit_logs 409
  - RetentionService.cleanup_audit_logs removed
affects: [82-11 and later retention UI plans, 82 operator install checklist]

actuals:
  tokens: 13815
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Review is a stateless token over every waiting row; paging only slices the items"
    - "Run-in-progress is the job lock (live _distributed_locks entry) or a started-but-unfinished run document"
    - "Tenant routes keep the wrapper for writes; the gate reads through the raw handle with an explicit tenantId, proven by a seam test"

key-files:
  created:
    - backend/autonomous_ops_retention_endpoints.py
    - backend/tests/test_platform_retention_review.py
    - backend/tests/test_retention_endpoints_phase82.py
  modified:
    - backend/retention_job.py
    - backend/retention_endpoints.py
    - backend/retention_service.py
    - backend/router_registry.py
    - backend/tests/test_retention_job.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The review lists every waiting row including those that counted 0; confirm applies to all of them, so the reviewer sees exactly what one click changes"
  - "POST /run answers {status, ran_at, result, types, stoppedEarly}: result stays a flat map of scalar tiles (<type>_counted / <type>_deleted) so the existing result card does not break, types is the structured per-type list"
  - "A busy manual run answers 409 and writes no retention_runs row; no tenant on the caller answers 400 before run_manual"
  - "Audit logs policy writes are refused with 409 (A-82-A13 confirmed safe, see below)"
  - "lastRun on the review is the newest finished scheduled run, not a tenant's manual run"

patterns-established:
  - "retention_run params {mode, records, tenants, ok, error}: records is the deleted total when mode is deleted, else the counted total; ok is false when any type's count or delete failed"

requirements-completed: [HEAL-06, HEAL-07]

coverage:
  - id: D1
    description: "Super Admin reviews the counted rows, confirms once with the review token, and the confirmation names the person in platform Activity"
    requirement: HEAL-06
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_retention_review.py#test_review_confirm_activity_and_the_next_run_deletes"
        status: pass
    human_judgment: false
  - id: D2
    description: "Scheduled runs write one retention_run row (counted or deleted, ok and error); manual runs write none; a ledger failure never fails the run"
    requirement: HEAL-07
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_retention_review.py#test_a_scheduled_run_writes_one_row_and_a_manual_run_writes_none"
        status: pass
      - kind: integration
        ref: "backend/tests/test_platform_retention_review.py#test_a_ledger_failure_never_fails_the_run"
        status: pass
    human_judgment: false
  - id: D3
    description: "Review paging (25 per page, stable token), ordering, uncountable rows excluded, notCountedYet, deleting_nightly, running, stale 409, empty 422, 403 for tenant admin, viewer, Platform Support and API keys"
    requirement: HEAL-06
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_retention_review.py (21 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Manual run counts waiting types, deletes confirmed ones for the caller's tenant only, never touches audit logs, 409 while busy, 400 without a tenant"
    requirement: HEAL-06
    verification:
      - kind: integration
        ref: "backend/tests/test_retention_endpoints_phase82.py#test_manual_run_counts_waiting_types_and_deletes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_retention_endpoints_phase82.py#test_manual_run_answers_409_and_records_nothing_while_a_run_is_in_progress"
        status: pass
    human_judgment: false
  - id: D5
    description: "Stats next_scheduled, policies gate flags for the caller's tenant only, audit_logs managed and refused with 409, countOnlyUntilConfirmed, and the writer/reader seam"
    requirement: HEAL-06
    verification:
      - kind: integration
        ref: "backend/tests/test_retention_endpoints_phase82.py (14 tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Operator step after the first 02:00 UTC run following deploy: review the counts per organization, confirm, and see the next night's Activity row with audit logs untouched"
    verification: []
    human_judgment: true
    rationale: "Needs the live platform, a real nightly run and the Phase 82 UI card (a later plan); not exercisable from a hermetic test"

duration: 15min
completed: 2026-10-30
status: complete
plan_head_before: 9112a94e0ffd95d477ae720fa019ab90c0bda550
plan_head_after: e88e1a57df4070707c560accbec44fbaceafe8e5
commits: 3
---

# Phase 82 Plan 10: Retention Review, Confirm and Tenant Routes Summary

**Super Admin retention review and one-click confirm guarded by a stateless review token, nightly runs and confirmations in platform Activity, and tenant retention routes that run behind the same count-only gate and never delete audit logs.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-10-30T18:47:30Z
- **Tasks:** 3 (1 tracer, 2 auto, all TDD)
- **Files:** 3 created, 8 modified

## Accomplishments

- `autonomous_ops_retention_endpoints.py`: `GET /review` (offset/limit 25 default, totals over all rows, `notCountedYet`, `nextRun`, `lastRun`, `countedAt`, `running` mode) and `POST /confirm` (409 stale, 409 running, 422 nothing countable, Activity row naming the person).
- `retention_job.run_all` writes one `retention_run` row per scheduled run; `run_in_progress` and the run `error` are recorded for the review.
- `POST /api/retention/run` calls `run_manual` for the caller's tenant; waiting types are counted, confirmed types deleted, and the response lists each type with its state and number.
- `/stats` returns the next 02:00 UTC; `/policies` adds `gate {waiting, reason}` for the caller's own tenant, and `audit_logs` carries `managedBy audit_ledger`, `editable false`; `POST /policies/audit_logs` answers 409; other writes report `countOnlyUntilConfirmed`.
- `RetentionService.cleanup_audit_logs` and its call are gone (D-16).
- 35 new tests (21 review, 14 tenant routes); 205 retention, platform-health, copy, ledger and watchdog-artifact tests pass together against a private throwaway mongod.

## Example GET /review response (real, from a test run, limit 2)

```json
{
  "mode": "counting_only",
  "notCountedYet": false,
  "nextRun": "2026-10-31T02:00:00+00:00",
  "lastRun": {"at": "2026-10-30T19:01:18.978000+00:00", "trigger": "scheduled", "counted": 3, "deleted": 0,
              "tenants": 2, "error": null, "stoppedEarly": false},
  "countedAt": "2026-10-30T19:01:18.878000+00:00",
  "reviewToken": "c081285930ff5fc5f41ebb8c485937e3f4e5b3601137c5cf1c3b25b9f7d111bf",
  "totals": {"records": 3, "tenants": 2, "rows": 16, "uncountable": 0},
  "items": [
    {"tenantId": "t1", "tenantName": "T1", "type": "agent_metrics", "label": "Agent metrics",
     "collection": "agent_metrics", "days": 30, "previousDays": null, "count": 3, "countError": null,
     "countedAt": "2026-10-30T19:01:18.878000+00:00", "reason": "first_run"},
    {"tenantId": "t1", "tenantName": "T1", "type": "agent_location_history", "label": "Agent location history",
     "collection": "agent_location_history", "days": 365, "previousDays": null, "count": 0, "countError": null,
     "countedAt": "2026-10-30T19:01:18.878000+00:00", "reason": "first_run"}
  ],
  "total": 16,
  "nextOffset": 2
}
```

## A-82-A13 finding (frameworks grep)

`grep -rn retention_policies backend/frameworks` finds exactly one reference: `backend/frameworks/iso27001.py` control A.8.10 ("Information deletion", `check_type count_gt_zero`, `check_collection retention_policies`). `frameworks/_common_checks.py` runs it as `count_documents({}) > 0` on that collection: it only tests that the collection has at least one document, never a value. The `log_retention` checks look at `audit_logs` timestamps, not at the policy. Refusing writes to the `audit_logs` policy therefore cannot change any compliance result; the seeded `audit_logs` policy row stays. Assumption confirmed.

## Task Commits

1. **Task 1: Tracer - review, confirm, Activity rows** - `15c4191d3` (feat)
2. **Task 2: Tenant retention routes** - `2840f0934` (feat)
3. **Task 3: Review details, guards and copy lists** - `e88e1a57d` (feat)

**Plan metadata:** committed after this SUMMARY (docs: complete plan)

## Decisions Made

See `key-decisions`. Two worth knowing: `totals.tenants` and `confirmed.tenants` count every tenant with a countable row (including rows that counted 0), exactly as `retention_gate.confirm` does, so the Activity line ("across N organizations") matches the review totals. `lastRun` shows scheduled runs only, so one tenant pressing Run cleanup now never appears as the platform's last run.

## User-side hunks (orchestrator note 5)

- Backups: `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/89eefb8e-80f2-4abe-9bb5-c658ae51577a/scratchpad/user-backup-pre-82-10/` (`retention_endpoints.py`, `retention_service.py`, `user-uncommitted.diff`).
- The commits contain HEAD plus this plan's hunks only. Checked with `git diff --cached` before each commit: no `AGENT_TELEMETRY`, `cleanup_agent_telemetry`, `purge_agent_telemetry`, no `tenant_id` parameter or branch of `run_cleanup`, and none of the four telemetry `_POLICY_DEFAULTS` rows. `git diff` confirms all of them are still in the working tree (the 13 matching lines).
- `retention_service.py`: staged cleanly by the helper (the audit removal and the user's run_cleanup lines did not collide in the end).
- `retention_endpoints.py`: the helper reported one conflict at the POST /run body; resolved by the fallback (preview edited to HEAD plus my change, `--from`).
- **The one user line this plan replaced:** `result = await svc.run_cleanup(policies=policies, tenant_id=getattr(user, "tenant_id", None))` in POST /run is gone from the working tree, as the acceptance grep requires (`grep -c ".run_cleanup(" backend/retention_endpoints.py` prints 0).
- **User lines in `retention_service.py` that are now unused** (left in place, not deleted): `from bson import ObjectId`, `AGENT_TELEMETRY`, `_created_before`, `cleanup_agent_telemetry`, `purge_agent_telemetry` (no caller since 82-09 removed the loop), and the `tenant_id` parameter and telemetry branch of `RetentionService.run_cleanup` (nothing passes `tenant_id`; `run_cleanup` itself now has no route or loop caller). The four telemetry `_POLICY_DEFAULTS` rows in `retention_endpoints.py` stay in use: they seed the tenant periods the job reads.
- The new tests do not depend on those lines. `test_retention_endpoints_phase82.py` stores the periods it reads and writes explicitly and was also run with the four telemetry defaults removed (HEAD state): 14 passed both ways.
- Consequence to know: in HEAD alone (without the user's uncommitted defaults), `POST /api/retention/policies/agent_metrics` for a tenant with no stored row hits the pre-existing unknown-collection branch. That is the user's pending defaults, not something this plan changed.

## Deviations from Plan

### Orchestrator-required additions

1. **Busy answer.** `run_manual` returning None maps to 409 "A retention run is in progress. Try again when it finishes."; no `retention_runs` row is written. Test: `test_manual_run_answers_409_and_records_nothing_while_a_run_is_in_progress`.
2. **Per-type results.** `run_manual` now carries `types` from `run_tenant`; the route returns them as a list `{type, label, days, state counted|deleted|failed, count|deleted}`. Test: `test_manual_run_counts_waiting_types_and_deletes_nothing` and the delete twin.
3. **Tenant guard.** No tenant on the caller answers 400 before `run_manual`; only in POST /run. Test: `test_manual_run_without_a_tenant_is_refused_before_anything_runs`.
4. **Seam test.** `test_a_period_saved_through_the_route_is_the_period_the_job_reads_for_that_tenant_only`.

### Auto-fixed issues

**1. [Rule 1 - Bug] 82-09 test counted rows in protected collections**
- **Found during:** Task 1
- **Issue:** `test_audit_and_decision_records_are_untouched_by_a_confirmed_run` compared document counts of the protected collections; a scheduled run now legitimately appends its own Activity and audit rows, so the count grew.
- **Fix:** the test now asserts every pre-existing document id is still present (nothing removed), which is the property it exists to prove.
- **Files modified:** backend/tests/test_retention_job.py
- **Committed in:** 15c4191d3

**2. [Rule 2 - Missing critical] Count failures reported as errors**
- **Found during:** Task 1
- **Issue:** `_record_count` swallowed the failure, so a run whose counts failed would write a retention_run row with ok true.
- **Fix:** `_record_count` returns `(count, error)`, the type entry carries `error`, and `run_all` records `ok` false plus the first error, also stored on the run document as `error` for the review's Last run cell.
- **Files modified:** backend/retention_job.py
- **Committed in:** 15c4191d3, e88e1a57d

**3. [Rule 2 - Missing critical] Run-in-progress detection**
- **Found during:** Task 3
- **Issue:** the plan's "started and not finished run document" never exists in real runs (run documents are inserted at the end). The real signal is the job lock.
- **Fix:** `retention_job.run_in_progress` is true for a live lock entry or a recent unfinished run document; the review and the confirm route use it.
- **Files modified:** backend/retention_job.py, backend/autonomous_ops_retention_endpoints.py
- **Committed in:** e88e1a57d

### Plan wording that differs from what shipped

- The tracer behaviour describes "one item" and `rows 1`. A real `run_all` counts all eight types per tenant, and `confirm` applies to every counted row (including zero ones, which must be confirmed or they would stay waiting forever), so the review lists every waiting row and `confirmed.rows` equals the number of countable rows. The UI plan may want to group or collapse the zero rows; the API keeps them listed.
- `result` of POST /run keeps flat scalar tiles because the existing screen renders every `result` entry as a tile; the structured list is the new top-level `types`.

**Total deviations:** 3 auto-fixed (1 bug, 2 missing critical) plus 4 orchestrator additions.
**Impact on plan:** all necessary for correctness or required by the orchestrator; no scope creep.

## Issues Encountered

None blocking.

## Pre-existing failures observed (not mine)

- `backend/tests/test_catalogue_route_parity.py::test_ledger_ratchets` fails on stale ledger entries from the user's uncommitted work; none of the failure lines name the retention routes.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-82-34 token and running guards, T-82-35 platform-only permission plus interactive session with 403 tests for tenant admin, viewer, Platform Support and API keys, T-82-36 manual run through `run_manual`, T-82-37 flags for the caller's own tenant only with a two-tenant test).

## User Setup Required

None. Like 82-09, this ships only when the user restarts the backend. The new router is registered in `router_registry.py`; it is not required at startup.

## Next Phase Readiness

The UI plans can consume `/review`, `/confirm`, the `/api/retention/*` fields and the `types` list. Copy to wire in the tenant screen: `gate.waiting`, `managedBy`, `editable`, `countOnlyUntilConfirmed`, `next_scheduled`.

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-30*

## Self-Check: PASSED

Created files exist (`autonomous_ops_retention_endpoints.py`, `test_platform_retention_review.py`, `test_retention_endpoints_phase82.py`); commits `15c4191d3`, `2840f0934`, `e88e1a57d` are ancestors of HEAD; acceptance greps: router_registry 1, record_platform_health present in both files, `cleanup_audit_logs` 0, `.run_cleanup(` 0, `"next_scheduled": None` 0, copy lists 1 each.
