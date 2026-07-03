---
phase: 15-evidence-review-workflow
reviewed: 2026-07-03T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/evidence_review_endpoints.py
  - backend/evidence_review_service.py
  - backend/router_registry.py
  - backend/tests/test_evidence_review.py
  - components/AssetComplianceList.tsx
  - components/EvidenceReviewPanel.tsx
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

I independently re-derived every finding below directly from the current file
contents (not from commit messages or prior `-SUMMARY.md`/`-REVIEW*.md`
artifacts in this phase directory, which describe several earlier fix
iterations). The backend (`evidence_review_endpoints.py`,
`evidence_review_service.py`, `router_registry.py`) is solid: tenant scoping
is consistently enforced on every query, the `$elemMatch` evidence-status
propagation guard correctly prevents cross-item corruption, the `find_one_and_
update(upsert=True)` dedup on `create_review` is genuinely atomic, `_id` is
projected out of every Mongo-document response, and the audit-log write is
correctly isolated from the review-decision transaction with a try/except so
a logging failure can't turn a successful decision into a spurious 500.

The frontend, however, ships one **Critical** bug that breaks the majority of
the feature's actual purpose: the Approve and Reject buttons in
`EvidenceReviewPanel.tsx` send the wrong `decision` string to the backend, so
every Approve/Reject click currently fails validation and shows a generic
"Decision failed" toast. Only "Request Changes" works end-to-end. I traced
this by hand from button click through to the Pydantic-validated backend
field and confirmed FastAPI would reject the payload before the handler body
ever runs — this is not a hypothetical, it is the current behavior of the
shipped code.

I also found a second functional regression introduced within this same
change set: the evidence file-picker's `accept` attribute was tightened to
`.pdf,.png,.jpg,.jpeg,.docx,.xlsx`, which excludes every MIME type the
`isIngestibleText` gate (added specifically to route text evidence to the LLM
auditor) actually checks for (`text/plain`, `text/markdown`,
`application/json`, `text/csv`). The two changes contradict each other and
were made in different commits within the reviewed range, so neither author
saw the conflict. Three further Warnings and two Info items round out the
pass — see below.

## Critical Issues

### CR-01: Approve/Reject buttons send an invalid `decision` value — every decision except "Request Changes" fails with 422

**File:** `components/EvidenceReviewPanel.tsx:60, 103, 231`

**Issue:** The `action` state only ever holds the literal values
`'approve' | 'reject' | 'changes' | ''` (set at lines 203/206/209 by the
three action buttons). The "Confirm" button's click handler converts this
state to a wire value inline:

```tsx
onClick={() => handleReviewDecision(action === 'changes' ? 'changes_requested' : action)}
```

This correctly maps `'changes'` → `'changes_requested'`, but `'approve'` and
`'reject'` are passed straight through **unconverted**. `handleReviewDecision`
then PATCHes that literal string to the backend:

```tsx
body: JSON.stringify({ decision, comment: comment.trim() || '' }),
```

But `evidence_review_endpoints.py`'s `UpdateDecisionRequest` only accepts the
exact strings `approved`, `rejected`, `changes_requested`:

```python
decision: str = Field(..., pattern=r"^(approved|rejected|changes_requested)$")
```

`decision: "approve"` or `decision: "reject"` fails Pydantic validation
before the endpoint body ever executes, returning a 422 whose `detail` is a
non-string list of Pydantic error objects. The frontend's `_errorDetail`
helper falls back to a generic string in that case, so the reviewer just sees
"Decision failed" on every Approve or Reject click — the entire
approve/reject workflow is non-functional in the code as it stands right now.

A secondary consequence of the same root cause: the client-side
required-comment guard also compares against the wrong string —

```tsx
if ((decision === 'rejected' || decision === 'changes_requested') && !comment.trim()) {
```

— so for a Reject click, `decision === 'rejected'` evaluates `false` (the
value actually passed in is `'reject'`), meaning the client-side
"comment required" short-circuit never fires for Reject at all; the
(already-broken) request is sent regardless and only fails once it reaches
the 422 from the backend.

**Fix:** Map the internal `action` state to the backend's accepted decision
strings explicitly, and let the existing comment-guard comparison operate on
that mapped value:

```tsx
const DECISION_MAP: Record<'approve' | 'reject' | 'changes', string> = {
  approve: 'approved',
  reject: 'rejected',
  changes: 'changes_requested',
};

// at the Confirm button:
onClick={() => action && handleReviewDecision(DECISION_MAP[action])}
```

No frontend test in this repo currently exercises the React component's
click handlers (the backend test suite only issues hand-constructed HTTP
requests with already-correct `decision` strings), so this class of bug is
invisible to the existing test suite — a component-level regression test
asserting the PATCH body's `decision` field for each of the three buttons
would have caught it.

## Warnings

### WR-01: File-picker `accept` attribute silently defeats the text-evidence ingestion gate added in the same change set

**File:** `components/AssetComplianceList.tsx:57-58, 268`

**Issue:** `handleFileChange` only calls `onIngestEvidence` (which drives the
LLM auditor) when the uploaded file's MIME type matches one of:

```tsx
const INGESTIBLE_TEXT_TYPES = ['text/plain', 'text/markdown', 'application/json', 'text/csv'];
const isIngestibleText = INGESTIBLE_TEXT_TYPES.some(t => file.type.startsWith(t));
```

But the `<input type="file">`'s `accept` attribute, in the same reviewed
diff range, was changed to:

```tsx
accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"
```

None of `.txt`, `.md`, `.json`, or `.csv` are offered by the file picker's
default filter, so in the normal UI flow a user can no longer select any
file type that would actually satisfy `isIngestibleText` — the branch added
specifically to route text evidence to the LLM auditor is effectively
unreachable through the primary upload path. (Most browsers let a user
override the filter via an "All Files" option in the picker, so this is not
an absolute block, but it silently defeats the intended default behavior for
the exact evidence types — logs, JSON exports, CSVs, markdown notes — this
feature was built to ingest.)

**Fix:** Either restore the text extensions to `accept` (so the two lists
agree), or drop `text/csv`/`text/markdown`/`application/json` from
`INGESTIBLE_TEXT_TYPES` if binary-only evidence is now the intended scope —
whichever is correct, the two lists must describe the same set of file
types:

```tsx
accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.md,.json,.csv"
```

### WR-02: Reviews-thread toggle shows a misleading "(0)" count before the panel is first opened

**File:** `components/EvidenceReviewPanel.tsx:54, 139, 155`

**Issue:** `reviews` state is initialized to `[]` and is only populated by
`fetchReviews()`, which fires from
`useEffect(() => { if (open) fetchReviews(); }, [open, fetchReviews])` — i.e.
only after the user opens the panel. The toggle button label renders
`reviews.length` unconditionally:

```tsx
{open ? 'Hide reviews' : `Reviews (${reviews.length})`}
```

Before the panel has ever been opened, this always reads "Reviews (0)"
regardless of how many review rounds actually exist for that evidence item —
misleading a reviewer into thinking there's no history worth checking (e.g. a
prior rejection comment explaining exactly what needs to change) before they
make a new decision.

**Fix:** Either fetch the count eagerly (independent of `open`), or avoid
rendering a specific number until it's actually known:

```tsx
const [hasFetchedOnce, setHasFetchedOnce] = useState(false);
// set hasFetchedOnce(true) at the end of fetchReviews()
{open ? 'Hide reviews' : (hasFetchedOnce ? `Reviews (${reviews.length})` : 'Show reviews')}
```

### WR-03: GET review endpoints are unprotected by rate limiting while every mutating endpoint in the same router is capped

**File:** `backend/evidence_review_endpoints.py:175-201`

**Issue:** `submit_evidence_for_review`, `create_evidence_review`, and
`update_evidence_review` are all decorated with `@limiter.limit("30/minute")`,
but `list_evidence_reviews` (`GET /api/evidence/{evidence_id}/reviews`) and
`list_pending_review_evidence` (`GET /api/evidence/pending-review`) carry no
rate limit at all. `list_pending_review_evidence` runs a `$unwind`
aggregation across the tenant's entire `asset_compliance` collection
(`get_pending_evidence`) — an authenticated caller (or a leaked/compromised
token) can hit either GET endpoint at unlimited frequency, inconsistent with
the rest of the router's own threat model.

**Fix:** Apply the same limiter to both GET routes (note both handlers
currently lack the `request: Request` parameter the limiter decorator
requires, so it must be added alongside the decorator):

```python
@router.get("/api/evidence/{evidence_id}/reviews")
@limiter.limit("60/minute")
async def list_evidence_reviews(request: Request, evidence_id: str, current_user: TokenData = Depends(get_current_user)):
    ...
```

### WR-04: The one regression test for the CR-01 `$elemMatch` propagation fix silently skips when no MongoDB is reachable

**File:** `backend/tests/test_evidence_review.py:363-444`

**Issue:** `test_evidence_propagation_query_does_not_corrupt_unrelated_evidence_item`
is the only test in the file (and, per a repo-wide search, the only test in
`backend/tests/` using this pattern) that verifies the propagation query's
`$elemMatch` correctly ties `id` and `status` to the same array element
instead of letting Mongo's positional `$` operator resolve to — and corrupt —
an unrelated evidence item in the same document. It does this by connecting
to a live MongoDB instance and calling `pytest.skip(...)` if none is
reachable:

```python
try:
    await client.admin.command("ping")
except Exception:
    client.close()
    import pytest
    pytest.skip(f"No live MongoDB reachable at {mongo_uri} for CR-01 regression test")
    return
```

Every other test in this file uses a fully mocked `db` (which, as the
surrounding comment on line ~356 correctly notes, "structurally cannot catch
a query-shape bug like a missing `$elemMatch`" since a mock always returns
`modified_count=1` regardless of the filter passed). If CI does not have a
reachable `MONGODB_URI`/`MONGO_URI`, this test silently no-ops (reported as
"skipped", not "failed") and the single test asserting the correctness of
the most safety-critical query in this file provides zero actual coverage —
a future regression of this exact query shape would ship undetected.

**Fix:** At minimum, fail the test suite loudly (rather than skip) when
`MONGODB_URI`/`MONGO_URI` is required but absent in a CI context (e.g. gate
the skip behind a `CI` env var check, or make this test mandatory in the CI
pipeline config rather than best-effort). Better: add a mock-based
regression test that inspects the *filter dict* passed to
`asset_compliance.update_one` and asserts it contains a `$elemMatch` combining
both `id` and `status` — this would give first-class, non-optional coverage
of the same invariant without depending on a live database being available.

## Info

### IN-01: `ev: any` loosens type safety for the evidence array passed into `EvidenceReviewPanel`

**File:** `components/AssetComplianceList.tsx:134`

**Issue:** `statusRecord.evidence.map((ev: any, idx: number) => ...)` types
each evidence item as `any`, even though `AssetComplianceEvidence` (in
`types.ts`) already declares `status?: 'pending_review' | 'approved' |
'rejected' | 'needs_revision'`. Using `any` here means a typo in a property
name (e.g. `ev.stauts`) or a future rename of `AssetComplianceEvidence.status`
would not be caught by the compiler, even though `ev.status` is passed
straight through as `EvidenceReviewPanel`'s `evidenceStatus` prop, which
drives the entire review-actions gating logic (`canSubmitForReview`, the
reviewer-action visibility gate, and the status badge).

**Fix:** Type the map callback against `AssetComplianceEvidence`, widened
with the ad-hoc fields the AI-auditor rendering path also reads (e.g.
`evidence_content`, `check_name`, `agent_type`, `stale`), instead of `any`.

### IN-02: `create_review`'s two distinct failure modes are both mapped to HTTP 404

**File:** `backend/evidence_review_endpoints.py:97-98`, `backend/evidence_review_service.py:128-138`

**Issue:** `create_review` raises `ValueError` for two semantically different
conditions — the evidence item genuinely doesn't exist for the tenant, and
the evidence item exists but is in the wrong status (e.g. already
`approved`) — and the endpoint maps both to `404`:

```python
except ValueError as exc:
    raise HTTPException(status_code=404, detail=str(exc))
```

A 404 for "wrong status" is misleading REST semantics (409 Conflict or 422
Unprocessable Entity would more accurately describe "the resource exists but
isn't in a state that permits this operation" — the same class of error the
`update_review_decision` failure path already maps to 422). Since the
frontend surfaces `detail` text verbatim, users aren't currently misled in
practice, but any future client that branches on status code rather than
parsing the message body would be.

**Fix:** Differentiate the two `ValueError` cases (e.g. distinct exception
subclasses, or a status-code hint attached to the raised error) so
"not found" and "not in the right state" map to different HTTP status codes,
consistent with how `update_review_decision`'s equivalent failure is already
handled.

---

_Reviewed: 2026-07-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
