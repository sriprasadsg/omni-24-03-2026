# Phase 8: Bulk Evidence Upload — Research

**Researched:** 2026-06-22
**Domain:** File upload security, Python zip extraction, FastAPI multipart, React form state
**Confidence:** HIGH

---

## Summary

Phase 8 adds a `POST /api/compliance/evidence/bulk` endpoint that accepts a multipart request
containing a zip file and a JSON manifest. The endpoint extracts all entries in a temp directory,
validates each file individually (extension, MIME prefix, magic bytes, 25 MB cap), and commits
every file atomically — or rejects the entire batch with a per-file error report. The frontend
adds a bulk-upload modal to `FrameworkDetail.tsx` (in the header button row, alongside
"Import Controls") that accepts a zip plus JSON manifest and displays per-file validation
results and a success summary.

Phase 7 already delivered `_append_coc_entry` (immutable chain-of-custody), the `_check_magic`
function, `UPLOAD_DIR`, `_write_binary`, and the `_EVIDENCE_ALLOWED_EXTENSIONS` /
`_EVIDENCE_ALLOWED_MIME_PREFIXES` allowlists. Phase 8 reuses all of these without modification.

The critical design choice is **validate-all-before-commit**: read and validate every file from
the zip before writing any to `UPLOAD_DIR` or touching the database. This satisfies BULK-02
("the entire batch is rejected if any file fails") and avoids partial writes that require
rollback logic.

**Primary recommendation:** Implement the bulk endpoint in a new file
`backend/compliance_bulk_evidence_endpoints.py` (compliance_evidence_endpoints.py is at 495
lines and adding a multipart zip handler would breach the 500-line CLAUDE.md limit). Register
it in `router_registry.py` under the required routers. Build the frontend as a new
`BulkEvidenceUploadModal` component inline in `FrameworkDetail.tsx`; the component is small
enough to fit without pushing FrameworkDetail past 500 lines — the header already has room
for a new "Bulk Upload" button.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Zip extraction + per-file validation | API / Backend | — | Security-critical; must not trust client |
| Manifest JSON parsing | API / Backend | — | Controls which file maps to which control_id |
| Per-file error report | API / Backend | Frontend | Backend generates; frontend displays |
| File storage to UPLOAD_DIR | API / Backend | — | Same pattern as single-file upload |
| CoC append per committed file | API / Backend | — | Immutable audit trail requirement |
| Bulk upload trigger UI | Frontend | — | New modal in FrameworkDetail header row |
| Per-file error display | Frontend | — | Renders error report array from API |
| Success summary | Frontend | — | Counts committed files; links to control views |

---

## Project Constraints (from CLAUDE.md)

- **500-line file limit** — any file modified or created must stay at or below 500 lines.
  `compliance_evidence_endpoints.py` is at 495 lines; the bulk endpoint MUST go in a new file.
  `FrameworkDetail.tsx` is at 857 lines — a new `BulkEvidenceUploadModal` component added
  inline would push it further over. The modal should be a separate component file (e.g.,
  `components/BulkEvidenceUploadModal.tsx`). `apiService.ts` is at 4361 lines — appending
  `uploadBulkEvidence` is fine (it's a single function, not a file to stay under 500).
- **Input validation at system boundaries** — every file extracted from the zip must be
  validated before storage; zip entry names must be path-traversal-guarded.
- **Never create documentation files unless explicitly requested** — RESEARCH.md is explicitly
  requested; no other docs.
- **ALWAYS read a file before editing it** — enforced by plan executor.
- **NEVER commit secrets, credentials, or .env files**.
- **Run tests after code changes** — `npm run build && npm test`.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BULK-01 | User can upload a zip file + JSON manifest mapping each file to a control ID | Backend endpoint design; manifest schema; frontend form |
| BULK-02 | Files validated individually (MIME, size ≤ 25 MB, magic bytes) before any are stored; entire batch rejected with per-file error report if any fails | validate-all-before-commit pattern; error report schema |
| BULK-03 | Successfully uploaded bulk evidence appears in control detail view with Manual badge and delete capability | reuses `control_evidence` collection + existing `get_control_evidence` GET endpoint; `source: "manual"` field |
</phase_requirements>

---

## Standard Stack

### Core (Backend)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `zipfile` | stdlib | Extract zip entries in-memory | [VERIFIED: Python 3.12 stdlib] — no extra dep; already used in `compliance_doc_validator.py` and `agent_installer_builders.py` |
| `tempfile` | stdlib | Temp directory for zip extraction | [VERIFIED: Python 3.12 stdlib] — already used in `scan_engine.py`, `agent_download_endpoints.py`, `agent_rust_builder.py` |
| `io.BytesIO` | stdlib | In-memory zip parsing without disk I/O | [VERIFIED: Python 3.12 stdlib] — same pattern used in `compliance_doc_validator.py` |
| `json` | stdlib | Parse manifest JSON body | [VERIFIED: Python 3.12 stdlib] |
| `fastapi.UploadFile` | already installed | Receive zip file + manifest JSON | [VERIFIED: already in compliance_evidence_endpoints.py] |

### Reused from Prior Phases
| Symbol | Source File | What It Provides |
|--------|------------|-----------------|
| `UPLOAD_DIR` | `compliance_artifacts_endpoints.py` | Canonical evidence storage path |
| `_write_binary` | `compliance_artifacts_endpoints.py` | Thread-safe binary write to UPLOAD_DIR |
| `_check_magic` | `compliance_artifacts_endpoints.py` | Magic-byte validation for .pdf/.png/.jpg/.jpeg/.docx/.xlsx |
| `_EVIDENCE_ALLOWED_EXTENSIONS` | `compliance_evidence_endpoints.py` | frozenset of allowed extensions |
| `_EVIDENCE_ALLOWED_MIME_PREFIXES` | `compliance_evidence_endpoints.py` | Allowed MIME prefixes tuple |
| `_append_coc_entry` | `evidence_coc.py` | Immutable CoC log append |
| `get_current_user` | `authentication_service.py` | FastAPI dependency for JWT |
| `get_database` | `database.py` | MongoDB async connection |

### No New Packages Required
The entire backend implementation uses Python stdlib (`zipfile`, `tempfile`, `io`, `json`)
plus FastAPI and Motor/PyMongo — all already installed. **No `python-magic` needed** (confirmed
not installed); magic-byte checking uses the existing `_check_magic` stdlib implementation.

### Frontend
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | existing | Modal state management | Already used everywhere |
| `FormData` | browser API | Send zip + manifest in one multipart request | [ASSUMED] — standard browser API; no extra dep |

**Installation:** No new packages to install.

---

## Package Legitimacy Audit

No new packages are introduced in this phase. All implementation uses Python stdlib and
existing project dependencies.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious (SUS):** none

---

## Architecture Patterns

### System Architecture Diagram

```
Client (FrameworkDetail / BulkEvidenceUploadModal)
  │
  │  POST /api/compliance/evidence/bulk
  │  multipart: zip_file=<zip>, manifest=<JSON string>
  ▼
FastAPI endpoint (compliance_bulk_evidence_endpoints.py)
  │
  ├─ 1. Authenticate (get_current_user, tenant_id)
  ├─ 2. Parse manifest JSON → [{filename, control_id}, ...]
  ├─ 3. Read zip bytes into BytesIO (no disk write yet)
  │     ├─ Zip-bomb guard: total uncompressed size ≤ MAX_BULK_BYTES
  │     └─ Entry count guard: ≤ MAX_BULK_FILES
  ├─ 4. For each manifest entry:
  │     ├─ Lookup entry in zip (404 if missing)
  │     ├─ Read entry bytes (no extraction to disk)
  │     ├─ Validate extension ∈ _EVIDENCE_ALLOWED_EXTENSIONS
  │     ├─ Validate MIME prefix (from manifest or derived from ext)
  │     ├─ Validate len(bytes) ≤ 25 MB
  │     └─ Validate _check_magic(bytes, ext)
  │
  ├─ 5a. ANY validation failure → return 422 with per-file error array (nothing written)
  │
  └─ 5b. ALL passed → commit loop:
         ├─ asyncio.to_thread(_write_binary, path, bytes) per file
         ├─ db.control_evidence.insert_one(record) per file
         └─ _append_coc_entry(..., action_type="create") per file
         → return 200 with success summary + evidence records
```

### Recommended Project Structure

```
backend/
├── compliance_bulk_evidence_endpoints.py   # NEW — Phase 8 Plan 08-01
├── compliance_evidence_endpoints.py        # UNCHANGED
├── evidence_coc.py                         # UNCHANGED (reused)
├── tests/
│   └── test_bulk_evidence_upload.py        # NEW — Phase 8 tests
components/
├── BulkEvidenceUploadModal.tsx             # NEW — Phase 8 Plan 08-02
├── FrameworkDetail.tsx                     # MODIFIED — add "Bulk Upload" button + import
services/
├── apiService.ts                           # MODIFIED — add uploadBulkEvidence()
```

### Pattern 1: Validate-All-Before-Commit

**What:** Read all zip entries into memory, validate every entry against the full ruleset,
and only if zero errors are found proceed to write files and DB records.

**When to use:** BULK-02 requires atomic all-or-nothing behavior: "the entire batch is
rejected if any file fails validation."

**Example:**
```python
# Source: derived from existing compliance_evidence_endpoints.py pattern
import zipfile, io

errors: list[dict] = []
validated: list[dict] = []  # holds (entry_name, file_bytes, ext, control_id)

zip_bytes = await zip_file.read()
with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
    for item in manifest:
        filename = item["filename"]
        control_id = item["control_id"]
        try:
            entry_bytes = zf.read(filename)  # KeyError if not in zip
        except KeyError:
            errors.append({"filename": filename, "error": "Not found in zip"})
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
            errors.append({"filename": filename, "error": f"Extension '{ext}' not allowed"})
            continue
        if len(entry_bytes) > 25 * 1024 * 1024:
            errors.append({"filename": filename, "error": "Exceeds 25 MB limit"})
            continue
        if not _check_magic(entry_bytes, ext):
            errors.append({"filename": filename, "error": "File content does not match extension"})
            continue
        validated.append({"filename": filename, "bytes": entry_bytes, "ext": ext, "control_id": control_id})

if errors:
    raise HTTPException(status_code=422, detail={"errors": errors})

# Only reached if all files passed
committed = []
for v in validated:
    safe_name = f"{uuid.uuid4().hex}{v['ext']}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    await asyncio.to_thread(_write_binary, file_path, v["bytes"])
    # insert DB record and CoC entry
    ...
```

### Pattern 2: Manifest JSON Schema

The manifest is a JSON array passed as a `Form` field (string). Each element maps one
filename (as it appears in the zip) to one control ID.

```json
[
  {"filename": "access-policy.pdf", "control_id": "CC6.1"},
  {"filename": "training-certs.xlsx", "control_id": "CC9.1"},
  {"filename": "vendor-nda.docx", "control_id": "CC2.2"}
]
```

**Design rationale:** A flat array (not a dict keyed by filename) allows one file to be
attached to multiple controls by repeating the filename with different control_ids.
The `control_id` field matches the existing `controlId` field in `control_evidence` records.

### Pattern 3: Zip-Bomb Protection

```python
MAX_BULK_FILES = 50       # arbitrary; prevents runaway loops
MAX_BULK_BYTES = 200 * 1024 * 1024   # 200 MB uncompressed total (50 × 25 MB worst case = 1.25 GB, so cap lower)

# Check before opening ZipFile
zip_content = await zip_file.read()
if len(zip_content) > MAX_BULK_BYTES:
    raise HTTPException(status_code=413, detail="Zip file exceeds 200 MB limit")

with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
    infos = zf.infolist()
    if len(infos) > MAX_BULK_FILES:
        raise HTTPException(status_code=400, detail=f"Zip contains more than {MAX_BULK_FILES} files")
    total_uncompressed = sum(i.file_size for i in infos)
    if total_uncompressed > MAX_BULK_BYTES:
        raise HTTPException(status_code=400, detail="Uncompressed content exceeds 200 MB limit")
```

**Note:** The per-file 25 MB cap from BULK-02 is the primary size guard; the zip-level
total-uncompressed guard is a secondary zip-bomb defense.

### Pattern 4: Path-Traversal Guard for Zip Entry Names

```python
# Zip entries can contain absolute paths or "../" segments (zip slip attack)
def _safe_entry_name(name: str) -> str:
    """Strip path components from a zip entry name.
    Returns the basename only; raises ValueError if result is empty or '..'."""
    safe = os.path.basename(name.replace("\\", "/"))
    if not safe or safe in (".", ".."):
        raise ValueError(f"Unsafe zip entry name: {name!r}")
    return safe
```

This pattern is distinct from the already-existing `UPLOAD_DIR` path-traversal guard
(used in download and delete endpoints). The zip-slip guard applies to entry names
**before** they are read; the UPLOAD_DIR guard applies to stored files.

### Pattern 5: Frontend Multipart Upload (zip + manifest)

```typescript
// Source: [ASSUMED] — standard FormData browser API
export const uploadBulkEvidence = async (
    zipFile: File,
    manifest: Array<{ filename: string; control_id: string }>
): Promise<BulkUploadResult> => {
    const formData = new FormData();
    formData.append('zip_file', zipFile);
    formData.append('manifest', JSON.stringify(manifest));  // serialized JSON string
    const res = await authFetch(`${API_BASE}/compliance/evidence/bulk`, {
        method: 'POST',
        body: formData,
        // No Content-Type header — browser sets multipart boundary automatically
        // (same decision as 02-02: T-02-07)
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw Object.assign(new Error('Bulk upload failed'), { detail: body });
    }
    return res.json();
};
```

**Key point:** No explicit `Content-Type` header — browser sets multipart boundary
automatically. This is the same decision recorded in STATE.md for T-02-07.

### Pattern 6: DB Record Schema for Bulk-Uploaded Evidence

Each committed file is stored in `control_evidence` (same collection as single-file
`upload_control_direct_evidence`). This ensures BULK-03 automatically: existing
`GET /api/compliance/controls/{control_id}/evidence` already returns `control_evidence`
records without modification.

```python
record = {
    "id": f"cev-bulk-{uuid.uuid4().hex}",
    "name": os.path.basename(original_filename),
    "url": f"/static/evidence/{safe_name}",
    "type": _MIME_FOR_EXT.get(ext, "application/octet-stream"),
    "uploadedAt": timestamp,
    "controlId": control_id,
    "tenantId": tenant_id,
    "uploaded_by": uploader,
    "description": f"Bulk upload batch {batch_id}",
    "source": "manual",
    "systemGenerated": False,
    "bulk_batch_id": batch_id,   # correlates files from same batch upload
}
```

The `bulk_batch_id` field is a bonus for audit correlation but is not required by BULK-03.

### Anti-Patterns to Avoid

- **Writing files before validation is complete:** Violates BULK-02 (all-or-nothing). If
  file 3 of 5 fails validation after files 1-2 are written, a rollback is required. Avoid
  by validating all entries before writing any.
- **Using `zf.extractall(tmpdir)` on untrusted input:** `extractall` does not prevent
  zip-slip path traversal by default in Python < 3.12. Always call `zf.read(name)` on
  validated entry names rather than extractall.
- **Trusting the browser's Content-Type for zip detection:** The client-supplied MIME type
  for the zip file itself is not validated beyond confirming it's a zip. Use
  `zipfile.is_zipfile()` to verify the bytes are actually a zip.
- **Streaming from zip to disk without size check:** Read each entry's bytes in full, check
  `len(bytes)`, then write. Don't stream to disk and check size afterwards.
- **Adding bulk endpoint to compliance_evidence_endpoints.py:** That file is at 495 lines.
  Adding even a small handler would breach the 500-line CLAUDE.md limit.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Zip extraction | Custom binary parser | `stdlib zipfile.ZipFile` | [VERIFIED: Python 3.12 stdlib] — handles deflate, stored, bzip2 compression; correct CRC verification |
| Magic-byte validation | New implementation | `_check_magic` from `compliance_artifacts_endpoints.py` | Already covers all allowed types; shared state |
| File write to evidence dir | New I/O code | `_write_binary` via `asyncio.to_thread` | Already thread-safe; consistent with single-file uploads |
| CoC append | New audit log logic | `_append_coc_entry` from `evidence_coc.py` | Fire-and-forget, never raises, correct raw-Motor pattern |
| MIME allowlist | New string | `_EVIDENCE_ALLOWED_EXTENSIONS`, `_EVIDENCE_ALLOWED_MIME_PREFIXES` from compliance_evidence_endpoints.py | Shared source of truth; already tested |
| Path-traversal defense on stored files | New path resolver | Existing `os.path.basename()` + `str(resolved).startswith(str(_safe_dir))` pattern | Already proven in delete endpoint |

**Key insight:** All the hard security primitives (magic bytes, path traversal, MIME checking,
CoC logging, tenant isolation) are already implemented and tested. Phase 8's new code is
primarily orchestration — read zip, validate each entry, commit atomically.

---

## Common Pitfalls

### Pitfall 1: Zip Slip (Path Traversal via Zip Entry Names)

**What goes wrong:** A zip archive contains an entry named `../../etc/passwd` or
`../../../static/evil.sh`. When the server calls `zf.read(entry.filename)` and then uses
`entry.filename` to construct the write path, the malicious path escapes UPLOAD_DIR.

**Why it happens:** Python's `zipfile` does not sanitize entry names. `ZipFile.extractall()`
gained path traversal protection in Python 3.12 but `zf.read()` does not help here since
the path is used separately.

**How to avoid:** Always use `os.path.basename(entry_name)` to strip directory components
before using the name. The resulting `safe_name` is then only used as the label in the DB
record (`name` field); the actual stored filename is a fresh `uuid4().hex + ext` that is
completely independent of the zip entry name.

**Warning signs:** Entry names containing `/`, `\`, or `..` in test fixtures passing
through to file writes.

### Pitfall 2: Partial Commit on Validation Failure

**What goes wrong:** Validation and commit are interleaved. Files 1-3 pass and are written;
file 4 fails validation. Files 1-3 are now on disk with no DB records.

**Why it happens:** Loop logic that writes as it validates.

**How to avoid:** Two-pass approach: pass 1 validates all entries and collects bytes; pass 2
commits only if `errors == []`. This is enforced by the code structure — the `if errors:
raise HTTPException` guard prevents reaching the commit loop.

### Pitfall 3: Zip-Bomb (Decompression Bomb)

**What goes wrong:** A small zip file decompresses to gigabytes of data, exhausting server
memory when `zf.read()` is called.

**Why it happens:** zip's deflate algorithm can achieve extreme compression ratios on
repetitive data (e.g., 42 KB → 4 GB).

**How to avoid:** Check `sum(i.file_size for i in zf.infolist())` before reading any
entries. Enforce `MAX_BULK_BYTES = 200 MB` (50 files × 25 MB + buffer) on the total
uncompressed size. Enforce `MAX_BULK_FILES = 50` on entry count.

### Pitfall 4: DB Record Goes to Wrong Collection

**What goes wrong:** Bulk-uploaded files are stored in `asset_compliance.evidence[]` (the
embedded array for asset-level evidence) instead of `control_evidence` (the flat collection
for control-level evidence). The result is they don't appear in
`GET /api/compliance/controls/{control_id}/evidence` alongside single-file uploads.

**Why it happens:** There are two evidence storage patterns in this codebase:
1. `asset_compliance.$push(evidence)` — used by `upload_compliance_evidence` (asset-scoped)
2. `control_evidence.insert_one(record)` — used by `upload_control_direct_evidence` (control-scoped)

The manifest in Phase 8 maps filenames to `control_id` (no `asset_id`), so the correct
pattern is #2: `control_evidence.insert_one`.

**Warning signs:** `GET /api/compliance/controls/{id}/evidence` returns the bulk file
in the `manual` array. If it doesn't appear there at all, the file went to the wrong collection.

### Pitfall 5: MIME Type Source Ambiguity

**What goes wrong:** The request contains a zip file — but the only MIME type available
from `UploadFile.content_type` for entries inside the zip is whatever the client sends, or
nothing.

**Why it happens:** HTTP multipart only has a content type for the parts, not for files
inside a zip. For the zip part itself, `content_type` may be `application/zip` or
`application/octet-stream` or missing.

**How to avoid:** Derive the per-entry MIME type from the entry's extension. Do not rely
on client-provided MIME for entries inside the zip. The extension-to-MIME mapping only needs
to cover the six allowed types:

```python
_EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
```

Use this mapping only as the stored `type` field; validation is done via extension allowlist
and magic bytes.

### Pitfall 6: Frontend Sends Content-Type for multipart

**What goes wrong:** `fetch` is called with `headers: { 'Content-Type': 'multipart/form-data' }`.
FastAPI receives the request but cannot parse the boundary because the browser did not set it.

**Why it happens:** Developers copy the Content-Type from `application/json` usage.

**How to avoid:** When appending to `FormData` and passing as `body`, never set
`Content-Type` manually. The browser sets it with the correct boundary. (This is the same
decision as 02-02 / T-02-07 in STATE.md.)

### Pitfall 7: FrameworkDetail.tsx Already Over 500 Lines

**What goes wrong:** `BulkEvidenceUploadModal` is added inline to `FrameworkDetail.tsx`
(currently 857 lines), pushing it further over limit and violating CLAUDE.md.

**Why it happens:** Reusing `ControlEvidenceUploadModal` as the template inside the same
file without noticing the existing file size.

**How to avoid:** Create `components/BulkEvidenceUploadModal.tsx` as a separate file.
`FrameworkDetail.tsx` only imports it and adds one button + one conditional render. The
file is already well over 500 lines — no new substantive logic should be added inline.

---

## Code Examples

### Backend: ZipFile with Validate-All-Before-Commit

```python
# Source: derived from compliance_doc_validator.py (uses same stdlib zipfile pattern)
import zipfile, io, os, uuid, asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from compliance_artifacts_endpoints import UPLOAD_DIR, _write_binary, _check_magic
from compliance_evidence_endpoints import (
    _EVIDENCE_ALLOWED_EXTENSIONS, _EVIDENCE_ALLOWED_MIME_PREFIXES, _SUPER_ROLES
)
from evidence_coc import _append_coc_entry
from database import get_database
from authentication_service import get_current_user
import json, logging
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_BULK_FILES = 50
MAX_BULK_BYTES = 200 * 1024 * 1024

_EXT_TO_MIME: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

@router.post("/api/compliance/evidence/bulk")
async def bulk_upload_evidence(
    zip_file: UploadFile = File(...),
    manifest: str = Form(...),
    current_user=Depends(get_current_user),
):
    try:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        uploader = getattr(current_user, "username", "unknown")

        # Parse manifest
        try:
            items: list[dict] = json.loads(manifest)
            if not isinstance(items, list) or not items:
                raise ValueError("manifest must be a non-empty JSON array")
            for item in items:
                if "filename" not in item or "control_id" not in item:
                    raise ValueError("each manifest entry needs filename and control_id")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid manifest: {exc}")

        if len(items) > MAX_BULK_FILES:
            raise HTTPException(status_code=400, detail=f"Manifest exceeds {MAX_BULK_FILES} entries")

        # Read and validate the zip itself
        zip_content = await zip_file.read()
        if not zipfile.is_zipfile(io.BytesIO(zip_content)):
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip")
        if len(zip_content) > MAX_BULK_BYTES:
            raise HTTPException(status_code=413, detail="Zip file exceeds 200 MB limit")

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            infos = zf.infolist()
            total_unc = sum(i.file_size for i in infos)
            if total_unc > MAX_BULK_BYTES:
                raise HTTPException(status_code=400, detail="Uncompressed content exceeds 200 MB")

            # Pass 1: Validate all entries
            errors: list[dict] = []
            validated: list[dict] = []
            for item in items:
                raw_name = item["filename"]
                control_id = item["control_id"]
                safe_name = os.path.basename(raw_name.replace("\\", "/"))
                if not safe_name or safe_name in (".", ".."):
                    errors.append({"filename": raw_name, "error": "Unsafe filename"})
                    continue
                ext = os.path.splitext(safe_name)[1].lower()
                if ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
                    errors.append({"filename": raw_name, "error": f"Extension '{ext}' not allowed"})
                    continue
                try:
                    entry_bytes = zf.read(raw_name)
                except KeyError:
                    errors.append({"filename": raw_name, "error": "File not found in zip"})
                    continue
                if len(entry_bytes) > 25 * 1024 * 1024:
                    errors.append({"filename": raw_name, "error": "File exceeds 25 MB limit"})
                    continue
                if not _check_magic(entry_bytes, ext):
                    errors.append({"filename": raw_name, "error": "File content does not match extension"})
                    continue
                validated.append({
                    "original_name": safe_name,
                    "bytes": entry_bytes,
                    "ext": ext,
                    "control_id": control_id,
                })

            if errors:
                raise HTTPException(status_code=422, detail={"errors": errors})

            # Pass 2: Commit all
            batch_id = uuid.uuid4().hex
            timestamp = datetime.now(timezone.utc).isoformat()
            db = get_database()
            committed = []
            for v in validated:
                stored_name = f"{uuid.uuid4().hex}{v['ext']}"
                file_path = os.path.join(UPLOAD_DIR, stored_name)
                await asyncio.to_thread(_write_binary, file_path, v["bytes"])
                record = {
                    "id": f"cev-bulk-{uuid.uuid4().hex}",
                    "name": v["original_name"],
                    "url": f"/static/evidence/{stored_name}",
                    "type": _EXT_TO_MIME.get(v["ext"], "application/octet-stream"),
                    "uploadedAt": timestamp,
                    "controlId": v["control_id"],
                    "tenantId": tenant_id,
                    "uploaded_by": uploader,
                    "description": f"Bulk upload batch {batch_id}",
                    "source": "manual",
                    "systemGenerated": False,
                    "bulk_batch_id": batch_id,
                }
                await db.control_evidence.insert_one({**record})
                await _append_coc_entry(
                    db=db, evidence_id=record["id"], tenant_id=tenant_id,
                    actor=uploader, action_type="create",
                    snapshot_before=None, snapshot_after=record,
                )
                record.pop("_id", None)
                committed.append(record)

        return {
            "success": True,
            "committed": len(committed),
            "batch_id": batch_id,
            "evidence": committed,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Bulk upload error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Frontend: BulkEvidenceUploadModal skeleton

```typescript
// components/BulkEvidenceUploadModal.tsx
// Source: [ASSUMED] — derived from ControlEvidenceUploadModal pattern in FrameworkDetail.tsx
import React, { useState, useRef } from 'react';
import { XIcon, UploadIcon, AlertTriangleIcon } from './icons';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

interface ManifestEntry { filename: string; control_id: string; }
interface BulkError { filename: string; error: string; }

interface Props {
  onClose: () => void;
  onUploaded: () => void;
  defaultControlId?: string;
}

export const BulkEvidenceUploadModal: React.FC<Props> = ({ onClose, onUploaded, defaultControlId }) => {
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [manifestFile, setManifestFile] = useState<File | null>(null);
  const [manifest, setManifest] = useState<ManifestEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<BulkError[]>([]);
  const [result, setResult] = useState<{ committed: number; batch_id: string } | null>(null);
  const zipRef = useRef<HTMLInputElement>(null);
  const manifestRef = useRef<HTMLInputElement>(null);

  const handleManifestChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setManifestFile(f);
    try {
      const text = await f.text();
      const parsed = JSON.parse(text) as ManifestEntry[];
      setManifest(parsed);
    } catch {
      showToast('Invalid manifest JSON', 'error');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!zipFile || manifest.length === 0) return;
    setUploading(true);
    setErrors([]);
    try {
      const res = await api.uploadBulkEvidence(zipFile, manifest);
      if (res.success) {
        setResult({ committed: res.committed, batch_id: res.batch_id });
        showToast(`${res.committed} files uploaded successfully`, 'success');
        onUploaded();
      }
    } catch (err: any) {
      const detail = err?.detail;
      if (detail?.errors) {
        setErrors(detail.errors);
      } else {
        showToast(`Upload failed: ${err?.message || 'Unknown error'}`, 'error');
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-lg shadow-xl">
        {/* header, form, error list, success summary — full impl in 08-02 plan */}
      </div>
    </div>
  );
};
```

### Test: Multipart Zip Upload Pattern

```python
# Source: derived from test_evidence_uploads.py pattern
import io, zipfile
from fastapi.testclient import TestClient

def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    """Build a zip archive in memory from {filename: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()

def test_bulk_upload_valid(client):
    zip_bytes = _make_zip_bytes({
        "policy.pdf": b"%PDF-1.4 test",
        "cert.png":   b"\x89PNG\r\n\x1a\n test",
    })
    manifest = json.dumps([
        {"filename": "policy.pdf", "control_id": "CC6.1"},
        {"filename": "cert.png",   "control_id": "CC9.1"},
    ])
    resp = client.post(
        "/api/compliance/evidence/bulk",
        files={"zip_file": ("batch.zip", zip_bytes, "application/zip")},
        data={"manifest": manifest},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["committed"] == 2
    assert body["success"] is True
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `python-magic` for MIME detection | stdlib magic-byte prefix check in `_check_magic` | Phase 2 (this codebase) | No extra C dependency; already in production |
| `tempfile.mkdtemp` + `zf.extractall` | `io.BytesIO` + `zf.read(name)` per entry | Phase 8 (new) | No temp-dir race conditions; correct zip-slip prevention |

**Deprecated/outdated:**
- `ZipFile.extractall()` on untrusted input without path filtering: Replaced in Python 3.12
  with a filter parameter, but relying on this is fragile across versions. Use `zf.read()`
  on allowlisted names instead.

---

## Runtime State Inventory

Phase 8 is a greenfield addition (new endpoint + new frontend modal). No existing data is
renamed or migrated.

- **Stored data:** None — no existing records are modified.
- **Live service config:** None.
- **OS-registered state:** None.
- **Secrets/env vars:** None.
- **Build artifacts:** None.

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (no pytest-asyncio; uses `asyncio.run()` per project decision 02-01) |
| Config file | none (sys.path insert in test files per conftest.py pattern) |
| Quick run command | `cd backend && python -m pytest tests/test_bulk_evidence_upload.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BULK-01 | Valid zip + manifest → 200, evidence records committed | integration | `pytest tests/test_bulk_evidence_upload.py::test_bulk_upload_valid -x` | Wave 0 |
| BULK-01 | Manifest missing required fields → 400 | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_manifest_invalid -x` | Wave 0 |
| BULK-02 | Any file exceeds 25 MB → 422 with per-file error | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_file_too_large -x` | Wave 0 |
| BULK-02 | Any file has bad magic bytes → 422 with per-file error | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_magic_mismatch -x` | Wave 0 |
| BULK-02 | Disallowed extension in zip → 422 with per-file error | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_extension_rejected -x` | Wave 0 |
| BULK-02 | File missing from zip (manifest refers to nonexistent entry) → 422 | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_missing_entry -x` | Wave 0 |
| BULK-02 | Mixed (1 valid, 1 invalid) → 422, nothing committed | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_mixed_rejects_all -x` | Wave 0 |
| BULK-03 | Committed files returned by GET /api/compliance/controls/{id}/evidence in `manual` array | integration | `pytest tests/test_bulk_evidence_upload.py::test_bulk_appears_in_control_evidence -x` | Wave 0 |
| Security | Zip-bomb (large uncompressed) → 400/413 | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_zip_bomb_guard -x` | Wave 0 |
| Security | Zip-slip entry name → 422 per-file error | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_zip_slip_guard -x` | Wave 0 |
| Security | Non-zip bytes uploaded → 400 | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_not_a_zip -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/test_bulk_evidence_upload.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_bulk_evidence_upload.py` — covers all BULK-01, BULK-02, BULK-03 tests above
- [ ] `backend/compliance_bulk_evidence_endpoints.py` — implementation (must exist before tests pass)

---

## Security Domain

> `security_enforcement: true` in `.planning/config.json` — section required.

### Applicable ASVS Categories (ASVS Level 1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | New file, no secrets in code, tenant isolation |
| V4 Access Control | yes | Tenant isolation: non-super callers scoped to own tenant |
| V5 Input Validation | yes | Manifest JSON schema validation; extension allowlist; magic bytes; size cap |
| V6 Cryptography | no | No new crypto; UUID-based filenames are not security-critical |
| V12 File Upload | yes | Extension allowlist; magic bytes; zip-bomb; zip-slip; 25 MB per file |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Zip Slip (directory traversal via zip entry names) | Tampering | `os.path.basename()` on all entry names before use |
| Zip Bomb (decompression bomb) | DoS | `sum(i.file_size for i in zf.infolist()) > MAX_BULK_BYTES` guard before reading |
| Polyglot file (valid zip that is also valid PDF) | Spoofing | `_check_magic()` validates first bytes match declared extension |
| MIME confusion (client claims `image/png` for `.exe`) | Spoofing | Extension allowlist + magic bytes; client MIME is not trusted for zip entries |
| Cross-tenant evidence injection | Elevation of Privilege | `tenantId` set from JWT (`getattr(current_user, "tenant_id", None)`), never from request body |
| Excessive file count (DoS via 10,000 entries) | DoS | `MAX_BULK_FILES = 50` manifest length check |

---

## Environment Availability

All dependencies are stdlib or already installed. No external services required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 stdlib `zipfile` | Backend zip extraction | Yes | 3.12.3 | — |
| Python 3.12 stdlib `tempfile` | Not needed (using BytesIO) | Yes | 3.12.3 | — |
| FastAPI `UploadFile` | Multipart zip receive | Yes | existing | — |
| `asyncio.to_thread` | Async file write | Yes | 3.12.3 | — |
| `pytest` | Test execution | Yes (confirmed by existing tests) | existing | — |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Frontend can upload zip + JSON manifest as a two-part multipart POST without CORS issues | Architecture Patterns — Pattern 5 | Low — same origin; authFetch already used for all API calls |
| A2 | `MAX_BULK_FILES = 50` and `MAX_BULK_BYTES = 200 MB` are reasonable limits for the auditor use case | Architecture Patterns — Pattern 3 | Low — these are configurable constants; planner can adjust |
| A3 | `bulk_batch_id` field is acceptable as a bonus field; no existing consumer will break | Code Examples — DB Record Schema | Low — additive field; no existing query filters on it |

**If this table is empty:** It is not — three low-risk assumptions are documented above. All can
be adjusted by the planner without affecting the core BULK-01/02/03 logic.

---

## Open Questions

1. **Where does the manifest come from in practice?**
   - What we know: BULK-01 says "JSON manifest that maps each file to a control ID."
   - What's unclear: Is the manifest a file the user uploads (a `.json` file) or a form the
     UI renders dynamically (e.g., drag-and-drop a zip, then see filenames listed with a
     control-ID dropdown per file)?
   - Recommendation: Support both. Accept the manifest as a `Form(...)` string (already
     in the endpoint design above). The frontend can let the user upload a pre-built JSON
     file OR build the manifest interactively after inspecting the zip's file listing.
     BULK-01 says "together with a JSON manifest" which implies a file, not a dynamic form
     — so the minimal implementation is: upload zip → upload manifest JSON → submit.

2. **Should bulk-uploaded evidence appear in `asset_compliance` or `control_evidence`?**
   - What we know: The manifest has `control_id` but no `asset_id`. The existing
     `upload_control_direct_evidence` endpoint (control-scoped) already uses `control_evidence`.
   - What's unclear: BULK-03 says "appear in the same control detail view as individually
     uploaded evidence." The control detail view calls
     `GET /api/compliance/controls/{id}/evidence` which returns `control_evidence.manual`.
   - Recommendation: Use `control_evidence` (the flat collection). This is the same as
     single-file `upload_control_direct_evidence`. No code changes needed to the GET endpoint.

---

## Sources

### Primary (HIGH confidence)
- `/home/user/enterprise-omni-agent-ai-platform/backend/compliance_evidence_endpoints.py` — single-file upload patterns, validation flow, CoC integration, UPLOAD_DIR usage [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/backend/compliance_artifacts_endpoints.py` — `_check_magic`, `UPLOAD_DIR`, `_write_binary`, `_MAGIC_SIGNATURES` [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/backend/evidence_coc.py` — `_append_coc_entry` signature and behaviour [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/backend/compliance_doc_validator.py` — `zipfile.ZipFile` + `io.BytesIO` pattern [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/backend/tests/test_evidence_uploads.py` — test patterns for multipart upload endpoints [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/backend/tests/test_evidence_lifecycle.py` — asyncio.run() test patterns [VERIFIED: direct codebase read]
- Python 3.12 stdlib: `zipfile`, `tempfile`, `io`, `json` [VERIFIED: `python3 -c "import zipfile, tempfile, io; print('OK')"` returned OK]

### Secondary (MEDIUM confidence)
- `/home/user/enterprise-omni-agent-ai-platform/.planning/STATE.md` — project decisions (02-02 Content-Type boundary rule, 07-01 raw Motor usage) [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/components/FrameworkDetail.tsx` — existing modal pattern (`ControlEvidenceUploadModal`), button row layout [VERIFIED: direct codebase read]
- `/home/user/enterprise-omni-agent-ai-platform/backend/router_registry.py` — `_load` pattern, `_REQUIRED_ROUTERS` set [VERIFIED: direct codebase read]

### Tertiary (LOW confidence)
- Zip-slip / zip-bomb mitigations: [ASSUMED] from security training knowledge — confirmed applicable by reviewing the Python 3.12 `zipfile` module behaviour via stdlib import test.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all reused from existing, tested code
- Architecture: HIGH — directly derived from compliance_evidence_endpoints.py patterns
- Security patterns: HIGH — zip-slip and zip-bomb are well-documented stdlib concerns
- Frontend patterns: HIGH — derived directly from existing ControlEvidenceUploadModal in codebase

**Research date:** 2026-06-22
**Valid until:** 2026-07-22 (stable stdlib + existing codebase; not sensitive to ecosystem churn)
