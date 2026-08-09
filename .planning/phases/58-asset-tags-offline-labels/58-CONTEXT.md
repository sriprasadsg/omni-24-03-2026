# Phase 58: Asset Tags & Offline Labels - Context

**Gathered:** 2026-08-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Backend/API-only phase (frontend console is Phase 61 — do not build UI here, same precedent as Phase 57). Delivers printable asset-tag labels for the "physical identification" workflow (ITAM-CAT-05):

- Generate a QR code and a 1D barcode encoding an asset's `assetTag`.
- Export a printable PDF label sheet for one or more assets.
- All generation happens fully offline — no external service or network call, verified by testing with outbound network access blocked.

</domain>

<decisions>
## Implementation Decisions

### Label Content & Format
- **D-01:** Each label shows human-readable text alongside the codes — asset tag, asset name, and model — not just the QR/barcode. — **Reversibility:** reversible — a rendering/layout choice, no stored data depends on it.

### QR Payload
- **D-02:** The QR code encodes the bare `assetTag` string (e.g. `ASSET-00001`), symmetric with the 1D barcode's payload — not a richer structured payload (no embedded tenant/asset id, no URL). — **Reversibility:** reversible — any future scan-to-lookup flow just resolves the tag string; a richer payload can be layered on later without invalidating already-printed labels (a tag-string QR still round-trips through the same lookup).

### Print Layout
- **D-03:** PDF label sheet uses a standard Avery-style fixed-grid layout (labels sized/positioned to match a common commercial label-sheet product), not a simple uniform grid tiled to the page. — **Reversibility:** reversible — a layout/template choice in the PDF-generation code, no data model impact.

### Claude's Discretion
- Exact Avery product/dimensions to target (e.g. a common 30-per-sheet 1"×2.625" address-label size is a reasonable default) — pick during planning/research; no specific product was named by the user.
- 1D barcode symbology — Code128 is the natural choice (alphanumeric-safe, matches the `assetTag` format like `ASSET-00001`, unlike numeric-only symbologies such as UPC/EAN) — this follows from D-02's bare-tag-string framing but wasn't separately negotiated as a distinct question.
- Label border/cut-lines, font sizing, exact PDF page margins.
- Bulk-selection API shape (query param list vs POST body) for "one or more assets" per the ROADMAP success criteria.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase source of truth
- `.planning/ROADMAP.md` (Phase 58 section) — goal, success criteria, depends-on Phase 56
- `.planning/REQUIREMENTS.md` (ITAM-CAT-05) — locked requirement text
- `.planning/PROJECT.md` (Current Milestone: v4.0 ITAM section) — confirms Phase 61 is the sole frontend phase for this milestone; Phase 58 is backend/API-only, mirroring Phase 57's precedent; also names `python-barcode` as this phase's one new dependency

### Phase 56 foundation (must extend, not fork)
- `backend/itam_models.py` — `assetTag` field on `ManualAssetCreate`
- `backend/itam_asset_endpoints.py` — `next_asset_tag` helper (per-tenant unique tag generation), `_require_itam_admin` (manage:assets RBAC dependency)
- `.planning/phases/56-catalog-foundation/56-01-SUMMARY.md`, `56-02-SUMMARY.md` — asset-tag field origin and Phase 56 handoff notes

### Existing reusable patterns (analogs for this phase's two new capabilities)
- `backend/mfa_service.py` — existing `qrcode[pil]` usage (QR generation for MFA enrollment); same library already installed, reusable here for asset-tag QR codes
- `backend/compliance_reporting_pdf.py`, `backend/compliance_automation_service.py`, `backend/export_service_pdf.py` — existing `reportlab`-based PDF generation patterns (page layout, styles); reusable analog for the label-sheet PDF
- `backend/requirements.txt` — confirms `qrcode[pil]` and `reportlab` are already installed; `python-barcode` (1D barcode) is the one genuinely new dependency this phase needs

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `qrcode[pil]` (already installed, used in `backend/mfa_service.py`) — QR code generation, no new dependency needed.
- `reportlab` (already installed, used across several `*_pdf.py` / `*reporting*` modules) — PDF generation, no new dependency needed for the sheet layout itself.
- `next_asset_tag` / `assetTag` field (Phase 56/57 foundation) — the data being encoded into each label.
- `_require_itam_admin` (`backend/itam_asset_endpoints.py`) — manage:assets RBAC dependency; label-generation endpoint(s) should reuse this rather than defining a new gate.

### Established Patterns
- Backend/API-only phase pattern established in Phase 57 — Phase 61 is the sole frontend phase for the entire v4.0 ITAM milestone; Phase 58 follows the same boundary.
- Tenant isolation convention — labels must only be generatable for assets within the caller's tenant (via `TenantIsolatedDatabase`/`TenantIsolatedCollection`, per project-wide convention).

### Integration Points
- New label-generation endpoint(s) should extend the ITAM router family and follow the same `router_registry.py` registration pattern used in Phase 56/57.
- `python-barcode` is the one new dependency this phase introduces — needs a legitimacy/version check during research (per project convention for new package additions).
- No frontend integration this phase — Phase 61 is the only consumer of these endpoints from the UI side.

</code_context>

<specifics>
## Specific Ideas

No particular external product screenshots or examples were referenced. The Avery-style layout choice (D-03) is about physical print-sheet compatibility with commonly-stocked label stock, not a specific vendor requirement.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

### Reviewed Todos (not folded)
None — no pending todos matched this phase.

</deferred>

---

*Phase: 58-Asset Tags & Offline Labels*
*Context gathered: 2026-08-05*
