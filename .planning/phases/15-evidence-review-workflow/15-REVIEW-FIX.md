---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-01T21:44:27Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-01T21:44:27Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (1 Critical + 6 Warning; `fix_scope: critical_warning` — IN-01 excluded from scope)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: Evidence-ID mismatch check runs after the mutating call — state changes without a matching audit log entry

**Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
**Commit:** `eec1abf`
**Applied fix:** `update_review_decision` now accepts `evidence_id` as a parameter and includes it directly in the `find_one_and_update` filter (`{"id": review_id, "evidenceId": evidence_id, "tenantId": tenant_id}`), so a URL/review mismatch is indistinguishable from "not found" and never mutates the review record or the evidence's status. The endpoint now passes `evidence_id` into the call and no longer performs the post-hoc check that previously ran after the mutation; the audit-log insert (T-10) is now only ever skipped when nothing was actually written.

### WR-01: Evidence-status propagation ignores whether the update actually matched anything

**Files modified:** `backend/evidence_review_service.py`
**Commit:** `7f060a1`
**Applied fix:** The `db.asset_compliance.update_one(...)` call in `update_review_decision` now captures its result and logs a warning (`logger.warning(...)`) including `review_id`, `decision`, `evidence_id`, and `tenant_id` when `modified_count == 0`, making the discrepancy observable instead of silently swallowed.

### WR-02: No workflow-state guard on `create_review` / `update_review_decision`

**Files modified:** `backend/evidence_review_service.py`
**Commit:** `7cf96a4`
**Applied fix:** `create_review` now locates the matching evidence item in the fetched `asset_compliance` document and raises `ValueError` unless its status is `pending_review`. `update_review_decision`'s `find_one_and_update` filter now additionally requires `status: "pending"` on the review record, so an already-decided review can no longer be re-decided by a repeated PATCH.
**Note:** This is a workflow/state-machine logic change, not just a syntax fix. All 10 existing/updated tests pass, but the underlying business-logic decision (e.g. whether "comment threads on non-pending-review evidence" should ever be a valid intentional use case, as the review's Fix section flagged as "undocumented either way") should be confirmed by a human before this is considered fully verified. Status: **fixed: requires human verification**.

### WR-03: Frontend "Submit for Review" gating doesn't match backend's submittable states

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** `d6e362d`
**Applied fix:** `canSubmitForReview` now also includes `evidenceStatus === 'rejected'`, matching the backend's `_submittable_statuses()` (`[None, "needs_revision", "rejected"]`), so rejected evidence is no longer stuck with no UI path to resubmit.

### WR-04: `EvidenceReviewPanel` is rendered with a possibly-`undefined` `evidenceId`

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** `0b52b10`
**Applied fix:** Wrapped `<EvidenceReviewPanel .../>` in `{evId && (...)}`, matching the existing guard already used for the adjacent delete button, so the panel no longer fires requests against literal `/api/evidence/undefined/...` URLs when `evId` is undefined.

### WR-05: `onStatusChange` callback overwrites compliance status with a stale value, using an inconsistent default

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** `63a53e9`
**Applied fix:** The `onStatusChange` callback passed to `EvidenceReviewPanel` now only calls `onUpdateStatus` (a real, side-effecting write) when `statusRecord?.status` is present, and uses that actual value directly rather than falling back to a guessed default. This removes both problems flagged in the review: the inconsistent `'Pending_Evidence'` default (vs. `'Non-Compliant'` used elsewhere in the file) and the risk of reverting a concurrent status change with a stale render-time value.

### WR-06: `test_tenant_isolation` does not test tenant isolation and cannot fail

**Files modified:** `backend/tests/test_evidence_review.py`
**Commit:** `456773c`
**Applied fix:** Replaced the single no-op `test_tenant_isolation` (which asserted `status_code in (200, 403, 404)` against a single-tenant fixture) with three focused tests using real two-tenant fixtures:
- `test_tenant_isolation_get_excludes_cross_tenant_reviews` — seeds a tenant-b-only review record for the same `evidenceId`, asserts a tenant-a GET returns `count == 0` / `reviews == []` (strict, not permissive).
- `test_tenant_isolation_patch_returns_404_for_cross_tenant_review` — seeds a review that only resolves for `tenantId == "tenant-b"`, asserts a tenant-a admin's PATCH against that review id returns exactly `404`.
- `test_non_reviewer_role_forbidden_from_decision` — preserves the original 403-on-non-admin-PATCH assertion as its own focused test.

All 10 tests (8 original + 2 net-new from the WR-06 split) pass.

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-07-01T21:44:27Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
