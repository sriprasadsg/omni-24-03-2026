---
phase: 20-multi-account-cloud
fixed_at: 2026-07-04T13:55:00Z
review_path: .planning/phases/20-multi-account-cloud/20-REVIEW.md
iteration: 2
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 20: Code Review Fix Report (Iteration 2)

**Fixed at:** 2026-07-04T13:55:00Z
**Source review:** .planning/phases/20-multi-account-cloud/20-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 4 (WR-07, IN-01, IN-02, IN-03 — fix_scope: `--all`)
- Fixed: 4
- Skipped: 0

Iteration 1 (`20-REVIEW-FIX.md`) fixed CR-01, CR-02, WR-01 through WR-06 (8 findings), explicitly leaving IN-01/IN-02/IN-03 out of scope. WR-07 was not in the original review pass — it was found during a fresh independent re-audit (prompted by lessons from phase 21's re-review) and folded into `20-REVIEW.md` before this fix pass, raising the finding count from 11 to 12.

## Fixed Issues

### WR-07: Missing authorization/RBAC enforcement on all cloud-account endpoints

**Files modified:** `backend/cloud_account_endpoints.py`, `backend/tests/test_cloud_accounts.py`
**Applied fix:** All 6 routes previously depended only on `Depends(get_current_user)` (valid JWT, no permission check). Gated reads/scans (`list_accounts`, `scan_account`, `get_account_results`, `get_summary`) with `rbac_service.has_permission("view:cloud_security")` — a permission already defined on every role but never referenced anywhere in the backend — and account-creation actions (`register_account`, `discover_org`) with `rbac_service.has_permission("manage:settings")`, matching the codebase's existing convention (`iac_scanner_endpoints.py`'s `/scan-config` mutation routes use the same tier). Removed the now-unused `get_current_user` import.
**Verification:** Updated the test suite's `_build()` helper to patch `rbac_service.get_database` (needed because `has_permission`'s permission-resolution path calls the database, unlike the previous bare `get_current_user` dependency) and mock `db.roles.find_one`. Added `test_insufficient_permission_rejected`, which confirms a `security_analyst`-role user (has neither `view:cloud_security` nor `manage:settings`) gets 403 on both `list_accounts` and `register_account` — this is the concrete regression test for the bug WR-07 describes. All 8 pre-existing tests still pass with the default `admin`-role test user, which has both permissions.

### IN-01: Pervasive `any` typing in a form that handles credential-adjacent input

**Files modified:** `components/CloudAccountsDashboard.tsx`
**Applied fix:** Added `CloudAccount`, `CloudAccountSummary`, `CloudCheckResult`, and `AccountFormState` interfaces matching the backend's actual response shapes (verified against `cloud_accounts_service.py`'s `register_account`/`list_accounts`/`get_summary`/`get_results` return values), and replaced every `any`/`any[]` state and map-callback annotation with them.
**Verification:** `tsc --noEmit` reports zero errors for this file.

### IN-02: `discover_org_accounts` accepts an unvalidated, effectively-unused `credentials` payload

**Files modified:** `backend/cloud_account_endpoints.py`, `backend/tests/test_cloud_accounts.py`
**Applied fix:** Added a boundary check requiring `management_account_id` in the request body (400 if missing), pinning the contract shape ahead of the real AWS Organizations integration that will eventually replace this stub — per CLAUDE.md's "validate input at system boundaries" rule. Updated `test_discover_org`'s payload to include the now-required field.
**Verification:** Added `test_discover_org_requires_management_account_id`, confirming a request without the field is rejected with 400.

### IN-03: `scan_account` endpoint always returns HTTP 200, even for a nonexistent account or an internal failure

**Files modified:** `backend/cloud_account_endpoints.py`, `components/CloudAccountsDashboard.tsx`
**Applied fix:** The endpoint now inspects the service result's `error` key and raises `HTTPException(404)` for "Cloud account not found" or `HTTPException(502)` for any other scan-execution error, instead of always returning the dict verbatim with an implicit 200. Updated the dashboard's `scan()` handler: the `r.error` success-path branch (now unreachable, since errors arrive as non-2xx) was removed, and the `catch` block now surfaces the thrown error's message in the toast instead of a generic string, preserving the specific error detail that used to come from the `r.error` branch.
**Verification:** Added `test_scan_nonexistent_account_returns_404`, confirming a scan against an unregistered `account_id` now returns 404 instead of 200. `tsc --noEmit` reports zero errors for the dashboard file.

## Skipped Issues

None — all 4 in-scope findings were fixed.

---

_Fixed: 2026-07-04T13:55:00Z_
_Fixer: Claude Sonnet 5_
_Iteration: 2_
