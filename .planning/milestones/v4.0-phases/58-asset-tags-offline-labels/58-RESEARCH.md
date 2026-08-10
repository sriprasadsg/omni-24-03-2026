# Phase 58: Asset Tags & Offline Labels - Research

**Researched:** 2026-08-05
**Domain:** FastAPI backend — offline QR/1D-barcode generation + fixed-grid PDF label sheets (reportlab). Backend/API-only (no frontend this phase).
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Label content):** Each label shows human-readable text alongside the codes — asset tag, asset name, and model — not just the QR/barcode. Reversibility: reversible — a rendering/layout choice, no stored data depends on it.

**D-02 (QR payload):** The QR code encodes the bare `assetTag` string (e.g. `ASSET-00001`), symmetric with the 1D barcode's payload — not a richer structured payload (no embedded tenant/asset id, no URL). Reversibility: reversible — any future scan-to-lookup flow just resolves the tag string; a richer payload can be layered on later without invalidating already-printed labels.

**D-03 (Print layout):** PDF label sheet uses a standard Avery-style fixed-grid layout (labels sized/positioned to match a common commercial label-sheet product), not a simple uniform grid tiled to the page. Reversibility: reversible — a layout/template choice in the PDF-generation code, no data model impact.

### Claude's Discretion

- Exact Avery product/dimensions to target — this research resolves it to **Avery 5160** (see Standard Stack / Architecture Patterns below).
- 1D barcode symbology — this research resolves it to **Code128** (alphanumeric-safe, matches `ASSET-00001`-shaped tags; EAN/UPC are numeric-only and don't fit).
- Label border/cut-lines, font sizing, exact PDF page margins — resolved in Architecture Patterns / Code Examples below (Avery 5160's own margins are not "discretion" — they're fixed by the physical product; discretion is limited to cosmetic choices like whether to draw a dashed cut-line).
- Bulk-selection API shape (query param list vs POST body) — this research resolves it to **POST body with a Pydantic model**, matching the existing `BulkUpdateAssetsRequest` convention in `backend/asset_endpoints.py` (see Architecture Patterns, Pattern 3).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope (per 58-CONTEXT.md).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITAM-CAT-05 | User can generate a printable QR + 1D barcode label (PDF label sheet) for an asset, fully offline (no external service or network call) | Standard Stack (`qrcode[pil]`, `python-barcode`, `reportlab` — all local-rendering, zero-network libraries), Pattern 1 (QR/barcode image generation), Pattern 2 (Avery 5160 fixed-grid PDF placement), Pattern 3 (bulk-selection endpoint shape), Common Pitfalls (offline verification, image-buffer lifetime), Code Examples, Validation Architecture (offline network-block test) |

</phase_requirements>

## Summary

Phase 58 is almost entirely disciplined reuse. Two of the three needed capabilities already have a working, already-installed precedent in this codebase: QR generation (`backend/mfa_service.py::generate_qr_base64` — `qrcode[pil]`, already a dependency) and reportlab-based PDF generation with tabular/paginated layout (`backend/compliance_reporting_pdf.py`, `backend/export_service_pdf.py`, `backend/compliance_automation_service.py`). The one genuinely new piece is 1D barcode generation, for which `python-barcode` is the correct, standard choice — it is pure-Python (no OS-level barcode renderer to install), already produces a PNG via its optional Pillow-backed `ImageWriter` (Pillow is already a dependency for `qrcode[pil]`), and its `Code128` symbology accepts the `ASSET-00001`-shaped alphanumeric tag string directly, unlike numeric-only symbologies (EAN/UPC).

The second genuinely new piece is *placing an image* into a reportlab-generated PDF — every existing reportlab usage in this codebase (`export_service_pdf.py`, `compliance_reporting_pdf.py`, `compliance_automation_service.py`, `payment_billing_endpoints.py`, `billing_endpoints.py`) generates tables/paragraphs only; none embeds a raster image. This is a first-time pattern for the codebase but a well-documented, low-risk one: wrap the QR/barcode PNG bytes in `reportlab.lib.utils.ImageReader(io.BytesIO(png_bytes))` and either place it via `canvas.drawImage(...)` (direct canvas API — recommended here, since Avery-grid label placement is exact-coordinate math, not flowing table content) or `reportlab.platypus.Image(...)` if a `SimpleDocTemplate`/flowable approach is preferred. Both are documented reportlab APIs, not homegrown code.

D-03 (Avery-style fixed-grid layout) is resolved to **Avery 5160** — 30 labels per sheet (3 columns × 10 rows), 1" × 2.625" each, on a standard US Letter (8.5"×11") sheet, with fixed margins (0.5" top/bottom, ~0.1875"/3.2mm gutter between columns) and zero vertical gap between rows. These are the single most common commercial address-label dimensions and the de facto default target for any "generic Avery label sheet" feature — confirmed against Avery's own product page. No maintained Python library ships these exact coordinates as an importable constant that's worth adding as a dependency (the one candidate, `pylabels2`, is a small, infrequently-updated niche package requiring Python ≥3.12 with no ready-made Avery-5160 preset baked in — see Alternatives Considered); the coordinates are simple, fixed, well-documented arithmetic, so hand-rolling them directly against reportlab (mirroring this codebase's existing direct-reportlab style, not adopting a new grid-layout abstraction) is the lower-risk, lower-dependency choice.

**Primary recommendation:** Add a new `backend/itam_label_service.py` (pure generation functions: QR PNG bytes, Code128 PNG bytes, Avery-5160 PDF sheet bytes — no FastAPI/DB imports, easy to unit-test in isolation) and a new `backend/itam_label_endpoints.py` router (RBAC-gated with the existing `_require_itam_admin` dependency, tenant-scoped asset lookups via `TenantIsolatedDatabase`), registered in `router_registry.py` immediately after `itam_lifecycle_endpoints`. Three routes: `GET /api/assets/{asset_id}/label/qr` (PNG), `GET /api/assets/{asset_id}/label/barcode` (PNG), `POST /api/assets/labels/sheet` (PDF, body `{"assetIds": [...]}, mirroring `BulkUpdateAssetsRequest`). Add exactly one new dependency, `python-barcode`, to `backend/requirements.txt`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| QR code image generation (bare `assetTag` payload) | API / Backend | — | Pure local rendering (`qrcode[pil]`), no network call, no persistence — computed on request |
| 1D barcode image generation (Code128, bare `assetTag` payload) | API / Backend | — | Same shape as QR — `python-barcode`'s `ImageWriter`, pure local rendering |
| Avery-grid PDF label sheet assembly (one or more assets) | API / Backend | Database / Storage | Backend composes the PDF from asset records fetched from `assets`; no separate "labels" collection — labels are a read-time rendering, never stored |
| Asset lookup / tenant scoping for label content | Database / Storage | API / Backend | Reuses `TenantIsolatedDatabase`/`TenantIsolatedCollection` exactly as `itam_asset_endpoints.py` does — no new isolation mechanism |
| RBAC gate (`manage:assets`) | API / Backend | — | Existing `_require_itam_admin` dependency in `itam_asset_endpoints.py`, reused verbatim |
| Offline guarantee (no external call) | API / Backend | — | Structural: every library involved (`qrcode`, `python-barcode`, `reportlab`, Pillow) is pure local computation with zero HTTP/socket client code paths — verified by grep of each library's source (see Common Pitfalls) and enforced by a dedicated network-blocked test (see Validation Architecture) |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `python-barcode` | PyPI | First released 2019-05-24 (0.10.0); current 0.16.1 `[VERIFIED: PyPI JSON API — pypi.org/pypi/python-barcode/json]` | Not resolvable via the automated seam (`weeklyDownloads: null`) — no pypistats figure obtained this session | `[VERIFIED: PyPI JSON API]` `project_urls.repository = "https://github.com/WhyNotHugo/python-barcode"` (confirmed present in PyPI's own metadata, contradicting the automated seam's `no-repository` signal — see note below) | **SUS** (per automated `package-legitimacy check` seam) | **Flagged — planner must add a `checkpoint:human-verify` task before this install.** |

**Automated seam output (verbatim):**
```json
{"name":"python-barcode","verdict":"SUS","signals":{"exists":true,"publishedAt":"2025-08-27T11:05:42.776490Z","weeklyDownloads":null,"repoUrl":null,"deprecated":false,"postinstall":null,"ecosystem":"pypi"},"reasons":["unknown-downloads","no-repository"]}
```

**Manual cross-check performed this session (for the human verifier's benefit — does not override the SUS disposition per protocol):** `curl https://pypi.org/pypi/python-barcode/json` shows `project_urls.repository = "https://github.com/WhyNotHugo/python-barcode"` — the seam's `no-repository` signal appears to be a detection gap (its heuristic likely checks a different metadata field than `project_urls`), not an actual absence of a source repo. The package: (a) has released continuously since 2019 (0.10.0 → 0.16.1, 6+ years), (b) is MIT licensed, (c) is classified `Development Status :: 5 - Production/Stable` in its own PyPI metadata, (d) has no `postinstall`/build script (`pip show`/wheel inspection confirms a pure-Python wheel with no `scripts.postinstall` equivalent — Python wheels don't have npm-style postinstall hooks at all), and (e) its GitHub org (`WhyNotHugo`) has an active release history and its own CI badge referenced in the README. **Despite this corroborating evidence, the disposition remains SUS per protocol** — the planner must still gate the `pip install python-barcode` step behind a `checkpoint:human-verify` task so a human explicitly confirms before it lands in `requirements.txt`.

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `python-barcode` — planner inserts `checkpoint:human-verify` before the install task.

**Verified installed already (no legitimacy check needed — confirmed present in `backend/requirements.txt` and already exercised in production code):**
- `qrcode[pil]>=7.4.2` `[VERIFIED: backend/requirements.txt:24]` — already used in `backend/mfa_service.py`.
- `Pillow>=12.2.0` `[VERIFIED: backend/requirements.txt:25]` — already a transitive/explicit dependency of `qrcode[pil]`; also needed by `python-barcode`'s optional `ImageWriter`.
- `reportlab>=4.0.0` `[VERIFIED: backend/requirements.txt:90]` — already used in 5+ backend modules.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `qrcode[pil]` | `>=7.4.2` (already pinned; installed) | QR code generation | Already the codebase's QR library (`mfa_service.py`); no reason to add a second QR library |
| `python-barcode` | `0.16.1` current on PyPI `[VERIFIED: pip index versions python-barcode — 2026-08-05]` — new dependency, gated by `checkpoint:human-verify` per Package Legitimacy Audit | 1D Code128 barcode generation | Pure-Python, MIT-licensed, no OS-level barcode renderer needed, PNG output via its Pillow-backed `ImageWriter` — the standard choice for barcode generation in Python (no serious competing library for Code128 specifically) |
| `reportlab` | `>=4.0.0` (already pinned; installed) | PDF label-sheet assembly (Avery-5160 fixed-grid layout) | Already the codebase's sole PDF library across every `*_pdf.py`/`*reporting*`/billing module; adding a second PDF library for one feature would be inconsistent |
| `Pillow` | `>=12.2.0` (already pinned; installed) | Backing image library for both `qrcode[pil]`'s and `python-barcode`'s `ImageWriter` | Already installed; both QR and barcode PNG rendering share it |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `reportlab.lib.utils.ImageReader` | (part of reportlab, already installed) | Wraps an in-memory PNG (`io.BytesIO`) so `canvas.drawImage`/`platypus.Image` can place it on a page | Needed for every QR/barcode image placed into the Avery-grid PDF — this is the first use of this reportlab submodule in the codebase (see Architecture Patterns, Pattern 2) |
| `pytest` + `pytest-asyncio` | already installed | Test framework for the new endpoint/service module | Matches `test_itam_foundation.py`/`test_itam_lifecycle.py` convention exactly |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled Avery-5160 coordinate math (recommended) | `pylabels2` (PyPI, MIT, requires Python ≥3.12) | `pylabels2` provides a generic label-sheet grid abstraction with reportlab-flowable rendering per label, but (a) it does not ship an out-of-the-box Avery-5160 preset — the exact coordinates still have to be supplied by the caller either way, (b) it is a small, low-adoption package (latest release Nov 2024, no subsequent update as of this research date) that would be this phase's *second* new dependency beyond what CONTEXT.md scoped (only `python-barcode` was named), and (c) it would need its own legitimacy audit and its own `checkpoint:human-verify` gate. Given the coordinate math is simple, fixed, and well-documented, hand-rolling directly against reportlab (already installed, already the codebase's PDF idiom) is lower-risk. `[ASSUMED — pylabels2's own PyPI page does not enumerate a bundled Avery-5160 template by name; this is training-knowledge + the PyPI metadata check performed this session, not a full read of its source]` |
| `python-barcode`'s Pillow-backed `ImageWriter` (PNG) | `python-barcode`'s default `SVGWriter` (no Pillow dependency) | SVG output avoids the Pillow dependency entirely, but reportlab's native image-placement APIs (`ImageReader`/`platypus.Image`) expect a raster format (PNG/JPEG) or a `PIL.Image` object — embedding SVG into a reportlab canvas requires an extra SVG-to-reportlab-graphics conversion step (e.g. `svglib`, itself a new dependency) with no clear benefit here since Pillow is already installed. PNG via `ImageWriter` is the lower-friction choice. |
| Bare `qrcode.QRCode` + `canvas.drawImage` per label | `reportlab.platypus.Image` flowable in a `Table` cell | Both are valid reportlab APIs; direct canvas placement (`canvas.drawImage(x, y, width, height)`) is recommended for the Avery grid specifically because label positions are fixed, absolute coordinates (not flowing content), which maps more naturally onto `canvas`'s coordinate-based drawing API than onto `platypus`'s flow-layout model. |

**Installation:**
```bash
# backend/requirements.txt — add this one line (gated by checkpoint:human-verify per Package Legitimacy Audit):
python-barcode>=0.16.1          # Code128 1D barcode generation for ITAM asset-tag labels (ITAM-CAT-05)

# No new install needed for qrcode[pil] / reportlab / Pillow — already present.
cd backend && venv/bin/pip install python-barcode>=0.16.1
```

**Version verification:** `pip index versions python-barcode` (run 2026-08-05) returned `0.16.1` as the newest available version, with a full history back to `0.8` — confirmed current and actively maintained. `[VERIFIED: pip index versions — PyPI registry]`

## Architecture Patterns

### System Architecture Diagram

```
Client (Phase 61 frontend, out of scope this phase)
        │
        │  GET /api/assets/{id}/label/qr        GET /api/assets/{id}/label/barcode
        │  POST /api/assets/labels/sheet {assetIds:[...]}
        ▼
┌──────────────────────────────────────────────────────────────┐
│ itam_label_endpoints.py (FastAPI router)                      │
│  - _require_itam_admin (RBAC: manage:assets) — reused         │
│  - resolve tenant_id from current_user                        │
│  - fetch asset doc(s) via TenantIsolatedDatabase.assets        │
│    (404 if asset not found / not in caller's tenant)           │
└───────────────┬────────────────────────────────────────────────┘
                │  asset dict(s): { assetTag, name, model, ... }
                ▼
┌──────────────────────────────────────────────────────────────┐
│ itam_label_service.py (pure functions — no DB/FastAPI import) │
│                                                                │
│  generate_qr_png(asset_tag: str) -> bytes                     │
│    qrcode.QRCode().add_data(asset_tag) → PIL Image → PNG bytes │
│                                                                │
│  generate_barcode_png(asset_tag: str) -> bytes                │
│    barcode.Code128(asset_tag, writer=ImageWriter()) → PNG bytes│
│                                                                │
│  generate_label_sheet_pdf(assets: list[dict]) -> bytes         │
│    for each asset: generate_qr_png + generate_barcode_png       │
│    → place at next Avery-5160 grid cell (3 cols × 10 rows)      │
│    → draw assetTag/name/model text alongside (D-01)             │
│    → new page every 30 labels                                   │
│    return reportlab canvas.getpdfdata()                         │
└───────────────┬────────────────────────────────────────────────┘
                │  PNG bytes / PDF bytes
                ▼
        StreamingResponse(io.BytesIO(data), media_type=..., Content-Disposition)
                │
                ▼
        Client receives image/png or application/pdf — no network call
        anywhere in this path (verified: Common Pitfalls + Validation Architecture)
```

### Recommended Project Structure
```
backend/
├── itam_label_service.py       # NEW — pure QR/barcode/PDF generation functions, no FastAPI/DB imports
├── itam_label_endpoints.py     # NEW — router: GET .../label/qr, GET .../label/barcode, POST /labels/sheet
├── itam_models.py              # EXTEND — add LabelSheetRequest(BaseModel) { assetIds: List[str] }
├── router_registry.py          # EXTEND — register itam_label_endpoints after itam_lifecycle_endpoints
├── requirements.txt            # EXTEND — add python-barcode>=0.16.1 (checkpoint:human-verify gated)
└── tests/
    └── test_itam_labels.py     # NEW — mirrors test_itam_lifecycle.py fixture/RBAC/tenant-isolation conventions
```

### Pattern 1: QR + Barcode PNG generation (pure functions, no side effects)
**What:** Two small, independently-testable functions that take a bare tag string and return PNG bytes.
**When to use:** Both the standalone QR/barcode endpoints and the label-sheet PDF assembly call these — single source of truth for "what does the QR/barcode actually encode" (D-02: bare `assetTag` string, nothing else).
**Example:**
```python
# Source: qrcode library API (already used identically in backend/mfa_service.py::generate_qr_base64)
# and python-barcode's documented codex.Code128 + writer.ImageWriter API
# (github.com/WhyNotHugo/python-barcode — barcode/codex.py, barcode/writer.py)
import io
import qrcode
import barcode
from barcode.writer import ImageWriter

def generate_qr_png(asset_tag: str) -> bytes:
    """Render `asset_tag` as a QR code PNG. Bare string payload per D-02 — no URL, no JSON."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(asset_tag)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_barcode_png(asset_tag: str) -> bytes:
    """Render `asset_tag` as a Code128 1D barcode PNG. Code128 accepts the full
    alphanumeric ASSET-00001-shaped tag; EAN/UPC would reject it (numeric-only)."""
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter(format="PNG")
    barcode_obj = code128(asset_tag, writer=writer)
    buf = io.BytesIO()
    barcode_obj.write(buf, options={"write_text": False})  # text drawn separately per D-01 layout
    return buf.getvalue()
```

### Pattern 2: Avery-5160 fixed-grid PDF placement (canvas-level, not flowable)
**What:** Direct `reportlab.pdfgen.canvas.Canvas` drawing at fixed Avery-5160 coordinates — 3 columns × 10 rows per US-Letter page, each label 1" tall × 2.625" wide.
**When to use:** For the `POST /api/assets/labels/sheet` endpoint. Avery-5160 exact dimensions (confirmed against Avery's own product page and cross-checked against two independent label-template sites): label size 2.625"×1" (w×h), top/bottom margin 0.5", left/right margin ~0.1875" (3 labels of 2.625" + 2 gutters of ~0.125"–0.19" ≈ 8.5" page width — exact gutter reconciles to (8.5 − 3×2.625)/2 = 0.3125" outer margin in the common 3-column layout, confirmed against the vertical pitch/horizontal pitch figures below), vertical pitch 1" (labels touch — 0 gap top-to-bottom), horizontal pitch 2.75" (0.125" gap between columns). `[CITED: avery.com/templates/5160]` `[CITED: techwalla.com — cross-check of the same figures]`
**Example:**
```python
# Source: Avery 5160 official spec (avery.com/templates/5160) — coordinates translated
# to reportlab's bottom-left-origin canvas coordinate system.
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
import io

PAGE_W, PAGE_H = letter  # 8.5in x 11in
LABEL_W, LABEL_H = 2.625 * inch, 1.0 * inch
COLS, ROWS = 3, 10
TOP_MARGIN = 0.5 * inch
LEFT_MARGIN = 0.3125 * inch          # reconciled outer margin for 3 columns of 2.625in each
COL_PITCH = 2.75 * inch              # column-to-column spacing (label + gutter)
ROW_PITCH = 1.0 * inch               # row-to-row spacing (no vertical gap on 5160)

def generate_label_sheet_pdf(assets: list[dict]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i, asset in enumerate(assets):
        page_i = i % (COLS * ROWS)
        if i > 0 and page_i == 0:
            c.showPage()
        col, row = page_i % COLS, page_i // COLS
        x = LEFT_MARGIN + col * COL_PITCH
        y = PAGE_H - TOP_MARGIN - (row + 1) * ROW_PITCH  # reportlab origin is bottom-left

        qr_png = generate_qr_png(asset["assetTag"])
        qr_img = ImageReader(io.BytesIO(qr_png))
        qr_size = 0.85 * inch
        c.drawImage(qr_img, x + 0.05 * inch, y + LABEL_H - qr_size - 0.05 * inch,
                    width=qr_size, height=qr_size, mask="auto")

        bc_png = generate_barcode_png(asset["assetTag"])
        bc_img = ImageReader(io.BytesIO(bc_png))
        c.drawImage(bc_img, x + qr_size + 0.1 * inch, y + 0.35 * inch,
                    width=LABEL_W - qr_size - 0.2 * inch, height=0.35 * inch,
                    preserveAspectRatio=True, mask="auto")

        # D-01: asset tag, name, model as human-readable text alongside the codes
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + 0.05 * inch, y + 0.2 * inch, asset["assetTag"])
        c.setFont("Helvetica", 6)
        c.drawString(x + 0.05 * inch, y + 0.1 * inch, str(asset.get("name", ""))[:28])
        c.drawString(x + 0.05 * inch, y + 0.02 * inch, str(asset.get("model", ""))[:28])
    c.save()
    return buf.getvalue()
```

### Pattern 3: Bulk-selection endpoint shape (resolves CONTEXT.md's Claude's Discretion item)
**What:** POST body with a Pydantic model carrying a list of asset ids — not query params.
**When to use:** `POST /api/assets/labels/sheet`. This mirrors the codebase's own established convention for "operate on N assets in one call," found in `backend/asset_endpoints.py::BulkUpdateAssetsRequest` (`POST /bulk-update`, body `{assetIds: List[str], updates: {...}}`) — the closest existing analog for "act on a list of asset ids." (`asset_endpoints.py::bulk_delete_assets_route` uses `Body(..., description=...)` with a bare `List[str]` for DELETE, but the POST convention with a named Pydantic model is the better match here since the label-sheet endpoint is a `POST`, not a `DELETE`.)
```python
# Source: backend/asset_endpoints.py:425-427 (BulkUpdateAssetsRequest) — same shape, new model
class LabelSheetRequest(BaseModel):
    assetIds: List[str]
    model_config = ConfigDict(extra="forbid")

@router.post("/labels/sheet")
async def generate_label_sheet(
    payload: LabelSheetRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    ...
```

### Anti-Patterns to Avoid
- **Encoding a richer QR/barcode payload (URL, JSON, tenant+asset composite id):** D-02 locks this to the bare `assetTag` string. A richer payload would also complicate the offline-verification story (a URL payload might *imply* a network call even if the QR generation itself doesn't make one, inviting confusion during audit/pen-test).
- **Persisting generated labels/PDFs to disk or a new collection:** Labels are a read-time rendering of existing asset data (assetTag/name/model), not a new stored artifact — generate on request and stream the response, matching `compliance_automation_endpoints.py::download_evidence_package`'s `StreamingResponse(io.BytesIO(...))` pattern exactly. No new collection, no filesystem writes.
- **Reaching for `pylabels2` (or any similar grid-abstraction library) as a second new dependency:** See Alternatives Considered — the coordinate math is simple and fixed; a second unaudited dependency for a thin abstraction over the same reportlab primitives is not worth the legitimacy-audit overhead.
- **Using `SVGWriter` (python-barcode's default) and trying to embed SVG into reportlab:** Requires an additional SVG→reportlab-graphics conversion dependency (e.g. `svglib`) for no benefit — use the Pillow-backed `ImageWriter` (PNG) instead, since Pillow is already installed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| QR code encoding/rendering | A custom QR matrix generator | `qrcode[pil]` (already installed, already used in `mfa_service.py`) | QR error-correction and module-matrix generation is a nontrivial spec (ISO/IEC 18004) — trivially gotten wrong (misaligned finder patterns, wrong error-correction level) and there's zero reason to reinvent it when a proven, already-vetted library is one import away |
| Code128 1D barcode encoding | A custom Code128 checksum/symbol-table implementation | `python-barcode` | Code128's symbol table + checksum algorithm is easy to get subtly wrong (checksum mistakes silently produce a barcode that *looks* right but scans as garbage) — this is exactly the kind of "deceptively simple, actually has sharp edges" problem worth a battle-tested library for |
| PDF page/coordinate layout | Raw PDF byte-stream construction | `reportlab` (already installed, already the codebase's PDF library) | Already established codebase convention — no reason to introduce a second PDF library or hand-write PDF syntax |

**Key insight:** The only place hand-rolling is actually correct in this phase is the Avery-5160 coordinate arithmetic itself (Pattern 2) — that's genuinely simple, fixed, well-documented geometry, not a "deceptively complex" problem, and pulling in a second dependency (`pylabels2`) for it would cost more in legitimacy-audit/maintenance overhead than it saves.

## Common Pitfalls

### Pitfall 1: Assuming "no visible HTTP call in this file" proves offline generation
**What goes wrong:** A reviewer eyeballs `itam_label_service.py`, sees no `requests`/`httpx` import, and assumes the offline requirement (ITAM-CAT-05 success criterion 3) is satisfied — but a transitive dependency could still make a network call (e.g. a font-fetching step, a telemetry ping in a library).
**Why it happens:** "No import of a network library in my file" is not the same guarantee as "no network call happens anywhere in the call graph."
**How to avoid:** Add a dedicated test that patches `socket.socket` (and/or `socket.create_connection`) to raise unconditionally, then calls `generate_qr_png`/`generate_barcode_png`/`generate_label_sheet_pdf` and asserts they succeed without raising — proving zero socket usage across the entire call graph, not just the top-level file. See Validation Architecture below for the concrete test shape. This repo has an existing *related* pattern (`backend/tests/test_ssrf_guards.py` patches `socket.getaddrinfo` to control DNS resolution for SSRF-guard tests) but no existing "prove nothing touches the network at all" test — this phase introduces that pattern for the first time.
**Warning signs:** A test that only asserts on the function's return value / HTTP status, with no network-blocking fixture around the call.

### Pitfall 2: In-memory PNG buffer reused/closed before reportlab reads it
**What goes wrong:** `ImageReader(io.BytesIO(png_bytes))` is lazy — if the underlying `BytesIO` is closed, garbage-collected early, or the same buffer object is reused/seeked back to 0 without re-wrapping across multiple `drawImage` calls, the image can silently render blank or raise a decode error partway through PDF assembly (especially notable when looping over dozens of labels).
**Why it happens:** `reportlab`'s `Canvas.drawImage` doesn't necessarily read the full image bytes at the moment `drawImage` is called — depending on internal caching, the buffer needs to remain valid at `canvas.save()` time.
**How to avoid:** Create one fresh `io.BytesIO`/`ImageReader` per QR/barcode image (as Pattern 2's example does — never share or reuse a single buffer object across labels), and keep references alive (e.g. in a local list) until `c.save()` returns if any doubt exists about reportlab's internal image caching behavior for the installed version.
**Warning signs:** Blank or corrupted images in the generated PDF, especially only on later pages/labels of a multi-page sheet (a lazy-read/premature-GC bug tends to manifest inconsistently, not on every label).

### Pitfall 3: Code128 encoding non-ASCII or empty `assetTag` values
**What goes wrong:** `python-barcode`'s `Code128` class raises on invalid character sets or empty strings — if a caller-supplied `assetTag` (recall `itam_asset_endpoints.py::create_manual_asset` allows a caller-supplied tag, not only auto-generated `IT-0001`-shaped ones) contains characters outside Code128's supported set, or is empty, barcode generation throws an unhandled exception that surfaces as a raw 500.
**Why it happens:** Asset tags are caller-suppliable strings (see `ManualAssetCreate.assetTag: Optional[str]`), not a closed enum — there's no existing validation constraining their character set beyond uniqueness-per-tenant.
**How to avoid:** Wrap barcode/QR generation in a try/except that returns a clear 4xx ("Asset tag contains characters that cannot be encoded as a barcode") rather than letting a library `BarcodeError` bubble up as a 500; validate/normalize before generation, not after a caller sees a stack trace.
**Warning signs:** A 500 (not 400) when generating a label for an asset whose tag has an unusual caller-supplied value.

### Pitfall 4: Off-by-one grid math dropping or overlapping labels across pages
**What goes wrong:** When the requested `assetIds` count isn't a multiple of 30 (Avery 5160's per-page capacity), naive modulo/floor-division math can either drop the last partial page or start overlapping labels onto positions from the previous page.
**Why it happens:** Grid-position calculation (`page_i = i % (COLS*ROWS)`, new page when `page_i == 0` and `i > 0`) is easy to get subtly wrong at the boundary (e.g. using `i % 30 == 0` unconditionally would incorrectly start a new blank page before placing the very first label, since `i == 0` also satisfies that).
**How to avoid:** Pattern 2's example guards the page-break condition with `i > 0 and page_i == 0` specifically to avoid an extra leading blank page — test explicitly with 1, 29, 30, 31, and 60 assets to cover the single-label, just-under-a-page, exactly-one-page, just-over-a-page, and exactly-two-page boundary cases.
**Warning signs:** An extra blank first page, or the 31st label overlapping the 1st label's position on page 2.

## Code Examples

Verified patterns from official/in-repo sources:

### Existing QR generation (already in production, reused verbatim for the tag-only case)
```python
# Source: backend/mfa_service.py:72-83 (existing, already-shipped code — same qrcode API this
# phase's generate_qr_png follows, minus the base64-encoding step which the new PNG-streaming
# endpoint doesn't need since it returns a StreamingResponse, not a JSON field)
def generate_qr_base64(uri: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
```

### Existing PDF-download streaming pattern (reuse exactly for the label-sheet endpoint)
```python
# Source: backend/compliance_automation_endpoints.py:115-132 (existing, already-shipped code)
@router.get("/evidence/package/{framework}")
async def download_evidence_package(framework: str, current_user = Depends(get_current_user)):
    pdf_data = await compliance_automation.generate_evidence_package(_tenant_id(current_user), framework)
    return StreamingResponse(
        io.BytesIO(pdf_data),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=compliance_evidence_{framework}.pdf"}
    )
# Phase 58's POST /api/assets/labels/sheet follows this exact shape:
# StreamingResponse(io.BytesIO(generate_label_sheet_pdf(assets)), media_type="application/pdf",
#                    headers={"Content-Disposition": "attachment; filename=asset-labels.pdf"})
```

### python-barcode Code128 generation (new for this phase)
```python
# Source: github.com/WhyNotHugo/python-barcode barcode/__init__.py::get / barcode/codex.py::Code128
# (verified by extracting the 0.16.1 wheel this session — see Sources)
import barcode
from barcode.writer import ImageWriter
code128_cls = barcode.get_barcode_class("code128")   # == barcode.codex.Code128
instance = code128_cls("ASSET-00001", writer=ImageWriter(format="PNG"))
with open("out.png", "wb") as f:
    instance.write(f, options={"write_text": False})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is new capability for the codebase | N/A | N/A | This phase introduces label generation from scratch; there is no prior/legacy approach in this codebase to migrate away from |

**Deprecated/outdated:** None identified — `qrcode`, `python-barcode`, and `reportlab` are all current, actively maintained libraries for their respective purposes.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pylabels2` does not ship a ready-made Avery-5160 coordinate preset out of the box (based on PyPI metadata review, not a full source read of the package) | Standard Stack — Alternatives Considered | Low — this claim only supports a "don't add this dependency" recommendation; if wrong (it does ship a preset), the only consequence is a slightly weaker case for hand-rolling, not an incorrect implementation, since hand-rolled Avery-5160 coordinates are correct either way (cross-checked against Avery's own site) |
| A2 | Avery 5160's precise gutter/outer-margin split (0.3125" per outer margin, reconciled from published width/pitch figures rather than found as a single explicit "outer margin" figure in one source) | Architecture Patterns — Pattern 2 | Medium — if Avery's actual outer margin differs slightly (e.g. some sources show 0.19"), printed labels could be marginally misaligned on real label stock; the planner should have the implementer add a "print a test page on plain paper and hold it up to a real Avery 5160 sheet" manual verification step before shipping, since sub-1/16" misalignment is only confirmable against physical label stock |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Exact Avery 5160 outer-margin figure**
   - What we know: Label size (2.625"×1"), 3×10 grid, vertical pitch 1" (no gap), horizontal pitch 2.75" (0.125" gap) are consistently reported across multiple sources.
   - What's unclear: The precise left/right outer margin (reconciled here to 0.3125" via `(8.5 - 3*2.625)/2`) wasn't found stated as a single authoritative figure in one place — different label-template sites present slightly different rounding.
   - Recommendation: Use the reconciled 0.3125" value (it's arithmetically exact given the other two widely-agreed figures); add a manual "print alignment check on real Avery 5160 stock" verification step to the plan rather than trusting the arithmetic blindly (see A2 above).

2. **Whether `python-barcode`'s SUS-flagged legitimacy should block or merely gate the phase**
   - What we know: The automated `package-legitimacy check` seam returned SUS due to `unknown-downloads`/`no-repository` signals; manual PyPI JSON API inspection this session found a repository URL and a 6-year release history that contradict the `no-repository` signal specifically.
   - What's unclear: Whether the seam's detection gap is a known limitation (e.g. it doesn't parse `project_urls`) or reflects something this session's manual check missed.
   - Recommendation: Per protocol, keep the SUS disposition and require a `checkpoint:human-verify` task before the `pip install` step lands in the plan — do not silently upgrade to OK based on this session's own manual cross-check.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | ✓ | 3.12.3 `[VERIFIED: python3 --version / backend/venv/bin/python --version]` | — |
| `qrcode[pil]` | QR generation | ✓ | `>=7.4.2` pinned, already installed (used by `mfa_service.py`) | — |
| `Pillow` | Image backend for QR + barcode | ✓ | `>=12.2.0` pinned, already installed | — |
| `reportlab` | PDF label-sheet assembly | ✓ | `>=4.0.0` pinned, already installed | — |
| `python-barcode` | Code128 barcode generation | ✗ (not yet in `requirements.txt`) | `0.16.1` available on PyPI `[VERIFIED: pip index versions]` | None viable — this is the one capability with no existing in-repo alternative; install is required, gated by `checkpoint:human-verify` per Package Legitimacy Audit |
| pytest / pytest-asyncio | Test suite | ✓ | already installed, exercised by `test_itam_foundation.py`/`test_itam_lifecycle.py` | — |

**Missing dependencies with no fallback:**
- `python-barcode` — must be installed (gated by `checkpoint:human-verify`); no equivalent library is already present in this codebase for Code128 generation.

**Missing dependencies with fallback:**
- None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`@pytest.mark.asyncio`), matching `test_itam_foundation.py`/`test_itam_lifecycle.py` |
| Config file | none — no `pytest.ini`/`pyproject.toml [tool.pytest]` section found in this repo (consistent with Phase 57's research finding) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_itam_labels.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests -q` (per project memory: use `backend/venv/bin/python`, NOT system Python) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-CAT-05 | `generate_qr_png(assetTag)` returns valid PNG bytes decodable back to the same string via a QR-decode round-trip (or, at minimum, non-empty valid-PNG-signature bytes if no decode library is available) | unit | `pytest backend/tests/test_itam_labels.py -k qr_generation -x` | ❌ Wave 0 |
| ITAM-CAT-05 | `generate_barcode_png(assetTag)` returns valid PNG bytes for a normal `ASSET-00001`-shaped tag | unit | `pytest backend/tests/test_itam_labels.py -k barcode_generation -x` | ❌ Wave 0 |
| ITAM-CAT-05 | Barcode generation on an empty or Code128-incompatible tag returns a 400, not a 500 (Pitfall 3) | unit | `pytest backend/tests/test_itam_labels.py -k barcode_invalid_tag -x` | ❌ Wave 0 |
| ITAM-CAT-05 | `POST /api/assets/labels/sheet` with 1, 29, 30, 31, 60 asset ids produces the correct page count and never drops/overlaps a label (Pitfall 4) | unit | `pytest backend/tests/test_itam_labels.py -k sheet_pagination -x` | ❌ Wave 0 |
| ITAM-CAT-05 (success criterion 3) | Generating a QR, a barcode, and a full label sheet succeeds with `socket.socket` patched to raise unconditionally — proves zero network calls anywhere in the generation call graph | unit | `pytest backend/tests/test_itam_labels.py -k offline_network_blocked -x` | ❌ Wave 0 |
| ITAM-CAT-05 | Label endpoints reject callers without `manage:assets` permission (403) | unit | `pytest backend/tests/test_itam_labels.py -k rbac -x` | ❌ Wave 0 |
| ITAM-CAT-05 | Requesting a label/sheet for an asset id belonging to another tenant returns 404, not another tenant's data | unit | `pytest backend/tests/test_itam_labels.py -k tenant_isolation -x` | ❌ Wave 0 |
| ITAM-CAT-05 (D-01) | Generated PDF's extracted text stream contains the asset's tag, name, and model (not just the codes) | unit | `pytest backend/tests/test_itam_labels.py -k label_content -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_itam_labels.py -q`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_itam_labels.py` — new file, covers all rows above; reuse the `MockTenantIsolatedDatabase`/`MockTenantIsolatedCollection` fixtures already present in `backend/tests/test_itam_foundation.py` (check for a promoted shared fixture in `conftest.py` before duplicating, per the same note in Phase 57's research).
- [ ] The offline-network-blocked test pattern (`socket.socket` patched to raise) is new to this codebase — no existing fixture to reuse; write it directly in `test_itam_labels.py` following Pitfall 1's guidance.
- [ ] Framework install: none — pytest/pytest-asyncio already installed.
- [ ] `python-barcode` install itself (gated by `checkpoint:human-verify`) is a Wave 0 prerequisite before any barcode-generation test can even import the module.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | `Depends(get_current_user)` via `_require_itam_admin` — unchanged, reused |
| V3 Session Management | no | No new session surface introduced |
| V4 Access Control | yes | `_require_itam_admin` (`manage:assets` permission) gates all three new routes; `TenantIsolatedDatabase` auto-scopes asset lookups to the caller's tenant |
| V5 Input Validation | yes | `LabelSheetRequest.assetIds: List[str]` validated by Pydantic + `ConfigDict(extra="forbid")`; barcode-incompatible/empty tag values caught and mapped to 400 (Pitfall 3), not left to raise a raw 500 |
| V6 Cryptography | no | No cryptographic operations in this phase — QR/barcode encoding is not a security control, it's a data-encoding format |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR — requesting a label/sheet for an `assetId` belonging to another tenant | Information Disclosure | `TenantIsolatedCollection` auto-injects `tenantId` into every `find_one`/`find` call on `db.assets` — a cross-tenant asset id resolves to "not found" (404), never another tenant's asset data. `[VERIFIED: backend/database.py:22-45]` |
| Barcode/QR payload injection — a caller-supplied `assetTag` containing control characters or an unexpectedly long string abused to break the PDF layout or crash generation | Tampering / Denial of Service | Wrap generation in try/except mapping library errors to 400 (Pitfall 3); truncate/clip name/model text fields drawn onto the label (Pattern 2's example truncates to 28 chars) so an unusually long asset name can't overflow into adjacent label cells |
| Unbounded `assetIds` list in `POST /labels/sheet` used to trigger excessive PDF generation (resource-exhaustion DoS) | Denial of Service | Cap `assetIds` length server-side (mirror `asset_endpoints.py::bulk_delete_assets_route`'s `ids = ids[:500]` cap) before generating the sheet — reject or truncate with a clear error rather than attempting to render an unbounded page count |
| Authorization bypass — a caller without `manage:assets` hits any of the three new routes directly | Elevation of Privilege | Reuse `_require_itam_admin` as a FastAPI `Depends` on every new route, verified via a dedicated 403 test per route |

## Sources

### Primary (HIGH confidence — verified via Read/grep of the actual codebase, or via authoritative registry APIs, this session)
- `backend/mfa_service.py` — existing `qrcode[pil]` QR-generation pattern (`generate_qr_base64`)
- `backend/itam_asset_endpoints.py` — `_require_itam_admin`, `next_asset_tag`, `ManualAssetCreate` usage, router registration comment/precedent
- `backend/itam_models.py` — `ManualAssetCreate.assetTag`, `LifecycleStatus`, discriminator constants
- `backend/router_registry.py` — actual registration order (`itam_catalog_endpoints` → `itam_asset_endpoints` → `itam_lifecycle_endpoints` → `asset_endpoints`)
- `backend/database.py` — `TenantIsolatedDatabase`/`TenantIsolatedCollection` mechanics and exemption allowlist
- `backend/export_service_pdf.py`, `backend/compliance_reporting_pdf.py`, `backend/compliance_automation_service.py` — existing reportlab PDF-generation conventions (page setup, style helpers, table styling)
- `backend/compliance_automation_endpoints.py:115-132` — `StreamingResponse(io.BytesIO(...), media_type="application/pdf", Content-Disposition)` download pattern, reused verbatim
- `backend/asset_endpoints.py:136-155,425-471` — existing bulk-operation endpoint conventions (`BulkUpdateAssetsRequest`, `ids[:500]` cap, tenant-scoped `$in` query)
- `backend/tests/test_ssrf_guards.py` — existing (related but distinct) network-mocking test pattern (`patch("integrations_v2.socket.getaddrinfo", ...)`), the closest in-repo precedent for the new offline-network-blocked test
- `backend/tests/test_itam_foundation.py` — `@pytest.mark.asyncio` usage and mock-fixture conventions
- PyPI JSON API (`pypi.org/pypi/python-barcode/json`) — package metadata, release history, `project_urls.repository` `[VERIFIED: PyPI registry, official]`
- `pip index versions python-barcode` — current version `0.16.1` `[VERIFIED: PyPI registry]`
- Direct extraction/inspection of the `python_barcode-0.16.1-py3-none-any.whl` wheel this session (`barcode/__init__.py`, `barcode/codex.py`, `barcode/writer.py`, `METADATA`) — confirmed MIT license, `Code128` class API, `ImageWriter` API, no postinstall scripts (wheels have no such mechanism) `[VERIFIED: direct wheel inspection]`
- `python-barcode` GitHub repository confirmed present at `github.com/WhyNotHugo/python-barcode` via PyPI's own `project_urls` metadata `[VERIFIED: PyPI JSON API]`

### Secondary (MEDIUM confidence — WebSearch cross-checked against an official source)
- Avery 5160 dimensions/margins/pitch — cross-checked across `avery.com/templates/5160` (official/vendor source) and independent label-template sites (techwalla.com, sheetstolabels.com) which agree on label size (1"×2.625"), grid (3×10=30/sheet), and pitch figures. `[CITED: avery.com/templates/5160]`
- `pylabels2` package metadata (PyPI page, requires-python ≥3.12, last release Nov 2024) — checked via PyPI JSON API this session. `[VERIFIED: PyPI registry for the metadata facts; ASSUMED for the "no bundled Avery-5160 preset" claim, since that required reading source not fetched this session]`

### Tertiary (LOW confidence — flagged for validation)
- The exact Avery 5160 outer-margin reconciliation (0.3125") — arithmetically derived, not found as a single stated figure; flagged in Open Questions / Assumptions Log for a physical-stock print-alignment check before shipping.
- `python-barcode`'s automated legitimacy verdict (SUS) — the seam's `no-repository`/`unknown-downloads` signals appear to reflect a detection gap rather than an actual absence, per this session's manual PyPI JSON API cross-check, but the SUS disposition is retained per protocol pending human verification.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every core library either already installed and verified via grep of production code (`qrcode[pil]`, `reportlab`, `Pillow`), or verified current via the PyPI registry directly (`python-barcode` 0.16.1)
- Architecture: HIGH — every pattern (RBAC gate, tenant isolation, streaming PDF response, bulk-endpoint shape) has a direct, already-shipped in-repo precedent; the two genuinely new pieces (barcode generation, image-embedding in reportlab) are both documented, mainstream library APIs, not novel engineering
- Pitfalls: MEDIUM-HIGH — Pitfalls 1-4 are grounded in concrete library-behavior facts (reportlab's lazy image reads, Code128's character-set constraints, page-break off-by-one arithmetic) rather than generic boilerplate, but none was reproduced with a failing test this session (research phase, not implementation)

**Research date:** 2026-08-05
**Valid until:** 2026-09-04 (30 days — stable domain: reportlab/qrcode/python-barcode release cadence is slow, Avery 5160's physical dimensions never change)
