---
phase: 02-manual-evidence-uploads
fixed_at: 2026-07-03T16:30:00Z
review_path: .planning/phases/02-manual-evidence-uploads/02-REVIEW.md
iteration: 2
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-03T16:30:00Z
**Source review:** .planning/phases/02-manual-evidence-uploads/02-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 11 (4 critical, 4 warning, 3 info)
- Fixed: 11
- Skipped: 0

This is the second review/fix round for this phase. The first round (see
`02-REVIEW-FIX.iter1.md`) fixed 15 findings from an earlier review; this
round's review (`02-REVIEW.md`) was a from-scratch re-review that found new,
unfixed issues, the most serious being an extension-allowlist bypass and
evidence files being served through an unauthenticated public static mount.

Backend changes were verified with `python -m ast.parse` (syntax) and the
full `backend/tests/` suite: all evidence/artifact/compliance tests pass
(117 passed), plus 2 new tests added for previously-uncovered fail-closed
paths in `upload_manual_artifact`. The 39 failures elsewhere in the suite
(auth MFA, notification service, IaC scanner, privacy service, ML feature
extraction) are pre-existing and reproduce identically on `main` before
this round's changes — unrelated to this phase. Frontend changes were
verified by re-reading the modified sections; `tsc` is not available in
this environment (same limitation noted in iteration 1).

## Fixed Issues

### CR-01: Extension allowlist bypass via omitted file extension in manual artifact upload

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `210cca1`
**Applied fix:** Changed `if file_ext and file_ext not in _ALLOWED_UPLOAD_EXTENSIONS` to `if not file_ext or file_ext not in _ALLOWED_UPLOAD_EXTENSIONS`, matching the fail-closed pattern already used in `compliance_evidence_endpoints.py`'s upload handlers.

### CR-02: Uploaded evidence/artifact files served publicly with no authentication

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `ae54ec9`
**Applied fix:** Moved `UPLOAD_DIR` from `static/evidence` to `private_uploads/evidence`, outside the publicly-mounted `/static` tree in `app.py`. Reads now depend exclusively on the RBAC/tenant-scoped download endpoints, which resolve files by basename against `UPLOAD_DIR` rather than trusting any URL prefix returned to clients.

### CR-03: `get_control_evidence` returns cross-tenant evidence when a non-super caller has no `tenant_id`

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** `b957fd9`
**Applied fix:** Non-super callers with no `tenant_id` now get a 403 ("Tenant context required") instead of silently querying across all tenants, matching the fail-closed posture of every other endpoint in the module.

### CR-04: Asset-tenant ownership check silently skipped when caller has no `tenant_id`

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `bdbd3f2`
**Applied fix:** The ownership check now fails closed for non-super callers with no `tenant_id` (403 "Tenant context required") instead of skipping the check outright when `_caller_tenant` is falsy.

## Warnings — Fixed

### WR-01: Evidence-upload endpoints lack the dedicated rate limit applied to the sibling artifact-upload endpoint

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** `2a175da`
**Applied fix:** Added `@limiter.limit("30/hour")` to `upload_compliance_evidence` and `upload_control_direct_evidence`, bringing both in line with the artifact-upload endpoint's throttling posture instead of relying on the much more permissive app-wide default.

### WR-02: Distinguishable 403 vs 404 responses allow cross-tenant existence probing in `delete_compliance_evidence`

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** `48cd7fc`
**Applied fix:** The initial aggregation `$match` now includes `tenantId` for non-super callers, so a cross-tenant evidence ID collapses into the same 404 as "not found" instead of leaking existence via a 403.

### WR-03: `_MAGIC_SIGNATURES` pass-through combines with CR-01 to fully defeat content validation

**Files modified:** `backend/compliance_artifacts_endpoints.py`
**Commit:** `abedd41`
**Applied fix:** `_check_magic` now rejects an empty `ext` outright (defense-in-depth; unreachable in practice now that CR-01 guarantees a non-empty, allowlisted extension) and adds a lightweight sanity check for genuinely-unsigned text extensions (`.txt`, `.csv`): reject NUL bytes in the first 4KB and reject content starting with `<script`, `<html`, `<!doctype`, or `<?php`.

### WR-04: Stale "RED phase" framing left in test module docstring understates actual coverage gaps

**Files modified:** `backend/tests/test_evidence_uploads.py`
**Commit:** `dd4766a`
**Applied fix:** Updated the module docstring to describe current (green) coverage instead of a pre-fix TDD-RED state. Added `test_manual_artifact_extension_omitted_rejected` (CR-01) and `test_manual_artifact_asset_ownership_requires_tenant` (CR-04), which previously had zero coverage on `upload_manual_artifact`. Also fixed `_make_request()`: WR-01's new `@limiter.limit` decorator on `upload_compliance_evidence` needs slowapi to inject rate-limit headers post-call, which requires `request.state` to behave like a real object (an auto-vivifying `MagicMock` attribute made `getattr(request.state, "_rate_limiting_complete", False)` always truthy, silently skipping the rate-limit check and leaving `state.view_rate_limit` unset) and `request.client.host` to be a concrete string. Without this, the two pre-existing tests that reach a 200 response (`test_upload_allowed_types`, `test_upload_record_schema`) would fail on every future run.

## Info — Fixed

### IN-01: Leftover debug `console.log` calls in evidence-ingestion path

**Files modified:** `components/FrameworkDetail.tsx`
**Commit:** `c54ffa6`
**Applied fix:** Removed the two debug `console.log` calls in `onIngestEvidence`.

### IN-02: Commented-out `alert(...)` call left in place

**Files modified:** `components/FrameworkDetail.tsx`
**Commit:** `c54ffa6`
**Applied fix:** Removed the dead commented-out `alert(...)` line.

### IN-03: `RenderedEvidence.model_used` access has no runtime guard

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** `ab95d13`
**Applied fix:** Changed `statusRecord.ai_evaluation.model_used.split('/').pop()` to `(statusRecord.ai_evaluation.model_used || '').split('/').pop() || 'unknown'`, tolerating a missing value at this backend-JSON boundary instead of throwing.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-03T16:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
