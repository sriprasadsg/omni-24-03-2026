---
phase: 70-core-data-audit-customization
plan: 01
subsystem: itam
tags: [fastapi, motor, mongodb, pydantic, react, typescript, vitest, itam]

# Dependency graph
requires:
  - phase: 56-itam-catalog-lifecycle
    provides: itam_catalog_service.validate_fieldsets, itam_catalog_service.validate_custom_field_values, AssetModelCreate/Update.fieldsets, Asset.customFields, CatalogPanel.tsx
provides:
  - "GET /api/itam/catalog/models/{model_id}/fields — flattened field definitions + per-key asset usage counts, tenant-scoped"
  - "flatten_fieldsets() and count_field_usage_keys() pure functions in itam_catalog_service.py"
  - "CustomFieldsManager.tsx — full add/edit/remove editor for a model's custom-field definitions, reachable from CatalogPanel's Models view"
  - "fetchAssetModelFields / updateAssetModelFieldsets API client functions"
  - "ItamCustomFieldDef / ItamFieldsetDef / ItamModelFields types"
affects: [70-02-audit-trail, 70-03-csv-import-export, itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read route declared before the generic {kind}/{entity_id} route so a literal path segment (models/{id}/fields) isn't swallowed by the {kind} path parameter"
    - "Draft-state editor pattern: comma-separated select options kept as raw text in local draft state, only split into string[] at save time, so a trailing comma while typing isn't silently dropped"
    - "Usage-count fan-out capped at 50 keys with a truncation flag, wrapped in a logged try/except that degrades to an empty usageCounts object rather than failing the definitions read"

key-files:
  created:
    - components/itam/CustomFieldsManager.tsx
    - backend/tests/test_itam_custom_fields.py
    - src/__tests__/ITAMCustomFieldsManager.test.tsx
  modified:
    - backend/itam_catalog_service.py
    - backend/itam_catalog_endpoints.py
    - services/apiService.ts
    - types.ts
    - components/itam/CatalogPanel.tsx

key-decisions:
  - "Fieldsets stay embedded on the asset_models document — no custom_field_definitions collection, matching the Phase 56 MVP boundary"
  - "No client-side copy of key-shape/duplicate/type/select-option validation — the server's validate_fieldsets remains the single enforcement point; the manager relies on itamThrow surfacing the server's exact message"
  - "Usage-count warning is advisory only — it names the affected keys and asset counts but never blocks Save"

patterns-established:
  - "Draft/API type split for editors with free-text fields whose real shape is an array (options: string[] edited as optionsText: string)"

requirements-completed: [ITAM-DAT-01]

coverage:
  - id: D1
    description: "ITAM admin can open Catalog → Models → Manage Fields and see a model's custom-field definitions grouped by fieldset"
    requirement: "ITAM-DAT-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_custom_fields.py::TestGetAssetModelFields::test_flattens_fieldsets_in_declaration_order"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMCustomFieldsManager.test.tsx::loads and displays a model's custom fields grouped by fieldset"
        status: pass
    human_judgment: false
  - id: D2
    description: "Admin adds/edits/removes a custom field and the change persists across reload, with the four validate_fieldsets failure modes surfaced verbatim to the UI on rejection"
    requirement: "ITAM-DAT-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_custom_fields.py::TestAuthorAssetModelFieldsets (5 tests)"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMCustomFieldsManager.test.tsx::adding a field then clicking Save calls updateAssetModelFieldsets with the expected fieldset array"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMCustomFieldsManager.test.tsx::a rejected save renders the server message and keeps the draft intact"
        status: pass
    human_judgment: false
  - id: D3
    description: "Admin sees a per-field asset usage count and an advisory warning before removing/retyping a field that assets already carry values for"
    requirement: "ITAM-DAT-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_custom_fields.py::TestUsageCounts (2 tests)"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMCustomFieldsManager.test.tsx::removing an in-use field surfaces a warning naming the key and its asset count"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live-browser confirmation that a select field with two options survives a page reload and that the removal warning appears before saving, in the running app"
    verification: []
    human_judgment: true
    rationale: "Plan Task 3's <human-check> requires driving the actual browser UI (start app, click through Catalog → Models → Manage Fields, reload the page). This project's human_verify_mode is end-of-phase, so this step was not executed in this autonomous run and is deferred to phase-level human verification."

# Metrics
duration: 45min
completed: 2026-08-12
status: complete
---

# Phase 70 Plan 01: Custom Fields Manager Summary

**ITAM admins can now author a model's custom-field definitions from the Catalog UI — add/edit/remove fields with types and select options, server-validated with exact error messages surfaced, plus per-field asset usage counts and an advisory warning before a destructive change — closing ITAM-DAT-01's authoring gap over the pre-existing but UI-less `validate_fieldsets`/`validate_custom_field_values` engine.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-08-12
- **Tasks:** 3 (1 tracer, 2 auto — one TDD)
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments
- New tenant-scoped `GET /api/itam/catalog/models/{model_id}/fields` route returns a model's fieldset definitions flattened for display, declared before the generic `{kind}/{entity_id}` route so the literal `models` path segment isn't swallowed
- New `CustomFieldsManager.tsx` panel, reached via a "Manage Fields" row action on `CatalogPanel.tsx`'s Models view, replaces the panel's table in place — full editor: add/remove fieldsets and fields, inline edit of key/label/type/required/select-options, single Save button
- All writes still flow through the pre-existing `PATCH /api/itam/catalog/models/{id}` route and `itam_catalog_service.validate_fieldsets` — no new backend write path, no client-side copy of validation, so a duplicate key / non-identifier key / unsupported type / empty select-options each 400 with the server's exact message shown in the UI without clearing the draft
- Per-field asset usage counts (`db.assets.count_documents({"modelId": ..., "customFields.<key>": {"$exists": True}})`, capped at 50 keys, degrades to `{}` on a logged exception) surface as "in use by N assets" next to each field, and as a named, non-blocking warning above Save when an in-use key is being removed or retyped

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end "view a model's custom fields"** - `047d6ae` (feat)
2. **Task 2: Author custom fields — add, edit, remove with server-validated errors surfaced** - `a11565f` (feat, tdd="true")
3. **Task 3: Usage counts — show how many assets already carry a field before removal/retyping** - `852fabb` (feat)

**Plan metadata:** pending (this SUMMARY's own commit, scoped per orchestrator instruction to SUMMARY.md + REQUIREMENTS.md only)

_Note: Task 2 is `tdd="true"`. The backend assertions (`TestAuthorAssetModelFieldsets`) exercise the pre-existing Phase 56 PATCH route and pass immediately — no backend RED phase, since no new backend production code was needed for those five behaviors. The frontend tests and the `CustomFieldsManager` editor / `updateAssetModelFieldsets` client function were authored together in the same working-tree pass before the first test run, so there is no separate committed RED (failing) state for the frontend half either — see "TDD Gate Compliance" below._

## Files Created/Modified
- `backend/itam_catalog_service.py` - added `flatten_fieldsets()` and `count_field_usage_keys()`, both pure/DB-I/O-free
- `backend/itam_catalog_endpoints.py` - added `GET /models/{model_id}/fields` (declared before the generic `{kind}/{entity_id}` GET), populates `usageCounts`/`usageCountsTruncated` with a capped, try/except-guarded count fan-out
- `services/apiService.ts` - added `fetchAssetModelFields` and `updateAssetModelFieldsets`
- `types.ts` - added `ItamCustomFieldDef`, `ItamFieldsetDef`, `ItamModelFields`
- `components/itam/CustomFieldsManager.tsx` (new) - the full fields editor
- `components/itam/CatalogPanel.tsx` - added `fieldsTarget` state and a "Manage Fields" row action, gated on `kind === 'models'`
- `backend/tests/test_itam_custom_fields.py` (new) - 9 tests across 3 classes (read route, authoring behaviors, usage counts)
- `src/__tests__/ITAMCustomFieldsManager.test.tsx` (new) - 5 tests (load/display, empty state, add-field-then-save, rejected-save, removal warning)

## Decisions Made
- Fieldsets remain embedded on `asset_models` — no `custom_field_definitions` collection, preserving the Phase 56 MVP boundary noted in `itam_catalog_service.py`'s module docstring
- Validation stays server-only: the manager never re-implements key-shape/duplicate/type/select-option checks; `updateAssetModelFieldsets` relies on `itamThrow` passing the server's plain-string `detail` through unchanged
- Select-field options are edited as raw comma-separated text in local draft state and only split into `string[]` at save time, avoiding mid-typing loss of a trailing comma
- Usage-count warning is advisory only (never blocks Save) per the plan's explicit instruction

## Deviations from Plan

None - plan executed exactly as written. One judgment call is worth recording explicitly:

**TDD Gate Compliance:** Task 2 is marked `tdd="true"` with a `<behavior>` block. Per `<tdd_execution>`, this normally implies a RED (failing test) commit followed by a GREEN (passing implementation) commit. In practice: (a) the five backend behaviors are exercised through the Phase 56 PATCH route, which already implements `validate_fieldsets` — so the backend tests in `TestAuthorAssetModelFieldsets` pass on first run with no new backend production code, and (b) the frontend editor (`CustomFieldsManager.tsx` extension, `updateAssetModelFieldsets`) and its tests were both authored in the same pass before any test run, so no standalone failing-test commit exists in git history for the frontend half either. The final state is fully verified (all 9 backend + 5 frontend tests green, confirmed via `pytest`/`vitest` runs shown in this session), but the strict RED→GREEN commit split was not captured. No functional gap results from this — flagging per the TDD gate-compliance instruction.

## Issues Encountered
- The first-draft `usageCounts` backend test used the shared `_wire_crud_store` helper for `mock_db.assets`, but that helper's exact-equality filter matcher can't express the Mongo dot-path + `$exists` query the fields route issues (`{"customFields.<key>": {"$exists": True}}`). Replaced with a purpose-built `_count_by_custom_field` stub for that one test rather than generalizing the shared helper (scoped to the test file only, no shared-fixture change).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `GET /models/{model_id}/fields` and `flatten_fieldsets` are the read primitives plan 65-03 (CSV column mapping) is designed to consume, per this plan's objective section
- One item remains human-only per `human_verify_mode: end-of-phase`: live-browser confirmation that a saved `select` field with two options survives a page reload, and that the removal-warning UI appears correctly in the running app (Task 3's `<human-check>`) — not executed in this autonomous run
- No blockers for 65-02 (Audit Trail) or 65-03 (CSV Import/Export)

---
*Phase: 65-core-data-audit-customization*
*Completed: 2026-08-12*

## Self-Check: PASSED

All created/modified files verified present on disk; all three task commit hashes (`047d6ae`, `a11565f`, `852fabb`) verified present in git history.
