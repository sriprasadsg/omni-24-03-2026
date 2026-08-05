---
phase: 58-asset-tags-offline-labels
plan: 03
subsystem: api
tags: [python-barcode, code128, fastapi, itam, rbac, tenant-isolation, offline-verification]

requires:
  - phase: 58-01
    provides: "itam_label_service.py/itam_label_endpoints.py scaffolding, generate_qr_png, LabelEncodingError, _load_asset_for_label, _safe_filename_part"
  - phase: 58-02
    provides: "python-barcode==0.16.1 pinned and installed into backend/venv"
provides:
  - "GET /api/assets/{asset_id}/label/barcode — streams a PNG Code128 barcode encoding an asset's bare assetTag"
  - "itam_label_service.generate_barcode_png — pure, no FastAPI/DB import, unit-testable in isolation, raises LabelEncodingError (never a 500) on empty/non-str/unencodable tags"
  - "Behavioral proof (not source inspection) that both QR and barcode generation complete with all socket entry points blocked — ROADMAP success criterion 3"
affects: ["58-04-label-sheet-pdf"]

tech-stack:
  added: []
  patterns:
    - "_resolve_tag_for_label(current_user, asset_id) shared prelude helper in itam_label_endpoints.py — tenant guard + asset load + tag extraction factored out of both the QR and barcode routes so they cannot drift apart in failure behavior; any future label route (Plan 04's sheet route) should call it too"
    - "block_all_sockets(monkeypatch) patches socket.socket/create_connection/getaddrinfo on the stdlib socket module itself (not a consumer's bound name) — catches network use anywhere in the call graph, including inside third-party libraries; guarded by a negative-control test that fails if the patching stops working"

key-files:
  created:
    - backend/tests/test_itam_labels_barcode.py
    - backend/tests/test_itam_labels_offline.py
  modified:
    - backend/itam_label_service.py
    - backend/itam_label_endpoints.py

key-decisions:
  - "generate_barcode_png catches barcode.errors.BarcodeError (plus ValueError/TypeError) narrowly and re-raises as LabelEncodingError chained with from exc — never catches bare Exception, so a genuine server fault still surfaces as a 500 while a bad tag never does"
  - "Unencodable-tag test fixture ('IT-000é') was chosen empirically by attempting generate_barcode_png against several non-ASCII/control-character candidates and keeping the first one that actually raised IllegalCharacterError, rather than hand-writing a character allowlist that could drift from the library's real accepted set"
  - "Shared _resolve_tag_for_label prelude extracted during this plan (not deferred) since the plan's action explicitly requires the QR and barcode routes to share tenant guard/asset-load/tag-extraction so they cannot diverge in failure behavior"

patterns-established:
  - "Any new label route (Plan 04's POST /labels/sheet) should call _resolve_tag_for_label for single-asset tag resolution, or a bulk analog of the same guard sequence for multi-asset requests"
  - "Any new offline-sensitive generator (Plan 04's generate_label_sheet_pdf) gets its socket-blocked proof added to test_itam_labels_offline.py's TestOfflineGeneration class alongside the QR/barcode tests, not a new file"

requirements-completed: [ITAM-CAT-05]

coverage:
  - id: D1
    description: "GET /api/assets/{asset_id}/label/barcode streams a PNG Code128 barcode for an asset within the caller's tenant"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_labels_barcode.py::TestBarcodeRouteEndToEnd::test_barcode_generation_route_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "Barcode payload is the bare assetTag string (D-02, symmetric with QR), deterministic, and rejects empty/non-string/unencodable tags via the typed LabelEncodingError rather than a library-native exception"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_labels_barcode.py::TestBarcodeGeneration"
        status: pass
    human_judgment: false
  - id: D3
    description: "Missing-tag and unencodable-tag cases return 400 (explicitly asserted not-500), cross-tenant/unknown asset ids return 404, unauthorized callers receive 403"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_labels_barcode.py::TestBarcodeInvalidTag"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_labels_barcode.py::TestBarcodeRbac"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_labels_barcode.py::TestBarcodeTenantIsolation"
        status: pass
    human_judgment: false
  - id: D4
    description: "Both generate_qr_png and generate_barcode_png complete successfully with socket.socket, socket.create_connection and socket.getaddrinfo raising unconditionally (ROADMAP success criterion 3, proven behaviorally over the whole call graph, guarded by a negative control)"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_labels_offline.py::TestOfflineGeneration"
        status: pass
    human_judgment: false

duration: ~15min (task-commit span; excludes research/read time)
completed: 2026-08-05
status: complete
---

# Phase 58 Plan 03: Code128 Barcode Route + Offline Proof Summary

**Added generate_barcode_png (Code128, python-barcode==0.16.1) and GET /api/assets/{asset_id}/label/barcode alongside the existing QR route, sharing one _resolve_tag_for_label prelude, then proved both generators complete with socket.socket/create_connection/getaddrinfo patched to raise unconditionally, backed by a verified negative control.**

## Performance

- **Duration:** ~15 min between task commits (df8d8d2 → 99d9c1f)
- **Completed:** 2026-08-05
- **Tasks:** 2/2 completed
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `generate_barcode_png(asset_tag) -> bytes` in `itam_label_service.py`: Code128 via `barcode.get_barcode_class("code128")` + `ImageWriter(format="PNG")`, `write_text=False`, catches `barcode.errors.BarcodeError`/`ValueError`/`TypeError` narrowly and re-raises `LabelEncodingError` (never bare `Exception`, so a real server fault still surfaces as 500)
- `GET /api/assets/{asset_id}/label/barcode` route, sharing tenant guard/asset-load/tag-extraction with the QR route via a new `_resolve_tag_for_label` helper (refactor applied to both routes, verified the QR route's own test suite still passes unchanged afterward)
- 12 new tests in `test_itam_labels_barcode.py`: PNG signature + determinism + 4 `LabelEncodingError` cases (empty/None/int/unencodable), 400-not-500 assertions for both invalid-tag paths, end-to-end 200+PNG+content-disposition, 403 RBAC, 404 cross-tenant isolation matching the unknown-id 404 byte-for-byte
- `test_itam_labels_offline.py`: `block_all_sockets(monkeypatch)` patches all three socket entry points on the stdlib `socket` module itself (not a consumer's bound name), proving `generate_qr_png` and `generate_barcode_png` both complete with the network cut off — this is the executable form of ROADMAP success criterion 3, satisfying the RESEARCH.md Pitfall 1 warning that "no import of a network library" is not the same guarantee as "no network call happens anywhere in the call graph"
- Negative control (`test_offline_network_blocked_negative_control_socket_really_blocked`) manually verified to fail when the patching is removed (observed: `Failed: DID NOT RAISE AssertionError`), then restored — recorded below per the plan's acceptance criteria

## Task Commits

1. **Task 1: Code128 barcode generation and its route** - `df8d8d2` (feat)
2. **Task 2: Prove generation works with all sockets blocked** - `99d9c1f` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/itam_label_service.py` - Added `import barcode`/`from barcode.errors import BarcodeError`/`from barcode.writer import ImageWriter`; `BARCODE_SYMBOLOGY = "code128"` constant; `generate_barcode_png(asset_tag) -> bytes`. 86 lines.
- `backend/itam_label_endpoints.py` - Imported `generate_barcode_png`; added `_resolve_tag_for_label` shared prelude; added `GET /{asset_id}/label/barcode`; updated the QR route to call the shared prelude; updated module docstring's route list. 131 lines.
- `backend/tests/test_itam_labels_barcode.py` - `TestBarcodeGeneration`, `TestBarcodeInvalidTag`, `TestBarcodeRouteEndToEnd`, `TestBarcodeRbac`, `TestBarcodeTenantIsolation`. 12 tests, 190 lines.
- `backend/tests/test_itam_labels_offline.py` - `block_all_sockets(monkeypatch)` helper, `TestOfflineGeneration` (3 tests: QR success, barcode success, negative control). 71 lines.

## Decisions Made
- `generate_barcode_png` catches `barcode.errors.BarcodeError` (Code128's `IllegalCharacterError` derives from it, confirmed via `IllegalCharacterError.__mro__`) plus `ValueError`/`TypeError`, never bare `Exception` — matches `generate_qr_png`'s existing fail-loud contract and keeps a genuine library/runtime bug distinguishable from a bad user-supplied tag.
- Chose `"IT-000é"` as the unencodable-tag test fixture by empirically running `generate_barcode_png` against several non-ASCII/control-character candidates at test-authoring time and keeping the one that actually raised (`IllegalCharacterError: not valid for Code 128: é`) — the library, not a hand-written allowlist, is the authority on what Code128 can encode (control characters like `\x00`/`\x01` were tried first and unexpectedly succeeded, confirming a hand-written allowlist would have been wrong here).
- `block_all_sockets` patches `socket.socket`/`socket.create_connection`/`socket.getaddrinfo` on the stdlib `socket` module object directly (not `itam_label_service.socket`, which doesn't even exist as a name) — this is the stricter pattern than `test_ssrf_guards.py`'s existing DNS-redirection pattern, since it must catch any consumer anywhere beneath, including inside `qrcode`, `python-barcode`, and Pillow.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. One extra verification step performed per the plan's own acceptance criteria: the negative-control test's patching was temporarily commented out, the test suite re-run to confirm the negative control genuinely fails without the patch (`FAILED ... Failed: DID NOT RAISE AssertionError`, 1 failed / 2 passed), then the file was restored from a scratchpad backup and re-verified green (3 passed).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `itam_label_service.py` now holds `generate_qr_png` and `generate_barcode_png` side by side, both pure/DB-free; Plan 04 adds `generate_label_sheet_pdf` alongside them following the same contract.
- `itam_label_endpoints.py`'s `_resolve_tag_for_label` prelude is ready for Plan 04's `POST /labels/sheet` to reuse for single-asset resolution, or to model a bulk analog on.
- `test_itam_labels_offline.py`'s `TestOfflineGeneration` class and `block_all_sockets` helper are ready for Plan 04 to extend with the label-sheet PDF generator's own socket-blocked proof (the third and last generator in this phase), per the comment left in the file.
- Full backend suite: 1671 passed / 35 skipped / 3 pre-existing failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — identical failure set to the pre-plan baseline (1656 passed at Plan 02), confirming no regression; the +15 passed count matches the 12 barcode tests + 3 offline tests added this plan.

---
*Phase: 58-asset-tags-offline-labels*
*Completed: 2026-08-05*

## Self-Check: PASSED
All created files found on disk; both task commit hashes (df8d8d2, 99d9c1f) found in git log.
