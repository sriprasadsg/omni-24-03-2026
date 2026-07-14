---
phase: 29-public-trust-center
plan: 01
subsystem: api
tags: [trust-center, persistence, tenant-isolation, fastapi, mongo, pytest]

# Dependency graph
requires: []
provides:
  - "Async, Mongo-backed trust_service.py (trust_profiles + trust_access_requests collections) replacing the former in-memory TrustService singleton"
  - "Admin routes in trust_endpoints.py repointed at the async service, auth model unchanged"
  - "Opaque per-tenant trust_slug (auto-generated on db.tenants) and settable trust_domain, both surfaced via GET/PUT /api/trust-center/profile"
  - "backend/tests/test_trust_center.py rewritten with persistence/tenant/admin_auth/admin_settings suites (Wave 0 scaffold for the phase)"
affects: [29-02-public-route-and-nda-flow, 29-03-custom-domain-resolution, 29-04-frontend-trustcenter-admin-view]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tenant-scoped CRUD via caller-supplied db handle (get_database()), never a raw module-level DB reference — mirrors privacy_service.py's create_tia/list_tia shape"
    - "trust_slug/trust_domain live on the tenant-isolation-exempt db.tenants document, keyed by tenant id, kept separate from the tenant-scoped trust_profiles collection"
    - "_ensure_trust_slug idempotent generate-if-absent pattern for opaque per-tenant identifiers"

key-files:
  created: []
  modified:
    - backend/trust_service.py
    - backend/trust_endpoints.py
    - backend/tests/test_trust_center.py

key-decisions:
  - "Rewrote test_trust_center.py from scratch rather than incrementally patching — the old file tested a MockTrustService shape (sync, in-memory) that has no analog in the new async DB-backed API; a previous execution attempt claimed this plan complete but committed nothing (verified via git log --all and runtime UAT), so this run treats the actual tree state as ground truth per the critical_context brief, not the phantom SUMMARY."
  - "get_profile drops its response_model=TrustProfile and returns a plain dict so the merged trust_slug/trust_domain fields pass through, per the plan's explicit instruction."
  - "trust_domain validation (strip scheme/path, lowercase, cap 253 chars) implemented inline in trust_endpoints.py's update_profile rather than as a separate helper module — kept the file well under the 500-line CLAUDE.md limit."

patterns-established:
  - "Pattern: any future tenant-scoped Trust Center collection must go through get_database() and must never be added to database.py's TenantIsolatedDatabase exemption allowlist (only db.tenants stays exempt for slug/domain resolution)."

requirements-completed: [TRUST-01, TRUST-03]

# Metrics
duration: 24min
completed: 2026-07-14
status: complete
---

# Phase 29 Plan 01: Trust Center DB Persistence Summary

**Retrofitted the in-memory TrustService singleton onto async Mongo-backed `trust_profiles`/`trust_access_requests` collections, repointed all five existing authenticated admin routes at the new service without changing their auth model, and added an auto-generated opaque `trust_slug` plus a settable `trust_domain` on `db.tenants`.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-13T23:50:00Z
- **Completed:** 2026-07-14T00:14:33Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- `backend/trust_service.py` is now fully async and Mongo-backed: `get_profile`, `update_profile`, `get_requests`, `create_request`, `update_request_status` all read/write through the tenant-isolated `db` handle passed in by the caller — no more `self.profile`/`self.requests` process state that resets on every restart.
- All five `backend/trust_endpoints.py` admin routes (`GET/PUT /profile`, `GET /requests`, `POST /requests`, `PUT /requests/{id}`) converted to `async def`, awaiting the Task-2 service helpers, with `Depends(get_current_user)` and the `_TRUST_ADMIN_ROLES` gate on every write preserved exactly as before.
- `_ensure_trust_slug(db, tenant_id)` generates and persists an idempotent `trust-{uuid4().hex[:12]}` slug onto the tenant-isolation-exempt `db.tenants` document; `GET /profile` merges `trust_slug` + `trust_domain` into its (now plain-dict) response, and `PUT /profile` accepts an optional `trust_domain` key, normalizes it, and persists it separately from the profile document.
- `backend/tests/test_trust_center.py` rewritten with the four suites this plan and 29-VALIDATION.md require: `TestTrustPersistence` (`-k persistence`), `TestTrustTenantIsolation` (`-k tenant`), `TestTrustAdminAuth` (`-k admin_auth`), and `TestTrustAdminSettings` covering the trust_domain read/write round trip — 6 tests, all green.
- `trust_profiles`/`trust_access_requests` confirmed absent from `database.py`'s tenant-isolation exemption allowlist (`grep` returns nothing) — the isolation boundary this phase's threat model requires (T-29-01) is intact.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create test scaffold and TRUST-01 persistence/tenant/admin_auth suites** - `21ed35b3` (test)
2. **Task 2: DB-back trust_service.py (trust_profiles + trust_access_requests, trust_slug generation)** - `435213be` (feat)
3. **Task 3: Repoint admin routes at the async service; surface trust_slug/trust_domain** - `86575edb` (feat)

_No TDD RED/GREEN split commits were needed for Task 2/3 — Task 1's scaffold was the RED state (verified failing before Task 2 landed); Task 2/3 commits are the GREEN state._

## Files Created/Modified
- `backend/trust_service.py` - Rewritten: `TrustService` singleton deleted; async module-level `get_profile`/`update_profile`/`get_requests`/`create_request`/`update_request_status`/`_ensure_trust_slug` added. `TrustProfile`/`AccessRequest` Pydantic models kept field-for-field identical.
- `backend/trust_endpoints.py` - All 5 routes converted to `async def`; `get_profile`/`update_profile` merge `trust_slug`/`trust_domain`; `_normalize_trust_domain` helper added.
- `backend/tests/test_trust_center.py` - Fully rewritten: old `MockTrustService`-based suite (9 tests against the sync in-memory API) replaced with `TestTrustPersistence`, `TestTrustTenantIsolation`, `TestTrustAdminAuth`, `TestTrustAdminSettings` (6 tests against the new async API).

## Decisions Made
- Treated the actual git history and tree state as ground truth over a prior phantom SUMMARY.md (quarantined at `.planning/phases/29-public-trust-center/phantom-summaries-2026-07-08/29-01-SUMMARY.md`) that claimed this plan was already executed — no commits from that claimed execution existed in `git log --all`, and the tree still had the old in-memory singleton and old test file. This run re-executed the plan from scratch against the real tree.
- `get_profile`'s `response_model=TrustProfile` was dropped (per the plan's explicit instruction) so the merged `trust_slug`/`trust_domain` fields aren't stripped by FastAPI's response-model filtering.
- `trust_domain` normalization (strip scheme/path/port, lowercase, cap 253 chars) lives inline in `trust_endpoints.py` rather than a new module, keeping the file at 97 lines (well under the CLAUDE.md 500-line limit) and avoiding an unnecessary new file per CLAUDE.md's "prefer editing existing files."

## Deviations from Plan

None — plan executed exactly as written. The three tasks matched their `<action>`/`<verify>`/`<acceptance_criteria>` blocks with no architectural surprises; `agent_registry_endpoints.py`, `privacy_service.py`, and `database.py`'s exemption list matched what 29-RESEARCH.md/29-PATTERNS.md described.

## Issues Encountered
- The cloned `_col()`/`_db()` test helpers (verbatim from `test_automation_and_baa.py` per the plan's `<read_first>` instruction) only populate a `MagicMock` collection attribute for names explicitly passed to `_db(...)`; the `TestTrustAdminAuth`/`TestTrustAdminSettings` tests needed to add `tenants=_col()` explicitly wherever a route path reaches `_ensure_trust_slug`/`db.tenants` — resolved by passing the extra kwarg, no helper-block changes needed (helper stayed byte-identical to the source file per the plan).
- Discovered a pre-existing, order-dependent failure in `tests/test_auth_mfa.py` (10 of 21 `TestMFAVerifyLogin` tests fail only when run as part of the full `tests/ -q` suite, not in isolation). Reproduced identically with `test_trust_center.py` fully excluded from the run, confirming it is unrelated to this plan's changes. Logged to `.planning/phases/29-public-trust-center/deferred-items.md` per the executor's scope-boundary rule rather than fixed (out of scope for this task).

## User Setup Required

None - no external service configuration required. No new packages introduced (confirmed by 29-RESEARCH.md's Package Legitimacy Audit: none).

## Next Phase Readiness
- `trust_service.py`'s async helpers and `_ensure_trust_slug` are ready for plan 29-02 to build the genuinely public `GET`/`POST /api/public/trust/{slug}` routes on top of (resolve tenant via `db.tenants.find_one({"trust_slug": slug})`, call `set_tenant_id`, then call these same service helpers).
- `trust_domain` is readable/settable via the admin routes, ready for plan 29-03's Host-header resolution.
- `backend/tests/test_trust_center.py`'s `_col`/`_db`/`_user`/`_app` helper block and `patch("trust_endpoints.get_database", return_value=db)` pattern is established for 29-02/29-03 to extend with `public_get`/`private_doc_filter`/`public_post`/`rate_limit`/`custom_domain` test classes in the same file, per 29-VALIDATION.md's `-k` marker contract.
- No blockers. The pre-existing `test_auth_mfa.py` order-dependent flakiness (see Issues Encountered) is unrelated and does not block this phase's continuation, but should be investigated separately.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources introduced by this plan.

## Threat Flags

None. This plan's surface (admin-only, authenticated routes; `trust_slug`/`trust_domain` on the exempt `tenants` collection) is fully covered by the plan's existing `<threat_model>` (T-29-01, T-29-01a). No new network endpoints, auth paths, or trust-boundary-crossing surface was introduced beyond what the plan's threat register already accounts for.

---
*Phase: 29-public-trust-center*
*Completed: 2026-07-14*
