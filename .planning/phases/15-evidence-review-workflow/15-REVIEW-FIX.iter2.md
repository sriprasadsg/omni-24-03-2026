---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-02T00:00:00Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-02T00:00:00Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (1 Critical + 1 Warning + 1 Info; `fix_scope: all`)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### CR-01: Orphaned "pending" review records can later be decided and silently corrupt evidence status without resubmission

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commit:** `3b82e42`
**Applied fix:** Closed both gaps identified in the finding:
- `update_review_decision`'s evidence-propagation `update_one(...)` filter now additionally requires `"evidence.status": "pending_review"`, so a stale/orphaned review record can no longer overwrite evidence that has since moved to a different status without the evidence being resubmitted for review. When the filter doesn't match (`modified_count == 0`), a `logger.warning(...)` records the review id, decision, evidence id, and tenant id so the discrepancy is observable instead of silently swallowed.
- `create_review` now checks for an existing `status: "pending"` review record for the same `evidenceId`/`tenantId` before inserting, and returns the existing record instead of creating a duplicate — closing the root cause that allowed multiple independent "pending" threads to accumulate against the same evidence item.
- Updated the shared mock DB fixture (`_make_mock_db`) in `test_evidence_review.py` to stub `evidence_reviews.find_one` (returns `None` by default, i.e. no existing pending review), since `create_review`'s new dedup guard calls it — without this stub the existing `test_create_review_record` test failed with a 500 (awaiting a non-async `MagicMock`). All 10 pre-existing tests pass after this change.

### WR-01: No regression test exercises the exact evidence-id-mismatch-within-same-tenant path that caused the prior CR-01

**Files modified:** `backend/tests/test_evidence_review.py`
**Commit:** `af576f1`
**Applied fix:** Added `test_evidence_id_mismatch_same_tenant_returns_404_without_mutation`, adapted directly from the review's suggested fix. It mocks `find_one_and_update` to only match when `evidenceId == "ev-1"`, then PATCHes `/api/evidence/ev-WRONG/review/rev-abc` (same tenant, mismatched evidence id) and asserts a `404` response with `db.audit_logs.insert_one.assert_not_awaited()` — confirming zero side effects on a mismatch. All 11 tests (10 pre-existing + 1 net-new) pass.

### IN-01: Unused `Optional` import remains in both service and endpoint modules

**Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
**Commit:** `c1acfad`
**Applied fix:** Removed the unused `from typing import Optional` line from both files. Confirmed no other reference to `Optional` remains in either file (both consistently use PEP 604 `X | None` syntax). Syntax-checked both files and re-ran the full test suite (11/11 pass) after removal.

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-07-02T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
