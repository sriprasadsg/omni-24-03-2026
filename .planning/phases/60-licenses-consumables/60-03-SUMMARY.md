---
phase: 60-licenses-consumables
plan: 03
subsystem: api
tags: [fastapi, pydantic, motor, itam, components]

# Dependency graph
requires:
  - phase: 56-catalog-foundation
    provides: itam_models.py CatalogEntityCreate/Update base classes, TenantIsolatedDatabase auto tenant-scoping
  - phase: 57-lifecycle-check-in-out
    provides: "itam_lifecycle_endpoints.py's GET /api/assets/{asset_id}/history — the asset-scoped sub-resource route shape this plan's new /components route mirrors"
provides:
  - POST/GET /api/itam/components(/{id}) — component catalog CRUD (create/list only — no PATCH/DELETE route exposed, see Known Gaps)
  - POST /api/itam/components/{id}/attach/{asset_id}, POST /api/itam/components/{id}/detach/{asset_id} — nullable parentAssetId attach/detach, record persists on detach (D-05)
  - GET /api/assets/{asset_id}/components — hydrated component listing scoped to a parent asset, added this session
affects: [62-frontend-itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nullable parentAssetId (not a status enum) for attached/detached state, mirroring Phase 57's assignedToType/assignedToId presence-as-state convention (60-RESEARCH.md Pattern 3 rationale)"
    - "Asset-scoped sub-resource route (GET /api/assets/{asset_id}/components) cloned from itam_lifecycle_endpoints.py's /history route shape, added as a second router (asset_components_router) in the same endpoints file rather than a new file"

key-files:
  created:
    - backend/itam_component_service.py
    - backend/itam_component_endpoints.py
    - backend/tests/test_itam_component.py
  modified:
    - backend/itam_models.py
    - backend/router_registry.py

key-decisions:
  - "New GET /api/assets/{asset_id}/components implemented as ComponentService.list_components_for_asset(), not a direct get_database() call in the endpoints file — see Deviations for why the direct-call version failed under this project's test harness"
  - "return_document=ReturnDocument.AFTER added to update_component/attach_component/detach_component's find_one_and_update calls this session — see Deviations, this was a real correctness bug, not a style choice"

requirements-completed: [ITAM-LIC-03]

coverage:
  - id: D1
    description: "Admin can attach a component (RAM/HDD/GPU-style item) to a parent asset and see it listed on that asset's record (ROADMAP Phase 60 success criterion 3)"
    requirement: "ITAM-LIC-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_component.py::TestComponentManagement"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_component.py::TestAssetComponentsSubResource"
        status: pass
    human_judgment: false
    rationale: "Before this session, the only 'listing' mechanism was a bare array of component-id strings riding along on the generic asset GET response (an accidental side effect of $addToSet, not a deliberate feature) — no name/type, and no dedicated query capability for Phase 61's console to use. GET /api/assets/{asset_id}/components (this session) is the real, hydrated listing the success criterion describes."

# Metrics
duration: unknown — implemented across multiple non-conventional prior commits, no SUMMARY existed; this session closed the gaps found during phase verification
completed: 2026-08-09
status: complete
---

# Phase 60 Plan 03: Component Attachment Summary

**Component catalog with nullable-parentAssetId attach/detach (record persists on detach, per D-05) and a hydrated asset-scoped listing route — closing the literal "see it listed on that asset's record" success criterion that a bare id-array response didn't satisfy. ITAM-LIC-03 complete.**

## Performance

- **Tasks:** as specified in 60-03-PLAN.md's 4-item sketch (model, attach/detach endpoints, asset-detail integration, tests) — delivered, but not through a single planned session; see Task Commits. The "Update AssetDetail schema to list attached components" item was never actually done until this session (see Deviations).
- **Files:** 3 created, 2 modified (itam_models.py, router_registry.py shared with 60-01/60-02).

## Accomplishments
- `POST/GET /api/itam/components(/{id})` — component catalog CRUD (create + list; see Known Gaps for the missing single-GET/PATCH/DELETE routes).
- `POST /api/itam/components/{id}/attach/{asset_id}` / `.../detach/{asset_id}` — sets/clears `parentAssetId`, writes `$addToSet`/`$pull` onto the parent asset's own `components` array; detaching clears the reference without deleting the component record (D-05).
- `GET /api/assets/{asset_id}/components` (new this session) — the actual hydrated listing ROADMAP success criterion 3 describes: full `Component` objects (name, type, etc.), not bare ids, scoped to one parent asset, 404 if the asset doesn't exist.
- Fixed a real correctness bug this session: `update_component`/`attach_component`/`detach_component` omitted `return_document=ReturnDocument.AFTER` on their `find_one_and_update` calls — Motor/pymongo defaults to `BEFORE`, so on a real database every one of those calls was returning the **pre-update** document to the caller (e.g. attach returning a component with no `parentAssetId` set yet). Mocked tests didn't catch it because `find_one_and_update`'s return value is stubbed directly in every test.
- 9 tests in `test_itam_component.py` (7 pre-existing + 2 new this session for the asset-scoped route).

## Task Commits

This plan's history is not the usual one-commit-per-task shape. Documented in full for traceability:

1. **Models + initial tests** — `9d38667` ("fix(itam-60): component tests pass", 2026-08-09). Added `Component`/`ComponentCreate`/`ComponentUpdate` to `itam_models.py` and `test_itam_component.py`.
2. **Service, endpoints, critical import-path fix** — `95ab0d7` ("fix(itam-60): restore dropped lifecycle/label models, fix backend.* import paths, wire component router", 2026-08-09). This is the commit that first shipped `itam_component_service.py`/`itam_component_endpoints.py` and registered the router — bundled with a genuinely critical, unrelated-in-scope-but-shared-in-commit fix: `itam_models.py`, `itam_component_endpoints.py`, and `itam_consumable_endpoints.py` had been importing sibling modules as `backend.X` instead of `X`. Pytest's rootdir setup resolved these either way, masking the bug in CI, but the real launcher runs uvicorn with `cwd=backend/` where `backend` itself isn't on `sys.path` — every ITAM router (plus `asset_endpoints`) would have failed to import in production. This commit also restored `CheckoutRequest`/`CheckinRequest`/`AuditMarkRequest` (Phase 57) and `MAX_LABEL_SHEET_ASSETS`/`LabelSheetRequest` (Phase 58), which the same `itam_models.py` rewrite had silently dropped.
3. **Response-shape fix** — `a025953` (2026-08-09): `response_model_by_alias=False` added to all component routes (were leaking `_id` instead of `id`).
4. **This session's gap-closure** (verification pass, 2026-08-09):
   - `7b3172e` — fixed the missing `return_document=ReturnDocument.AFTER` on 3 `find_one_and_update` calls.
   - `de3ee37` — added `GET /api/assets/{asset_id}/components` (`ComponentService.list_components_for_asset`, `asset_components_router`, 2 new tests).
   - `e1c15ff` — corrected a test fixture using the wrong field name (`componentType` instead of the model's actual `type`).

## Files Created/Modified
- `backend/itam_component_service.py` — `ComponentService` class; added `list_components_for_asset` this session.
- `backend/itam_component_endpoints.py` — CRUD + attach/detach routes; added `asset_components_router` (`GET /api/assets/{asset_id}/components`) this session.
- `backend/router_registry.py` — added a second `_load()` call for `asset_components_router`.
- `backend/tests/test_itam_component.py` — 9 tests (7 pre-existing + 2 new this session).

## Decisions Made
- The new asset-scoped route delegates to `ComponentService.list_components_for_asset()` rather than calling `get_database()` directly in `itam_component_endpoints.py`. A first attempt calling `get_database()` inline in the endpoint failed the new tests with `RuntimeError: Database not connected` — because the test file imports the router via `from backend.itam_component_endpoints import router, asset_components_router` (a `backend.`-prefixed import) while the test's `monkeypatch.setattr` patches the bare `itam_component_endpoints` module. Since `backend/router_registry.py`'s real launcher and this test file's import both coexist in the same process, `backend.itam_component_endpoints` and the bare `itam_component_endpoints` are two distinct `sys.modules` entries with two distinct `__globals__` dicts — the exact class of bug `95ab0d7` fixed elsewhere in this phase, encountered fresh while adding new code. Routing the DB call through `ComponentService` (which the test harness already correctly patches via the bare `itam_component_service` module) sidesteps it entirely rather than adding a second, differently-patched code path.

## Deviations from Plan

### Auto-fixed Issues (this session)

**1. [Rule 2 - Correctness bug] find_one_and_update missing return_document=ReturnDocument.AFTER**
- **Found during:** Pre-commit review of the already-uncommitted sibling `itam_consumable_service.py` diff, which prompted a comparison against `itam_component_service.py`'s equivalent calls.
- **Issue:** `update_component`, `attach_component`, `detach_component` all called `find_one_and_update` without specifying `return_document`, defaulting to Motor/pymongo's `BEFORE` — every one of these calls returns the pre-update document on a real database. `attach_component`'s response, for example, would show `parentAssetId: null` even though the attach succeeded.
- **Fix:** Added `return_document=ReturnDocument.AFTER` to all 3 calls.
- **Verification:** All 9 tests still pass (mocked tests stub the return value directly, so this required no test changes — the fix corrects real-database behavior the mocks couldn't have caught).
- **Committed in:** `7b3172e`

**2. [Missing requirement coverage] "See it listed on that asset's record" (ROADMAP success criterion 3) had no hydrated implementation**
- **Found during:** Phase 60 verification pass, checking success criterion 3's literal wording against actual endpoint responses.
- **Issue:** The only place a component showed up on its parent asset was a bare `components: [component_id, ...]` array — an accidental side effect of `attach_component`'s `$addToSet` onto the asset document, riding along on the generic (non-ITAM-specific) `GET /api/assets/{id}` route, which returns a raw, unfiltered dict with no `response_model`. No name, type, or any other component detail; no dedicated query capability at all.
- **Fix:** Added `GET /api/assets/{asset_id}/components`, cloned from `itam_lifecycle_endpoints.py`'s existing `/history` sub-resource shape per 60-RESEARCH.md's own Pattern 3 recommendation (which had specified exactly this route and was simply never implemented).
- **Verification:** 2 new tests (`test_list_asset_components`, `test_list_asset_components_asset_not_found`).
- **Committed in:** `de3ee37`

**Total deviations:** 2 auto-fixed (1 correctness bug, 1 missing requirement-criterion coverage). No functional scope added beyond what ITAM-LIC-03 and the phase's own success criteria require.

## Known Gaps (not fixed — out of session scope, flagged for Phase 61)

- `itam_component_endpoints.py` exposes no `GET /{component_id}`, `PATCH /{component_id}`, or `DELETE /{component_id}` route, even though `ComponentService` has `get_component`/`update_component`/`delete_component` methods ready to use. Not required by ITAM-LIC-03's text or ROADMAP success criterion 3, but Phase 61's console will likely want at least a single-component GET for a detail view — flagged here rather than added speculatively, since CLAUDE.md's "nothing more than asked" cuts against adding unrequested CRUD surface during a verification pass.

## Issues Encountered

None beyond the shared Phase 60 process issue documented in `60-01-SUMMARY.md` (multiple non-conventional commits, no prior SUMMARY.md, plus the `backend.`-vs-bare dual-import footgun encountered fresh in this session's own new code).

## Next Phase Readiness
- ITAM-LIC-03 complete, with one flagged-not-fixed gap (missing single-component CRUD routes) for Phase 61 to either request or work around. See `60-VERIFICATION.md` for the phase-level goal-backward check across all three requirements.

---
*Phase: 60-licenses-consumables*
*Completed: 2026-08-09*
