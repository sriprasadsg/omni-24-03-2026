---
phase: 15-evidence-review-workflow
fixed_at: 2026-07-03T09:15:00Z
review_path: .planning/phases/15-evidence-review-workflow/15-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-07-03T09:15:00Z
**Source review:** .planning/phases/15-evidence-review-workflow/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (1 Critical + 4 Warning + 2 Info; `fix_scope: all`)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: `evidence_reviews` collection bypasses the tenant-isolation wrapper used everywhere else in this file

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commit:** `0e25a5e`
**Applied fix:** Changed all three raw `db._db[_EVIDENCE_REVIEWS_COL]` accesses (in `create_review`, `update_review_decision`, `get_reviews`) to the wrapped subscript accessor `db[_EVIDENCE_REVIEWS_COL]`, exactly as the review suggested — `TenantIsolatedDatabase.__getitem__` already wraps non-exempt collection names in `TenantIsolatedCollection`, so `evidence_reviews` now gets the same automatic `tenantId`-overwrite / fail-closed protection as `asset_compliance` and `audit_logs` in this file. Updated `_make_mock_db()` in the test file to wire `db.__getitem__` (the outer mock standing in for `TenantIsolatedDatabase`) to the same `evidence_reviews` mock object the assertions reference, and added `__getitem__` to the live-Mongo regression test's `_RealDbWrapper` shim (it previously only exposed `._db`, which would have broken under the new access pattern). Full suite (19 tests, including the new WR-01/WR-02/WR-03 tests added below) passes.

### WR-01: `create_review` silently discards a concurrent reviewer's comment, not just a retried request's

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commit:** `ce505ca`
**Applied fix:** After the atomic `find_one_and_update` upsert, `create_review` now compares the returned record's `reviewer` field against the calling `reviewer`. When they differ (a different reviewer already has a pending review open on the same evidence item), the returned dict gets an additional `already_open_by: <reviewer>` key — computed only in the response, never persisted — so the endpoint/frontend can distinguish "created/reused-by-you" from "reused-from-a-different-reviewer" instead of identical 200 success semantics. Added `test_create_review_flags_already_open_by_different_reviewer` (asserts the flag appears with the correct value and that the new caller's comment was never persisted) and extended the existing same-caller-retry test to assert the flag is absent in that case.

### WR-02: comment-required rule for `rejected`/`changes_requested` is enforced only at the API boundary, not inside the service function

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commit:** `9fe3b57`
**Applied fix:** Added `if requires_comment(decision) and not (comment or "").strip(): raise ValueError(...)` inside `update_review_decision` itself, right after decision validation — the endpoint's existing `except ValueError` handler already maps this to 422, so no endpoint change was needed. The invariant now holds regardless of caller (script, future endpoint, reordered check), matching what the function's docstring already claimed. Added `test_update_review_decision_rejects_empty_comment_at_service_layer`, which calls the service function directly (bypassing the endpoint) for both `rejected` and `changes_requested` with a whitespace-only comment and asserts `ValueError` is raised with zero mutation.

### WR-03: a stale/duplicate review decision returns `200 success` even though the evidence's status was never actually changed

**Files modified:** `backend/evidence_review_service.py`, `backend/tests/test_evidence_review.py`
**Commit:** `a974488`
**Applied fix:** `update_review_decision` now returns `{**review, "evidence_updated": result.modified_count > 0}` instead of the bare review dict, so the caller (and eventually the UI) can distinguish "decision fully applied" from "decision recorded on an orphaned review, evidence status unchanged" — matching the review's suggested fix exactly. Added `test_update_review_decision_flags_evidence_updated_false_on_stale_review` (mocks `asset_compliance.update_one` to return `modified_count=0` and asserts the response's `review.evidence_updated` is `False`) and a happy-path companion asserting `True` on normal success.

### WR-04: `evidence_review_endpoints` is excluded from `_REQUIRED_ROUTERS` despite belonging to the same evidence-lifecycle feature set as routers that are required

**Files modified:** `backend/router_registry.py`
**Commit:** `1f600cc`
**Applied fix:** Added `"evidence_review_endpoints"` to `_REQUIRED_ROUTERS`, consistent with its sibling evidence routers (`compliance_evidence_lifecycle_endpoints`, `compliance_bulk_evidence_endpoints`, `compliance_score_endpoints`) — a broken import for this router now aborts startup instead of silently starting the app with the entire review/approve/reject workflow absent. Verified by importing `router_registry` directly and confirming `evidence_review_endpoints` is present in the resulting `_REQUIRED_ROUTERS` frozenset.

### IN-01: reviewer role list duplicated between backend and frontend with no shared source of truth

**Files modified:** `backend/evidence_review_endpoints.py`, `components/EvidenceReviewPanel.tsx`
**Commit:** `9e12f8c`
**Applied fix:** Added explicit cross-referencing comments above each `_REVIEWER_ROLES` literal, pointing at the other file/line and stating that any change to one must be mirrored in the other. Scoping note: the review's primary suggestion (a shared constants module or an `/api/config`-style endpoint returning the role list) would require introducing a new cross-language shared source — no such module or endpoint already exists in this codebase, and creating one is a larger architectural change than is appropriate for an Info-severity finding in a review-fix pass (per this project's CLAUDE.md constraint against creating new files/endpoints unless necessary). The documented-sync comments are a proportionate mitigation: they don't eliminate the drift risk, but make it discoverable to any future editor of either file. This is a partial fix relative to the review's stated ideal; the shared-source approach remains available as a follow-up if this drift risk needs to be closed more fully.

### IN-02: `any`-typed error handling in `EvidenceReviewPanel.tsx`

**Files modified:** `components/EvidenceReviewPanel.tsx`
**Commit:** `6c6130c`
**Applied fix:** Changed `_errorDetail`'s parameter from `d: any` to `d: unknown`, narrowing via a cast-then-optional-chain (`(d as { detail?: unknown } | null | undefined)?.detail`) before the existing `typeof detail === 'string'` check, rather than accessing a property directly on `unknown` (which TypeScript disallows). Changed all three `catch (err: any)` blocks (in `fetchReviews`, `handleSubmitForReview`, `handleReviewDecision`) to `catch (err: unknown)` paired with `err instanceof Error ? err.message : '<fallback>'`, matching the review's suggested pattern exactly. Verified no `any` remains in the file (`grep -n ": any\|<any>\|as any"` returns no matches). No local TypeScript compiler was available in this environment (no `node_modules`/`tsc`), so verification fell back to Tier 1 (re-read of all four modified sites, confirming correct syntax and intact surrounding code) per the verification strategy's Tier 3 fallback.

## Skipped Issues

None — all 7 in-scope findings were fixed.

---

_Fixed: 2026-07-03T09:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
