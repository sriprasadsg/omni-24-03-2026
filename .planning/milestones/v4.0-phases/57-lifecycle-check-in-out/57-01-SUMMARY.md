---
phase: 57-lifecycle-check-in-out
plan: 01
subsystem: api
tags: [fastapi, pydantic, mongodb, motor, itam, tenant-isolation, rbac, tdd]

requires:
  - phase: 56-catalog-foundation
    provides: assetSource discriminator, lifecycleStatus vocabulary/enum, ManualAssetCreate, _require_itam_admin RBAC dependency, next_asset_tag counter pattern
provides:
  - "POST /api/assets/{asset_id}/checkout — atomic guarded check-out to a user or a location (ITAM-LIFE-02)"
  - "Append-only assignment_history collection + itam_lifecycle_service.py (write_history/list_history — the entire public surface, ITAM-LIFE-04 write half)"
  - "itam_lifecycle_endpoints.py router (multi-segment routes only, mounted adjacent to itam_asset_endpoints) — the structural template 57-02/57-03/Phase 61 extend"
  - "Repaired Phase-56 defect: POST /api/assets was raising a false 500 on every real caller due to an errant await on a synchronous cache_service.invalidate_cache"
affects: [57-02-check-in-and-history-read, 57-03-physical-audit, 61-frontend-itam-console]

tech-stack:
  added: []
  patterns:
    - "Append-only audit/history service: exactly two exported coroutines (write_*/list_*), no update/delete anywhere in the module — modelled on remediation_audit_service.py"
    - "Atomic guarded state transition: the eligibility guard (lifecycleStatus deployable-or-absent) lives inside the find_one_and_update filter itself, never in a preceding conditional read — eliminates the TOCTOU window a separate read-then-write would introduce"
    - "Deployable-or-absent guard ($or: [{lifecycleStatus: 'deployable'}, {lifecycleStatus: {$exists: false}}]) admits every pre-existing agent-discovered asset that has never had the key written"
    - "Polymorphic assignment pair (assignedToType/assignedToId) rather than one nullable field per target kind (PD-01)"
    - "History-write failure surfaces as 500, never a false-success 200 — a state transition and its audit trail are treated as one atomic unit of trust"

key-files:
  created:
    - backend/itam_lifecycle_service.py
    - backend/itam_lifecycle_endpoints.py
    - backend/tests/test_itam_lifecycle.py
    - backend/tests/test_itam_lifecycle_expansion.py
    - backend/tests/itam_lifecycle_test_support.py
  modified:
    - backend/itam_models.py
    - backend/router_registry.py
    - backend/database.py
    - backend/itam_asset_endpoints.py
    - backend/tests/test_itam_foundation.py

key-decisions:
  - "PD-01: assignedToType/assignedToId polymorphic pair, not a single new assignedToUserId field reusing locationId for location targets — keeps a location check-out distinguishable from a catalogued home location and gives check-in one uniform clear (57-02)."
  - "PD-02 recorded but not yet exercised in this plan: the overdue-audit report route will be GET /api/assets/reports/overdue-audit (multi-segment, 57-03) — noted here since this plan's registration-order acceptance criterion depends on the same reasoning."
  - "PD-03: return_document=ReturnDocument.AFTER on the guarded transition — the handler returns the asset's new state to the caller."
  - "PD-04: assignment_history stores targetId/targetType references only, never a copied snapshot of the resolved user's email/name — enforced by never reading those fields into the history record in the first place, not by a redaction step."
  - "Implemented the full checkout handler (location branch, all four refusal paths, concurrency-safe atomic guard) directly in Task 1 rather than splitting incrementally across Task 1/2 as the plan's task boundaries suggested — both were straightforward to author together. Task 2 then added the ten tests proving the already-complete behavior, rather than driving new implementation."
  - "Split the combined test file into itam_lifecycle_test_support.py (shared fixtures) + test_itam_lifecycle.py (Task 1) + test_itam_lifecycle_expansion.py (Task 2/3) after it grew to 609 lines — CLAUDE.md's 500-line cap and this plan's own <verification> block both require every file under 500 lines. Task 2/3's literal <verify> command paths (which named test_itam_lifecycle.py specifically) are stale after the split; the underlying test coverage is unchanged and reproducible from the new paths (documented below)."

patterns-established:
  - "Lifecycle action endpoints live in one router file (itam_lifecycle_endpoints.py) mounted adjacent to itam_asset_endpoints.py, every route multi-segment under /{asset_id}/{action} so none can ever be shadowed by asset_endpoints.py's single-segment GET /{asset_id}, regardless of router registration order."

requirements-completed: [ITAM-LIFE-02, ITAM-LIFE-04]

coverage:
  - id: D1
    description: "An admin can check a deployable asset out to a platform user through POST /api/assets/{asset_id}/checkout; the asset comes back lifecycleStatus=deployed with assignedToType/assignedToId recorded"
    requirement: "ITAM-LIFE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckoutToUser::test_checkout_to_user_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "A location check-out overwrites the asset's locationId with the target id (D-02) while a user check-out leaves locationId untouched"
    requirement: "ITAM-LIFE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_to_location_overwrites_location_id"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_to_user_produces_no_location_id_key"
        status: pass
    human_judgment: false
  - id: D3
    description: "Refusal paths: 409 for a non-deployable asset, 404 for a missing/cross-tenant asset, 400 for an unresolvable user or location target, 403 for a caller lacking manage:assets — and an unresolvable-target check-out never mutates the asset"
    requirement: "ITAM-LIFE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_of_non_deployable_asset_returns_409"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_of_missing_asset_returns_404"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_target_user_not_found_returns_400"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_target_location_not_found_returns_400"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_requires_manage_assets_permission"
        status: pass
    human_judgment: false
  - id: D4
    description: "An agent-discovered asset with no lifecycleStatus key at all can still be checked out (missing key == deployable), and two concurrent check-outs against the same asset yield exactly one 200 and one 409 — never two successes"
    requirement: "ITAM-LIFE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_of_agent_asset_without_lifecycle_key_succeeds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_concurrent_checkout_only_one_succeeds"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every successful check-out writes exactly one immutable assignment_history entry (assetId/action/targetType/targetId/actorUsername/ts), never copies the target's email/name into it, and a history-write failure surfaces as 500 rather than a false-success 200"
    requirement: "ITAM-LIFE-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckoutToUser::test_checkout_writes_exactly_one_history_entry"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle.py::TestCheckoutToUser::test_checkout_history_entry_stores_reference_not_personal_data"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCheckoutExpansion::test_checkout_history_write_failure_surfaces_as_500"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCacheInvalidationRepair::test_checkout_invalidates_asset_cache_without_await"
        status: pass
    human_judgment: false
  - id: D6
    description: "itam_lifecycle_service.py exposes exactly write_history and list_history and no function that alters or removes a written record (the append-only guarantee); assignment_history has no expiry index; POST /api/assets returns 201 through the real (non-awaited) cache-invalidation call path, repairing a Phase-56 defect"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_expansion.py::TestCacheInvalidationRepair::test_manual_asset_creation_survives_real_cache_invalidation"
        status: pass
      - kind: other
        ref: "python -c \"import itam_lifecycle_service as s; assert sorted(n for n in dir(s) if not n.startswith('_') and callable(getattr(s,n)) and getattr(getattr(s,n),'__module__','')=='itam_lifecycle_service') == ['list_history','write_history']\""
        status: pass
      - kind: other
        ref: "grep -v '^\\s*#' backend/database.py | grep 'assignment_history' | grep -c expireAfterSeconds  (expect 0)"
        status: pass
    human_judgment: false

duration: 19min
completed: 2026-08-04
status: complete
---

# Phase 57 Plan 01: ITAM Lifecycle Check-Out Tracer Summary

**Atomic, tenant-isolated check-out endpoint (POST /api/assets/{asset_id}/checkout) with a new append-only assignment_history ledger, proving the entire Phase-57 router/collection/state-transition architecture end-to-end before 57-02/57-03/Phase-61 build on it.**

## Performance

- **Duration:** ~19 min
- **Started:** 2026-08-04T13:20:10Z (session)
- **Completed:** 2026-08-04T13:39:02Z
- **Tasks:** 3
- **Files modified:** 9 (5 created, 4 modified — plus 1 pre-existing test fixture repair)

## Accomplishments

- New `POST /api/assets/{asset_id}/checkout` route: admin checks a deployable asset out to a platform user or a location; the asset atomically transitions to `deployed` with `assignedToType`/`assignedToId` recorded, and a location check-out overwrites `locationId` (D-02) while a user check-out leaves it untouched.
- Atomic guarded transition: the deployable-or-absent-key guard lives inside the `find_one_and_update` filter itself (no read-then-write race) — proven with a real `asyncio.gather` concurrency test against in-memory state, not a pre-scripted mock sequence.
- New `itam_lifecycle_service.py`: exactly `write_history`/`list_history`, no update/delete anywhere in the module — the append-only guarantee behind ITAM-LIFE-04.
- Every successful check-out writes exactly one `assignment_history` entry recording the asset, action, target (by id reference only — never the target's email/name), actor, and timestamp; a failing history write surfaces as 500 rather than a silent success.
- Full refusal surface: 409 (non-deployable asset), 404 (missing/cross-tenant asset — same response for both, no existence disclosure), 400 (unresolvable user or location target, checked before any write), 403 (missing `manage:assets`).
- Repaired a live Phase-56 defect discovered during Phase-57 planning: `create_manual_asset` was `await`-ing the synchronous `cache_service.invalidate_cache`, raising a `TypeError` that the broad exception handler converted into a false 500 on every real `POST /api/assets` call — the Phase-56 suite stayed green only because its fixture replaces the helper with an `AsyncMock`. Fixed and covered by a test that exercises the real synchronous helper end-to-end.
- Added the three Phase-57 indexes (`assignment_history` on `(tenantId, assetId)` and `(tenantId, ts desc)`; `assets` on `(tenantId, lastAuditedAt)` for 57-03) with an explicit no-expiry-index comment matching the neighboring `evidence_audit_log` precedent.

## Task Commits

Each task was committed atomically (Task 1 followed the plan's `tdd="true"` RED/GREEN cycle):

1. **Task 1: End-to-end "check an asset out to a user"** — `ff47909` (test, RED) + `5077b3b` (feat, GREEN)
2. **Task 2: Location targets, refusal paths, concurrency** — `7f632e6` (test — behavior was already implemented in Task 1's commit; see Deviations)
3. **Task 3: Phase-57 indexes + cache-invalidation repair** — `c02c302` (fix)

**Post-task refactor (CLAUDE.md 500-line compliance):** `2d11bf4` (refactor — splits the combined test file; see Deviations)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `backend/itam_lifecycle_service.py` — append-only `write_history`/`list_history`, no other exported callables
- `backend/itam_lifecycle_endpoints.py` — the lifecycle router; `checkout_asset` handler, `_deployable_guard`, `_resolve_target`, `_now_iso`, action/interval constants for 57-02/57-03
- `backend/itam_models.py` — added `CheckoutRequest` (`targetType`, `targetId`, `note`, `expectedReturnDate`, `extra="forbid"`)
- `backend/router_registry.py` — registers `itam_lifecycle_endpoints` immediately after `itam_asset_endpoints`
- `backend/database.py` — three new indexes (`assignment_history` x2, `assets.lastAuditedAt`)
- `backend/itam_asset_endpoints.py` — removed the erroneous `await` before `invalidate_cache("assets:*")`
- `backend/tests/itam_lifecycle_test_support.py` — shared mock `TenantIsolatedCollection`/`Database` + fixtures (new, not `test_*`-named)
- `backend/tests/test_itam_lifecycle.py` — Task 1's 6 checkout-happy-path tests
- `backend/tests/test_itam_lifecycle_expansion.py` — Task 2's 10 tests + Task 3's 2 tests (19 total across both files)
- `backend/tests/test_itam_foundation.py` — `invalidate_cache` mock changed `AsyncMock()` → `MagicMock()` to match the now-synchronous real call and stop an unawaited-coroutine warning

## Decisions Made

See `key-decisions` in frontmatter (PD-01 through PD-04 resolved per plan, plus two execution-time decisions: collapsing Task 1/2's implementation, and splitting the test file for the 500-line limit).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, pre-existing] Repaired Phase-56's `await invalidate_cache` TypeError**
- **Found during:** Task 3 (as directed by the plan itself — this was pre-identified, not newly discovered)
- **Issue:** `create_manual_asset` awaited a synchronous `cache_service.invalidate_cache`, raising `TypeError` converted to a false 500 for every real caller
- **Fix:** Removed the `await`; the Phase-56 test double (`AsyncMock`) had masked the defect
- **Files modified:** `backend/itam_asset_endpoints.py`
- **Verification:** `test_manual_asset_creation_survives_real_cache_invalidation` (exercises the real synchronous helper)
- **Committed in:** `c02c302`

**2. [Rule 1 - Bug, caused by Task 3's own fix] `test_itam_foundation.py`'s `invalidate_cache` mock left an unawaited-coroutine warning**
- **Found during:** Task 3, running the full lifecycle+foundation suite after removing the `await`
- **Issue:** `test_itam_foundation.py`'s fixture still patched `invalidate_cache` with an `AsyncMock`; once the real call site stopped awaiting it, calling that `AsyncMock` synchronously left a `RuntimeWarning: coroutine ... was never awaited` on 3 tests
- **Fix:** Changed the fixture's mock to a plain `MagicMock`, matching the real (and now-correct) synchronous signature
- **Files modified:** `backend/tests/test_itam_foundation.py`
- **Verification:** Re-ran `pytest tests/test_itam_lifecycle.py tests/test_itam_lifecycle_expansion.py tests/test_itam_foundation.py -q` — 32 passed, 0 warnings
- **Committed in:** `c02c302`

**3. [Scope efficiency, not a Rule 1-4 fix] Task 1's implementation already included Task 2's scope**
- **Found during:** Writing Task 1's endpoint — the location branch, the 404/409 disambiguation, and the deployable guard were all straightforward to author together rather than splitting the handler across two edits
- **Effect:** Task 2's commit (`7f632e6`) is test-only — it adds the ten tests proving behavior that Task 1's commit (`5077b3b`) already implemented, rather than driving new implementation changes
- **Verification:** All 10 of Task 2's named tests pass against the unmodified Task-1 code

**4. [CLAUDE.md compliance, discovered post-Task-3] Combined test file exceeded the 500-line limit**
- **Found during:** Final plan-level verification pass (`wc -l` across every file this plan touches)
- **Issue:** `test_itam_lifecycle.py` had grown to 609 lines across Tasks 1-3, violating CLAUDE.md's hard 500-line cap and this plan's own `<verification>` block ("wc -l under 500 for every backend file this plan writes or modifies")
- **Fix:** Split into `itam_lifecycle_test_support.py` (shared fixtures, 153 lines), `test_itam_lifecycle.py` (Task 1, 164 lines), `test_itam_lifecycle_expansion.py` (Tasks 2+3, 347 lines) — same 19 tests, same assertions, no test logic changed
- **Files modified:** `backend/tests/test_itam_lifecycle.py`, new `backend/tests/test_itam_lifecycle_expansion.py`, new `backend/tests/itam_lifecycle_test_support.py`
- **Verification:** `pytest tests/test_itam_lifecycle.py tests/test_itam_lifecycle_expansion.py tests/test_itam_foundation.py -q` — 32 passed
- **Committed in:** `2d11bf4`
- **Note:** This makes Task 2's and Task 3's literal `<verify>` command paths (which named `test_itam_lifecycle.py` specifically) stale — the equivalent commands using the new paths are recorded in the coverage table above and were re-run to confirm.

---

**Total deviations:** 4 (2 auto-fixed bugs [Rule 1], 1 scope-efficiency note, 1 CLAUDE.md-driven file split)
**Impact on plan:** No scope creep beyond what the plan itself specified (Task 3's cache-invalidation repair was pre-authorized in the plan text). The file split was mandatory under CLAUDE.md and left test coverage and behavior unchanged.

## Issues Encountered

None beyond the deviations documented above.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data paths were introduced — every code path added in this plan reads/writes real (mocked-in-tests) collections.

## User Setup Required

None - no external service configuration required. `assignment_history` indexes are created automatically by `connect_to_mongo()` on next backend startup against a real MongoDB instance; no manual migration step.

## Next Phase Readiness

- **57-02 (check-in + history read route)** can build directly on this plan's `assignment_history` shape, `_deployable_guard`/`_resolve_target`/`_now_iso` helpers, and the `ACTION_CHECKIN`/`list_history` scaffolding already present in `itam_lifecycle_endpoints.py`/`itam_lifecycle_service.py`.
- **57-03 (physical audit)** can build on `ACTION_AUDIT`/`AUDIT_INTERVAL_DAYS` (already declared) and the `assets.lastAuditedAt` index added in this plan's Task 3.
- **Phase 61 (frontend ITAM console)** has a stable `assignedToType`/`assignedToId`/`assignment_history` document shape to render against (PD-01/PD-04).
- No blockers. Full backend suite (excluding the pre-existing `test_graphql.py` strawberry/pydantic environment incompatibility, unrelated to this plan) was re-run after every task: 1600 passed / 35 skipped / 3 failed, all 3 failures pre-existing and confirmed unrelated (`test_agentic_ai` tool_choice, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type) per this project's memory index baseline.

---
*Phase: 57-lifecycle-check-in-out*
*Completed: 2026-08-04*

## Self-Check: PASSED

All 11 files created/modified by this plan (including this SUMMARY.md) confirmed present on disk; all 5 commits (`ff47909`, `5077b3b`, `7f632e6`, `c02c302`, `2d11bf4`) confirmed present in `git log --all`.
