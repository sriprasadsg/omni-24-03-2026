---
phase: 58-asset-tags-offline-labels
plan: 04
subsystem: api
tags: [reportlab, pdf, avery-5160, fastapi, itam, rbac, tenant-isolation, offline-verification]

requires:
  - phase: 58-01
    provides: "itam_label_service.py/itam_label_endpoints.py scaffolding, generate_qr_png, LabelEncodingError, _load_asset_for_label, _safe_filename_part"
  - phase: 58-03
    provides: "generate_barcode_png, _resolve_tag_for_label shared prelude, block_all_sockets offline-proof pattern in test_itam_labels_offline.py"
provides:
  - "POST /api/assets/labels/sheet — streams a printable Avery-5160 PDF label sheet (QR + barcode + tag/name/model text) for a caller-ordered, duplicate-honouring list of asset ids"
  - "itam_label_service.generate_label_sheet_pdf / label_cell_origin / label_draw_boxes / _fit_text — pure, no FastAPI/DB import, unit-testable in isolation"
  - "Behavioral proof (not source inspection) that all three generators (QR, barcode, PDF sheet) complete with every socket entry point blocked — ROADMAP success criterion 3 now fully discharged"
affects: ["61-frontend-itam-console"]

tech-stack:
  added: []
  patterns:
    - "label_cell_origin is the single source of the Avery-5160 grid arithmetic — both generate_label_sheet_pdf and TestSheetGeometry read it, so the geometry test cannot pass against arithmetic the renderer doesn't use"
    - "_fit_text truncates by measured pdfmetrics.stringWidth against a band's pixel width, never by character count — the mitigation that stops a long/wide-glyph asset name from bleeding into the neighbouring label (T-58-02)"
    - "One fresh io.BytesIO + ImageReader per embedded PNG, held alive in a local list until after canvas.save() returns — reportlab reads image data lazily, so a shared/GC'd buffer renders blank rather than erroring (T-58-09)"
    - "_resolve_assets_for_sheet: one $in query bounded by the request cap, then a caller-order walk (duplicates included) over the results — the no-silent-drop, order-preserving, duplicate-honouring bulk-resolve pattern any future ITAM bulk route should follow instead of asset_endpoints.py's ids[:500] truncation"

key-files:
  created:
    - backend/tests/test_itam_labels_sheet.py
    - backend/tests/test_itam_labels_sheet_route.py
  modified:
    - backend/itam_models.py
    - backend/itam_label_service.py
    - backend/itam_label_endpoints.py
    - backend/tests/test_itam_labels_offline.py

key-decisions:
  - "COL_PITCH set equal to LABEL_W (2.625in, edge-to-edge columns) instead of Avery's separately published 2.75in horizontal gutter pitch — see Deviations below, this is a Rule 1 bug auto-fix, not a plan choice"
  - "LabelSheetRequest.assetIds carries no Pydantic length constraint; both the empty-list and over-cap checks live in the route handler so both violations produce an explanatory 400 body instead of a bare 422"
  - "An over-length assetIds list is refused outright (400), never trimmed to MAX_LABEL_SHEET_ASSETS — deliberate departure from asset_endpoints.py's bulk_delete_assets_route ids[:500] truncation convention"
  - "Route-level tests split into test_itam_labels_sheet_route.py (plan-sanctioned fallback) to keep both test files under the CLAUDE.md 500-line cap"

patterns-established:
  - "Any future multi-asset bulk route in this codebase that must not silently drop caller input should model _resolve_assets_for_sheet's shape: one bounded $in query, then a caller-order/duplicate-preserving walk, with an explicit named-id-list 400 for anything that didn't resolve"

requirements-completed: [ITAM-CAT-05]

coverage:
  - id: D1
    description: "POST /api/assets/labels/sheet streams an Avery-5160 PDF label sheet (3x10 grid, US Letter) with QR, barcode, and human-readable tag/name/model text per label, honouring request order and duplicate ids"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_labels_sheet_route.py::TestSheetRoute"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_labels_sheet.py::TestLabelContent"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every drawn element (QR, barcode, all 3 text lines) provably lies inside its own Avery cell across all 30 grid positions; page counts are exact at every page-break boundary with no leading blank page"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_labels_sheet.py::TestSheetGeometry"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_labels_sheet.py::TestSheetPagination"
        status: pass
    human_judgment: false
  - id: D3
    description: "No request is ever partially served: empty list, over-cap list, unresolved ids, and untagged assets all produce a 400 naming exactly what was wrong; a cross-tenant id is indistinguishable in response shape from a fabricated id"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_labels_sheet_route.py::TestSheetRequestGuards"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_labels_sheet_route.py::TestSheetRbac"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_labels_sheet_route.py::TestSheetTenantIsolation"
        status: pass
    human_judgment: false
  - id: D4
    description: "generate_label_sheet_pdf (the third and last generator) completes successfully with socket.socket/create_connection/getaddrinfo raising unconditionally, discharging ROADMAP success criterion 3 across all three generators"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_labels_offline.py::TestOfflineGeneration::test_offline_network_blocked_label_sheet_pdf_generation_succeeds"
        status: pass
    human_judgment: false
  - id: D5
    description: "Avery 5160 physical print-alignment check (outer margin verified to better than a sixteenth of an inch)"
    human_judgment: true
    rationale: "The automated geometry test proves every drawn element sits inside the cell the code computes; only printing onto real Avery 5160 stock can prove the computed cell matches the physically printed one. Outstanding per 58-VALIDATION.md's Manual-Only Verifications table — not exercised this session."

duration: ~8min (task-commit span; excludes research/read time)
completed: 2026-08-05
status: complete
---

# Phase 58 Plan 04: Avery-5160 PDF Label Sheet Summary

**POST /api/assets/labels/sheet renders a printable Avery-5160 PDF (3x10 grid, QR + barcode + tag/name/model text per label) for a caller-ordered, duplicate-honouring list of asset ids, refusing every partial request outright rather than silently trimming or dropping it — completing all three label generators' offline proof and closing out Phase 58.**

## Performance

- **Duration:** ~8 min between task commits (22b72b2 → 2c11ddf)
- **Completed:** 2026-08-05
- **Tasks:** 3/3 completed
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- `generate_label_sheet_pdf` composes the existing `generate_qr_png`/`generate_barcode_png` (never re-implements either) onto a reportlab `canvas.Canvas`, one label per Avery 5160 cell, with a guarded page-break condition (`i > 0 and page_i == 0`) that never emits a leading blank page — verified exact at every boundary: 1→1, 29→1, 30→1, 31→2, 60→2, 61→3 pages
- `label_cell_origin`/`label_draw_boxes` proven, across all 30 grid positions, to keep every drawn element (QR image, barcode image, all 3 text lines) fully inside its own cell — the mitigation that stops a pathologically long asset name from bleeding into the neighbouring label (T-58-02), backed by `_fit_text`'s measured-width truncation rather than a fixed character budget
- D-01 (human-readable tag/name/model text) and D-03 (Avery-style fixed grid, not a uniform tiled grid) both realised and pinned by `extract_pdf_text`/`pdf_page_count` — hand-decoding reportlab's ASCII85+Flate content streams was necessary because a raw-byte membership check on drawn text silently returns `False` (the plan's own reportlab 5.0.0 pageCompression=1 warning, confirmed live)
- `POST /api/assets/labels/sheet`'s no-silent-drop contract: an empty list and an over-cap list both refuse outright (400) rather than serve a shorter sheet than requested; unresolved ids and untagged assets are each named explicitly in the 400 body (`unresolvedAssetIds`/`assetIdsMissingTag`); a cross-tenant id lands in `unresolvedAssetIds` with the identical response shape as a fabricated id (T-58-01)
- Third and final generator (`generate_label_sheet_pdf`) added to `test_itam_labels_offline.py`'s socket-blocked proof with a 31-asset sheet — the first call to exercise reportlab, Pillow's PNG encoder, python-barcode's font handling, and the qrcode renderer together with the network cut off, discharging ROADMAP success criterion 3 across all three generators rather than partially covering it

## Task Commits

1. **Task 1: Avery-5160 grid arithmetic and the PDF sheet generator** - `22b72b2` (feat)
2. **Task 2: POST /api/assets/labels/sheet with an explicit no-silent-drop contract** - `b26ffd8` (feat)
3. **Task 3: Complete the offline proof across all three generators** - `2c11ddf` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/itam_models.py` - Added `MAX_LABEL_SHEET_ASSETS = 500` and `LabelSheetRequest` (`assetIds: List[str]`, `extra="forbid"`), no length constraint (enforced in the handler for a 400 rather than 422). 227 lines.
- `backend/itam_label_service.py` - Added the Avery 5160 constant block, `label_cell_origin`, `label_draw_boxes`, `_fit_text`, `_label_text_or_blank`, and `generate_label_sheet_pdf`. 299 lines.
- `backend/itam_label_endpoints.py` - Added `_resolve_assets_for_sheet` and `POST /labels/sheet`; updated module docstring's route list and shadowing note. 244 lines.
- `backend/tests/test_itam_labels_sheet.py` - `extract_pdf_text`/`pdf_page_count` helpers, `TestSheetGeometry`, `TestSheetPagination`, `TestLabelContent`, `TestSheetInputGuards`. 19 tests, 191 lines.
- `backend/tests/test_itam_labels_sheet_route.py` - `TestSheetRoute`, `TestSheetRequestGuards`, `TestSheetRbac`, `TestSheetTenantIsolation` (split out per the plan's own 500-line fallback). 8 tests, 229 lines.
- `backend/tests/test_itam_labels_offline.py` - Extended `TestOfflineGeneration` with the third generator's socket-blocked proof (31-asset sheet). 1 new test.

## Decisions Made

- `_resolve_assets_for_sheet` queries once with `$in` over the de-duplicated id set, then walks the caller's original `assetIds` list in order (duplicates included) building the response — de-duplication is only for the query round trip; the rendered sheet always preserves both caller order and caller-requested duplicates.
- `MAX_LABEL_SHEET_ASSETS` violations are refused outright (400), never trimmed — a deliberate, code-commented departure from `asset_endpoints.py::bulk_delete_assets_route`'s `ids[:500]` convention, because silently serving a shorter sheet means the operator discovers the gap physically, at the shelf.
- Route-level tests moved into a second file (`test_itam_labels_sheet_route.py`) rather than inlined into `test_itam_labels_sheet.py`, per the plan's own pre-authorized fallback for the 500-line CLAUDE.md limit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] COL_PITCH corrected to LABEL_W (2.625in) instead of the plan's literal 2.75in**
- **Found during:** Task 1, geometry verification
- **Issue:** The plan's action text specifies both `LEFT_MARGIN = 0.3125 * inch` (explicitly derived in the plan's own comment as the "arithmetically reconciled `(8.5 - 3 * 2.625) / 2`") and `COL_PITCH = 2.75 * inch` (Avery's separately published horizontal gutter pitch). These two values are mutually inconsistent: the 0.3125in margin's derivation assumes edge-to-edge column packing (pitch == label width, no horizontal gutter), while 2.75in pitch assumes a 0.125in gutter between columns. Combined, the last column's right edge lands at `LEFT_MARGIN + 2*COL_PITCH + LABEL_W = 8.4375in`, which exceeds `PAGE_W - LEFT_MARGIN = 8.1875in` by 0.25in — directly violating the plan's own must-have truth ("Every cell ... lies fully inside the US Letter page ... x + LABEL_W <= PAGE_W - LEFT_MARGIN within a small tolerance").
- **Fix:** Set `COL_PITCH = LABEL_W` (2.625in), making the columns edge-to-edge and internally consistent with the reconciled `LEFT_MARGIN`. Verified: last column's right edge lands exactly at `PAGE_W - LEFT_MARGIN` (8.1875in), matching to zero tolerance. `ROW_PITCH = LABEL_H` (1.0in, no vertical gutter) was already internally consistent with `TOP_MARGIN` and needed no change.
- **Files modified:** `backend/itam_label_service.py`
- **Commit:** `22b72b2`
- **Note:** This is exactly the geometry the phase's one manual-only verification exists to catch — see below.

### Test-authoring correction (not a plan deviation)

- An early `Edit` call on `itam_models.py` matched only a substring of the target block, leaving the pre-existing `_validate_audited_at = field_validator(...)` line (belonging to `AuditMarkRequest`) sandwiched after the newly-inserted `LabelSheetRequest` class instead of before it, which broke Pydantic model construction (`PydanticUserError: Decorators defined with incorrect fields`). Caught immediately by re-running the acceptance-criteria import check; fixed by moving the validator line back to `AuditMarkRequest` before committing. No behavior change — this never reached a commit in the broken state.

## Issues Encountered

None beyond the deviation above.

## Outstanding Manual Verification

**Avery 5160 physical print-alignment check — still outstanding, per `58-VALIDATION.md`'s Manual-Only Verifications table.** The reconciled 0.3125in outer margin (see Deviations above) is the one figure the automated geometry test cannot validate: `TestSheetGeometry` proves every drawn element sits inside the *cell the code computes*, not that the computed cell matches the *cell Avery 5160 stock actually prints at*. Confirming that to better than a sixteenth of an inch requires printing `POST /api/assets/labels/sheet`'s output (31+ assets, to exercise both the page-break and all three grid columns) onto real Avery 5160 label stock — or holding a plain-paper print against a real sheet — and confirming the QR, the barcode, and all three text lines land inside each physical cell with no overlap and no drift across the sheet. Not exercised this session.

## Flagged Assumption (Concurrency)

Per the plan's Task 3 instruction, recorded here rather than backed by a test: `generate_label_sheet_pdf` and `_resolve_assets_for_sheet` issue no database write and no filesystem write, so two concurrent requests for the same asset cannot race each other. A sheet request overlapping an asset deletion resolves either to the pre-delete snapshot (if `_resolve_assets_for_sheet`'s `find` ran before the delete completed) or to a 400 naming that id under `unresolvedAssetIds` (if it ran after) — never to a partially written or corrupt PDF, since the PDF is assembled entirely in memory and only returned once complete. This reasoning is a backstop that follows from the read-only design of the whole label-sheet path, not from a concurrency test; it stops holding the moment a future phase adds caching or persistence to this path.

## User Setup Required
None - no external service configuration required.

## Phase 58 Completion

All 4 plans of Phase 58 (Asset Tags & Offline Labels) are now executed:
- **58-01:** `GET /api/assets/{asset_id}/label/qr` (QR tracer slice)
- **58-02:** `python-barcode==0.16.1` dependency pin
- **58-03:** `GET /api/assets/{asset_id}/label/barcode` (Code128) + offline proof for QR/barcode
- **58-04:** `POST /api/assets/labels/sheet` (Avery-5160 PDF) + offline proof for the PDF generator

**ROADMAP success criteria for Phase 58, confirmed end-to-end:**
1. QR + barcode generation for a single asset (D-02 bare-tag payload) — **met**, 58-01/58-03.
2. Printable PDF label sheet export for one or more assets, Avery-5160 grid (D-03), tag/name/model text (D-01) — **met**, 58-04.
3. Offline guarantee across all three generators, proven behaviorally with every socket entry point blocked — **met**, 58-03 (QR/barcode) + 58-04 (PDF sheet).

Requirement ITAM-CAT-05 is fully delivered by the backend; Phase 61 (Frontend ITAM Console) is the sole remaining consumer.

One item remains genuinely outstanding across the whole phase: the Avery 5160 physical print-alignment manual check (above), which no automated test in this or prior plans can discharge.

## Next Phase Readiness
- `itam_label_service.py` now holds all three pure, DB-free generators (`generate_qr_png`, `generate_barcode_png`, `generate_label_sheet_pdf`) with a byte-identical fail-loud `LabelEncodingError` contract across all three.
- `itam_label_endpoints.py`'s router carries all three routes registered on `router_registry.py`, ready for Phase 61's frontend console to call directly.
- Full backend suite (excluding the pre-existing `test_graphql.py` collection error): **1699 passed / 35 skipped / 3 pre-existing failures** (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — identical failure set to the pre-plan baseline (1671 passed), confirming no regression; the +28 passed count matches the 19 sheet-geometry/pagination/content tests + 8 sheet-route tests + 1 offline-proof test added this plan.

---
*Phase: 58-asset-tags-offline-labels*
*Completed: 2026-08-05*

## Self-Check: PASSED
All created files found on disk; all three task commit hashes (22b72b2, b26ffd8, 2c11ddf) found in git log.
