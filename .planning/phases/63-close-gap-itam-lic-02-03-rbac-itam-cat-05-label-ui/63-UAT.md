---
status: testing
phase: 63-close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui
source: [63-01-SUMMARY.md, 63-02-SUMMARY.md]
started: 2026-08-11T11:25:50Z
updated: 2026-08-11T11:25:50Z
---

## Current Test

number: 4
name: Single shared _require_itam_admin gate (project-wide)
expected: |
  A grep across all backend/itam_*_endpoints.py files shows every router referencing the _require_itam_admin gate — no route left ungated.
awaiting: user response

## Tests

### 1. Non-admin gets 403 on every consumables route
expected: Non-admin authenticated user gets HTTP 403 from every route on itam_consumable_endpoints.py
result: pass
source: automated
coverage_id: D1

### 2. Non-admin gets 403 on every components route (both router objects)
expected: Non-admin authenticated user gets HTTP 403 from every route on itam_component_endpoints.py, on both the router and asset_components_router objects
result: pass
source: automated
coverage_id: D2

### 3. Admin behavior unchanged
expected: All 16 pre-existing consumable/component tests still pass unmodified (19 total with the 3 new RBAC tests)
result: pass
source: automated
coverage_id: D3

### 4. Single shared _require_itam_admin gate (project-wide)
expected: |
  All 8 backend/itam_*_endpoints.py router files reference the shared _require_itam_admin gate; consumable/component routers import rather than redefine it. Known caveat: itam_catalog_endpoints.py (pre-existing, Phase 56) still keeps its own local copy of the same check — functionally identical, already accepted as a documented risk in 63-VERIFICATION.md and 63-SECURITY.md. Confirm you're OK treating this the same way here.
result: [pending]

### 5. Label routes reachable from client code
expected: All three previously-unreachable Phase 58 label routes (QR, barcode, sheet) now have a client function reachable from rendered UI; no backend files touched
result: pass
source: automated
coverage_id: D2

### 6. Label row action — live browser download
expected: |
  Open the ITAM console's Lifecycle tab as an admin. Pick any asset row, click Label, then each of QR Code / Barcode / Label Sheet (this asset) in turn (reopening the menu between clicks — no preview or confirmation step, download starts immediately). Each downloads a real file using the backend's own filename (not a generic one); the QR/barcode files open as valid images and the PDF contains one label for that asset. Then open the menu once more and click elsewhere on the page — it closes.
result: [pending]

## Summary

total: 6
passed: 4
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
