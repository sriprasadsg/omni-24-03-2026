---
phase: 42-comment-threads-on-compliance-controls
plan: 01
subsystem: api
tags: [fastapi, mongodb, motor, pytest, tenant-isolation, rbac]

# Dependency graph
requires:
  - phase: 15-evidence-review-workflow
    provides: role-gate + rate-limit + mock-db TestClient conventions cloned for this plan (evidence_review_endpoints.py / test_evidence_review.py)
provides:
  - "control_comments collection (MongoDB, tenant-isolated via default TenantIsolatedCollection path)"
  - "control_comments_service.add_comment/list_comments"
  - "control_comments_endpoints.router (POST/GET /api/control-comments), registered in router_registry.py"
affects: [42-02, 42-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dedicated tenant-scoped collection instead of $push onto a shared/exempt parent document, for any future comment-like/append-only resource"
    - "D-03-style immutability enforced purely by omission (no PATCH/DELETE route ever written)"

key-files:
  created:
    - backend/control_comments_service.py
    - backend/control_comments_endpoints.py
    - backend/tests/test_control_comments.py
  modified:
    - backend/router_registry.py

key-decisions:
  - "42-01: control_comments is a brand-new dedicated collection, deliberately absent from database.py's tenant-isolation exemption allowlists, so every read/write is auto-scoped by TenantIsolatedCollection with no manual tenantId filter in the service"
  - "42-01: GET /api/control-comments is open to any authenticated tenant user (A2) — only POST is role-gated to admin/super_admin/compliance_reviewer (D-01)"
  - "42-01: no PATCH/DELETE route exists for control comments — D-03 immutability enforced by omission, not by a DB-level guard"

patterns-established:
  - "Comment-thread services store one document per comment in a dedicated collection, never array-append onto a shared parent document (anti-pattern seen in tickets_service.py)"

requirements-completed: [CMT-01]

# Metrics
duration: ~20min
completed: 2026-07-21
status: complete
---

# Phase 42 Plan 01: Comment Threads Backend Core Summary

**Tenant-scoped `control_comments` collection with role-gated POST / open GET routes, registered in the live app router.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-21T08:17:19Z
- **Tasks:** 3
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments
- New `control_comments_service.py` — `add_comment`/`list_comments` against a dedicated `control_comments` collection, never touching the shared/exempt controls document and never using array-append onto a parent doc.
- New `control_comments_endpoints.py` — role-gated (`admin`/`super_admin`/`compliance_reviewer`, D-01) + rate-limited (`30/minute`) `POST /api/control-comments`, and an open `GET /api/control-comments` for any authenticated tenant user (A2). No PATCH/DELETE route (D-03 immutability by omission).
- Router registered in `router_registry.py` immediately after `evidence_review_endpoints` — confirmed resolving in the live `FastAPI` app (`_fastapi_app.routes` contains both `/api/control-comments` paths, not 404).
- 3 hermetic unit tests (`test_non_author_role_forbidden`, `test_post_and_list_comment`, `test_tenant_isolation`) cloning `test_evidence_review.py`'s mock-db + `dependency_overrides` convention; RED confirmed before implementation, GREEN after.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing backend unit tests (Wave 0 scaffold)** - `cbb863e` (test)
2. **Task 2: Implement control_comments_service.py** - `7b6ce15` (feat)
3. **Task 3: Implement role-gated endpoints and register router** - `6f9a5a3` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `backend/control_comments_service.py` - `add_comment(db, control_id, author, text)` / `list_comments(db, control_id)` against `db.control_comments` only
- `backend/control_comments_endpoints.py` - `router`, `post_control_comment`, `get_control_comments`, `CreateCommentRequest`, `_COMMENT_AUTHOR_ROLES`
- `backend/tests/test_control_comments.py` - role-gate 403, post+list persistence, tenant-isolation coverage
- `backend/router_registry.py` - added `_load(app, "control_comments_endpoints", "router")` after `evidence_review_endpoints`

## Decisions Made
- `control_comments` deliberately left out of `database.py`'s two exemption allowlists so the existing `TenantIsolatedCollection` wrapper does all tenant scoping automatically — no manual `tenantId` filtering added in the service, matching the plan's instruction and the pattern map's tenant-isolation guidance.
- `insert_one` is called with a fresh `dict(comment)` copy (not the same reference returned to the caller) so that pymongo's real in-place `_id` mutation of the inserted document never leaks into the returned/response payload.
- Test 3 (`test_tenant_isolation`) asserts the structural guarantee (endpoint obtains its db handle exclusively via `get_database()`; neither service nor endpoints reference `compliance_controls`) plus a functional check that separate tenant-scoped mock DB instances never bleed into each other's GET results — mirroring how `get_database()` returns a per-request tenant-scoped handle in production; this plan intentionally does not fabricate a live two-tenant Mongo test since the isolation guarantee is delegated entirely to the already-covered `TenantIsolatedCollection` wrapper.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring literal tripped the plan's own `grep -c 'compliance_controls'` acceptance check**
- **Found during:** Task 2 (control_comments_service.py implementation)
- **Issue:** The module docstring explaining "not appended onto the shared compliance_controls document" contained the literal string `compliance_controls`, which the plan's acceptance criterion `grep -c 'compliance_controls' backend/control_comments_service.py` (expected 0) would flag as a false positive — the intent of that check is "the service never references the shared collection in code," not "the string never appears in prose."
- **Fix:** Reworded the docstring to describe the same constraint without using the literal collection name (now reads "any shared/tenant-exempt controls document").
- **Files modified:** `backend/control_comments_service.py`
- **Verification:** `grep -c 'compliance_controls' backend/control_comments_service.py` now returns `0`; module still imports and exposes `add_comment`/`list_comments`.
- **Committed in:** `7b6ce15` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Cosmetic-only fix to satisfy the plan's own automated acceptance grep; no behavior change.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Backend core (service + endpoints + router registration) for control comments is complete and verified live in the app. Full backend suite run: 1311 passed / 34 skipped / 7 failed — all 7 failures reproduce identically on the clean tree with this plan's changes stashed (confirmed via `git stash -u` before/after comparison), i.e. pre-existing and unrelated: `test_log_heartbeat.py`, `test_virustotal.py`, `test_webhook_logic.py` (network-dependent, no live server), `test_agentic_ai.py::TestRunCallsAnthropicWithToolChoiceAny` (SDK version drift), `test_e2e_integration.py::test_golden_path_evidence_to_remediation` and `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` (both previously logged as pre-existing in STATE.md's 39-06 session note). 3 additional test files (`test_ai_service_config.py`, `test_network_endpoint.py`, `test_sbom_api.py`) fail at collection time on a live network dependency, also reproducing identically on the clean tree — excluded from the run via `--ignore`.

Ready for 42-02 (frontend `ControlCommentsPanel.tsx` + `apiService.ts` wrappers + `FrameworkDetail.tsx` mount) to consume `GET`/`POST /api/control-comments` directly against this backend.

---
*Phase: 42-comment-threads-on-compliance-controls*
*Completed: 2026-07-21*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 3 task commit hashes (`cbb863e`, `7b6ce15`, `6f9a5a3`) confirmed present in `git log`.
