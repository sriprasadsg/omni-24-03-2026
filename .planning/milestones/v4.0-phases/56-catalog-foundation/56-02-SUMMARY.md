---
phase: 56-catalog-foundation
plan: 02
subsystem: itam
tags:
  - ITAM-CAT-01
  - ITAM-CAT-03
  - ITAM-CAT-04
  - fastapi
  - pydantic-v2

# Dependency graph
requires:
  - phase: 56-catalog-foundation (plan 01)
    provides: itam_models, itam_catalog_endpoints, kind-parameterized CATALOG_KINDS/CATALOG_REFERENCE_FIELDS router, manage:assets RBAC gate
provides:
  - CATALOG_KINDS/CATALOG_REFERENCE_FIELDS entries for categories/locations/suppliers/models
  - CATALOG_MODELS per-kind request-body registry (SupplierCreate/Update, AssetModelCreate/Update)
  - itam_catalog_service.validate_fieldsets / collect_field_defs / validate_custom_field_values
affects:
  - phase_56_04_customfields_on_assets
  - phase_59_procurement_finance

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-kind request-body registry (CATALOG_MODELS: kind -> (create, update) model pair) so one generic route validates five different Pydantic body shapes without five route functions"
    - "Fieldset definitions embedded on the owning Model document, validated by a router-independent service module so a later phase's asset write path can import validation without importing a router"

key-files:
  created:
    - backend/itam_catalog_service.py
    - backend/tests/test_itam_catalog.py
  modified:
    - backend/itam_catalog_endpoints.py
    - backend/itam_models.py

key-decisions:
  - "SupplierCreate/Update and AssetModelCreate/Update are registered per-kind in CATALOG_MODELS rather than adding new route functions — the generic POST/PATCH handlers resolve the model from the registry and validate the raw body against it explicitly (Dict[str, Any] at the signature, 422 with pydantic's own error detail on failure)."
  - "Fieldsets live embedded on the asset Model document; itam_catalog_service.py is the single validation surface (no I/O) both the router and 56-04's asset write path import — no custom_field_definitions collection introduced."

requirements-completed: [ITAM-CAT-01, ITAM-CAT-03, ITAM-CAT-04]

coverage:
  - id: D1
    description: "Category and Location catalog kinds registered, full CRUD + tenant scoping + in-use delete guard via the existing generic router"
    requirement: ITAM-CAT-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_create_and_read_category"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_create_and_read_location"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_patch_category_updates_only_supplied_fields"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_delete_in_use_category_returns_409"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_delete_unused_location_succeeds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_every_registered_kind_is_tenant_scoped"
        status: pass
    human_judgment: false
  - id: D2
    description: "Supplier catalog kind with dedicated contact fields (contactName/contactEmail/contactPhone/website/address), EmailStr-validated, extra fields rejected with 422"
    requirement: ITAM-CAT-03
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_create_supplier_with_contact_fields"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestCategoryLocationSupplier::test_supplier_rejects_unknown_field"
        status: pass
    human_judgment: false
  - id: D3
    description: "Asset Model kind with validated Manufacturer/Category references (400 naming the offending field on an unknown id) and model-level fieldset definitions (duplicate keys, non-identifier keys, and option-less select fields all refused with 400)"
    requirement: ITAM-CAT-04
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_create_asset_model_with_valid_references"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_asset_model_rejects_unknown_manufacturer"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_asset_model_rejects_unknown_category"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_asset_model_accepts_fieldsets"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_duplicate_field_key_across_fieldsets_rejected"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_select_field_without_options_rejected"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_field_key_must_be_identifier_shaped"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_validate_custom_field_values_flags_unknown_and_missing"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_catalog.py::TestAssetModel::test_editing_model_fieldsets_does_not_touch_existing_assets"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-08-04
status: complete
---

# Phase 56 Plan 02: Catalog Expansion — Category/Location/Supplier + Asset Models Summary

**All five ITAM catalog kinds live behind one generic router via a new CATALOG_MODELS per-kind body registry, plus a router-independent `itam_catalog_service.py` fieldset validator (duplicate keys, identifier-shaped keys, option-less selects) that 56-04's asset write path will import directly.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 2 completed
- **Files modified:** 4 (2 new: `itam_catalog_service.py`, `tests/test_itam_catalog.py`; 2 modified: `itam_catalog_endpoints.py`, `itam_models.py`)

## Accomplishments
- Registered `categories` (→ `asset_categories`), `locations`, and `suppliers` in `CATALOG_KINDS`/`CATALOG_REFERENCE_FIELDS`, extending the 56-01 generic CRUD router to all four kinds with no new route functions.
- Added `SupplierCreate`/`SupplierUpdate` (contactName/contactEmail [`EmailStr`]/contactPhone/website/address, `extra="forbid"`) as the first per-kind bespoke request contract, introducing `CATALOG_MODELS: Dict[str, Tuple[type, type]]` so the create/patch handlers validate the raw JSON body against a resolved model instead of one hardcoded Pydantic type.
- Added `backend/itam_catalog_service.py` (no DB I/O, no import of any endpoints module) with `validate_fieldsets`, `collect_field_defs`, and `validate_custom_field_values` — the fieldset contract 56-04's asset write path will consume directly.
- Registered `models` → `asset_models` with `AssetModelCreate`/`AssetModelUpdate` (`modelNumber`, `manufacturerId`, `categoryId`, `fieldsets: List[FieldsetDef]`); create/patch now run a `models`-only post-validation hook confirming `manufacturerId`/`categoryId` resolve against their collections (400 naming the field) and that `fieldsets` pass `validate_fieldsets` (400 on violation).
- 21 new tests in `backend/tests/test_itam_catalog.py` covering both tasks; `backend/tests/test_itam_foundation.py` (13 tests) confirmed unaffected.

## Task Commits

Each task was committed atomically:

1. **Task 1: Register Category, Location, and Supplier as catalog kinds** - `17954de` (feat)
2. **Task 2: Asset Models with validated catalog references and model-level fieldsets** - `941418f` (feat)

_Note: both commits are TDD-style (tests + implementation together per task) rather than separate test→feat commits, matching this plan's `tdd="true"` task attribute where the test suite was authored and run to green before each task's commit — not split into a further RED/GREEN commit pair since 56-01 established the same per-task granularity._

## Files Created/Modified
- `backend/itam_catalog_endpoints.py` - Adds `categories`/`locations`/`suppliers`/`models` to the kind registries; adds `CATALOG_MODELS` and `_resolve_models`; POST/PATCH now validate the raw body against the resolved per-kind model; adds `_validate_asset_model_references` post-validation hook for the `models` kind
- `backend/itam_models.py` - Adds `SupplierCreate`/`SupplierUpdate`, `CustomFieldDef`, `FieldsetDef`, `AssetModelCreate`/`AssetModelUpdate`
- `backend/itam_catalog_service.py` (new) - `validate_fieldsets`, `collect_field_defs`, `validate_custom_field_values`; module docstring records the deliberate MVP boundary (fieldsets embedded on the model, no `custom_field_definitions` collection)
- `backend/tests/test_itam_catalog.py` (new) - 21 tests: `TestCategoryLocationSupplier` (Task 1, 8 tests including a parametrized tenant-scoping check across all 5 kinds) and `TestAssetModel` (Task 2, 9 tests + 1 non-HTTP direct-function test for `validate_custom_field_values`)

## Decisions Made
- Kept `CATALOG_MODELS` keyed by URL `kind` (not collection name), consistent with `CATALOG_REFERENCE_FIELDS`'s existing keyspace — see the Rule 1 fix below, which was caused by exactly this kind-vs-collection-name key mismatch already present in the 56-01 code.
- `_validate_asset_model_references` is a single helper called from both create and patch for the `models` kind, checking references then fieldsets in one pass, so a caller gets one 400 for whichever violation occurs first rather than requiring two round trips.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `CATALOG_REFERENCE_FIELDS` lookup keyed by `collection_name` instead of `kind` in the delete guard**
- **Found during:** Task 1 (before writing new tests, while reading the existing `delete_catalog_entity` handler per the `<read_first>` instruction)
- **Issue:** The 56-01 `delete_catalog_entity` handler resolved the in-use reference field via `CATALOG_REFERENCE_FIELDS.get(collection_name)`, but `CATALOG_REFERENCE_FIELDS` is keyed by the URL `kind` segment. For `manufacturers` the two strings are identical, so the bug was invisible in 56-01's tests — but `CATALOG_KINDS["categories"] == "asset_categories"` (kind != collection name), so the same lookup would have silently returned `None` and skipped the in-use delete guard entirely for every kind this plan adds, defeating this plan's own `test_delete_in_use_category_returns_409`.
- **Fix:** Changed the lookup to `CATALOG_REFERENCE_FIELDS.get(kind)`, with an inline comment explaining why the manufacturers-only case masked it in 56-01.
- **Files modified:** `backend/itam_catalog_endpoints.py`
- **Verification:** `test_delete_in_use_category_returns_409` (409 + entity still readable afterward) and `test_delete_unused_location_succeeds` (204) both pass; the plan's own acceptance-criteria check (`set(CATALOG_REFERENCE_FIELDS) == set(CATALOG_KINDS)`) also passes.
- **Committed in:** `17954de` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Necessary for the delete-in-use guard — a real must_have (`Deleting a Category, Location, Supplier, or Model that at least one asset references is refused with 409`) would otherwise have silently regressed for every kind but manufacturers. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All five catalog kinds (Manufacturer, Category, Location, Supplier, Model) are live, tenant-scoped, and delete-guarded through one generic router.
- `itam_catalog_service.validate_custom_field_values`/`collect_field_defs` are ready for 56-04 to import when it wires `customFields` value validation into the asset create/patch path.
- No blockers for 56-03/56-04.

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; both task commit hashes (`17954de`, `941418f`) confirmed in `git log`.

---
*Phase: 56-catalog-foundation*
*Completed: 2026-08-04*
