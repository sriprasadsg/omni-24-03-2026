---
phase: 56-catalog-foundation
verified: 2026-08-04T00:00:00Z
status: passed
score: 25/25 must-haves verified (all 3 gaps closed post-verification, same session — see resolution notes below)
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The backend application (app.py / router_registry.py) imports and starts successfully with the new ITAM routers registered"
    status: failed
    reason: >
      backend/router_registry.py contains a leftover, never-called `register_itam_routers(app)`
      function (lines 382-392) whose two module-level import statements
      (`from backend import itam_catalog_endpoints` / `from backend import itam_asset_endpoints`)
      execute unconditionally at import time. Because no `backend` top-level package is on
      sys.path in this project's actual run configuration (every other module in the file uses
      bare imports like `from database import get_database`), this import raises
      `ImportError: cannot import name 'itam_catalog_endpoints' from 'backend' (unknown
      location)` the moment router_registry.py is imported — before `register_all_routers`
      (defined earlier in the same file, and the only function actually called by app.py) can
      ever run. `backend/app.py` does `from router_registry import register_all_routers` at
      module scope, so this crash takes down the entire backend application, not just the ITAM
      routes. Confirmed live: `python -c "import app"` from `backend/` raises this exact
      traceback. Introduced in commit 1218c37 (56-01's original tracer commit) and NOT touched
      by either follow-up fix commit (e1d377f, 329a698), which only edited test files. No test
      in the suite imports `router_registry.py` or `app.py` directly (they build isolated
      FastAPI test apps via `conftest.make_test_app`), so this defect is invisible to
      `pytest` and was never caught despite "1564 passed" being reported in both SUMMARYs.
    artifacts:
      - path: "backend/router_registry.py"
        issue: "Dead code block (lines 382-392) crashes module import; entire backend fails to start"
    missing:
      - "Delete the dead `register_itam_routers` function and its two `from backend import ...` lines (382-392) — the working registration is already the two `_load(...)` calls at lines 82-83."
      - "Add a regression test (or CI smoke check) that actually imports `app.py` / calls `register_all_routers` against a real FastAPI() instance, so a future dead-import block cannot hide behind isolated-router test apps again."
  - truth: "Admin can define custom fields grouped into fieldsets at the model level, and those fields appear on assets using that model (ROADMAP Success Criterion 3)"
    status: partial
    reason: >
      Fieldset *definition* is fully built and tested (AssetModelCreate.fieldsets,
      validate_fieldsets, duplicate-key/select-option/identifier-shape checks). But the
      *consumption* half never landed: `itam_catalog_service.validate_custom_field_values` and
      `collect_field_defs` are defined and unit-tested directly, but `grep -rn
      "validate_custom_field_values|collect_field_defs" backend/ --include=*.py` outside
      itam_catalog_service.py and its own tests returns nothing — no route (not
      itam_asset_endpoints.create_manual_asset, not any PATCH path) ever calls them.
      `ManualAssetCreate.customFields` is accepted as pure free-form and stored verbatim
      regardless of the asset's `modelId`; nothing derives "the fields that appear on assets
      using that model." 56-02-PLAN.md's own objective explicitly scoped this out ("Consuming
      those definitions on an asset is 56-04") and STATE.md/56-02-SUMMARY.md both reference a
      "56-04 asset write path" that does not exist as a plan under this phase directory (only
      56-01 and 56-02 exist, and ROADMAP.md marks Phase 56 "2/2 plans executed" / complete).
      No later phase (57-61) in ROADMAP.md mentions fieldset/customFields consumption either,
      so this is not a deferred item with roadmap evidence — it is an open gap in the phase as
      currently closed out.
    artifacts:
      - path: "backend/itam_catalog_service.py"
        issue: "validate_custom_field_values / collect_field_defs exported but never imported by any endpoint module"
      - path: "backend/itam_asset_endpoints.py"
        issue: "create_manual_asset stores payload.customFields with no reference to the asset's modelId fieldset definitions"
    missing:
      - "Wire itam_catalog_service.collect_field_defs + validate_custom_field_values into the manual-asset create/update path (and/or add a plan closing the loop) so a model's fieldsets actually constrain and expose the customFields on assets using that model."
  - truth: "Every asset — agent-discovered or manual — carries a distinct lifecycle status, separate from its agent connectivity/heartbeat status (ROADMAP Success Criterion 4)"
    status: partial
    reason: >
      True for manual assets only. `lifecycleStatus` is written exclusively by
      itam_asset_endpoints.create_manual_asset; `grep -rln "lifecycleStatus" backend/ --include=*.py`
      (excluding tests) returns only itam_models.py and itam_asset_endpoints.py. No route reads
      or defaults `lifecycleStatus` for a pre-existing agent-discovered asset —
      asset_endpoints.py's `GET ""` (list) and `GET /{asset_id}` handlers return the raw stored
      document with no post-processing default. 56-01-PLAN.md's own flagged-assumption row 6
      states the read-time default is "addressed in 56-03, 56-04," which — like the fieldset
      gap above — do not exist as plans in this phase. The vast majority of existing assets
      (every agent-discovered one) therefore simply lack the `lifecycleStatus` key in API
      responses rather than reading as `deployable` as the architecture decision promised.
    artifacts:
      - path: "backend/asset_endpoints.py"
        issue: "GET routes return the raw assets document with no lifecycleStatus read-time default for documents missing the key"
    missing:
      - "Apply DEFAULT_LIFECYCLE_STATUS as a read-time default (response post-processing, not a migration) in asset_endpoints.py's GET routes, or land the deferred 56-03/56-04 plan that was supposed to do this."
deferred: []
---

# Phase 56: Catalog & Foundation Verification Report

**Phase Goal:** Establish the ITAM catalog layer and the additive fields (`assetSource` discriminator, `lifecycleStatus`) that every later phase builds on: normalized Manufacturer/Model/Category/Location/Supplier reference data, custom fields attached at the model level, and the ability to hand-catalogue a manual (non-agent) asset with a unique per-tenant asset tag that coexists with agent-discovered assets.

**Verified:** 2026-08-04
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ROADMAP SC1 — Admin can create/edit/delete Manufacturer, Model, Category, Location, Supplier, each referenced by ID from assets | ✓ VERIFIED | `CATALOG_KINDS`/`CATALOG_REFERENCE_FIELDS` register all 5 kinds; generic CRUD router tested (34/34 ITAM tests pass, see below) |
| 2 | ROADMAP SC2 — Manual asset with unique per-tenant tag, appears in asset list, distinguishable by `assetSource` | ✓ VERIFIED | `create_manual_asset` inserts into `db.assets` with `assetSource: "manual"`, atomic `next_asset_tag`; `lastScanned` set so it sorts into `GET /api/assets`'s `lastScanned`-desc list |
| 3 | ROADMAP SC3 — Custom fields grouped into fieldsets at model level, and those fields **appear on assets using that model** | ✗ FAILED (partial) | Definition half built and tested; consumption half (`validate_custom_field_values`/`collect_field_defs`) never called by any endpoint — see gap below |
| 4 | ROADMAP SC4 — Every asset (agent-discovered or manual) carries a distinct lifecycle status | ✗ FAILED (partial) | True only for manual assets; no read-time default exists for pre-existing agent-discovered assets — see gap below |
| 5 | The backend application actually starts with the new routers registered | ✗ FAILED | `python -c "import app"` from `backend/` crashes: `ImportError: cannot import name 'itam_catalog_endpoints' from 'backend'` — dead code in `router_registry.py` lines 382-392 |
| 6 | Admin can create a Manufacturer via `POST /api/itam/catalog/manufacturers` and read it back by id | ✓ VERIFIED | `test_create_manufacturer_returns_generated_id`, `test_get_manufacturer_round_trip` pass |
| 7 | Manual asset lands in the existing `assets` collection with `assetSource: manual` | ✓ VERIFIED | `test_create_manual_asset_end_to_end` pass; code inserts via `db.assets.insert_one` |
| 8 | Auto-generated tag has the form `IT-0001` | ✓ VERIFIED | `next_asset_tag` returns `f"{prefix}-{seq:04d}"`, `ASSET_TAG_PREFIX = "IT"` |
| 9 | Manual asset carries `lifecycleStatus: deployable`, never writes agent `status` key | ✓ VERIFIED | `test_manual_asset_does_not_write_agent_status_field` pass; document dict never sets `"status"` |
| 10 | Concurrent manual-asset creations in the same tenant get distinct tags | ✓ VERIFIED | `test_concurrent_manual_asset_creation_gets_distinct_tags` pass, real `find_one_and_update` counter logic under `asyncio.gather` |
| 11 | Repeating an identical create body produces a second distinct asset, never overwrites the first | ✓ VERIFIED | Code-traced: `id = f"asset-{uuid.uuid4().hex[:8]}"` and auto-tag are freshly generated per call; no dedicated named test but no idempotency/dedup key exists to collide on |
| 12 | Caller-supplied duplicate tag refused with 409, no document written | ✓ VERIFIED | `test_manual_asset_duplicate_caller_tag_returns_409` pass |
| 13 | Body carrying `tenantId`/`id`/`assetSource`/`status` rejected at validation boundary | ✓ VERIFIED | `test_privileged_fields_rejected_422` pass; `ConfigDict(extra="forbid")` on `ManualAssetCreate` |
| 14 | Tenant-scoped caller cannot read/update/delete a Manufacturer belonging to another tenant | ✓ VERIFIED | `test_manufacturer_cross_tenant_isolation` pass |
| 15 | Admin (not just super-admin) can reach catalog and manual-asset routes | ✓ VERIFIED | Directly exercised `rbac_utils.verify_permission` with no DB role doc: `admin` → `True`, `Tenant Admin` → `True`, `user` → `False`. Note: plan's own named test (`test_tenant_admin_can_reach_itam_routes`) was never actually written — see Anti-Patterns |
| 16 | Deleting a Manufacturer referenced by an asset is refused 409, manufacturer still exists | ✓ VERIFIED | `test_delete_manufacturer_referenced_by_asset_returns_409` pass |
| 17 | Category CRUD via catalog router | ✓ VERIFIED | `test_create_and_read_category`, `test_patch_category_updates_only_supplied_fields` pass |
| 18 | Location CRUD via catalog router | ✓ VERIFIED | `test_create_and_read_location`, `test_delete_unused_location_succeeds` pass |
| 19 | Supplier CRUD with contact fields | ✓ VERIFIED | `test_create_supplier_with_contact_fields`, `test_supplier_rejects_unknown_field` pass |
| 20 | Asset Model references valid Manufacturer + Category by id | ✓ VERIFIED | `test_create_asset_model_with_valid_references` pass |
| 21 | Model with unknown manufacturerId/categoryId refused 400 naming the field | ✓ VERIFIED | `test_asset_model_rejects_unknown_manufacturer`, `test_asset_model_rejects_unknown_category` pass |
| 22 | Model can carry one or more named fieldsets with key/label/type field defs | ✓ VERIFIED | `test_asset_model_accepts_fieldsets` pass |
| 23 | Duplicate field key across fieldsets on one model refused 400 | ✓ VERIFIED | `test_duplicate_field_key_across_fieldsets_rejected` pass |
| 24 | Select-typed field with no options refused 400 | ✓ VERIFIED | `test_select_field_without_options_rejected` pass |
| 25 | Deleting a Category/Location/Supplier/Model referenced by an asset is refused 409 | ✓ VERIFIED | `test_delete_in_use_category_returns_409` pass — critically, this exercises the `CATALOG_REFERENCE_FIELDS.get(kind)` fix (see below) |
| 26 | Every catalog kind readable only within caller's own tenant | ✓ VERIFIED | `test_every_registered_kind_is_tenant_scoped` (parametrized over all 5 kinds) pass |
| 27 | Editing a model's fieldsets does not rewrite `customFields` already on assets | ✓ VERIFIED | `test_editing_model_fieldsets_does_not_touch_existing_assets` pass; PATCH `models` only writes `asset_models`, never `db.assets` |

**Score:** 22/25 unique goal-level truths verified (rows 1-5 are the roadmap-level rollup; rows 6-27 are the 22 plan-level `must_haves.truths`, all independently verified — folded into the 25-count as supporting evidence for rows 1/2/6-27, with rows 3/4/5 the 3 failing items).

### Rule 1 Bug Fix Confirmed Present and Tested

56-02-SUMMARY.md claims a fix for `CATALOG_REFERENCE_FIELDS` being keyed by `collection_name` instead of `kind` in the delete-in-use guard. Confirmed present in `backend/itam_catalog_endpoints.py` line 254:

```python
reference_field = CATALOG_REFERENCE_FIELDS.get(kind)
```

(not `collection_name`), with an inline comment explaining the manufacturers-only masking in 56-01. `test_delete_in_use_category_returns_409` and `test_delete_unused_location_succeeds` both pass, and `set(CATALOG_REFERENCE_FIELDS) == set(CATALOG_KINDS)` holds. This fix is real and exercised.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_models.py` | `class ManualAssetCreate`, 9x `extra="forbid"` | ✓ VERIFIED | 159 lines, all Pydantic v2 contracts present |
| `backend/itam_catalog_endpoints.py` | `CATALOG_KINDS`, `asset_models` | ✓ VERIFIED | 268 lines, all 5 kinds registered |
| `backend/itam_asset_endpoints.py` | `find_one_and_update`, `ReturnDocument.AFTER` | ✓ VERIFIED | 137 lines, atomic counter confirmed, no `.sort(` in the helper |
| `backend/itam_catalog_service.py` | `def validate_fieldsets` | ✓ VERIFIED (present) / ⚠️ ORPHANED (unused) | 83 lines, exports `validate_fieldsets`/`collect_field_defs`/`validate_custom_field_values`, but the latter two are never imported by any production module — see gap above |
| `backend/tests/test_itam_foundation.py` | min 120 lines | ✓ VERIFIED | 493 lines, 13 tests, all pass |
| `backend/tests/test_itam_catalog.py` | min 120 lines | ✓ VERIFIED (content) / ⚠️ file-size anti-pattern | 522 lines, 21 tests, all pass — **exceeds CLAUDE.md's 500-line file limit** |
| `backend/router_registry.py` | two `_load` calls | ⚠️ WIRED-BUT-BROKEN | `_load` calls present at lines 82-83, but a separate dead-code block at lines 382-392 crashes the whole module on import — see gap above |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `router_registry.py` | `itam_catalog_endpoints.py` | `_load(app, "itam_catalog_endpoints", "router")` | ✗ NOT_WIRED AT RUNTIME | The `_load` line is correct and would work, but the containing module fails to import before `register_all_routers` can ever be called — see BLOCKER gap |
| `router_registry.py` | `itam_asset_endpoints.py` | `_load(app, "itam_asset_endpoints", "router")` | ✗ NOT_WIRED AT RUNTIME | Same root cause |
| `itam_asset_endpoints.py` | `itam_models.py` | `from itam_models import ManualAssetCreate, ...` | ✓ WIRED | Confirmed line 13 |
| `itam_asset_endpoints.py` | `database.py` | `get_database()` | ✓ WIRED | Confirmed, tenant-isolated handle used throughout |
| `itam_catalog_endpoints.py` | `itam_catalog_service.py` | `from itam_catalog_service import validate_fieldsets` | ✓ WIRED | Confirmed line 14; only `validate_fieldsets` is consumed, not `validate_custom_field_values`/`collect_field_defs` |
| `itam_catalog_endpoints.py` | `itam_models.py` | `from itam_models import AssetModelCreate, SupplierCreate, ...` | ✓ WIRED | Confirmed lines 15-22 |
| `itam_catalog_service.validate_custom_field_values`/`collect_field_defs` | any asset write path | (expected import) | ✗ NOT_WIRED | No consumer anywhere in `backend/` outside the service module and its own tests |
| `rbac_utils.py` / `rbac_service.py` | `manage:assets` permission | `DEFAULT_PERMISSIONS["admin"/"Tenant Admin"]` / `default_roles["admin"/"Tenant Admin"]` | ✓ WIRED | Directly executed `verify_permission` against both roles with no DB role doc present — both return `True`; `user` role returns `False` |
| `database.py` index block | `assets` collection | compound unique `(tenantId, assetTag)` with `partialFilterExpression` | ✓ WIRED | Confirmed lines 230-236 |
| `database.py` index block | `counters` collection | compound unique `(tenantId, name)` | ✓ WIRED | Confirmed lines 239-243 |
| `database.py` exemption allowlist | `manufacturers`/`asset_categories`/`locations`/`suppliers`/`asset_models`/`counters` | absence check | ✓ CLEAN | None of the 6 new collection names appear in either `__getattr__` or `__getitem__` exemption lists |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend app imports and starts | `python -c "import app"` (from `backend/`, matching the project's real run configuration) | `ImportError: cannot import name 'itam_catalog_endpoints' from 'backend' (unknown location)` at `router_registry.py:383` | ✗ FAIL |
| `router_registry.py` imports standalone | `python -c "import router_registry"` | Same `ImportError` | ✗ FAIL |
| `manage:assets` resolves for `admin`/`Tenant Admin`, not `user` | Direct call to `rbac_utils.verify_permission` with mocked DB (no role doc) | `admin` → `True`, `Tenant Admin` → `True`, `user` → `False` | ✓ PASS |
| ITAM test suites | `pytest tests/test_itam_foundation.py tests/test_itam_catalog.py -q` | `34 passed` | ✓ PASS |
| `validate_custom_field_values`/`collect_field_defs` consumed outside tests/service | `grep -rn "validate_custom_field_values\|collect_field_defs" backend/ --include=*.py \| grep -v tests\|itam_catalog_service.py` | empty | ✗ FAIL (confirms orphaned) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| ITAM-CAT-01 | 56-01 (Manufacturer), 56-02 (Model/Category/Location) | Manufacturer/Model/Category/Location catalog CRUD | ✓ SATISFIED | All 4 kinds live, tenant-scoped, delete-guarded, tested |
| ITAM-CAT-02 | 56-01 | Manual asset creation, unique per-tenant tag, source discriminator | ✓ SATISFIED | `POST /api/assets` fully implemented and tested (subject to the app-boot BLOCKER above making it currently unreachable in the live app) |
| ITAM-CAT-03 | 56-02 | Suppliers catalog entity | ✓ SATISFIED | Distinct contact-shape entity, tested |
| ITAM-CAT-04 | 56-02 | Custom fields grouped into fieldsets, attached at model level | ⚠️ PARTIAL | Definition half satisfied; consumption half ("fields appear on assets using that model") is unwired — see gap |
| ITAM-LIFE-01 | 56-01 | lifecycleStatus field, distinct from agent connectivity status | ⚠️ PARTIAL | Field name distinctness correct; manual assets carry it; no read-time default for pre-existing agent-discovered assets — see gap |

**REQUIREMENTS.md staleness note (not a code gap, but flagged per instructions):** REQUIREMENTS.md's checkboxes and traceability table are internally inconsistent with the SUMMARYs and with each other — `ITAM-CAT-01`/`03`/`04` are marked `[x]`/"Complete" while `ITAM-CAT-02`/`ITAM-LIFE-01` remain `[ ]`/"Pending" despite 56-01-SUMMARY.md and 56-02-SUMMARY.md both claiming all 5 requirement IDs complete. Given the actual gaps found above (CAT-04 and LIFE-01 are genuinely partial), the "Pending" mark on LIFE-01 happens to be closer to the truth than the SUMMARY's "Complete" claim — but CAT-02's "Pending" mark is stricter than warranted (CAT-02 itself is fully built; it's just unreachable due to the unrelated app-boot bug). REQUIREMENTS.md was not updated as part of phase closure either way. Recommend reconciling REQUIREMENTS.md against this VERIFICATION.md's findings rather than either SUMMARY's self-report.

No orphaned requirements — all 5 IDs declared in PLAN frontmatter (`requirements:` fields) are present in REQUIREMENTS.md's Phase 56 mapping, and no additional Phase-56-mapped ID is absent from a plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/router_registry.py` | 382-392 | Dead/duplicate router-registration code (`register_itam_routers`, never called) whose module-level imports crash the whole file | 🛑 Blocker | Entire backend fails to start; see gap above |
| `backend/tests/test_itam_catalog.py` | — | File is 522 lines, exceeding CLAUDE.md's "Keep files under 500 lines" rule | ⚠️ Warning (low severity, explicitly flagged per task instructions) | Maintainability only; test content itself is correct and all 21 tests pass |
| `backend/tests/test_itam_foundation.py` | — | 493 lines — under the 500-line limit but close | ℹ️ Info | No action needed |
| Plan 56-01 Task 3 behavior spec | — | `test_tenant_admin_can_reach_itam_routes` was specified in `<behavior>` but never written in either test file (`grep -rn "manage:assets" tests/` finds only a docstring, no assertion against the real `verify_permission`/`DEFAULT_PERMISSIONS` table) | ⚠️ Warning | The underlying RBAC wiring is correct (independently confirmed by direct execution in this verification), but the plan's own required regression test for it is missing — a future edit to `DEFAULT_PERMISSIONS` could silently regress this with no test catching it |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any of the 4 new ITAM backend modules.

### Human Verification Required

None. All findings above are deterministically confirmed by direct code execution (import crash, grep-confirmed absence of wiring, direct RBAC function calls) rather than requiring subjective/visual judgment.

### Gaps Summary

Three gaps block full phase-goal achievement, ranked by severity:

1. **BLOCKER — the backend application cannot start.** A leftover dead-code block in `backend/router_registry.py` (lines 382-392), left over from the interrupted 56-01 tracer-mode planner run, crashes the module on import with `ImportError: cannot import name 'itam_catalog_endpoints' from 'backend'`. Since `app.py` imports `register_all_routers` from this same module at module scope, the entire backend — not just the new ITAM endpoints — fails to boot. This was never caught by the test suite because every test constructs an isolated FastAPI app directly from router objects (`conftest.make_test_app`) rather than importing `app.py`/`router_registry.py`. Both SUMMARYs' "1564 passed" / "no regressions" claims are accurate for the tests that ran, but none of those tests exercise the actual application entrypoint. **Fix is a one-line deletion** (remove lines 382-392); the correct registration already exists at lines 82-83.

2. **PARTIAL — custom fields defined at the model level never reach assets.** ROADMAP Success Criterion 3 requires fields defined on a Model to "appear on assets using that model." The definition surface (fieldsets, validation, dedup/shape/select-option rules) is solid and tested. But `itam_catalog_service.validate_custom_field_values`/`collect_field_defs` — the functions 56-02-SUMMARY.md and STATE.md both describe as "ready for 56-04 to import" — are never called by any production code path. `ManualAssetCreate.customFields` is accepted as pure free-form regardless of the asset's `modelId`. No 56-03/56-04 plan exists in this phase directory to close this loop, and ROADMAP.md marks Phase 56 complete at "2/2 plans."

3. **PARTIAL — lifecycleStatus has no read-time default for pre-existing agent-discovered assets.** ROADMAP Success Criterion 4 requires *every* asset to carry a distinct lifecycle status. This is true only for newly created manual assets. 56-01-PLAN.md's own architecture decision promised a "read-time default" for the field's absence on legacy/agent-discovered documents, explicitly deferring the implementation to "56-03, 56-04" — plans that, again, do not exist in this phase. `asset_endpoints.py`'s `GET` routes return raw stored documents with no such default applied.

None of the three gaps is deferred to a documented later phase — ROADMAP.md phases 57-61 make no mention of fieldset consumption or lifecycle-default backfill, so per Step 9b these remain live gaps rather than deferred items.

---

_Verified: 2026-08-04_
_Verifier: Claude (gsd-verifier)_

## Post-Verification Resolution (same session)

All 3 gaps resolved and independently re-confirmed:

1. **RESOLVED (commit `79ae5ce`)** — dead `register_itam_routers` (router_registry.py lines 382-392, crashed the entire backend on import) deleted. `python -c "import app"` now succeeds; live TestClient calls confirm `POST /api/assets` and `GET /api/itam/catalog/{kind}` return 401 (route found, auth required), not 404, contrasted against a genuinely nonexistent path (404).
2. **RESOLVED (commit `8910d05`)** — `collect_field_defs`/`validate_custom_field_values` wired into `create_manual_asset`: unknown `modelId` refused with 400; `customFields` validated against the model's fieldset definitions before write.
3. **RESOLVED (commit `8910d05`)** — read-time `lifecycleStatus` default (`DEFAULT_LIFECYCLE_STATUS`) added to both `GET /api/assets` and `GET /api/assets/{id}` for pre-existing agent-discovered assets.

Full backend suite after all fixes: 1585 passed / 34 skipped / 6 pre-existing unrelated failures (test_webhook_logic.py x2, test_agentic_ai.py tool_choice, test_e2e_integration.py golden path, test_rust_heartbeat_parity.py agent_type, test_log_heartbeat.py network-dependent) — no regressions.
