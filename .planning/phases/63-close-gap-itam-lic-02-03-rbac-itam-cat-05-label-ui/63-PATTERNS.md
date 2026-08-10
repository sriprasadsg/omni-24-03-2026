# Phase 63: Close gap: ITAM-LIC-02/03 RBAC + ITAM-CAT-05 label UI - Pattern Map

**Mapped:** 2026-08-11
**Files analyzed:** 5 (2 backend edits + 2 backend test edits + 2 frontend edits — apiService.ts and LifecyclePanel.tsx counted separately)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/itam_consumable_endpoints.py` | controller (route) | request-response | `backend/itam_license_endpoints.py` | exact |
| `backend/itam_component_endpoints.py` | controller (route) | request-response | `backend/itam_finance_endpoints.py` | exact |
| `backend/tests/test_itam_consumable.py` | test | request-response | `backend/tests/test_itam_finance.py` (`TestFinanceRbacAndTenantIsolation`) | exact |
| `backend/tests/test_itam_component.py` | test | request-response | `backend/tests/test_itam_finance.py` (`TestFinanceRbacAndTenantIsolation`) | exact |
| `services/apiService.ts` (3 new functions) | service (API client) | file-I/O (blob download) | `exportReport` (services/apiService.ts:1191-1225) | exact |
| `components/itam/LifecyclePanel.tsx` (Label action) | component | request-response / event-driven (UI menu) | same file, existing row-action buttons (lines 176-181) | exact (self-analog, no external component exists) |

## Pattern Assignments

### `backend/itam_consumable_endpoints.py` (controller, request-response)

**Analog:** `backend/itam_license_endpoints.py`

**Imports pattern (target shape):**
```python
from auth_types import TokenData
from itam_asset_endpoints import _require_itam_admin
# DELETE: from authentication_service import get_current_user  (unused after swap — confirmed no other use in this file)
```

**Current state (7 occurrences to swap), verified this session:**
```python
# backend/itam_consumable_endpoints.py lines 25,40,54,72,88,105,120
current_user=Depends(get_current_user),
```
becomes, matching the license-router style exactly:
```python
current_user: TokenData = Depends(_require_itam_admin),
```

**RBAC gate itself — do not touch, import only** (`backend/itam_asset_endpoints.py` lines 35-44, per RESEARCH.md; file's own imports confirmed lines 1-19 this session):
```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    """Dependency to ensure the current user has 'manage:assets' permission."""
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to manage ITAM assets."
        )
    return current_user
```

---

### `backend/itam_component_endpoints.py` (controller, request-response)

**Analog:** `backend/itam_finance_endpoints.py` (5-occurrence pattern, same scale)

**Imports pattern:** identical swap as above — add `from auth_types import TokenData` + `from itam_asset_endpoints import _require_itam_admin`; delete `from authentication_service import get_current_user` (line 8, confirmed unused elsewhere this session).

**Current state (5 occurrences across TWO router objects — verified this session):**
```python
# router = APIRouter(prefix="/api/itam/components", ...)  — 4 routes
# asset_components_router = APIRouter(prefix="/api/assets", ...) — 1 route
# lines 32, 47, 62, 77, 92:
current_user=Depends(get_current_user),      # line 32
current_user = Depends(get_current_user),    # line 47 (inconsistent spacing — normalize)
current_user = Depends(get_current_user)     # line 62 (no trailing comma — last param)
current_user = Depends(get_current_user),    # line 77
current_user = Depends(get_current_user),    # line 92
```
**Pitfall (must not miss):** `asset_components_router`'s single route (`list_asset_components_endpoint`, defined before `router`'s own 4 routes in file order) needs the identical swap — grep `Depends(get_current_user)` post-edit must return zero matches in this file.

Target for all 5: `current_user: TokenData = Depends(_require_itam_admin),` (normalize spacing to match license-file convention).

---

### `backend/tests/test_itam_consumable.py` and `backend/tests/test_itam_component.py` (test, request-response)

**Analog:** `backend/tests/test_itam_finance.py` lines 185-197 (`TestFinanceRbacAndTenantIsolation`) — the only ITAM router test file that actually contains a working 403 RBAC test (test_itam_license.py does NOT, despite CONTEXT.md's original pointer).

**Core pattern to clone exactly:**
```python
class TestFinanceRbacAndTenantIsolation:
    """Task 2 — 403 without manage:assets; cross-tenant asset id is
    indistinguishable from an unknown one."""

    @pytest.mark.asyncio
    async def test_rbac_denied_patch_returns_403(self, mock_db, finance_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"poNumber": "PO-1"})
        assert r.status_code == 403, r.text
```

**Critical fixture note (do not rewrite existing tests):** `consumable_app` (test_itam_consumable.py:140-146) and `component_app` (test_itam_component.py:142-148) already do:
```python
monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
```
at fixture setup — currently dead code, becomes live once the swap lands. The new 403 test must **override** this per-test with `return_value=False` (monkeypatch applied inside the test wins over the fixture-level one). No existing test needs modification.

**Coverage required:** `TestConsumableRbac` (1 test against e.g. `POST /api/itam/consumables`) and `TestComponentRbac` (2 tests: one against `POST /api/itam/components`, one against `GET /api/assets/{asset_id}/components` to cover `asset_components_router` separately, per Pitfall 1 in RESEARCH.md).

---

### `services/apiService.ts` — 3 new functions (service, file-I/O/blob-download)

**Analog:** `exportReport` (services/apiService.ts:1191-1225) — verified this session, exact text:
```typescript
export const exportReport = async (type: string, format: 'csv' | 'pdf') => {
    try {
        const response = await authFetch(`${API_BASE}/reports/export?type=${encodeURIComponent(type)}&format=${format}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Export failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;

        // Try to get filename from Content-Disposition header
        const disposition = response.headers.get('Content-Disposition');
        let filename = `${type.replace(/\s+/g, '_').toLowerCase()}_report.${format}`;
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        return { success: true };
    } catch (error) {
        console.error('Export error:', error);
        throw error;
    }
};
```

**Secondary precedent (simpler shape, verified this session, lines 3658-3670):**
```typescript
export const downloadComplianceReport = async (filename: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/compliance/reports/download/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error('Failed to download report');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
};
```

**Recommended combination for the 3 new functions (`fetchAssetQrLabel`, `fetchAssetBarcodeLabel`, `fetchAssetLabelSheet`):** `downloadComplianceReport`'s simplicity (single `void`-returning function, no caller-supplied filename param) + `exportReport`'s `Content-Disposition` header-parsing regex (filename must be server-derived, not invented — see Pitfall 3 in RESEARCH.md). Target backend routes (verified in `backend/itam_label_endpoints.py`):
```
GET  /api/assets/{asset_id}/label/qr       -> image/png,  filename=asset-label-{tag}-qr.png
GET  /api/assets/{asset_id}/label/barcode  -> image/png,  filename=asset-label-{tag}-barcode.png
POST /api/assets/labels/sheet              -> application/pdf, filename=asset-labels.pdf
                                               body: { assetIds: [asset_id] }
```

---

### `components/itam/LifecyclePanel.tsx` — new "Label" action (component, event-driven UI menu)

**Analog:** the file's own existing per-row action buttons and per-row `useState` targets (no dropdown/menu component exists anywhere else in the codebase — confirmed by grep this session and in RESEARCH.md Finding 6).

**Current row-action markup (verified this session, current working-tree state — includes the uncommitted "Logged-in User" column, do NOT revert):**
```tsx
// components/itam/LifecyclePanel.tsx lines 174-181
<td className="py-2 pr-4 text-gray-400">{a.loggedInUser || '—'}</td>
...
<button onClick={() => setCheckinTarget(a)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3">Check In</button>
...
<button onClick={() => setCheckoutTarget(a)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3">Check Out</button>
...
<button onClick={() => setAuditTarget(a)} className="text-gray-400 hover:text-gray-200 text-xs font-medium">Mark Audited</button>
```
Existing `useState` targets follow the `xTarget = useState<Asset | null>(null)` shape (`checkoutTarget`, `checkinTarget`, `auditTarget`) — the new Label menu should follow the same file convention but keyed by id (since it's a toggle, not a modal target):
```tsx
const [labelMenuAssetId, setLabelMenuAssetId] = useState<string | null>(null);

<div className="relative inline-block">
  <button
    onClick={() => setLabelMenuAssetId(labelMenuAssetId === a.id ? null : a.id)}
    className="text-gray-400 hover:text-gray-200 text-xs font-medium ml-3"
  >
    Label
  </button>
  {labelMenuAssetId === a.id && (
    <div className="absolute right-0 mt-1 w-44 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10">
      <button onClick={() => { handleLabelDownload(a.id, 'qr'); setLabelMenuAssetId(null); }} className="block w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-700">QR Code</button>
      <button onClick={() => { handleLabelDownload(a.id, 'barcode'); setLabelMenuAssetId(null); }} className="block w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-700">Barcode</button>
      <button onClick={() => { handleLabelDownload(a.id, 'sheet'); setLabelMenuAssetId(null); }} className="block w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-700">Label Sheet (this asset)</button>
    </div>
  )}
</div>
```
This is illustrative (not copied from an existing dropdown, since none exists) but matches D-02/D-03/D-04 and the file's existing Tailwind/useState conventions exactly. A flat 3-button inline group is an equally valid discretionary alternative per RESEARCH.md's Pattern 3 note — pick whichever needs less new code; either satisfies D-02.

**Modal component reference (available, not required for D-02):** `Modal` is already imported/used for Check Out/Check In/Mark Audited (lines 214-229) — not needed here since D-02 explicitly avoids a modal, listed only in case planning reconsiders.

---

## Shared Patterns

### RBAC gate (backend)
**Source:** `backend/itam_asset_endpoints.py` lines 35-44 (`_require_itam_admin`)
**Apply to:** every route in `itam_consumable_endpoints.py` and `itam_component_endpoints.py` (both routers)
```python
from itam_asset_endpoints import _require_itam_admin
...
current_user: TokenData = Depends(_require_itam_admin),
```
Do not redefine locally in either file — import only.

### Blob-download client pattern (frontend)
**Source:** `services/apiService.ts` lines 1191-1225 (`exportReport`) + lines 3658-3670 (`downloadComplianceReport`)
**Apply to:** all 3 new label-fetching functions in `apiService.ts`
```typescript
const res = await authFetch(url, { method });
if (!res.ok) throw new Error(...);
const blob = await res.blob();
const url2 = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.style.display = 'none';
a.href = url2;
// parse filename from res.headers.get('Content-Disposition') via exportReport's regex — do not hardcode
a.download = filename;
document.body.appendChild(a);
a.click();
window.URL.revokeObjectURL(url2);
document.body.removeChild(a);
```

### 403 RBAC test pattern (backend tests)
**Source:** `backend/tests/test_itam_finance.py` lines 185-197 (`TestFinanceRbacAndTenantIsolation`)
**Apply to:** new `TestConsumableRbac` (test_itam_consumable.py) and `TestComponentRbac` (test_itam_component.py) classes
```python
monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
xxx_app.dependency_overrides[real_get_current_user] = lambda: current_user
async with AsyncClient(transport=ASGITransport(app=xxx_app), base_url="http://testserver") as ac:
    r = await ac.post("/api/itam/xxx", json={...})
assert r.status_code == 403, r.text
```

## No Analog Found

None — every file this phase touches has a direct, verified in-repo analog (see RESEARCH.md's own "Key insight": every piece of this phase already has a working, in-repo precedent).

## Metadata

**Analog search scope:** `backend/itam_*_endpoints.py`, `backend/tests/test_itam_*.py`, `components/itam/LifecyclePanel.tsx`, `services/apiService.ts` — all read/grepped directly this session or in the upstream RESEARCH.md session (2026-08-11).
**Files scanned:** 10 (5 backend endpoint files, 3 test files, 1 component file, 1 service file)
**Pattern extraction date:** 2026-08-11
</content>
