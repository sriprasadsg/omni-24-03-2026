---
phase: 15-evidence-review-workflow
reviewed: 2026-07-02T08:04:38Z
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
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-02T08:04:38Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a fresh, independent pass, not a re-check of the prior two review iterations. I re-verified all previously reported findings (CR-01 `$elemMatch` propagation fix, WR-01 atomic-upsert dedup, WR-02 reviewer-button gating, WR-03 audit-log try/except, WR-04 non-mutating `onEvidenceReviewed` callback, IN-01/IN-02) directly against the current file contents and confirmed all six remain correctly applied — no regressions there.

Independent analysis of the current code surfaced one new **Critical** bug that neither prior iteration caught, and it is not theoretical: I stood up a real local MongoDB instance, ran the actual service and endpoint code against it end-to-end (bypassing the unit tests' mocks entirely), and reproduced a **500 Internal Server Error on every endpoint in this feature that returns a Mongo document** — `POST /review`, `PATCH /review/{id}`, `GET /reviews`, and `GET /pending-review` all fail against real data. Only `POST /submit-for-review` (which returns a hand-built static dict, not a Mongo document) is unaffected. The existing unit test suite (13/13 "passing") never catches this because every mock in `test_evidence_review.py` hand-crafts its return dicts and never includes the `_id: ObjectId(...)` field that real MongoDB always injects — this is a clear case of "tests pass" masking a completely broken feature.

Beyond that, this pass also found a data-integrity gap in review-record attribution (reviewer identity is fixed at creation time, not decision time), a narrower TOCTOU in `create_review`'s validation step, a frontend crash path when a validation error's `detail` is a non-string payload, and a test-hygiene issue (`mock.patch` never stopped) that can leak mocked state into other test modules in the same pytest session.

Status is `issues_found` because of the Critical finding below.

## Critical Issues

### CR-01: `_id` (a raw `bson.ObjectId`) is never stripped from Mongo documents before they're returned from the API — every document-returning endpoint in this feature 500s against real MongoDB

**File:** `backend/evidence_review_service.py:127-144` (`create_review`), `:193-208` (`update_review_decision`), `:252-268` (`get_reviews`), `:271-303` (`get_pending_evidence`); consumed directly in `backend/evidence_review_endpoints.py:99,166,181,195`

**Issue:** `create_review`'s `find_one_and_update(..., upsert=True, return_document=True)`, `update_review_decision`'s `find_one_and_update(...)`, `get_reviews`'s `cursor.to_list(...)`, and `get_pending_evidence`'s aggregation `$project` stage all return/emit the raw MongoDB document (or, for the aggregation, an inclusion-mode `$project` that keeps `_id` by default since it is never explicitly excluded with `"_id": 0`). None of these functions strip the `_id` field before the dict is handed back to the endpoint layer, which returns it directly in the JSON response body (`{"success": True, "review": review}`, `{"reviews": reviews, ...}`, `{"items": items, ...}`).

`_id` on a real MongoDB document is a `bson.ObjectId`, which FastAPI's default `jsonable_encoder` cannot serialize:

```pycon
>>> from fastapi.encoders import jsonable_encoder
>>> from bson import ObjectId
>>> jsonable_encoder({'_id': ObjectId(), 'name': 'x'})
ValueError: [TypeError("'ObjectId' object is not iterable"), TypeError('vars() argument must have __dict__ attribute')]
```

**Empirically reproduced end-to-end against a live local MongoDB** (not speculative — ran the real service + endpoint code, not the mocked unit tests):

```
CREATE: 500 Internal Server Error   # POST /api/evidence/{id}/review
LIST:   500 Internal Server Error   # GET  /api/evidence/{id}/reviews
PENDING:500 Internal Server Error   # GET  /api/evidence/pending-review
```
(`PATCH /review/{id}` shares the identical `find_one_and_update` → raw-dict-with-`_id` → `jsonable_encoder` path and fails the same way; not separately reproduced only because the prerequisite `CREATE` call above already fails before a `review_id` exists to PATCH.)

This means the entire evidence review workflow — creating a review, deciding it, listing its history, and the pending-review queue — is non-functional against a real database. `POST /submit-for-review` is the *only* endpoint in this router unaffected, because it's the only one that returns a hand-built literal dict (`{"success": True, "status": "pending_review"}`) rather than a document read back from Mongo.

The unit test suite passes (13/13) and gave false confidence here because `_make_mock_db()` in `test_evidence_review.py` hand-crafts every mocked return value (e.g. `{"id": "rev-abc", "evidenceId": "ev-1", "status": "approved", ...}`) — none of these fixtures include an `_id` key, since a `MagicMock`/`AsyncMock` has no way to know MongoDB would inject one. The gap between "what the mock returns" and "what a real `insert_one`/`find_one_and_update` call actually returns" is exactly the kind of thing that makes a green test suite an unreliable signal of correctness.

**Fix:** Strip `_id` (or project it out) everywhere a document crosses the API boundary. Two options, pick one and apply consistently:

```python
# Option A: project it out at the query level
review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
    {...}, {...}, upsert=True, return_document=True,
    projection={"_id": 0},
)

cursor = (
    db._db[_EVIDENCE_REVIEWS_COL]
    .find({"evidenceId": evidence_id, "tenantId": tenant_id}, {"_id": 0})
    .sort("created_at", -1)
)

# aggregation $project stage:
{"$project": {"_id": 0, "assetId": 1, "controlId": 1, ...}}
```

```python
# Option B: strip it after the fact, once, right before returning
def _strip_id(doc: dict | None) -> dict | None:
    if doc and "_id" in doc:
        doc = {k: v for k, v in doc.items() if k != "_id"}
    return doc
```

Recommend adding a regression test that exercises these code paths against a real (or embedded) MongoDB rather than a mock — exactly the pattern the existing CR-01 regression test (`test_evidence_propagation_query_does_not_corrupt_unrelated_evidence_item`) already establishes for this same reason (mocks can't catch structural/serialization bugs). That test's own `_RealDbWrapper` harness can be reused directly; it already skips cleanly when no MongoDB is reachable.

## Warnings

### WR-01: A review's `reviewer` field is fixed at creation time and never updated at decision time — the record can permanently misattribute who actually approved/rejected/requested changes

**File:** `backend/evidence_review_service.py:130-140` (creation sets `reviewer`), `:200-206` (decision `$set` never touches `reviewer`)
**Issue:** `create_review`'s atomic upsert only sets `"reviewer": reviewer` inside `$setOnInsert` (line 134) — i.e. only on the *first* creation of a `pending` record for that `evidenceId`. If that dedup path is hit (an existing `pending` record is returned instead of a new one being inserted — exactly the scenario the WR-01 fix from the prior iteration was designed to handle), the returned `review.id` belongs to whoever created it first, and `current_user.username` passed into `create_review` by the *current* caller is silently discarded.

`update_review_decision`'s `$set` clause (lines 200-206) then only updates `status`, `comment`, and `updated_at` — never `reviewer` — when the decision is actually made. So if reviewer A opens the panel and creates the pending review, and reviewer B (in a different tab/session) is the one who actually clicks Approve/Reject (their `POST /review` call dedups onto A's existing pending record via the atomic upsert, then their `PATCH .../review/{id}` decides it), the final review record shows `reviewer: "A"` even though B made the decision. `EvidenceReviewPanel.tsx:154` renders `rv.reviewer` prominently in the review thread, so this misattribution is directly user-visible, not just an internal detail. The separate `audit_logs` entry written in the endpoint (`evidence_review_endpoints.py:152-160`) does correctly capture `performed_by: current_user.username`, so there is a secondary correct record — but the primary, user-facing review document itself is wrong.

**Fix:** Pass the deciding user's identity into `update_review_decision` and set it explicitly, e.g. add a `decided_by` field (or update `reviewer` if that's meant to represent "current owner of the decision" rather than "who opened the thread"):

```python
async def update_review_decision(review_id, evidence_id, decision, comment, db, tenant_id, decided_by: str):
    ...
    review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {...},
        {"$set": {"status": decision, "comment": comment, "updated_at": now, "decided_by": decided_by}},
        return_document=True,
    )
```
and pass `current_user.username` through from `evidence_review_endpoints.py:134-136`.

### WR-02: `create_review`'s "evidence must be pending_review" validation is check-then-act, not atomic — the guard can be stale by the time the review record is actually written

**File:** `backend/evidence_review_service.py:111-144`
**Issue:** The evidence-status validation (`find_one` + manual scan of the `evidence` array, lines 111-124) is a separate read from the atomic `find_one_and_update(upsert=True)` that follows it (lines 127-143). The upsert's own filter is only `{"tenantId": tenant_id, "evidenceId": evidence_id, "status": "pending"}` — it does not re-check that the evidence is still `pending_review` at the moment of the write. Between the validation read and the upsert, another request (e.g. a reviewer deciding the evidence in the same window) can change the evidence's status, and a new `pending` review record would still be created/reused against evidence that is no longer actually pending review. The downstream `update_review_decision` propagation guard (its own `"status": "pending_review"` re-check, lines 224-233) prevents this from corrupting the evidence record itself, but it does mean an orphaned review record can end up "decided" with no corresponding evidence-status change and only a server-side `logger.warning` (never surfaced to any user) marking the discrepancy.
**Fix:** This is a narrow window and the downstream guard limits the blast radius, but for full correctness the validation should be folded into the same atomic operation, e.g. by re-reading evidence status inside a transaction, or by having the upsert's `$setOnInsert` path itself fail/no-op when evidence isn't pending_review (requires a multi-document transaction since `asset_compliance` and `evidence_reviews` are separate collections). At minimum, document the residual race explicitly next to the existing docstring, since the current docstring implies the check fully prevents this ("Validates the evidence item exists ... and is currently in 'pending_review' status before inserting").

### WR-03: A non-string `detail` from a pydantic validation error (e.g. comment exceeding 2000 chars) crashes the toast renderer instead of showing a message

**File:** `components/EvidenceReviewPanel.tsx:93,100,183-189`; confirmed via `components/ToastContainer.tsx:50`
**Issue:** The comment `<textarea>` (lines 183-189) has no `maxLength` attribute, but the backend's `CreateReviewRequest.comment` and `UpdateDecisionRequest.comment` are capped at `max_length=2000` (`evidence_review_endpoints.py:43,48`). If a user pastes more than 2000 characters and submits, FastAPI's automatic request-validation handler returns a 422 whose `detail` is an **array** of error objects (`[{"type": ..., "loc": ..., "msg": ...}]`), not a string. `handleReviewDecision`'s error paths do:
```tsx
const d = await reviewRes.json().catch(() => ({}));
showToast(d.detail || 'Failed to create review', 'error');
```
`d.detail` here is an array, which is truthy, so it gets passed directly as `showToast`'s `message` argument (typed `string`, but `d` is untyped `any` so TypeScript doesn't catch the mismatch). `ToastContainer.tsx:50` renders `{toast.message}` directly as a JSX child — passing an array of plain objects there causes React to throw ("Objects are not valid as a React child"), crashing the toast instead of showing any error message to the user.
**Fix:** Add client-side `maxLength={2000}` to the textarea to prevent the condition in the common case, and harden the error-extraction helper to only use `detail` when it's actually a string:
```tsx
const detail = typeof d.detail === 'string' ? d.detail : 'Failed to create review';
showToast(detail, 'error');
```

### WR-04: `mock.patch` is started but never stopped in every test, leaking the mocked `get_database` into the module for the rest of the pytest session

**File:** `backend/tests/test_evidence_review.py:74-76`
**Issue:** `_build_client()` is called by all 12 tests in this file and does:
```python
patcher = patch("evidence_review_endpoints.get_database", return_value=mock_db)
patcher.start()
return TestClient(app, raise_server_exceptions=False)
```
`patcher.stop()` is never called (no corresponding cleanup, no `try/finally`, no pytest fixture with `yield` + teardown, no `addCleanup`). Each `patch(...).start()` call replaces `evidence_review_endpoints.get_database` again but never restores the previous value, so after this test module runs, `evidence_review_endpoints.get_database` remains permanently monkey-patched to the *last* test's `mock_db` for the remainder of the pytest process — including any other test file that runs afterward in the same session and imports/exercises `evidence_review_endpoints` expecting the real function.
**Fix:** Use `patch(...)` as a context manager or fixture with guaranteed teardown:
```python
def _build_client(mock_db, current_user):
    ...
    patcher = patch("evidence_review_endpoints.get_database", return_value=mock_db)
    patcher.start()
    client = TestClient(app, raise_server_exceptions=False)
    client.addCleanup = None  # TestClient has no addCleanup; use a fixture instead
    return client, patcher  # caller must call patcher.stop()
```
or, more idiomatically, convert `_build_client` into a pytest fixture that does `patcher.start()` then `yield client` then `patcher.stop()` in a `finally`/generator-teardown block.

## Info

### IN-01: Reviewer-role list is duplicated between frontend and backend with no shared source of truth

**File:** `components/EvidenceReviewPanel.tsx:8` (`_REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer']`) vs. `backend/evidence_review_endpoints.py:36` (`_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer"}`)
**Issue:** Both lists are hand-maintained independently. The backend value is authoritative (enforced via 403), so this isn't a security gap, but if the backend's reviewer-role set changes and the frontend copy isn't updated in lockstep, the UI will silently under- or over-show the Approve/Reject/Request-Changes controls relative to what the server will actually allow, producing either a hidden-but-available action or a visible-but-guaranteed-403 action.
**Fix:** Not urgent, but consider exposing the reviewer-role set via a config/whoami endpoint or a shared constants module (if the frontend/backend already share any generated types) rather than two independently maintained literals.

### IN-02: `rv.status.replace('_', ' ')` only replaces the first underscore, not all of them

**File:** `components/EvidenceReviewPanel.tsx:160`
**Issue:** `String.prototype.replace` with a string (non-regex) argument only replaces the first match. Every status value currently in use (`approved`, `rejected`, `changes_requested`, `pending`) has at most one underscore, so this doesn't currently produce a visibly wrong label, but it's a latent bug the moment a status with two or more underscores is introduced (e.g. a future `needs_more_evidence`).
**Fix:** `rv.status.replace(/_/g, ' ')`.

---

_Reviewed: 2026-07-02T08:04:38Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
