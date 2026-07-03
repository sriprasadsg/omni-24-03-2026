---
phase: 15-evidence-review-workflow
reviewed: 2026-07-03T00:00:00Z
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
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is the fifth review round for the evidence review workflow. I re-verified
every finding from the prior review rounds directly against the current file
contents rather than trusting the commit messages that claim they were fixed:
the ObjectId-leak fix (`projection={"_id": 0}` on every `find_one_and_update`
and `find`, and `"_id": 0` in the aggregation `$project`), the `decided_by`
attribution field, the autouse `_stop_patchers` fixture, the `/_/g` global
underscore replace, and the `_errorDetail` non-string-`detail` guard are all
genuinely present and correct in the current code — no regressions there.
`router_registry.py` correctly wires `evidence_review_endpoints` into the app,
and the backend test suite (14/14) passes, including the CR-01 `$elemMatch`
regression test against a live MongoDB.

Independent analysis of the current code, tracing the full request path from
`EvidenceReviewPanel.tsx` through to `evidence_review_endpoints.py`, surfaced
one **Critical** bug that none of the four prior review rounds caught: the
Approve and Reject buttons send an invalid `decision` value to the backend,
so every Approve/Reject click currently fails with a 422 and a generic
"Decision failed" toast. Only "Request Changes" works end-to-end. This bug
predates the most recent commit (`5460c38`, "address UI review findings") —
`git log -p --follow` confirms the offending line is unchanged since the
feature's original introduction — so it is not a regression introduced by
that commit, but it is a genuine, currently-shipping defect in the reviewed
file, and it breaks the majority of the feature's core purpose. The most
recent commit itself does not introduce new regressions: every change in it
(icon additions, error-detail extraction, `aria-expanded`, button sizing,
`REVIEW_STATUS_STYLES`) is well-formed and consistent with the rest of the
component.

Two Warnings and one Info round out this pass: a misleading "Reviews (0)"
count shown before the panel is first opened, an inconsistency in rate-limit
coverage across the router's GET vs. mutating endpoints, and a loosened
`any` type on the evidence array in `AssetComplianceList.tsx`.

## Critical Issues

### CR-01: Approve/Reject buttons send an invalid `decision` value — every decision except "Request Changes" fails with 422

**File:** `components/EvidenceReviewPanel.tsx:60, 103, 231`

**Issue:** The `action` state only ever holds `'approve' | 'reject' | 'changes' | ''` (set at lines 203/206/209). The "Confirm" button converts `action` to a wire value at the call site:

```tsx
onClick={() => handleReviewDecision(action === 'changes' ? 'changes_requested' : action)}
```

This maps `'changes'` → `'changes_requested'`, but leaves `'approve'` and `'reject'` **unconverted** — they are passed straight through as the literal strings `'approve'` and `'reject'`. `handleReviewDecision` then PATCHes that literal value to the backend:

```tsx
body: JSON.stringify({ decision, comment: comment.trim() || '' }),
```

But `evidence_review_endpoints.py`'s `UpdateDecisionRequest` only accepts the exact strings `approved`, `rejected`, `changes_requested`:

```python
decision: str = Field(..., pattern=r"^(approved|rejected|changes_requested)$")
```

Sending `decision: "approve"` or `decision: "reject"` fails FastAPI's Pydantic validation before the endpoint body ever runs, returning a 422 whose `detail` is a non-string list of Pydantic error objects. The frontend's own `_errorDetail` helper correctly falls back to a generic string in that case, so the user just sees "Decision failed" on every Approve or Reject click — the entire approve/reject workflow is non-functional in the current code. Only "Request Changes" (which correctly maps to `changes_requested`) works.

A secondary consequence of the same root cause: the client-side required-comment guard at line 103 also compares against the wrong string —

```tsx
if ((decision === 'rejected' || decision === 'changes_requested') && !comment.trim()) {
```

— so for a Reject click, `decision === 'rejected'` is `false` (the value received is `'reject'`), meaning the client-side "comment required" short-circuit never actually fires for Reject; the (already-broken) request is sent regardless and fails on the 422 instead.

Verified this is not a new regression from the most recent commit: `git log -p --follow -- components/EvidenceReviewPanel.tsx` shows this exact line unchanged since the feature's original commit (`e52393a`), and none of the four subsequent fix commits (`0ef3c4b`, `299c92d`, `7975d71`, `7eb0cb7`, `5460c38`) touched it. It is, however, still present in the code under review right now and breaks the majority of the feature's purpose.

**Fix:** Map the internal `action` state to the backend's accepted decision strings explicitly, and fix the comment-guard comparison to match:

```tsx
const DECISION_MAP: Record<'approve' | 'reject' | 'changes', string> = {
  approve: 'approved',
  reject: 'rejected',
  changes: 'changes_requested',
};

// at the Confirm button:
onClick={() => action && handleReviewDecision(DECISION_MAP[action])}
```

`handleReviewDecision`'s existing comment-guard logic (`decision === 'rejected' || decision === 'changes_requested'`) needs no further change once the caller always passes a backend-shaped value. Add a frontend regression test (or at minimum a manual UAT pass) asserting the PATCH body's `decision` field is `approved`/`rejected`/`changes_requested` for each of the three action buttons — the backend test suite cannot catch this class of bug since it never exercises the React component, only hand-constructed HTTP requests with already-correct decision strings.

## Warnings

### WR-01: Reviews-thread toggle shows a misleading "(0)" count before the panel is first opened

**File:** `components/EvidenceReviewPanel.tsx:54, 139, 155`

**Issue:** `reviews` state is initialized to `[]` and is only populated by `fetchReviews()`, which is triggered from `useEffect(() => { if (open) fetchReviews(); }, [open, fetchReviews])` — i.e. only after the user opens the panel. The toggle button label, however, renders `reviews.length` unconditionally:

```tsx
{open ? 'Hide reviews' : `Reviews (${reviews.length})`}
```

Before the panel has ever been opened, this always reads "Reviews (0)" regardless of how many review rounds actually exist for that evidence item. This can mislead a reviewer into believing there is no review/rejection history worth checking before making a new decision, when in fact there may be several prior rounds (e.g. a previous rejection comment explaining exactly what needs to change).

**Fix:** Either fetch the review count eagerly (independent of `open`), or don't render a specific count until it's actually known:

```tsx
const [hasFetchedOnce, setHasFetchedOnce] = useState(false);
// ...set hasFetchedOnce(true) at the end of fetchReviews()...
{open ? 'Hide reviews' : (hasFetchedOnce ? `Reviews (${reviews.length})` : 'Show reviews')}
```

### WR-02: GET review endpoints are unprotected by rate limiting while every mutating endpoint in the same router is capped

**File:** `backend/evidence_review_endpoints.py:175-201`

**Issue:** `submit_evidence_for_review`, `create_evidence_review`, and `update_evidence_review` are all decorated with `@limiter.limit("30/minute")`, but `list_evidence_reviews` (`GET /api/evidence/{evidence_id}/reviews`) and `list_pending_review_evidence` (`GET /api/evidence/pending-review`) have no rate limit at all. The latter runs a `$unwind` aggregation across the tenant's entire `asset_compliance` collection (`get_pending_evidence`) — an authenticated user (or a compromised/leaked token) can hit this endpoint at unlimited frequency, which is inconsistent with the rest of the router's own threat model.

**Fix:** Apply the same limiter to both GET routes for consistency (note both handlers currently lack the `request: Request` parameter the limiter decorator requires, so it must be added alongside the decorator):

```python
@router.get("/api/evidence/{evidence_id}/reviews")
@limiter.limit("60/minute")
async def list_evidence_reviews(request: Request, evidence_id: str, current_user: TokenData = Depends(get_current_user)):
    ...
```

## Info

### IN-01: `ev: any` loosens type safety for the evidence array passed into `EvidenceReviewPanel`

**File:** `components/AssetComplianceList.tsx:134`

**Issue:** `statusRecord.evidence.map((ev: any, idx: number) => ...)` types each evidence item as `any`, even though `AssetComplianceEvidence` (in `types.ts`) already declares a `status?: 'pending_review' | 'approved' | 'rejected' | 'needs_revision'` field. Using `any` here means a typo in a property name (e.g. `ev.stauts`) or a future rename of `AssetComplianceEvidence.status` would not be caught by the compiler at this call site, even though `ev.status` is passed straight through as `EvidenceReviewPanel`'s `evidenceStatus` prop, which drives the entire review-actions gating logic.

**Fix:** Type the map callback against `AssetComplianceEvidence` (widened with the ad-hoc fields the AI-auditor rendering path also reads, e.g. `evidence_content`, `check_name`) instead of `any`.

---

_Reviewed: 2026-07-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
