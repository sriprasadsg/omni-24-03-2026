---
phase: 63-close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui
verified: 2026-08-11T11:09:26Z
status: gaps_found
score: 10/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "All 8 backend/itam_*_endpoints.py router files gate on the single shared _require_itam_admin definition; none redefines it locally (ITAM-UI-01, D-05)."
    status: partial
    reason: "backend/itam_catalog_endpoints.py (line 63) defines its own local `async def _require_itam_admin(current_user: TokenData = Depends(get_current_user))` instead of importing the canonical one from itam_asset_endpoints.py. `grep -rn 'async def _require_itam_admin' backend/itam_*_endpoints.py` matches both itam_asset_endpoints.py:35 and itam_catalog_endpoints.py:63 — not a single project-wide definition. This predates Phase 63 (introduced in Phase 56, commit 1218c37) and is outside the files_modified scope of both 63-01 and 63-02. The 63-01-SUMMARY.md itself discloses this (coverage item D4, human_judgment: true) and backs it with .planning/phases/63.../deferred-items.md. Functionally it is not a live authorization gap — the local copy calls the identical verify_permission(current_user, 'manage:assets') check and still 403s non-admins — but the plan's own must_have literal text ('none redefines it locally') does not hold."
    artifacts:
      - path: "backend/itam_catalog_endpoints.py"
        issue: "Local redefinition of _require_itam_admin (line 63) instead of `from itam_asset_endpoints import _require_itam_admin`"
    missing:
      - "Replace itam_catalog_endpoints.py's local _require_itam_admin definition with an import from itam_asset_endpoints, matching the pattern this phase applied to itam_consumable_endpoints.py and itam_component_endpoints.py (already recommended as follow-up in deferred-items.md)."
---

# Phase 63: Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI Verification Report

**Phase Goal:** Both v4.0 milestone-audit BLOCKERs are closed — the consumables and components routers enforce the same `manage:assets` admin gate as every sibling ITAM router (non-admins receive 403 on all 12 routes across 3 router objects), and Phase 58's three offline label routes become reachable from the product through a Label action on each asset row in the ITAM Lifecycle table.
**Verified:** 2026-08-11T11:09:26Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Non-admin gets HTTP 403 from every route on `itam_consumable_endpoints.py` (7 routes) | ✓ VERIFIED | Direct code read of all 7 handlers confirms `current_user: TokenData = Depends(_require_itam_admin)` on every one (create/list/get/update/delete/checkout/checkin); `TestConsumableRbac::test_rbac_denied_create_returns_403` proves the dependency actually returns 403 for a `role="user"` token with `verify_permission` stubbed False. `grep -c '_require_itam_admin' backend/itam_consumable_endpoints.py` = 8 (1 import + 7 uses). `grep -c 'Depends(get_current_user)'` = 0. |
| 2 | Non-admin gets HTTP 403 from every route on `itam_component_endpoints.py`, both `router` and `asset_components_router` objects (5 routes) | ✓ VERIFIED | Direct code read confirms all 5 handlers (`list_asset_components_endpoint` on `asset_components_router`; `create_component_endpoint`, `list_components_endpoint`, `attach_component_endpoint`, `detach_component_endpoint` on `router`) use `Depends(_require_itam_admin)`. `TestComponentRbac` has one test per router object, both passing. `grep -c '_require_itam_admin'` = 6 (1 import + 5 uses). |
| 3 | Admin behavior unchanged — 16 pre-existing consumable/component tests pass unmodified | ✓ VERIFIED | `pytest tests/test_itam_consumable.py tests/test_itam_component.py -q` → `19 passed` (16 pre-existing + 3 new RBAC tests), run live during this verification. |
| 4 | 403 assertions are real, not harness artifacts (fixture patches the module the dependency actually resolves) | ✓ VERIFIED | `grep -c 'backend.itam_asset_endpoints' backend/tests/test_itam_consumable.py` = 0 (prefixed-module patch target removed); fixture now binds unprefixed `itam_asset_endpoints`, matching `test_itam_component.py`/`test_itam_finance.py`. |
| 5 | All 8 `backend/itam_*_endpoints.py` router files gate on the **single shared** `_require_itam_admin` definition; none redefines it locally | ✗ FAILED | `grep -rn 'async def _require_itam_admin' backend/itam_*_endpoints.py` returns **two** definitions: `itam_asset_endpoints.py:35` (canonical) and `itam_catalog_endpoints.py:63` (local redefinition, pre-existing since Phase 56). Functionally equivalent and still 403s non-admins, but the literal "none redefines it locally" claim is false. Disclosed by 63-01-SUMMARY.md itself (D4) and `deferred-items.md`. See Gaps Summary below. |
| 6 | Admin sees a Label action in each asset row, next to Check In / Check Out / Mark Audited | ✓ VERIFIED | `components/itam/LifecyclePanel.tsx:214-222` — `Label` button rendered per row inside the action cell, `aria-haspopup`/`aria-expanded` wired to `labelMenuAssetId === a.id`. |
| 7 | Clicking Label opens a menu with exactly 3 choices: QR Code, Barcode, single-asset label sheet | ✓ VERIFIED | `LifecyclePanel.tsx:223-229` — exactly 3 buttons (`QR Code`, `Barcode`, `Label Sheet (this asset)`). `grep -ci 'checkbox\|selectedAssetIds\|bulk'` = 0 (no multi-select). |
| 8 | Choosing any of the 3 immediately triggers a browser download, no preview/confirmation | ✓ VERIFIED (code) / see human check below | `triggerLabelDownload` (`services/apiService.ts:5302-5324`) calls `res.blob()` → creates object URL → detached anchor → `a.click()` → revoke, with no modal/confirmation step in between. `handleLabelDownload` dispatches directly on menu-item click. Automated tests (8/8) assert the fetch functions are called with correct args; jsdom cannot exercise a real browser download, so the actual file-lands-on-disk behavior is a documented human-check item (Task 3 of 63-02-PLAN.md) — see Human Verification below. |
| 9 | Each choice calls the correct backend route for that row's asset id; the sheet choice sends exactly that one id | ✓ VERIFIED | `fetchAssetQrLabel`/`fetchAssetBarcodeLabel` hit `/assets/{assetId}/label/qr` \| `/label/barcode`; `fetchAssetLabelSheet([assetId])` sends a single-element array to `POST /assets/labels/sheet`. Routes match `backend/itam_label_endpoints.py`'s registered paths exactly (`@router.get("/{asset_id}/label/qr")`, `.../label/barcode`, `@router.post("/labels/sheet")`), and both routers are mounted in `router_registry.py`. |
| 10 | Downloaded filename comes from backend response headers, not client-invented | ✓ VERIFIED | `triggerLabelDownload` parses `Content-Disposition` via the same bounded regex used by the pre-existing `exportReport`, falling back to a generic name only when the header is absent/unparseable. `grep -c 'Content-Disposition' services/apiService.ts` ≥ 3. |
| 11 | A failed label request surfaces a toast instead of a silent no-op or unhandled rejection | ✓ VERIFIED | `handleLabelDownload`'s try/catch calls `showToast(e?.message \|\| 'Failed to generate label.', 'error')`; covered by a passing test that makes a label fetch reject and asserts `showToast` was called with `'error'`. |

**Score:** 10/11 truths verified (1 failed, 0 present-but-behavior-unverified as a truth-level classification)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_consumable_endpoints.py` | Imports `_require_itam_admin`; zero bare-auth deps | ✓ VERIFIED | 123 lines, all 7 handlers gated, `get_current_user` import removed |
| `backend/itam_component_endpoints.py` | Same, across both router objects | ✓ VERIFIED | 95 lines, all 5 handlers (2 router objects) gated |
| `backend/tests/test_itam_consumable.py::TestConsumableRbac` | New 403 test class | ✓ VERIFIED | 1 test, passing |
| `backend/tests/test_itam_component.py::TestComponentRbac` | New 403 test class, 2 tests | ✓ VERIFIED | 2 tests (one per router object), passing |
| `services/apiService.ts` — `fetchAssetQrLabel`/`fetchAssetBarcodeLabel`/`fetchAssetLabelSheet`/`triggerLabelDownload` | 3 exported + 1 module-local helper | ✓ VERIFIED | All present at lines 5302-5344; helper not exported (`grep -c 'export const triggerLabelDownload'` = 0) |
| `components/itam/LifecyclePanel.tsx` | Label trigger, row-scoped menu, state, handler | ✓ VERIFIED | `labelMenuAssetId`, `labelMenuRef`, `handleLabelDownload` all present and wired; 283 lines (under 500-line limit) |
| `src/__tests__/LifecyclePanelLabels.test.tsx` | New vitest suite, 8 tests | ✓ VERIFIED | 8/8 passing, run live during this verification |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `itam_consumable_endpoints.py` handlers | `itam_asset_endpoints._require_itam_admin` | `Depends(_require_itam_admin)` import (not local redefinition) | ✓ WIRED | Confirmed by direct read; `grep -c 'async def _require_itam_admin' backend/itam_consumable_endpoints.py` = 0 |
| `itam_component_endpoints.py` handlers (both router objects) | `itam_asset_endpoints._require_itam_admin` | Same | ✓ WIRED | Confirmed by direct read |
| `test_itam_consumable.py::consumable_app` fixture | unprefixed `itam_asset_endpoints` module | `import itam_asset_endpoints` + `monkeypatch.setattr` | ✓ WIRED | `grep -c 'backend.itam_asset_endpoints'` = 0; fix verified |
| `LifecyclePanel` row action | `handleLabelDownload` → apiService label function → `authFetch` → backend `itam_label_endpoints` route | Direct call chain | ✓ WIRED | Traced end-to-end in code; route paths match backend registration |
| Backend `Content-Disposition` header | Parsed filename → anchor `download` attribute | `triggerLabelDownload` regex parse | ✓ WIRED | Confirmed in code |
| `LifecyclePanel` apiService import list | `vi.mock` factory in `LifecyclePanelLabels.test.tsx` | Import/mock sync | ✓ WIRED | Test suite imports and passes; no import-throw observed |

### Data-Flow Trace (Level 4)

Not applicable in the classic "renders DB-backed data" sense — this phase's artifacts are (a) an authorization gate (deterministic dependency injection, not data-flow) and (b) a client-triggered file download whose "data" is the backend response blob itself, traced above under Key Links. No hardcoded/static-fallback data source was found in either plan's artifacts.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Consumables + components RBAC suite | `cd backend && venv/bin/python -m pytest tests/test_itam_consumable.py tests/test_itam_component.py -q` | `19 passed` | ✓ PASS |
| Full backend regression | `cd backend && venv/bin/python -m pytest tests/ -q` | `3 failed, 1844 passed, 35 skipped` — same 3 pre-existing failures as documented baseline (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity`); zero ITAM failures | ✓ PASS (no regression) |
| Label UI test suite | `npx vitest run src/__tests__/LifecyclePanelLabels.test.tsx` | `8 passed` | ✓ PASS |
| Full frontend suite | `npx vitest run src/__tests__` | `184 passed`, 25 files, 0 failures | ✓ PASS (no regression) |
| Production build | `npm run build` | exit 0 | ✓ PASS |
| Single-definition invariant | `grep -rn 'async def _require_itam_admin' backend/itam_*_endpoints.py` | 2 matches (`itam_asset_endpoints.py`, `itam_catalog_endpoints.py`) | ✗ FAIL — see gap |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ITAM-LIC-02 | 63-01 | Admin can manage consumables with quantity-aware checkout | ✓ SATISFIED (RBAC gap closed) | All 7 routes gated; 403 test passing |
| ITAM-LIC-03 | 63-01 | Admin can attach components to a parent asset | ✓ SATISFIED (RBAC gap closed) | All 5 routes gated across both router objects; 2 403 tests passing |
| ITAM-UI-01 | 63-01 | API-layer admin gate matches console's admin-only intent | ⚠ PARTIAL | Consumables/components now match; `itam_catalog_endpoints.py`'s pre-existing local redefinition (Phase 56) means the "single shared gate" framing isn't literally true project-wide, though it is functionally equivalent |
| ITAM-CAT-05 | 63-02 | Printable QR/barcode label generation, offline, reachable by a user | ✓ SATISFIED (unreachable-UI gap closed) | Label action + 3-item menu wired to all 3 Phase 58 routes; 8/8 tests passing; live-browser download confirmation is an outstanding human-check item |

REQUIREMENTS.md itself notes "Phase 63 is not formally mapped in REQUIREMENTS.md" — this is expected for a gap-closure phase against the milestone audit rather than a v1-requirements phase; no orphaned-requirement issue.

### Anti-Patterns Found

None. Scanned all 7 files touched by this phase (`backend/itam_consumable_endpoints.py`, `backend/itam_component_endpoints.py`, `backend/tests/test_itam_consumable.py`, `backend/tests/test_itam_component.py`, `services/apiService.ts`, `components/itam/LifecyclePanel.tsx`, `src/__tests__/LifecyclePanelLabels.test.tsx`) for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/stub patterns — zero hits (the only `placeholder` matches are legitimate HTML `placeholder=` input attributes, not stub markers).

**Test-coverage note (non-blocking, from 63-REVIEW.md WR-01/WR-02):** `TestConsumableRbac` and `TestComponentRbac` each assert 403 on only 1-2 of the routes they cover, not every route individually — the docstrings slightly overstate per-route coverage. This is a regression-protection gap, not a functional gap: independent code inspection in this verification (see Truths 1-2 above) confirms every one of the 12 routes across 3 router objects genuinely uses `Depends(_require_itam_admin)` today. A future edit that touches only one route's dependency (e.g. a bad merge) would not be caught by today's test suite. Recommend adopting the code review's suggested parametrized-route test pattern in a follow-up.

## Human Verification Required

### 1. Live browser download confirmation (harvested from 63-02-PLAN.md Task 3 `<human-check>`)

**Test:** Sign in as an ITAM admin, open the ITAM console's Lifecycle tab, pick any asset row. Click `Label`, then each of `QR Code`, `Barcode`, `Label Sheet (this asset)` in turn (reopening the menu between clicks). Then open the menu once more and click elsewhere on the page.
**Expected:** Each of the three items downloads a real file with the backend's own filename (`asset-label-<tag>-qr.png`, `asset-label-<tag>-barcode.png`, `asset-labels.pdf`) — not a generic name — and the QR/barcode files open as valid images and the PDF contains one label for that asset. Clicking elsewhere closes the menu.
**Why human:** No automated harness in this codebase intercepts real browser file downloads (same accepted gap as the pre-existing `exportReport`/`downloadComplianceReport` functions); jsdom-based vitest can prove the correct fetch call was made and the correct blob-download code path was invoked, but not that a real file lands on disk with the correct name/content. 63-02-SUMMARY.md itself flags this as not yet exercised ("Outstanding: Task 3's manual browser human-check ... was not exercised in a live browser this session").

## Gaps Summary

One must-have from 63-01-PLAN.md's own frontmatter — a stricter, plan-added condition beyond the roadmap's literal goal text — does not hold: `backend/itam_catalog_endpoints.py` still defines its own local copy of `_require_itam_admin` (predating this phase, from Phase 56) rather than importing the canonical one from `itam_asset_endpoints.py`. This means the claim "all 8 ITAM router files gate on the single shared `_require_itam_admin` definition; none redefines it locally" is false as literally written — there are two definitions project-wide, not one.

This does **not** represent a live authorization/security gap: `itam_catalog_endpoints.py`'s local copy calls the identical `verify_permission(current_user, "manage:assets")` check and still returns 403 to non-admins. It is a single-source-of-truth / drift-risk finding (the plan's own threat register even names this exact risk class as T-63-06), not a broken access-control bug. It is outside both plans' `files_modified` scope, was proactively discovered and disclosed by the 63-01 executor (`deferred-items.md`, SUMMARY coverage item D4 with `human_judgment: true`), and is not addressed by any later phase in `ROADMAP.md`.

**This looks intentional / pre-existing, not a phase-63 regression.** To accept this deviation and close the phase without a follow-up plan, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "All 8 backend/itam_*_endpoints.py router files gate on the single shared _require_itam_admin definition; none redefines it locally (ITAM-UI-01, D-05)."
    reason: "itam_catalog_endpoints.py's local _require_itam_admin redefinition predates Phase 63 (introduced Phase 56) and is functionally identical (same manage:assets check, same 403 behavior). Not in either plan's files_modified scope. Tracked as a documented follow-up in deferred-items.md rather than fixed here to avoid unplanned scope expansion."
    accepted_by: "<name>"
    accepted_at: "<ISO timestamp>"
```

Alternatively, run a small follow-up plan to replace `itam_catalog_endpoints.py`'s local definition with `from itam_asset_endpoints import _require_itam_admin`, exactly mirroring what 63-01 did for consumables/components — this is a low-risk, well-scoped fix per the plan's own recommendation.

Separately, the live-browser download human-check from 63-02's Task 3 has not yet been performed and should be completed before considering ITAM-CAT-05 fully closed end-to-end (see Human Verification Required above).

Both of the milestone audit's two literal BLOCKER findings — the RBAC gap on consumables/components, and the unreachable label UI — are otherwise closed and independently confirmed via live test runs (19/19 backend ITAM tests, 1844/1844 non-pre-existing-failure backend tests, 184/184 frontend tests, clean production build) during this verification pass.

---

*Verified: 2026-08-11T11:09:26Z*
*Verifier: Claude (gsd-verifier)*
