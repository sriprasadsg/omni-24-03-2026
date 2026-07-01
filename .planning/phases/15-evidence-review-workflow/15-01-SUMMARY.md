---
phase: 15-evidence-review-workflow
plan: 01
subsystem: compliance
tags: [fastapi, mongodb, motor, react, evidence-review, rbac]

requires:
  - phase: 08-bulk-evidence-upload
    provides: control_evidence collection and evidence upload lifecycle this phase reviews
provides:
  - Per-evidence approval/reject/request-changes workflow with comment thread
  - evidence_reviews MongoDB collection tracking review decisions per tenant
  - Role-gated review decisions (admin / super_admin / compliance_reviewer)
affects: [09-compliance-score-dashboard]

tech-stack:
  added: []
  patterns:
    - "Review lifecycle state machine: draft/needs_revision -> pending_review -> approved|rejected|needs_revision"
    - "Tenant-scoped Mongo queries on every read/write (tenantId filter required on every collection access)"

key-files:
  created:
    - backend/evidence_review_service.py
    - backend/evidence_review_endpoints.py
    - backend/tests/test_evidence_review.py
    - components/EvidenceReviewPanel.tsx
  modified:
    - backend/router_registry.py
    - types.ts
    - components/AssetComplianceList.tsx

key-decisions:
  - "Evidence review stored in separate evidence_reviews collection (supports multiple reviews per evidence item over time)"
  - "Evidence status tracked inline on asset_compliance.evidence[].status via positional $ operator, not denormalized elsewhere"
  - "Comment required for rejected/changes_requested decisions (422 if missing)"
  - "Frontend: colocated review panel within evidence entry row (not modal) for UX flow"

patterns-established:
  - "Pattern: every service function scoped to tenant_id as an explicit parameter, not inferred implicitly — CR-01 fix made this uniform across update_review_decision() to match the rest of the module"

requirements-completed: [REV-01, REV-02, REV-03]

# Metrics
duration: ~22min (original implementation) + review/fix cycle
completed: 2026-07-02
status: complete
---

# Phase 15: Evidence Review Workflow Summary

**Per-evidence approval/reject/request-changes workflow with tenant-scoped review records in a dedicated `evidence_reviews` collection, role-gated to admin/super_admin/compliance_reviewer**

## Performance

- **Duration:** ~22 min original implementation (2026-06-27), plus a code-review + fix + UAT cycle on 2026-07-02
- **Started:** 2026-06-27T12:41:00Z (approx, from file mtimes — this SUMMARY was authored retroactively; see Issues Encountered)
- **Completed:** 2026-07-02T00:05:00Z (UAT sign-off)
- **Tasks:** 6 (per original `.continue-here.md` task tracking)
- **Files modified:** 7

## Accomplishments
- POST `/api/evidence/{evidence_id}/submit-for-review` — sets evidence status to `pending_review`, guarded to only fire from unset/`needs_revision`/`rejected` states
- POST `/api/evidence/{evidence_id}/review` — creates a review record; validates the evidence item exists for the caller's tenant before inserting
- PATCH `/api/evidence/{evidence_id}/review/{review_id}` — approve/reject/request-changes, tenant-scoped, comment required for non-approved decisions, `evidence_id` validated against the review's actual `evidenceId`
- GET `/api/evidence/{evidence_id}/reviews` — review thread sorted newest-first
- GET `/api/evidence/pending-review` — tenant's pending-review queue, correctly sorted (fixed post-review — see below)
- `EvidenceReviewPanel.tsx` — review thread, status badges, role-gated action buttons, comment textarea, wired into `AssetComplianceList.tsx`
- 8/8 unit tests in `test_evidence_review.py` passing

## Files Created/Modified
- `backend/evidence_review_service.py` - review lifecycle logic: submit, create, update decision, list, list pending
- `backend/evidence_review_endpoints.py` - FastAPI router mounted at `/api/evidence` (review sub-routes)
- `backend/tests/test_evidence_review.py` - 8-test TDD suite
- `backend/router_registry.py` - registers `evidence_review_endpoints` router
- `types.ts` - `AssetComplianceEvidence.status` field
- `components/EvidenceReviewPanel.tsx` - review thread UI
- `components/AssetComplianceList.tsx` - wires `EvidenceReviewPanel` into each evidence entry

## Decisions Made
- Evidence review stored in a separate `evidence_reviews` collection rather than embedded in `asset_compliance`, to support multiple review rounds per evidence item without growing the parent document unboundedly
- Evidence's live review status tracked inline via `asset_compliance.evidence[].status` (positional `$` operator) so existing evidence-list UI needs no schema migration
- Comment is mandatory for `rejected` / `changes_requested` decisions (422 if blank), optional for `approved`
- Frontend review panel is colocated in the evidence row rather than a modal, to keep the review thread visible alongside the evidence file itself

## Deviations from Plan

### Auto-fixed Issues (found in post-hoc code review, 2026-07-02)

**1. [Critical] Cross-tenant IDOR in `update_review_decision`**
- **Found during:** `/gsd-code-review 15` (quick depth)
- **Issue:** The review-decision update path filtered only by `{"id": review_id}` (and evidence propagation only by `{"evidence.id": evidence_id}`) with no `tenantId` scoping, unlike every other function in the module. Any reviewer-role user in any tenant could approve/reject a different tenant's evidence review.
- **Fix:** Added a required `tenant_id` parameter, applied to both the review lookup and the evidence-status propagation query; threaded `current_user.tenant_id` through from the endpoint.
- **Files modified:** `backend/evidence_review_service.py`, `backend/evidence_review_endpoints.py`
- **Verification:** UAT test 8 (cross-tenant review isolation) passed after fix.
- **Committed in:** `56be785`

**2. [Critical] `EvidenceReviewPanel.tsx` made unauthenticated requests**
- **Found during:** `/gsd-code-review 15`
- **Issue:** All network calls used raw browser `fetch()` instead of the project's `authFetch()` helper, so no `Authorization` header was ever sent — every request 401'd against the backend's `OAuth2PasswordBearer` dependency. The panel was non-functional as originally shipped.
- **Fix:** Replaced all four `fetch()` calls with `authFetch()` from `services/apiService.ts`.
- **Files modified:** `components/EvidenceReviewPanel.tsx`
- **Verification:** UAT test 2 passed after fix.
- **Committed in:** `168a94e`

**3. [Warning] `get_pending_evidence` aggregation sort was a no-op**
- **Issue:** `$sort` on `evidence.review_updated_at` ran after a `$project` stage that had already dropped that field, so "newest first" ordering silently didn't happen.
- **Fix:** Reordered the pipeline so `$sort` runs before `$project`.
- **Committed in:** `6bdeeb4`

**4. [Warning] PATCH endpoint ignored the `evidence_id` path parameter**
- **Fix:** Added a check that `review.evidenceId == evidence_id` after lookup, returning 404 on mismatch.
- **Committed in:** `67854fc`

**5. [Warning] Missing lifecycle-state guards**
- **Fix:** `submit_for_review` now requires the evidence be in an unset/`needs_revision`/`rejected` state; `create_review` now validates the evidence exists for the tenant before inserting a review record.
- **Committed in:** `594f362`

**6. [Warning] Unhandled `ValueError` surfaced as raw 500**
- **Fix:** Wrapped the `update_review_decision` call with `try/except ValueError` -> `HTTPException(422)`.
- **Committed in:** `15e824e`

**7. [Warning] Broken test mocks masked all of the above from CI**
- **Found during:** post-fix `pytest` run still showed 6/8 tests failing
- **Issue:** Three independent mock/API mismatches in `test_evidence_review.py` (subscript vs. attribute access on the mock DB, a missing `find_one` stub, and `aggregate` mocked as async when the real Motor call is sync-returning-a-cursor) meant the test suite had likely never actually gone green, regardless of code correctness.
- **Fix:** Corrected all three mock configurations to match actual Motor/FastAPI call patterns.
- **Files modified:** `backend/tests/test_evidence_review.py`
- **Verification:** `pytest backend/tests/test_evidence_review.py` — 8 passed
- **Committed in:** `baf484e`

---

**Total deviations:** 7 (2 critical security/functional, 4 warning-level correctness, 1 test-infrastructure). None were scope creep — all were fixes to what the plan already specified.
**Impact on plan:** Plan's core design (review lifecycle, tenant-scoped collection, role gating) was sound; the deviations were implementation bugs caught by review rather than design gaps.

## Issues Encountered

- **No dedicated phase-15 commit exists.** All phase 15 files (implementation, plus the fix commits above) landed as part of git history alongside phase 16/17 work — the original implementation was folded into commits labeled `feat(phase-16): implement program control grouping` (`e52393a`, `692dfdc`) rather than a phase-15-labeled commit. This meant `/gsd-code-review 15`'s git-diff file-scoping tier failed and had to fall back to an explicit `--files` list, and this SUMMARY.md itself was authored retroactively on 2026-07-02 (rather than by `/gsd-execute-phase` at implementation time) to unblock `/gsd-secure-phase`.
- **REV-01/REV-02/REV-03 were never added to `.planning/REQUIREMENTS.md`** — they appear in ROADMAP.md and this plan's frontmatter but have no corresponding entry or traceability row in REQUIREMENTS.md. Worth a follow-up requirements-doc pass.
- Python test runner is blocked by the permission classifier when invoked via the Claude Bash tool in this environment — tests had to be run with a `!`-prefixed (user-invoked) shell command per `.continue-here.md`'s documented workaround.

## Next Phase Readiness

- Evidence review workflow is functionally complete, security-reviewed, and passes an 8-test UAT script covering the full approve/reject/request-changes lifecycle plus the two critical fixes (auth, tenant isolation).
- Phase 9 (compliance-score-dashboard) should confirm whether `approved` review status is actually consumed by the score calculation — the phase 15 plan's objective states approved evidence "counts toward compliance score," but that integration point wasn't verified as part of this phase.
- Recommend a follow-up pass to add REV-01/02/03 to REQUIREMENTS.md for traceability.

---
*Phase: 15-evidence-review-workflow*
*Completed: 2026-07-02*
