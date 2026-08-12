---
phase: 65-core-data-audit-customization
plan: 03
subsystem: itam
tags: [fastapi, motor, mongodb, react, typescript, vitest, itam, csv, tdd]

# Dependency graph
requires:
  - phase: 65-02
    provides: backend/itam_audit_service.py log_itam_action/ITAM_RESOURCE_TYPES, the shared hash-chained audit ledger every ITAM write route uses
provides:
  - "backend/itam_data_service.py — pure CSV shaping with zero DB I/O: ASSET_EXPORT_COLUMNS, sanitize_csv_cell (formula-injection mitigation), asset_to_row, generate_assets_csv, parse_csv_rows, row_to_asset_payload, MAX_IMPORT_BYTES/MAX_IMPORT_ROWS"
  - "GET /api/itam/data/export — tenant-scoped, formula-safe CSV export of assets, one column per custom field, logs itam_export.assets"
  - "POST /api/itam/data/import — 64 KiB-chunked, size/row-capped (5 MiB / 5000 rows), per-row-validated CSV import with dry-run support, a capped per-row failure report, and itam_asset.create + itam_import.assets audit entries"
  - "backend/itam_asset_endpoints.py build_asset_document(payload, tenant_id, asset_tag, now) — asset-document assembly extracted from create_manual_asset and shared with the import path so the two write paths cannot drift"
  - "components/itam/BulkImportExportPanel.tsx — new Import / Export tab in ITAMConsole.tsx: export button plus upload/dry-run/per-row-report import UI"
affects: [65-04-settings-customization, itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure CSV-shaping module (itam_data_service.py) with zero DB I/O, mirroring itam_catalog_service.py's convention — ASSET_EXPORT_COLUMNS and the customFields.<key> column naming are defined once and shared by both the export and import halves so the two directions cannot drift apart"
    - "A bulk write path reuses the exact validator pair (collect_field_defs + validate_custom_field_values) and document builder (build_asset_document) the single-write path (create_manual_asset) uses, rather than reimplementing validation — this plan's key_links constraint, closing the highest-risk gap a bulk-write endpoint creates"
    - "Bounded upload read via a 64 KiB chunk loop with an early HTTP 413 abort — never a bare `await file.read()` — bounding memory before CSV parsing even starts"
    - "Hand-rolled <input type=\"file\"> + FormData for the upload UI — no existing upload component in this frontend (65-PATTERNS.md 'No Analog Found'), no new dependency added"

key-files:
  created:
    - backend/itam_data_service.py
    - backend/itam_data_endpoints.py
    - backend/tests/test_itam_data_csv.py
    - components/itam/BulkImportExportPanel.tsx
    - src/__tests__/ITAMBulkImportExport.test.tsx
  modified:
    - backend/itam_asset_endpoints.py
    - backend/itam_audit_service.py
    - backend/router_registry.py
    - services/apiService.ts
    - types.ts
    - components/itam/ITAMConsole.tsx
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "build_asset_document extracted from create_manual_asset's inline document assembly into a standalone, reusable function (itam_asset_endpoints.py) rather than duplicating the id/tenantId/assetSource/lifecycleStatus/timestamp assembly logic in the import path — the plan's explicit key_link, verified not to change create_manual_asset's externally observable behavior (full itam_foundation/itam_audit suites still pass unchanged)"
  - "TDD gate followed literally for Task 2 (tdd=\"true\"): a RED commit (30 tests added, collection error since MAX_IMPORT_BYTES/parse_csv_rows/row_to_asset_payload/the /import route did not exist yet) landed before the GREEN implementation commit"
  - "Server-owned columns (id, createdAt, updatedAt, tenantId, assetSource, lastScanned, warrantyAlertSentAt) are silently dropped by row_to_asset_payload rather than forwarded to ManualAssetCreate — this is what makes an exported file re-importable into the same tenant without an 'unexpected field' error, while still leaving assetTag-duplicate detection (a deliberate business rule) in place to skip an unmodified re-import's rows rather than silently double-creating them"
  - "Any column name that survives row_to_asset_payload's drop/customFields-split logic (i.e. isn't server-owned and isn't customFields.<key>-prefixed) is forwarded to ManualAssetCreate verbatim; the model's extra=\"forbid\" is what rejects an unknown column, so this module invents no unknown-column validation of its own — kept the two failure paths (structural vs domain) from drifting apart"

requirements-completed: [ITAM-DAT-03]

coverage:
  - id: D1
    description: "An ITAM admin clicks Export in the ITAM console's Import / Export tab and receives a formula-safe CSV of their tenant's assets, including one column per custom field actually present"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestExportAssetsRoute::test_export_two_assets_returns_csv_with_header_and_custom_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestExportAssetsRoute::test_export_with_no_assets_still_writes_a_header_row"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMBulkImportExport.test.tsx::clicking the export button calls exportItamAssetsCsv"
        status: pass
    human_judgment: false
  - id: D2
    description: "The exported CSV cannot carry a spreadsheet formula payload — sanitize_csv_cell neutralises any cell whose first character would make Excel/Sheets treat it as a formula or escape sequence"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestExportAssetsRoute::test_export_neutralizes_formula_leading_cell"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestSanitizeCsvCell (6 parametrized + 3 unit tests, one per risky leading char plus benign/None/non-string cases)"
        status: pass
    human_judgment: false
  - id: D3
    description: "An ITAM admin uploads a CSV and the valid assets in it are created, with a per-row report naming exactly which rows were rejected and why (unknown modelId, out-of-options select value, unknown column, duplicate assetTag), rendered in a readable table in the console"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestImportAssetsRoute (valid-row, unknown-modelId, out-of-options-value, unknown-column, duplicate-assetTag, error-cap tests)"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMBulkImportExport.test.tsx::a result with two errors renders both row numbers and their problems"
        status: pass
    human_judgment: false
  - id: D4
    description: "A dry run validates an uploaded CSV and reports what would happen (created/skipped counts, per-row errors) without writing a single asset or audit entry"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestImportAssetsRoute::test_dry_run_reports_same_counts_and_writes_nothing (asserts insert_one never awaited and audit_logs store stays empty)"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMBulkImportExport.test.tsx::choosing a file and clicking Import calls importItamAssetsCsv with dryRun true by default"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every imported row's customFields are validated against the owning asset model's fieldset definitions by the same collect_field_defs + validate_custom_field_values pair the manual-create path uses — not a reimplementation"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestImportAssetsRoute::test_custom_field_value_outside_select_options_is_skipped_with_shared_validator_message (asserts the exact message validate_custom_field_values produces)"
        status: pass
      - kind: other
        ref: "grep -c validate_custom_field_values backend/itam_data_endpoints.py returns 4 (import + 3 doc/comment references); grep -c 'def build_asset_document' backend/itam_asset_endpoints.py returns 1"
        status: pass
    human_judgment: false
  - id: D6
    description: "An oversized upload is refused with HTTP 413 before its bytes are fully buffered into memory — the route reads in 64 KiB chunks and aborts the moment the accumulated size passes MAX_IMPORT_BYTES (5 MiB), never a bare unbounded read()"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestImportAssetsRoute::test_oversized_upload_refused_with_413_before_parsing"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_data_csv.py::TestImportAssetsRoute::test_row_count_over_cap_refused_with_400"
        status: pass
    human_judgment: false
  - id: D7
    description: "An export never contains a row belonging to another tenant — the export query runs exclusively through the tenant-isolated get_database() wrapper, never a raw internal database handle"
    requirement: "ITAM-DAT-03"
    verification:
      - kind: other
        ref: "grep -c 'db._db' backend/itam_data_endpoints.py returns 0 (structural proof no raw handle is used); the same get_database() wrapper is exercised by every passing test in backend/tests/test_itam_data_csv.py and by the platform-wide TenantIsolatedDatabase tests already covering this wrapper elsewhere (e.g. test_itam_audit.py::TestAuditLogsFilterRoute::test_get_audit_logs_query_always_carries_tenant_id)"
        status: pass
    human_judgment: true
    rationale: "No dedicated two-tenant integration test seeds tenant-a and tenant-b assets and asserts tenant-a's export excludes tenant-b's rows in this plan's own test file — this plan's hand-rolled mock (matching test_itam_foundation.py/test_itam_audit.py's established convention) does not itself enforce tenant filtering in the fake, only the real TenantIsolatedDatabase does. The grep-based structural proof (no raw db._db handle) plus reuse of the identical get_database() wrapper every other ITAM route already relies on is strong evidence, but a live cross-tenant behavioral test was not written for this specific route — flagged for human/phase-level verification rather than silently asserted proven."
  - id: D8
    description: "Live-browser confirmation: export a CSV and open it, edit a bad row and dry-run import it (report names the bad row, nothing created), then import for real and see the good row appear in the asset list and both the creation and the batch show up in Activity"
    verification: []
    human_judgment: true
    rationale: "Task 3's <human-check> requires driving the actual browser UI against a running backend. This project's human_verify_mode is end-of-phase (matching 65-01/65-02 precedent), so it was not executed in this autonomous run and is deferred to phase-level human verification."

# Metrics
duration: 80min
completed: 2026-08-12
status: complete
---

# Phase 65 Plan 03: CSV Import/Export Summary

**Bidirectional ITAM asset CSV pipeline — GET /api/itam/data/export streams a formula-safe, tenant-scoped CSV with one column per custom field, and POST /api/itam/data/import validates every row through the exact same collect_field_defs/validate_custom_field_values/build_asset_document functions the manual-create route uses, size-capped at 5 MiB / 5000 rows with a dry-run mode and a per-row failure report — closing ITAM-DAT-03, the last of the three Core Data requirements.**

## Performance

- **Duration:** ~80 min
- **Completed:** 2026-08-12
- **Tasks:** 3 (1 tracer, 1 auto/tdd, 1 auto)
- **Files modified:** 12 (5 created, 7 modified)

## Accomplishments
- New `backend/itam_data_service.py` — pure, zero-DB-I/O CSV shaping shared by both directions: `ASSET_EXPORT_COLUMNS` (the permanent export column order), `sanitize_csv_cell` (the sole formula-injection mitigation, T-65-03-01), `asset_to_row`/`generate_assets_csv` (export), `parse_csv_rows`/`row_to_asset_payload` (import), `MAX_IMPORT_BYTES`/`MAX_IMPORT_ROWS`
- New `backend/itam_data_endpoints.py` — `GET /export` (tenant-scoped via `get_database()`, never a raw handle; T-65-03-04) and `POST /import` (64 KiB-chunked read aborting at 413 past `MAX_IMPORT_BYTES`, T-65-03-02; per-row `ManualAssetCreate` + `collect_field_defs`/`validate_custom_field_values`, T-65-03-03; dry-run writes nothing; capped 100-entry error report), both gated by `itam_asset_endpoints._require_itam_admin` (T-65-03-05)
- `backend/itam_asset_endpoints.py` — `build_asset_document(payload, tenant_id, asset_tag, now)` extracted from `create_manual_asset`'s inline assembly and now shared by both the manual-create and CSV-import write paths, so an asset document has exactly one definition
- `backend/itam_audit_service.py` — `itam_export` added to `ITAM_RESOURCE_TYPES`; every export logs `itam_export.assets`, every created-via-import asset logs `itam_asset.create`, every non-dry-run batch logs one `itam_import.assets` summary (T-65-03-06)
- `backend/router_registry.py` — `itam_data_endpoints` registered in the ITAM block
- New `components/itam/BulkImportExportPanel.tsx` mounted as `ITAMConsole.tsx`'s 8th tab ("Import / Export"): an Export section (optional model-id filter, blob download via the existing `triggerLabelDownload` helper) and an Import section (hand-rolled `<input type="file">` + `FormData`, a dry-run checkbox checked by default, a results region with created/skipped counts, a dry-run banner, and a per-row errors table)
- `services/apiService.ts` — `exportItamAssetsCsv(modelId?)` and `importItamAssetsCsv(file, dryRun?)`; `types.ts` — `ItamImportRowError`/`ItamImportResult`

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end CSV export — console button to downloaded file** (tracer) - `91e3fc67` (feat)
2. **Task 2: CSV import — size-capped upload, per-row validation, dry run, audited writes** (tdd) - RED `b6c342c9` (test), GREEN `37264a72` (feat)
3. **Task 3: Import UI — upload, dry run, and a readable per-row failure report** - `740cfbb0` (feat)

**Plan metadata:** pending (this SUMMARY's own commit, scoped per orchestrator instruction to SUMMARY.md + REQUIREMENTS.md only)

## Files Created/Modified
- `backend/itam_data_service.py` (new) - `ASSET_EXPORT_COLUMNS`, `sanitize_csv_cell`, `asset_to_row`, `generate_assets_csv`, `parse_csv_rows`, `row_to_asset_payload`, `MAX_IMPORT_BYTES`/`MAX_IMPORT_ROWS`
- `backend/itam_data_endpoints.py` (new) - `GET /api/itam/data/export`, `POST /api/itam/data/import`, `MAX_EXPORT_ROWS`
- `backend/itam_asset_endpoints.py` - `build_asset_document` extracted from `create_manual_asset`
- `backend/itam_audit_service.py` - `itam_export` added to `ITAM_RESOURCE_TYPES`
- `backend/router_registry.py` - registers `itam_data_endpoints`
- `backend/tests/test_itam_data_csv.py` (new) - 30 tests: export route (4), sanitize_csv_cell unit tests (10), row_to_asset_payload unit tests (6), parse_csv_rows (1), import route (9)
- `services/apiService.ts` - `exportItamAssetsCsv`, `importItamAssetsCsv`
- `types.ts` - `ItamImportRowError`, `ItamImportResult`
- `components/itam/BulkImportExportPanel.tsx` (new) - Export + Import sections, 191 lines
- `components/itam/ITAMConsole.tsx` - `'data'` tab ("Import / Export")
- `src/__tests__/ITAMBulkImportExport.test.tsx` (new) - 8 tests (3 export, 5 import)
- `src/__tests__/ITAMConsole.test.tsx` - extended mock factory (`exportItamAssetsCsv`) + 8th-tab assertions

## Decisions Made
- `build_asset_document` extraction kept `create_manual_asset`'s externally observable behavior byte-for-byte identical — proven by the full `itam_foundation`/`itam_audit` suites passing unchanged, not just by inspection
- Task 2's `tdd="true"` gate followed literally: tests committed first against a not-yet-existing `/import` route and not-yet-existing service functions (confirmed to fail collection), then the implementation commit made them pass
- Server-owned columns (`id`, `createdAt`, `updatedAt`, `tenantId`, `assetSource`, `lastScanned`, `warrantyAlertSentAt`) are dropped by `row_to_asset_payload` rather than forwarded — this is what lets an exported file re-import without an "unexpected field" error, while the independent duplicate-`assetTag` check still stops an unmodified re-import from silently double-creating every row
- Any column that isn't server-owned and isn't `customFields.<key>`-prefixed is forwarded to `ManualAssetCreate` verbatim; `extra="forbid"` is what rejects it — `row_to_asset_payload` invents no unknown-column validation of its own, keeping structural and domain validation from drifting apart
- Switched `HTTP_413_REQUEST_ENTITY_TOO_LARGE` to the non-deprecated `HTTP_413_CONTENT_TOO_LARGE` alias (both resolve to 413; the deprecated one emitted a `StarletteDeprecationWarning` on every oversized-upload test run) — Rule 1 auto-fix, zero behavior change

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used the non-deprecated FastAPI 413 status constant**
- **Found during:** Task 2, first `pytest` run after implementing `POST /import`
- **Issue:** `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` is deprecated in the installed Starlette version (`StarletteDeprecationWarning: Use 'HTTP_413_CONTENT_TOO_LARGE' instead`), surfaced as a warning on every oversized-upload test.
- **Fix:** Switched to `status.HTTP_413_CONTENT_TOO_LARGE` (identical numeric value, no behavior change). The plan's acceptance criterion (`grep -c "413" backend/itam_data_endpoints.py` returns at least 1) still holds against the new constant name.
- **Files modified:** backend/itam_data_endpoints.py
- **Verification:** `backend/venv/bin/python -m pytest backend/tests/test_itam_data_csv.py -q` — 30/30 pass, warning gone
- **Committed in:** `37264a72` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Cosmetic — a deprecation-warning fix with zero behavior change. No scope creep.

## Issues Encountered
- None beyond the deviation above — every acceptance-criteria grep count in the plan matched on first or second attempt (one `db._db`-in-docstring false-positive was reworded, see below).
- Two module-docstring sentences in `itam_data_endpoints.py` originally used the literal substring `` `db._db` `` for readability, which collided with the plan's acceptance criterion `grep -c "db._db" backend/itam_data_endpoints.py` returning 0 (the criterion is meant to catch a raw handle *used* in code, not mentioned in prose). Reworded both sentences to "a raw internal database handle" — no code change, criterion now passes cleanly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ITAM-DAT-01/02/03 (Custom Fields, Audit Trail, CSV Import/Export) — all three Core Data requirements are now complete, closing out the 65-core-data-audit-customization phase's Core Data scope for the v4.1 ITAM-Backlog milestone
- The export/import round trip is structurally clean: every `ASSET_EXPORT_COLUMNS` entry either round-trips through `ManualAssetCreate` unchanged or is a server-owned column `row_to_asset_payload` silently drops — no "unexpected field" error is possible on a straight re-import of an unmodified export
- Two items remain human-only per `human_verify_mode: end-of-phase` (matching 65-01/65-02 precedent), both deferred to phase-level human verification:
  1. A live two-tenant cross-export isolation check (D7) — this plan proved the property structurally (grep for the absence of a raw database handle, plus reuse of the platform's existing tenant-isolated wrapper) but did not write a dedicated two-tenant behavioral test
  2. The full live-browser round trip described in Task 3's `<human-check>` (D8): export → edit → dry-run import → real import → confirm in the asset list and Activity tab
- No blockers for 65-04 (Settings & Customization) — `itam_audit_service.ITAM_RESOURCE_TYPES` already reserves `itam_settings` for that phase to use with the same `log_itam_action` helper this plan reused

---
*Phase: 65-core-data-audit-customization*
*Completed: 2026-08-12*

## Self-Check: PASSED

All created files (`backend/itam_data_service.py`, `backend/itam_data_endpoints.py`, `backend/tests/test_itam_data_csv.py`, `components/itam/BulkImportExportPanel.tsx`, `src/__tests__/ITAMBulkImportExport.test.tsx`, this SUMMARY.md) verified present on disk; all four task commit hashes (`91e3fc67`, `b6c342c9`, `37264a72`, `740cfbb0`) verified present in `git log`.
