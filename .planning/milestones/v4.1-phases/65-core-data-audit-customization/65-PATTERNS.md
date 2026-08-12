# Phase 65: Core Data, Audit & Customization - Pattern Map

**Mapped:** 2026-08-12
**Files analyzed:** 13 (new/modified, per RESEARCH.md's Recommended Project Structure + audit backfill scope)
**Analogs found:** 13 / 13

## Scope Notes (binding for this pattern map)

1. Global Settings / Branding (ITAM-SET-01/02) = a **new ITAM-console-scoped** settings surface (new tab in `components/itam/ITAMConsole.tsx`, new `ItamSettingsPanel.tsx` alongside `CatalogPanel.tsx`/`LifecyclePanel.tsx`), NOT an extension of `components/TenantBrandingSettings.tsx` / `backend/tenant_endpoints.py`. Those two files are excerpted below only as a rough analog for "how this repo already does a settings form + persistence."
2. Audit trail (ITAM-DAT-02) includes backfilling `log_action_async` calls into the **existing** `itam_catalog_endpoints.py`, `itam_asset_endpoints.py`, `itam_component_endpoints.py`, `itam_consumable_endpoints.py`, `itam_finance_endpoints.py`, `itam_license_endpoints.py`, `itam_lifecycle_endpoints.py` write paths, in addition to new Phase 65 work. `backend/agent_remote_control.py` is the calling-convention analog since grep confirms zero ITAM callers of `log_action_async` exist today.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/itam_customization_endpoints.py` (NEW) | route/controller | CRUD (settings GET/POST) | `backend/settings_endpoints.py` (`/database`, `/llm` routes) | exact |
| `backend/itam_customization_service.py` (NEW) | service | CRUD | `backend/itam_catalog_service.py` (pure-function service, no DB I/O) for validation shape; `backend/settings_endpoints.py`'s inline persistence logic for the DB-I/O shape | role-match |
| `backend/itam_audit_service.py` (NEW) | service | event-driven (write) + request-response (read) | `backend/audit_service.py` (`AuditService.log_action_async`, `get_logs`) — wrap, don't fork | exact |
| `backend/itam_data_service.py` (NEW) | service | batch / file-I/O (CSV) | `backend/export_service.py` (`_generate_csv`) + `backend/itam_catalog_service.py` (pure validation functions) | role-match |
| `backend/itam_data_endpoints.py` (NEW) | route/controller | file-I/O (multipart upload + streaming download) | `backend/compliance_framework_mgmt_endpoints.py` (`import_compliance_controls`) for import; `services/apiService.ts::downloadComplianceReport` + `export_service.py` for export | exact |
| `backend/itam_catalog_endpoints.py` (MODIFY — audit backfill + optional field-registry route) | controller | CRUD + event-driven (audit write) | `backend/agent_remote_control.py` lines 102-114 (audit call site) | exact |
| `backend/itam_asset_endpoints.py` (MODIFY — audit backfill) | controller | CRUD + event-driven | `backend/agent_remote_control.py` lines 102-114 | exact |
| `backend/itam_lifecycle_endpoints.py`, `itam_finance_endpoints.py`, `itam_license_endpoints.py`, `itam_consumable_endpoints.py`, `itam_component_endpoints.py` (MODIFY — audit backfill) | controller | CRUD + event-driven | `backend/agent_remote_control.py` lines 102-114 | exact |
| `backend/audit_endpoints.py` (MODIFY — add `resourceType`/`resourceId` query filter) | controller | request-response | itself (extend in place); `backend/audit_service.py::get_logs` signature | exact (self-extend) |
| `backend/router_registry.py` (MODIFY — register 2 new routers) | config | n/a | itself, lines 82-90 (existing `_load(app, "itam_..._endpoints", "router")` block) | exact |
| `components/itam/ITAMConsole.tsx` (MODIFY — add tab(s)) | component | request-response | itself (extend `Tab` union + `TABS` array + `<main>` conditional) | exact (self-extend) |
| `components/itam/ItamSettingsPanel.tsx` (NEW) | component | CRUD (form) | `components/TenantBrandingSettings.tsx` (form shape/fields) — different scope but closest form-persistence analog; `components/itam/CatalogPanel.tsx` for ITAM-console tab-panel conventions | role-match |
| `components/itam/ActivityLogPanel.tsx` (NEW) | component | request-response (read-only list) | `components/itam/CatalogPanel.tsx` (load/list/error-state pattern), read-only subset | role-match |
| `components/itam/CustomFieldsManager.tsx` (NEW) | component | CRUD (form) | `components/itam/CatalogPanel.tsx` (create/list/delete + Modal pattern) | exact |
| `components/itam/BulkImportExportPanel.tsx` (NEW) | component | file-I/O | `services/apiService.ts::downloadComplianceReport` (download) + `components/itam/CatalogPanel.tsx` (panel shell/error state) | role-match |
| `services/apiService.ts` (MODIFY — add itam data/audit/settings client fns) | utility (API client) | request-response + file-I/O | itself, lines 5218-5259 (`itamThrow` + `fetchCatalogEntities`/`createCatalogEntity` block) + lines 3658-3667 (`downloadComplianceReport`) | exact (self-extend) |
| `backend/tests/test_itam_customization.py`, `test_itam_audit.py`, `test_itam_data_csv.py` (NEW) | test | request-response | `backend/tests/test_itam_catalog.py` (httpx `AsyncClient`/`ASGITransport`, `MockTenantIsolatedCollection`, `tests/conftest.make_test_app`/`make_token_data`) | exact |
| `src/__tests__/ITAMSettingsPanel.test.tsx`, `ITAMActivityLogPanel.test.tsx`, `ITAMCustomFieldsManager.test.tsx`, `ITAMBulkImportExport.test.tsx` (NEW) | test | request-response | `src/__tests__/ITAMCatalogPanel.test.tsx`, `ITAMConsole.test.tsx` | exact |

## Pattern Assignments

### `backend/itam_customization_endpoints.py` / `itam_customization_service.py` (route+service, CRUD)

**Analog:** `backend/settings_endpoints.py`

**Imports pattern** (lines 1-12):
```python
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
```

**Admin-role gate** (lines 38-43) — copy this exact literal set, per RESEARCH.md Pitfall 4:
```python
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

def _require_admin(user: TokenData) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")
```

**Core GET/POST persistence pattern** (lines 46-65, `/database` type — simplest example; the `/llm` route around lines 71-116 shows the tenant-scoped + global-fallback variant that ITAM settings should actually follow, per RESEARCH.md Pattern 5 / Pitfall 2):
```python
@router.get("/database")
async def get_database_settings(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    settings = await db.system_settings.find_one({"type": "database"}, {"_id": 0})
    return settings or {}

@router.post("/database")
async def save_database_settings(settings: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    _require_admin(current_user)
    db = get_database()
    settings["type"] = "database"
    await db.system_settings.update_one({"type": "database"}, {"$set": settings}, upsert=True)
    return settings
```

**CRITICAL deviation required (RESEARCH.md Pattern 5 / Pitfall 2):** for `type: "itam_settings"` (tenant-scoped + global-fallback), use the `raw = db._db if hasattr(db, "_db") else db` unwrap and explicit `tenantId` filtering shown in RESEARCH.md's Pattern 5 code block — do NOT use the wrapped `db.system_settings` accessor shown in the `/database` example above (that example is `type`-only, no tenant scoping; `/llm`'s pattern at lines 71-116 is the one to actually clone for the tenant-scoped shape).

**Validation reuse for a Custom Fields Manager backing route** — clone `backend/itam_catalog_service.py` verbatim, do not reimplement:
```python
from itam_catalog_service import validate_fieldsets, collect_field_defs, validate_custom_field_values
```
(Full source already read in full — 83 lines, no DB I/O, three pure functions: `validate_fieldsets`, `collect_field_defs`, `validate_custom_field_values`. See RESEARCH.md Pattern 1 for the exact call sites.)

---

### `backend/itam_audit_service.py` (service, event-driven write + request-response read)

**Analog (write side):** `backend/agent_remote_control.py` lines 102-114 — the only real in-repo caller of `log_action_async` today:
```python
try:
    from audit_service import get_audit_service
    audit_service = get_audit_service()
    await audit_service.log_action_async(
        user_name=current_user.username,
        action="remote_command.execute",
        resource_type="agent",
        resource_id=agent_id,
        details=f"Executed command: {command.get('command')} {command.get('args', [])}",
        tenant_id=current_user.tenant_id
    )
except Exception as e:
    # log-and-continue, never fail the parent request over audit-write failure
    ...
```
For ITAM this becomes (per RESEARCH.md Pattern 2): `action="itam_asset.update"` (`<domain>.<verb>` convention), `resource_type="itam_asset"`, and `previous_state=existing_doc` for rollback support.

**Analog (read side):** `backend/audit_endpoints.py` (58 lines, read in full):
```python
# lines 1-13: imports + router setup
from audit_service import get_audit_service
from rbac_utils import require_permission
router = APIRouter(prefix="/api/audit-logs", tags=["Audit & Rollback"])
_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

# lines 16-27: list route — this is the route to extend with resourceType/resourceId
@router.get("", response_model=List[Dict[str, Any]])
async def get_audit_logs(
    limit: int = Query(100, le=1000),
    skip: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_permission("view:audit_log"))
):
    tenant_id = get_tenant_id()
    is_super_admin = getattr(current_user, "role", "") in _SUPER_ROLES
    return await get_audit_service().get_logs(tenant_id=tenant_id, is_super_admin=is_super_admin)
```
`itam_audit_service.py` should be thin wrapper functions around `audit_service.get_audit_service()` — e.g. `async def get_itam_audit_logs(resource_type, resource_id, tenant_id, is_super_admin)` calling an extended `get_logs()` — NOT a new class/collection (RESEARCH.md Anti-Pattern: "Building a new AuditLog collection/class for ITAM specifically").

**Gap to close in `backend/audit_service.py`:** `get_logs()` currently only takes `tenant_id`/`is_super_admin` — add optional `resource_type`/`resource_id` params, mirrored into `audit_endpoints.py`'s `GET /api/audit-logs` query params (`Query(None)`).

---

### `backend/itam_data_service.py` / `itam_data_endpoints.py` (service+route, batch/file-I/O)

**Export analog:** `backend/export_service.py::_generate_csv` (lines 466-481, full function read):
```python
def _generate_csv(self, data):
    if not data:
        return ""
    output = io.StringIO()
    if isinstance(data[0], dict):
        all_keys = list(dict.fromkeys(k for row in data for k in row.keys()))
        writer = csv.DictWriter(output, fieldnames=all_keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    else:
        writer = csv.writer(output)
        writer.writerows(data)
    return output.getvalue()
```

**Import analog:** `backend/compliance_framework_mgmt_endpoints.py::import_compliance_controls` (lines 224-262, CSV branch):
```python
@router.post("/api/compliance/{framework_id}/import")
async def import_compliance_controls(
    framework_id: str,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    content = await file.read()
    new_controls: List[Dict[str, Any]] = []
    if filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
        for row in reader:
            cid  = (row.get("ID") or row.get("id") or "").strip()
            name = (row.get("Name") or row.get("name") or "").strip()
            if cid and name:
                new_controls.append({...})
    ...
    if not new_controls:
        raise HTTPException(status_code=400, detail="No controls could be extracted...")
```
ITAM's version should route each row's `customFields` through `validate_custom_field_values(collect_field_defs(model_doc), parsed_custom_fields)` per RESEARCH.md Pattern 4 and Pitfall/Threat table — never bulk-insert unvalidated rows, and enforce a file-size cap (not present in this analog — a phase-specific addition per RESEARCH.md's threat table).

**Frontend download analog:** `services/apiService.ts::downloadComplianceReport` (lines 3658-3667+):
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
    // (a.click(); revoke URL; remove node — rest of function not re-read, same shape as RESEARCH.md's excerpt)
};
```

---

### Audit backfill into existing ITAM endpoints (`itam_catalog_endpoints.py`, `itam_asset_endpoints.py`, `itam_lifecycle_endpoints.py`, `itam_finance_endpoints.py`, `itam_license_endpoints.py`, `itam_consumable_endpoints.py`, `itam_component_endpoints.py`)

**Analog:** `backend/agent_remote_control.py` lines 102-114 (same excerpt as above — this is the single calling convention to replicate verbatim at every ITAM create/update/delete site, per Scope Note 2). Existing imports pattern for these files already includes `from auth_types import TokenData`, `from rbac_utils import verify_permission` (see `itam_catalog_endpoints.py` lines 1-27) — add `from audit_service import get_audit_service` alongside.

**`itam_catalog_endpoints.py` current header** (lines 1-27, for import-block conventions when adding the audit import):
```python
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo import ReturnDocument

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from itam_catalog_service import validate_fieldsets
from itam_models import (...)
from rbac_utils import verify_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/itam/catalog", tags=["ITAM Catalog"])
```
The `manage:assets` permission gate at lines 63-72 (`_require_itam_admin`) is the auth pattern already used in this file — do not add a new/different gate for the audit-wiring change itself.

---

### `backend/router_registry.py` (config)

**Analog:** existing ITAM registration block, lines 82-90:
```python
_load(app, "itam_catalog_endpoints", "router")  # ITAM Phase 56 Catalog Router
_load(app, "itam_asset_endpoints", "router")    # ITAM Phase 56 Asset Router
_load(app, "itam_lifecycle_endpoints", "router")  # ITAM Phase 57 Lifecycle Router
_load(app, "itam_license_endpoints",   "router")  # ITAM Phase 60 License Router
_load(app, "itam_consumable_endpoints", "router")  # ITAM Phase 60 Consumable Router
_load(app, "itam_component_endpoints", "router")  # ITAM Phase 60 Component Router
_load(app, "itam_component_endpoints", "asset_components_router")  # ITAM Phase 60: GET /api/assets/{id}/components
_load(app, "itam_label_endpoints",     "router")    # ITAM Phase 58 Label Router
_load(app, "itam_finance_endpoints",   "router")    # ITAM Phase 59 Finance Router
```
Add two new lines: `_load(app, "itam_data_endpoints", "router")` and `_load(app, "itam_customization_endpoints", "router")`, following the exact `# ITAM Phase N <Name> Router` comment convention. New routers are unreachable without this registration (RESEARCH.md "State of the Art" table).

---

### `components/itam/ITAMConsole.tsx` (component, request-response — tab shell)

**Analog:** itself, full file (76 lines, already read):
```typescript
type Tab = 'catalog' | 'lifecycle' | 'finance' | 'licenses' | 'compliance' | 'software';

const TABS: { id: Tab; label: string }[] = [
  { id: 'catalog', label: 'Catalog' },
  ...
];
// ...
<nav className="flex gap-1 mb-4 border-b border-gray-700" aria-label="Tabs">
  {TABS.map((t) => ( <button key={t.id} onClick={() => setTab(t.id)} ... /> ))}
</nav>
<main>
  {tab === 'catalog' && <CatalogPanel />}
  ...
</main>
```
Add `'settings' | 'audit'` (or similar) to the `Tab` union, a `{ id: 'settings', label: 'Settings' }` entry to `TABS`, and `{tab === 'settings' && <ItamSettingsPanel />}` / `{tab === 'audit' && <ActivityLogPanel />}` to the `<main>` block. Import new panels the same way `CatalogPanel`/`LifecyclePanel` are imported at the top (lines 4-9).

---

### `components/itam/CustomFieldsManager.tsx` / `ActivityLogPanel.tsx` / `ItamSettingsPanel.tsx` / `BulkImportExportPanel.tsx` (components, CRUD/read-only forms)

**Analog:** `components/itam/CatalogPanel.tsx` (167 lines; excerpt lines 1-60 read):
```typescript
import React, { useEffect, useState, useCallback } from 'react';
import Modal from '../ui/Modal';
import { ItamCatalogEntity, ItamCatalogKind } from '../../types';
import { fetchCatalogEntities, createCatalogEntity, deleteCatalogEntity } from '../../services/apiService';
import { showToast } from '../../utils/toast';

export function CatalogPanel() {
  const [entities, setEntities] = useState<ItamCatalogEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setEntities(await fetchCatalogEntities(kind));
    } catch (e: any) {
      setError(e?.message || `Couldn't load ...`);
    } finally { setLoading(false); }
  }, [kind, kindMeta.label]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    try {
      await createCatalogEntity(kind, { ... });
      showToast(`... created.`, 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || `Couldn't save ...`, 'error');
    }
  }
  // ... Modal-based create/delete dialogs follow (not re-read past line 60)
}
```
This load/error-state/`showToast` pattern is the one to clone for `ActivityLogPanel.tsx` (read-only subset — list + load + error state, no create/delete) and `CustomFieldsManager.tsx` (full CRUD subset).

**Form/settings-persistence analog (different scope, per Scope Note 1):** `components/TenantBrandingSettings.tsx` (116 lines, full file read) — clone the controlled-input + `useEffect` fetch-on-mount + `handleSave` shape for `ItamSettingsPanel.tsx`, but call the NEW `/api/itam/settings` endpoint, not `/api/tenants/{id}/branding`:
```typescript
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

const [config, setConfig] = useState<BrandingConfig>({});
useEffect(() => {
    (async () => {
        try {
            const res = await authFetch(`/api/tenants/${tenantId}/branding`); // -> becomes /api/itam/settings
            if (res.ok) setConfig(await res.json());
        } catch (error) { console.error("Failed to load branding", error); }
    })();
}, [tenantId]);

const handleSave = async () => {
    setLoading(true);
    try {
        await authFetch(`/api/tenants/${tenantId}/branding`, { method: 'POST', body: JSON.stringify(config) }); // -> /api/itam/settings
        setSaved(true);
    } catch (error) {
        showToast("Failed to save configuration", 'error');
    } finally { setLoading(false); }
};
```
Reuse the same field *shape* (`logoUrl`, `primaryColor`, `companyName`) for the branding portion of `ItamSettingsPanel.tsx` per RESEARCH.md Open Question 1's recommendation, even though the persistence target is the new `type: "itam_settings"` document, not `/api/tenants/{id}/branding`.

**Bulk import/export analog:** combine `CatalogPanel.tsx`'s panel shell/error-state pattern with `downloadComplianceReport`'s Blob-download client call (see above) for the export half of `BulkImportExportPanel.tsx`; the import half needs a `<input type="file">` + `FormData`/`authFetch(..., { method: 'POST', body: formData })` call — no existing ITAM frontend file does file upload yet, so this piece has no exact in-repo analog (noted in "No Analog Found" below).

---

### `services/apiService.ts` (utility/API client, MODIFY)

**Analog:** itself, lines 5218-5259 (ITAM client-function block) + lines 3658-3667 (download pattern):
```typescript
// lines 5221-5224
async function itamThrow(res: Response, fallback: string): Promise<never> {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ? (typeof body.detail === 'string' ? body.detail : fallback) : fallback);
}

// lines 5226-5230 — GET pattern
export const fetchCatalogEntities = async (kind: ItamCatalogKind): Promise<ItamCatalogEntity[]> => {
    const res = await authFetch(`${API_BASE}/itam/catalog/${kind}`);
    if (!res.ok) return itamThrow(res, `Failed to load ${kind}`);
    return res.json();
};

// lines 5232-5238 — POST pattern
export const createCatalogEntity = async (kind: ItamCatalogKind, data: Record<string, unknown>): Promise<ItamCatalogEntity> => {
    const res = await authFetch(`${API_BASE}/itam/catalog/${kind}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    if (!res.ok) return itamThrow(res, `Failed to create ${kind}`);
    return res.json();
};
```
New functions (`fetchItamAuditLogs`, `getItamSettings`, `saveItamSettings`, `exportItamData`, `importItamData`) must follow this exact `authFetch` + `itamThrow` + `${API_BASE}/itam/...` convention, appended near the existing ITAM block (after line ~5259 region), not scattered elsewhere in the 5518-line file.

---

### Test files (backend)

**Analog:** `backend/tests/test_itam_catalog.py` (excerpt lines 1-50, full file available):
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from tests.conftest import make_test_app, make_token_data, _make_col
from authentication_service import get_current_user as real_get_current_user

class MockTenantIsolatedCollection:
    """Real `async def` proxy methods (single await chain) — never
    AsyncMock(side_effect=lambda ...) wrapping another AsyncMock."""
    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        ...
        async def _find_one(f, *args, **kwargs):
            return await raw_collection_mock.find_one({**f, "tenantId": self._tenant_id}, *args, **kwargs)
        self.find_one = _find_one
```
Use `tests/conftest.py`'s `make_test_app`/`make_token_data`/`_make_col` fixtures and this same `MockTenantIsolatedCollection` fake-db convention for `test_itam_audit.py`, `test_itam_data_csv.py`, `test_itam_customization.py` — do not invent a second mocking style (file's own docstring is explicit about this).

### Test files (frontend)

**Analog:** `src/__tests__/ITAMCatalogPanel.test.tsx`, `src/__tests__/ITAMConsole.test.tsx` (existing, Vitest) — follow their render/interaction/assert structure for the four new panel test files listed in RESEARCH.md's Wave 0 Gaps.

## Shared Patterns

### Admin-role gate
**Source:** `backend/settings_endpoints.py` lines 38-43 (`_SETTINGS_ADMIN_ROLES` / `_require_admin`)
**Apply to:** `itam_customization_endpoints.py`'s settings-write routes. Copy the literal role set verbatim — do NOT invent a fourth slightly-different set (RESEARCH.md Pitfall 4 documents 3 existing near-duplicate sets: `_SUPER_ROLES` in `audit_endpoints.py`, `_SETTINGS_ADMIN_ROLES` in `settings_endpoints.py`, `_AP_SUPER_ROLES` in `audit_program_service.py`).
```python
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
def _require_admin(user: TokenData) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")
```

### ITAM permission gate (existing endpoints being modified)
**Source:** `backend/itam_catalog_endpoints.py` lines 63-72 (`_require_itam_admin`, `manage:assets` permission)
**Apply to:** All audit-backfill edits to existing `itam_*_endpoints.py` files — keep using each file's existing `verify_permission`/`require_permission` dependency; the audit-wiring change must not alter existing auth gates.

### Audit write (log-and-continue)
**Source:** `backend/agent_remote_control.py` lines 102-114
**Apply to:** Every ITAM create/update/delete route touched by ITAM-DAT-02 (both new Phase 65 routes and the 7 backfilled existing files). Always wrap in `try/except Exception` that logs and does not fail the parent request.

### CSV generation (stdlib, not pandas)
**Source:** `backend/export_service.py::_generate_csv` lines 466-481
**Apply to:** `itam_data_service.py`'s export path — `csv.DictWriter` via `io.StringIO()`, matching the existing in-repo CSV-generation convention (RESEARCH.md explicitly rejects pandas `.to_csv()` here to match precedent).

### API client error unwrapping
**Source:** `services/apiService.ts` lines 5221-5224 (`itamThrow`)
**Apply to:** All new ITAM client functions in `apiService.ts` for this phase.

### system_settings raw-DB access (tenant-scoped + global-fallback)
**Source:** RESEARCH.md Pattern 5 (`backend/settings_endpoints.py`'s `/llm` route family, lines ~71-116, and its documented `raw = db._db if hasattr(db, "_db") else db` unwrap)
**Apply to:** `itam_customization_endpoints.py`'s `system_settings` reads/writes for `type: "itam_settings"`. Do NOT use the wrapped `db.system_settings` accessor shown in the simpler `/database` example — `system_settings` is absent from `database.py`'s `TenantIsolatedDatabase` exemption allowlist, so the wrapped accessor would silently double-apply tenant filtering (RESEARCH.md Pitfall 2).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| CSV/file-upload half of `BulkImportExportPanel.tsx` (the `<input type="file">` + `FormData` submit) | component | file-I/O | No existing ITAM (or platform) frontend component does a file upload today; `compliance_framework_mgmt_endpoints.py`'s import route is a backend analog but there's no matching frontend upload-form analog in this repo. Planner should hand-roll a standard `<input type="file">` + `FormData` + `authFetch(url, { method: 'POST', body: formData })` (no `Content-Type` header, so the browser sets the multipart boundary) — not a hard problem, just genuinely new in this codebase. |
| Lightweight locale-context provider (if i18next is NOT chosen per RESEARCH.md Open Question 2) | provider | request-response | Zero i18n infrastructure exists anywhere in the repo (confirmed in RESEARCH.md); no analog to copy from either path (i18next or hand-rolled). |

## Metadata

**Analog search scope:** `backend/` (itam_*.py, settings_endpoints.py, audit_*.py, export_service.py, compliance_framework_mgmt_endpoints.py, agent_remote_control.py, router_registry.py, rbac_utils.py), `components/itam/`, `components/TenantBrandingSettings.tsx`, `services/apiService.ts`, `backend/tests/test_itam_catalog.py`, `src/__tests__/ITAM*.test.tsx`
**Files scanned:** 17 read directly this session (in addition to the 65-RESEARCH.md sources already read in the prior session)
**Pattern extraction date:** 2026-08-12
