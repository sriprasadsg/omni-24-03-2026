---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-02T08:15:01Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 6
skipped: 1
status: partial
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-02T08:15:01Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7
- Fixed: 6
- Skipped: 1

## Fixed Issues

### CR-01: `_id` (a raw `bson.ObjectId`) is never stripped from Mongo documents before they're returned from the API

**Files modified:** `backend/evidence_review_service.py`
**Commit:** 5f461a4
**Applied fix:** Added `projection={"_id": 0}` to the `find_one_and_update` calls in `create_review` and `update_review_decision`, added `{"_id": 0}` as the projection argument to the `find()` call in `get_reviews`, and added `"_id": 0` to the `$project` aggregation stage in `get_pending_evidence`. This is Option A from the review (project `_id` out at the query level), applied consistently across all four document-returning functions so no raw `bson.ObjectId` ever reaches the API/JSON-encoding boundary.

### WR-01: A review's `reviewer` field is fixed at creation time and never updated at decision time

**Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
**Commit:** f0ca5a3
**Applied fix:** Added a `decided_by: str | None = None` parameter to `update_review_decision`, set via `$set` on the review document at decision time, and wired `current_user.username` through from the PATCH endpoint (`evidence_review_endpoints.py`). The `reviewer` field itself is left untouched (still records who opened the thread) per the review's suggested "add a `decided_by` field" option, rather than overwriting `reviewer`'s original semantics.
**Note:** `components/EvidenceReviewPanel.tsx` still renders `rv.reviewer` in the review thread and was not changed to also surface `decided_by` — the review's own code snippet only covered the backend change. **Status: fixed: requires human verification** — a developer should confirm whether the frontend also needs a follow-up to display `decided_by` for the misattribution to be fully resolved from a user-visible standpoint.

### WR-02: `create_review`'s evidence-status validation is check-then-act, not atomic

**Files modified:** `backend/evidence_review_service.py`
**Commit:** f28f797
**Applied fix:** Per the review's own guidance ("at minimum, document the residual race explicitly next to the existing docstring"), added an explicit "KNOWN RESIDUAL RACE (WR-02)" section to `create_review`'s docstring describing the check-then-act window, why the blast radius is limited (the downstream atomic re-check in `update_review_decision`), and what a full fix would require (a cross-collection transaction). No behavioral/logic change was made — the review explicitly frames this as "narrow" and full remediation as optional given the existing downstream guard.

### WR-03: A non-string `detail` from a pydantic validation error crashes the toast renderer

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** 7975d71
**Applied fix:** Added a `_errorDetail(d, fallback)` helper that only returns `d.detail` when it is actually a `string`, otherwise returns the fallback message; replaced all three `d.detail || 'fallback'` call sites (`handleSubmitForReview`, and both error branches in `handleReviewDecision`) with `_errorDetail(d, 'fallback')`. Also added `maxLength={2000}` to the comment `<textarea>` to prevent the 422-with-array-detail condition from being triggered in the common case, matching the backend's `max_length=2000` cap.

### WR-04: `mock.patch` is started but never stopped in every test

**Files modified:** `backend/tests/test_evidence_review.py`
**Commit:** 61ed400
**Applied fix:** Added a module-level `_active_patchers` list that `_build_client` appends each started patcher to, plus an `@pytest.fixture(autouse=True)` `_stop_patchers` fixture that stops every active patcher after each test (success or failure), guaranteeing teardown without needing to touch all 12 existing test-function call sites. Also fixed a test regression surfaced by the CR-01 fix: `test_tenant_isolation_get_excludes_cross_tenant_reviews`'s `_find_side_effect` mock only accepted one positional argument, but the CR-01 fix now calls `.find(query, {"_id": 0})` with a second positional projection argument — updated the mock signature to `_find_side_effect(query, *args, **kwargs)`. Verified: all 14 tests in `backend/tests/test_evidence_review.py` pass after both changes (`python3 -m pytest tests/test_evidence_review.py -q` → `14 passed`).

### IN-02: `rv.status.replace('_', ' ')` only replaces the first underscore

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** 7eb0cb7
**Applied fix:** Changed `rv.status.replace('_', ' ')` to `rv.status.replace(/_/g, ' ')` exactly as suggested in the review.

## Skipped Issues

### IN-01: Reviewer-role list is duplicated between frontend and backend with no shared source of truth

**File:** `components/EvidenceReviewPanel.tsx:8`, `backend/evidence_review_endpoints.py:36`
**Reason:** The review itself frames this as "not urgent" and offers only a prose suggestion ("consider exposing the reviewer-role set via a config/whoami endpoint or a shared constants module"), not a concrete patch. I checked the codebase for an existing shared-constants or config/whoami pattern between the Python backend and TypeScript frontend and found none (no `shared/` directory, no generated-types bridge, no whoami-style config endpoint). Introducing one is an architectural decision (new API surface or a cross-runtime build-time shared-constants mechanism) that goes beyond a narrow, safe code fix and risks touching unrelated infrastructure. Per critical_rules ("DO NOT modify files unrelated to the finding — scope each fix narrowly" and "DO NOT create new files unless the fix explicitly requires it"), this was left for a human to design and implement deliberately.
**Original issue:** Both `_REVIEWER_ROLES` lists (frontend array, backend set) are hand-maintained independently; the backend value is authoritative (enforced via 403), so this is not a security gap, but the two copies can drift out of sync, producing either a hidden-but-available action or a visible-but-guaranteed-403 action in the UI.

---

_Fixed: 2026-07-02T08:15:01Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
