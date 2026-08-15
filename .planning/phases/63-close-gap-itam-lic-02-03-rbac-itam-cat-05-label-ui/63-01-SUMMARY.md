---
phase: 63-close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui
plan: 01
subsystem: api
tags: [rbac, fastapi, authorization, itam, gap-closure]

# Dependency graph
requires:
  - phase: 60-licenses-and-consumables
    provides: itam_consumable_endpoints.py, itam_component_endpoints.py (authenticated but unauthorized routes)
  - phase: 57-lifecycle-and-check-in-out
    provides: itam_asset_endpoints._require_itam_admin (the shared RBAC gate reused here)
provides:
  - Consumables router (7 routes) now requires manage:assets via _require_itam_admin
  - Components router (5 routes, both router + asset_components_router objects) now requires manage:assets via _require_itam_admin
  - Corrected test module-identity bug in test_itam_consumable.py's consumable_app fixture
affects: [63-02, future ITAM plans touching itam_catalog_endpoints.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RBAC-by-import: route handlers depend on the single itam_asset_endpoints._require_itam_admin, never redefine it locally"

key-files:
  created: []
  modified:
    - backend/itam_consumable_endpoints.py
    - backend/itam_component_endpoints.py
    - backend/tests/test_itam_consumable.py
    - backend/tests/test_itam_component.py

key-decisions:
  - "Fixed two plan-specified test payloads ({\"name\":...,\"quantity\":10} and {\"name\":...,\"quantity\":4}) to match the real ConsumableCreate/ComponentCreate Pydantic schemas (extra=\"forbid\"), which reject an unrecognized `quantity` field with 422 before the RBAC gate is ever reached — the corrected payloads (initialQuantity/unitType, and name/type respectively) let the tests actually exercise and prove the 403 path."
  - "Left itam_catalog_endpoints.py's pre-existing local _require_itam_admin redefinition untouched — it's outside this plan's files_modified scope, functionally still 403s non-admins, and is logged as a deferred follow-up rather than silently expanding scope."

requirements-completed: [ITAM-LIC-02, ITAM-LIC-03, ITAM-UI-01]

coverage:
  - id: D1
    description: "Non-admin authenticated user gets HTTP 403 from every route on itam_consumable_endpoints.py"
    requirement: "ITAM-LIC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_consumable.py::TestConsumableRbac::test_rbac_denied_create_returns_403"
        status: pass
    human_judgment: false
  - id: D2
    description: "Non-admin authenticated user gets HTTP 403 from every route on itam_component_endpoints.py, on both the router and asset_components_router objects"
    requirement: "ITAM-LIC-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_component.py::TestComponentRbac::test_rbac_denied_create_returns_403"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_component.py::TestComponentRbac::test_rbac_denied_list_asset_components_returns_403"
        status: pass
    human_judgment: false
  - id: D3
    description: "Admin behavior unchanged — all 16 pre-existing consumable/component tests pass unmodified"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_consumable.py + backend/tests/test_itam_component.py (19 passed total: 16 pre-existing + 3 new)"
        status: pass
    human_judgment: false
  - id: D4
    description: "All 8 backend/itam_*_endpoints.py router files reference the shared _require_itam_admin gate; consumable/component import rather than redefine it"
    requirement: "ITAM-UI-01"
    verification:
      - kind: other
        ref: "grep invariant: `for f in itam_*_endpoints.py; do grep -q '_require_itam_admin' \"$f\" || echo UNGATED:$f; done` — no output"
        status: pass
    human_judgment: true
    rationale: "The single-definition check (grep -rc 'async def _require_itam_admin' itam_*_endpoints.py) additionally matches itam_catalog_endpoints.py — a pre-existing local redefinition predating this phase, outside this plan's file scope. Functionally every router still gates correctly, but the literal 'exactly one definition project-wide' acceptance criterion does not hold; flagging for human awareness rather than auto-passing."

duration: 25min
completed: 2026-08-10
status: complete
---

# Phase 63 Plan 01: ITAM Consumable/Component RBAC Gap Closure Summary

**Closed the BLOCKER RBAC gap on `itam_consumable_endpoints.py` (7 routes) and `itam_component_endpoints.py` (5 routes, 2 router objects) by swapping their bare-authentication dependency for the shared `_require_itam_admin` gate — proven by 3 new tests that fail on the pre-fix code and pass after.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-08-10T20:02:00Z (approx, from init read)
- **Completed:** 2026-08-10T20:27:00Z
- **Tasks:** 3 (2 code tasks + 1 verification-only gate task)
- **Files modified:** 4

## Accomplishments
- Every route on `backend/itam_consumable_endpoints.py` now requires `manage:assets`, closing OWASP API5:2023 Broken Function Level Authorization on 7 endpoints (create/list/get/update/delete/checkout/checkin).
- Every route on `backend/itam_component_endpoints.py` now requires `manage:assets`, across **both** router objects — the main `router` (create/list/attach/detach) and the easily-missed `asset_components_router` sub-resource (`GET /api/assets/{asset_id}/components`), each with its own dedicated 403 test.
- Fixed a real test-harness integrity bug in `test_itam_consumable.py`: the `consumable_app` fixture was patching `verify_permission` on the `backend.itam_asset_endpoints` module object — a different `sys.modules` entry than the unprefixed `itam_asset_endpoints` the route dependency actually resolves against at request time. The stub was a no-op; fixed to match the pattern already used correctly in `test_itam_component.py` and `test_itam_finance.py`.
- Full backend regression suite: 1844 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity`) — identical baseline, zero new failures, zero ITAM failures.

## Task Commits

Each task was committed atomically, following the plan's TDD RED→GREEN structure per task:

1. **Task 1 RED — consumables failing test + fixture fix** - `f9ed291` (test)
2. **Task 1 GREEN — consumables RBAC swap** - `1e5506e` (feat)
3. **Task 2 RED — components failing tests (both router objects)** - `1f02aac` (test)
4. **Task 2 GREEN — components RBAC swap** - `0e08738` (feat)
5. **Task 3 — cross-router invariant + full regression gate** - no commit (verification-only; no file changes made, per the task's own "this is a gate, not an edit" instruction)

## Files Created/Modified
- `backend/itam_consumable_endpoints.py` - all 7 route handlers now use `Depends(_require_itam_admin)` imported from `itam_asset_endpoints`; removed the unused `get_current_user` import
- `backend/itam_component_endpoints.py` - all 5 route handlers (both router objects) now use `Depends(_require_itam_admin)`; normalized inconsistent `Depends(...)` spacing to match sibling routers
- `backend/tests/test_itam_consumable.py` - fixed `consumable_app` fixture's patch target to the unprefixed `itam_asset_endpoints` module; removed dead `itam_asset_verify_permission` import alias; added `TestConsumableRbac` (1 test)
- `backend/tests/test_itam_component.py` - added `TestComponentRbac` (2 tests: one per router object); no fixture change needed (already correct)

## Decisions Made
- Corrected two plan-specified test request payloads that would have failed for the wrong reason (422 schema-validation errors instead of exercising the 403 path), since `ConsumableCreate`/`ComponentCreate` both declare `model_config = ConfigDict(extra="forbid")` and neither accepts a `quantity` field on create. Rewrote to `{"name": "Cat6 Cable", "initialQuantity": 10, "unitType": "unit"}` and `{"name": "8GB DIMM", "type": "RAM"}` respectively, matching the schemas and the existing sibling tests' payload shapes.
- Did not touch `itam_catalog_endpoints.py`'s own pre-existing local `_require_itam_admin` redefinition (predates this phase, since Phase 56) — out of this plan's file scope; logged as a deferred item rather than silently expanding scope into an unrelated file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected invalid test payloads that would fail for the wrong reason**
- **Found during:** Task 1 (RED confirmation) and Task 2 (RED confirmation)
- **Issue:** The plan's literal payloads (`{"name": "Cat6 Cable", "quantity": 10}` and `{"name": "8GB DIMM", "quantity": 4}`) include a `quantity` field neither `ConsumableCreate` nor `ComponentCreate` accepts — both models declare `extra="forbid"`, and `ConsumableCreate` additionally requires `initialQuantity`/`unitType`. Running the tests as literally specified produced 422 (schema validation) instead of 201, which would still make the RED assertion fail but not for the reason the test claims to prove (i.e., it would give false confidence that the RBAC gap was demonstrated when it was really just a bad request).
- **Fix:** Rewrote both payloads to satisfy the real schema and mirror existing passing tests in the same files (`test_create_consumable`, `test_create_component`).
- **Files modified:** `backend/tests/test_itam_consumable.py`, `backend/tests/test_itam_component.py`
- **Verification:** Both tests now correctly RED (201/200 on pre-fix router) and GREEN (403 on post-fix router) for the intended reason.
- **Committed in:** `f9ed291`, `1f02aac` (part of each task's RED commit)

---

**Total deviations:** 1 auto-fixed (test-payload correctness bug), plus 1 out-of-scope discovery logged (not fixed).
**Impact on plan:** The payload fix was necessary for the tests to actually prove what they claim; no scope creep. The `itam_catalog_endpoints.py` discovery is documented in `deferred-items.md` and the `.planning/WINDOWS.md` ledger, not fixed in this plan.

## Issues Encountered
- Task 3's literal acceptance criterion for "exactly one `_require_itam_admin` definition project-wide" does not hold — `itam_catalog_endpoints.py` has had its own local redefinition since Phase 56, predating this phase and outside this plan's `files_modified` scope. See `deferred-items.md` and coverage item D4 above. This does not represent a live authorization gap (the local copy calls the identical `verify_permission(current_user, "manage:assets")` check and still 403s non-admins) — it is a single-source-of-truth / drift-risk finding (T-63-06 in this plan's own threat register), tracked for a future small follow-up plan.

## Next Phase Readiness
- ITAM-LIC-02, ITAM-LIC-03, and ITAM-UI-01 are now delivered: all 8 ITAM router files gate on `manage:assets` in some form (7 of 8 via the shared import, 1 via a functionally-identical local copy).
- Plan 63-02 (label UI gap) is independent of this plan's files and can proceed without waiting on the `itam_catalog_endpoints.py` follow-up.
- Recommended: a small future plan to replace `itam_catalog_endpoints.py`'s local `_require_itam_admin` with the same import pattern used here, closing the single-source-of-truth gap fully.

---
*Phase: 63-close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui*
*Completed: 2026-08-10*

## Self-Check: PASSED

All modified/created files confirmed present on disk (`backend/itam_consumable_endpoints.py`, `backend/itam_component_endpoints.py`, `backend/tests/test_itam_consumable.py`, `backend/tests/test_itam_component.py`, this SUMMARY, `deferred-items.md`). All 5 commit hashes (`f9ed291`, `1e5506e`, `1f02aac`, `0e08738`, `8dfa07b`) confirmed present in `git log --oneline --all`.
