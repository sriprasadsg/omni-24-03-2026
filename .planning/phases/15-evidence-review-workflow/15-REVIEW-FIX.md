---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-03T08:22:33Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-03T08:22:33Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: Approve/Reject buttons send an invalid `decision` value — every decision except "Request Changes" fails with 422

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** e47e63d
**Applied fix:** Added a `DECISION_MAP` constant mapping the internal button-click state (`'approve' | 'reject' | 'changes'`) to the exact strings the backend's `UpdateDecisionRequest` pattern validates (`approved`, `rejected`, `changes_requested`), and changed the Confirm button's `onClick` to call `handleReviewDecision(DECISION_MAP[action])` instead of passing the unconverted `action` value through for approve/reject. This also fixes the downstream comment-required guard (`decision === 'rejected' || decision === 'changes_requested'`), which now receives the correctly mapped value and fires as intended.

### WR-01: File-picker `accept` attribute silently defeats the text-evidence ingestion gate added in the same change set

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** 05d48da
**Applied fix:** Extended the `<input type="file">` `accept` attribute from `.pdf,.png,.jpg,.jpeg,.docx,.xlsx` to also include `.txt,.md,.json,.csv`, so the file picker's default filter now agrees with `INGESTIBLE_TEXT_TYPES` (`text/plain`, `text/markdown`, `application/json`, `text/csv`) that `isIngestibleText` checks against.

### WR-02: Reviews-thread toggle shows a misleading "(0)" count before the panel is first opened

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** ebfac27
**Applied fix:** Added a `hasFetchedOnce` state flag, set `true` in `fetchReviews()`'s `finally` block (covering both success and error paths), and changed the toggle label to render `'Show reviews'` instead of `Reviews (0)` until the first fetch has actually completed.

### WR-03: GET review endpoints are unprotected by rate limiting while every mutating endpoint in the same router is capped

**Files modified:** `backend/evidence_review_endpoints.py`
**Commit:** 6c972b0
**Applied fix:** Added `@limiter.limit("60/minute")` plus the required `request: Request, response: Response` parameters to `list_evidence_reviews` and `list_pending_review_evidence`, matching the `request: Request, response: Response` signature convention already used by every other rate-limited endpoint in this codebase (e.g. `bundle_endpoints.py`), rather than only `request: Request` as shown in the review's illustrative snippet.

### WR-04: The one regression test for the CR-01 `$elemMatch` propagation fix silently skips when no MongoDB is reachable

**Files modified:** `backend/tests/test_evidence_review.py`
**Commit:** fb2e027
**Applied fix:** Implemented both remediation options from the review: (1) gated the live-Mongo test's skip behind a `CI` env var check — in CI, an unreachable MongoDB now fails the test suite loudly via `pytest.fail(...)` instead of silently reporting "skipped"; locally, the skip is preserved for developer convenience. (2) Added a new always-running, mock-based companion test (`test_update_review_decision_propagation_filter_uses_elem_match`) that inspects the actual filter dict passed to `db.asset_compliance.update_one` via a `MagicMock`'s `await_args`, asserting it contains `evidence.$elemMatch` with both `id` and `status` tied together — giving first-class, non-optional coverage of the same invariant with no live-database dependency. Verified: full suite (15 tests) passes with 0 skips in this environment.

### IN-01: `ev: any` loosens type safety for the evidence array passed into `EvidenceReviewPanel`

**Files modified:** `components/AssetComplianceList.tsx`
**Commit:** 9573820
**Applied fix:** Added a local `RenderedEvidence` interface extending the canonical `AssetComplianceEvidence` (imported from `../types`) with the ad-hoc, automated/AI-auditor-only fields the rendering path reads (`systemGenerated`, `source`, `evidence_id`, `evidence_content`, `content`, `details`, `check_name`, `stale`, `stale_days`, `agent_type`), and typed the `.map()` callback parameter as `RenderedEvidence` instead of `any`.

### IN-02: `create_review`'s two distinct failure modes are both mapped to HTTP 404

**Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
**Commit:** ad5d4fa
**Applied fix:** Added a new `EvidenceNotFoundError(ValueError)` subclass in `evidence_review_service.py`, raised specifically when the evidence item doesn't exist for the tenant at all (the "wrong status" case still raises a plain `ValueError`). Updated the `create_evidence_review` endpoint to catch `EvidenceNotFoundError` first (→ 404) and the remaining `ValueError` case second (→ 409 Conflict, consistent with how `update_review_decision`'s equivalent failure already maps to 422). Verified no existing test asserted 404 for the "wrong status" create-review path; full suite (15 tests) still passes.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-03T08:22:33Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
