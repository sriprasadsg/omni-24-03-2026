---
phase: 02-manual-evidence-uploads
plan: "01"
subsystem: backend/compliance
tags: [evidence-upload, file-validation, rbac, delete-endpoint, magic-bytes]
dependency_graph:
  requires: []
  provides:
    - _check_magic helper in compliance_artifacts_endpoints
    - 25 MB size cap on evidence upload
    - Full metadata (uploaded_by, description, tenantId, source, systemGenerated) on evidence record
    - DELETE /api/assets/{asset_id}/compliance/evidence/{evidence_id} endpoint
    - EVID-01/02/04/05 test coverage in backend/tests/test_evidence_uploads.py
  affects:
    - backend/compliance_evidence_endpoints.py
    - backend/compliance_artifacts_endpoints.py
tech_stack:
  added: []
  patterns:
    - stdlib bytes slicing for magic-byte MIME validation
    - FastAPI Request/Response injection in upload handler
    - MongoDB $pull via aggregate pipeline lookup for asset-scoped delete
key_files:
  created:
    - backend/tests/test_evidence_uploads.py
  modified:
    - backend/compliance_artifacts_endpoints.py
    - backend/compliance_evidence_endpoints.py
decisions:
  - "Used asyncio.run() instead of pytest-asyncio (not installed) — consistent with test_rust_heartbeat_parity.py pattern"
  - "DELETE route is asset-scoped: /api/assets/{asset_id}/compliance/evidence/{evidence_id} per plan decision"
  - "Aggregate pipeline uses assetId + evidence.id match to avoid cross-asset ID collisions"
  - "Path-traversal guard uses str(resolved).startswith(str(_safe_dir) + os.sep) to prevent sibling-path bypass"
metrics:
  duration: "~20 minutes"
  completed: "2026-06-17"
  tasks_completed: 3
  files_modified: 3
---

# Phase 02 Plan 01: Backend Evidence Upload Gaps Summary

One-liner: Added 25 MB cap, magic-byte validation (PDF/PNG/JPEG/DOCX/XLSX stdlib-only), full EVID-02 metadata, and an asset-scoped DELETE endpoint with owner/admin RBAC + disk cleanup across two existing backend files.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 0 | Scaffold failing test module (RED) | a3f66e2 | backend/tests/test_evidence_uploads.py (created) |
| 1 | _check_magic helper + hardened upload handler | 097678e | compliance_artifacts_endpoints.py, compliance_evidence_endpoints.py |
| 2 | DELETE endpoint with RBAC + disk cleanup | 3468888 | compliance_evidence_endpoints.py |

## What Was Built

### compliance_artifacts_endpoints.py

Added:
- `_MAGIC_SIGNATURES` dict mapping `.pdf`, `.png`, `.jpg`, `.jpeg`, `.docx`, `.xlsx` to their leading byte signatures
- `_check_magic(content: bytes, ext: str) -> bool` — returns True when content's leading bytes match, or True when no signature defined (pass-through for unknown types)

### compliance_evidence_endpoints.py

Added at module level:
- `_EVIDENCE_ALLOWED_EXTENSIONS` — narrowed frozenset: `{".pdf",".png",".jpg",".jpeg",".docx",".xlsx"}`
- `_EVIDENCE_ALLOWED_MIME_PREFIXES` — narrowed tuple of 6 prefixes (application/pdf, image/png, image/jpeg, etc.)

Updated `upload_compliance_evidence`:
- Added `request: Request`, `response: Response`, `description: str = Form("", max_length=1000)` params
- Validates extension against narrowed `_EVIDENCE_ALLOWED_EXTENSIONS` (not shared broad list)
- Validates MIME against narrowed `_EVIDENCE_ALLOWED_MIME_PREFIXES`
- Reads file once: size check (`> 25 MB -> 413`) then magic check (`-> 400`) before any disk write
- Evidence record now includes: `uploaded_by`, `description`, `tenantId`, `source:"manual"`, `systemGenerated:False`
- ID format changed to `ev-manual-{uuid.uuid4().hex}` (collision-safe, RESEARCH Pitfall 4)
- `$set` block also writes `tenantId` to top-level document (RESEARCH Pitfall 2 fix)

Added `delete_compliance_evidence`:
- Route: `DELETE /api/assets/{asset_id}/compliance/evidence/{evidence_id}`
- Aggregate pipeline lookup: `$unwind evidence`, `$match` on `assetId + evidence.id`
- Guards: systemGenerated==True -> 403, tenant mismatch -> 403, non-owner non-admin -> 403
- `$pull` sub-document from `asset_compliance.evidence[]`
- Disk cleanup: `Path(UPLOAD_DIR).resolve()` + startswith guard before `unlink(missing_ok=True)`

### backend/tests/test_evidence_uploads.py

9 tests covering EVID-01/02/04/05:
- `test_upload_allowed_types` — valid PDF succeeds
- `test_upload_size_limit` — 26 MB raises 413
- `test_upload_record_schema` — all 5 metadata fields present
- `test_magic_bytes_valid_pdf` — `_check_magic` accepts PDF bytes
- `test_magic_bytes_mismatch` — `<script` bytes with .pdf ext raises 400
- `test_delete_own_evidence` — owner delete succeeds
- `test_delete_other_user_evidence` — non-owner 403
- `test_admin_delete_any_evidence` — admin deletes cross-tenant
- `test_delete_automated_evidence_blocked` — systemGenerated 403

## Verification Results

```
PYTHONPATH=venv/lib/python3.12/site-packages python3.12 -m pytest tests/test_evidence_uploads.py -q
9 passed in 0.97s
```

Line counts (must be < 500):
- `compliance_artifacts_endpoints.py`: 212 lines
- `compliance_evidence_endpoints.py`: 296 lines

`_check_magic` definition + import confirmed:
- Defined at `compliance_artifacts_endpoints.py:68`
- Imported at `compliance_evidence_endpoints.py:11`
- Called at `compliance_evidence_endpoints.py:75`

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Adjustments (non-deviations)

**1. [Adaptation] asyncio.run() instead of pytest.mark.asyncio**
- **Found during:** Task 0 verification
- **Issue:** `pytest-asyncio` is not installed in the environment; `pytest.mark.asyncio` was unknown
- **Fix:** Rewrote async tests using `asyncio.run()` inside plain `def` test functions — consistent with the existing `test_rust_heartbeat_parity.py` pattern already in this repo
- **Impact:** No behavior difference; all 9 tests pass

**2. [Adaptation] Path-traversal guard boundary condition**
- **Found during:** Task 2 implementation
- **Issue:** `str(resolved).startswith(str(_safe_dir))` would pass for sibling paths like `/static/evidence-malicious/file`
- **Fix:** Changed to `str(resolved).startswith(str(_safe_dir) + os.sep)` to ensure the resolved path is strictly inside the directory, not just a path that shares the prefix string

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes beyond what the plan's `<threat_model>` already covers. All 7 threat register entries (T-02-01 through T-02-SC) have been mitigated as specified.

## Known Stubs

None — all required functionality is fully implemented and covered by passing tests.

## Self-Check

All 4 success criteria verified:
- [x] Upload <= 25 MB succeeds; > 25 MB returns 413 (test_upload_size_limit: PASS)
- [x] Stored record includes uploaded_by, description, tenantId, source:manual, systemGenerated:false (test_upload_record_schema: PASS)
- [x] DELETE enforces owner/admin rules, tenant isolation, systemGenerated guard, disk cleanup (4 delete tests: PASS)
- [x] Magic-byte mismatch rejected via _check_magic stdlib-only (test_magic_bytes_mismatch: PASS)
- [x] No new packages added
- [x] No new source files beyond the test module
- [x] Both backend files under 500 lines
