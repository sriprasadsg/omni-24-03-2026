---
phase: 28-governance-document-management
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backend/governance_document_service.py
  - backend/governance_document_endpoints.py
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-07-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 28 builds versioned governance documents with a draft → pending_approval → approved → published state machine, e-signature capture, and signed-PDF export. Tenant scoping is applied on every service call, sign/export derive identity server-side, and PDF content is `html.escape`d — all good. However, the approval gate has a Critical bypass: `add_version` resets a document to draft while retaining the prior `approval_request_id`, so a newly-added (unapproved) version can be published and signed on the strength of the *previous* version's approval.

## Critical Issues

### CR-01: Stale approval_request_id lets an unapproved new version be published and signed

**File:** `backend/governance_document_service.py:52-81` (add_version), `130-158` (publish_document), `161-201` (sign_document)
**Issue:** `add_version` appends a new version, increments `current_version`, and sets `status: "draft"` — but does **not** clear `approval_request_id`. `publish_document` and `sign_document` gate solely on `service.get_request(approval_request_id).status == "approved"`, then act on `current_version`. Sequence: (1) create doc v1, submit, get it approved → `approval_request_id` set, approval status `approved`; (2) `add_version` with malicious/unreviewed content → v2, status draft, **approval_request_id unchanged**; (3) call publish → the v1 approval still reads `approved`, so v2 is published; call sign → v2 is signed under the old approval. This defeats the entire approval workflow (threat the phase set out to enforce) and produces a legally-signed PDF of never-approved content.
**Fix:** In `add_version`, reset the approval linkage: add `"approval_request_id": None` to the `$set` (and to the in-memory `doc`). Then `publish_document`/`sign_document`'s existing `if not approval_request_id: raise` guard correctly blocks a re-approval-less publish/sign. Optionally also assert the approval's `details.document_version` matches `current_version`.

## Warnings

### WR-01: create_document leaks internal exception text to the client

**File:** `backend/governance_document_endpoints.py:36-38`
**Issue:** `raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")` returns the raw exception message (DB errors, stack-adjacent detail) to the caller. Every other handler in the file returns a generic 500; this one leaks internals.
**Fix:** Log `exc_info=True` (already done) and return a generic `detail="Internal server error"` without `str(e)`.

### WR-02: publish/sign approval check dereferences approval fields inconsistently

**File:** `backend/governance_document_service.py:148-149, 183-184`
**Issue:** The guard is `if not approval or approval.get("status") != "approved"`, which is correct, but the error message calls `approval.get('status')` inside an expression already guarded by `approval is None` via a ternary — readable but fragile. More importantly, there is no re-verification that the approval actually corresponds to the *current* version (see CR-01), so even a correctly-approved request authorizes any later version.
**Fix:** Bind version to approval as described in CR-01; keep the null-safe ternary.

## Info

### IN-01: `_sub` labelled as email but returns username

**File:** `backend/governance_document_endpoints.py:19-21`, used as `signer_email` at `146`
**Issue:** `_sub` returns `getattr(current_user, "username", "unknown")` but its docstring says "email" and its value is persisted into `signature_record.signer_email` and the signed PDF. If username != email, the signed evidence records the wrong identifier.
**Fix:** Derive email explicitly (`getattr(current_user, "email", None) or username`) or rename the field to `signer_identity`.

### IN-02: add_version has no optimistic-concurrency guard

**File:** `backend/governance_document_service.py:60-80`
**Issue:** Read-modify-write of the `versions` array without a version predicate; two concurrent `add_version` calls can lose one version (last-writer-wins on the whole array).
**Fix:** Use `$push` on `versions` with a `current_version` predicate in the filter, or `$inc` current_version atomically. Low likelihood; noted for correctness.

---

_Reviewed: 2026-07-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
