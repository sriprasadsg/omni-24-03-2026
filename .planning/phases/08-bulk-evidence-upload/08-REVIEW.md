---
phase: 08-bulk-evidence-upload
reviewed: 2026-06-22T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/compliance_bulk_evidence_endpoints.py
  - backend/router_registry.py
  - backend/tests/test_bulk_evidence_upload.py
  - components/BulkEvidenceUploadModal.tsx
  - components/FrameworkDetail.tsx
  - services/apiService.ts
findings:
  critical: 3
  warning: 5
  info: 3
  total: 11
status: issues_found
---

# Phase 8: Bulk Evidence Upload — Code Review Report

**Reviewed:** 2026-06-22
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

The core zip-slip guard, magic-bytes check, and validate-all-before-commit (BULK-02) logic are
correctly implemented. The authentication source for `tenant_id` is cleanly derived from JWT
(`current_user`), never from the request body. The test suite covers 12 distinct scenarios and
all pass the critical BULK-01/02/03 surface.

Three blockers require attention before this ships: the backend bulk-upload endpoint enforces no
role-based authorization (any authenticated user can write evidence), the zip-bomb guard relies on
spoofable zip metadata so it can be bypassed with crafted entries, and the commit loop has no
rollback — a mid-batch DB failure leaves orphaned files on disk. Five warnings address the unused
`canManageEvidence` permission flag in the UI, missing keyboard accessibility on the manifest
picker, a misleading uncompressed-size error path, untested CoC writes, and a false module-level
docstring.

---

## Critical Issues

### CR-01: No authorization check on bulk upload endpoint — any authenticated user can write evidence

**File:** `backend/compliance_bulk_evidence_endpoints.py:42-53`
**Issue:** The `bulk_upload_evidence` endpoint depends only on `get_current_user` (authentication).
It performs no role or permission check before writing files to disk and inserting records into
`control_evidence`. All sibling endpoints in `compliance_artifacts_endpoints.py` and
`compliance_evidence_endpoints.py` guard write operations behind role checks
(`user_role in {"admin", "Super Admin", ...}`). A read-only user, an analyst, or any compromised
account that holds a valid JWT can submit a bulk upload and persist evidence records to any control
within their tenant.

**Fix:**
```python
# At the top of the try block, after extracting tenant_id / uploader:
_WRITE_ROLES: frozenset[str] = frozenset({
    "admin", "Admin", "Super Admin", "superadmin", "super_admin", "platform-admin"
})
user_role = getattr(current_user, "role", "")
if user_role not in _WRITE_ROLES:
    raise HTTPException(status_code=403, detail="Insufficient permissions to upload evidence")
```

---

### CR-02: Zip-bomb guard uses spoofable metadata — `file_size` can be set to 0 to bypass the 200 MB total check

**File:** `backend/compliance_bulk_evidence_endpoints.py:84-88`
**Issue:** The uncompressed-size guard at line 84 reads `i.file_size` from zip metadata
(`ZipInfo.file_size`). A crafted zip can store `file_size=0` for every entry in its central
directory while the actual decompressed content is arbitrarily large. When this happens:

1. `total_uncompressed = 0 < MAX_BULK_BYTES` — guard passes.
2. The per-entry loop calls `zf.read(raw_name)` at line 113, which decompresses each entry
   fully into memory before the 25 MB length check at line 120.
3. With 50 manifest entries each decompressing to ~25 MB, up to ~1.25 GB of RAM is allocated
   across the loop before any entry is rejected.

The test at line 320 mocks `infolist` to return objects with honest `file_size` values, so it
does not catch this bypass.

**Fix:** Use `ZipInfo.compress_size` (which cannot lie for entries that must fit in the
already-bounded `zip_content` buffer) as the basis for the per-entry pre-read guard, or limit
uncompressed expansion per entry before the `zf.read()` call by reading in chunks:

```python
# Replace the unconditional zf.read(raw_name) with a bounded read:
MAX_ENTRY_BYTES = 25 * 1024 * 1024
buf = io.BytesIO()
with zf.open(raw_name) as entry_fh:
    read = 0
    while True:
        chunk = entry_fh.read(65536)
        if not chunk:
            break
        read += len(chunk)
        if read > MAX_ENTRY_BYTES:
            errors.append({"filename": raw_name, "error": "File exceeds 25 MB limit"})
            buf = None
            break
        buf.write(chunk)
if buf is None:
    continue
entry_bytes = buf.getvalue()
```

This ensures decompression is bounded by `MAX_ENTRY_BYTES` per entry without relying on metadata.

---

### CR-03: Commit loop has no rollback — DB failure after partial write leaves orphaned files on disk

**File:** `backend/compliance_bulk_evidence_endpoints.py:156-186`
**Issue:** The commit loop interleaves disk writes (`_write_binary`) with database inserts
(`db.control_evidence.insert_one`). If `insert_one` raises an exception for the Nth file (e.g.,
a MongoDB timeout or network error), the outer `except Exception` block returns HTTP 500 but N-1
files are already written to `UPLOAD_DIR` with no corresponding DB records and no cleanup. The
caller receives a generic error with no committed evidence, yet N-1 files consume disk space
indefinitely and are unreachable via the API.

**Fix:** Collect all `(file_path, stored_name)` pairs during the commit loop and clean up on
failure:

```python
written_paths: list[str] = []
try:
    for v in validated:
        stored_name = f"{uuid.uuid4().hex}{v['ext']}"
        file_path = os.path.join(UPLOAD_DIR, stored_name)
        await asyncio.to_thread(_write_binary, file_path, v["bytes"])
        written_paths.append(file_path)
        # ... insert_one ...
except Exception:
    for p in written_paths:
        try:
            await asyncio.to_thread(os.unlink, p)
        except OSError:
            pass
    raise HTTPException(status_code=500, detail="Internal server error")
```

---

## Warnings

### WR-01: `canManageEvidence` permission flag is computed but never used to gate any UI element

**File:** `components/FrameworkDetail.tsx:410`
**Issue:** `canManageEvidence = hasPermission('manage:compliance_evidence')` is declared but
never referenced in JSX. The "Add Control", "Import Controls", "Bulk Upload Evidence", and
per-row "Upload" buttons are all rendered unconditionally for every authenticated user. The
permission check was evidently wired up in preparation but the conditional rendering was never
applied to the bulk button (or any button in this component).

**Fix:**
```tsx
{canManageEvidence && (
  <button
    onClick={() => setIsBulkUploadOpen(true)}
    aria-label="Open bulk evidence upload modal"
    className="inline-flex items-center ..."
  >
    <UploadIcon size={14} className="mr-1.5" />
    Bulk Upload Evidence
  </button>
)}
```
Apply the same guard to "Add Control", "Import Controls", and the per-row "Upload" button.

---

### WR-02: Manifest picker `<div>` is not keyboard-accessible (WCAG 2.1 SC 2.1.1)

**File:** `components/BulkEvidenceUploadModal.tsx:112-115`
**Issue:** The zip file picker (Section 1) correctly uses `role="button"`, `tabIndex={0}`, and
`onKeyDown` (lines 86-88). The manifest picker `<div>` at line 112 uses only `onClick` with no
`role`, `tabIndex`, or keyboard handler. Keyboard-only users cannot activate it.

**Fix:**
```tsx
<div
  role="button"
  tabIndex={0}
  aria-label="Select manifest JSON file"
  onClick={() => manifestRef.current?.click()}
  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') manifestRef.current?.click(); }}
  className="border-2 border-dashed ..."
>
```

---

### WR-03: Frontend cannot distinguish "uncompressed size exceeded" (HTTP 400) from generic errors

**File:** `components/BulkEvidenceUploadModal.tsx:59` / `backend/compliance_bulk_evidence_endpoints.py:86`
**Issue:** The backend returns HTTP 413 when the compressed zip exceeds 200 MB (line 79) but HTTP
400 when the uncompressed content exceeds 200 MB (line 87). The frontend catch block at line 59
only tests `err.status === 413`, so the "Uncompressed content exceeds 200 MB" 400 response falls
through to the generic "Upload failed. Please try again..." message. Users who hit the zip-bomb
guard receive an unhelpful error with no actionable guidance.

**Fix (two options):**
1. Change the backend status code for the uncompressed check to 413 as well, so the frontend
   check already handles it:
   ```python
   raise HTTPException(status_code=413, detail="Uncompressed content exceeds 200 MB")
   ```
2. Or extend the frontend catch to also check for the 400 with the uncompressed message:
   ```tsx
   else if (typeof err.detail === 'string' && err.detail.includes('Uncompressed content'))
       setFatalError('The zip contains too much data when decompressed. Reduce the batch size.');
   ```

---

### WR-04: Chain-of-custody writes are not asserted in any test

**File:** `backend/tests/test_bulk_evidence_upload.py:43-56, 346-379`
**Issue:** `_make_mock_db` sets up `raw.evidence_audit_log.insert_one` as an `AsyncMock` and
attaches it as `db._db.evidence_audit_log.insert_one`. However, no test asserts that
`db_mock._db.evidence_audit_log.insert_one` is called. A regression that silently skips CoC
writes would not be caught by the current suite.

**Fix:** Add to `test_bulk_appears_in_control_evidence`:
```python
# One CoC entry per file committed
assert db_mock._db.evidence_audit_log.insert_one.await_count == 2
coc_calls = db_mock._db.evidence_audit_log.insert_one.call_args_list
assert all(c[0][0]["action_type"] == "create" for c in coc_calls)
assert all(c[0][0]["tenantId"] == "tenant-b" for c in coc_calls)
```

---

### WR-05: Test module docstring incorrectly claims `asyncio.run()` is used

**File:** `backend/tests/test_bulk_evidence_upload.py:3`
**Issue:** The module docstring states "Uses asyncio.run() (pytest-asyncio not installed —
project decision 02-01)". No `asyncio.run()` call exists anywhere in the file. All tests use
`TestClient` (synchronous) and `patch("asyncio.to_thread", ...)`. The false claim could mislead
future contributors into believing async test infrastructure is present.

**Fix:**
```python
"""Phase 8 bulk evidence upload tests — BULK-01, BULK-02, BULK-03, security guards.

All tests are synchronous (TestClient). asyncio.to_thread is patched where needed.
(pytest-asyncio not installed — project decision 02-01)
"""
```

---

## Info

### IN-01: `FrameworkDetail.tsx` exceeds the 500-line project limit (873 lines)

**File:** `components/FrameworkDetail.tsx:1-873`
**Issue:** CLAUDE.md mandates files under 500 lines. At 873 lines, this file is 74% over budget.
It contains four embedded modal components (`ControlEvidenceUploadModal`, `AddControlModal`,
`ReportsModal`, `FrameworkDetail`) that could each be extracted to their own files.

**Fix:** Extract the three inline modals to `components/ControlEvidenceUploadModal.tsx`,
`components/AddControlModal.tsx`, and `components/ReportsModal.tsx` respectively.

---

### IN-02: `BulkUploadResult.evidence` typed as `any[]`

**File:** `services/apiService.ts:705`
**Issue:**
```ts
export interface BulkUploadResult {
    evidence: any[];   // <-- untyped
}
```
The response shape is known from the backend: each entry has `id`, `name`, `url`, `type`,
`uploadedAt`, `controlId`, `tenantId`, `source`, `bulk_batch_id`, etc. Using `any[]` loses type
safety for any code that consumes `BulkUploadResult.evidence`.

**Fix:**
```ts
export interface BulkEvidenceRecord {
    id: string;
    name: string;
    url: string;
    type: string;
    uploadedAt: string;
    controlId: string;
    tenantId: string;
    source: string;
    bulk_batch_id: string;
}

export interface BulkUploadResult {
    success: boolean;
    committed: number;
    batch_id: string;
    evidence: BulkEvidenceRecord[];
}
```

---

### IN-03: Close buttons in `FrameworkDetail` modals lack `aria-label`

**File:** `components/FrameworkDetail.tsx:90, 213, 275`
**Issue:** Three `<button onClick={onClose}><XIcon ...></button>` elements have no `aria-label`
or `title`, so screen readers announce only "button" with no context.

**Fix:**
```tsx
<button onClick={onClose} aria-label="Close modal">
  <XIcon size={20} className="text-gray-500" />
</button>
```

---

_Reviewed: 2026-06-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
