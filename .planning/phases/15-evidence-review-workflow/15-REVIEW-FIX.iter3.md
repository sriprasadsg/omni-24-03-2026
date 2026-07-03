---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-02T04:15:00Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 2
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-02T04:15:00Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 6 (0 Critical + 4 Warning + 2 Info; `fix_scope: all`)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### WR-01: `create_review`'s dedup check is not atomic — concurrent requests can still create duplicate pending review records

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commit:** `7bdc0d2`
**Applied fix:** Replaced the check-then-act `find_one` + `insert_one` pair in `create_review` with a single atomic `find_one_and_update(..., upsert=True, return_document=True)` keyed on `(tenantId, evidenceId, status="pending")`, using `$setOnInsert` for the new-record fields — matching the review's suggested fix exactly. Two concurrent create-review calls for the same evidence item can no longer both observe "no existing pending review" and both insert a duplicate. Updated the existing `test_create_review_record` assertion, which previously asserted `insert_one` was awaited — that call no longer exists under the new implementation, so the assertion now checks `find_one_and_update` was awaited instead. Ran the full test file after the change: 11/11 passed.

### WR-02: Reviewer action buttons render regardless of the evidence's actual review status, guaranteeing failed calls in the common case

**File modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** `0ef3c4b`
**Applied fix:** Gated the reviewer-action block (Approve / Reject / Request Changes) on `isReviewer && evidenceStatus === 'pending_review'`, matching the invariant `create_review` actually enforces server-side (`is not pending review (current status: ...)` → 404). `npx tsc --noEmit` reported no errors for this file.

### WR-03: Audit-log write failure after a successful decision surfaces as a 500 despite the mutation having already succeeded

**File modified:** `backend/evidence_review_endpoints.py`
**Commit:** `021f816`
**Applied fix:** Wrapped the `db.audit_logs.insert_one(...)` call (after a successful `update_review_decision`) in `try/except Exception: logger.exception(...)`, exactly as suggested — a transient audit-log write failure can no longer surface as a 500 for a review decision that has already been durably committed. Full test suite re-run after the change: 11/11 passed.

### WR-04: `onStatusChange` re-asserts the current (unchanged) asset compliance status purely as a side-channel refresh trigger

**Files modified:** `components/AssetComplianceList.tsx`, `components/FrameworkDetail.tsx`
**Commit:** `bdc0e99`
**Applied fix:** Added a new optional `onEvidenceReviewed?: (assetId: string) => void` prop to `AssetComplianceList`, and rewired `EvidenceReviewPanel`'s `onStatusChange` callback to call it instead of the mutating `onUpdateStatus(asset.id, statusRecord.status)`. Wired `FrameworkDetail.tsx` (referenced in the finding's File line as the call site, though outside the original review's file scope) to pass `onEvidenceReviewed={(assetId) => refreshAssetCompliance(assetId)}`, reusing the existing non-mutating refresh helper already defined there. Evidence-review decisions no longer trigger a spurious `updateAssetComplianceStatus` backend write. `npx tsc --noEmit` reported no errors for either file.

### IN-01: Inconsistent error-detail handling in `handleReviewDecision`

**File modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** `299c92d`
**Applied fix:** Changed the create-review failure branch from a hardcoded `showToast('Failed to create review', 'error')` to read `d.detail` from the JSON error body first (`const d = await reviewRes.json().catch(() => ({})); showToast(d.detail || 'Failed to create review', 'error');`), matching the pattern already used by the PATCH failure branch and `handleSubmitForReview` in the same component. `npx tsc --noEmit` reported no errors for this file.

### IN-02: No regression tests for the dedup short-circuit or the "already decided" re-PATCH guard added in the prior fix

**File modified:** `backend/tests/test_evidence_review.py`
**Commit:** `8309825`
**Applied fix:** Added two tests, adapted to the WR-01 atomic-upsert implementation applied earlier in this run: `test_create_review_dedup_returns_existing_pending_via_atomic_upsert` mocks `find_one_and_update` to return a pre-existing pending review and asserts the response returns that record's id unchanged with `insert_one` never awaited; `test_repatch_already_decided_review_returns_404` mocks `find_one_and_update` to return `None` (simulating the `status: "pending"` filter failing to match an already-decided review) and asserts a 404 with `audit_logs.insert_one` never awaited. Full suite re-run after the change: 13/13 passed.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-02T04:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
