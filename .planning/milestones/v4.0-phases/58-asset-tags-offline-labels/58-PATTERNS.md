# Phase 58: Asset Tags & Offline Labels - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 6 (new) + 2 (extended)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/itam_label_service.py` | service (pure functions) | transform (bytes-in/bytes-out, no I/O) | `backend/mfa_service.py` (QR gen) + `backend/compliance_automation_service.py`/`export_service_pdf.py` (PDF gen) | role-match (composite — no single existing analog does QR+barcode+PDF together) |
| `backend/itam_label_endpoints.py` | route/controller | request-response (streaming file download) | `backend/itam_asset_endpoints.py` (RBAC/tenant/router shape) + `backend/compliance_automation_endpoints.py` (StreamingResponse PDF download) | exact (RBAC/router shape) / exact (streaming shape) |
| `backend/itam_models.py` (extend — `LabelSheetRequest`) | model | CRUD (request body) | `backend/asset_endpoints.py::BulkUpdateAssetsRequest` (line 425) | exact |
| `backend/router_registry.py` (extend) | config | request-response (route registration) | existing `_load(app, "itam_lifecycle_endpoints", "router")` line (router_registry.py:84) | exact |
| `backend/requirements.txt` (extend) | config | — | existing dependency-pin lines (`qrcode[pil]`, `reportlab`) | exact |
| `backend/tests/test_itam_labels.py` | test | request-response / unit | `backend/tests/test_itam_foundation.py` (fixtures/RBAC/tenant-isolation conventions) + `backend/tests/test_ssrf_guards.py` (socket-mocking pattern, for the new offline-network-blocked test) | exact (fixtures) / partial (network-block is new to this codebase) |

## Pattern Assignments

### `backend/itam_label_service.py` (service, transform — pure, no FastAPI/DB imports)

**Analog 1 (QR generation):** `backend/mfa_service.py`

**Imports pattern** (lines 1-19):
```python
import pyotp
import qrcode
import io
import base64
import secrets
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import get_database
```
For `itam_label_service.py`, mirror the same shape but keep it deliberately narrower — no `database`/`pyotp` imports since this module must stay pure (no FastAPI/DB imports, per RESEARCH.md's architecture map):
```python
import io
import qrcode
import barcode
from barcode.writer import ImageWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
```

**Core QR pattern** (`mfa_service.py:72-83`, `generate_qr_base64`):
```python
def generate_qr_base64(uri: str) -> str:
    """Render the OTP URI as a base64-encoded PNG QR code."""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""  # Frontend falls back to showing the raw URI
```
Copy this pattern verbatim for `generate_qr_png(asset_tag: str) -> bytes` — same `QRCode(version=1, box_size=10, border=4)` params, same `io.BytesIO()`/`.save(..., format="PNG")` idiom, but return raw PNG bytes (no base64) since the new endpoint streams PNG directly rather than embedding it in JSON. Per D-02, `add_data(asset_tag)` gets the bare tag string only — no URI wrapping.

**Error-handling difference to apply (Pitfall 3):** unlike `mfa_service.py`'s silent `except Exception: return ""`, `itam_label_service.py`'s barcode function must raise a typed/catchable exception (or let `barcode`'s own exception propagate) so `itam_label_endpoints.py` can map it to a 400, not swallow it — MFA's silent-failure convention is wrong for this use case since a blank/failed barcode PNG must never be silently served as if it succeeded.

**Analog 2 (PDF generation with page/layout structure):** `backend/compliance_automation_service.py`, `backend/export_service_pdf.py`, `backend/compliance_reporting_pdf.py` (all reportlab-based; none embeds a raster image — first use of `ImageReader`/`canvas.drawImage` in this codebase, per RESEARCH.md). Use RESEARCH.md's Pattern 2 code example directly (already verified against Avery 5160 official spec) — reproduced here for convenience:
```python
PAGE_W, PAGE_H = letter
LABEL_W, LABEL_H = 2.625 * inch, 1.0 * inch
COLS, ROWS = 3, 10
TOP_MARGIN = 0.5 * inch
LEFT_MARGIN = 0.3125 * inch
COL_PITCH = 2.75 * inch
ROW_PITCH = 1.0 * inch

def generate_label_sheet_pdf(assets: list[dict]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i, asset in enumerate(assets):
        page_i = i % (COLS * ROWS)
        if i > 0 and page_i == 0:
            c.showPage()
        col, row = page_i % COLS, page_i // COLS
        x = LEFT_MARGIN + col * COL_PITCH
        y = PAGE_H - TOP_MARGIN - (row + 1) * ROW_PITCH
        # ... draw QR/barcode images + text, see RESEARCH.md Pattern 2 for full body
    c.save()
    return buf.getvalue()
```
Guard the page-break condition with `i > 0 and page_i == 0` (Pitfall 4) — do not use a bare `i % 30 == 0`.

**Barcode pattern (new to codebase — no in-repo analog, use library API directly):**
```python
def generate_barcode_png(asset_tag: str) -> bytes:
    if not asset_tag:
        raise ValueError("assetTag must be non-empty for barcode generation")
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter(format="PNG")
    barcode_obj = code128(asset_tag, writer=writer)
    buf = io.BytesIO()
    barcode_obj.write(buf, options={"write_text": False})
    return buf.getvalue()
```

---

### `backend/itam_label_endpoints.py` (controller, request-response — streaming file download)

**Analog 1 (RBAC + tenant + router shape):** `backend/itam_asset_endpoints.py`

**Imports pattern** (lines 1-16):
```python
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from itam_models import ManualAssetCreate, ASSET_SOURCE_MANUAL, DEFAULT_LIFECYCLE_STATUS, ASSET_TAG_PREFIX
from itam_catalog_service import collect_field_defs, validate_custom_field_values
from cache_service import invalidate_cache
from rbac_utils import verify_permission
```
For `itam_label_endpoints.py`, drop the catalog/cache imports (not needed) and add `StreamingResponse` + `io` + the new service module:
```python
import io
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from auth_types import TokenData
from authentication_service import get_current_user
from database import TenantIsolatedDatabase
from itam_label_service import generate_qr_png, generate_barcode_png, generate_label_sheet_pdf
from rbac_utils import verify_permission
```

**RBAC gate pattern** (`itam_asset_endpoints.py:35-43`):
```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'manage:assets' permission.
    """
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to manage ITAM assets."
        )
    return current_user
```
Import and reuse this dependency directly (do not redefine it) — `itam_label_endpoints.py` should `from itam_asset_endpoints import _require_itam_admin`.

**Router declaration and prefix-sharing precedent** (`itam_asset_endpoints.py:20-29`):
```python
router = APIRouter(prefix="/api/assets", tags=["ITAM Assets"])

# WR-04 (57-REVIEW): This router shares the /api/assets prefix with
# backend/asset_endpoints.py. ...
```
Follow the same commenting convention — new file shares `/api/assets` prefix; note in a header comment which routes are added (`/{asset_id}/label/qr`, `/{asset_id}/label/barcode`, `/labels/sheet`) and confirm no path collides with `asset_endpoints.py` or `itam_lifecycle_endpoints.py`.

**Analog 2 (streaming PDF/binary download):** `backend/compliance_automation_endpoints.py:115-132`
```python
@router.get("/evidence/package/{framework}")
async def download_evidence_package(framework: str, current_user = Depends(get_current_user)):
    """Download evidence package as PDF"""
    pdf_data = await compliance_automation.generate_evidence_package(
        _tenant_id(current_user), framework
    )
    return StreamingResponse(
        io.BytesIO(pdf_data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=compliance_evidence_{framework}.pdf"
        }
    )
```
Reuse verbatim for all three new routes — swap `media_type="image/png"` for the two GET routes and `application/pdf` for the sheet route; swap the DB-service call for `generate_qr_png`/`generate_barcode_png`/`generate_label_sheet_pdf`.

**Tenant-scoped asset lookup pattern** (mirrors `TenantIsolatedDatabase` usage in `itam_asset_endpoints.py:46-55`, `next_asset_tag`):
```python
async def next_asset_tag(db: TenantIsolatedDatabase, tenant_id: str, prefix: str = ASSET_TAG_PREFIX) -> str:
    counter_doc = await db.counters.find_one_and_update(
        {"tenantId": tenant_id, "name": "asset_tag"},
        {"$inc": {"seq": 1}},
        ...
```
For the label endpoints, use `db.assets.find_one({"id": asset_id})` via `TenantIsolatedDatabase` (auto-injects `tenantId`) — a cross-tenant `asset_id` naturally resolves to `None` → raise `HTTPException(404)`, never leak another tenant's asset (per RESEARCH.md's IDOR mitigation section, verified against `backend/database.py:22-45`).

---

### `backend/itam_models.py` (extend — `LabelSheetRequest`)

**Analog:** `backend/asset_endpoints.py:425-427` (`BulkUpdateAssetsRequest`)
```python
class BulkUpdateAssetsRequest(BaseModel):
    assetIds: List[str]
    updates: Dict[str, Any]
```
New model, same shape minus `updates`, with `extra="forbid"` per RESEARCH.md Pattern 3:
```python
class LabelSheetRequest(BaseModel):
    assetIds: List[str]
    model_config = ConfigDict(extra="forbid")
```
Also cap `assetIds` length server-side in the endpoint (mirror `asset_endpoints.py:143`'s `ids = ids[:500]` truncation) to prevent unbounded PDF-generation DoS (RESEARCH.md Security Domain).

---

### `backend/router_registry.py` (extend)

**Analog** (lines 82-84):
```python
_load(app, "itam_catalog_endpoints", "router")  # ITAM Phase 56 Catalog Router
_load(app, "itam_asset_endpoints", "router")    # ITAM Phase 56 Asset Router
_load(app, "itam_lifecycle_endpoints", "router")  # ITAM Phase 57 Lifecycle Router
```
Add immediately after line 84:
```python
_load(app, "itam_label_endpoints", "router")    # ITAM Phase 58 Label Router
```

---

### `backend/tests/test_itam_labels.py` (test)

**Analog 1 (fixtures/RBAC/tenant-isolation conventions):** `backend/tests/test_itam_foundation.py`
```python
import sys, os, asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from pymongo import ReturnDocument

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest import make_test_app, make_token_data, _make_col
from itam_models import ASSET_SOURCE_MANUAL, DEFAULT_LIFECYCLE_STATUS, ASSET_SOURCE_AGENT
from authentication_service import get_current_user as real_get_current_user
```
Reuse `MockTenantIsolatedCollection`/`MockTenantIsolatedDatabase` from this file (check `conftest.py` first for a promoted shared fixture before duplicating, per RESEARCH.md's Wave 0 Gaps note).

**Analog 2 (offline network-blocked test — new pattern, closest precedent):** `backend/tests/test_ssrf_guards.py`
```python
import socket
def _loopback_dns_mock(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]
...
with patch("integrations_v2.socket.getaddrinfo", _loopback_dns_mock):
    ...
```
This file patches `socket.getaddrinfo` at the *module* level (`integrations_v2.socket.getaddrinfo`) to control DNS resolution for SSRF tests — a different goal (redirecting DNS) than what Phase 58 needs (proving zero socket usage at all). For the new offline test, patch `socket.socket` (and/or `socket.create_connection`) globally to raise unconditionally, per RESEARCH.md Pitfall 1:
```python
def test_offline_network_blocked(monkeypatch):
    def _raise(*a, **kw):
        raise AssertionError("network call attempted during offline label generation")
    monkeypatch.setattr(socket, "socket", _raise)
    monkeypatch.setattr(socket, "create_connection", _raise)
    png = generate_qr_png("ASSET-00001")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    bc = generate_barcode_png("ASSET-00001")
    assert bc[:8] == b"\x89PNG\r\n\x1a\n"
    pdf = generate_label_sheet_pdf([{"assetTag": "ASSET-00001", "name": "Laptop", "model": "X1"}])
    assert pdf[:5] == b"%PDF-"
```

## Shared Patterns

### RBAC gate (`manage:assets`)
**Source:** `backend/itam_asset_endpoints.py:35-43` (`_require_itam_admin`)
**Apply to:** All three new routes in `itam_label_endpoints.py` — import and reuse, do not redefine.
```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="User does not have permission to manage ITAM assets.")
    return current_user
```

### Tenant isolation
**Source:** `backend/database.py:22-45` (`TenantIsolatedDatabase`/`TenantIsolatedCollection`)
**Apply to:** Asset lookups in `itam_label_endpoints.py` — auto-injects `tenantId`; cross-tenant `asset_id` → 404, never leaked data.

### Streaming binary/PDF response
**Source:** `backend/compliance_automation_endpoints.py:115-132`
**Apply to:** All three new routes (PNG for QR/barcode, PDF for the sheet).
```python
return StreamingResponse(
    io.BytesIO(data),
    media_type="image/png",  # or "application/pdf" for the sheet route
    headers={"Content-Disposition": "attachment; filename=asset-label.png"}
)
```

### Bulk-selection request body
**Source:** `backend/asset_endpoints.py:425-427` (`BulkUpdateAssetsRequest`) + `backend/asset_endpoints.py:143` (`ids[:500]` cap)
**Apply to:** `LabelSheetRequest` in `itam_models.py` and the `POST /labels/sheet` handler — cap `assetIds` length server-side to prevent unbounded PDF-generation DoS.

### Router registration
**Source:** `backend/router_registry.py:82-84`
**Apply to:** New `_load(app, "itam_label_endpoints", "router")` line, added directly after the `itam_lifecycle_endpoints` line.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Barcode (Code128) generation logic within `itam_label_service.py` | service | transform | No existing 1D-barcode code in this codebase — first use of `python-barcode`; use RESEARCH.md's Code Examples section (library API directly, not an in-repo pattern) |
| Image-embedding-in-reportlab-PDF logic (`ImageReader`/`canvas.drawImage`) within `itam_label_service.py` | service | transform | Every existing reportlab usage (`export_service_pdf.py`, `compliance_reporting_pdf.py`, `compliance_automation_service.py`) generates tables/paragraphs only, never a raster image — first use of this reportlab submodule in the codebase; follow RESEARCH.md Pattern 2 (documented reportlab API, not homegrown) |
| Offline/no-network test methodology (`socket.socket` patched to raise unconditionally) | test | request-response | `test_ssrf_guards.py` patches `socket.getaddrinfo` for a different purpose (redirecting DNS resolution in SSRF tests, not proving zero network usage) — closest partial precedent only; write the new pattern directly per RESEARCH.md Pitfall 1 |

## Metadata

**Analog search scope:** `backend/*.py` (itam_*, compliance_*, export_service_pdf, asset_endpoints, mfa_service, router_registry, database.py), `backend/tests/*.py` (test_itam_foundation.py, test_ssrf_guards.py)
**Files scanned:** ~12
**Pattern extraction date:** 2026-08-05
</content>
