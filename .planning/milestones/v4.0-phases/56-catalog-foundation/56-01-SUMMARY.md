---
phase: 56-catalog-foundation
plan: 01
subsystem: itam
tags:
  - ITAM-CAT-01
  - ITAM-CAT-02
  - ITAM-LIFE-01
  - tracer
dependency_graph:
  requires: []
  provides:
    - itam_models
    - itam_catalog_endpoints
    - itam_asset_endpoints
    - asset_source_discriminator
    - lifecycle_status_field
    - atomic_asset_tag_counter
  affects:
    - phase_57_checkout
    - phase_58_labels
    - phase_59_procurement_finance
    - phase_60_licenses_consumables
    - phase_61_frontend_console
tech_stack:
  added: []
  patterns:
    - Kind-parameterized catalog CRUD router (CATALOG_KINDS dict)
    - Extend-not-fork asset model via assetSource discriminator
    - Atomic per-tenant counter via find_one_and_update + $inc
key_files:
  created:
    - backend/itam_models.py
    - backend/itam_catalog_endpoints.py
    - backend/itam_asset_endpoints.py
    - backend/tests/test_itam_foundation.py
  modified:
    - backend/router_registry.py
    - backend/rbac_utils.py
    - backend/rbac_service.py
    - backend/database.py
decisions:
  - "Extend the existing assets collection with assetSource: agent|manual rather than fork a parallel itam_assets collection — promote decision from the milestone architecture research, corroborated by all 4 research files (search/dashboards/bulk-update/criticality-gating already assume one assets collection is the CMDB)."
  - "New field name lifecycleStatus, not status — assets.status already carries agent-liveness/connectivity meaning; reusing it would silently collide with the heartbeat path."
  - "Asset tag generation uses a tenant-scoped counters collection + atomic find_one_and_update($inc) — first atomic-counter precedent in this codebase, reused by Phase 59 for PO numbers."
  - "POST /api/assets is new — no prior manual asset-creation endpoint existed; assets were previously only created via the hostname-keyed agent heartbeat/registry upsert."
metrics:
  duration: 0m
  completed_at: 2026-08-04T08:15:00Z
status: complete
---
# Phase 56 Plan 01: Catalog & Foundation tracer slice Summary

**Objective:** Prove the Phase 56 architecture end-to-end on one thin slice: an admin creates a Manufacturer through a new tenant-isolated catalog router, then hand-catalogues a manual asset that references it — landing in the existing `assets` collection with the new `assetSource` discriminator, `lifecycleStatus` field, and an atomically generated per-tenant asset tag.

**Summary:** Built `itam_models.py` (Pydantic v2 request contracts: `ManualAssetCreate`, `CatalogEntityCreate`/`Update`, the `ASSET_SOURCE_*`/`LifecycleStatus` vocabulary — every later ITAM phase imports these), `itam_catalog_endpoints.py` (kind-parameterized CRUD router at `/api/itam/catalog/{kind}` — currently registers `manufacturers`, extensible via `CATALOG_KINDS`/`CATALOG_REFERENCE_FIELDS`, with delete-protection when a catalog entity is still referenced by an asset), and `itam_asset_endpoints.py` (`POST /api/assets` manual-asset creation sharing the `/api/assets` prefix with the existing agent-facing `asset_endpoints.py`, registered after it so the existing single-segment `GET /{asset_id}` route keeps first-match priority; the atomic `next_asset_tag()` counter helper). Both new routers registered in `router_registry.py`; `manage:assets` permission gates both. Manual creation never writes the `status` key (reserved for agent-liveness) and rejects client-supplied `id`/`assetSource`/`status`/`tenantId` at the Pydantic validation boundary.

The plan was produced by a `gsd-planner` agent run under `TRACER_MODE=true`, which — beyond its normal planning scope — also implemented and committed the tracer slice's code directly (commit `1218c37`) before hitting a session limit mid-run. The committed test suite (`test_itam_foundation.py`) was not green at that point: 5 of 8 tests failed, none of which were caught before commit. Diagnosed and fixed in two follow-up commits (`e1d377f`, `329a698`) as part of this same plan's closure:

- `MockTenantIsolatedCollection`'s proxy methods wrapped `AsyncMock(side_effect=lambda ...)` around another AsyncMock — calling an AsyncMock synchronously inside a sync lambda returns a live, never-awaited coroutine instead of the real value, producing `TypeError`/`ResponseValidationError`/silent-no-op failures depending on call site. Replaced with real `async def` proxy methods (single await chain).
- `itam_catalog_endpoints.py`/`itam_asset_endpoints.py` use `from X import Y` name-binding imports for `get_database`, `verify_permission`, and `invalidate_cache` — the test fixtures patched the *source* module's attribute (`database.get_database`, `rbac_utils.verify_permission`, `cache_service.invalidate_cache`), which does not affect the already-bound local names in the importing modules. Fixed to patch each importing module's own name.
- A lambda using `:=` on an outer-scope variable creates a new local binding scoped to the lambda (`UnboundLocalError` on read-before-assign, or a silently-tautological outer assertion) instead of mutating the outer name — fixed with mutable-container closures.
- Two minor bugs: a dead unused assertion list, and a wrong expected string-length constant.

Also closed a real must_haves coverage gap: 4 of the 11 `must_haves.truths` (delete-protection 409, duplicate-caller-tag 409, cross-tenant isolation, concurrent-tag-generation distinctness) had no dedicated test even though the application logic for all four already existed. Added 5 new tests (including a real `asyncio.gather` concurrency test against the actual `find_one_and_update`-based counter, not a pre-scripted sequence) plus the missing `delete_one` proxy method.

**Final state:** 13/13 ITAM tests pass. Full backend suite: 1564 passed / 34 skipped / 6 pre-existing unrelated failures (`test_webhook_logic.py` x2, `test_agentic_ai.py` tool_choice, `test_e2e_integration.py` golden path, `test_rust_heartbeat_parity.py` agent_type, `test_log_heartbeat.py` network-dependent) — no regressions.

## Deviations from Plan

### Process deviation (not a code deviation)

The `gsd-planner` agent implemented and committed real application code and tests as part of what should have been a plan-only run (planning and execution are normally separate GSD roles). The resulting code was directionally correct and matched the plan's own `files_modified`/`must_haves`, but was committed without a passing test run — a violation of "always run tests before committing." This plan's closure work (this summary + the two follow-up commits) treats the already-committed code as the Wave 1 execution output and brings it up to the same bar a normal `/gsd-execute-phase` run would have enforced before commit.

### Auto-fixed Issues

- 5 of 8 committed tests were failing at commit time (test-infrastructure bugs only — see Summary above). Fixed, not deferred.
- 4 of 11 must_haves lacked test coverage despite the underlying logic existing. Fixed, not deferred.

## Threat Flags

None beyond the plan's own `<threat_model>` (ASVS L1, admin-only CRUD reusing the existing `manage:assets` permission and `TenantIsolatedCollection` pattern — no new auth mechanism introduced).

## Requirements Coverage

- ITAM-CAT-01 (Manufacturer/Model/Category/Location catalog CRUD): Manufacturer CRUD delivered this plan; Model/Category/Location deferred to 56-02 per the wave split.
- ITAM-CAT-02 (manual asset creation with unique per-tenant asset tag + source discriminator): Complete.
- ITAM-LIFE-01 (lifecycleStatus field, distinct from agent connectivity status): Complete.
