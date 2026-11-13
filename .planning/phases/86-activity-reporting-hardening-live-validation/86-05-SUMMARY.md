---
phase: 86-activity-reporting-hardening-live-validation
plan: 05
subsystem: autonomous-ops-reporting
tags: [digest, notifications, smtp, distributed-lock, mongodb, pytest, autonomous-ops]
status: complete

requires:
  - phase: 86-01
    provides: reporting package constants (DIGEST_*, DIGESTS, state groups, EXCLUDED_KINDS) and rule_names
provides:
  - backend/autonomous_ops/reporting/digest_text.py (pure notice and email builders)
  - backend/autonomous_ops/reporting/digest.py (window queries, claim, quiet rule, tenant-admin notice, email)
  - backend/autonomous_ops/reporting/digest_job.py (due, run_once, digest_loop)
  - background task autonomous_ops_digest registered in app_startup
  - collection autonomy_digests with indexes digest_once_per_day and tenant_finished (made on the first pass)
affects: [86-13]

requirements-completed: [ACTV-04]

actuals:
  tokens: 14046
  tasks: 3
  commits: 6
plan_head_before: 8cd94bbf37df604439b9dbeea2b7e76b1234368b
plan_head_after: 278ba267a7e0a1bf21e2df0b6cd03d046e0206f1

tech-stack:
  added: []
  patterns:
    - claim (tenantId, day) before send under a unique index: at most once across restarts and workers
    - audience-tagged in-app notice written through pending_agents._post_in_app only
    - retention_job-style loop (lock_with_renewal, SimpleNamespace shim, _sleep indirection)

key-files:
  created:
    - backend/autonomous_ops/reporting/digest_text.py
    - backend/autonomous_ops/reporting/digest.py
    - backend/autonomous_ops/reporting/digest_job.py
    - backend/tests/test_autonomous_ops_digest.py
    - backend/tests/test_autonomous_ops_digest_job.py
  modified:
    - backend/app_startup.py

key-decisions:
  - "A read failure while gathering a day's counts releases the claim (nothing was sent yet), so the next 5-minute pass retries instead of losing the day. A crash after the notice is posted still leaves the claim 'claimed' and is never re-sent (A-86-A4)."
  - "A pass whose claim index cannot be made is skipped, not run unprotected (the same rule as the rollout loop)."
  - "Admin recipients exclude users whose status is Inactive, Disabled, Pending, Suspended or Locked; the compliance helper the plan names does not filter by status at all."
  - "The closing line of the email says the digest is also sent on days when shadow mode would have done something, because the amended D-03 sends simulation-only days."

duration: ~12min
completed: 2026-11-13
---

# Phase 86 Plan 05: Daily digest Summary

**Each ticked organization's admins now get one "Autonomous Ops daily digest" at 07:00 UTC (in-app always, email when mail is configured): the three counts, a separate simulation line, and up to 10 items per section, claimed once per organization and day so a restart, a second worker or a failing mail server never makes it two.**

## What was built

- **digest_text.py** (205 lines, pure): `DigestItem`, `Group(total, items)`, `counts_line`, `simulation_line`, `section_lines` (newest first, ties by id descending, cut at 10 with the overflow sentence, targets cut to 80 characters, control characters collapsed), `notice_title`, `notice_text`, `email_subject` (CR/LF stripped), `email_text` and `email_html` (`html.escape` on every server string, no images). `SIMULATION_VERBS` words the "Would have ..." lines.
- **digest.py** (189 lines): `window(day)` is the half-open 24 hours before 07:00 UTC; `gather` returns ran and undone by `finishedAt`, simulation by `createdAt`, and waiting as `incident_views._waiting_filter(now)` (the screen's own set), all on the raw handle with an explicit `tenantId` and control and platform-health rows excluded; `send_for_tenant` claims, stays quiet when all four counts are 0, posts one notice with the `tenant_admins` audience, emails admin-role users (each send inside `asyncio.wait_for` 30 s, failures only counted) and records state, counts and email result on the claim.
- **digest_job.py** (101 lines): `due`, `run_once` under the `autonomous_ops_digest` lock (None before 07:00, when the lock is held, or when the index cannot be made), one `distinct` read of today's claims, one `try/except` per organization, and `digest_loop` (120 s start delay, one info line `autonomous_ops digest loop started`, a pass every 300 s).
- **app_startup.py**: one comment line and two registration lines after the retention task (3 added lines, none of the user's hunks touched).

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | RED | 780c5e0a0 | test(86-05): add failing tests for the digest text |
| 1 | GREEN | dc7574c58 | feat(86-05): pure digest text for the in-app notice and the email |
| 2 | RED | d06712470 | test(86-05): add failing tests for the digest of one organization |
| 2 | GREEN | 873251240 | feat(86-05): daily digest for one organization |
| 3 | RED | d5811b66d | test(86-05): add failing tests for the 07:00 UTC digest loop |
| 3 | GREEN | 278ba267a | feat(86-05): 07:00 UTC digest loop with the single-runner lock |

## TDD Gate Compliance

All three tasks went RED then GREEN with an inert skeleton committed in each RED commit, so the failures are assertions on the planned behavior and not load errors. No refactor commits were needed.

- **Task 1:** 18 of 19 tests failed on empty-string assertions (for example `'' == 'Autonomous Ops daily digest for Acme'`); the one that passed was the bounded-length test, which an empty string satisfies. Semantic assessment: the target tests ran and failed on the planned text shapes. I did not run the `gsd-tools check tdd-red-evidence` classifier (plain pytest output, no JUnit report was persisted for this plan).
- **Task 2:** 19 of 38 failed (counts, claims, notices, email); the same assertion-style failures (`'quiet' == 'sent'`, `IndexError` on the missing notice, `DID NOT RAISE`) on the private mongod.
- **Task 3:** 7 of 11 failed (`None == {...}`, missing index, loop did not raise, registration string absent); the 4 that passed were the constants and the before-07:00 cases an inert skeleton already satisfies.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 3 tests live in a second file**
- **Found during:** Task 3
- **Issue:** `test_autonomous_ops_digest.py` was already 457 lines after Tasks 1 and 2, and the project rule is files under 500 lines.
- **Fix:** the loop tests are in `backend/tests/test_autonomous_ops_digest_job.py` (175 lines). I ran both files for the Task 3 verification.
- **Files modified:** backend/tests/test_autonomous_ops_digest_job.py (new)
- **Commit:** d5811b66d

**2. [Rule 1 - Bug prevented] Claim released on a read failure**
- **Found during:** Task 2 design
- **Issue:** the plan's "claim before send" would permanently lose a day's digest when the counting queries failed transiently, although nothing had been sent.
- **Fix:** `send_for_tenant` deletes its own `claimed` row and re-raises when `gather` fails; `run_once` counts it under `failed` and the next pass retries. Tested by `test_a_failed_read_releases_the_claim_so_the_day_is_not_lost` and `test_one_organizations_failure_never_stops_the_others`.
- **Commit:** 873251240, 278ba267a

**3. [Rule 2 - Missing critical] Skip the pass when the claim index cannot be made**
- **Issue:** the plan retries `ensure_indexes` on failure but does not say what to do meanwhile; sending without the unique index would break the once-a-day guarantee.
- **Fix:** `run_once` returns None and logs an error; tested.
- **Commit:** 278ba267a

**4. [Plan note] Email recipients filtered by status**
- The plan says "active users only, as `_tenant_admin_emails` does", but that helper has no status filter. I excluded Inactive, Disabled, Pending, Suspended and Locked users.

**5. [Plan note] Email closing line wording**
- UI-SPEC section 5 ends the email with "...only on days when something ran, was undone or is waiting for approval." Under the amended D-03 a simulation-only day also sends, so the sentence now ends "...is waiting for approval or would have been done in shadow mode."

**6. [Plan note] Acceptance grep for app_startup**
- `grep -c "autonomous_ops_digest" backend/app_startup.py` prints 1 (counts lines); the string appears twice on the single `create_task` line, which is what the plan's two prescribed lines can produce. The diff is exactly 3 added lines.

**7. [Plan note] Function shapes**
- `notice_text(ran, undone, waiting, simulation)` and `email_text/email_html(org, day, sections, link)` take `Group(total, items)` values (a plain list is also accepted), because the listed items are capped at 10 while the heading must show the true total.

### Test-run incident (disclosed)

My first run of `test_autonomous_ops_digest.py` (RED stage of Task 2) had no `MONGO_TEST_URL`, so the `mongo_db` fixture connected to the live mongod at 127.0.0.1:27017 and created, then dropped, one `omni_test_*` database. A read-only listing afterwards showed no `omni_test_*` database left. Every later run set `MONGO_TEST_URL`, `MONGODB_URL` and `MONGO_URI` to the private mongod at 27998.

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug prevented, 1 missing critical) plus 4 plan notes. **Impact:** none on the specified behavior.

## Verification

- `pytest` digest (38), digest job (11), copy gate, structural, retention job and notification audience structure, private mongod 27998: 148 passed, 0 skipped (`-rs`).
- `ruff check` on the new files: all checks passed.
- Acceptance greps: 7 builder functions in digest_text.py, 0 motor or `scope import raw` in it; 0 `notify.notify` or `post_to_recipients` in digest.py, `TENANT_ADMIN_AUDIENCE`, `_waiting_filter` and `wait_for` each present; digest.py 189 lines; `lock_with_renewal` present in digest_job.py.
- Nothing was run against the live database after the incident above, no restart, no UI publish, no push. The live digest starts only after the user's restart (86-13).

## Known Stubs

None.

## Threat Flags

None. The only new surface is the plan's own T-86-07..10 (tenant_admins audience, subject and html escaping, send time limit, claim); each has a test.

## Notes for later plans

- The digest creates `autonomy_digests` and its indexes on the first pass after the restart, so migration 035 may be a no-op for them.
- 86-13 can confirm the live start with the log line `autonomous_ops digest loop started`; the first digest goes out at the first wake after 07:00 UTC.
- There is no opt-out and no per-organization hour (both deferred), and a day with only failed or refused rows stays quiet by design (A-86-OQ3).

## Self-Check: PASSED

All five created files exist and all six commits (780c5e0a0, dc7574c58, d06712470, 873251240, d5811b66d, 278ba267a) are ancestors of HEAD.
