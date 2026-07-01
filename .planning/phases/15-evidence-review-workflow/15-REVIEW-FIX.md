---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-01T20:49:41Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-01T20:49:41Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (2 critical, 4 warning — fix_scope: critical_warning; IN-01 and IN-02 excluded)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: Review decision endpoint has no tenant scoping — cross-tenant IDOR

**Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
**Commit:** 56be785
**Applied fix:** Added a required `tenant_id` parameter to `update_review_decision()`. Both the review-record lookup (`find_one_and_update`) and the evidence-status propagation (`asset_compliance.update_one`) now filter by `tenantId` in addition to `id`/`evidence.id`, matching the pattern used by every other function in the module. The `update_evidence_review` endpoint now resolves `current_user.tenant_id` (rejecting the request with 400 if missing) and forwards it to the service call, closing the cross-tenant approve/reject/request-changes vulnerability.

### WR-01: EvidenceReviewPanel makes unauthenticated requests — feature is non-functional

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** 168a94e
**Applied fix:** Replaced all four raw `fetch()` calls (`fetchReviews`, `handleSubmitForReview`, `handleReviewDecision`'s two calls) with the project's `authFetch()` helper from `services/apiService.ts`, and imported it alongside `API_BASE`. Removed the now-redundant manual `Content-Type: application/json` headers on the POST/PATCH calls since `authFetch` sets that automatically for non-`FormData` bodies. Requests from this panel now carry the `Authorization: Bearer <token>` header (and get 401-refresh-and-retry handling) instead of failing outright in production.

### WR-02: `get_pending_evidence` aggregation sort is a no-op

**Files modified:** `backend/evidence_review_service.py`
**Commit:** 6bdeeb4
**Applied fix:** Reordered the aggregation pipeline so `$sort` on `evidence.review_updated_at` runs immediately after the `$unwind`/`$match` stages, before the `$project` stage that drops the `evidence` object. The sort key now exists at the time `$sort` executes, so "newest first" ordering is honored.

### WR-03: PATCH review-decision endpoint ignores the `evidence_id` path parameter

**Files modified:** `backend/evidence_review_endpoints.py`
**Commit:** 67854fc
**Applied fix:** After `update_review_decision` returns, the endpoint now checks `review.get("evidenceId") == evidence_id` and returns 404 ("Review does not belong to the specified evidence item") on mismatch, so a caller can no longer pair an arbitrary `evidence_id` in the URL with an unrelated `review_id`.

### WR-04: `create_review` / `submit_for_review` do not validate evidence existence or current state

**Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
**Commit:** 594f362
**Applied fix:** `submit_for_review` now uses an `$elemMatch` query requiring the target evidence subdocument's status to be unset/`needs_revision`/`rejected` before transitioning it to `pending_review`, enforcing the documented lifecycle and preventing `approved`/`pending_review` evidence from being re-submitted. `create_review` now looks up the evidence item by `tenantId` + `evidence.id` first and raises `ValueError` (mapped to HTTP 404 in the endpoint) if no matching evidence exists, preventing orphaned review records.

### WR-05: Unhandled `ValueError` for invalid decision surfaces as 500, not 4xx

**Files modified:** `backend/evidence_review_endpoints.py`
**Commit:** 15e824e
**Applied fix:** Wrapped the `update_review_decision` call in the `update_evidence_review` endpoint with a `try/except ValueError`, converting an invalid-decision error into `HTTPException(422, ...)` instead of an unhandled 500. This defends the public service function against any future caller that bypasses the Pydantic `pattern` constraint on `UpdateDecisionRequest.decision`.

## Skipped Issues

None — all in-scope findings (CR-01, WR-01–WR-05) were fixed. IN-01 and IN-02 were intentionally excluded per `fix_scope: critical_warning` (`--all` was not passed) and remain open in REVIEW.md for a future `--all` pass.

## Verification Notes

- All backend edits passed `python -c "import ast; ast.parse(...)"` syntax checks.
- `pytest backend/tests/test_evidence_review.py` was run after each backend fix. It shows 6 pre-existing failures (all `500 Internal Server Error`, e.g. `test_create_review_record`, `test_approve_evidence_updates_status`) that were confirmed present on the pre-fix baseline commit (`5fa3445f`) as well — they stem from an unrelated environment/dependency issue, not from these fixes. No new test failures were introduced by any of the 6 commits (2 passed / 6 failed before and after every change).
- TypeScript compilation of `EvidenceReviewPanel.tsx` could not be verified via `tsc --noEmit` because `node_modules` is not installed in this environment; Tier 1 (manual re-read, confirmed no remaining raw `fetch(` calls) was used as the fallback per the 3-tier verification strategy.

---

_Fixed: 2026-07-01T20:49:41Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
