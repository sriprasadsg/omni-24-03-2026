# Stack Research

**Domain:** ITAM (IT Asset Management) lifecycle features — Snipe-IT parity — added to an existing FastAPI + MongoDB + React security/compliance platform
**Researched:** 2026-08-04
**Confidence:** HIGH

This file covers ONLY the new v4.0 ITAM additions. It assumes the existing FastAPI (Python 3.12) + MongoDB (Motor async driver) + React/TypeScript frontend + `TenantIsolatedCollection`/`set_tenant_id`/`reset_tenant_id` tenant-isolation pattern + `backend/asset_endpoints.py` CMDB already in place — do not re-research or replace those. (Note: this file replaces the prior milestone's STACK.md, which covered an unrelated domain — v3.3 agent geo fleet map + VPN/ASN detection — and is now stale; that content is preserved in git history / the archived v3.3 milestone.)

## Recommended Stack

### Core Technologies

No new core technologies are needed. This milestone is additive endpoints/collections/UI on the existing stack. The only additions are **one new Python library** plus reuse of three libraries the project already has installed for an unrelated purpose (MFA QR codes, compliance PDF/Excel reports) — a strong signal this milestone needs zero new infrastructure.

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI + Motor + MongoDB | (existing, unchanged) | New ITAM collections/endpoints | Already the project's async data layer; every new ITAM collection (`asset_assignments`, `licenses`, `license_seats`, `consumables`, `accessories`, `components`, `manufacturers`, `asset_models`, `suppliers`, `locations`, `custom_fields`) is just a new Mongo collection behind the same `TenantIsolatedCollection` pattern — no new datastore justified for this scope |
| React/TypeScript (existing) | unchanged | ITAM UI (new AppView pages) | Follows the Phase 47/48 admin-gated nav pattern already established for the native security console: new `AppView` entries + `App.tsx` routes + `Sidebar` entries + permission gate |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-barcode` | **0.16.1** (confirmed live via PyPI JSON API `pypi.org/pypi/python-barcode/json`; `requires_python >=3.9`) — **the one genuinely new dependency this milestone needs** | Linear/1D barcode generation: Code128 (recommended default), Code39, EAN-13, EAN-8, UPC-A | Asset-tag labels that need a 1D barcode (many printed asset-tag labels and handheld scanners still expect Code128/Code39, not QR). Pure-Python for SVG output — zero extra deps; PNG raster output uses Pillow, which is **already installed** (`Pillow>=12.2.0` pinned, `12.3.0` in the venv) |
| `qrcode[pil]` | **already installed** — pinned `>=7.4.2` in `backend/requirements.txt`, venv currently has **8.2** | QR-code generation for asset tags/labels | **No new dependency.** Already used in `backend/mfa_service.py` for MFA-enrollment QR codes (`qrcode.QRCode(version=1, box_size=10, border=4)` → `.make_image()`). Reuse the identical call pattern for asset-tag QR payloads (e.g. a deep-link URL to the asset detail page, or a bare `{tenant_id}:{asset_tag}` string for fully air-gapped tenants with no reachable hostname) |
| `reportlab` | **already installed** — pinned `>=4.0.0`, venv currently has **5.0.0** | PDF label-sheet generation (multi-up asset-tag label sheets, e.g. Avery-style grids) | **No new dependency.** Already used for compliance PDF reports (`backend/compliance_reporting_pdf.py`, using `reportlab.platypus.SimpleDocTemplate`/`Table`/`TableStyle`). Reuse that exact flowable pattern: place a QR/barcode PNG as an `Image` flowable next to a `Paragraph` of the plain-text asset tag, inside a `Table` grid, laid out across pages |
| `Pillow` | **already installed** — pinned `>=12.2.0`, venv currently has **12.3.0** | Underlying raster support for both `qrcode[pil]` and `python-barcode`'s PNG writer | No action needed; `python-barcode` reuses the existing pin, no version bump required |
| `openpyxl` | **already installed** — pinned `>=3.1.0`, venv currently has **3.1.5** | Excel export of ITAM data (e.g. asset/license/consumable inventory exports) | Reuse for any ITAM-side "export to Excel" need, following `backend/compliance_reporting_excel.py`'s existing pattern — no new dependency |
| `python-dateutil` | verify presence (very likely already transitive via `pandas`); if absent, add `>=2.9.0` | Warranty-expiry date math, calendar-month depreciation-schedule stepping (`dateutil.relativedelta`) | Warranty-expiry alerts and month-based depreciation schedules need calendar-month arithmetic, not fixed 30-day deltas. `pandas>=2.1.0` (already pinned) depends on `python-dateutil` transitively, but relying on a transitive dependency for a module you `import` directly is fragile — add an explicit line to `requirements.txt` once `pip show python-dateutil` confirms it's present |
| *(none — hand-roll)* | n/a | Straight-line depreciation calculation | **Do not add a depreciation/accounting library.** Straight-line depreciation is `current_value = cost - (cost - salvage_floor) * (months_elapsed / months_total)`, clamped at the floor — roughly 10 lines of arithmetic. This is the exact formula Snipe-IT itself hand-rolls in `App\Models\Depreciable` (verified via Snipe-IT's own docs/issue tracker). A library would be over-engineering here, and PROJECT.md explicitly scopes this milestone to "straight-line at minimum" with "deep accounting/GL integration" and "multi-currency finance" out of scope |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pip show <pkg>` in `backend/venv` | Version verification during this research pass | Confirmed installed versions ahead of `requirements.txt` floor pins: reportlab 5.0.0, qrcode 8.2, Pillow 12.3.0, openpyxl 3.1.5, pandas 2.3.3 |
| PyPI JSON API (`pypi.org/pypi/<pkg>/json`) | Authoritative version + `requires_python` lookup for the one new dependency | Used directly (not via search snippet) to confirm `python-barcode` is 0.16.1, avoiding stale-cache search-result versions |

## Installation

```bash
# Only ONE new package needed — everything else is already installed
cd backend
pip install python-barcode==0.16.1

# Add to backend/requirements.txt, next to the existing qrcode/Pillow/reportlab block:
#   python-barcode>=0.16.0    # Code128/Code39 barcode generation for ITAM asset-tag labels

# Verify python-dateutil is present (likely already transitive via pandas — confirm, don't assume):
pip show python-dateutil || pip install "python-dateutil>=2.9.0"
```

No frontend package additions are required. QR/barcode images are generated server-side (PNG/SVG, or embedded directly into a server-rendered label-sheet PDF) and served as static image responses, base64 payloads, or PDF downloads — the React side renders an `<img>` or triggers a download, exactly like the existing compliance-report PDF/Excel flow.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| `python-barcode` (pure-Python) | `treepoem` (wraps Ghostscript/BWIPP) | Only if the project needed exotic symbologies (GS1-128, PDF417, Data Matrix) beyond Code128/Code39/EAN/UPC. Rejected: pulls in a Ghostscript **system binary** dependency, which is a heavier air-gapped packaging burden than a pure-Python library, for zero benefit at this milestone's scope |
| `qrcode[pil]` (already installed) | `segno` | `segno` is a more actively maintained, zero-dependency QR library with broader QR variants (Micro QR, structured append). Not worth the churn: the project already has a proven, working QR call-site (`mfa_service.py`); a second QR library for the same "encode a short string, render a PNG" job adds inconsistency for no functional gain |
| `reportlab` (already installed) for label PDFs | `weasyprint` (HTML/CSS-to-PDF) | Only if label layout needed complex CSS-driven design. Rejected: `weasyprint` requires system-level Cairo/Pango libraries — heavier air-gapped install footprint than pure-Python reportlab, and the project has an established, working reportlab pattern with zero existing weasyprint usage |
| Hand-rolled straight-line depreciation | A dedicated `depreciation`/accounting PyPI package | Only if the milestone scope included declining-balance, MACRS, or multi-schedule depreciation. PROJECT.md explicitly excludes "deep accounting/GL integration beyond basic depreciation" — a library would be premature for a formula this small |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Any cloud/SaaS QR or barcode generation API (e.g. goqr.me, QuickChart) | Violates the platform's offline-first/air-gapped constraint — asset-tag generation must work with zero network calls, including in fully air-gapped deployments | `qrcode[pil]` (already installed) + `python-barcode` (new, pure-Python) — both generate images entirely in-process, no network required |
| A message queue/broker (Celery, RabbitMQ, Redis Streams) for check-in/out or bulk label generation | Nothing in this milestone's scope needs async job processing. Check-in/out is a synchronous state transition on a Mongo document; even a batch label-sheet PDF for a few hundred assets is a sub-second synchronous reportlab call. The existing sync request/response FastAPI pattern (as used for compliance PDF/Excel export) is sufficient | Keep it synchronous: `POST /api/itam/assets/{id}/checkout` returns immediately; `POST /api/itam/labels/generate` streams the PDF directly in the response, matching `compliance_reporting_pdf.py`'s existing pattern |
| A separate/forked "ITAM asset" collection or model | PROJECT.md explicitly says reuse `assets`/`asset_endpoints.py`, don't fork it | Extend the existing `assets` collection with new optional fields (`asset_tag`, `status_label`, `assigned_to`, `purchase_cost`, `warranty_expires`, `depreciation`, etc.) plus a `source: "manual"` vs `source: "agent"` discriminator, so agent-auto-discovered and hand-catalogued assets share one collection and one detail view |
| A new ORM/schema library (SQLAlchemy, Beanie, ODMantic) | The codebase uses raw Motor + Pydantic request/response models throughout `asset_endpoints.py`; introducing an ODM for just the ITAM slice creates two data-access patterns in one family of files | Follow the existing pattern exactly: Pydantic `BaseModel` for request/response validation, raw `db["collection_name"]` Motor calls for persistence |
| `barcode` (unqualified PyPI package name — a different, stale/unrelated package) | Name-collision risk in `requirements.txt` | Always pin `python-barcode` explicitly as the **PyPI package name** (the `import barcode` statement at call sites is correct and expected — only the requirements-file package name differs) |

## Stack Patterns by Variant

**If asset tags need both a human-readable code and a machine-scannable code on one label (the default assumption for Snipe-IT parity):**
- Render the QR/barcode image via `qrcode[pil]`/`python-barcode`, place it as a reportlab `Image` flowable next to a `Paragraph` showing the plain-text asset tag, inside a `Table` grid (e.g. 3x8 cells per page for standard label sheets) — the same flowable/`Table` machinery already used for compliance PDF report tables

**If a label needs to deep-link into the app when scanned with a generic phone camera (not a dedicated barcode scanner):**
- Encode a URL in the QR payload (e.g. `https://<tenant-host>/itam/assets/{asset_tag}`) instead of a bare asset tag
- Fall back to bare-tag encoding for fully air-gapped deployments with no externally reachable hostname — make this configurable per tenant rather than hardcoded

**If check-out/check-in volume is low (typical for ITAM — dozens to low-hundreds of transactions/day, not high-frequency event streams):**
- A small `asset_assignments` collection (`asset_id`/`assigned_to`/`checked_out_at`/`checked_in_at`/`checked_out_by`) or an `assignment_history` sub-array on the asset document is sufficient — no event-sourcing or CQRS needed
- This mirrors the existing `status_history` pattern already used for compliance-status overrides (Phase 6 decision: immutable `status_history` with `changedBy`/`changedAt`/`previous_status`)

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `python-barcode==0.16.1` | `Pillow>=12.2.0` (already pinned), Python `>=3.9` | Project runs Python 3.12 — well within range. The SVG output path has zero image-library dependency; the PNG output path imports Pillow lazily |
| `qrcode[pil]>=7.4.2` (venv has 8.2) | `Pillow>=12.2.0` | Already validated in production via `mfa_service.py` — no compatibility risk adding a second call-site for a different payload |
| `reportlab>=4.0.0` (venv has 5.0.0) | Python 3.12, Pillow (for embedding raster images as flowables) | Already validated via `compliance_reporting_pdf.py`; embedding a `qrcode`/`python-barcode` PNG as a reportlab `Image` flowable is a standard, documented reportlab pattern |
| `python-dateutil>=2.9.0` (verify presence) | `pandas>=2.1.0,<3.0.0` (already pinned; pandas depends on `python-dateutil` transitively) | Very likely already present transitively — confirm with `pip show python-dateutil` before assuming, and add an explicit `requirements.txt` line once confirmed present, since a directly-`import`ed module should not rely on an unpinned transitive dependency |

## Integration Points with Existing `asset_endpoints.py` / Tenant Isolation

- **Tenant isolation is non-negotiable and project-wide, not per-feature.** Every new ITAM collection (`asset_assignments`, `licenses`, `license_seats`, `consumables`, `accessories`, `components`, `manufacturers`, `asset_models`, `suppliers`, `locations`, `custom_fields`) MUST go through the same `TenantIsolatedCollection` wrapper (`backend/database.py`) and the `set_tenant_id`/`reset_tenant_id` context pattern (`backend/tenant_context.py`). Every query in `asset_endpoints.py` already follows an `is_super_admin(current_user.role)` branch + `tenantId` filter pattern (see every `find_one`/`find`/`update_one`/`delete_one`/`delete_many` call in that file, plus the defense-in-depth `tenantId` filter on the delete/update paths) — new ITAM routers must replicate this exactly, not introduce a shortcut.
- **Extend the `assets` collection, don't fork it.** Add ITAM fields (`asset_tag`, `status_label`, `assigned_to`, `assigned_location`, `purchase_cost`, `po_number`, `supplier_id`, `warranty_expires`, `depreciation`, `manufacturer_id`, `model_id`, `category_id`, `custom_fields`) as optional keys on the existing document shape rather than a parallel `itam_assets` collection — this directly satisfies PROJECT.md's constraint. A `source` field (`"agent"` | `"manual"`) discriminates auto-discovered vs. hand-catalogued rows so `AssetManagementDashboard`/`AssetIntelligenceDashboard` can filter/badge without a schema fork, and so the manual-catalog creation path (required since ITAM assets are hand-entered, unlike the agent-auto-discovered inventory) writes into the same collection the security/observability CMDB already reads.
- **New router files, not one bloated `asset_endpoints.py`.** `asset_endpoints.py` is already ~500 lines — at the CLAUDE.md ceiling. New ITAM capability belongs in **new sibling router files**, each kept under 500 lines and mounted alongside the existing router in the FastAPI app, following the identical `APIRouter(prefix="/api/...", tags=[...])` + `Depends(get_database)` + `Depends(get_current_user)` construction already used:
  - `backend/asset_lifecycle_endpoints.py` — check-out/check-in, status-label transitions, assignment history (Cluster A)
  - `backend/asset_procurement_endpoints.py` — purchase cost/PO/supplier, warranty, depreciation schedule (Cluster B)
  - `backend/asset_catalog_endpoints.py` — manufacturers, models, categories, suppliers, locations, custom fields (Cluster C)
  - `backend/asset_labels_endpoints.py` — QR/barcode generation + label-sheet PDF export (part of Cluster C, split out because it's the one file that needs the `qrcode`/`python-barcode`/`reportlab` imports — keeps that dependency surface contained to a single ~200-line file rather than spreading image-generation code across catalog endpoints)
  - `backend/asset_licenses_endpoints.py` — license seats + accessories/consumables/components checkout with quantity tracking (Cluster D)
- **Cache invalidation.** `GET /api/assets` is `@cached(ttl=60, key_prefix="assets")`. Any lifecycle/assignment mutation (check-out, check-in, status change) must call `invalidate_cache("assets:*")` afterward — same as the existing `delete_asset`/`bulk_update_assets`/`set_asset_criticality` endpoints already do — otherwise a checked-out asset can show stale assignment state for up to 60 seconds.
- **Frontend nav.** New ITAM pages follow the Phase 47/48 admin-gated nav pattern PROJECT.md names explicitly: new `AppView` entries + `App.tsx` routes + `Sidebar` entries + permission gate, mirroring how `NativeSecurityConsole` was wired for the v3.4 native security console.

## Sources

- `backend/requirements.txt` (repo, read directly) — confirmed existing pins: `qrcode[pil]>=7.4.2`, `Pillow>=12.2.0`, `pandas>=2.1.0,<3.0.0`, `reportlab>=4.0.0`, `openpyxl>=3.1.0`, `jinja2>=3.1.0` — HIGH confidence (primary source, the actual repo)
- `backend/venv` `pip show` (executed directly, 2026-08-04) — confirmed installed versions: reportlab 5.0.0, qrcode 8.2, Pillow 12.3.0, openpyxl 3.1.5, pandas 2.3.3 — HIGH confidence (primary source, live environment)
- `backend/mfa_service.py` (repo, read directly) — confirmed existing QR-generation call-site to reuse as the pattern for asset-tag QR generation — HIGH confidence
- `backend/compliance_reporting_pdf.py` (repo, read directly) — confirmed existing reportlab usage pattern (`platypus.SimpleDocTemplate`, `Table`, `TableStyle`) to reuse for label-sheet PDF generation — HIGH confidence
- `backend/asset_endpoints.py` (repo, read directly, 501 lines) — confirmed the tenant-isolation query pattern (`is_super_admin` branch + `tenantId` filter) every new ITAM endpoint must replicate, and that the file is already at the CLAUDE.md 500-line ceiling, motivating new sibling router files — HIGH confidence
- PyPI JSON API (`https://pypi.org/pypi/python-barcode/json`, queried directly, 2026-08-04) — confirmed `python-barcode` latest version 0.16.1, `requires_python >=3.9` — HIGH confidence (primary source, live API)
- [python-barcode · PyPI](https://pypi.org/project/python-barcode/) — package overview, pure-Python + optional Pillow — MEDIUM confidence (web search corroboration of the PyPI API result)
- [Supported Formats — python-barcode docs](https://python-barcode.readthedocs.io/en/stable/supported-formats.html) — confirms Code128/Code39/EAN-13/EAN-8/UPC-A support — MEDIUM confidence
- [qrcode · PyPI](https://pypi.org/project/qrcode/) — confirms `qrcode` is actively maintained, Production/Stable, Python 3.9–3.13 — MEDIUM confidence
- [Depreciation Types — Snipe-IT Documentation](https://snipe-it.readme.io/docs/depreciation-types) — confirms the straight-line depreciation reference formula: `current_value = cost - (cost - floor) * (months_passed / months_total)` — MEDIUM confidence (vendor docs for the product this milestone targets parity with)
- [Depreciation Calculations · Issue #11822 · grokability/snipe-it](https://github.com/grokability/snipe-it/issues/11822) — corroborates that Snipe-IT's own depreciation math is hand-rolled, not library-driven — MEDIUM confidence

---
*Stack research for: ITAM (Snipe-IT-parity) lifecycle features on existing FastAPI+MongoDB+React platform (v4.0)*
*Researched: 2026-08-04*
