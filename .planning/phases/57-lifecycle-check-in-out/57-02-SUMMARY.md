---
phase: 57-lifecycle-check-in-out
plan: 02
subsystem: api
tags: [fastapi, pydantic, mongodb, motor, itam, tenant-isolation, rbac, tdd]

requires:
  - phase: 57-lifecycle-check-in-out
    plan: 01
    provides: "assignment_history collection + itam_lifecycle_service.py (write_history/list_history), itam_lifecycle_endpoints.py router, ACTION_CHECKIN/ACTION_AUDIT constants, _now_iso helper"
provides:
  - "POST /api/assets/{asset_id}/checkin — atomic guarded return-to-stock that clears assignment, retains locationId (ITAM-LIFE-03)"
  - "GET /api/assets/{asset_id}/history — the full per-asset hand-off trail, newest first, deterministic ts/_id-descending total order (ITAM-LIFE-04, write half was 57-01)"
  - "CheckinRequest model + _deployed_guard() (the reverse of 57-01's _deployable_guard())"
  - "Regression tests pinning the append-only prohibition at both the router and the service-module surface"
affects: [57-03-physical-audit, 61-frontend-itam-console]

tech-stack:
  added: []
  patterns:
    - "Deployed-only guard (no missing-key admission), the deliberate asymmetry with checkout's deployable-or-absent guard — an asset that was never checked out through this API must never be silently returned to stock by a stray check-in"
    - "A state-clearing transition uses $set and $unset in the same find_one_and_update update document — no separate read/clear/write steps"
    - "Tenant-isolation boundary for a read route implemented as an existence check (assets.find_one) strictly before the scoped read, so unknown and cross-tenant ids produce the same 404 and the scoped read never executes for either"
    - "Self-referencing MagicMock cursor double (sort/limit return the cursor itself, to_list is the only AsyncMock leaf) for mocking a chained Motor cursor — AsyncMock's own unconfigured children default to AsyncMock, so a bare AsyncMock-returning find() double breaks a .sort().limit().to_list() chain with an unawaited-coroutine error"

key-files:
  created:
    - backend/tests/test_itam_lifecycle_history.py
  modified:
    - backend/itam_models.py
    - backend/itam_lifecycle_endpoints.py
    - backend/tests/test_itam_lifecycle.py
    - backend/tests/itam_lifecycle_test_support.py

key-decisions:
  - "Row 2 (ITAM-LIFE-03, unclassified) resolved: check-in is gated on lifecycleStatus==deployed exactly (no missing-key admission, unlike checkout's guard), and clears exactly five assignment fields via $unset while deliberately never touching locationId — D-02 defines locationId as current physical location, not assignment."
  - "Row 3 (ITAM-LIFE-04, adjacency) resolved: two assignment_history entries sharing an identical ts both persist and both return from the history read — never merged or deduplicated."
  - "Row 4 (ITAM-LIFE-04, empty) resolved: an asset with zero history entries returns 200 + [], never 404/null; an unresolvable or cross-tenant asset id returns 404 identical to the unknown-id case, and the scoped history read never executes for either."
  - "Row 5 (ITAM-LIFE-04, ordering) resolved: sort is the two-key form [(\"ts\", -1), (\"_id\", -1)] — already implemented in 57-01's list_history, regression-pinned here at the route level."
  - "New test file (test_itam_lifecycle_history.py) rather than appending to test_itam_lifecycle.py or test_itam_lifecycle_expansion.py — both were already close to the CLAUDE.md 500-line cap after Task 1's checkin tests; same split precedent 57-01 established."
  - "Fixed a latent test-fixture bug while wiring Task 2: _make_col()'s find() returns a bare AsyncMock, whose own unconfigured child attributes (.sort) default to AsyncMock too, so a naive .find().sort().limit().to_list() mock chain returned an unawaited coroutine instead of a chainable cursor. Replaced with a self-referencing MagicMock cursor (sort/limit return self, to_list is the only async leaf) in the shared mock_db fixture."

patterns-established:
  - "Reverse-transition endpoints (check-in mirrors check-out) live in the same router file, share the same tenant/permission preamble, and reuse the identical 404-vs-409 disambiguation follow-up read — copy the shape, invert the guard and the $set/$unset direction."

requirements-completed: [ITAM-LIFE-03, ITAM-LIFE-04]

coverage:
  - id: D1
    description: "An admin can check a deployed asset back in through POST /api/assets/{asset_id}/checkin; the asset returns to stock with lifecycleStatus deployable"
    requirement: "ITAM-LIFE-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_returns_asset_to_stock"
        status: pass
    human_judgment: false
  - id: D2
    description: "Check-in clears the five assignment fields via $unset (assignedToType/assignedToId/checkedOutAt/checkedOutBy/expectedReturnDate) and deliberately never touches locationId (D-02)"
    requirement: "ITAM-LIFE-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_clears_assignment_fields"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_retains_location_id"
        status: pass
    human_judgment: false
  - id: D3
    description: "Check-in of an asset not currently checked out is refused with 409 (no history write); a missing/cross-tenant asset id is refused with 404; two concurrent check-ins against one asset yield exactly one 200 and one 409"
    requirement: "ITAM-LIFE-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_of_asset_not_checked_out_returns_409"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_of_missing_asset_returns_404"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_concurrent_checkin_only_one_succeeds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_requires_manage_assets_permission"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every successful check-in writes exactly one assignment_history entry (action=checkin, actorUsername, ts, optional note, no target fields, no agent-liveness status key)"
    requirement: "ITAM-LIFE-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_writes_one_history_entry"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_records_optional_note"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckinAsset::test_checkin_does_not_write_agent_liveness_field"
        status: pass
    human_judgment: false
  - id: D5
    description: "GET /api/assets/{asset_id}/history returns an asset's full hand-off trail newest-first under a deterministic ts-descending/_id-descending total order; two entries sharing an identical ts both persist and both return"
    requirement: "ITAM-LIFE-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_returns_entries_newest_first"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_sort_is_a_deterministic_total_order"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_identical_timestamps_both_returned"
        status: pass
    human_judgment: false
  - id: D6
    description: "An asset with no history returns 200 + empty list, never 404/null; an unknown or cross-tenant asset id returns 404 identical for both, and the scoped history read never executes for either case; a limit above 500 is rejected with 422; the route is RBAC-gated"
    requirement: "ITAM-LIFE-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_empty_returns_200_and_empty_list"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_unknown_asset_returns_404"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_cross_tenant_asset_returns_404"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_respects_limit_cap"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_requires_manage_assets_permission"
        status: pass
    human_judgment: false
  - id: D7
    description: "No route on the lifecycle router uses PUT/PATCH/DELETE, and itam_lifecycle_service.py exposes exactly write_history/list_history — the append-only guarantee is regression-tested at both the routing and the service-module surface, not only by convention"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_no_mutating_route_exists_on_the_lifecycle_router"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_history.py::TestAssignmentHistory::test_history_service_module_exposes_no_mutating_function"
        status: pass
      - kind: other
        ref: "backend/venv/bin/python -c \"import itam_lifecycle_endpoints as m; bad=[(r.path, sorted(r.methods)) for r in m.router.routes if {'PUT','PATCH','DELETE'} & set(r.methods)]; assert bad == []\""
        status: pass
    human_judgment: false

duration: ~30min
completed: 2026-08-04
status: complete
---

# Phase 57 Plan 02: ITAM Lifecycle Check-In & History Read Summary

**Atomic check-in endpoint (POST /api/assets/{asset_id}/checkin) that closes the hand-off round trip 57-01 opened, plus the per-asset history read (GET /api/assets/{asset_id}/history) that makes the append-only assignment_history trail actually visible — with all three ITAM-LIFE-04 edge semantics (empty, identical timestamps, tie ordering) pinned by tests.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-08-04T13:20 (session, includes 57-01 file review carried into this plan's context)
- **Completed:** 2026-08-04T13:58:11Z
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- New `POST /api/assets/{asset_id}/checkin` route: an admin returns a checked-out asset to stock in one atomic guarded transition. The guard (`_deployed_guard()`) is the deliberate inverse of checkout's guard — it admits only `lifecycleStatus == "deployed"` exactly, never a missing key, so an asset that was never checked out through this API (an agent-discovered asset, a `retired`/`disposed`/`broken` record) can never be silently flipped into stock by a stray check-in.
- The transition's `$unset` document names exactly five fields (`assignedToType`, `assignedToId`, `checkedOutAt`, `checkedOutBy`, `expectedReturnDate`) and deliberately never touches `locationId` — D-02 defines that field as the asset's current physical location, not its assignment, so returning an asset to stock must never erase where it actually is.
- Full refusal surface mirrors checkout: 409 for any non-deployed starting status (no history entry written), 404 for a missing or cross-tenant asset id, 403 without `manage:assets`. A real `asyncio.gather` concurrency test proves the deployed-status guard living inside the `find_one_and_update` filter yields exactly one 200 and one 409 against two simultaneous check-ins — never two successes.
- Every successful check-in writes exactly one `assignment_history` entry (`action="checkin"`, `actorUsername`, `ts`, optional `note`) carrying no target fields — a check-in has no target, unlike a check-out.
- New `GET /api/assets/{asset_id}/history` route: resolves the asset through the tenant-isolated `assets` collection first — that lookup is the route's entire tenant-isolation boundary, since an unknown id and a cross-tenant id both resolve to nothing and both get the identical 404 (never disclosing which case it is), and the scoped history read never executes for either. An asset that resolves but has no entries returns 200 with an empty list, never 404/null. `limit: int = Query(100, ge=1, le=500)` bounds every read (T-57-13).
- The three ITAM-LIFE-04 edge semantics the spec-less probe surfaced are each pinned by a dedicated test: two entries sharing an identical `ts` both persist and both return (never merged/deduplicated); the sort handed to the cursor is the two-key form `[("ts", -1), ("_id", -1)]`, not a single key, giving a deterministic total order for tied timestamps; an asset with zero entries is a real, distinct 200-empty-list answer from "asset does not exist."
- The 57-01 append-only prohibition is now regression-tested at two layers from inside the test suite (not only by plan-time convention): no route on the lifecycle router uses PUT/PATCH/DELETE under any path, and `itam_lifecycle_service.py`'s public surface is exactly `list_history`/`write_history`.
- Fixed a latent shared-fixture bug discovered while wiring Task 2's tests: `_make_col()`'s `find()` returns a bare `AsyncMock`, and an `AsyncMock`'s own unconfigured child attributes default to `AsyncMock` too — so `.sort([...])` on that double returned an unawaited coroutine instead of a chainable cursor, breaking the `.sort().limit().to_list()` chain `list_history` performs. Replaced with a self-referencing `MagicMock` cursor (`sort`/`limit` return the cursor itself, `to_list` is the only async leaf) in the shared `mock_db` fixture.

## Task Commits

Each task followed the plan's `tdd="true"` RED/GREEN cycle:

1. **Task 1: Check an asset back in** — `dc4c74c` (test, RED) + `d76c97e` (feat, GREEN)
2. **Task 2: Make the trail visible per asset** — `7be8d00` (test, RED) + `0f5995b` (feat, GREEN)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `backend/itam_models.py` — added `CheckinRequest` (`note` only, `extra="forbid"`) directly after `CheckoutRequest`
- `backend/itam_lifecycle_endpoints.py` — added `_deployed_guard()`, `checkin_asset` handler, `list_assignment_history` handler; imports `CheckinRequest`, `Query`, `list_history`
- `backend/tests/test_itam_lifecycle.py` — added `TestCheckinAsset` (10 tests: happy path, field-clearing, locationId retention, 409/404 refusals, one-history-entry, optional note, concurrency, RBAC, no agent-liveness field)
- `backend/tests/test_itam_lifecycle_history.py` — new file, `TestAssignmentHistory` (10 tests: newest-first, deterministic sort, identical-timestamp both-returned, empty, unknown/cross-tenant 404, limit cap, RBAC, router/service-module append-only regression guards)
- `backend/tests/itam_lifecycle_test_support.py` — `find_one_and_update` default plus the self-referencing `assignment_history.find()` cursor double the history route's tests need

## Decisions Made

See `key-decisions` in frontmatter (spec-less-probe rows 2 through 5, all resolved as the plan's `<flagged_assumptions>` anticipated, plus two execution-time decisions: the new test file to respect the 500-line cap, and the shared-fixture cursor-chain fix).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, test-fixture only] `assignment_history` mock cursor chain returned an unawaited coroutine**
- **Found during:** Task 2, first test run against the newly-added history route
- **Issue:** `itam_lifecycle_test_support.py`'s shared `mock_db` fixture built every collection with `tests/conftest.py::_make_col()`, whose `find` is `MagicMock(return_value=AsyncMock())`. An `AsyncMock`'s own unconfigured child attributes default to `AsyncMock` as well, so setting `.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(...)` still left `.sort(...)` itself returning an unawaited coroutine rather than a synchronous cursor — `list_history`'s real `.find().sort().limit().to_list()` chain broke with `AttributeError: 'coroutine' object has no attribute 'limit'`.
- **Fix:** Replaced the chain with a self-referencing `MagicMock` cursor (`sort.return_value` and `limit.return_value` both point back to the same cursor object; only `to_list` is an `AsyncMock` leaf), assigned directly to `db.assignment_history.find`. Existing and new test code that sets `.find.return_value.sort.return_value.limit.return_value.to_list` per-test still works unchanged, since that chain resolves back to the same cursor object.
- **Files modified:** `backend/tests/itam_lifecycle_test_support.py`
- **Verification:** `pytest backend/tests/test_itam_lifecycle_history.py -q` — 4 previously-failing tests now pass; full lifecycle suite (39 tests) green
- **Committed in:** `0f5995b` (Task 2 GREEN commit)

**2. [Scope efficiency, not a Rule 1-4 fix] New test file rather than appending to an existing one**
- **Found during:** Planning Task 2's test placement
- **Effect:** `test_itam_lifecycle.py` grew to 396 lines after Task 1's 10 checkin tests, and `test_itam_lifecycle_expansion.py` was already at 347 lines from 57-01 — appending Task 2's 10 history tests to either would have risked breaching CLAUDE.md's 500-line cap. Created `backend/tests/test_itam_lifecycle_history.py` instead, following the exact split precedent 57-01 established.
- **Verification:** `wc -l` confirms every touched file is under 500 lines (largest is 396)

---

**Total deviations:** 2 (1 auto-fixed test-fixture bug [Rule 1], 1 scope-efficiency file-placement note)
**Impact on plan:** No scope creep beyond what the plan itself specified. The fixture fix was necessary for the history route's own tests to exercise the real `list_history` cursor chain rather than a broken double; the file split was mandatory under CLAUDE.md and left no test coverage or behavior changed.

## Issues Encountered

None beyond the deviation documented above.

## Known Stubs

None. Every code path added in this plan reads/writes real (mocked-in-tests) collections; no hardcoded empty values, placeholder text, or unwired data paths.

## User Setup Required

None — no external service configuration required. No new indexes or migrations; this plan reuses 57-01's `assignment_history` indexes unchanged.

## Next Phase Readiness

- **57-03 (physical audit)** can build on `ACTION_AUDIT`/`AUDIT_INTERVAL_DAYS` (already declared in `itam_lifecycle_endpoints.py`) and the `assets.lastAuditedAt` index 57-01 added, following this plan's established pattern for a third state-adjacent transition endpoint on the same router.
- **Phase 61 (frontend ITAM console)** now has both halves of the hand-off loop (`checkout`/`checkin`) and the history read to render against — the full `assignedToType`/`assignedToId`/`assignment_history` document shape plus a stable, paginated-by-limit read surface.
- No blockers. Full backend suite re-run after both tasks: 1620 passed / 35 skipped / 3 failed, all 3 failures pre-existing and confirmed unrelated (`test_agentic_ai` tool_choice, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type) — identical to the 57-01 baseline (`test_graphql.py` excluded from the run per the pre-existing strawberry/pydantic environment incompatibility noted in project memory).

---
*Phase: 57-lifecycle-check-in-out*
*Completed: 2026-08-04*
