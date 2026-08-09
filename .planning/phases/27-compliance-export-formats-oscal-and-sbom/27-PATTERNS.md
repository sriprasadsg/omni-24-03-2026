# Phase 27: Compliance Export Formats (OSCAL and SBOM) - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 6 (2 new backend endpoint modules, 1 modified router registry, 2 new test files, 2 modified frontend components)
**Analogs found:** 6 / 6 (all files have a strong, directly-read analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/oscal_endpoints.py` (NEW) | controller (thin GET endpoint) | request-response (transform, no persistence) | `backend/ocsf_endpoints.py` (structural shape) + `backend/compliance_reports_endpoints.py` (auth/tenant pattern) | exact (structure) / exact (auth) |
| `backend/container_scanner_endpoints.py` (MODIFIED — add `GET /{scan_id}/sbom`) | controller (thin GET endpoint added to existing file) | request-response (transform, no persistence) | same file's existing `/results` route | exact |
| `backend/router_registry.py` (MODIFIED — 1 line) | config | — | existing `_load(app, "ocsf_endpoints", "router")` line | exact |
| `backend/tests/test_oscal_export.py` (NEW) | test | request-response | `backend/tests/test_bundles_and_reports.py` | exact |
| `backend/tests/test_container_sbom_export.py` (NEW) | test | request-response | `backend/tests/test_bundles_and_reports.py` (adapted for `db._db` raw accessor) | role-match |
| `components/ApiExtensionsDashboard.tsx` (MODIFIED — add "Export OSCAL" button) | component | request-response (blob download) | same file's existing `exportOcsf()` + OCSF Export button block | exact |
| `components/IacContainerDashboard.tsx` (MODIFIED — add "Export SBOM" button per row) | component | request-response (blob download) | `ApiExtensionsDashboard.tsx`'s `exportOcsf()` pattern (generalize/copy, not a new invention) | role-match |

## Pattern Assignments

### `backend/oscal_endpoints.py` (NEW controller, request-response)

**Analog #1 (structure):** `backend/ocsf_endpoints.py` (72 lines, read in full)
**Analog #2 (auth/tenant pattern):** `backend/compliance_reports_endpoints.py` (164 lines, read in full)

**Imports pattern** — combine both analogs (OCSF's leanness + compliance-reports' auth imports):
```python
# from backend/ocsf_endpoints.py lines 1-11
"""OCSF Output Format — findings and cloud checks in OCSF 1.0 schema."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from database import get_database
...
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ocsf", tags=["OCSF Export"])

# from backend/compliance_reports_endpoints.py lines 1-13 (use THIS auth import,
# NOT ocsf_endpoints.py's rbac_service — see Pitfall 4 in RESEARCH.md)
from fastapi import APIRouter, HTTPException, Form, Depends
from authentication_service import get_current_user
```
Resulting new-file import block should be:
```python
import logging, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from authentication_service import get_current_user
from compliance_reporting_data import _build_report_data

router = APIRouter(prefix="/api/oscal", tags=["OSCAL Export"])
logger = logging.getLogger(__name__)
```

**Auth/tenant pattern — copy VERBATIM from `backend/compliance_reports_endpoints.py` lines 18-32** (this is the sibling-file auth convention per RESEARCH.md Pitfall 4 — do NOT use `rbac_service.has_permission(...)` here):
```python
@router.post("/api/compliance/reports/generate")
async def generate_compliance_report(
    framework_id: str = Form(...),
    current_user=Depends(get_current_user),
):
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        report = await compliance_reporting_service.generate_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error("Failed to generate CSV compliance report for tenant %s: %s", tenant_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
```
Adapted for OSCAL (GET + Query, per `ocsf_endpoints.py`'s `@router.get(...)` shape at lines 22-23, and reusing `_build_report_data` per RESEARCH.md Pattern 1):
```python
@router.get("/assessment-results")
async def oscal_assessment_results(
    framework_id: str = Query(...),
    current_user=Depends(get_current_user),
):
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        framework, asset_summary, control_rows = await _build_report_data(framework_id, tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_oscal_assessment_results(framework, control_rows)
```

**Core transform pattern** — mirrors `ocsf_endpoints.py` lines 30-45 (build a plain-dict list from DB rows, return dict with items); for OSCAL use the full builder already drafted in RESEARCH.md Pattern 2 (lines 171-207 of `27-RESEARCH.md`), which maps `_build_report_data()`'s `control_rows` (fields: `Control ID`, `Control Name`, `Control Status`, `Evidence Desc`, from `backend/compliance_reporting_data.py` lines 191-201/215-228) into OSCAL `findings[]`.

**`_build_report_data` signature to call** (`backend/compliance_reporting_data.py` line 114):
```python
async def _build_report_data(framework_id: str, tenant_id: str = None):
    # returns: framework (dict), asset_summary (list), control_rows (list)
```
Note the platform status vocabulary from `_score_status()`/`_overall_verdict()` (`compliance_reporting_data.py` lines 39-46, 56-61) is `Compliant` / `Warning` / `Non-Compliant` / `Partially Compliant` — this is what `Control Status`/`Asset Status` values will contain; map per RESEARCH.md Open Question 1 recommendation (`Non-Compliant` → `"planned"`, not `"not-applicable"`).

**Error handling pattern** — copy the `try/except ValueError → 404` + generic `except Exception → 500 + logger.error(..., exc_info=True)` shape from `compliance_reports_endpoints.py` lines 27-32.

**No file write / no `Content-Disposition`** — explicitly do NOT copy `compliance_reports_endpoints.py`'s `download_compliance_report` (lines 89-123) or `_REPORTS_DIR`/`FileResponse` machinery. Return the dict directly (FastAPI serializes to JSON automatically), exactly like `ocsf_endpoints.py` line 45 (`return {"items": ocsf_items, "count": len(ocsf_items)}`).

---

### `backend/container_scanner_endpoints.py` (MODIFIED — add SBOM route)

**Analog:** same file, existing `/results` route (lines 43-47, full file read — only 47 lines)

**Imports** — no new imports needed beyond what's already in the file (lines 1-13); add `uuid` if the CycloneDX builder lives inline, or import it from a new small helper.

**Auth pattern — copy VERBATIM from the same file's existing routes** (lines 29, 44) — this is the container-scanner family convention (differs from OSCAL's auth per RESEARCH.md Pitfall 4):
```python
@router.get("/results")
async def list_results(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await svc.list_results(db, get_tenant_id())
    return {"items": items, "count": len(items)}
```
New route, following the identical shape (RESEARCH.md suggests considering `"view:sbom"` permission instead of `"view:dashboard"` — planner's call):
```python
@router.get("/results/{scan_id}/sbom")
async def container_result_sbom(scan_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    tenant_id = get_tenant_id()
    result = await db._db.container_scan_results.find_one({"scan_id": scan_id, "tenantId": tenant_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Scan result not found")
    return _to_cyclonedx(result)
```

**Data source pattern — raw `db._db` accessor** (NOT the tenant-isolated wrapper used elsewhere), matching `container_scanner_service.py` lines 92-99:
```python
async def save_result(db, tenant_id: str, result: dict) -> str:
    doc = {"tenantId": tenant_id, **result}
    await db._db.container_scan_results.insert_one(doc)
    return result["scan_id"]

async def list_results(db, tenant_id: str) -> list:
    return await db._db.container_scan_results.find({"tenantId": tenant_id}, {"_id": 0}).sort("scanned_at", -1).to_list(length=100)
```
The new SBOM route must query the same `db._db.container_scan_results` collection with an explicit tenant filter (per RESEARCH.md V4 access-control note) rather than the higher-level `get_database()`-only wrapper pattern used in `oscal_endpoints.py`.

**Scan result document shape to transform** (`container_scanner_service.py` lines 69, 88 and `_simulated_results` line 75-89): keys are `scan_id`, `image`, `trivy` (bool), `simulated` (bool), `vulns` (list of `{id, pkg_name, installed_version, fixed_version, severity, title, description}`), `total`, `critical`/`high`/`medium`/`low`, `scanned_at`. The `simulated` flag (Pitfall 3 / Open Question 2) must be surfaced in the CycloneDX `metadata.properties` per RESEARCH.md Pattern 3 / recommendation.

**CycloneDX builder** — use RESEARCH.md Pattern 3 verbatim (lines 219-248 of `27-RESEARCH.md`), which already handles the `(pkg_name, installed_version)` dedup required by Pitfall 2.

**Error handling** — this file has no explicit try/except around DB calls (see `/scan` and `/results`, lines 23-47) — errors propagate to FastAPI's default handler. Follow the same minimal style; only add explicit `HTTPException(404, ...)` for the not-found case shown above (mirrors the existing image-name validation raising `HTTPException(422, ...)` at line 36).

---

### `backend/router_registry.py` (MODIFIED — 1 line)

**Analog:** existing line 241 region
```python
# backend/router_registry.py line 235
_load(app, "container_scanner_endpoints", "router")
...
# line 241
_load(app, "ocsf_endpoints",              "router")
```
Add immediately after line 241:
```python
_load(app, "oscal_endpoints",             "router")
```
No new line needed for `container_scanner_endpoints.py` — it is already registered (line 235); the new SBOM route is added inside that existing module.

---

### `backend/tests/test_oscal_export.py` (NEW)

**Analog:** `backend/tests/test_bundles_and_reports.py` (389 lines; read lines 1-90 — helper/fixture setup is representative of the whole file's pattern)

**Mocking pattern to copy** (lines 22-76):
```python
def _col():
    col = MagicMock()
    col.find_one      = AsyncMock(return_value=None)
    col.insert_one    = AsyncMock(return_value=MagicMock(inserted_id="id"))
    col.update_one    = AsyncMock(return_value=MagicMock(matched_count=1))
    col.count_documents = AsyncMock(return_value=0)
    col.find          = MagicMock()
    col.find.return_value.sort = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    col.aggregate     = MagicMock(side_effect=lambda _: _async_iter([]))
    return col

def _db():
    db = MagicMock()
    db.tenants = _col()
    db.tickets = _col()
    db.__getitem__ = lambda self, key: getattr(self, key, _col())
    return db

def _app_with_limiter(router, user):
    from authentication_service import get_current_user as _gcu
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_gcu] = lambda: user
    try:
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        test_limiter = Limiter(key_func=get_remote_address, enabled=False)
        app.state.limiter = test_limiter
    except ImportError:
        pass
    return app
```
For OSCAL tests, extend `_db()` to include the collections `_build_report_data()` reads (`compliance_frameworks`, `asset_compliance`, `compliance_artifacts`, `assets` — see `backend/compliance_reporting_data.py` lines 123, 130, 134, 143), and override `get_current_user` (not `rbac_service.has_permission`) since `oscal_endpoints.py` follows the `compliance_reports_endpoints.py` auth convention. Use `TestClient` + `app.dependency_overrides[get_current_user] = lambda: tenant_user` exactly as in the analog. Add a `-k tenant` test verifying cross-tenant `framework_id` requests are rejected/scoped (RESEARCH.md test map row 2).

---

### `backend/tests/test_container_sbom_export.py` (NEW)

**Analog:** `backend/tests/test_bundles_and_reports.py` same helpers, adapted per RESEARCH.md Wave 0 Gaps note: mock `db._db.container_scan_results.find_one` (raw accessor, not `db.<collection>` directly) since `container_scanner_service.py` uses `db._db` (lines 94, 99). Override `rbac_service.has_permission` dependency (not `get_current_user`) to match `container_scanner_endpoints.py`'s auth convention (lines 29, 44). Include a `-k simulated` test asserting the `simulated` flag propagates into the CycloneDX output (RESEARCH.md test map row 4).

---

### `components/ApiExtensionsDashboard.tsx` (MODIFIED)

**Analog:** same file's existing `exportOcsf()` helper + OCSF Export button block (lines 41-51, 85-98; 136-line file read in relevant part)

**Export helper — reuse exactly, rename per RESEARCH.md recommendation** ("generalize the existing function... rather than adding a near-duplicate helper"):
```typescript
// lines 41-51 (existing, format-agnostic already)
const exportOcsf = async (endpoint: string, filename: string) => {
  try {
    const res = await authFetch(endpoint);
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename;
    a.click(); URL.revokeObjectURL(url);
    showToast(`Exported ${filename}`, 'success');
  } catch { showToast('Export failed', 'error'); }
};
```
**New button — copy exact JSX shape** (lines 89-96):
```typescript
<button onClick={() => exportOcsf('/api/oscal/assessment-results?framework_id=${fw}', 'assessment-results-oscal.json')}
  className="px-4 py-2 bg-green-600 text-white text-xs rounded">
  Export OSCAL
</button>
```
Place inside the same "OCSF 1.0 Export" section (lines 86-98) or a new adjacent section following the identical `<div className="space-y-2">` wrapper structure.

---

### `components/IacContainerDashboard.tsx` (MODIFIED — add per-row "Export SBOM" button)

**Analog:** `ApiExtensionsDashboard.tsx`'s `exportOcsf()` pattern (copy the same helper into this file, or import/share it — planner's call; file not yet read in full since it wasn't in the required-reading list, but the button/fetch/blob pattern to copy is identical to the excerpt above). Wire the endpoint per scan row: `` `/api/container/results/${scanId}/sbom` `` → filename `` `sbom-${scanId}.json` ``.

## Shared Patterns

### Tenant-scoped auth — two DISTINCT conventions (do not cross-wire)
**OSCAL (`oscal_endpoints.py`)** — Source: `backend/compliance_reports_endpoints.py` lines 18-26
```python
current_user=Depends(get_current_user)
...
tenant_id = getattr(current_user, "tenant_id", None) or None
if not tenant_id:
    raise HTTPException(status_code=403, detail="Tenant context required")
```
**Container SBOM (`container_scanner_endpoints.py`)** — Source: same file, lines 29/44
```python
current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))
...
tenant_id = get_tenant_id()  # from tenant_context
```
**Apply to:** exactly one file each — do not mix (RESEARCH.md Pitfall 4 is the explicit warning against cross-wiring these).

### Thin GET, in-memory JSON, no persistence
**Source:** `backend/ocsf_endpoints.py` (whole file, 72 lines) — every route: query DB → build list of dicts in a for-loop → `return {"items": ..., "count": ...}`. No file write, no `db.compliance_reports`-style metadata tracking, no `Content-Disposition`.
**Apply to:** both `oscal_endpoints.py` and the new SBOM route in `container_scanner_endpoints.py`.

### Frontend blob-download export button
**Source:** `components/ApiExtensionsDashboard.tsx` lines 41-51 (`exportOcsf`) + 89-96 (button JSX)
**Apply to:** both new "Export OSCAL" and "Export SBOM" buttons across `ApiExtensionsDashboard.tsx` and `IacContainerDashboard.tsx`.

### Router registration
**Source:** `backend/router_registry.py` line 241 (`_load(app, "ocsf_endpoints", "router")`)
**Apply to:** `oscal_endpoints.py` only — add one new line immediately after. Container SBOM route needs no registry change (file already registered at line 235).

## No Analog Found

None — all files have a direct, recently-modified analog in the codebase (OCSF endpoints shipped Phase 22, container scanner shipped Phase 24/25).

## Metadata

**Analog search scope:** `backend/*.py` (ocsf_endpoints.py, compliance_reports_endpoints.py, compliance_reporting_data.py, container_scanner_endpoints.py, container_scanner_service.py, router_registry.py), `backend/tests/test_bundles_and_reports.py`, `components/ApiExtensionsDashboard.tsx`
**Files scanned:** 8 (all read directly, no re-reads of overlapping ranges)
**Pattern extraction date:** 2026-07-06
