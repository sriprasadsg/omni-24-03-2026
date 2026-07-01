# Phase 7: Evidence Lifecycle (Staleness + Chain-of-Custody) — Pattern Map

**Mapped:** 2026-06-21
**Files analyzed:** 11 (3 new, 8 modified)
**Analogs found:** 11 / 11

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/evidence_staleness.py` | utility | transform | `backend/audit.py` (datetime+timezone pattern) | role-match |
| `backend/evidence_coc.py` | utility | CRUD (insert-only) | `backend/audit.py` (`AuditService.log_event`) | exact |
| `backend/compliance_evidence_lifecycle_endpoints.py` | controller | request-response | `backend/settings_endpoints.py` (`/api/settings/llm` GET+POST) | exact |
| `backend/compliance_evidence_endpoints.py` (modify) | controller | CRUD | itself — add CoC call sites | self-reference |
| `backend/settings_endpoints.py` (modify) | controller | request-response | itself — no change; new endpoints go to lifecycle file | self-reference |
| `backend/router_registry.py` (modify) | config | — | itself — `_load(app, "compliance_status_endpoints", ...)` at line 121 | exact |
| `backend/database.py` (modify) | config | — | itself — index block lines 246–264 | exact |
| `components/ChainOfCustodyPanel.tsx` | component | request-response | `components/AssetComplianceList.tsx` (lazy fetch pattern) | role-match |
| `components/EvidenceSettings.tsx` | component | request-response | `backend/settings_endpoints.py` LLM settings panel shape | role-match |
| `components/AssetComplianceList.tsx` (modify) | component | transform | itself — badge pattern lines 151–155 | exact |
| `components/FrameworkDetail.tsx` (modify) | component | request-response | itself — `canManageEvidence` + `expandedControlId` pattern lines 406–407, 763 | exact |
| `services/apiService.ts` (modify) | service | request-response | `services/apiService.ts` `fetchLlmSettings` (lines 911–918) | exact |

---

## Pattern Assignments

### `backend/evidence_staleness.py` (utility, transform)

**Analog:** `backend/audit.py` — datetime+timezone usage

**Imports pattern** (audit.py lines 1–3):
```python
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from database import get_database
```

**Core pattern** — staleness helper (based on confirmed codebase datetime style):
```python
from datetime import datetime, timezone, timedelta

def compute_stale(uploaded_at: str, threshold_days: int) -> dict:
    """Return stale flag and days-old for a single evidence record.
    Caller is responsible for only passing automated evidence (systemGenerated=True or source='auto').
    """
    try:
        dt = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return {"stale": False, "stale_days": 0}
    now = datetime.now(timezone.utc)
    age_days = (now - dt).days
    return {"stale": age_days >= threshold_days, "stale_days": age_days}


async def get_staleness_threshold(db, tenant_id) -> int:
    """Fetch per-tenant staleness threshold with global fallback. Returns int (default 7)."""
    raw = db._db if hasattr(db, "_db") else db
    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "evidence_staleness", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("thresholdDays"), int):
            return doc["thresholdDays"]
    doc = await raw.system_settings.find_one(
        {"type": "evidence_staleness", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("thresholdDays"), int):
        return doc["thresholdDays"]
    return 7
```

**Key analog note:** `settings_endpoints.py` lines 71–82 show the exact `_get_raw_llm_settings` pattern (tenant-specific first, global fallback) — copy that structure for `get_staleness_threshold`. The `raw = db._db if hasattr(db, "_db") else db` idiom is used at lines 73, 118, 279 of `settings_endpoints.py`.

---

### `backend/evidence_coc.py` (utility, CRUD insert-only)

**Analog:** `backend/audit.py` (`AuditService.log_event`, lines 10–46)

**Imports pattern** (audit.py lines 1–4):
```python
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from database import get_database
import logging
```

**Core pattern** — immutable append (audit.py lines 28–46):
```python
# audit.py lines 29-41 — the insert_one + fire-and-forget pattern to copy:
async def log_event(...) -> bool:
    try:
        db = get_database()
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            ...
            "tenantId": tenant_id
        }
        await db.audit_logs.insert_one(event)
        self.logger.info(...)
        return True
    except Exception as e:
        self.logger.error(f"Failed to write audit log: {e}")
        return False
```

**Adaptation for `evidence_coc.py`:** Replace `db.audit_logs` with `db._db.evidence_audit_log` (raw Motor, bypassing `TenantIsolatedCollection.insert_one` which would auto-inject `tenantId` from context and conflict with the explicit `tenantId` we set). Never raises — fire-and-forget. Use `return None` instead of `return bool`. Add `snapshot_before` and `snapshot_after` fields not present in `audit.py`.

**Full function signature to implement:**
```python
async def _append_coc_entry(
    db,
    evidence_id: str,
    tenant_id: str,
    actor: str,
    action_type: str,        # "create" | "delete" | "update"
    snapshot_before: dict | None,
    snapshot_after: dict | None,
) -> None:
    """Append an immutable chain-of-custody entry. Fire-and-forget; never raises."""
    try:
        raw = db._db if hasattr(db, "_db") else db
        await raw.evidence_audit_log.insert_one({
            "evidenceId":      evidence_id,
            "tenantId":        tenant_id,
            "actor":           actor,
            "action_type":     action_type,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "snapshot_before": snapshot_before,
            "snapshot_after":  snapshot_after,
        })
    except Exception as e:
        logging.getLogger(__name__).error("CoC append failed: %s", e)
```

---

### `backend/compliance_evidence_lifecycle_endpoints.py` (controller, request-response)

**Analog:** `backend/settings_endpoints.py` — the `GET /api/settings/llm` + `POST /api/settings/llm` pair (lines 85–149)

**Imports pattern** (settings_endpoints.py lines 1–12):
```python
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
```

**Router declaration pattern** (settings_endpoints.py line 36):
```python
router = APIRouter(prefix="/api/settings", tags=["Settings"])
```
For the new file, use `router = APIRouter()` without a prefix since it serves two URL spaces (`/api/settings/evidence-staleness` and `/api/compliance/evidence/{id}/audit-log`).

**`_require_admin` pattern** (settings_endpoints.py lines 38–43):
```python
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}

def _require_admin(user: TokenData) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")
```
Copy `_SETTINGS_ADMIN_ROLES` and `_require_admin` verbatim into the new file (do NOT import from `settings_endpoints.py` — keep the file self-contained).

**Per-tenant GET + upsert PATCH pattern** (settings_endpoints.py lines 113–148 for POST /llm):
```python
# settings_endpoints.py lines 117–148
_require_admin(current_user)
db = get_database()
raw = db._db if hasattr(db, "_db") else db
tenant_id = getattr(current_user, "tenant_id", None)

settings["type"] = "llm"
if _is_super_admin(current_user):
    await raw.system_settings.update_one(
        {"type": "llm", "tenantId": {"$exists": False}},
        {"$set": settings}, upsert=True,
    )
else:
    settings["tenantId"] = tenant_id
    await raw.system_settings.update_one(
        {"type": "llm", "tenantId": tenant_id},
        {"$set": settings}, upsert=True,
    )
```
For the PATCH staleness endpoint, adapt: use `{"type": "evidence_staleness"}` and `Field(ge=1, le=365)` on the Pydantic model. Non-admin GET is allowed (threshold is not sensitive) — omit `_require_admin` from the GET handler.

**Pydantic validation pattern** (used throughout settings_endpoints.py):
```python
from pydantic import BaseModel, Field

class StalenessThresholdUpdate(BaseModel):
    thresholdDays: int = Field(ge=1, le=365)
```

**CoC GET endpoint pattern** — mirror `get_all_compliance_evidence` (compliance_evidence_endpoints.py lines 123–146) for tenant isolation + raw Motor access:
```python
# compliance_evidence_endpoints.py lines 127-146 — tenant isolation pattern
user_role = getattr(current_user, "role", "")
is_super_admin = user_role in {"Super Admin", "superadmin", "super_admin", "platform-admin"}
if is_super_admin:
    query: dict = {}
else:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return []
    query = {"tenantId": tenant_id}
```
For the CoC GET, use `db._db.evidence_audit_log.find(query, {"_id": 0}).sort("timestamp", 1)` and `.to_list(length=500)`.

**Error handling pattern** (compliance_evidence_endpoints.py lines 116–120):
```python
except HTTPException:
    raise
except Exception as e:
    logger.error("...: %s", e)
    raise HTTPException(status_code=500, detail="Internal server error")
```

---

### `backend/compliance_evidence_endpoints.py` (modify — add CoC call sites)

**Analog:** itself — the 4 mutation functions

**CoC call-site pattern** — place AFTER the successful DB write `await`, BEFORE `return`:

For `upload_compliance_evidence` (after line 112 `upsert=True` call):
```python
# After: await db.asset_compliance.update_one(..., upsert=True)
from evidence_coc import _append_coc_entry
await _append_coc_entry(
    db=db,
    evidence_id=evidence_record["id"],
    tenant_id=tenant_id,
    actor=uploader,
    action_type="create",
    snapshot_before=None,
    snapshot_after=evidence_record,
)
```

For `delete_compliance_evidence` (after line 284 `$pull` `update_one`):
```python
# After: await db.asset_compliance.update_one({"assetId": asset_id, "evidence.id": evidence_id}, {"$pull": ...})
await _append_coc_entry(
    db=db,
    evidence_id=evidence_id,
    tenant_id=doc_tenant or caller_tenant or "",
    actor=caller_username,
    action_type="delete",
    snapshot_before=ev,
    snapshot_after=None,
)
```

For `upload_control_direct_evidence` (after line 367 `insert_one`):
```python
# After: await db.control_evidence.insert_one({**record})
await _append_coc_entry(db=db, evidence_id=record["id"], tenant_id=tenant_id,
    actor=uploader, action_type="create", snapshot_before=None, snapshot_after=record)
```

For `delete_control_direct_evidence` (after line 438 `delete_one`):
```python
# After: await db.control_evidence.delete_one({"id": evidence_id})
await _append_coc_entry(db=db, evidence_id=evidence_id,
    tenant_id=record.get("tenantId", ""), actor=caller_username,
    action_type="delete", snapshot_before=record, snapshot_after=None)
```

**Staleness injection call-site** — in `get_control_evidence` (lines 378–413), fetch threshold once before the loop and inject:
```python
# Before building manual_docs / system_docs lists — fetch threshold once:
from evidence_staleness import get_staleness_threshold, compute_stale
threshold = await get_staleness_threshold(db, tenant_id)

# After building system_docs list, iterate and inject:
for ev in system_docs:
    is_auto = ev.get("systemGenerated") or ev.get("source") == "auto"
    if is_auto:
        r = compute_stale(ev.get("uploadedAt") or ev.get("uploaded_at", ""), threshold)
        ev["stale"] = r["stale"]
        ev["stale_days"] = r["stale_days"]
    else:
        ev["stale"] = False
        ev["stale_days"] = 0
```
Apply the same injection loop for `manual_docs` (always `stale=False, stale_days=0` since `source='manual'`).

---

### `backend/router_registry.py` (modify — register new router)

**Analog:** itself — line 121 is the closest adjacent entry point:

```python
# router_registry.py line 119-122 — existing compliance block:
_load(app, "compliance_endpoints",      "router")
_load(app, "compliance_scans_endpoints", "router")
_load(app, "compliance_status_endpoints",  "router")
_load(app, "ai_auditor_endpoints",      "router", prefix="/api/compliance", tags=["Compliance AI"])
```

**Add after line 128** (`compliance_remediation_endpoints`):
```python
_load(app, "compliance_evidence_lifecycle_endpoints", "router")
```

This uses the standard `_load(app, module_name, "router")` pattern. No prefix kwargs needed — the new file declares full URL paths.

---

### `backend/database.py` (modify — add indexes)

**Analog:** itself — lines 246–264, compound index block pattern:

```python
# database.py lines 246-264 — copy the two-index pattern per collection:
await mongodb.db.compliance_evidence.create_index("tenantId")
await mongodb.db.compliance_evidence.create_index("controlId")
...
await mongodb.db.compliance_evidence.create_index([("tenantId", 1), ("controlId", 1)])
```

**Add after line 264** (after the `compliance_evidence` compound index):
```python
# evidence_audit_log: CoC collection — no TTL (compliance audit trail must be long-lived)
await mongodb.db.evidence_audit_log.create_index([("evidenceId", 1), ("tenantId", 1)])
await mongodb.db.evidence_audit_log.create_index([("tenantId", 1), ("timestamp", -1)])
```

---

### `components/ChainOfCustodyPanel.tsx` (new component, request-response)

**Analog:** `components/AssetComplianceList.tsx` — `useState` + async fetch + loading/error state pattern (lines 1–75)

**Imports pattern** (AssetComplianceList.tsx lines 1–5):
```tsx
import React, { useState } from 'react';
import { Asset, AssetCompliance, Control } from '../types';
import { CheckIcon, XIcon, AlertCircleIcon, ... } from './icons';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
```

**Lazy fetch on expand pattern** (mirror AssetComplianceList.tsx `handleDeleteEvidence` async state pattern, lines 64–75):
```tsx
const [entries, setEntries] = useState<any[]>([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);

React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.fetchEvidenceAuditLog(evidenceId)
        .then(data => { if (!cancelled) setEntries(data.entries ?? []); })
        .catch(() => { if (!cancelled) setError('Failed to load audit log'); })
        .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
}, [evidenceId]);
```

**Permission gate pattern** (FrameworkDetail.tsx lines 406–407):
```tsx
const { hasPermission } = useUser();
const canViewCoC = hasPermission('view:audit_log');
// Gate render: {canViewCoC && <ChainOfCustodyPanel ... />}
```
Use `'view:audit_log'` — NOT `'audit:read'` (see RESEARCH.md Pitfall 3).

**Badge/row pattern** (AssetComplianceList.tsx lines 151–155):
```tsx
<span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
    Automated
</span>
```
Use same `px-1.5 py-0.5 text-xs font-semibold rounded-full` base for CoC entry type badges.

---

### `components/EvidenceSettings.tsx` (new component, request-response)

**Analog:** `components/SettingsDashboard.tsx` — the infrastructure panel shape (tab content area pattern, lines 287–303)

**Imports pattern:**
```tsx
import React, { useState, useEffect } from 'react';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
```

**Fetch-on-mount + controlled-input + save pattern** — mirror any tab panel in SettingsDashboard.tsx that calls GET+PATCH:
```tsx
const [threshold, setThreshold] = useState<number>(7);
const [saving, setSaving] = useState(false);

useEffect(() => {
    api.fetchStalenessThreshold().then(d => setThreshold(d.thresholdDays ?? 7));
}, []);

const handleSave = async () => {
    setSaving(true);
    try {
        await api.saveStalenessThreshold(threshold);
        showToast('Evidence staleness threshold saved', 'success');
    } catch {
        showToast('Failed to save threshold', 'error');
    } finally {
        setSaving(false);
    }
};
```

**Input validation pattern** — enforce 1–365 client-side before sending (mirrors the Pydantic `ge=1, le=365` server-side rule):
```tsx
<input
    type="number"
    min={1}
    max={365}
    value={threshold}
    onChange={e => setThreshold(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))}
    className="..."
/>
```

---

### `components/AssetComplianceList.tsx` (modify — add stale badge)

**Analog:** itself — lines 151–155 (existing "Automated" / "Manual" badge pattern)

**Existing badge pattern to extend** (lines 150–155):
```tsx
<div className="flex items-center gap-1 flex-shrink-0">
    {isAutomated ? (
        <span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">Automated</span>
    ) : (
        <span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">Manual</span>
    )}
```

**Add stale badge immediately after the Automated/Manual badge** (same `flex items-center gap-1` container):
```tsx
{isAutomated && ev.stale && (
    <span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 flex items-center gap-0.5">
        <ClockIcon size={10} className="mr-0.5" />Stale
    </span>
)}
```
`ClockIcon` is already imported in `FrameworkDetail.tsx` line 6 — confirm it is exported from `./icons` before using here, or use `AlertCircleIcon` (already imported in AssetComplianceList.tsx line 3).

The `ev.stale` field is injected by the backend GET response — no frontend computation needed.

---

### `components/FrameworkDetail.tsx` (modify — mount ChainOfCustodyPanel)

**Analog:** itself — lines 406–407 (`canManageEvidence`) and lines 763–766 (`expandedControlId` mount pattern)

**Permission declaration pattern** (lines 406–407):
```tsx
const { hasPermission } = useUser();
const canManageEvidence = hasPermission('manage:compliance_evidence');
// ADD:
const canViewCoC = hasPermission('view:audit_log');
```

**Mount pattern** (lines 763–766):
```tsx
{expandedControlId === control.id && (
    <div className="...">
        <AssetComplianceList
            ...
        />
        {/* ADD below AssetComplianceList: */}
        {canViewCoC && (
            <ChainOfCustodyPanel controlId={control.id} />
        )}
    </div>
)}
```

**Import addition** (line 4, after AssetComplianceList import):
```tsx
import { ChainOfCustodyPanel } from './ChainOfCustodyPanel';
```

---

### `services/apiService.ts` (modify — add 3 new API functions)

**Analog:** itself — `fetchLlmSettings` (lines 911–918) for GET pattern; `saveInfrastructure` (lines 2603–2618) for PATCH pattern

**GET pattern** (fetchLlmSettings, lines 911–918):
```typescript
export const fetchLlmSettings = async () => {
    try {
        const res = await authFetch(`${API_BASE}/settings/llm`);
        return await res.json();
    } catch {
        return null;
    }
};
```

**Three new functions to add** (copy fetchLlmSettings structure):
```typescript
export const fetchStalenessThreshold = async (): Promise<{ thresholdDays: number }> => {
    try {
        const res = await authFetch(`${API_BASE}/settings/evidence-staleness`);
        return await res.json();
    } catch {
        return { thresholdDays: 7 };
    }
};

export const saveStalenessThreshold = async (thresholdDays: number): Promise<void> => {
    const res = await authFetch(`${API_BASE}/settings/evidence-staleness`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thresholdDays }),
    });
    if (!res.ok) throw new Error('Failed to save staleness threshold');
};

export const fetchEvidenceAuditLog = async (evidenceId: string): Promise<{ entries: any[] }> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/evidence/${evidenceId}/audit-log`);
        if (!res.ok) return { entries: [] };
        return await res.json();
    } catch {
        return { entries: [] };
    }
};
```

---

## Shared Patterns

### Authentication / Tenant Isolation
**Source:** `backend/compliance_evidence_endpoints.py` lines 47–55, 159–163
**Apply to:** `compliance_evidence_lifecycle_endpoints.py` (all endpoints)
```python
user_role = getattr(current_user, "role", "")
is_super = user_role in _SUPER_ROLES
tenant_id = getattr(current_user, "tenant_id", None)

if not is_super:
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    query["tenantId"] = tenant_id
```

### Admin Guard
**Source:** `backend/settings_endpoints.py` lines 38–43
**Apply to:** PATCH `/api/settings/evidence-staleness` in `compliance_evidence_lifecycle_endpoints.py`
```python
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}

def _require_admin(user) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")
```

### Raw DB Access for `system_settings`
**Source:** `backend/settings_endpoints.py` lines 73, 118, 279
**Apply to:** `evidence_staleness.py` (`get_staleness_threshold`), `compliance_evidence_lifecycle_endpoints.py` (PATCH)
```python
raw = db._db if hasattr(db, "_db") else db
await raw.system_settings.update_one(...)
```

### Error Handling
**Source:** `backend/compliance_evidence_endpoints.py` lines 116–120
**Apply to:** All endpoints in `compliance_evidence_lifecycle_endpoints.py`
```python
except HTTPException:
    raise
except Exception as e:
    logger.error("...: %s", e)
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Frontend Permission Check
**Source:** `components/FrameworkDetail.tsx` lines 406–407
**Apply to:** `ChainOfCustodyPanel.tsx` (gate rendering), `EvidenceSettings.tsx` (gate save button)
```tsx
const { hasPermission } = useUser();
const canViewCoC = hasPermission('view:audit_log');  // NOT 'audit:read'
```

### `router_registry.py` `_load` Pattern
**Source:** `backend/router_registry.py` lines 24–39
**Apply to:** New `_load(app, "compliance_evidence_lifecycle_endpoints", "router")` entry
```python
def _load(app: FastAPI, module_name: str, attr: str = "router", **kwargs) -> None:
    try:
        mod = importlib.import_module(module_name)
        app.include_router(getattr(mod, attr), **kwargs)
    except Exception as exc:
        logger.error("[Router] Failed to load %s: %s", module_name, exc)
        if module_name in _REQUIRED_ROUTERS:
            raise
```

### Test Mock Pattern
**Source:** `backend/tests/test_core_endpoints.py` lines 25–50
**Apply to:** `backend/tests/test_evidence_lifecycle.py`
```python
def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app

def _col(**kw):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.find = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    for k, v in kw.items():
        setattr(col, k, v)
    return col
```

---

## No Analog Found

All files have analogs. No entries.

---

## Critical Implementation Notes

1. **`TenantIsolatedCollection.insert_one` auto-injects `tenantId`** from context (database.py lines 47–54). For `_append_coc_entry`, use `db._db.evidence_audit_log.insert_one(...)` (raw Motor) to avoid double-injecting `tenantId`. We set `tenantId` explicitly in the document.

2. **`FrameworkDetail.tsx` is at 854 lines** — already over CLAUDE.md's 500-line limit (existing violation). Minimize additions: only import + one permission const + one mount expression. All panel logic goes in `ChainOfCustodyPanel.tsx`.

3. **`SettingsDashboard.tsx` is at 529 lines** — already over limit. Add only `'evidence'` to `SettingsView` type, one tab button, and one `{activeView === 'evidence' && <EvidenceSettings />}` render. All UI logic goes in `EvidenceSettings.tsx`.

4. **Staleness threshold fetch: one call per GET request**, not per evidence item. Fetch `threshold = await get_staleness_threshold(db, tenant_id)` once, then iterate.

5. **`'view:audit_log'` is the correct permission string** (types.ts line 205). Never use `'audit:read'`.

6. **Index registration goes in `database.py`** lines ~265 (after the `compliance_evidence` compound index). No TTL for `evidence_audit_log` — compliance audit trails must not expire.

---

## Metadata

**Analog search scope:** `backend/`, `components/`, `services/`
**Files scanned:** 12 (compliance_evidence_endpoints.py, settings_endpoints.py, router_registry.py, database.py, audit.py, AssetComplianceList.tsx, FrameworkDetail.tsx, SettingsDashboard.tsx, apiService.ts, test_core_endpoints.py, test_alerts_and_ai.py, auth_types.py)
**Pattern extraction date:** 2026-06-21
