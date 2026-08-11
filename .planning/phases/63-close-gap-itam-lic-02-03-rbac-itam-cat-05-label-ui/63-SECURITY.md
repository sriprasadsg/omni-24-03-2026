---
phase: 63
slug: close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-11
---

# Phase 63 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| authenticated non-admin client → ITAM consumables/components API | Valid JWT crosses this boundary; authentication proven, authorization (role/permission) is what 63-01 adds. Frontend nav gate is NOT a boundary — client-side, trivially bypassed by calling the API directly. | ITAM sub-inventory records (consumables, components) |
| FastAPI route → tenant-isolated database handle | Already enforced via `TenantIsolatedDatabase`; unchanged by this phase. | Tenant-scoped asset/consumable/component documents |
| test harness → module registry (`sys.modules`) | Verification-integrity boundary — a stub applied to the wrong module object produces a passing test that proves nothing about the deployed dependency chain. | Test fixture patch target |
| browser client → ITAM label API | Crossed by three new `authFetch` calls added in 63-02. Authorization enforced server-side by `_require_itam_admin` on `itam_label_endpoints.py` (already correct since Phase 58); client adds no authorization logic. | Asset id → label file (QR/barcode/PDF) |
| backend response headers → browser filesystem | Server-supplied `Content-Disposition` value becomes an anchor `download` attribute — attacker-influenceable data reaching a file-write sink. | Filename string |
| in-memory blob → object URL | `URL.createObjectURL` allocates a document-lifetime handle that leaks unless explicitly revoked. | Label file blob |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-63-01 | Elevation of Privilege | `backend/itam_consumable_endpoints.py` — all 7 routes | high | mitigate | `Depends(_require_itam_admin)` on every route; proven by `TestConsumableRbac::test_rbac_denied_create_returns_403` | closed |
| T-63-02 | Elevation of Privilege | `backend/itam_component_endpoints.py` — `router` (create/list/attach/detach) | high | mitigate | Identical dependency swap on all 4 `router` routes; proven by `TestComponentRbac::test_rbac_denied_create_returns_403` | closed |
| T-63-03 | Elevation of Privilege | `backend/itam_component_endpoints.py` — `asset_components_router` (separately registered) | high | mitigate | Second router object explicitly gated + dedicated test `test_rbac_denied_list_asset_components_returns_403` | closed |
| T-63-04 | Information Disclosure | Read routes on both routers exposing tenant sub-inventory to any authenticated role | medium | mitigate | Same gate applied to GET routes, not just mutating ones — swap is per-route and unconditional | closed |
| T-63-05 | Tampering | Test fixture stubbed `verify_permission` on the wrong module object (`backend.itam_asset_endpoints` vs unprefixed `itam_asset_endpoints`) | high | mitigate | Fixture repointed to unprefixed module, matching `test_itam_component.py`/`test_itam_finance.py`; full suite re-run confirmed no other file had the mismatch | closed |
| T-63-06 | Elevation of Privilege | Drift risk — a second, locally redefined copy of `_require_itam_admin` diverging from the canonical one | medium | accept | `itam_catalog_endpoints.py` (pre-existing since Phase 56, outside this phase's `files_modified` scope) still defines its own local copy instead of importing the canonical one from `itam_asset_endpoints.py`. Functionally identical — same `verify_permission(current_user, "manage:assets")` check, same 403 behavior — so no live authorization gap exists today, but the single-source-of-truth guarantee this threat's mitigation plan called for does not hold project-wide. See Accepted Risks Log. | closed (accepted) |
| T-63-07 | Spoofing | Test using a super-admin role name would make the 403 assertion vacuous (`verify_permission` short-circuits to True for super-admin) | medium | mitigate | Tests pin `role="user"` explicitly and stub `verify_permission` to False, exercising the deny path directly | closed |
| T-63-08 | Tampering | Filename derived from `Content-Disposition` header, assigned to anchor `download` attribute in `triggerLabelDownload` | medium | mitigate | Parsed with `exportReport`'s bounded regex, quote-stripped; backend sanitizes the tag via `itam_label_endpoints._safe_filename_part` before it reaches the header; no client-side concatenation of user-controlled fields | closed |
| T-63-09 | Elevation of Privilege | Label action rendered for any user who can reach the Lifecycle tab | low | accept | UI visibility is not an authorization boundary — all 3 label routes gated by `_require_itam_admin` server-side (verified since Phase 58); non-admin gets 403 surfaced as an error toast | closed (accepted) |
| T-63-10 | Denial of Service | `POST /api/assets/labels/sheet` with a large `assetIds` array | low | accept | This UI always sends exactly one id (D-03); backend independently enforces `MAX_LABEL_SHEET_ASSETS` | closed (accepted) |
| T-63-11 | Information Disclosure | Requesting a label for an asset id belonging to another tenant | low | accept | Already mitigated server-side — `itam_label_endpoints._load_asset_for_label` reads through the tenant-isolated database handle; this UI only ever sends ids from the tenant-scoped `fetchAssets` response | closed (accepted) |
| T-63-12 | Denial of Service | Object URL / DOM leak — unrevoked blob URL or orphaned anchor per download | low | mitigate | `triggerLabelDownload` calls `window.URL.revokeObjectURL` and removes the anchor after `click()`, centralized in one helper for all 3 call sites | closed |
| T-63-13 | Repudiation | Failed label request silently doing nothing, leaving the operator unsure whether a label was produced | low | mitigate | Non-ok responses go through `itamThrow`; `handleLabelDownload` catches and raises an error toast with backend detail (tested) | closed |
| T-63-SC | Tampering | npm/pip/cargo installs (supply chain) | low | accept | Zero packages installed by either plan — Package Legitimacy Gate out of scope by its own trigger condition; no new dependency surface | closed (accepted) |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (`high`) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-63-01 | T-63-06 | `itam_catalog_endpoints.py`'s local `_require_itam_admin` redefinition predates Phase 63 (introduced Phase 56) and is functionally identical (same `manage:assets` check, same 403 behavior). Not in either plan's `files_modified` scope. Same deviation already accepted as a phase-verification override; tracked as a documented follow-up in `deferred-items.md` rather than fixed here to avoid unplanned scope expansion. | Sriprasad | 2026-08-11 |
| AR-63-02 | T-63-09 | UI visibility of the Label action is not an authorization boundary — all 3 backend label routes are independently gated by `_require_itam_admin`, verified since Phase 58. Duplicating the check client-side would add no security value. | 63-02-PLAN.md (plan-time acceptance) | 2026-08-11 |
| AR-63-03 | T-63-10 | This UI always sends exactly one asset id per label-sheet request (D-03); the backend independently enforces `MAX_LABEL_SHEET_ASSETS`, so no second client-side limit exists to drift out of sync. | 63-02-PLAN.md (plan-time acceptance) | 2026-08-11 |
| AR-63-04 | T-63-11 | Cross-tenant label requests are already blocked server-side via the tenant-isolated database handle in `itam_label_endpoints._load_asset_for_label`; this UI only ever sends ids already tenant-scoped by `fetchAssets`. | 63-02-PLAN.md (plan-time acceptance) | 2026-08-11 |
| AR-63-05 | T-63-SC | Zero packages installed by either plan in this phase — no new dependency/supply-chain surface introduced. | 63-01-PLAN.md / 63-02-PLAN.md (plan-time acceptance) | 2026-08-11 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-11 | 14 | 14 | 0 | Claude (gsd-secure-phase, register authored at plan time — L1 grep-depth) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-11
