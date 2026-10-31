---
phase: 82-platform-self-healing-scheduled-retention
reviewed: 2026-10-31T12:00:00Z
depth: standard
scope: gap round re-review (plans 82-15, 82-16, 82-17 and cbdb97708, diff base 7c946fb97)
files_reviewed: 20
files_reviewed_list:
  - backend/autonomous_ops/health_messages.py
  - backend/autonomous_ops/selfheal.py
  - backend/autonomous_ops_retention_endpoints.py
  - backend/retention_gate.py
  - backend/retention_job.py
  - backend/tests/test_platform_health_status.py
  - backend/tests/test_platform_health_sync.py
  - backend/tests/test_platform_retention_review.py
  - backend/tests/test_retention_endpoints_phase82.py
  - backend/tests/test_retention_gate.py
  - backend/tests/test_retention_job.py
  - backend/tests/test_retention_unreached.py
  - components/AutonomousOpsRetentionConfirmDialog.tsx
  - components/AutonomousOpsRetentionReview.tsx
  - components/RetentionPolicyDashboard.tsx
  - services/autonomousOpsApi.ts
  - src/__tests__/AutonomousOpsRetentionConfirmDialog.test.tsx
  - src/__tests__/AutonomousOpsRetentionReview.test.tsx
  - src/__tests__/RetentionPolicyDashboard.test.tsx
  - src/__tests__/_platformHealthHarness.tsx
findings:
  critical: 0
  warning: 2
  info: 8
  total: 10
status: issues_found
---

# Phase 82: Code Review Report (gap round re-review)

**Reviewed:** 2026-10-31
**Depth:** standard
**Files Reviewed:** 20 (changed lines since 7c946fb97 and what they affect; `retention_gate.py`, `retention_job.py` and `selfheal.py` were read whole)
**Status:** issues_found

## Summary

This round re-reviews the gap closure for CR-01, WR-01, WR-02, WR-03 and WR-05. No backend test was run (they default to the live mongod); every conclusion below comes from reading the code and the call chains.

Disposition of the previous findings that were targets of this round:

| Id | Verdict | Evidence |
|---|---|---|
| CR-01 | Fixed | `gate_state` now adopts only when the tenant's own creation time is readable and strictly later than the global confirmation (`retention_gate.py:129-143`). `run_tenant`, `review_rows` and `tenant_gate_flags` all decide through `created_at_of`, which reads both field names, fails closed and takes the earlier value (`:110-126`, `retention_job.py:125,133`). A tenant the first pass never reached keeps `confirmedDays` null, is `first_run`, is counted by the next run, and is deleted only after a confirmation. `incomplete_review` plus `ReviewIncomplete` is checked inside `confirm()` before any write (`:320-324`). `run_all` guards each tenant, records `failedTenants` and always writes the run row (`retention_job.py:167-195`). |
| WR-01 | Fixed client-side | `allLoaded = state?.nextOffset === null` is in the button's `disabled` (`AutonomousOpsRetentionReview.tsx:262,346`). The remaining client-only limit is already recorded in 82-SECURITY.md and is not re-reported. |
| WR-02 | Fixed | `_cert_rule` derives the rule from the unrounded `daysLeft` with `<=` comparisons that match `CERT_LADDER` in `warnings.py:27,77-78`. Checked: the watchdog opens a separate incident per suffix (30d, 14d, 7d, 1d), so each threshold emits its own event with the `daysLeft` at the crossing, and the rule id follows it. An unreadable certificate has its own `cert-unreadable` rule and wording. A cleared incident emits no `cert_warning` event (`warnings.py:89-99`), so the new "Can't read this file." text cannot appear for a healthy certificate. |
| WR-03 | Fixed | The `clean_params` call moved inside the `try`, a final `except Exception` counts the event as dropped and the loop continues (`selfheal.py:191-204`). Non-finite floats and integers outside signed 64-bit are dropped in `clean_params` and `_scrub`; `_finite` guards `math.isfinite` to floats only. An unhashable `kind` no longer raises `TypeError` (`isinstance(kind, str)` first). `CancelledError` is a `BaseException` and still propagates. A bad event in a batch that also holds an unrecordable one is re-sent until the watchdog's `MAX_TRIES` and then abandoned (`sync.py:128-133`), so the wedge is bounded. |
| WR-05 | Fixed | `runCleanup` checks `r.ok` and a string `ran_at` before setting the success card, and has a `catch` (`RetentionPolicyDashboard.tsx:49-60`). `ran_at` is a string in the real response (`retention_endpoints.py:112-114`). A list-valued 422 `detail` falls back to the generic message. |

Carried and deliberately not re-reviewed: WR-04 and IN-01 to IN-05 (their files are out of this scope). They stay open under the same ids and are listed at the end.

The hardest-looked-at paths (`incomplete_review`, `confirm`, `gate_state`, `run_all`, `ingest_events`) hold up: I could not construct a case where unconfirmed data is deleted, and the refusal cases all clear on the next complete scheduled run. One availability weakness in the confirm token (WR-06) and three minor items (IN-06 to IN-08) are new.

## Warnings

### WR-06: A tenant admin's "Run Cleanup Now" re-stamps `countedAt` and so invalidates the Super Admin's review token on demand

**File:** `backend/retention_job.py:74-85` (also `:149-154`, `:268-285`; `backend/retention_gate.py:301-305`; `backend/retention_endpoints.py:99-115`)

**Issue:** `review_token` hashes `tenantId|type|days|count|countedAt` for every waiting row. `_record_count` always writes `countedAt: now` (`retention_job.py:81-84`), even when days, count and error are unchanged. `POST /api/retention/run` is open to any tenant admin for their own tenant and calls `run_manual` -> `run_tenant`, which recounts every `first_run` and `shortened` row of that tenant. So any tenant admin can change the platform-wide token with one request, and while a manual run holds the lock the confirm route answers 409 `RUN_IN_PROGRESS`. The route has only the default limit of 600 per minute (`rate_limiter.py:18`). One script looping on it from any tenant keeps the Super Admin's Confirm deletion answering 409 (stale review), and the tenant's own rows stay waiting precisely because the confirmation is being blocked. The refusal clears only when the loop stops. Because the review spans all organizations, one tenant can stall retention confirmation for every tenant. An honest tenant admin pressing the button during a review causes the same 409 by accident.

**Fix:** Do not change the count row when nothing changed, so the token only moves for a real recount:

```python
async def _record_count(db, tenant_id, rtype, days, now):
    try:
        count, error = await count_type(db, rtype, tenant_id, days, now), None
    except Exception as exc:
        count, error = None, f"{type(exc).__name__}: {exc}"[:300]
        logger.warning(...)
    coll = raw(db)[gate.COUNTS]
    prev = await coll.find_one({"tenantId": tenant_id, "type": rtype.id},
                               {"_id": 0, "days": 1, "count": 1, "error": 1})
    if prev and prev.get("days") == days and prev.get("count") == count and prev.get("error") == error:
        return count, error                       # same answer: keep the old countedAt, keep the token
    await coll.update_one(...)                    # as today
```

Optionally also have a manual run skip recounting a row whose usable count already exists, and rate limit the route per tenant.

### WR-04 (carried, open): un-gated platform-wide delete paths remain in `retention_service.py`

Not re-reviewed this round. See the previous review entry; unchanged.

## Info

### IN-06: `gate_state` parameter shadows the module function `tenant_created_at`

**File:** `backend/retention_gate.py:129-130` (function defined at `:120`)

**Issue:** The new parameter is named `tenant_created_at`, the same name as the async function defined nine lines above it. It is harmless today because the body never calls the function, but any later edit that wants to call `tenant_created_at(db, ...)` inside `gate_state` gets the datetime instead, and fails with a confusing `TypeError`.

**Fix:** Rename the parameter to `created` (the body already uses that local name for the aware value) and update the keyword uses in the tests.

### IN-07: Adoption now rests on a mutable `createdAt`, and the demo seed script rewrites it for existing tenants

**File:** `backend/seed_demo_data.py:19,26,30`

**Issue:** `await db.tenants.update_one({"id": t["id"]}, {"$set": t}, upsert=True)` sets `createdAt` to the current time on every run, including for tenants that already exist (the Acme and Exafluence entries are real-looking ids). Adoption (`created > global confirmedAt`) trusts that field, so running this script after the first confirmation makes those tenants read as brand new, and the next nightly run deletes their old records without a count or a confirmation. The script has no caller in the app (manual use only), and the live tenant routes cannot set `createdAt`, so this is a latent path, not an active one.

**Fix:** In the script use `{"$set": {k: v for k, v in t.items() if k != "createdAt"}, "$setOnInsert": {"createdAt": ...}}`. Longer term, record an explicit immutable `retentionAdoptable` or the creation time inside the gate collection at tenant creation, so adoption does not depend on a field every writer can touch.

### IN-08: The "run document without `finishedAt`" branch of `run_in_progress` can never match

**File:** `backend/retention_job.py:247-249`

**Issue:** `run_all` and `run_manual` insert their run document only at the end, with `finishedAt` set (`:193-195`, `:281-284`). `count_documents({"finishedAt": {"$exists": False}, ...})` therefore never counts anything, and "a run is in progress" rests only on the lock document. If the lock expires while a run is still going (event loop blocked past the 120 s TTL), the confirm route and the review no longer see the run. The docstring promises both signals.

**Fix:** Either insert a `{startedAt, trigger}` document at the start of `run_all` and update it at the end, or delete the dead branch and the claim in the docstring.

## Carried from the previous review (not re-reviewed)

- WR-04: un-gated delete paths remain in `backend/retention_service.py`. Open.
- IN-01: outbox pages are trigger-only. Open.
- IN-02: `testAlert.error` and Activity `error` params are not URL-scrubbed. Open.
- IN-03: loopback test compares literal strings. Open.
- IN-04: INSTALL.md section 12 names a control that does not exist there. Open.
- IN-05: service state from the snapshot is not validated server-side. Open.

Already recorded and not re-reported: the client-side limit on "every row loaded", `_EVENT_ID` accepting one trailing newline, the LedgerUnavailable log line, the adoption persistent case (A-82-A16), the sub-millisecond adoption window (A-82-A15), and the UI items in 82-UI-REVIEW.md (including the 409 incomplete answer showing the "counts changed" text).

---

_Reviewed: 2026-10-31_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
