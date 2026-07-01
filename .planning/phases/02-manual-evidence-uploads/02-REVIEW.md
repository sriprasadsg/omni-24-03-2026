---
phase: "02"
status: findings
depth: standard
reviewed_at: 2026-06-17
files_reviewed: 5
files_reviewed_list:
  - backend/compliance_evidence_endpoints.py
  - backend/compliance_artifacts_endpoints.py
  - backend/tests/test_evidence_uploads.py
  - services/apiService.ts
  - components/AssetComplianceList.tsx
findings:
  critical: 5
  warning: 5
  info: 3
  total: 13
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-17
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 2 delivers the core evidence-upload hardening (size cap, magic-byte validation, metadata, DELETE endpoint) and frontend wiring. The happy path is correct. However, five critical defects were found: a tenant-isolation bypass in the DELETE endpoint that allows a JWT with no tenant to delete any user's evidence when usernames collide across tenants; a Content-Disposition response-header injection vector via the evidence `name` field; an unfixed `Content-Type: multipart/form-data` bug in `importComplianceControls` that breaks multipart uploads; a missing `tenantId` field in artifact records that makes the artifact list permanently empty for all non-super users; and a non-idempotent artifact record ID that throws a duplicate-key error when two uploads arrive in the same second. Five warnings and three info items follow.

---

## Critical Issues

### CR-01: Tenant Isolation Bypass in DELETE When JWT Has No `tenant_id`

**File:** `backend/compliance_evidence_endpoints.py:268`

**Issue:** The tenant isolation guard is:
```python
if not is_super and caller_tenant and doc_tenant != caller_tenant:
    raise HTTPException(status_code=403, ...)
```
`caller_tenant` is `getattr(current_user, "tenant_id", None)` and is never coerced to a non-falsy value. When a JWT is issued without a `tenant_id` claim (e.g., during early onboarding or from a misconfigured IdP), `caller_tenant` is `None` and the `and caller_tenant` short-circuits the check to `False`. The owner check that follows (`ev.get("uploaded_by") != caller_username`) can also be bypassed when the attacker's username matches the victim's — a realistic scenario in multi-tenant systems where usernames are only required to be unique per tenant, not globally.

Concrete attack: attacker authenticates with username `john` and no `tenant_id`; victim is `john@tenant-b` with `tenant_id=tenant-b`. The tenant guard is skipped; the owner check passes; the victim's evidence is deleted.

**Fix:**
```python
# Reject callers with no tenant unless they are super-admins
if not is_super and not caller_tenant:
    raise HTTPException(status_code=403, detail="Tenant context required")
if not is_super and doc_tenant != caller_tenant:
    raise HTTPException(status_code=403, detail="Evidence not found in your tenant")
```

---

### CR-02: HTTP Response-Header Injection via Evidence `name` in Content-Disposition

**File:** `backend/compliance_evidence_endpoints.py:179-183`

**Issue:** The system-generated markdown download path builds the `Content-Disposition` header by directly interpolating `evidence['name']` from the database:
```python
filename = f"{evidence['name'].replace(' ', '_').replace(':', '')}.md"
return Response(
    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    ...
)
```
`evidence['name']` originates from `file.filename` at upload time (line 87), which is fully attacker-controlled. A filename containing a double-quote breaks out of the `filename="..."` token. A filename containing `\r\n` allows injecting arbitrary HTTP response headers (header injection). Example: a file named `x"\r\nSet-Cookie: session=evil` produces a malformed/hijacked response header.

**Fix:** Sanitize the filename before embedding it in the header — strip all characters except `[A-Za-z0-9._-]`, or use RFC 5987 percent-encoding for the `filename*` parameter:
```python
import re
safe_name = re.sub(r'[^\w.\-]', '_', evidence['name']) + '.md'
# Or use RFC 5987:
encoded = urllib.parse.quote(evidence['name'] + '.md', safe='')
headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
```
Apply the same fix to `filename` in the `FileResponse` path (line 202-205) as a defence-in-depth measure even though those filenames are currently UUID-based.

---

### CR-03: `importComplianceControls` Still Sets `Content-Type: multipart/form-data` Explicitly (Breaks Upload)

**File:** `services/apiService.ts:606`

**Issue:** The comment on line 606 says `authFetch will handle this or we can let browser do it`, but `authFetch` does not strip caller-supplied headers — it spreads them at priority over its own defaults (line 209). The explicit `Content-Type: multipart/form-data` header is therefore forwarded to `fetch()` **without the required `boundary` parameter**. The server cannot parse the body, and the upload silently fails (HTTP 400/422 from the backend form parser). This is the exact bug that Phase 2 was supposed to fix for `uploadComplianceEvidence`, but it was only fixed for that function; `importComplianceControls` was left broken.

**Fix:** Remove the `headers` override entirely from `importComplianceControls`:
```typescript
export const importComplianceControls = async (frameworkId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await authFetch(`${API_BASE}/compliance/${frameworkId}/import`, {
        method: 'POST',
        body: formData
        // No headers — browser sets Content-Type with boundary automatically
    });
    if (!res.ok) throw new Error("Import failed");
    return await res.json();
};
```

---

### CR-04: `tenantId` Not Stored in Artifact Records — Non-Super Users Always Get Empty List

**File:** `backend/compliance_artifacts_endpoints.py:146-162` and `197`

**Issue:** `upload_manual_artifact` never writes `tenantId` into the `record` dict that is persisted to MongoDB. The `list_manual_artifacts` endpoint (line 197) then filters non-super-admin users by `query["tenantId"] = user_tenant`, which never matches any stored document. Every non-super-admin user gets an empty artifact list regardless of what they uploaded.

**Fix:** Add `tenantId` to the artifact record:
```python
uploader_tenant = getattr(current_user, "tenant_id", None)
record = {
    ...
    "uploaded_by": uploader,
    "tenantId": uploader_tenant,   # add this
    ...
}
```

---

### CR-05: Artifact Record ID Collision on Concurrent Uploads (500 Error)

**File:** `backend/compliance_artifacts_endpoints.py:147` and `165`

**Issue:** The artifact record ID is `f"artifact-{timestamp}"` where `timestamp` is `datetime.now().strftime("%Y%m%d%H%M%S")` — second-level granularity. Two uploads arriving within the same calendar second produce the same ID, which is also used as the MongoDB `_id` (line 165: `insert_one({**record, "_id": record["id"]})`). The second insert raises a `DuplicateKeyError`, which propagates as an unhandled 500. The file was already written to disk at this point, leaving an orphan file.

**Fix:** Use UUID4 for the artifact ID:
```python
import uuid
record = {
    "id": f"artifact-{uuid.uuid4().hex}",
    ...
}
```

---

## Warnings

### WR-01: Inconsistent Super-Admin Role Sets Across Endpoints

**File:** `backend/compliance_evidence_endpoints.py:18,128,159`

**Issue:** Three different role sets are used to decide super-admin status, with overlapping but non-identical membership:

| Role string | `_SUPER_ROLES` (line 18) | `get_all_compliance_evidence` (line 128) | `download` (line 159) |
|-------------|--------------------------|------------------------------------------|-----------------------|
| `"superadmin"` | **absent** | present | **absent** |
| `"admin"` | present | **absent** | present |

A user with role `"admin"` can upload and delete without tenant checks, but cannot see all evidence in `get_all_compliance_evidence` — their view is silently scoped to their tenant. A user with role `"superadmin"` can see all evidence but is subject to tenant checks on upload and delete.

**Fix:** Define a single frozenset constant and use it everywhere:
```python
_SUPER_ROLES: frozenset[str] = frozenset({
    "Super Admin", "super_admin", "superadmin", "admin", "platform-admin"
})
```
Then replace all inline role-set definitions with `_SUPER_ROLES`.

---

### WR-02: Path Traversal Guard in Download Endpoint Missing `os.sep` Suffix

**File:** `backend/compliance_evidence_endpoints.py:194`

**Issue:** The download endpoint guards the resolved path with:
```python
if not str(file_path_resolved).startswith(str(_safe_dir)):
```
The DELETE endpoint (line 287) correctly uses `startswith(str(_safe_dir) + os.sep)`. Without the separator, a path like `/app/static/evidence_backup/x.pdf` would pass the check if `_safe_dir` is `/app/static/evidence`. In practice this is currently mitigated because `Path(file_url).name` extracts only the basename, so the joined path always lands inside `_safe_dir`. However, the guard is logically weaker than intended and would fail to protect if the file-url parsing ever changes.

**Fix:**
```python
if not str(file_path_resolved).startswith(str(_safe_dir) + os.sep):
    raise HTTPException(status_code=400, detail="Invalid file path")
```

---

### WR-03: `uploadComplianceEvidence` in `apiService.ts` Sends `controlId` But Backend Expects `control_id`

**File:** `services/apiService.ts:636` and `backend/compliance_evidence_endpoints.py:40`

**Issue:** The frontend appends the form field as `formData.append('controlId', controlId)` (camelCase). FastAPI's `Form(...)` parameter is declared as `control_id: str = Form(...)` (snake_case). FastAPI uses the Python parameter name as the form-field key with no automatic camelCase conversion. The backend will never receive `control_id`, and FastAPI will return a `422 Unprocessable Entity` on every evidence upload.

**Fix:**
```typescript
formData.append('control_id', controlId);  // match backend snake_case
```

---

### WR-04: `file.text()` Called on Binary Files in Frontend Ingestion Flow

**File:** `components/AssetComplianceList.tsx:40`

**Issue:** `file.text()` reads the file content as a UTF-8 string. For binary evidence files (PDF, PNG, DOCX, XLSX — all permitted by the backend), this silently garbles the data with replacement characters before passing it to `onIngestEvidence`. The ingested content will be nonsensical, causing the LLM-based AI auditor to produce incorrect evaluations. No error is surfaced to the user.

**Fix:** Skip binary-format files from text ingestion, or use `file.arrayBuffer()` / a proper parser for supported text formats. At minimum, guard against binary types:
```typescript
const textTypes = ['text/plain', 'text/markdown', 'application/json', 'text/csv'];
if (textTypes.some(t => file.type.startsWith(t))) {
    const text = await file.text();
    await onIngestEvidence(selectedAssetId, file.name, text);
}
// else: skip ingestion silently or show a notice
```

---

### WR-05: Frontend `<input accept>` Allows File Types the Backend Rejects and Blocks Types the Backend Accepts

**File:** `components/AssetComplianceList.tsx:213`

**Issue:** The file input declares:
```html
accept=".txt,.md,.json,.csv,.log,.pdf"
```
The backend's `_EVIDENCE_ALLOWED_EXTENSIONS` allows: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.docx`, `.xlsx`.

The discrepancy means:
1. Users cannot select `.png`, `.jpg`, `.jpeg`, `.docx`, or `.xlsx` from the file picker — the main document formats the feature was built for.
2. Users CAN select `.txt`, `.md`, `.json`, `.csv`, `.log` — all of which the backend will reject with HTTP 400.

**Fix:**
```html
accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"
```

---

## Info

### IN-01: `Pending_Review` Status Not Styled in Frontend — Displays as Red

**File:** `components/AssetComplianceList.tsx:94-96` and `backend/compliance_evidence_endpoints.py:105`

**Issue:** After evidence upload, the backend sets `status: "Pending_Review"`. The frontend status badge styling only checks for `"Compliant"` (green) and `"Pending_Evidence"` (yellow); everything else falls through to red. Uploaded evidence therefore appears to make the asset look "Non-Compliant" (red) instead of "Pending Review" (yellow).

**Fix:** Add `Pending_Review` to the yellow branch, or align the backend status string to `Pending_Evidence`.

---

### IN-02: Test Patches `pathlib.Path.exists` But Code Never Calls It

**File:** `backend/tests/test_evidence_uploads.py:228,274`

**Issue:** Both `test_delete_own_evidence` and `test_admin_delete_any_evidence` patch `pathlib.Path.exists`, but `delete_compliance_evidence` uses `Path.unlink(missing_ok=True)` (which does not call `.exists()`). The patch is dead code and shows the test was written against a different implementation. The tests still pass, but the patch is misleading.

**Fix:** Remove the `patch("pathlib.Path.exists", return_value=False)` context manager from both tests.

---

### IN-03: No Test Coverage for Null-Tenant Cross-Tenant DELETE Bypass (CR-01)

**File:** `backend/tests/test_evidence_uploads.py`

**Issue:** The test suite covers same-tenant non-owner deletion (WR-01), cross-tenant admin deletion, and systemGenerated blocking, but has no test for the critical scenario identified in CR-01: a caller with `tenant_id=None` attempting to delete another tenant's evidence where usernames match.

**Fix:** Add a test case:
```python
def test_delete_cross_tenant_no_tenant_in_jwt():
    """CR-01: Caller with no tenant_id must be rejected even if username matches."""
    from compliance_evidence_endpoints import delete_compliance_evidence
    from fastapi.exceptions import HTTPException

    user = _make_user(username="john", role="Viewer", tenant_id=None)
    agg_result = _manual_ev_doc(uploaded_by="john", tenant_id="tenant-b")
    db = _make_db(aggregate_result=agg_result)

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await delete_compliance_evidence(
                asset_id="asset-1",
                evidence_id="ev-manual-abc",
                current_user=user,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 403
```

---

_Reviewed: 2026-06-17_
_Reviewer: Claude (adversarial code review)_
_Depth: standard_
