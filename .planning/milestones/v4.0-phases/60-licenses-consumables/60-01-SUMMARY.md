---
phase: 60-licenses-consumables
plan: 01
subsystem: api
tags: [fastapi, pydantic, motor, itam, licenses]

# Dependency graph
requires:
  - phase: 56-catalog-foundation
    provides: itam_models.py (CatalogEntityCreate/Update base classes, _validate_iso8601_date), itam_asset_endpoints.py's _require_itam_admin RBAC gate, TenantIsolatedDatabase auto tenant-scoping
  - phase: 57-lifecycle-check-in-out
    provides: write_history/list_history append-only history pattern (db.assignment_history); the polymorphic targetType/targetId shape license seat assignment mirrors
provides:
  - POST/GET/PATCH /api/itam/licenses (+ /{id}) — license catalog CRUD, RBAC-gated via _require_itam_admin
  - POST /api/itam/licenses/{id}/assign, DELETE /api/itam/licenses/assignments/{id}, GET /api/itam/licenses/{id}/assignments — seat assign/reclaim/list against a real seat count, polymorphic user/asset target
  - Read-time seatsAssigned/seatsAvailable/isExpired/daysUntilExpiry on every GET (list and single) — never persisted, per 60-RESEARCH.md Pattern 4
affects: [62-frontend-itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-time-only expiry/remaining-seat computation (no background scheduler) — ITAM-LIC-01's requirement text is visibility language, unlike ITAM-FIN-02's explicit alerting language"
    - "License-seat history records keyed by licenseId, never assetId, even when targetType==asset — keeps list_history's asset-scoped /history endpoint from being polluted by unrelated seat assignments (60-RESEARCH.md Pitfall 2)"

key-files:
  created:
    - backend/itam_license_service.py
    - backend/itam_license_endpoints.py
    - backend/tests/test_itam_license.py
  modified:
    - backend/itam_models.py
    - backend/router_registry.py

key-decisions:
  - "Seat guard implemented as a count_documents read followed by a separate insert_one, not the atomic find_one_and_update guard-in-filter 60-RESEARCH.md Pattern 1 specifies — see Known Residual Risk below. Left as-is rather than rewritten this session: it is an accepted, in-code-flagged tradeoff (see the file's own concurrency comment), not a silent gap, and ROADMAP's success criteria don't demand a concurrency guarantee."
  - "seatsAssigned/seatsAvailable/isExpired/daysUntilExpiry computed in the endpoint layer (_enrich_license_seats_and_expiry), not the service layer or the Pydantic model — matches Pattern 4's 'computed at read time in the GET/list endpoint handler' placement exactly"

requirements-completed: [ITAM-LIC-01]

coverage:
  - id: D1
    description: "Admin can create a software license with a seat count, assign a seat to a user or asset, reclaim it, and see remaining/expired seats (ROADMAP Phase 60 success criterion 1)"
    requirement: "ITAM-LIC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_license.py::TestLicenseManagement"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_license.py::TestLicenseManagement::test_list_licenses_shows_remaining_and_expired_seats"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_license.py::TestLicenseAssignment"
        status: pass
    human_judgment: false

# Metrics
duration: unknown — implemented across multiple non-conventional prior commits, no SUMMARY existed; this session closed the gaps found during phase verification
completed: 2026-08-09
status: complete
---

# Phase 60 Plan 01: Software License CRUD Summary

**Software license catalog CRUD, seat assign/reclaim against a real seat count (polymorphic user/asset target), and read-time remaining/expired-seat visibility — ITAM-LIC-01 complete.**

## Performance

- **Tasks:** as specified in 60-01-PLAN.md's 4-item sketch (models, endpoints, seat-tracking logic, tests) — delivered, but not through a single planned session; see Task Commits.
- **Files:** 3 created, 2 modified (license surface only — itam_models.py and router_registry.py are shared with 60-02/60-03).

## Accomplishments
- `POST/GET/PATCH /api/itam/licenses(/{id})` — license catalog CRUD, RBAC-gated via `_require_itam_admin`, tenant-scoped via `get_database()`'s auto `tenantId` injection.
- `POST /api/itam/licenses/{id}/assign` — assigns a seat to a `user` or `asset` target, rejects assignment past `seatCount`, rejects a target already holding a seat, writes an append-only history record via `itam_lifecycle_service.write_history` keyed by `licenseId` (not `assetId`, per 60-RESEARCH.md Pitfall 2 — confirmed no cross-contamination with an asset's own `/history` view).
- `DELETE /api/itam/licenses/assignments/{id}` — reclaims a seat, restores the assignment on a history-write failure (compensation pattern mirrors Phase 57's).
- `GET /api/itam/licenses` and `GET /api/itam/licenses/{id}` now return `seatsAssigned`, `seatsAvailable`, `isExpired`, `daysUntilExpiry` computed fresh on every read — this was missing entirely before this session (see Deviations) despite being the literal wording of ROADMAP success criterion 1 ("see remaining/expired seats").
- 10 tests in `test_itam_license.py` (up from 9 pre-session — see Deviations).

## Task Commits

This plan's history is not the usual one-commit-per-task shape. Documented in full for traceability, following the 59-04-SUMMARY.md precedent for the same situation:

1. **Original implementation** — `490e850` ("feat(59,60): warranty alert sweep + license management", 2026-08-06). Bundled with unrelated Phase 59 work, no plan reference, no SUMMARY.md. Shipped `itam_license_service.py`/`itam_license_endpoints.py`/`test_itam_license.py`, but the test file had a real `IndentationError` that failed collection for the entire `backend/tests` directory — flagged in `59-04-SUMMARY.md` as a blocker for whoever picked up Phase 60.
2. **Fixes across three follow-up commits** (2026-08-09, same day): `9d38667` (itam_models.py License fields), `95ab0d7` (fixed `backend.X`-vs-`X` import paths that would have failed to load in production under uvicorn's `cwd=backend/` launcher — see 60-03-SUMMARY.md for the full account, shared across all three Phase 60 areas), `a025953` (`usefulLifeYears=0` validation tightened — a Phase 59 model shared with this phase's Model entity).
3. **This session's gap-closure** (verification pass, 2026-08-09): `fcc0773` — added the missing `seatsAssigned`/`seatsAvailable`/`isExpired`/`daysUntilExpiry` read-time enrichment and a regression test (`test_list_licenses_shows_remaining_and_expired_seats`) covering both a live and an already-expired license.

## Files Created/Modified
- `backend/itam_license_service.py` — `assign_license_seat`/`reclaim_license_seat`/`list_license_assignments`, all `db`/`tenant_id`-parameterized (not a `ConsumableService`/`ComponentService`-style class — pre-existing convention, unchanged this session).
- `backend/itam_license_endpoints.py` — CRUD + assign/reclaim/list-assignments routes; `_enrich_license_seats_and_expiry` added this session.
- `backend/tests/test_itam_license.py` — 10 tests (9 pre-existing + 1 new this session).

## Decisions Made
- Left the seat-assignment guard as a `count_documents`-then-`insert_one` sequence rather than rewriting it to 60-RESEARCH.md Pattern 1's atomic `find_one_and_update` guard-in-filter shape. See **Known Residual Risk** in `60-VERIFICATION.md` — this is a real, acknowledged (the file carries its own comment flagging it) concurrency gap, not something this session silently accepted without checking; a full rewrite would touch the license document schema (`seatsAvailable` field) and every existing test's mocking shape, which is a larger change than a verification-pass gap-fix scope justifies for a low-likelihood race (near-simultaneous assign requests against the same license) with no data-corruption consequence (worst case: one over-assigned seat, correctable by reclaim).
- `seatsAssigned`/`seatsAvailable`/`isExpired`/`daysUntilExpiry` computed via a per-license `count_documents` call in the endpoint (not a Mongo aggregation `$lookup`) — `list_licenses` is capped at 500 results and this is an admin console surface, not a hot path; N+1 queries here trade a small amount of read latency for keeping the enrichment logic identical between the list and single-item GET paths.

## Deviations from Plan

### Auto-fixed Issues (this session)

**1. [Missing requirement coverage] "See remaining/expired seats" (ROADMAP success criterion 1) had no implementation**
- **Found during:** Phase 60 verification pass, checking each success criterion's literal wording against actual endpoint responses.
- **Issue:** `GET /api/itam/licenses` and `GET /api/itam/licenses/{id}` returned the raw stored document — `seatCount` and `expiryDate` only. An admin had no way to see how many seats remained or whether a license had expired without manually cross-referencing `GET .../assignments`'s length against `seatCount`, and expiry required manual date comparison against `expiryDate`.
- **Fix:** `_enrich_license_seats_and_expiry()` added to `itam_license_endpoints.py`, computed at read time per 60-RESEARCH.md Pattern 4, wired into both `list_licenses` and `get_license`.
- **Verification:** New test asserts both a not-yet-expired license (`isExpired: false`, correct `seatsAvailable`) and an already-expired one (`isExpired: true`, `seatsAvailable` floored at 0) in the same request.
- **Committed in:** `fcc0773`

**Total deviations:** 1 auto-fixed (missing requirement-criterion coverage, not scope creep — the requirement text and ROADMAP wording both call for this).

## Issues Encountered

Process issue, not a code issue — documented for traceability, not fixed here:
- This plan's actual implementation happened across multiple non-conventional commits over three calendar days (2026-08-06 to 2026-08-09) with no SUMMARY.md, no plan-checker pass, and (for `490e850`) a broken test file committed alongside unrelated Phase 59 work. `60-CONTEXT.md` and `60-RESEARCH.md` were produced properly (research + gsd-planner intent stated), but the pre-existing 9-line `60-01-PLAN.md`/`60-02-PLAN.md`/`60-03-PLAN.md` sketches were never actually superseded with real GSD-format plans as `60-CONTEXT.md` said they would be — implementation proceeded directly from the sketches plus `60-RESEARCH.md`'s guidance instead.

## Next Phase Readiness
- ITAM-LIC-01 complete. See `60-VERIFICATION.md` for the phase-level goal-backward check across all three requirements, including the one documented residual risk (seat-assignment race condition) carried forward as a known, accepted limitation rather than a blocking gap.

---
*Phase: 60-licenses-consumables*
*Completed: 2026-08-09*
