---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-01T22:51:42Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 3
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-01T22:51:42Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 3

**Summary:**
- Findings in scope: 3 (1 Critical + 0 Warning + 2 Info; `fix_scope: all`)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### CR-01: Evidence-status propagation query is missing `$elemMatch`, allowing a decision to silently corrupt a *different* evidence item's status in the same document

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commits:** `7576fdf` (core fix), `ba89cc0` (regression test)
**Applied fix:** Rewrote the filter in `update_review_decision`'s evidence-status-propagation `update_one(...)` call to use `"evidence": {"$elemMatch": {"id": evidence_id, "status": "pending_review"}}` instead of the two independent top-level conditions `"evidence.id": evidence_id` / `"evidence.status": "pending_review"`, matching the pattern already used by `submit_for_review` in the same file and `approval_service.py:74-79`. This guarantees both conditions are evaluated against the *same* array element, so the positional `$` operator can no longer resolve to an unrelated evidence item.

**Empirical verification (live MongoDB, not just static reasoning):** Started a real `mongod` (v8.x) instance locally. Reproduced the exact bug first: seeded an `asset_compliance` document with `evidence: [{id: "ev-1", status: "needs_revision"}, {id: "ev-2", status: "pending_review"}]`, ran the *pre-fix* query targeting `ev-1`, and confirmed `ev-2` silently flipped to `approved` while `matched_count`/`modified_count` both reported `1` (no error surfaced). Applied the fix, re-ran the identical scenario, and confirmed `matched_count`/`modified_count` correctly came back `0`, neither evidence item was touched, and the existing `logger.warning(...)` branch fires as intended. Also confirmed the fixed query still correctly updates the *right* element when it genuinely is the target (`ev-2` pending_review, decided against `ev-2` — updates as expected, `ev-1` untouched).

Also added a regression test (`test_evidence_propagation_query_does_not_corrupt_unrelated_evidence_item` in `backend/tests/test_evidence_review.py`) per the review's recommendation, since the existing mock-based tests structurally cannot catch a query-*shape* bug (the mock unconditionally returns `modified_count=1` regardless of the filter passed in). The new test runs the real `update_review_decision` service function against a live MongoDB instance (connects via `MONGODB_URI`/`MONGO_URI` env var, defaulting to `mongodb://localhost:27017`; skips gracefully via `pytest.skip` if no Mongo is reachable), seeds the same two-evidence-item document, and asserts `ev-2` is never touched by a decision made against `ev-1`. Verified the test's discriminating power directly: temporarily reverted the source file to the pre-fix query and confirmed the new test **fails** with `AssertionError: CR-01 regression: ev-2 was corrupted...`; restored the fix and confirmed it **passes**. Full suite: `pytest backend/tests/test_evidence_review.py` — **14/14 passed** (13 pre-existing + 1 new).

### IN-01: Stale comment and dead mock in test fixture no longer match the current `create_review` implementation

**Files modified:** `backend/tests/test_evidence_review.py`
**Commit:** `b78591a`
**Applied fix:** Removed the unused `inner.evidence_reviews.find_one = AsyncMock(return_value=None)` line and its stale "backs `create_review()`'s dedup guard (CR-01)" comment from `_make_mock_db()`. Confirmed no test in the file references `evidence_reviews.find_one` (the dedup guard is fully implemented via `find_one_and_update(..., upsert=True)`, mocked separately a few lines below). Full suite re-run after removal: 14/14 passed.

### IN-02: `create_review`'s "not pending review" error message can render as "current status: None" instead of a human-readable state

**Files modified:** `backend/evidence_review_service.py`
**Commit:** `e82b8da`
**Applied fix:** The current code already had `current_status = evidence_item.get("status") if evidence_item else "unknown"` (a prior partial fix handling the missing-evidence-item case), but the leaked-`None` case the reviewer flagged — an existing evidence item whose `status` key was never set — was still open, since `evidence_item.get("status")` returns `None` and that flowed straight into the f-string. Adapted the review's suggested fix to preserve the existing "unknown" (missing item) branch while adding an `or "unset"` fallback for the None-status-but-item-exists case: `current_status = (evidence_item.get("status") or "unset") if evidence_item else "unknown"`. Verified directly: calling `create_review` against an evidence item with no `status` key now raises `ValueError("Evidence 'ev-1' is not pending review (current status: unset)")` instead of `"... (current status: None)"`. Full suite: 14/14 passed.

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-07-01T22:51:42Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 3_
