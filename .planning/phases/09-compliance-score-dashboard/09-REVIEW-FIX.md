---
phase: 09-compliance-score-dashboard
fixed_at: 2026-07-02T13:12:27Z
review_path: .planning/phases/09-compliance-score-dashboard/09-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-07-02T13:12:27Z
**Source review:** .planning/phases/09-compliance-score-dashboard/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 10
- Fixed: 10
- Skipped: 0

## Fixed Issues

### CR-01: `GET /api/compliance/score/history` crashes on every request — `timedelta` is never imported

**Files modified:** `backend/compliance_score_endpoints.py`
**Commit:** `e503a41`
**Applied fix:** Added `timedelta` to the existing `from datetime import datetime, timezone` import. The endpoint's `cutoff = datetime.now(timezone.utc) - timedelta(days=days)` call now resolves correctly instead of raising `NameError` (previously masked as an opaque 500).

### CR-02: `is_super` role check incorrectly includes tenant-scoped `"admin"`, causing cross-tenant data leakage

**Files modified:** `backend/compliance_score_endpoints.py`
**Commit:** `2dc63f6`
**Applied fix:** Changed the import from `auth_roles.SUPER_AND_ADMIN_ROLES` to `auth_roles.SUPER_ROLES` (aliased as `_SUPER_ROLES`), matching the narrower, already-established platform-role convention used in `user_endpoints.py` and `compliance_evidence_lifecycle_endpoints.py`. This closes both the unscoped `/score/history` query bypass and the shared `"__super__"` cache-key collision for ordinary tenant `"admin"` callers. Verified all 8 pre-existing tests in `test_compliance_score.py` still pass (they use role `"admin"`, which is no longer treated as platform-super, but tenant scoping via `TenantIsolatedCollection` is unaffected).

### CR-03: `compliance:score:__super__` and `compliance:threat-score:*` caches are never invalidated by any write path

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`, `backend/compliance_status_endpoints.py`, `backend/tests/test_compliance_score.py`
**Commit:** `1530984`
**Applied fix:** Added `invalidate_cache("compliance:score:__super__")`, `invalidate_cache(f"compliance:threat-score:{tenant_id}")`, and `invalidate_cache("compliance:threat-score:__super__")` alongside the existing `invalidate_cache(f"compliance:score:{tenant_id}")` call in both write paths (bulk evidence upload and status override). Updated the existing `test_cache_invalidated_on_upload` test, which previously asserted `invalidate_cache` was called exactly once — it now asserts all four expected keys are present in the call list (the bulk-upload path calls `invalidate_cache` 4 times after this fix).

### CR-04: `PATCH /api/assets/{asset_id}/compliance/status` has no write-permission check

**Files modified:** `backend/compliance_status_endpoints.py`, `backend/tests/test_compliance_status.py`
**Commit:** `e573612`
**Applied fix:** Added a `_WRITE_ROLES` frozenset mirroring the pattern already used in `compliance_bulk_evidence_endpoints.py`, and a `403 Insufficient permissions to override compliance status` gate before any DB access. Updated `test_patch_compliance_status_success` (now uses `role="admin"`, a write-permitted role, since the prior default `"Viewer"` would now correctly be rejected) and `test_patch_compliance_status_cross_tenant_403` (now uses `role="Admin"`, which passes the write gate but is intentionally excluded from the case-sensitive tenant-bypass `_SUPER_ROLES` set, so it still exercises the tenant-isolation check specifically rather than being short-circuited by the new write-role check). Added a new `test_patch_compliance_status_read_only_role_403` regression test for the vulnerability itself.

## Warnings — Fixed

### WR-01: Bulk-upload docstring guarantee broken for corrupt/unreadable zip entries

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `9fde950`
**Applied fix:** Added `import zlib` and broadened the per-entry exception handler from `except KeyError` alone to also catch `zipfile.BadZipFile`, `OSError`, and `zlib.error`, appending a per-file error entry and continuing instead of falling through to the function-level `except Exception` (which previously turned a corrupt zip entry into a generic 500 instead of the documented 422).

### WR-02: `ComplianceScorePanel`'s "no monitored controls" empty state is effectively unreachable

**Files modified:** `components/ComplianceScorePanel.tsx`
**Commit:** `fb6a871`
**Applied fix:** Replaced the `data.frameworks.length === 0 && data.overall_score === 0` check with a `totalEvaluated` sum of `total_controls` across all frameworks, so the onboarding empty-state message renders correctly for any tenant with zero evaluated controls, regardless of how many frameworks are seeded globally. (No local TypeScript compiler available — verified via Tier 1 re-read only; the `FrameworkScore.total_controls: number` field was confirmed present in `types.ts`.)

### WR-03: `patch_asset_compliance_status` has a TOCTOU race between reading and writing `previous_status`

**Files modified:** `backend/compliance_status_endpoints.py`, `backend/tests/test_compliance_status.py`
**Commit:** `cc45006`
**Applied fix:** Replaced the separate `find_one` + `update_one` calls with `find_one_and_update` for the `$set` portion (status, `lastUpdated`, `manual_override`, `overriddenBy`, `overriddenAt`), capturing `previous_status` atomically from the pre-update document (`find_one_and_update`'s pymongo/motor default `return_document=BEFORE`). The `status_history` `$push` remains a separate `update_one` call, since it only appends and does not depend on current document state — its correctness relies on `previous_status` having already been captured atomically, not on its own ordering relative to concurrent requests. Updated `test_patch_compliance_status_success` to mock `find_one_and_update` and split its assertions between the two calls.
**Note:** This fix addresses a concurrency/logic issue. Syntax and unit-test verification pass, but the atomicity argument (no race window under concurrent requests) cannot be fully validated by automated tests without a live DB under load — **fixed: requires human verification** before this phase proceeds to the verifier stage.

### WR-04: No coverage for the cache-key namespace or the `/score/history` endpoint

**Files modified:** `backend/tests/test_compliance_score.py`
**Commit:** `9e02676`
**Applied fix:** Added `test_score_cache_key_namespace_no_cross_tenant_collision`, which exercises the **real** cache (not mocked) with two different tenants both using role `"admin"`, asserting each tenant populates its own cache key, the shared `"__super__"` key remains untouched, and the two tenants' responses differ. Added `test_score_history_endpoint`, a smoke test for `GET /api/compliance/score/history` asserting `200` with the expected response shape — this is also a direct regression test for CR-01.

## Info — Fixed

### IN-01: Unmapped control categories silently default to "Low" severity

**Files modified:** `backend/compliance_score_endpoints.py`
**Commit:** `7668027`
**Applied fix:** Extracted a `_category_severity()` helper that logs a rate-limited warning (once per distinct unmapped category, tracked via a module-level set) when a control's `category` isn't found in `_CATEGORY_SEVERITY`, then falls back to `"Low"` as before. Replaced all 3 call sites (`get_compliance_score` ×2, `get_threat_score` ×1) that previously called `_CATEGORY_SEVERITY.get(..., "Low")` directly.

### IN-02: `notes` field on the status-override request has no length bound

**Files modified:** `backend/compliance_status_endpoints.py`, `backend/tests/test_compliance_status.py`
**Commit:** `e49ddb7`
**Applied fix:** Changed `notes: str = ""` to `notes: str = Field("", max_length=2000)` on `ComplianceStatusUpdate`, per CLAUDE.md's "Validate input at system boundaries." Added `test_patch_compliance_status_notes_length_bound_422` to verify both the rejection at 2001 chars and acceptance at exactly 2000.

## Skipped Issues

None — all 10 in-scope findings were fixed.

---

_Fixed: 2026-07-02T13:12:27Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
