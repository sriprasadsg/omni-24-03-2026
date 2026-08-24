---
phase: 60-licenses-consumables
plan: 02
subsystem: api
tags: [fastapi, pydantic, motor, itam, consumables]

# Dependency graph
requires:
  - phase: 56-catalog-foundation
    provides: itam_models.py CatalogEntityCreate/Update base classes, TenantIsolatedDatabase auto tenant-scoping
  - phase: 58-asset-tags-offline-labels
    provides: "no-silent-drop bulk-operation contract precedent (empty/over-cap requests refused outright, never trimmed) — same principle applied to over-quantity checkout"
provides:
  - POST/GET/PUT/DELETE /api/itam/consumables(/{id}) — consumable catalog CRUD
  - POST /api/itam/consumables/{id}/checkout, POST /api/itam/consumables/{id}/checkin — atomic, quantity-aware pool decrement/increment
affects: [62-frontend-itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic guard-in-filter find_one_and_update ({availableQuantity: {$gte: requested}}) for checkout — never a preceding read-then-check — combined with $inc in one call, matching 60-RESEARCH.md Pattern 2 and the checkout_asset precedent it was cloned from"
    - "Whole-request rejection on insufficient quantity — no partial fulfillment, mirrors Phase 58's no-silent-drop bulk contract"

key-files:
  created:
    - backend/itam_consumable_service.py
    - backend/itam_consumable_endpoints.py
    - backend/tests/test_itam_consumable.py
  modified: []

key-decisions:
  - "ConsumableService aligned to the same class-based, get_database()/self._tenant_id(current_user) shape as ComponentService this session, rather than the license surface's module-function shape — the two services were drifting inconsistently before this session's cleanup"
  - "checkin_consumable's quantity is a query parameter, not a request body field — mirrors the license-reclaim endpoint's note: str = Query(None) convention already in this same phase, not a new shape"

requirements-completed: [ITAM-LIC-02]

coverage:
  - id: D1
    description: "Admin can create an accessory/consumable and check it out in a quantity greater than one in a single transaction, with available quantity correctly decremented (ROADMAP Phase 60 success criterion 2)"
    requirement: "ITAM-LIC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_consumable.py::TestConsumableManagement"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_consumable.py::TestConsumableCheckoutQuantity"
        status: pass
    human_judgment: false
    rationale: "Before this session, test_itam_consumable.py had only create+list coverage — the checkout/checkin/quantity-guard logic that is this requirement's actual substance had zero test coverage despite the routes existing and working. TestConsumableCheckoutQuantity (5 tests) closes that gap."

# Metrics
duration: unknown — implemented across multiple non-conventional prior commits, no SUMMARY existed; this session closed the gaps found during phase verification
completed: 2026-08-09
status: complete
---

# Phase 60 Plan 02: Consumables Quantity-Aware Checkout Summary

**Accessory/consumable catalog CRUD plus an atomically-guarded checkout/checkin pair — quantity > 1 supported per transaction, over-request rejected outright, available quantity always correct under the guard-in-filter pattern. ITAM-LIC-02 complete.**

## Performance

- **Tasks:** as specified in 60-02-PLAN.md's 4-item sketch (model, endpoints, decrement/block logic, tests) — delivered, but not through a single planned session; see Task Commits.
- **Files:** 3 (all consumable-specific, no shared-file changes this plan).

## Accomplishments
- `POST/GET/PUT/DELETE /api/itam/consumables(/{id})` — consumable catalog CRUD.
- `POST /api/itam/consumables/{id}/checkout` — atomic `find_one_and_update` with `{"availableQuantity": {"$gte": request.quantity}}` in the filter and `$inc`/`$push` in the same call; a request that can't be fully satisfied is rejected in full (400 "Insufficient quantity available"), never partially fulfilled.
- `POST /api/itam/consumables/{id}/checkin` — symmetric atomic increment; rejects `quantity <= 0` before ever reaching the database.
- Cleaned up this session: a stray `__import__("motor.motor_asyncio", fromlist=["ReturnDocument"])` dynamic-import hack (worked, but was the only place in the ITAM codebase not using a normal `from pymongo import ReturnDocument`) replaced with the standard import; service brought onto the same `get_database()`/`self._tenant_id(current_user)` class shape `ComponentService` already used, closing a drift between the two sibling services.
- 7 tests in `test_itam_consumable.py` (2 pre-existing + 5 new this session covering the actual checkout/checkin/quantity-guard behavior).

## Task Commits

This plan's history is not the usual one-commit-per-task shape. Documented in full for traceability:

1. **Original implementation** — `e858fc3` ("feat(itam-lic): implement license management and fix tests", 2026-08-06). Despite the commit message referencing "license management," this commit is what actually introduced `itam_consumable_service.py`/`itam_consumable_endpoints.py` (confirmed via `git log --follow`) — bundled alongside unrelated `ai_providers.py`/`rag_service.py`/`rbac_service.py` changes, no plan reference, no SUMMARY.md.
2. **Fix pass** — `a025953` (2026-08-09): `response_model_by_alias=False` added (consumable routes were leaking Mongo's `_id` instead of `id` in every response), and three independent bugs in `test_itam_consumable.py`'s mock harness fixed (`MockTenantIsolatedCollection.find()` wasn't proxying to the raw collection, among others).
3. **This session's gap-closure** (verification pass, 2026-08-09):
   - `7b3172e` — replaced the dynamic `__import__` `ReturnDocument` lookup with a normal import; aligned the service to `ComponentService`'s class shape.
   - `f951da3` — added 5 tests directly exercising the checkout-decrement, over-request-rejection, checkout-404, checkin-increment, and checkin-rejects-non-positive paths — none of which had any coverage before this session despite being the actual substance of ITAM-LIC-02.

## Files Created/Modified
- `backend/itam_consumable_service.py` — `ConsumableService` class; `create/get/update/delete_consumable`, `checkout_consumable`, `checkin_consumable`.
- `backend/itam_consumable_endpoints.py` — CRUD + checkout/checkin routes, RBAC via `Depends(get_current_user)` (not `_require_itam_admin` — matches this file's existing, unchanged convention).
- `backend/tests/test_itam_consumable.py` — 7 tests (2 pre-existing + 5 new this session).

## Decisions Made
- See `key-decisions` in frontmatter: service-shape alignment with `ComponentService`, and the query-parameter checkin quantity (unchanged from the original implementation, not revisited this session since it matches an existing in-repo convention).

## Deviations from Plan

### Auto-fixed Issues (this session)

**1. [Test-coverage gap] Checkout/checkin/quantity-guard logic had zero test coverage**
- **Found during:** Phase 60 verification pass, reviewing test coverage against ROADMAP success criterion 2's literal wording ("checked out in a quantity greater than one... available quantity correctly decremented").
- **Issue:** `test_itam_consumable.py` had exactly 2 tests (create, list) — the checkout/checkin endpoints existed, were registered, and worked, but nothing verified the atomic guard, the decrement/increment arithmetic, the whole-request-rejection contract, or the non-positive-checkin-quantity guard.
- **Fix:** Added `TestConsumableCheckoutQuantity` (5 tests) directly asserting the `find_one_and_update` filter/update shape and response values for a successful over-1 checkout, a rejected over-request, a 404 against a nonexistent consumable, a successful checkin, and a rejected zero-quantity checkin.
- **Committed in:** `f951da3`

**2. [Code smell / consistency] Hacky ReturnDocument import**
- **Found during:** Pre-commit review of the already-uncommitted `itam_consumable_service.py` diff.
- **Issue:** `return_document=__import__("motor.motor_asyncio", fromlist=["ReturnDocument"]).ReturnDocument.AFTER` — functionally correct but the only place in the ITAM codebase not using a plain `from pymongo import ReturnDocument`.
- **Fix:** Replaced with the standard import, matching `itam_license_service.py`'s existing convention.
- **Committed in:** `7b3172e`

**Total deviations:** 2 auto-fixed (1 test-coverage gap, 1 code-quality cleanup). No functional scope added beyond what ITAM-LIC-02 and the phase's own success criteria require.

## Issues Encountered

None beyond the shared Phase 60 process issue documented in `60-01-SUMMARY.md` (multiple non-conventional commits, no prior SUMMARY.md).

## Next Phase Readiness
- ITAM-LIC-02 complete. See `60-VERIFICATION.md` for the phase-level goal-backward check across all three requirements.

---
*Phase: 60-licenses-consumables*
*Completed: 2026-08-09*
