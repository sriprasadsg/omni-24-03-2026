# Phase 2: Manual Evidence Uploads — Research

**Researched:** 2026-06-17
**Domain:** File upload, compliance evidence management, multi-tenant FastAPI + React
**Confidence:** HIGH

---

## Summary

Phase 2 is primarily a gap-closing exercise, not greenfield development. A substantial
fraction of the required infrastructure already exists across two backend endpoints
(`compliance_evidence_endpoints.py` and `compliance_artifacts_endpoints.py`) and in the
frontend (`FrameworkDetail.tsx`, `AssetComplianceList.tsx`, `apiService.ts`). The existing
code handles basic file upload to local disk, extension and MIME-prefix allowlisting, and
display of uploaded evidence in the control detail view. What is missing maps precisely to
four specific gaps: (1) the evidence record is missing required metadata fields
(uploader identity, description, tenant scoping at record level, explicit `source` flag);
(2) there is no delete endpoint for manual evidence on the backend; (3) MIME validation
uses only the browser-reported `Content-Type` header, not magic-byte inspection of the
actual file content; and (4) the file size cap (required: 25 MB; artifacts endpoint sets
50 MB; upload endpoint has no cap at all) is inconsistent and incomplete.

The auth/tenant model is fully resolved. JWT tokens carry `tenant_id` and `role` in
claims; `get_current_user` is an async dependency returning a `TokenData` dataclass with
`username`, `role`, and `tenant_id`. Tenant isolation for reads uses an assets-lookup
pattern (find assets where `tenantId == caller.tenant_id`, then scope queries to those
asset IDs). The permission `manage:compliance_evidence` is defined and used in the
frontend permission guard; the backend currently enforces only role-based checks
(`_SUPER_ROLES`), not the fine-grained permission string.

The storage layer is local filesystem (`backend/static/evidence/`), served via FastAPI's
`StaticFiles` mount at `/static`. No GridFS, S3, or external blob storage exists or is
planned. Files are referenced by URL (`/static/evidence/<uuid><ext>`) embedded in the
evidence sub-document inside `asset_compliance` collection records.

**Primary recommendation:** Extend `compliance_evidence_endpoints.py` to add missing
metadata fields to the upload handler, add a DELETE handler for manual evidence with
owner-check logic, tighten the size cap to 25 MB, and implement magic-byte MIME validation
using Python's stdlib `imghdr`/`struct` for images and file-signature checking for PDF and
Office documents. On the frontend, extend the upload form to accept a description field and
add a delete button to the evidence list in `AssetComplianceList.tsx`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| File receipt and storage | API / Backend | — | Multi-part form upload; browser cannot write to server disk |
| MIME + extension validation | API / Backend | — | Client-supplied MIME is untrusted; backend must re-check magic bytes |
| File size enforcement | API / Backend | Frontend (UX) | Backend is authoritative; frontend can give early feedback only |
| Tenant scoping of uploads | API / Backend | — | JWT claim is authoritative; frontend cannot enforce isolation |
| Owner-only delete enforcement | API / Backend | — | Frontend can hide button; backend must enforce |
| Evidence display (automated + manual) | Browser / Client | — | `AssetComplianceList.tsx` already renders evidence arrays |
| Delete button + description field | Browser / Client | — | UI additions in existing component |
| API service wrappers | Browser / Client | — | `apiService.ts` functions called by components |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVID-01 | Authenticated user can upload PDF/PNG/JPEG/DOCX/XLSX (max 25 MB) for a specific control | Upload endpoint exists at `POST /api/assets/{asset_id}/compliance/evidence`; needs 25 MB cap and MIME allowlist tightened to exactly these 5 types |
| EVID-02 | Uploaded evidence stored per-tenant with control ID, uploader identity, timestamp, description | Evidence record missing `uploaded_by`, `description`, `source: "manual"`, and `tenantId` at record level; all fields are available from JWT and form params |
| EVID-03 | Uploaded evidence appears alongside automated evidence in control detail view | Frontend `AssetComplianceList.tsx` already renders `evidence[]` array; automated and manual records live in same array; needs source badge to visually distinguish |
| EVID-04 | User can delete own evidence; admin can delete any tenant's evidence | No DELETE endpoint exists; owner-check pattern must be added using `uploaded_by == caller.username` for users, bypassed for admins |
| EVID-05 | File uploads validated against MIME type allowlist; rejected if type doesn't match extension | Current validation uses browser-reported `Content-Type` header only; magic-byte check for PDF (`%PDF-`), PNG (`\x89PNG`), JPEG (`\xFF\xD8\xFF`), DOCX/XLSX (zip magic `PK\x03\x04`) required |
</phase_requirements>

---

## Existing Infrastructure

### What Already Exists (do not rebuild)

| Component | Location | What It Provides |
|-----------|----------|-----------------|
| Upload endpoint | `backend/compliance_evidence_endpoints.py` L21–84 | `POST /api/assets/{asset_id}/compliance/evidence` — receives file + `control_id`, validates extension/MIME prefix, saves to disk, pushes evidence sub-doc |
| Download endpoint | `backend/compliance_evidence_endpoints.py` L113–169 | `GET /api/compliance/evidence/download/{evidence_id}` — tenant-scoped, path-traversal-guarded |
| Get all evidence | `backend/compliance_evidence_endpoints.py` L87–111 | `GET /api/compliance/evidence` — tenant-scoped read |
| Get asset compliance | `backend/compliance_evidence_endpoints.py` L172–197 | `GET /api/assets/{asset_id}/compliance` |
| UPLOAD_DIR, _write_binary, _ALLOWED_UPLOAD_EXTENSIONS, _ALLOWED_UPLOAD_MIME_PREFIXES | `backend/compliance_artifacts_endpoints.py` L16–42 | Shared constants imported by evidence endpoint; must not be redeclared |
| Static file serving | `backend/app.py` L81–82 | `StaticFiles(directory="backend/static")` mounted at `/static`; `backend/static/evidence/` already exists |
| RBAC permission | `backend/rbac_service.py`, `backend/rbac_utils.py` | `manage:compliance_evidence` permission assigned to admin and compliance_manager roles |
| Frontend upload UI | `components/AssetComplianceList.tsx`, `components/FrameworkDetail.tsx` | File input, `onUploadEvidence` callback, evidence list rendering |
| Frontend API wrapper | `services/apiService.ts` L633–646 | `uploadComplianceEvidence(assetId, controlId, file)` — calls `POST /api/assets/{asset_id}/compliance/evidence` |
| Auth dependency | `backend/authentication_service.py` L169 | `get_current_user` async dependency returning `TokenData(username, role, tenant_id, mfa_verified)` |
| Evidence display | `components/AssetComplianceList.tsx` L93 | Distinguishes `systemGenerated` vs file-based evidence; renders download link for file evidence |
| Rate limiter | `backend/compliance_artifacts_endpoints.py` L73 | `@limiter.limit("10/hour")` via `slowapi` — pattern to copy for upload endpoint |

### Evidence Record Schema (automated — current)

Automated evidence sub-documents in `asset_compliance.evidence[]` have this shape:
```json
{
  "id": "auto-ev-{hostname}-{controlId}-{check_slug}-{ts}",
  "name": "System Check: {check_name}",
  "url": "#",
  "type": "application/json",
  "uploadedAt": "{iso8601}",
  "assetId": "{asset_id}",
  "controlId": "{control_id}",
  "tenantId": "{tenant_id}",
  "systemGenerated": true,
  "content": "{markdown}",
  "agent_type": "python|rust|null"
}
```

Manual evidence sub-documents (current, partial):
```json
{
  "id": "ev-{timestamp}",
  "name": "{original filename}",
  "url": "/static/evidence/{uuid}{ext}",
  "type": "{content_type}",
  "uploadedAt": "{iso8601}",
  "assetId": "{asset_id}",
  "controlId": "{control_id}"
}
```
Fields present in automated but absent from manual: `tenantId`, `systemGenerated` (should be `false`), `agent_type` (should be absent or `null`). Fields required by EVID-02 but absent from both: `uploaded_by`, `description`, `source`.

---

## Gap Analysis

### GAP-1: Missing metadata fields in upload endpoint (EVID-02)

**Current state:** The upload handler at `compliance_evidence_endpoints.py` L55–63 creates
an evidence record with only 7 fields (`id`, `name`, `url`, `type`, `uploadedAt`, `assetId`,
`controlId`). It does not capture `uploaded_by`, `description`, `source`, or `tenantId`.

**Required additions:**
- `description: str = Form("")` parameter to the endpoint
- `uploaded_by` derived from `current_user.username`
- `tenant_id` derived from `current_user.tenant_id` (or asset lookup result for non-admins)
- `source: "manual"` constant field to distinguish from automated records
- `systemGenerated: false` constant field

**Where to edit:** `compliance_evidence_endpoints.py` — the `upload_compliance_evidence`
function signature and the `evidence_record` dict construction.

**Frontend:** `uploadComplianceEvidence` in `apiService.ts` must add `description` to the
`FormData`. `AssetComplianceList.tsx` needs a description `<input>` field before the file
picker trigger.

### GAP-2: No delete endpoint (EVID-04)

**Current state:** No `DELETE` route exists in any evidence or artifacts endpoint.
`compliance_artifacts_endpoints.py` and `compliance_evidence_endpoints.py` contain only
`POST` and `GET` handlers.

**Required:** `DELETE /api/compliance/evidence/{evidence_id}` with:
1. Lookup evidence sub-document across `asset_compliance` collection by `evidence.id`
2. Reject if `evidence.systemGenerated == true` (prevent deleting automated records)
3. Owner check: non-admins may only delete where `evidence.uploaded_by == current_user.username`
4. Admin roles (`_SUPER_ROLES`) bypass owner check but are still scoped to their tenant (unless platform-admin)
5. `$pull` the evidence sub-document from the array
6. Delete the file from disk if `evidence.url` points to `static/evidence/` (using
   path-traversal guard already established in the download handler)

**MongoDB operation:**
```python
await db.asset_compliance.update_one(
    {"evidence.id": evidence_id},
    {"$pull": {"evidence": {"id": evidence_id}}}
)
```

**Frontend:** Add a delete button (`TrashIcon`) to each manual evidence row in
`AssetComplianceList.tsx`. Only show for `!ev.systemGenerated`. Call a new
`deleteComplianceEvidence(evidenceId)` wrapper in `apiService.ts`.

### GAP-3: Weak MIME validation (EVID-05)

**Current state:** Both existing upload handlers validate only:
1. File extension against `_ALLOWED_UPLOAD_EXTENSIONS` (frozenset in `compliance_artifacts_endpoints.py`)
2. Browser-reported `Content-Type` header against `_ALLOWED_UPLOAD_MIME_PREFIXES`

Neither approach verifies the actual file content. A user can upload a PHP script named
`evidence.pdf` with `Content-Type: application/pdf` and it will pass.

**Required for EVID-05:** Magic-byte inspection of the first 8–16 bytes of the file
content (read into memory before writing to disk). Python stdlib is sufficient:

| Type | Magic bytes | Check |
|------|-------------|-------|
| PDF | `%PDF-` (5 bytes) | `content[:5] == b'%PDF-'` |
| PNG | `\x89PNG\r\n\x1a\n` (8 bytes) | `content[:8] == b'\x89PNG\r\n\x1a\n'` |
| JPEG | `\xFF\xD8\xFF` (3 bytes) | `content[:3] == b'\xFF\xD8\xFF'` |
| DOCX/XLSX | `PK\x03\x04` (4 bytes, zip) | `content[:4] == b'PK\x03\x04'` |

**No new dependency required.** Python `struct`/raw bytes slicing is sufficient. Do not
add `python-magic` (requires `libmagic` C library, adds deployment complexity). The phase
requires exactly PDF/PNG/JPEG/DOCX/XLSX — all have well-known magic bytes.

**Implementation location:** Add a private `_check_magic(content: bytes, ext: str) -> bool`
function to `compliance_artifacts_endpoints.py` (exported alongside `_write_binary`) or
directly in `compliance_evidence_endpoints.py`. The upload handler calls it after reading
the file content and before writing to disk.

**Extension-to-magic mapping** (Phase 2 allowlist only):
```python
_MAGIC_SIGNATURES: dict[str, bytes] = {
    ".pdf":  b"%PDF-",
    ".png":  b"\x89PNG\r\n\x1a\n",
    ".jpg":  b"\xFF\xD8\xFF",
    ".jpeg": b"\xFF\xD8\xFF",
    ".docx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
}
```

### GAP-4: File size inconsistency (EVID-01)

**Current state:**
- `compliance_artifacts_endpoints.py` L94: enforces 50 MB limit
- `compliance_evidence_endpoints.py`: no size check at all (reads entire file into memory with `await file.read()`)
- Requirement EVID-01: 25 MB maximum

**Fix:** Add size check after `file_content = await file.read()` in `upload_compliance_evidence`:
```python
if len(file_content) > 25 * 1024 * 1024:
    raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")
```

Note: `compliance_artifacts_endpoints.py` keeps its 50 MB limit (for pentest reports, etc.) —
only the Phase 2 evidence endpoint must enforce 25 MB per EVID-01.

### GAP-5: MIME type allowlist scope (EVID-01 / EVID-05)

**Current state:** `_ALLOWED_UPLOAD_EXTENSIONS` includes `.zip`, `.tar`, `.gz`, `.md`,
`.json`, `.xml`, `.html`, `.gif`, `.webp`, `.csv`, `.txt`, `.doc`, `.xls` — much broader
than the Phase 2 requirement.

**Fix:** The Phase 2 upload endpoint (`upload_compliance_evidence`) must use a narrower
local allowlist, not the shared `_ALLOWED_UPLOAD_EXTENSIONS` constant. The shared constant
is correct for `compliance_artifacts_endpoints.py` (which accepts more types for policy
documents, etc.). Add a phase-specific constant to `compliance_evidence_endpoints.py`:
```python
_EVIDENCE_ALLOWED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"})
_EVIDENCE_ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.openxmlformats",
    "application/msword",
    "application/vnd.ms-excel",
    "image/png",
    "image/jpeg",
)
```

### GAP-6: Frontend upload form missing description field (EVID-02)

**Current state:** `AssetComplianceList.tsx` triggers a hidden file input directly. There
is no description field. `uploadComplianceEvidence` in `apiService.ts` sends only `file`
and `controlId` in the FormData.

**Fix:** Add a small inline form (or modal) before the upload confirming the description.
The simplest approach consistent with existing UI patterns: add a `description` `<input>`
rendered inline in the upload trigger area, store in local state, include in FormData.
Update `uploadComplianceEvidence` signature to accept `description?: string`.

### GAP-7: Frontend evidence list missing delete affordance and source label (EVID-03, EVID-04)

**Current state:** Evidence rows in `AssetComplianceList.tsx` show a download link for
file-based evidence but no delete button and no "Manual" vs "Automated" badge.

**Fix:**
- Add `source` badge: if `ev.systemGenerated` is true → label "Automated"; if false/absent
  and `ev.uploaded_by` is set → label "Manual"; use different badge colors.
- Add delete icon button for manual evidence. Conditionally rendered only when
  `!ev.systemGenerated` and (`ev.uploaded_by === currentUser.username` or user is admin).

### GAP-8: Content-Type header bug in apiService.ts

**Current state:** `apiService.ts` L640 sets `'Content-Type': 'multipart/form-data'`
explicitly when calling the evidence upload. This is incorrect — it omits the required
`boundary` parameter, which causes FastAPI's form parser to reject the request. `authFetch`
at L208 already correctly strips `Content-Type` when the body is a `FormData` instance (so
the browser sets the correct multipart boundary). The explicit header override undoes this.

**Fix:** Remove `headers: { 'Content-Type': 'multipart/form-data' }` from
`uploadComplianceEvidence` in `apiService.ts`. Let `authFetch` handle it automatically.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File write async safety | Custom async file writer | `asyncio.to_thread(_write_binary, ...)` | Already established pattern — `_write_binary` imported from `compliance_artifacts_endpoints` |
| Path traversal prevention | Custom path sanitizer | `Path(UPLOAD_DIR).resolve()` + startswith check | Already implemented in download handler L156–160 |
| JWT extraction | Manual header parsing | `get_current_user = Depends(get_current_user)` | Existing FastAPI dependency; already returns `tenant_id`, `username`, `role` |
| Rate limiting | Custom counter | `@limiter.limit("10/hour")` via `slowapi` | Already in `compliance_artifacts_endpoints.py`; `limiter` imported from `rate_limiter` |
| MIME detection library | python-magic / filetype | `content[:N] == b'<magic>'` | No C library dependency; stdlib bytes slicing is sufficient for the 6 file types in scope |

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (user)
    |
    | POST /api/assets/{asset_id}/compliance/evidence
    | (multipart/form-data: file + control_id + description)
    |
FastAPI backend
    |--- get_current_user (JWT -> TokenData{username, role, tenant_id})
    |--- Tenant isolation check (non-admin: asset must belong to caller's tenant)
    |--- Extension check (_EVIDENCE_ALLOWED_EXTENSIONS)
    |--- MIME prefix check (_EVIDENCE_ALLOWED_MIME_PREFIXES)
    |--- File size check (> 25 MB -> 413)
    |--- Magic byte check (_check_magic(content, ext))
    |--- asyncio.to_thread(_write_binary, path, content)  --> backend/static/evidence/<uuid>.<ext>
    |--- MongoDB: asset_compliance.$push(evidence_record)
    |
    |  GET /api/assets/{asset_id}/compliance (existing)
    |  -> evidence[] array (automated + manual mixed)
    |
    |  DELETE /api/compliance/evidence/{evidence_id}
    |--- get_current_user
    |--- Lookup evidence sub-doc (aggregate $unwind + $match)
    |--- Reject systemGenerated == true
    |--- Owner check (non-admin: uploaded_by == caller.username)
    |--- Tenant scope check (non-platform-admin: evidence.tenantId == caller.tenant_id)
    |--- MongoDB: asset_compliance.$pull({evidence.id: evidence_id})
    |--- os.remove(file_path) if file exists on disk

React Frontend
    AssetComplianceList.tsx
        - description <input> (new)
        - hidden file <input> (existing)
        - onUploadEvidence callback -> apiService.uploadComplianceEvidence(assetId, controlId, file, description)
        - evidence[] render loop (existing)
            - source badge: ev.systemGenerated ? "Automated" : "Manual"
            - delete button (new): calls apiService.deleteComplianceEvidence(ev.id)
```

### Recommended Project Structure

No new files needed. Extend existing files:

```
backend/
├── compliance_evidence_endpoints.py   # extend: add metadata fields, add DELETE handler, add size + magic check
├── compliance_artifacts_endpoints.py  # extend: add _check_magic() helper, export it
components/
├── AssetComplianceList.tsx            # extend: description field, source badge, delete button
services/
├── apiService.ts                      # extend: add description param, fix Content-Type bug, add deleteComplianceEvidence()
```

### Pattern: Evidence Upload with Full Metadata

```python
# Source: compliance_evidence_endpoints.py (extended)
@router.post("/api/assets/{asset_id}/compliance/evidence")
@limiter.limit("10/hour")
async def upload_compliance_evidence(
    request: Request,
    response: Response,
    asset_id: str,
    file: UploadFile = File(...),
    control_id: str = Form(...),
    description: str = Form(""),
    current_user=Depends(get_current_user),
):
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or ""
    uploader = getattr(current_user, "username", "unknown")

    if user_role not in _SUPER_ROLES:
        db = get_database()
        asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
        if not asset:
            raise HTTPException(status_code=403, detail="Asset not found in your tenant")

    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{file_ext}' not allowed")
    content_type = (file.content_type or "").split(";")[0].strip()
    if not any(content_type.startswith(p) for p in _EVIDENCE_ALLOWED_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' not allowed")

    file_content = await file.read()
    if len(file_content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")
    if not _check_magic(file_content, file_ext):
        raise HTTPException(status_code=400, detail="File content does not match extension")

    safe_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    await asyncio.to_thread(_write_binary, file_path, file_content)

    timestamp = datetime.now(timezone.utc).isoformat()
    evidence_record = {
        "id": f"ev-manual-{uuid.uuid4().hex}",
        "name": os.path.basename(file.filename or "evidence"),
        "url": f"/static/evidence/{safe_filename}",
        "type": file.content_type,
        "uploadedAt": timestamp,
        "assetId": asset_id,
        "controlId": control_id,
        "tenantId": tenant_id,
        "uploaded_by": uploader,
        "description": description,
        "source": "manual",
        "systemGenerated": False,
    }
    # ... $push to asset_compliance
```

### Pattern: Magic Byte Check

```python
# Source: to be added to compliance_artifacts_endpoints.py
_MAGIC_SIGNATURES: dict[str, bytes] = {
    ".pdf":  b"%PDF-",
    ".png":  b"\x89PNG\r\n\x1a\n",
    ".jpg":  b"\xFF\xD8\xFF",
    ".jpeg": b"\xFF\xD8\xFF",
    ".docx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
}

def _check_magic(content: bytes, ext: str) -> bool:
    """Return True if file content matches the expected magic bytes for ext."""
    sig = _MAGIC_SIGNATURES.get(ext)
    if sig is None:
        return True  # No signature check defined for this ext — pass through
    return content[:len(sig)] == sig
```

### Pattern: Evidence Delete

```python
# DELETE /api/compliance/evidence/{evidence_id}
@router.delete("/api/compliance/evidence/{evidence_id}")
async def delete_compliance_evidence(
    evidence_id: str,
    current_user=Depends(get_current_user),
):
    db = get_database()
    user_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    caller_username = getattr(current_user, "username", "")
    is_super_admin = user_role in _SUPER_ROLES

    pipeline = [
        {"$unwind": "$evidence"},
        {"$match": {"evidence.id": evidence_id}},
        {"$project": {"evidence": 1, "tenantId": 1, "_id": 0}},
    ]
    result = await db.asset_compliance.aggregate(pipeline).to_list(length=1)
    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")

    ev = result[0]["evidence"]
    doc_tenant = result[0].get("tenantId")

    # Never allow deletion of automated evidence
    if ev.get("systemGenerated"):
        raise HTTPException(status_code=403, detail="Automated evidence cannot be deleted")

    # Tenant isolation: non-platform-admins cannot delete other tenants' records
    if not is_super_admin and caller_tenant and doc_tenant != caller_tenant:
        raise HTTPException(status_code=403, detail="Evidence not found in your tenant")

    # Owner check: non-admins can only delete their own uploads
    if not is_super_admin and ev.get("uploaded_by") != caller_username:
        raise HTTPException(status_code=403, detail="You can only delete your own evidence")

    await db.asset_compliance.update_one(
        {"evidence.id": evidence_id},
        {"$pull": {"evidence": {"id": evidence_id}}}
    )

    # Clean up file from disk
    file_url = ev.get("url", "")
    fname = Path(file_url).name
    if fname and not fname.startswith("."):
        _safe_dir = Path(UPLOAD_DIR).resolve()
        resolved = (_safe_dir / fname).resolve()
        if str(resolved).startswith(str(_safe_dir)) and resolved.exists():
            resolved.unlink(missing_ok=True)

    return {"success": True}
```

### Anti-Patterns to Avoid

- **Setting `Content-Type: multipart/form-data` explicitly in fetch calls.** `authFetch`
  already omits `Content-Type` for `FormData` bodies; the browser sets the correct boundary.
  Explicit override breaks the boundary, causing 422 from FastAPI.

- **Redeclaring `UPLOAD_DIR`, `_write_binary`, `_ALLOWED_UPLOAD_EXTENSIONS`.** These are
  defined once in `compliance_artifacts_endpoints.py` and imported by
  `compliance_evidence_endpoints.py`. A third definition creates drift risk.

- **Using the shared `_ALLOWED_UPLOAD_EXTENSIONS` for the Phase 2 upload handler.** It is
  deliberately broader (includes `.zip`, `.xml`, etc.). Phase 2 must use a narrower local
  constant restricted to the 6 types in EVID-01.

- **Allowing `$pull` of `systemGenerated: true` evidence.** The processor uses `$pull` by
  name to replace auto records on re-scan. Manual delete must explicitly reject records
  where `systemGenerated == true`.

- **Writing files before validation.** Size check and magic check must happen on the
  in-memory `file_content` bytes before calling `_write_binary`. Disk writes are
  irreversible within a request.

- **Using `file.read()` twice.** `UploadFile.read()` consumes the stream. Read once into
  `file_content`, then use the bytes variable for validation and write.

---

## Common Pitfalls

### Pitfall 1: `Content-Type: multipart/form-data` without boundary

**What goes wrong:** FastAPI returns 422 Unprocessable Entity; the form fields including
`control_id` are not parsed; upload appears to fail silently (the file bytes may arrive
but form params are missing).

**Why it happens:** Setting `Content-Type` explicitly overrides the browser's automatic
header that includes `; boundary=<uuid>`. Without the boundary, multipart parsing fails.

**How to avoid:** Never set `Content-Type` on a `fetch` call when the body is `FormData`.
Remove the explicit header from `uploadComplianceEvidence` in `apiService.ts`.

**Warning signs:** Backend logs show `422` with body `{"detail": [{"type": "missing", "loc":
["body", "control_id"]}]}`; file_content arrives but form fields do not.

### Pitfall 2: Tenant ID not written to the evidence sub-document

**What goes wrong:** The GET endpoint at `compliance_evidence_endpoints.py` L87–111 scopes
reads by looking up assets by `tenantId` and then filtering `assetId`. But the download
endpoint at L124–127 adds a `tenantId` filter directly against the `asset_compliance`
document. If `tenantId` was never written to the document, the download filter
`match_filter["tenantId"] = _tid` silently returns 0 results for non-admin callers.

**Why it happens:** The current `upload_compliance_evidence` handler does not write
`tenantId` to the `$set` block.

**How to avoid:** Add `"tenantId": tenant_id` to the `$set` dict in `update_one`. Also
add `"tenantId": tenant_id` to the `evidence_record` sub-document (the processor already
does this for automated records).

**Warning signs:** Upload returns success; GET by asset returns the record; download returns
404 for a non-admin caller.

### Pitfall 3: `os.path.exists(file_path)` fails on delete after disk path changes

**What goes wrong:** If the working directory changes between upload and delete, the
relative path `"static/evidence/{filename}"` resolves differently. `os.path.exists` returns
False and the file is silently not deleted.

**Why it happens:** `UPLOAD_DIR = "static/evidence"` is a relative path. If uvicorn is
started from a different directory, the path resolves incorrectly.

**How to avoid:** Use `Path(__file__).parent / "static" / "evidence"` for UPLOAD_DIR, or
use the existing `UPLOAD_DIR` which is set in `compliance_artifacts_endpoints.py` as a
relative string (this is consistent with how `app.py` resolves the static dir using
`os.path.dirname(__file__)`). The path traversal guard using `Path(UPLOAD_DIR).resolve()`
will catch absolute-path mismatches. In practice: always verify the file exists before
unlinking; use `unlink(missing_ok=True)`.

**Warning signs:** Delete endpoint returns 200 but the file remains on disk. Subsequent
uploads with the same filename do not overwrite (uuid prevents this, but orphaned files
accumulate).

### Pitfall 4: `$pull` targets wrong field when evidence IDs collide

**What goes wrong:** The automated evidence ID uses the format
`auto-ev-{hostname}-{controlId}-{check_slug}-{timestamp}`. The manual upload generates
`f"ev-{timestamp}"` (current code) which can collide across tenants if two uploads occur
at the same millisecond.

**How to avoid:** Generate manual evidence IDs with UUID: `f"ev-manual-{uuid.uuid4().hex}"`.
The `$pull` operator filters the `evidence` array by the exact `id` value; UUID ensures
no collisions.

### Pitfall 5: Reading large files fully into memory without size check first

**What goes wrong:** `file_content = await file.read()` with no prior size limit reads the
entire upload into process memory. A 500 MB upload would OOM the server before hitting
any size check.

**How to avoid:** FastAPI does not natively support streaming size checks on `UploadFile`
without reading. The practical mitigation at this scale is to read fully then check, but
do it early. For future hardening, set `max_upload_size` in the ASGI server config or
wrap with a `LimitUploadSize` middleware. For Phase 2 (25 MB cap), reading fully is
acceptable given typical GRC file sizes.

---

## Standard Stack

No new packages required. All required functionality is achievable with the existing stack:

| Capability | Tool | Already in requirements.txt |
|------------|------|-----------------------------|
| File upload | FastAPI `UploadFile` + `python-multipart` | Yes (line 15) |
| File storage | Local filesystem via `asyncio.to_thread` | Yes |
| MIME validation | Python stdlib `bytes` slicing (magic bytes) | Yes (no package needed) |
| JWT / auth | `PyJWT` + `get_current_user` dependency | Yes |
| MongoDB | `motor` async driver | Yes |
| Rate limiting | `slowapi` via `rate_limiter.py` | Yes (already used in artifacts endpoint) |

**No new dependencies to add.**

### Package Legitimacy Audit

Not applicable — Phase 2 introduces no new packages.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Extension allowlist + magic-byte check + size cap |
| V4 Access Control | yes | Owner check for delete; tenant isolation for all operations |
| V1.9 File Upload | yes | Allowlist extension + MIME + magic bytes; random UUID filename; no execution |
| V2 Authentication | yes | `get_current_user` dependency on all endpoints |
| V6 Cryptography | no | No encryption of stored files (files are audit artifacts; encryption at rest is OS-level) |

### Known Threat Patterns for File Upload

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious file disguised as PDF | Tampering | Magic-byte check (EVID-05 gap) |
| Path traversal in filename | Tampering/EoP | `Path(UPLOAD_DIR).resolve()` + startswith guard (already in download handler) |
| File bomb (decompression) | DoS | Phase 2 allowlist excludes `.zip`/archives; 25 MB cap limits raw size |
| Cross-tenant evidence read | Information Disclosure | Asset-ownership check on upload; `tenantId` filter on download + delete |
| Deleting another user's evidence | Tampering | `uploaded_by == caller.username` check on delete |
| Deleting automated evidence | Tampering | `systemGenerated == true` guard on delete |
| Bypassing file size via chunked upload | DoS | Read fully before write; check `len(file_content)` |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (backend) |
| Config file | `backend/tests/` directory |
| Quick run command | `cd backend && python -m pytest tests/test_evidence_uploads.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EVID-01 | Upload PDF/PNG/JPEG/DOCX/XLSX ≤25 MB → 200 | unit | `pytest tests/test_evidence_uploads.py::test_upload_allowed_types -x` | Wave 0 |
| EVID-01 | Upload >25 MB → 413 | unit | `pytest tests/test_evidence_uploads.py::test_upload_size_limit -x` | Wave 0 |
| EVID-02 | Evidence record has `uploaded_by`, `description`, `tenantId`, `source:"manual"` | unit | `pytest tests/test_evidence_uploads.py::test_upload_record_schema -x` | Wave 0 |
| EVID-03 | GET /api/assets/{id}/compliance returns both automated and manual evidence | unit | `pytest tests/test_evidence_uploads.py::test_evidence_mixed_display -x` | Wave 0 |
| EVID-04 | Owner can delete own evidence → 200 | unit | `pytest tests/test_evidence_uploads.py::test_delete_own_evidence -x` | Wave 0 |
| EVID-04 | Non-owner cannot delete another's evidence → 403 | unit | `pytest tests/test_evidence_uploads.py::test_delete_other_user_evidence -x` | Wave 0 |
| EVID-04 | Admin can delete any tenant's evidence → 200 | unit | `pytest tests/test_evidence_uploads.py::test_admin_delete_any_evidence -x` | Wave 0 |
| EVID-04 | Deleting systemGenerated evidence → 403 | unit | `pytest tests/test_evidence_uploads.py::test_delete_automated_evidence_blocked -x` | Wave 0 |
| EVID-05 | PDF with .pdf ext + PDF magic → 200 | unit | `pytest tests/test_evidence_uploads.py::test_magic_bytes_valid_pdf -x` | Wave 0 |
| EVID-05 | .js file renamed to .pdf → 400 | unit | `pytest tests/test_evidence_uploads.py::test_magic_bytes_mismatch -x` | Wave 0 |

### Wave 0 Gaps

- [ ] `backend/tests/test_evidence_uploads.py` — covers all EVID-01 through EVID-05 test cases listed above
- [ ] Shared fixtures for mock `current_user`, mock MongoDB in `backend/tests/conftest.py` (may already exist from Phase 1)

---

## Environment Availability

Step 2.6: SKIPPED — Phase 2 introduces no external service dependencies. All required
infrastructure (MongoDB, FastAPI, local filesystem) is already in use by the existing
codebase.

---

## Recommended Plan Structure

### Wave 1 — Backend: Extend upload endpoint + add delete endpoint + add magic check

**Plan 02-01:** Backend evidence endpoint gaps

Tasks:
1. Add `_check_magic()` helper to `compliance_artifacts_endpoints.py` (5 lines)
2. Extend `upload_compliance_evidence` in `compliance_evidence_endpoints.py`: add
   `description` Form param, add `uploader`/`tenant_id`/`source`/`systemGenerated` fields
   to evidence record, enforce 25 MB cap, narrow allowlist to 6 types, call `_check_magic`
3. Add `DELETE /api/compliance/evidence/{evidence_id}` to `compliance_evidence_endpoints.py`:
   lookup, guard systemGenerated, owner check, tenant check, `$pull`, disk cleanup
4. Fix Content-Type bug in `services/apiService.ts` `uploadComplianceEvidence` (remove
   explicit `Content-Type` header)
5. Add `deleteComplianceEvidence(evidenceId)` to `services/apiService.ts`

**Wave 1 success gate:** Backend tests pass for EVID-01/02/04/05.

### Wave 2 — Frontend: Description field, source badge, delete button

**Plan 02-02:** Frontend evidence UI gaps

Tasks:
1. `AssetComplianceList.tsx`: add `description` input before file picker trigger; pass
   description to `onUploadEvidence` callback
2. `FrameworkDetail.tsx`: update `onUploadEvidence` prop signature to accept description;
   pass to `api.uploadComplianceEvidence`
3. `AssetComplianceList.tsx`: add source badge to each evidence row
   (`ev.systemGenerated ? "Automated" : "Manual"`)
4. `AssetComplianceList.tsx`: add delete button for manual evidence; call
   `api.deleteComplianceEvidence(ev.id)`; confirm before delete; refresh evidence list on
   success

**Wave 2 success gate:** Manual upload shows correct metadata; source badges visible;
delete works for own evidence; admin delete works across tenants (manual verify).

---

## Open Questions

1. **Control-level upload vs. asset-level upload**
   - What we know: the existing endpoint is `POST /api/assets/{asset_id}/compliance/evidence`
     — it requires an `asset_id`. Controls can exist without a specific asset (framework-level).
   - What's unclear: should manual evidence be attachable to a control without specifying an
     asset? (e.g., a policy document that applies to all assets for a control)
   - Recommendation: keep asset-scoped for Phase 2 (consistent with existing endpoint);
     framework-level / asset-agnostic upload can be done via the existing
     `compliance_artifacts_endpoints.py` which already accepts `asset_id: Optional[str]`.

2. **Tenant ID for platform-admin uploads**
   - What we know: platform-admin users have `tenant_id` set to `"platform-admin"` by the
     `verify_token` path in `authentication_service.py`. If a platform-admin uploads
     evidence, `tenantId: "platform-admin"` is written to the record.
   - What's unclear: should platform-admin be able to upload evidence into a specific
     tenant's records?
   - Recommendation: out of scope for Phase 2. Platform-admin can impersonate a tenant
     context in a future phase if needed.

3. **Description length limit**
   - What we know: no length limit is specified in EVID-02.
   - Recommendation: add `description: str = Form("", max_length=1000)` to prevent
     excessive content in MongoDB sub-documents.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | python-magic / libmagic is not installed in the production environment | Gap Analysis GAP-3 | If libmagic were available, using it would give more robust detection; stdlib approach covers all 6 required types regardless |
| A2 | `tenant_id` is always populated in JWT for non-platform-admin users | Auth Pattern | If `tenant_id` is sometimes null for valid users, tenant isolation checks need a null guard |
| A3 | `compliance_evidence_endpoints.py` is included via `compliance_endpoints.py` without changes to `router_registry.py` | Architecture | Pattern file (02-PATTERNS.md) states this; not independently verified by reading `compliance_endpoints.py` |

---

## Sources

### Primary (HIGH confidence — code verified in this session)

- `backend/compliance_evidence_endpoints.py` — full file read; upload handler, download handler, schema, tenant check
- `backend/compliance_artifacts_endpoints.py` — full file read; UPLOAD_DIR, _write_binary, _ALLOWED_*, rate limiting
- `backend/compliance_evidence_processor.py` — process_automated_evidence function (L147–270); automated evidence schema
- `backend/authentication_service.py` — get_current_user, verify_token_async, TokenData fields
- `backend/auth_types.py` — TokenData dataclass definition
- `backend/requirements.txt` — confirmed python-multipart, motor, PyJWT present; python-magic absent
- `components/AssetComplianceList.tsx` — full file read; upload trigger, evidence render, source detection
- `components/FrameworkDetail.tsx` — partial read; canManageEvidence, onUploadEvidence wiring
- `services/apiService.ts` — uploadComplianceEvidence (L633–646), authFetch (L197–240)
- `.planning/phases/02-manual-evidence-uploads/02-PATTERNS.md` — analog mapping confirming existing patterns

### Secondary (HIGH confidence — planning docs verified)

- `.planning/PROJECT.md` — multi-tenant model, storage decision, security requirements
- `.planning/REQUIREMENTS.md` — EVID-01 through EVID-05 exact text
- `.planning/ROADMAP.md` — Phase 2 success criteria

### Tertiary (LOW confidence — not verified in this session)

- `backend/compliance_endpoints.py` — assumed to be the router that includes `compliance_evidence_endpoints`; not read (A3 above)

---

## Metadata

**Confidence breakdown:**
- Existing infrastructure: HIGH — all key files read directly
- Gap analysis: HIGH — gaps identified from direct code reading, not inference
- Magic-byte signatures: HIGH — well-known file format specifications
- Frontend patterns: HIGH — component code read directly
- Plan structure: MEDIUM — task sizing is an estimate; actual line counts may vary

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (stable stack — no fast-moving dependencies)
