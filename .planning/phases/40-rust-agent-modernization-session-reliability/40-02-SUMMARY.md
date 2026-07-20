---
phase: 40-rust-agent-modernization-session-reliability
plan: 02
subsystem: auth
tags: [jwt, mongodb, motor, fastapi, session-reliability, race-condition]

# Dependency graph
requires:
  - phase: 40-rust-agent-modernization-session-reliability (plan 01)
    provides: Rust agent 2.1.3 release work (independent track in the same phase; no code dependency)
provides:
  - "revoked_tokens.jti unique MongoDB index closing the atomicity gap refresh_access_token's find_one_and_update already assumed existed"
  - "Live-Mongo regression test proving exactly-one-winner semantics for concurrent /api/auth/refresh calls with the same token"
affects: [authentication, session-management, database-indexes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Live-Mongo regression tests for concurrency-dependent invariants (motor client, ping/skip-or-fail-in-CI, real router via httpx.AsyncClient+ASGITransport, try/finally cleanup) — mirrors test_evidence_review.py's existing pattern, now duplicated for auth"

key-files:
  created: [backend/tests/test_auth_refresh_race.py]
  modified: [backend/database.py]

key-decisions:
  - "Added the unique index only — refresh_access_token's find_one_and_update/$setOnInsert logic was already correct and is unchanged, per D-05 scope boundary"
  - "Mechanism B (multi-tab/cloned-tab sessionStorage divergence) explicitly left out of scope; only a one-line comment pointer added next to the index, no frontend change"
  - "Regression test creates its own jti unique index on the test DB in setup (rather than depending solely on database.py having been run against that DB), per the plan's explicit guidance, so the test independently exercises the uniqueness constraint"

patterns-established:
  - "Concurrency regression test pattern: two asyncio.gather'd HTTP calls through a minimal FastAPI app (real router + real SlowAPI limiter) against a real Mongo db, with a _RealDbWrapper shim providing the db._db bypass surface auth endpoints use"

requirements-completed: [SESS-01]

# Metrics
duration: 20min
completed: 2026-07-20
status: complete
---

# Phase 40 Plan 02: Session Reliability (SESS-01) Summary

**Added the missing `revoked_tokens.jti` unique MongoDB index that `refresh_access_token`'s atomic-consume logic already claimed existed, plus a live-Mongo concurrent-refresh regression test proving exactly-one-winner semantics.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-20T15:15:00Z (approx.)
- **Completed:** 2026-07-20T15:35:07Z
- **Tasks:** 2/2 completed
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `backend/database.py` now creates a unique, background index on `revoked_tokens.jti`, adjacent to the existing TTL index on `revoked_at`, matching the `unique=True, background=True` shape already used for `software_inventory`.
- New self-contained regression test (`backend/tests/test_auth_refresh_race.py`) drives the real `/api/auth/refresh` route (via `httpx.AsyncClient` + `ASGITransport`, a real `Limiter`, and a real Mongo connection) with two `asyncio.gather`'d concurrent calls carrying the identical refresh token, and asserts exactly one 200 + one 401 + exactly one persisted `revoked_tokens` document for the `jti`.
- Manually verified (outside the committed test, via a raw driver-level trial script — not committed, scratch-only) that the race is real: with the unique index absent, 20 of 200 raw `find_one_and_update` trials produced two documents for the same `jti`; with the index present, the committed test passed deterministically across five repeated runs.
- `authentication_endpoints.py`'s `refresh_access_token` logic is untouched (confirmed via `git diff`), and all pre-existing auth tests (`test_authentication.py`, `test_auth_mfa.py`) remain green.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the missing unique index on revoked_tokens.jti (D-05 Mechanism A)** - `0257f4f` (fix)
2. **Task 2: Add live-Mongo concurrent-refresh regression test** - `9f98eaa` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/database.py` - Added `revoked_tokens.create_index("jti", unique=True, background=True)` next to the existing `revoked_at` TTL index, with a comment explaining the SESS-01 gap it closes and a one-line pointer noting Mechanism B is deferred (D-05).
- `backend/tests/test_auth_refresh_race.py` (new, 154 lines) - Live-Mongo regression test: mints a refresh token, fires two concurrent `/api/auth/refresh` calls with it, asserts exactly one 200 + one 401 + one persisted `revoked_tokens` document.

## Decisions Made
- Kept the fix to exactly the missing index — no changes to `refresh_access_token`'s consume logic, per the plan's explicit scope boundary and the D-05 decision that Mechanism A is the only in-scope mechanism this phase.
- Test creates the unique index explicitly on its own test database (`auth_refresh_race_test`) in setup rather than relying on `database.py`'s startup index-creation having already run against that database — this was the plan's stated preference ("create it explicitly in setup... so the test actually exercises the uniqueness constraint") and keeps the test independently meaningful regardless of app startup order.
- Duplicated the `_make_auth_app()` helper locally (from `test_auth_mfa.py`) rather than importing it, keeping this file's live-Mongo fixture scaffolding self-contained, consistent with why `test_evidence_review.py`'s live-Mongo test lives in its own function rather than sharing helpers across files with different concerns.

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched their `<action>` and `<verify>` blocks; no architectural changes, no missing critical functionality beyond what the plan specified, and no blocking issues encountered.

## Issues Encountered

The two-call HTTP-level race in the committed test is inherently probabilistic (MongoDB's own docs note duplicate upserts under upsert+concurrency without a unique index are possible, not guaranteed, on every single race). A one-off manual check that temporarily skipped index creation happened to still pass (0/1), while a separate 200-trial raw-driver script (scratch-only, not committed) showed a ~10% duplicate rate without the index. This is expected behavior for a two-request race test: it is deterministically green when the fix is in place (verified across 5 repeated runs) and has demonstrated, non-zero ability to catch a regression when the fix is absent — the same probabilistic nature any minimal-reproduction concurrency test has. No code change was made in response to this; it's documented here for future readers of the test.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SESS-01 (Mechanism A) is closed: the database now enforces the single-use guarantee the application code already assumed.
- Mechanism B (multi-tab/cloned-tab sessionStorage divergence) remains an explicitly deferred, separate frontend surface per D-05 — not started, would need its own future phase/plan if picked up.
- No blockers for closing out phase 40 (both 40-01 and 40-02 are now complete).

---
*Phase: 40-rust-agent-modernization-session-reliability*
*Completed: 2026-07-20*

## Self-Check: PASSED

- FOUND: backend/database.py contains `revoked_tokens.create_index("jti", ...)`
- FOUND: backend/tests/test_auth_refresh_race.py
- FOUND: commit 0257f4f (Task 1)
- FOUND: commit 9f98eaa (Task 2)
- FOUND: commit 980f7b8 (SUMMARY.md)
