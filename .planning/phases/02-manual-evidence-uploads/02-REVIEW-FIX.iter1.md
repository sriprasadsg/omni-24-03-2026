---
phase: 02-manual-evidence-uploads
fixed_at: 2026-07-03T15:20:00Z
review_path: .planning/phases/02-manual-evidence-uploads/02-REVIEW.md
iteration: 1
findings_in_scope: 15
fixed: 15
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-03T15:20:00Z
**Source review:** .planning/phases/02-manual-evidence-uploads/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 15 (6 critical, 7 warning, 2 info — fix_scope was "all")
- Fixed: 15
- Skipped: 0

All 15 findings applied cleanly against the current state of the source files.
Backend changes were verified with `python -m ast.parse` (syntax) and the full
`backend/tests/test_evidence_uploads.py` suite (9/9 passing before and after).
Frontend changes were verified by re-reading the modified sections; `tsc` was
not available in this environment, so a manual type-compatibility check was
done for the one change (WR-07) that touched a literal-union type.

Note on commit granularity: CR-01, CR-02, CR-03, CR-04, CR-05, CR-06 (artifact
endpoint), WR-02, WR-03 (artifact endpoint), and IN-01 all modify the same
~100-line `upload_manual_artifact` function body in
`compliance_artifacts_endpoints.py`. Wrapping the function in a try/except
(WR-03) reindents every line inside it, which merges all of those fixes into
a single unavoidable git hunk — they are recorded as one commit
(`995925c`) rather than split further, since a forced split would have meant
hand-editing a diff rather than applying the tool's actual edits.

## Fixed Issues

### CR-01: Unrestricted `.html`/`.xml` upload + same-origin static serving enables stored XSS

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `995925c`
**Applied fix:** Removed `.md`, `.json`, `.xml`, `.html` from `_ALLOWED_UPLOAD_EXTENSIONS` (kept as a commented-out note explaining why), closing the stored-XSS path through the `static/evidence` mount.

### CR-02: MIME-type check silently no-ops when `Content-Type` is blank

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `995925c`
**Applied fix:** Changed `if content_type and not any(...)` to `if not content_type or not any(...)`, matching the fail-closed pattern already used in `compliance_evidence_endpoints.py`.

### CR-03: Magic-byte validation (`_check_magic`) never called in the artifact upload endpoint

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `995925c`
**Applied fix:** Added a `_check_magic(file_content, file_ext)` call right after the extension/MIME checks, before the file is written to disk.

### CR-04: Non-unique, low-resolution filename generation corrupts evidence integrity

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `995925c`
**Applied fix:** Replaced the second-granularity `timestamp` in `safe_filename` with `uuid.uuid4().hex`, eliminating same-second collisions and the resulting silent file-overwrite/sha256-mismatch bug.

### CR-05: Non-unique MongoDB filter can silently attach evidence to an unrelated asset

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `995925c`
**Applied fix:** Split the per-control update: asset-scoped controls keep the unambiguous `{"assetId": asset_id, "controlId": control_id}` filter against `asset_compliance`; org-wide (no-`asset_id`) controls now route to `db.control_evidence.insert_one(...)` instead of upserting into `asset_compliance` with an ambiguous filter.

### CR-06: No server-side authorization check on evidence/artifact upload endpoints

**Files modified:** `backend/compliance_artifacts_endpoints.py`, `backend/compliance_evidence_endpoints.py`
**Commits:** `995925c` (`upload_manual_artifact`), `34aa75c` (`upload_compliance_evidence`), `ec627c3` (`upload_control_direct_evidence`)
**Applied fix:** Replaced `Depends(get_current_user)` with `Depends(require_permission("manage:compliance_evidence"))` on all three upload endpoints, using the existing `rbac_utils.require_permission` dependency and matching the permission string the frontend already gates its upload buttons behind. Verified this doesn't break `test_evidence_uploads.py`, since those tests call the handler functions directly with an explicit `current_user=` keyword argument, bypassing FastAPI's dependency injection entirely.

## Warnings — Fixed

### WR-01: Backend validation `detail` messages discarded by frontend evidence API wrappers

**Files modified:** `services/apiService.ts`
**Commit:** `555bef7`
**Applied fix:** `uploadComplianceEvidence`, `deleteComplianceEvidence`, `uploadControlEvidence`, `getControlEvidence`, and `deleteControlEvidence` now parse the response body and throw `body.detail || <generic fallback>`, matching the pattern already used by `uploadBulkEvidence`.

### WR-02: Super-admin role sets drifted between the two compliance-upload modules

**Files modified:** `backend/compliance_artifacts_endpoints.py`, `backend/compliance_evidence_endpoints.py`
**Commits:** `995925c` (defined `_SUPER_ROLES` in the artifacts module, updated `list_manual_artifacts`), `b405cbd` (evidence module now imports the shared set instead of keeping its own copy)
**Applied fix:** `_SUPER_ROLES` is now defined once in `compliance_artifacts_endpoints.py` and imported into `compliance_evidence_endpoints.py`, eliminating the drift between the two inline role checks.

### WR-03: Inconsistent error handling/logging across sibling endpoints

**Files modified:** `backend/compliance_artifacts_endpoints.py`, `backend/compliance_evidence_endpoints.py`
**Commits:** `995925c` (`upload_manual_artifact`), `8de94e0` (`delete_control_direct_evidence`)
**Applied fix:** Wrapped both previously-unwrapped functions in `try/except HTTPException: raise / except Exception as e: logger.error(...); raise HTTPException(500, ...)`, matching their siblings in the same files.

### WR-04: Frontend evidence file picker advertises formats the backend always rejects

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** `a3cee38`
**Applied fix:** Narrowed the `accept` attribute on the hidden evidence file input from `.pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.md,.json,.csv` to `.pdf,.png,.jpg,.jpeg,.docx,.xlsx`, matching `_EVIDENCE_ALLOWED_EXTENSIONS`.

### WR-05: Dead/misleading MIME-prefix entries with no corresponding allowed extension

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** `b405cbd`
**Applied fix:** Removed the unreachable `application/msword` and `application/vnd.ms-excel` entries from `_EVIDENCE_ALLOWED_MIME_PREFIXES`, since `.doc`/`.xls` are not in `_EVIDENCE_ALLOWED_EXTENSIONS`.

### WR-06: `onUploadEvidence` invoked without `await`, relying on caller's try/catch

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** `5ab8ab4`
**Applied fix:** Awaited `onUploadEvidence` inside its own `try/catch` in `handleFileChange`, so this component no longer depends on an implicit contract with its caller to avoid an unhandled promise rejection.

### WR-07: `Pending_Review` status not recognized by the frontend status badge

**Files modified:** `components/AssetComplianceList.tsx`, `types.ts`
**Commit:** `a4664da`
**Applied fix:** Extended the badge condition to treat `Pending_Review` the same as `Pending_Evidence` (yellow, not red). Also widened `AssetCompliance['status']` in `types.ts` to include `'Pending_Review'` (the backend already sets this value; the type previously didn't declare it, which would have made the new literal comparison a type error).

## Info — Fixed

### IN-01: Local `import uuid as _uuid` inside a function body

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `995925c`
**Applied fix:** Promoted `import uuid` to module scope alongside the other imports, removed the local `import uuid as _uuid`, and updated both `uuid.uuid4().hex` call sites (record `id` and, per CR-04, the filename) to use it.

### IN-02: "Upload" button for control-level evidence not gated by the same permission as "Bulk Upload Evidence"

**Files modified:** `components/FrameworkDetail.tsx`
**Commit:** `d56ec81`
**Applied fix:** Gated the per-control "Upload" button behind `canManageEvidence`, matching the "Bulk Upload Evidence" button right next to it — now that CR-06 enforces this permission server-side, the UI is consistent with the enforced access boundary.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-03T15:20:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
