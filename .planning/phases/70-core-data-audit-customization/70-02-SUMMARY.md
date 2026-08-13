---
phase: 70-core-data-audit-customization
plan: 02
subsystem: itam
tags: [fastapi, motor, mongodb, react, typescript, vitest, itam, audit, hash-chain]

# Dependency graph
requires:
  - phase: 70-01
    provides: components/itam/CatalogPanel.tsx load/loading/error convention, src/__tests__/ITAMConsole.test.tsx mock-factory convention (extended here)
provides:
  - "backend/itam_audit_service.py — log_itam_action/get_itam_audit_logs/catalog_resource_type/ITAM_RESOURCE_TYPES, the single path every ITAM write route uses to reach the platform's existing hash-chained audit ledger"
  - "AuditService.get_logs(resource_type, resource_id, limit, skip) and GET /api/audit-logs?resourceType=&resourceId=&limit=&skip= — resource-scoped, paged reads over the shared ledger"
  - "All twenty ITAM write routes across all seven itam_*_endpoints.py files append to the ledger (D-02 backfill)"
  - "components/itam/ActivityLogPanel.tsx — Activity tab in ITAMConsole.tsx: filterable, paged activity feed with a ledger-integrity check, reusable pre-filtered via resourceType/resourceId props for a future asset-detail view"
affects: [70-03-csv-import-export, 70-04-settings-customization, itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin backfill-adapter module (itam_audit_service.py) centralizing a permanent-forever vocabulary (ITAM_RESOURCE_TYPES) that many call sites reference, rather than spelling resource-type strings inline at each of twenty call sites — costly to rename later because entries land in an append-only hash chain"
    - "log_itam_action never raises (internal try/except around the ledger write) — every ITAM write route calls it unconditionally after its own write succeeds, with no per-call-site try/except needed"
    - "Two same-purpose, differently-shaped functions can share the same name only if truly interchangeable; fetchAuditLogs already existed (legacy Time Machine timeline) with a swallow-on-error/different-field-shape contract, so the new ITAM reader is named fetchItamAuditLogs rather than merged or overwritten"

key-files:
  created:
    - backend/itam_audit_service.py
    - backend/tests/test_itam_audit.py
    - components/itam/ActivityLogPanel.tsx
    - src/__tests__/ITAMActivityLogPanel.test.tsx
  modified:
    - backend/audit_service.py
    - backend/audit_endpoints.py
    - backend/itam_asset_endpoints.py
    - backend/itam_catalog_endpoints.py
    - backend/itam_lifecycle_endpoints.py
    - backend/itam_finance_endpoints.py
    - backend/itam_license_endpoints.py
    - backend/itam_consumable_endpoints.py
    - backend/itam_component_endpoints.py
    - services/apiService.ts
    - types.ts
    - components/itam/ITAMConsole.tsx
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "D-02 (recorded in the plan): backfill audit calls into all 20 write routes across all 7 pre-existing itam_*_endpoints.py files, not just new-endpoint-only — 'view audit trail for any asset/entity' is read as covering the whole ITAM surface"
  - "AuditService._compute_hash, log_action_async, rollback, and verify_integrity left byte-for-byte untouched — only get_logs gained new optional filter/paging parameters — so every audit entry written before this phase still verifies"
  - "Renamed the new ITAM audit-read client function from fetchAuditLogs to fetchItamAuditLogs after discovering a pre-existing, differently-shaped fetchAuditLogs() already exported from apiService.ts for the legacy AuditLog.tsx timeline (Rule 1 auto-fix — duplicate export broke the production build)"

requirements-completed: [ITAM-DAT-02]

coverage:
  - id: D1
    description: "Every ITAM create/update/delete/assign/attach/detach/check-out/check-in write path across all seven itam_*_endpoints.py files appends one entry to the shared hash-chained audit ledger"
    requirement: "ITAM-DAT-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_audit.py::TestAssetCreateAuditBackfill::test_create_manual_asset_logs_one_audit_entry"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_audit.py::TestBackfillOneRoutePerFile (6 tests, one per newly-instrumented file)"
        status: pass
      - kind: other
        ref: "grep -c 'await log_itam_action' across the 7 endpoint files sums to 20 (asset:1, catalog:3, lifecycle:3, finance:1, license:4, consumable:5, component:3), matching the plan's per-file acceptance-criteria counts exactly"
        status: pass
    human_judgment: false
  - id: D2
    description: "An ITAM admin opens the ITAM console's Activity tab and sees the most recent ITAM changes with who, what, which entity, and when; filtering by entity type and entity id narrows to that entity's history within the tenant"
    requirement: "ITAM-DAT-02"
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMActivityLogPanel.test.tsx (8 tests: rows render, empty state, error state, type-filter refetch, id-filter refetch, pre-filtered props hide controls, integrity pass/fail rendering)"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx::switches to the Activity tab and shows the empty state"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_audit.py::TestAuditLogsFilterRoute (3 tests: resourceType+resourceId filtering, limit/skip forwarding, tenantId always present in the built query)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A failure inside audit logging never fails the ITAM write it is recording, across the tracer route and the backfilled routes"
    requirement: "ITAM-DAT-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_audit.py::TestAssetCreateAuditBackfill::test_asset_create_still_succeeds_when_audit_write_raises"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_audit.py::TestBackfillOneRoutePerFile::test_catalog_create_still_succeeds_when_audit_write_raises"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live-browser confirmation: create/check out an asset, open the Activity tab and see it with username/action/asset id, filter by entity id to that asset alone, and confirm 'Verify ledger integrity' reports a valid chain in the running app"
    verification: []
    human_judgment: true
    rationale: "Task 3's <human-check> requires driving the actual browser UI against a running backend. This project's human_verify_mode is end-of-phase (matching 65-01's precedent), so it was not executed in this autonomous run and is deferred to phase-level human verification."

# Metrics
duration: 65min
completed: 2026-08-12
status: complete
---

# Phase 70 Plan 02: Audit Trail Summary

**Every ITAM write across all seven pre-existing itam_*_endpoints.py files (20 routes) now appends to the platform's existing SHA-256 hash-chained audit_logs ledger via a single new itam_audit_service.log_itam_action helper, and a new filterable, paged Activity tab in the ITAM console reads it back through the extended GET /api/audit-logs, closing ITAM-DAT-02's "audit trail for any asset/entity" gap that `grep -rn "log_action_async" backend/itam_*.py` previously returned zero matches for.**

## Performance

- **Duration:** ~65 min
- **Completed:** 2026-08-12
- **Tasks:** 3 (1 tracer, 2 auto)
- **Files modified:** 17 (4 created, 13 modified)

## Accomplishments
- New `backend/itam_audit_service.py` — the single path every ITAM write route uses to reach the ledger: `log_itam_action` (never raises), `get_itam_audit_logs` (read pass-through), `catalog_resource_type` (URL-segment → resource-type mapping), and the frozen `ITAM_RESOURCE_TYPES` vocabulary
- `AuditService.get_logs` extended with `resource_type`/`resource_id`/`limit`/`skip` — narrows the existing tenant-scoped query as additional equality terms, replaces the previous hard-coded `to_list(length=100)` with a real `.sort().skip().limit().to_list()` chain, clamps `limit` to 1..1000; `_compute_hash`/`log_action_async`/`rollback`/`verify_integrity` untouched
- `GET /api/audit-logs` gained `resourceType`/`resourceId` query params and now honours the previously-declared-but-ignored `limit`/`skip`
- All twenty ITAM write routes across `itam_asset_endpoints.py` (1), `itam_catalog_endpoints.py` (3), `itam_lifecycle_endpoints.py` (3), `itam_finance_endpoints.py` (1), `itam_license_endpoints.py` (4), `itam_consumable_endpoints.py` (5), and `itam_component_endpoints.py` (3) call `log_itam_action` after their write succeeds and before their existing success response — none call `get_audit_service()` directly and none touch `db.audit_logs`
- New `components/itam/ActivityLogPanel.tsx` mounted as the ITAM console's 7th tab ("Activity"): entity-type filter + free-text entity-id filter (hidden when the panel is mounted pre-filtered via `resourceType`/`resourceId` props, so a future asset-detail view can embed it), 50-row Previous/Next paging, a "Verify ledger integrity" button surfacing `POST /api/audit-logs/integrity-check`'s pass/fail result, and a per-row expand toggle rendering `previousState` as pretty-printed JSON

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end audit trail for one entity type — asset create → ledger → console** - `8f622e5` (feat, tracer)
2. **Task 2: Backfill audit logging into the remaining six ITAM endpoint files (D-02)** - `f08f1b0` (feat)
3. **Task 3: Entity-scoped activity view — filters, paging, and a ledger-integrity indicator** - `8643953` (feat)

**Plan metadata:** pending (this SUMMARY's own commit, scoped per orchestrator instruction to SUMMARY.md + REQUIREMENTS.md only)

## Files Created/Modified
- `backend/itam_audit_service.py` (new) - `log_itam_action`, `get_itam_audit_logs`, `catalog_resource_type`, `ITAM_RESOURCE_TYPES`
- `backend/audit_service.py` - `get_logs` gains `resource_type`/`resource_id`/`limit`/`skip`, real cursor chain replacing the hard-coded page
- `backend/audit_endpoints.py` - `GET /api/audit-logs` gains `resourceType`/`resourceId`, forwards `limit`/`skip`
- `backend/itam_asset_endpoints.py` - `create_manual_asset` logs `itam_asset.create` (Task 1 tracer)
- `backend/itam_catalog_endpoints.py` - `create_catalog_entity`/`update_catalog_entity`/`delete_catalog_entity` log against `catalog_resource_type(kind)`
- `backend/itam_lifecycle_endpoints.py` - `checkout_asset`/`checkin_asset`/`mark_asset_audited` log `itam_asset.{checkout,checkin,audit}`
- `backend/itam_finance_endpoints.py` - `update_asset_purchase` logs `itam_asset.purchase_update`
- `backend/itam_license_endpoints.py` - `create_license`/`update_license`/`assign_license`/`reclaim_license` log against `itam_license`/`itam_license_assignment`
- `backend/itam_consumable_endpoints.py` - all 5 write routes log against `itam_consumable`
- `backend/itam_component_endpoints.py` - `create`/`attach`/`detach` log against `itam_component`
- `backend/tests/test_itam_audit.py` (new) - 12 tests: tracer coverage, filter/paging/tenant-isolation coverage, one representative route per backfilled file, resilience-to-audit-failure coverage
- `services/apiService.ts` - `fetchItamAuditLogs(params?)`, `verifyAuditIntegrity()`
- `types.ts` - `AuditLogEntry`
- `components/itam/ActivityLogPanel.tsx` (new) - the full activity feed panel
- `components/itam/ITAMConsole.tsx` - `'activity'` tab
- `src/__tests__/ITAMActivityLogPanel.test.tsx` (new) - 8 tests
- `src/__tests__/ITAMConsole.test.tsx` - extended mock factory (`fetchItamAuditLogs`, `verifyAuditIntegrity`) + Activity tab assertions

## Decisions Made
- D-02 backfill scope: all 20 pre-existing write routes across all 7 endpoint files, not just this phase's own additions — matches the plan's explicit reading of ROADMAP success criterion 2
- `_compute_hash` and its payload field order are permanently off-limits — verified by a diff check in Task 1's acceptance criteria — so every entry written before this phase still verifies under the unchanged hash chain
- Renamed the new client function `fetchAuditLogs` → `fetchItamAuditLogs` after discovering a same-named, pre-existing function in `apiService.ts` (used by the unrelated legacy `components/AuditLog.tsx` "Time Machine" timeline) — the two have incompatible shapes and error-handling contracts (the legacy one swallows all errors and returns `actor`/`status`-shaped rows; the new one throws on non-2xx, including a distinct 403 message, and returns the ledger's real `userName`/`resourceType`/`resourceId` shape), so they were kept separate rather than merged
- `itam_audit_service.py`'s module docstring explicitly notes that its own `get_itam_audit_logs` function name (mandated by this plan's own Task 1 artifact spec) will always show up in a literal `grep audit_logs backend/itam_*.py` scan — documented rather than worked around, since the function name is a required artifact and the real security property (no `itam_*.py` file calls a Mongo collection method directly) is independently verified

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Renamed the new ITAM audit-read function to avoid a duplicate-export build break**
- **Found during:** Task 3, running `npm run build` as part of the plan's `<verification>` block
- **Issue:** The plan specified naming the new filterable/paged ITAM audit-read client function `fetchAuditLogs`, matching Task 1's action text. `services/apiService.ts` already exported a different `fetchAuditLogs` (no params, swallows all errors, returns `actor`/`status`-shaped rows) consumed by the pre-existing, unrelated `components/AuditLog.tsx` "Time Machine" timeline and `App.tsx`'s `loadAllData`. Two `export const fetchAuditLogs` declarations in one module is a hard Rolldown/Vite parse error (`Duplicated export 'fetchAuditLogs'`), which `npm run build` caught but the earlier `npx vitest` runs (which stub the whole module via `vi.mock`) did not.
- **Fix:** Renamed the new function to `fetchItamAuditLogs` throughout — its definition in `apiService.ts`, the import/call in `ActivityLogPanel.tsx`, and the mocks/assertions in `ITAMActivityLogPanel.test.tsx` and `ITAMConsole.test.tsx`. Verified the pre-existing `fetchAuditLogs()` and its two callers (`AuditLog.tsx`, `App.tsx`) were left completely untouched — confirmed via `grep` that neither file was modified.
- **Files modified:** services/apiService.ts, components/itam/ActivityLogPanel.tsx, src/__tests__/ITAMActivityLogPanel.test.tsx, src/__tests__/ITAMConsole.test.tsx
- **Verification:** `npm run build` succeeds; `npx vitest run src/__tests__` — 65/65 pass; `backend` suite unaffected (no backend files touched by this fix)
- **Committed in:** `8643953` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for the frontend to build at all; no scope creep — the fix is a rename with zero behavior change to either function, and the plan's stated artifact list, resource-type vocabulary, and route coverage are otherwise unaffected.

## Issues Encountered
- None beyond the deviation above — every acceptance-criteria grep count in the plan (per-file `log_itam_action` counts, `resourceType`/`verifyAuditIntegrity` occurrence counts, line-count cap) matched on the first attempt after implementation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `itam_audit_service.py`'s `ITAM_RESOURCE_TYPES` and `log_itam_action` are available for 65-03 (CSV Import/Export) to log `itam_import` actions and for 65-04 (Settings & Customization) to log `itam_settings` actions, using the exact same vocabulary strings already reserved in this plan
- One item remains human-only per `human_verify_mode: end-of-phase` (matching 65-01's precedent): live-browser confirmation of the Activity tab against a running backend — checkout/checkin an asset, see it appear, filter by entity id, and confirm "Verify ledger integrity" reports valid — deferred to phase-level human verification
- No blockers for 65-03 or 65-04

---
*Phase: 65-core-data-audit-customization*
*Completed: 2026-08-12*

## Self-Check: PASSED

All created/modified files verified present on disk; all three task commit hashes (`8f622e5`, `f08f1b0`, `8643953`) verified present in git history.
