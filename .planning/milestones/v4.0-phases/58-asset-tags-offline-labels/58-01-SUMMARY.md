---
phase: 58-asset-tags-offline-labels
plan: 01
subsystem: api
tags: [qrcode, fastapi, itam, rbac, tenant-isolation]

requires:
  - phase: 56-catalog-foundation
    provides: "assetTag field on the assets collection, next_asset_tag helper"
  - phase: 57-lifecycle-checkinout
    provides: "_require_itam_admin RBAC dependency, router_registry.py registration pattern for itam_*_endpoints"
provides:
  - "GET /api/assets/{asset_id}/label/qr — streams a PNG QR code encoding an asset's bare assetTag"
  - "itam_label_service.generate_qr_png — pure, no FastAPI/DB import, unit-testable in isolation"
  - "itam_label_endpoints.py router registered in router_registry.py, ready for Plans 02-04 to extend with barcode/PDF-sheet routes"
affects: ["58-02-python-barcode-pin", "58-03-barcode-route", "58-04-label-sheet-pdf"]

tech-stack:
  added: []
  patterns:
    - "Pure-service module holding zero FastAPI/DB imports (itam_label_service.py), so generation functions stay unit-testable without an app or a DB — Plans 02-04 will follow the same shape for generate_barcode_png/generate_label_sheet_pdf"
    - "Typed LabelEncodingError (not bare Exception) raised by the service layer, mapped to 400 by the endpoint layer, unlike mfa_service.generate_qr_base64's silent except-Exception-return-empty-string convention"
    - "_safe_filename_part(value) sanitizes any caller-suppliable string before it reaches a Content-Disposition header — every future label route in this phase must reuse it"

key-files:
  created:
    - backend/itam_label_service.py
    - backend/itam_label_endpoints.py
    - backend/tests/itam_label_test_support.py
    - backend/tests/test_itam_labels.py
  modified:
    - backend/router_registry.py

key-decisions:
  - "generate_qr_png raises LabelEncodingError rather than mfa_service's silent except-Exception-return-empty-string, because a blank PNG served as if it succeeded would be printed and stuck on physical hardware"
  - "QR payload is the bare assetTag string per D-02 — no URL wrapping, no JSON, no tenant/asset id mixed in — pinned by a byte-identical reference-render test"

patterns-established:
  - "Label routes reuse _require_itam_admin from itam_asset_endpoints rather than redefining the manage:assets RBAC gate"
  - "Cross-tenant asset lookups return the identical 404 body/status as a genuinely unknown id, via the tenant-scoped db.assets.find_one — never leak asset existence across tenants"

requirements-completed: [ITAM-CAT-05]

coverage:
  - id: D1
    description: "GET /api/assets/{asset_id}/label/qr streams a PNG QR code for an asset within the caller's tenant"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_labels.py::TestQrLabelRouteEndToEnd::test_qr_generation_route_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "QR payload is the bare assetTag string (D-02), byte-pinned against a reference qrcode render, deterministic, and rejects empty/non-string tags"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_labels.py::TestQrPayloadFidelity"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cross-tenant, unauthorized, and untagged-asset requests fail closed with 404/403/400 respectively"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_labels.py::TestQrLabelMissingTag"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_labels.py::TestQrLabelRbac"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_labels.py::TestQrLabelTenantIsolation"
        status: pass
    human_judgment: false

duration: ~5min (task-commit span; excludes research/read time)
completed: 2026-08-05
status: complete
---

# Phase 58 Plan 01: QR Label Tracer Slice Summary

**GET /api/assets/{asset_id}/label/qr streams a PNG QR code of an asset's bare assetTag, RBAC-gated and tenant-isolated, through a newly registered router built on a pure, DB-free generation service.**

## Performance

- **Duration:** ~5 min between task commits (168787c → 3bd71af)
- **Completed:** 2026-08-05
- **Tasks:** 2/2 completed
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments
- End-to-end QR label slice: pure generation service → RBAC-gated tenant-scoped route → real router registration → ASGI test driving the actual route
- QR payload contract (D-02, bare `assetTag` string) byte-pinned against an independently built reference render, proving no URL/JSON wrapping
- Fail-closed boundary behavior for missing tag (400), unauthorized caller (403), and cross-tenant asset id (404, indistinguishable from an unknown id) all covered by passing tests
- Content-Disposition filename sanitization (T-58-05) verified against a tag containing header-control characters

## Task Commits

1. **Task 1: End-to-end "print a QR label for one asset"** - `168787c` (feat)
2. **Task 2: Harden the QR slice — payload fidelity, missing tag, RBAC, cross-tenant** - `3bd71af` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/itam_label_service.py` - Pure generation service: `generate_qr_png(asset_tag) -> bytes`, `LabelEncodingError`, `QR_BOX_SIZE`/`QR_BORDER` constants. No FastAPI/DB imports.
- `backend/itam_label_endpoints.py` - New router (`prefix="/api/assets"`, `tags=["ITAM Labels"]`) with `GET /{asset_id}/label/qr`, `_load_asset_for_label`, `_safe_filename_part`.
- `backend/router_registry.py` - Registers `itam_label_endpoints.router` immediately after `itam_lifecycle_endpoints.router` and before `asset_endpoints.router`.
- `backend/tests/itam_label_test_support.py` - `MockTenantIsolatedCollection`/`MockTenantIsolatedDatabase`, `mock_db`, `patch_label_get_database`, `label_app`, `tagged_asset()` fixtures (adapted from `itam_lifecycle_test_support.py`).
- `backend/tests/test_itam_labels.py` - `TestQrLabelRouteEndToEnd` (Task 1) plus `TestQrPayloadFidelity`, `TestQrLabelMissingTag`, `TestQrLabelRbac`, `TestQrLabelTenantIsolation` (Task 2); 11 tests, 190 lines (under the 500-line CLAUDE.md limit).

## Decisions Made
- `generate_qr_png` never swallows an exception (unlike `mfa_service.generate_qr_base64`'s `except Exception: return ""`) — raises the typed `LabelEncodingError` instead, so a failed render is always visible rather than silently producing a blank label.
- QR payload is the bare `assetTag` string per D-02 (locked in 58-CONTEXT.md), pinned by a byte-identical comparison against a reference render built independently in the test, plus a byte-different comparison against a URL-wrapped payload.

## Deviations from Plan

None - plan executed exactly as written. Two test-authoring corrections made during Task 2 verification (not deviations from the plan's intent, just fixing my own first-draft test bugs before committing):
- Cross-tenant tests initially used a static `AsyncMock(return_value=...)` on `mock_db.assets.find_one`, which ignored the tenant-injected filter and always returned the tenant-a document even when queried as tenant-b — switched to a `side_effect` that actually checks the filter's `tenantId`/`id`, matching the established pattern in `test_itam_foundation.py::test_manufacturer_cross_tenant_isolation`.
- The filename-sanitization assertion initially checked the entire `Content-Disposition` header string (which legitimately contains a space and semicolon in `attachment; filename=...`) instead of only the filename value — narrowed to check just the substring after `filename=`.
- Renamed the three `TestQrLabelTenantIsolation` test methods to include the literal substring `tenant_isolation` so the plan's own `-k tenant_isolation` verification command (acceptance criteria) selects them — pytest's `-k` is a substring match against the full node id, and the original names (`test_cross_tenant_...`) didn't contain that exact substring.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `itam_label_service.py`'s pure, DB-free shape is ready for Plans 03/04 to add `generate_barcode_png`/`generate_label_sheet_pdf` alongside `generate_qr_png` without introducing FastAPI/DB coupling.
- `itam_label_endpoints.py`'s router and `_safe_filename_part`/`_load_asset_for_label` helpers are ready for Plans 03/04 to add `GET /{asset_id}/label/barcode` and `POST /labels/sheet` on the same router.
- Plan 58-02 (python-barcode dependency pin) runs independently and touches no files this plan touched.
- Full backend suite: 1656 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — identical to the pre-plan baseline, confirming no regression.

---
*Phase: 58-asset-tags-offline-labels*
*Completed: 2026-08-05*

## Self-Check: PASSED
All created files found on disk; both task commit hashes (168787c, 3bd71af) found in git log.
