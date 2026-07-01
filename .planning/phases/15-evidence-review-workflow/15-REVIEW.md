---
phase: 15-evidence-review-workflow
reviewed: 2026-07-02T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/evidence_review_service.py
  - backend/evidence_review_endpoints.py
  - backend/tests/test_evidence_review.py
  - components/EvidenceReviewPanel.tsx
  - backend/router_registry.py
  - components/AssetComplianceList.tsx
findings:
  critical: 1
  warning: 6
  info: 1
  total: 8
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a fresh standard-depth re-review of the evidence review workflow after the prior quick-depth pass (2026-07-01) and its fix commits (tenant scoping, `authFetch`, aggregation sort order, evidence-existence validation, 422-on-invalid-decision, T-10 audit logging, T-11 rate limiting, T-12 result-set capping). Those fixes are confirmed present and working in the current code. However, the WR-03 fix ("validate evidence_id path param matches review's evidenceId") was implemented incorrectly: the validation runs *after* the mutating database call it's supposed to guard, so a mismatched request still mutates state (and skips the audit log entirely) before being rejected with a 404. This is a genuine regression introduced by the "fix" itself and is classified as a new Critical finding below. Several additional workflow-integrity and frontend/backend consistency gaps were found that were not covered by the prior review.

## Critical Issues

### CR-01: Evidence-ID mismatch check runs after the mutating call — state changes without a matching audit log entry

**File:** `backend/evidence_review_endpoints.py:134-159` (root cause in `backend/evidence_review_service.py:117-177`)
**Issue:** `update_evidence_review` calls `update_review_decision(review_id, ...)` — which unconditionally updates the review record's status *and* propagates the new status onto the evidence array in `asset_compliance` — before it ever checks whether the URL's `evidence_id` matches the review's actual `evidenceId`:

```python
review = await update_review_decision(review_id, body.decision, body.comment, db, tenant_id)  # <- mutates DB here
...
if review.get("evidenceId") != evidence_id:   # <- checked AFTER the mutation
    raise HTTPException(status_code=404, detail="Review does not belong to the specified evidence item")

await db.audit_logs.insert_one({...})   # <- never reached on mismatch
```

`update_review_decision` doesn't take `evidence_id` as an input at all — it derives the evidence to update from the review record it just fetched (`review.get("evidenceId", "")`), completely independent of what was in the URL. So when `evidence_id` (URL) and the review's real `evidenceId` diverge:
1. The review record and the (real, different-from-URL) evidence item's status are both mutated for real.
2. The caller receives a 404 ("Review does not belong to the specified evidence item"), which reads as "nothing happened" — misleading given a write actually occurred.
3. The audit-log insert (added specifically for T-10 non-repudiation) is never reached, so this decision is applied with **no audit trail at all** — directly undermining the guarantee T-10 was written to provide.

This is reachable by any user holding a reviewer role in their own tenant (no cross-tenant IDOR required — `review_id` need only belong to a *different* evidence item within the same tenant, which is plausible given `create_review` lets any user create reviews against arbitrary evidence IDs with no ownership check, see WR-02 below). No test in `test_evidence_review.py` exercises this path — every test's mocked `find_one_and_update` returns `"evidenceId": "ev-1"` and every test PATCHes `/api/evidence/ev-1/review/...`, so the mismatch branch is never hit and this was not caught before merge.

**Fix:** Make the mismatch check part of the same atomic lookup, not a post-hoc check on the result of a call that already wrote. Pass `evidence_id` into `update_review_decision` and include it in the initial filter so a mismatch naturally yields "not found" with zero side effects:
```python
async def update_review_decision(review_id, evidence_id, decision, comment, db, tenant_id):
    ...
    review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {"id": review_id, "evidenceId": evidence_id, "tenantId": tenant_id},
        {"$set": {"status": decision, "comment": comment, "updated_at": now}},
        return_document=True,
    )
    if not review:
        return None  # covers "not found" AND "belongs to a different evidence item"
    ...
```
And in the endpoint, drop the after-the-fact check and call with `evidence_id` up front, so the audit log is only ever skipped when nothing was actually mutated.

## Warnings

### WR-01: Evidence-status propagation ignores whether the update actually matched anything

**File:** `backend/evidence_review_service.py:164-175`
**Issue:** After updating the review record, the evidence status propagation call is fire-and-forget:
```python
await db.asset_compliance.update_one(
    {"evidence.id": evidence_id, "tenantId": tenant_id},
    {"$set": {"evidence.$.status": evidence_status, "evidence.$.review_updated_at": now}},
)
```
The result (`modified_count`) is never checked. If the evidence item no longer exists at this `id` (e.g., deleted via `onDeleteEvidence` after the review was created, or the `evidence.id` was otherwise changed), this call silently matches nothing. `update_review_decision` still returns the updated review dict, the endpoint still returns `200 {"success": true}`, and an audit log entry is still written claiming the decision was applied — but the evidence record's badge/status was never actually changed. Contrast with `submit_for_review`, which correctly returns `False`/404 based on `modified_count`.
**Fix:** Check `result.modified_count` and log a warning (or surface a non-fatal flag in the response) when the evidence propagation didn't match, so the discrepancy is at least observable.

### WR-02: No workflow-state guard on `create_review` / `update_review_decision` — decisions can bypass `pending_review` and be re-applied indefinitely

**File:** `backend/evidence_review_service.py:84-114` (`create_review`), `117-177` (`update_review_decision`)
**Issue:** `submit_for_review` correctly restricts itself to evidence currently in `[None, "needs_revision", "rejected"]` via `_submittable_statuses()`. That guard is not mirrored anywhere else in the lifecycle:
- `create_review` only checks that the evidence item *exists* for the tenant (`594f3622`'s WR-04 fix) — it does not check that the evidence is currently `pending_review`. Any authenticated user can open a review thread against evidence in any state.
- `update_review_decision` applies `evidence_status` unconditionally to whatever the review's `evidenceId` currently is — it never checks that the evidence's current status is `pending_review`, nor that the review's own current status is still `pending` (i.e., a review that has already been decided `approved` can be PATCHed again to `rejected`, silently flipping the evidence status back and forth with no idempotency guard).

Net effect: the documented lifecycle (`Uploaded → submit-for-review → pending_review → approved/rejected/needs_revision`) is only enforced at one edge (`submit_for_review`); a reviewer can approve/reject evidence that was never submitted for review, and repeated PATCH calls on the same `review_id` can re-decide it arbitrarily.
**Fix:** In `create_review`, additionally check the matched evidence's `status == "pending_review"` (or accept it as an explicit "comment thread" concept if that's intentional — currently undocumented either way). In `update_review_decision`, filter the review lookup on `status: "pending"` so a review can only be decided once, and/or verify the evidence's current status is `pending_review` before propagating.

### WR-03: Frontend "Submit for Review" gating doesn't match backend's submittable states

**File:** `components/EvidenceReviewPanel.tsx:43`
**Issue:**
```tsx
const canSubmitForReview = !evidenceStatus || evidenceStatus === 'needs_revision';
```
The backend's `_submittable_statuses()` (`backend/evidence_review_service.py:44-49`) explicitly allows resubmission from `[None, "needs_revision", "rejected"]`. The frontend condition omits `'rejected'`, so once evidence is rejected, the "Submit for Review" button disappears and the user has no UI path to resubmit — the evidence appears permanently stuck, even though the backend would accept the resubmission.
**Fix:**
```tsx
const canSubmitForReview = !evidenceStatus || evidenceStatus === 'needs_revision' || evidenceStatus === 'rejected';
```

### WR-04: `EvidenceReviewPanel` is rendered with a possibly-`undefined` `evidenceId`, unlike the adjacent delete button

**File:** `components/AssetComplianceList.tsx:125, 166, 179-187`
**Issue:** `evId` is derived as `ev.id || ev.evidence_id`, which is `undefined` for evidence entries lacking both fields (this exact gap was already fixed for the delete button in commit `552d4e02`, which added an explicit `evId &&` guard: `{!isAutomated && evId && (<button onClick={() => handleDeleteEvidence(asset.id, evId)} .../>)}`). The newer `EvidenceReviewPanel` added in this phase has no equivalent guard:
```tsx
<EvidenceReviewPanel
  evidenceId={evId}
  evidenceStatus={ev.status}
  onStatusChange={...}
/>
```
When `evId` is `undefined`, the panel still renders, `fetchReviews`/`handleSubmitForReview`/`handleReviewDecision` all fire requests against literal URLs like `/api/evidence/undefined/reviews` and `/api/evidence/undefined/submit-for-review`.
**Fix:** Guard the same way the delete button already does: `{evId && <EvidenceReviewPanel evidenceId={evId} .../>}`.

### WR-05: `onStatusChange` callback overwrites compliance status with a stale value, using a default inconsistent with the rest of the file

**File:** `components/AssetComplianceList.tsx:182-186` (compare with the default used at line 101)
**Issue:**
```tsx
onStatusChange={() => {
  if (typeof onUpdateStatus === 'function') {
    onUpdateStatus(asset.id, statusRecord?.status || 'Pending_Evidence');
  }
}}
```
This is invoked after every review decision purely to trigger a parent refresh (`FrameworkDetail.tsx`'s `onUpdateStatus` handler calls `api.updateAssetComplianceStatus(...)` followed by `refreshAssetCompliance(assetId)`). Two problems:
1. It writes the control-level compliance status back using `statusRecord?.status`, a value captured at render time — if another user changed the status concurrently between render and this callback firing, this call silently reverts it to the stale value (and `updateAssetComplianceStatus` is a real, side-effecting write, not a pure refresh).
2. The fallback default here is `'Pending_Evidence'`, but the fallback used elsewhere in the same file for the same field (line 101: `const status = statusRecord?.status || 'Non-Compliant';`) is `'Non-Compliant'`. If `statusRecord` is `undefined` when a review decision completes, this callback actively sets the compliance status to `'Pending_Evidence'` — a value inconsistent with what the rest of the component treats as the "no record" default — causing a spurious, wrong status write.
**Fix:** Don't reuse `onUpdateStatus` (a real write) to trigger a refresh. Either add a dedicated read-only refresh callback prop, or at minimum use the same default (`'Non-Compliant'`) as line 101 for consistency, and avoid firing the write when `statusRecord` is undefined.

### WR-06: `test_tenant_isolation` does not test tenant isolation and cannot fail

**File:** `backend/tests/test_evidence_review.py:193-208`
**Issue:** The test is named and commented as verifying "tenant-a user cannot access tenant-b evidence reviews," but it only constructs a single tenant (`tenant-a`) and a nonexistent evidence id (`ev-other`) — there is no tenant-b user, no tenant-b data, and no assertion that cross-tenant data is actually excluded. The GET assertion is maximally permissive:
```python
resp = client.get("/api/evidence/ev-other/reviews")
assert resp.status_code in (200, 403, 404), f"Got {resp.status_code}: {resp.text}"
```
Any of the three most likely response codes passes, so this assertion cannot distinguish correct tenant-scoped behavior from a broken one. This is precisely the class of bug the previous review's CR-01 (cross-tenant IDOR) was in, and it's also precisely the class of gap that let CR-01 (this review) go undetected — a real cross-tenant or cross-evidence fixture with a strict expected status code would have exercised the code path this review's CR-01 finding lives in.
**Fix:** Build an actual second-tenant fixture (different `tenant_id` on the mock user, mock DB seeded to reflect a document that belongs only to tenant-b) and assert a single, specific expected status code (404, given tenant-scoped queries return "not found" for cross-tenant records in this codebase's convention).

## Info

### IN-01: Unused `Optional` import

**File:** `backend/evidence_review_service.py:15`, `backend/evidence_review_endpoints.py:16`
**Issue:** `from typing import Optional` is imported in both files but never referenced — no `Optional[...]` annotation appears in either file (both use `dict | None` PEP 604 syntax instead).
**Fix:** Remove the unused import from both files.

---

_Reviewed: 2026-07-02T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
