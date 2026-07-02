---
phase: "02"
fixed_at: 2026-07-02T18:20:02Z
review_path: .planning/phases/02-manual-evidence-uploads/02-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 3
skipped: 7
status: partial
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-02T18:20:02Z
**Source review:** .planning/phases/02-manual-evidence-uploads/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (5 critical, 5 warning — the 3 Info findings were out of scope for this pass)
- Fixed: 3
- Skipped: 7 (all 7 were already resolved by later, unrelated work — root cause verified absent in current code, no patch applied)

This REVIEW.md is from an early phase (reviewed 2026-06-17). Before applying any fix, each finding was re-verified against the current state of the source files. 7 of the 10 in-scope findings had already been fixed by subsequent commits unrelated to this review — their fix sections were not force-applied since doing so would have been a no-op or would have reintroduced already-superseded code. Only the 3 findings whose root cause was still present were fixed in this pass.

## Fixed Issues

### WR-01: Inconsistent Super-Admin Role Sets Across Endpoints

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** c608c42
**Applied fix:** Confirmed the finding still applied — `_SUPER_ROLES` (module-level) was missing `"superadmin"`, `get_all_compliance_evidence` used an inline set missing `"admin"`, and `download_compliance_evidence` used an inline list missing `"superadmin"`. Replaced `_SUPER_ROLES` with a single `frozenset[str]` containing `{"Super Admin", "super_admin", "superadmin", "admin", "platform-admin"}` and replaced both inline role-set literals with references to `_SUPER_ROLES`, matching the review's suggested fix exactly.

### WR-02: Path Traversal Guard in Download Endpoint Missing `os.sep` Suffix

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** d69afd4
**Applied fix:** Confirmed the finding still applied — the download endpoint's guard at the cited location still used `startswith(str(_safe_dir))` without the separator (unlike the DELETE endpoint's already-correct guard). Changed to `startswith(str(_safe_dir) + os.sep)`, aligning it with the DELETE endpoint's stronger guard.

### WR-04: `file.text()` Called on Binary Files in Frontend Ingestion Flow

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** c32bd9e
**Applied fix:** Confirmed the finding still applied — `handleFileChange` still called `file.text()` unconditionally on every uploaded file before passing it to `onIngestEvidence`, regardless of MIME type. Added an `INGESTIBLE_TEXT_TYPES` allowlist (`text/plain`, `text/markdown`, `application/json`, `text/csv`) and gated the `file.text()` / `onIngestEvidence` call behind a `file.type.startsWith(...)` check, matching the review's suggested guard. Binary evidence (PDF, PNG, JPEG, DOCX, XLSX — all currently accepted by the file input per WR-05) is now uploaded normally but silently skipped from text ingestion instead of being garbled into replacement characters.
Note: since the `<input accept>` list (see WR-05 below, already fixed) currently only allows binary formats, this guard means text-ingestion is a no-op today; it will resume functioning correctly if text formats are ever re-added to the accepted extensions.

## Skipped Issues — Already Fixed by Later Work

All 7 items below were re-verified against current source and found to already implement the review's suggested fix (or an equivalent). No patch was applied to avoid redundant/stale changes; each is listed with the current code state that resolves the original finding.

### CR-01: Tenant Isolation Bypass in DELETE When JWT Has No `tenant_id`

**File:** `backend/compliance_evidence_endpoints.py` (delete_compliance_evidence)
**Reason:** Already fixed. Current code (lines ~281-285) explicitly rejects non-super callers with no `caller_tenant` before the tenant-match check:
```python
if not is_super:
    if not caller_tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if doc_tenant != caller_tenant:
        raise HTTPException(status_code=403, detail="Evidence not found in your tenant")
```
This matches the review's suggested fix exactly.

### CR-02: HTTP Response-Header Injection via Evidence `name` in Content-Disposition

**File:** `backend/compliance_evidence_endpoints.py` (download_compliance_evidence)
**Reason:** Already fixed. The system-generated markdown path now sanitizes the filename with `re.sub(r'[^A-Za-z0-9._-]', '_', evidence.get('name', 'evidence'))` before embedding it in the `Content-Disposition` header. The `FileResponse` path uses `os.path.basename(file_path)`, which is UUID-based and never attacker-controlled.

### CR-03: `importComplianceControls` Still Sets `Content-Type: multipart/form-data` Explicitly

**File:** `services/apiService.ts`
**Reason:** Already fixed. `importComplianceControls` no longer passes a `headers` override — it only sets `method` and `body`, letting the browser set `Content-Type` with the correct `boundary` automatically, exactly as the review's suggested fix specifies.

### CR-04: `tenantId` Not Stored in Artifact Records

**File:** `backend/compliance_artifacts_endpoints.py`
**Reason:** Already fixed. `upload_manual_artifact`'s `record` dict includes `"tenantId": getattr(current_user, "tenant_id", None)`, so `list_manual_artifacts`'s tenant filter now matches stored documents correctly.

### CR-05: Artifact Record ID Collision on Concurrent Uploads

**File:** `backend/compliance_artifacts_endpoints.py`
**Reason:** Already fixed. The artifact `id` field is now generated via `f"artifact-{uuid.uuid4().hex}"` instead of a second-granularity timestamp, eliminating the collision that caused `DuplicateKeyError` on concurrent uploads.
(Note, out of scope for this finding: the on-disk `safe_filename` used for the stored file — `f"artifact_{category}_{timestamp}{file_ext}"` — still uses second-granularity timestamp and could theoretically collide/overwrite on truly simultaneous uploads. This is a distinct filename-collision concern, not the record-ID/`_id` collision CR-05 describes, and was not raised by the review, so it was left untouched.)

### WR-03: `uploadComplianceEvidence` Sends `controlId` But Backend Expects `control_id`

**File:** `services/apiService.ts`
**Reason:** Already fixed. `uploadComplianceEvidence` now calls `formData.append('control_id', controlId)` (snake_case), matching the backend's `control_id: str = Form(...)` parameter.

### WR-05: Frontend `<input accept>` Mismatches Backend Allowed Extensions

**File:** `components/AssetComplianceList.tsx`
**Reason:** Already fixed. The file input's `accept` attribute is now `.pdf,.png,.jpg,.jpeg,.docx,.xlsx`, matching `_EVIDENCE_ALLOWED_EXTENSIONS` in the backend exactly.

---

_Fixed: 2026-07-02T18:20:02Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
