---
phase: 15-evidence-review-workflow
reviewed: 2026-07-01T20:40:22Z
depth: quick
files_reviewed: 7
files_reviewed_list:
  - backend/evidence_review_service.py
  - backend/evidence_review_endpoints.py
  - backend/tests/test_evidence_review.py
  - backend/router_registry.py
  - types.ts
  - components/EvidenceReviewPanel.tsx
  - components/AssetComplianceList.tsx
findings:
  critical: 2
  warning: 5
  info: 2
  total: 9
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-01T20:40:22Z
**Depth:** quick (extended to a light standard-depth read on the two service/endpoint files and one call-chain check, since the pattern scan surfaced structural risk worth confirming against actual code)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the evidence review workflow: backend service/endpoints, tests, router registration, and the two frontend components that consume the feature. Two blocking defects were found: a cross-tenant IDOR in the review-decision update path, and a frontend authentication gap that makes the entire panel non-functional in production (every request will 401). Several warnings cover a broken sort in the pending-evidence aggregation, a decoupled path parameter, missing state-machine guards, and a test that provides false confidence due to over-mocking.

## Critical Issues

### CR-01: Review decision endpoint has no tenant scoping — cross-tenant IDOR

**File:** `backend/evidence_review_service.py:89-146` (also `backend/evidence_review_endpoints.py:92-120`)
**Issue:** `update_review_decision()` looks up and mutates a review record using only `{"id": review_id}` — no `tenant_id` filter is applied, unlike every other function in this module (`submit_for_review`, `create_review`, `get_reviews`, `get_pending_evidence` all filter by `tenantId`). The evidence-status propagation step (lines 136-144) similarly filters only by `{"evidence.id": evidence_id}` with no tenant scoping.

The endpoint that calls it (`update_evidence_review`, `evidence_review_endpoints.py:92-120`) never receives or forwards `current_user.tenant_id` to `update_review_decision`. It only checks the caller's **role** (`admin`/`super_admin`/`compliance_reviewer`), not that the review belongs to the caller's tenant.

Net effect: any authenticated user with a reviewer role in **any** tenant can approve/reject/request-changes on a review record belonging to a **different** tenant, simply by guessing or observing a `review_id` (UUID hex, but IDs are often visible in shared UI/logs/URLs). This also lets a reviewer in Tenant A flip the evidence status for Tenant B's compliance record.

**Fix:**
```python
async def update_review_decision(
    review_id: str,
    decision: str,
    comment: str,
    db,
    tenant_id: str,
) -> dict | None:
    ...
    review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {"id": review_id, "tenantId": tenant_id},
        {"$set": {"status": decision, "comment": comment, "updated_at": now}},
        return_document=True,
    )
    if not review:
        return None
    evidence_id = review.get("evidenceId", "")
    if evidence_id:
        await db.asset_compliance.update_one(
            {"evidence.id": evidence_id, "tenantId": tenant_id},
            {"$set": {"evidence.$.status": evidence_status, "evidence.$.review_updated_at": now}},
        )
    return review
```
And in the endpoint:
```python
review = await update_review_decision(review_id, body.decision, body.comment, db, current_user.tenant_id)
```

## Warnings

### WR-01: EvidenceReviewPanel makes unauthenticated requests — feature is non-functional

**File:** `components/EvidenceReviewPanel.tsx:53,69,89,96`
**Issue:** Every network call in this component uses the raw browser `fetch()` API directly, instead of the project's `authFetch()` helper (`services/apiService.ts:198`). `authFetch` is responsible for attaching `Authorization: Bearer <token>` from `sessionStorage`, retrying on 401 with a refreshed token, and appending `X-Tenant-ID`. The backend's `get_current_user` dependency (`authentication_service.py:166-169`) uses `OAuth2PasswordBearer`, which reads the token **only** from the `Authorization` header — there is no cookie fallback.

Because `fetchReviews`, `handleSubmitForReview`, and `handleReviewDecision` never set an `Authorization` header, every request from this panel will return `401 Unauthorized` in a real deployment. The component's own error handling (`if (!res.ok) { setError(...) }`) will surface this as a generic error, but the review workflow itself cannot function at all — this is the single UI component that exercises the whole feature built in this phase.

Reclassified as blocking (should be CR-tier) given it makes the phase's primary deliverable inoperable; keeping as WARNING per the "no source files modified, cite concrete fix" formatting but flagging severity explicitly for the fixer: **treat as ship-blocking**.

**Fix:**
```tsx
import { authFetch, API_BASE } from '../services/apiService';
...
const res = await authFetch(`${API_BASE}/evidence/${evidenceId}/reviews`);
...
const res = await authFetch(`${API}/evidence/${evidenceId}/submit-for-review`, { method: 'POST' });
...
const reviewRes = await authFetch(`${API}/evidence/${evidenceId}/review`, {
  method: 'POST', body: JSON.stringify({ comment: comment.trim() || 'Review' }),
});
```
(`authFetch` already sets `Content-Type: application/json` when body isn't `FormData`, so the manual header can be dropped too.)

### WR-02: `get_pending_evidence` aggregation sort is a no-op — "newest first" claim is false

**File:** `backend/evidence_review_service.py:172-192`
**Issue:** The `$sort` stage (line 189) sorts by `"evidence.review_updated_at"`, but the preceding `$project` stage (lines 176-188) does not include the `evidence` object or an `evidence_updated_at` field — it only projects `assetId`, `controlId`, `status`, `lastUpdated`, `checkName`, and several flattened `evidence_*` fields, none of which is `review_updated_at`. Since MongoDB `$project` drops any field not explicitly listed, `evidence.review_updated_at` does not exist by the time `$sort` runs, so the sort has no effect (MongoDB treats a missing sort key as an implicit constant and result order becomes effectively undefined/insertion-order).
**Fix:** Either project the field explicitly, or sort before projecting:
```python
pipeline = [
    {"$match": {"tenantId": tenant_id}},
    {"$unwind": "$evidence"},
    {"$match": {"evidence.status": "pending_review"}},
    {"$sort": {"evidence.review_updated_at": -1}},
    {"$project": {
        "assetId": 1, "controlId": 1, "status": 1, "lastUpdated": 1, "checkName": 1,
        "evidence_id": "$evidence.id", "evidence_name": "$evidence.name",
        "evidence_date": "$evidence.uploadedAt", "evidence_agent_type": "$evidence.agent_type",
    }},
]
```

### WR-03: PATCH review-decision endpoint ignores the `evidence_id` path parameter

**File:** `backend/evidence_review_endpoints.py:92-120`
**Issue:** The route is `PATCH /api/evidence/{evidence_id}/review/{review_id}`, but `evidence_id` is never read or validated inside the handler — only `review_id` and `body.decision`/`body.comment` are used. A caller can supply any `evidence_id` in the URL (including one that doesn't match the review's actual `evidenceId`) and the decision will still be applied to whatever review `review_id` resolves to. This makes the URL structure misleading and, combined with CR-01, removes any implicit scoping the path might have suggested.
**Fix:** Validate that `review.get("evidenceId") == evidence_id` after lookup (in addition to fixing CR-01), or drop the redundant `evidence_id` segment from the route.

### WR-04: `create_review` / `submit_for_review` do not validate evidence existence or current state

**File:** `backend/evidence_review_service.py:44-86`
**Issue:** `create_review()` inserts a review record referencing `evidence_id` without checking that the evidence item exists for the given `tenant_id`, or that it is currently in a reviewable state (e.g., `pending_review`). Likewise `submit_for_review()` (lines 44-63) has no guard preventing a transition from `approved` (or `rejected`) directly back to `pending_review` — the docstring's stated lifecycle (`needs_revision → submit-for-review → pending_review`) is not enforced anywhere; any status can be moved to `pending_review` at any time, and orphaned review records can be created for evidence IDs that don't exist.
**Fix:** Add a state check in `submit_for_review` (only allow from unset/`needs_revision`/`rejected`) and validate evidence existence before `create_review` inserts a record.

### WR-05: Unhandled `ValueError` for invalid decision surfaces as 500, not 4xx

**File:** `backend/evidence_review_service.py:108-110`
**Issue:** `update_review_decision` raises `ValueError` for a decision outside `_valid_decisions()`. The FastAPI endpoint (`evidence_review_endpoints.py:116`) does not catch this — currently unreachable via the HTTP API because `UpdateDecisionRequest.decision` is constrained by a Pydantic `pattern`, but the service function is a public module-level API and any other caller (script, future endpoint, test) that passes an invalid decision will get an unhandled 500-style stack trace instead of a controlled error.
**Fix:** Wrap the call site or catch `ValueError` and re-raise as `HTTPException(422, ...)` defensively, since relying solely on the Pydantic regex at one call site is fragile.

## Info

### IN-01: Unused `Optional` import

**File:** `backend/evidence_review_service.py:15`, `backend/evidence_review_endpoints.py:15`
**Issue:** `from typing import Optional` is imported in both files but never referenced (no `Optional[...]` annotations exist in either file).
**Fix:** Remove the unused import.

### IN-02: `test_approve_evidence_updates_status` / `test_changes_requested_sets_needs_revision` provide false confidence

**File:** `backend/tests/test_evidence_review.py:35-39, 96-141`
**Issue:** `_make_mock_db()` stubs `find_one_and_update` to always return a hardcoded dict with `"status": "approved"`, regardless of the `decision` argument passed by the code under test. `test_approve_evidence_updates_status` asserts `data["review"]["status"] == "approved"`, which would pass even if `update_review_decision` silently dropped or mis-mapped the `decision` parameter before calling `find_one_and_update`. The `changes_requested` test doesn't assert on `status` at all, so the "needs_revision" mapping documented in the service module is not actually verified by any test.
**Fix:** Make the mock echo back the `decision`/filter it received (e.g., use `side_effect` reading the `$set` dict), and add an assertion on `evidence.$.status` mapping (e.g., assert `db.asset_compliance.update_one` was called with `"evidence.$.status": "needs_revision"`).

---

_Reviewed: 2026-07-01T20:40:22Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
