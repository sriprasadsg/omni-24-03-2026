---
phase: 82-platform-self-healing-scheduled-retention
plan: 15
subsystem: retention
tags: [retention, gate, tenant-creation-time, self-healing, activity, mongodb, gap-closure, cr-01]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-09 retention_gate and retention_job; 82-10 review and confirm routes and the manual run; 82-11 retention_run Activity row and chip"
provides:
  - "gate_state keyed on tenant creation time, read through one fail-closed reader (created_at_of, tenant_created_at)"
  - "run_all guards each tenant and the tenants cursor, stores failedTenants, and always writes the run document and the Activity row"
  - "incomplete_review and ReviewIncomplete: confirm() refuses an incomplete counted set; GET /review carries incomplete; POST /confirm answers 409 REVIEW_INCOMPLETE"
affects: [82-17 review card (consumes the incomplete field), 82 verification, 82 operator install checklist]

requirements-completed: [HEAL-06, HEAL-07]

actuals:
  tokens: 21000
  tasks: 3
  commits: 3

key-files:
  created:
    - backend/tests/test_retention_unreached.py
  modified:
    - backend/retention_gate.py
    - backend/retention_job.py
    - backend/autonomous_ops_retention_endpoints.py
    - backend/tests/test_retention_gate.py
    - backend/tests/test_retention_job.py
    - backend/tests/test_platform_retention_review.py
    - backend/tests/test_retention_endpoints_phase82.py

key-decisions:
  - "Adoption keys on the tenant's creation time, not on when the job first saw a gate row: a tenant is adopted only when its readable createdAt/created_at is strictly later than the global confirmation (A-82-A12 narrowed)"
  - "created_at_of fails closed: absent, unparseable, non-string and non-datetime values read as None, which means first_run; when both fields parse the earlier wins"
  - "A scheduled run stopped only by the 60-minute cap or a lost lock keeps ok true in its Activity row: the cap is the designed bound of T-82-31, not a failure. The incomplete notice carries that case to the reviewer"
  - "Refusal is 409 REVIEW_INCOMPLETE, so the dialog's existing 409 branch shows the stale block and Reload review; the card then shows the reason (82-17)"
  - "confirm() checks incomplete_review only when at least one row is eligible, so the empty-set 422 and the stale-token 409 keep their meaning"

patterns-established:
  - "One reader decides tenant creation time for run_tenant, review_rows, tenant_gate_flags and incomplete_review"
  - "A test stops a counting pass at an exact point with lost_after(n): run_all calls lost once per tenant and run_tenant once per type"

duration: 8min
completed: 2026-10-31
status: complete
plan_head_before: 5e4bddb70ffdb757444167ad8a08d8265e76cef8
plan_head_after: 642624ac48c7462b23279feb42ac326987c44f47
commits: 3
---

# Phase 82 Plan 15: CR-01 - adopt by creation time, guard each tenant, refuse an incomplete confirmation Summary

**A tenant the first retention pass never reached is now counted and waits for a Super Admin confirmation before anything of it is deleted: adoption keys on the tenant's own creation time (fail closed), run_all survives one tenant's failure and always records the run, and a confirmation is refused with 409 while the counted set is incomplete.**

## Accomplishments

- `backend/retention_gate.py`: `_read_time`, `created_at_of(tenant)` and `tenant_created_at(db, tenant_id)` are the only readers of `createdAt` and `created_at`. `gate_state`'s fourth parameter is now `tenant_created_at`; `adopt` needs `confirmed_days` None and a creation time strictly later than the global confirmation; an equal, earlier, absent or unparseable time is `first_run`. `firstSeenAt` is still written by `mark_seen` and `set_confirmed_days` and decides nothing. `review_rows` and `tenant_gate_flags` decide through the same reader.
- `backend/retention_job.py`: `run_tenant` reads the creation time once and passes it to `gate_state`. `run_all` wraps each tenant in `except Exception` (never BaseException): the failed id lands in `failedTenants`, the error in `errors`, and the pass continues. A second `except Exception` around the tenants cursor sets `stoppedEarly`. The run document and the `retention_run` Activity row are always written, so a failed tenant shows as `ok false` / chip critical. `asyncio.CancelledError` still propagates and writes nothing.
- `incomplete_review(db)` (in `retention_gate.py`) reads the latest scheduled run and the gate rows and returns `{reason, tenants}` or None. `confirm()` raises `ReviewIncomplete` before any write when something would be confirmed. `GET /review` adds `incomplete`; `POST /confirm` maps the refusal to 409 `REVIEW_INCOMPLETE`.
- Example `incomplete` value in GET /review (a manual run reached t1 only; t2 has no gate rows): `{"reason": "not_reached", "tenants": 1}`. Other reasons: `stopped_early`, `tenant_failed`.

## Task Commits

1. **Task 1 (tracer)** `afd90e532` fix - adopt by creation time; CR-01 regression tests
2. **Task 2** `0a4de3acd` fix - per-tenant guard, failedTenants, run always recorded
3. **Task 3** `642624ac4` fix - incomplete_review, ReviewIncomplete, 409 REVIEW_INCOMPLETE, review field

## RED evidence (Task 1, before the fix, private mongod on 27998)

All 7 collected cases of `test_retention_unreached.py` failed on today's code. The reproduction:

```
test_a_tenant_the_first_pass_never_reached_is_counted_then_confirmed_before_anything_is_deleted
backend/tests/test_retention_unreached.py:102:
    assert await kept(mongo_db, "t-z") == 5                       # nothing of the unreached tenant is deleted
E   assert 2 == 5
```

and `test_an_unreadable_creation_time_is_never_adopted[None]` (the same line for `absent`, `"not a time"` and `12345`):

```
backend/tests/test_retention_unreached.py:162: in test_an_unreadable_creation_time_is_never_adopted
    assert await kept(mongo_db, "t-z") == 5
E   assert 2 == 5
```

t-z (never reached) lost its three old records with no count and no confirmation. After the fix both pass. Task 2: 4 of the 5 new tests failed first (`KeyError: 'failedTenants'`, `RuntimeError: mongo down` / `cursor lost` escaping run_all); `test_cancellation_is_not_swallowed` already held and is a guard. Task 3: written after the code this time, then proven RED by reverse-applying the gate and endpoint diff: 10 of 22 cases in the module failed with `AttributeError: module 'retention_gate' has no attribute 'incomplete_review'`, and the diff was re-applied.

## Revised A-82-A12

Adoption now applies only to a tenant created after the global confirmation. A data type added to the registry later, for a tenant that already existed, waits for the review instead of being adopted. A sign-up requested before the confirmation and approved after it keeps its earlier `createdAt`, so it also goes through the review. Rated reversible: one branch in `gate_state`. (Supersedes the 82-09 wording, which adopted anything first seen after the confirmation.)

## A time-capped run keeps ok true

A scheduled run stopped only by the 60-minute cap or a lost lock appends no error, so its Activity row stays `ok true` (healthy chip). The cap is the designed bound of T-82-31, not a failure. The reviewer sees the case through `incomplete` (`stopped_early`), and a confirmation is refused until a run completes.

## The persistent case

If every nightly run hits the 60-minute cap, or the same tenant raises every night, confirmation stays refused until a run completes, because `due()` allows one scheduled run a day. That is the safe direction. The way out is to fix the failing tenant or let the delete backlog drain.

## Verification

Plan-level command on a private mongod (27998): `pytest test_retention_unreached.py test_retention_gate.py test_retention_job.py test_platform_retention_review.py test_retention_endpoints_phase82.py test_autonomous_ops_copy.py test_route_auth_baseline.py` gave **181 passed, 0 skipped** (run after the Task 3 code and tests, before its commit). The private mongod was stopped through its pidfile; the live mongod (pid 605) was untouched. Acceptance greps: `created_at_of`/`tenant_created_at` defs 2, `tenant_created_at` in the job 1, `failedTenants` 2, `except Exception` in retention_job.py 4 -> 6, `except BaseException` 0, `incomplete_review|ReviewIncomplete` defs 2, `REVIEW_INCOMPLETE` 2, file sizes under 500 (gate 356, job 302, unreached tests 407, job tests 467). `backend/retention_endpoints.py` appears in none of the three commits (its four uncommitted `_POLICY_DEFAULTS` lines are the user's).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 3 RED evidence taken after the implementation**
- **Found during:** Task 3
- **Issue:** The gate and endpoint code was written before the Task 3 tests, so a plain first run could not show RED.
- **Fix:** Saved the diff, reverse-applied it, ran the new module (10 failures), re-applied it.
- **Files modified:** none beyond the plan's
- **Commit:** n/a (no code change)

**Total deviations:** 1 (process only). **Impact:** none on shipped behaviour.

Not RED-proven separately: the two new HTTP tests in `test_platform_retention_review.py` and the T-82-36 test in `test_retention_endpoints_phase82.py`; they pass against the final code, and the T-82-36 case rests on the Task 1 change that the module-level RED already covers.

## Requirements

HEAL-06 and HEAL-07 are listed in `requirements-completed` as the template asks, but per the plan (commit 4e5fc45ce reverted premature ticks) no requirement was marked complete in REQUIREMENTS.md; the HEAL ticks stay Pending until phase verification.

## Known Stubs

None.

## Threat Flags

None. GET /review gains one read-only field; no new endpoint, auth path or schema change.

## Authentication Gates

None.

## Next Phase Readiness

82-17 can read `incomplete` from GET /review. Nothing is deployed: no backend restart, no UI publish, no push, no retention confirm on the live server.

## Self-Check: PASSED

Created and modified files exist; commits afd90e532, 0a4de3acd and 642624ac4 are ancestors of HEAD; `git rev-list --count 5e4bddb70..642624ac4` is 3.
