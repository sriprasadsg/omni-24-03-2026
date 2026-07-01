# Phase 2: Manual Evidence Uploads - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 8 new/modified files (backend endpoint, frontend component, API service additions, delete handler)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/compliance_evidence_endpoints.py` | controller | file-I/O + CRUD | `backend/compliance_artifacts_endpoints.py` | exact |
| `backend/compliance_evidence_endpoints.py` (DELETE handler) | controller | CRUD | `backend/knowledge_endpoints.py` lines 291-304 | role-match |
| `components/AssetComplianceList.tsx` (evidence delete button) | component | request-response | `components/AssetComplianceList.tsx` existing upload button | exact |
| `services/apiService.ts` (deleteEvidence, listEvidence) | service | request-response | `services/apiService.ts` `uploadComplianceEvidence` lines 633-646 | exact |
| `backend/compliance_artifacts_endpoints.py` (reference) | controller | file-I/O + CRUD | self | reference |

---

## Pattern Assignments

### 1. File Upload Endpoint

**Analog:** `backend/compliance_evidence_endpoints.py` lines 21-84 (the existing `upload_compliance_evidence` handler)

This endpoint ALREADY EXISTS and handles `POST /api/assets/{asset_id}/compliance/evidence`. New work must not duplicate it — extend it or add sibling routes.

**Imports pattern** (lines 1-13):
```python
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import FileResponse, Response
import asyncio
import logging
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from compliance_artifacts_endpoints import UPLOAD_DIR, _write_binary, _ALLOWED_UPLOAD_EXTENSIONS, _ALLOWED_UPLOAD_MIME_PREFIXES
```

**Core upload pattern** (lines 21-84):
```python
@router.post("/api/assets/{asset_id}/compliance/evidence")
async def upload_compliance_evidence(
    asset_id: str,
    file: UploadFile = File(...),
    control_id: str = Form(...),
    current_user=Depends(get_current_user),
):
    try:
        # Tenant ownership check — non-admins only
        user_role = getattr(current_user, "role", "")
        if user_role not in _SUPER_ROLES:
            tenant_id = getattr(current_user, "tenant_id", None) or ""
            db = get_database()
            asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
            if not asset:
                raise HTTPException(status_code=403, detail="Asset not found in your tenant")

        # Whitelist extension and MIME type
        file_ext = os.path.splitext(file.filename or "")[1].lower()
        if file_ext and file_ext not in _ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type '{file_ext}' is not allowed.")
        content_type = (file.content_type or "").split(";")[0].strip()
        if content_type and not any(content_type.startswith(p) for p in _ALLOWED_UPLOAD_MIME_PREFIXES):
            raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' is not allowed.")

        safe_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        file_content = await file.read()
        await asyncio.to_thread(_write_binary, file_path, file_content)

        file_url = f"/static/evidence/{safe_filename}"
        timestamp = datetime.now(timezone.utc).isoformat()

        evidence_record = {
            "id": f"ev-{timestamp}",
            "name": file.filename,
            "url": file_url,
            "type": file.content_type,
            "uploadedAt": timestamp,
            "assetId": asset_id,
            "controlId": control_id,
        }

        db = get_database()
        await db.asset_compliance.update_one(
            {"assetId": asset_id, "controlId": control_id},
            {
                "$set": {"status": "Pending_Review", "lastUpdated": timestamp},
                "$push": {"evidence": evidence_record},
            },
            upsert=True,
        )
        return {"success": True, "evidence": evidence_record}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Key notes:**
- File size limit is NOT enforced in this handler. The artifacts endpoint (`compliance_artifacts_endpoints.py` line 94) enforces `50 * 1024 * 1024` — add the same check here.
- Use `asyncio.to_thread(_write_binary, file_path, file_content)` for async-safe disk writes (not `open()` directly).
- `_write_binary` and `UPLOAD_DIR` are defined in `compliance_artifacts_endpoints.py` and imported — do not redeclare.

---

### 2. Evidence Delete Endpoint (NEW — does not exist yet)

**Analog:** `backend/knowledge_endpoints.py` lines 291-304

**Pattern to follow:**
```python
@router.delete("/api/assets/{asset_id}/compliance/evidence/{evidence_id}")
async def delete_compliance_evidence(
    asset_id: str,
    evidence_id: str,
    current_user=Depends(rbac_service.has_permission("manage:compliance_evidence")),
):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)

    # Tenant ownership check (mirror of upload handler)
    user_role = getattr(current_user, "role", "")
    if user_role not in _SUPER_ROLES:
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
        if not asset:
            raise HTTPException(status_code=403, detail="Asset not found in your tenant")

    # Pull the evidence item from the array
    result = await db.asset_compliance.update_one(
        {"assetId": asset_id, "evidence.id": evidence_id},
        {"$pull": {"evidence": {"id": evidence_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Also remove the file from disk if it was a user-uploaded file
    # (lookup the record before pulling — or use find+update pipeline)
    return {"success": True}
```

**RBAC:** Use `rbac_service.has_permission("manage:compliance_evidence")` — this permission is already defined for `admin` and `Tenant Admin` roles in `rbac_service.py` lines 17 and 32.

**File cleanup:** Before `$pull`, query the evidence record to get its `url`, derive the filename, and `Path(UPLOAD_DIR / filename).unlink()` if it exists on disk. Confine to `UPLOAD_DIR` using path traversal check (see download endpoint `compliance_evidence_endpoints.py` lines 156-160).

---

### 3. Evidence Schema — `asset_compliance.evidence[]` Array

**Source:** `backend/compliance_evidence_endpoints.py` lines 55-63 (manual upload record) and `backend/compliance_evidence_processor.py` lines 234-246 (auto-generated record)

**Manual upload evidence record fields:**
```python
{
    "id": f"ev-{timestamp}",          # string, primary key within array
    "name": file.filename,             # original filename shown in UI
    "url": f"/static/evidence/{safe_filename}",  # download URL path
    "type": file.content_type,         # MIME type
    "uploadedAt": timestamp,           # ISO-8601 UTC string
    "assetId": asset_id,
    "controlId": control_id,
    # NOT present: systemGenerated, content (those are for auto-generated)
}
```

**Auto-generated evidence record fields (for contrast):**
```python
{
    "id": evidence_id,
    "name": f"System Check: {check_name}",
    "url": "#",                        # sentinel: no file on disk
    "systemGenerated": True,           # frontend discriminates on this
    "content": evidence_content,       # markdown string rendered by EvidenceMarkdownViewer
    "tenantId": tenant_id,
    ...
}
```

**Frontend discriminates** at `AssetComplianceList.tsx` line 93:
```tsx
{ev.systemGenerated || ev.url === '#' || ev.evidence_content || ev.content ? (
    <EvidenceMarkdownViewer ... />
) : (
    <a href={`/api/compliance/evidence/download/${ev.id || ev.evidence_id}`} ...>
```

New manual evidence records must NOT set `systemGenerated: True` or `url: "#"` — those are auto-generated sentinels.

---

### 4. Tenant Isolation Pattern

**Source:** `backend/compliance_evidence_endpoints.py` lines 29-36 (asset ownership check) and lines 87-110 (list endpoint scoping)

**Standard pattern — non-admin asset ownership check:**
```python
_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

user_role = getattr(current_user, "role", "")
if user_role not in _SUPER_ROLES:
    tenant_id = getattr(current_user, "tenant_id", None) or ""
    db = get_database()
    asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
    if not asset:
        raise HTTPException(status_code=403, detail="Asset not found in your tenant")
```

**Standard pattern — list scoping:**
```python
is_super_admin = user_role in {"Super Admin", "superadmin", "super_admin", "platform-admin"}
if is_super_admin:
    query: dict = {}
else:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return []
    tenant_asset_ids = await db.assets.distinct("id", {"tenantId": tenant_id})
    query = {"assetId": {"$in": tenant_asset_ids}}
```

**Anti-pattern to avoid:** `problem_management_endpoints.py` uses a `_tenant()` helper function and a separate `tenant_context` import. The compliance module uses inline `getattr(current_user, "tenant_id", None)` — stay consistent with the compliance module pattern.

---

### 5. Auth Pattern

**Source:** `backend/authentication_service.py` lines 169-171, `backend/rbac_service.py` lines 115-129

**Two dependency options:**

Option A — basic auth only (used in existing evidence endpoints):
```python
current_user=Depends(get_current_user)
# Returns TokenData with .role, .tenant_id, .username, .email
```

Option B — RBAC permission gate (preferred for write/delete operations):
```python
from rbac_service import rbac_service
current_user: TokenData = Depends(rbac_service.has_permission("manage:compliance_evidence"))
```

**Accessing user fields:**
```python
user_role   = getattr(current_user, "role", "")
tenant_id   = getattr(current_user, "tenant_id", None)
uploader    = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
```

Use `getattr` with defaults — `TokenData` attributes may be absent in test contexts.

---

### 6. Frontend Evidence Rendering

**Source:** `components/AssetComplianceList.tsx` lines 88-137

The evidence column iterates `statusRecord.evidence[]` and branches on `systemGenerated`/`url`:

```tsx
{statusRecord?.evidence?.length ? (
    <div className="flex flex-col space-y-3">
        {statusRecord.evidence.map((ev: any, idx: number) => (
            <div key={`${ev.id || ev.evidence_id}-${idx}`}>
                {ev.systemGenerated || ev.url === '#' || ev.evidence_content || ev.content ? (
                    <EvidenceMarkdownViewer evidence={{ id, name, content, details }} />
                ) : (
                    <a href={`/api/compliance/evidence/download/${ev.id || ev.evidence_id}`}
                       target="_blank" rel="noopener noreferrer"
                       className="flex items-center text-blue-600 hover:text-blue-500 text-xs">
                        <FileTextIcon size={12} className="mr-1" />
                        {ev.name || ev.check_name || "Evidence Document"}
                    </a>
                )}
            </div>
        ))}
    </div>
) : (
    <span className="text-gray-400 italic text-xs">No evidence attached</span>
)}
```

**To add a delete button** per evidence item: insert it inside the `<div key=...>` after the link/viewer, using the same icon-button pattern as the existing status buttons (lines 140-149):
```tsx
<button
    onClick={() => onDeleteEvidence(asset.id, control_id, ev.id || ev.evidence_id)}
    className="text-red-400 hover:text-red-600"
    title="Delete evidence"
    disabled={ev.systemGenerated}   // block deletion of auto-generated evidence
>
    <TrashIcon size={12} />
</button>
```

**Props interface** (line 6-13) will need `onDeleteEvidence` added:
```tsx
onDeleteEvidence: (assetId: string, controlId: string, evidenceId: string) => Promise<void>;
```

---

### 7. File Upload — Frontend Pattern

**Source:** `components/AssetComplianceList.tsx` lines 15-44 and lines 156-163

Hidden `<input type="file">` pattern + ref click:
```tsx
const fileInputRef = React.useRef<HTMLInputElement>(null);
const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

const handleUploadClick = (assetId: string) => {
    setSelectedAssetId(assetId);
    fileInputRef.current?.click();
};

const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !selectedAssetId) return;
    // ... call upload handler ...
    if (fileInputRef.current) fileInputRef.current.value = ''; // reset
};

// In JSX:
<input type="file" ref={fileInputRef} className="hidden"
    onChange={handleFileChange}
    accept=".txt,.md,.json,.csv,.log,.pdf" />
```

---

### 8. Frontend API Service — Upload and Delete

**Source:** `services/apiService.ts` lines 633-646 (existing `uploadComplianceEvidence`)

**Existing upload function:**
```typescript
export const uploadComplianceEvidence = async (assetId: string, controlId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('controlId', controlId);

    const res = await authFetch(`${API_BASE}/assets/${assetId}/compliance/evidence`, {
        method: 'POST',
        headers: { 'Content-Type': 'multipart/form-data' },
        body: formData
    });

    if (!res.ok) throw new Error("Evidence upload failed");
    return await res.json();
};
```

**WARNING — existing bug:** `headers: { 'Content-Type': 'multipart/form-data' }` is incorrect for multipart. The `authFetch` helper at lines 206-208 already strips `Content-Type` for `FormData` bodies. The manual override re-adds it without the boundary, which will cause server-side parse failures. When implementing the delete function, do NOT set `Content-Type` for FormData requests — let `authFetch` handle it automatically.

**New delete function to add** (follow the same pattern):
```typescript
export const deleteComplianceEvidence = async (
    assetId: string,
    controlId: string,
    evidenceId: string,
): Promise<void> => {
    const res = await authFetch(
        `${API_BASE}/assets/${assetId}/compliance/evidence/${evidenceId}`,
        { method: 'DELETE' }
    );
    if (!res.ok) throw new Error("Evidence delete failed");
};
```

---

### 9. Delete Endpoint — Existing Pattern Reference

**Source:** `backend/knowledge_endpoints.py` lines 291-304 and `backend/tickets_endpoints.py` lines 466-493

**Knowledge doc delete (simplest):**
```python
@router.delete("/docs/{doc_id}")
async def delete_doc(
    doc_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    result = await db.knowledge_docs.delete_one({"id": doc_id, "tenantId": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True}
```

**Ticket attachment delete** (with disk cleanup, lines 466-493) — use this as model for evidence delete since both involve removing a file from the `static/evidence/` directory and pulling from a sub-array.

---

## Shared Patterns

### Authentication
**Source:** `backend/authentication_service.py` lines 169-171
**Apply to:** All new backend endpoints
```python
from authentication_service import get_current_user
current_user=Depends(get_current_user)
```

### RBAC Permission Gate
**Source:** `backend/rbac_service.py` lines 115-129
**Apply to:** DELETE endpoint; POST endpoint can use plain `get_current_user` with inline ownership check (matches existing upload endpoint pattern)
```python
from rbac_service import rbac_service
current_user: TokenData = Depends(rbac_service.has_permission("manage:compliance_evidence"))
```
The `manage:compliance_evidence` permission is already defined for `admin` and `Tenant Admin` roles.

### Super Admin Role Set
**Source:** `backend/compliance_evidence_endpoints.py` line 18
**Apply to:** All compliance evidence endpoints that branch on tenant scope
```python
_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
```

### Error Handling
**Source:** `backend/compliance_evidence_endpoints.py` lines 80-84
**Apply to:** All new endpoints
```python
except HTTPException:
    raise
except Exception as e:
    logger.error("Upload error: %s", e)
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Path Traversal Guard (disk file access)
**Source:** `backend/compliance_evidence_endpoints.py` lines 156-160
**Apply to:** Any endpoint that reads a file from `UPLOAD_DIR` by name derived from DB
```python
_safe_dir = Path(UPLOAD_DIR).resolve()
file_path_resolved = (_safe_dir / possible_filename).resolve()
if not str(file_path_resolved).startswith(str(_safe_dir)):
    raise HTTPException(status_code=400, detail="Invalid file path")
```

### File I/O — async-safe write
**Source:** `backend/compliance_artifacts_endpoints.py` lines 58-60, 120
**Apply to:** Any new file-write path
```python
def _write_binary(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)

await asyncio.to_thread(_write_binary, file_path, file_content)
```
`_write_binary` is already imported from `compliance_artifacts_endpoints` in the evidence endpoint — do not redeclare.

### MongoDB $push evidence
**Source:** `backend/compliance_evidence_endpoints.py` lines 66-76
```python
await db.asset_compliance.update_one(
    {"assetId": asset_id, "controlId": control_id},
    {
        "$set": {"status": "Pending_Review", "lastUpdated": timestamp},
        "$push": {"evidence": evidence_record},
    },
    upsert=True,
)
```

### MongoDB $pull evidence
**Source:** `backend/compliance_evidence_processor.py` lines 248-251
```python
await db.asset_compliance.update_one(
    {"assetId": asset_id, "controlId": control_id},
    {"$pull": {"evidence": {"name": f"System Check: {check_name}"}}},
)
```
For delete by ID: `{"$pull": {"evidence": {"id": evidence_id}}}`

---

## Router Registration

**Source:** `backend/compliance_endpoints.py` lines 1-18

All compliance sub-routers are included here. New routes added to `compliance_evidence_endpoints.py` are automatically registered via:
```python
from compliance_evidence_endpoints import router as evidence_router
router.include_router(evidence_router)
```
No changes needed to `router_registry.py` or `compliance_endpoints.py` if new endpoints go into `compliance_evidence_endpoints.py`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Evidence delete with disk cleanup | controller | CRUD + file-I/O | Partial analog exists in `tickets_endpoints.py` lines 466-493 but for a different collection structure (sub-document array vs standalone record) |

---

## Anti-Patterns to Avoid

1. **Wrong `Content-Type` for FormData** — `services/apiService.ts` line 640 incorrectly sets `'Content-Type': 'multipart/form-data'` without boundary. `authFetch` already omits `Content-Type` for `FormData` (line 208); do not override it.

2. **Duplicating `_write_binary` / `UPLOAD_DIR`** — These are defined once in `compliance_artifacts_endpoints.py` and imported by `compliance_evidence_endpoints.py`. Adding them a third time creates drift risk.

3. **Inconsistent tenant scope sets** — The codebase has at least two slightly different `_SUPER_ROLES` sets (lines 18 and 92 of `compliance_evidence_endpoints.py` use different string sets). Use the set at line 18 (`{"Super Admin", "super_admin", "admin", "platform-admin"}`) as the canonical definition for new code.

4. **`$pull` on systemGenerated evidence** — The `compliance_evidence_processor.py` uses `$pull` by name to replace auto-generated evidence records. Manual delete must match only on `id` and must reject attempts to delete records with `systemGenerated: true` (guard at both API and UI layer).

5. **Missing file size check in `upload_compliance_evidence`** — The existing handler at `compliance_evidence_endpoints.py` reads the file without enforcing a size cap. When extending this endpoint, add `if len(file_content) > 50 * 1024 * 1024: raise HTTPException(413, ...)` matching `compliance_artifacts_endpoints.py` line 94.

---

## Metadata

**Analog search scope:** `backend/*.py`, `components/*.tsx`, `services/apiService.ts`
**Key files read:** `compliance_evidence_endpoints.py`, `compliance_artifacts_endpoints.py`, `compliance_evidence_processor.py`, `authentication_service.py`, `rbac_service.py`, `knowledge_endpoints.py`, `tickets_endpoints.py`, `components/AssetComplianceList.tsx`, `services/apiService.ts`, `database.py`
**Pattern extraction date:** 2026-06-17
