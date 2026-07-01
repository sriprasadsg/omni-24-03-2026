---
phase: 08-bulk-evidence-upload
fixed_at: 2026-06-22T00:00:00Z
review_path: .planning/phases/08-bulk-evidence-upload/08-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-06-22
**Source review:** .planning/phases/08-bulk-evidence-upload/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (CR-01, CR-02, CR-03, WR-01, WR-02, WR-03, WR-04, WR-05)
- Fixed: 8
- Skipped: 0

## Fixed Issues

### CR-01: No authorization check on bulk upload endpoint

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** 24c09e5
**Applied fix:** Added `_WRITE_ROLES` frozenset constant at module level. Added role check after extracting `tenant_id`/`uploader` — raises HTTP 403 if `current_user.role` is not in the allowed write roles.

---

### CR-02: Zip-bomb guard uses spoofable metadata

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** 98577e7
**Applied fix:** Replaced `zf.read(raw_name)` with bounded chunk-reading using `zf.open()`. Reads in 64 KB chunks, tracks cumulative byte count, and appends a per-file error and breaks early if decompressed size exceeds `MAX_ENTRY_BYTES` (25 MB). Moved `MAX_ENTRY_BYTES` to module-level constant. Removed the old post-read `len(entry_bytes) > 25 MB` check (now handled in the read loop).

---

### CR-03: Commit loop has no rollback on DB failure

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** 4d3c7b1
**Applied fix:** Added `written_paths: list[str] = []` before the commit loop. Appends each `file_path` after a successful `_write_binary` call. Wrapped the commit loop in a `try/except Exception` that iterates `written_paths` and calls `asyncio.to_thread(os.unlink, p)` (swallowing `OSError`) on failure, then re-raises as HTTP 500.

---

### WR-01: canManageEvidence flag not used to gate bulk upload button

**Files modified:** `components/FrameworkDetail.tsx`
**Commit:** a3c31cf
**Applied fix:** Wrapped the "Bulk Upload Evidence" button in `{canManageEvidence && (...)}`. Left the "Add Control" and "Import Controls" buttons unchanged (out of scope for Phase 8 per instructions).

---

### WR-02: Manifest picker div not keyboard-accessible

**Files modified:** `components/BulkEvidenceUploadModal.tsx`
**Commit:** 2088481
**Applied fix:** Added `role="button"`, `tabIndex={0}`, `aria-label="Select manifest JSON file"`, and `onKeyDown` handler (activates click on Enter/Space with `e.preventDefault()`) to the manifest picker `<div>`, matching the pattern already used by the zip picker above it.

---

### WR-03: Uncompressed size error returns HTTP 400 instead of 413

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** b20737b
**Applied fix:** Changed `status_code=400` to `status_code=413` on the uncompressed content size guard, so both the compressed and uncompressed size limits return 413. The frontend `err.status === 413` check now catches both cases.

---

### WR-04: Chain-of-custody writes not asserted in tests

**Files modified:** `backend/tests/test_bulk_evidence_upload.py`
**Commit:** 0ab6506
**Applied fix:** Added three assertions at the end of `test_bulk_appears_in_control_evidence`: checks that `db_mock._db.evidence_audit_log.insert_one` was awaited exactly 2 times (one per committed file), that all CoC entries have `action_type == "create"`, and that all have `tenantId == "tenant-b"`.

---

### WR-05: Module docstring incorrectly claims asyncio.run() is used

**Files modified:** `backend/tests/test_bulk_evidence_upload.py`
**Commit:** 7097687
**Applied fix:** Replaced the false claim "Uses asyncio.run()" with the accurate description "All tests are synchronous (TestClient). asyncio.to_thread is patched where needed."

---

## Skipped Issues

None — all findings were fixed.

---

**Verification:** All 12 tests in `tests/test_bulk_evidence_upload.py` pass after all fixes (1.28s).

---

_Fixed: 2026-06-22_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
