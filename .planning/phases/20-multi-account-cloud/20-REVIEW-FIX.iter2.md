---
phase: 20-multi-account-cloud
fixed_at: 2026-07-04T11:45:00Z
review_path: .planning/phases/20-multi-account-cloud/20-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 7
skipped: 3
status: partial
---

# Phase 20: Code Review Fix Report

**Fixed at:** 2026-07-04T11:45:00Z
**Source review:** .planning/phases/20-multi-account-cloud/20-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (CR-01, CR-02, WR-01..04, IN-01..04 — fix_scope: all)
- Fixed: 7
- Skipped: 3

This is a fix pass against a freshly re-audited `20-REVIEW.md` (10 new findings, independent of the prior iteration's 8-finding review/fix history for this phase).

## Fixed Issues

### CR-01: `register_account` silently wipes stored credentials on any update that omits `credentials_ref`

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** `a4d2daf`
**Applied fix:** Reordered `register_account()` so `existing` is looked up before computing `creds_enc`, and added an else-branch that falls back to `existing.get("credentials_ref", "")` when the caller doesn't supply a new `credentials_ref`, exactly mirroring the existing "sticky field" pattern already used for `last_scan`/`scan_status`/`created_at`. A re-registration that omits `credentials_ref` (as the shipped UI always does) now preserves the previously-stored encrypted credential instead of overwriting it with an empty string.

### CR-02: Production fail-closed encryption-key guard is neutered by optional-router exception swallowing

**Files modified:** `backend/router_registry.py`
**Commit:** `1af04d0`
**Applied fix:** Applied option (a) from the review's fix suggestion (the minimal fix): added `"cloud_account_endpoints"` to `_REQUIRED_ROUTERS` with an explanatory comment. A production misconfiguration (`CLOUD_CREDENTIALS_KEY` unset) now causes `_load()` to re-raise the `RuntimeError` and abort startup as originally intended, instead of being caught, logged at ERROR, and silently swallowed.

### WR-01: `register()` in the dashboard discards the server's specific validation error

**Files modified:** `components/CloudAccountsDashboard.tsx`
**Commit:** `4e4213c`
**Applied fix:** Changed `catch { showToast('Failed', 'error'); }` to `catch (e: any) { showToast(e.message || 'Failed', 'error'); }`, matching the pattern already used by the `scan()` function a few lines below. The backend's specific validation message (e.g. `"provider must be one of ['aws', 'azure', 'gcp']"`) is now surfaced to the user instead of a generic "Failed" toast.

### WR-02: `register_account` has no type validation on `credentials_ref`, allowing an unhandled crash from a malformed request body

**Files modified:** `backend/cloud_account_endpoints.py`
**Commit:** `fa8e4d0`
**Applied fix:** Added `if payload.get("credentials_ref") is not None and not isinstance(payload["credentials_ref"], str): raise HTTPException(400, ...)` in `register_account`, before the payload reaches `svc.register_account`. A non-string `credentials_ref` (object, number, etc.) now returns a clean `400` instead of an unhandled `AttributeError` inside `_encrypt()` that surfaces as a generic 500 with an ERROR-level log entry.

### WR-03: `list_accounts` hard-caps at 100 documents with no pagination, silently hiding accounts for orgs above that threshold

**Files modified:** `backend/cloud_accounts_service.py`, `backend/cloud_account_endpoints.py`, `backend/tests/test_cloud_accounts.py`
**Commits:** `07c97f8` (implementation), `78dc02d` (test mock update)
**Applied fix:** Added `skip`/`limit` parameters to `svc.list_accounts()` and a new `svc.count_accounts()` helper backed by `count_documents`. Surfaced both as query params (`skip`, `limit`, clamped to 1-500) on `GET /api/cloud-accounts`, and added `total_count` to the response so the frontend/caller can detect truncation instead of accounts silently disappearing past the 100th.
Applying this fix changed the mongo cursor call chain from `.find().sort().to_list()` to `.find().sort().skip().limit().to_list()` and added a new `count_documents` call, which broke 3 existing tests (`test_list_accounts`, `test_summary`, `test_tenant_isolation`) whose mocks didn't support the new chain shape — confirmed as a genuine regression by diffing against the pre-fix commit (all 11 tests passed there). Updated the `_mkdb()` test helper and `test_tenant_isolation`'s local `_find` mock to use a shared `_chain()` helper supporting `.sort()/.skip()/.limit()/.to_list()` in any combination, and added `count_documents` `AsyncMock`s. All 11 tests in `test_cloud_accounts.py` pass after this update.

### WR-04: `get_summary`'s fixed 5000-document cap silently produces inaccurate aggregate statistics at scale

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** `cd14c39`
**Applied fix:** Replaced the `db.cloud_check_results.find(...).to_list(length=5000)` + in-memory `sum()` pattern with three `count_documents` calls (`total`, `result: "PASS"`, `result: "FAIL"`). `total_checks`/`pass`/`fail` in the summary dashboard are now accurate regardless of how many check-result documents a tenant has accumulated. Verified against `test_summary` (uses the same test suite / mocks updated for WR-03, which also mocks `count_documents` on `cloud_check_results`).

### IN-03: Inconsistent DB-access pattern for `cloud_accounts` between cooperating modules

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** `eaa8216`
**Applied fix:** Added a module-level docstring note explaining that this file's `db._db.<collection>` + manual `"tenantId"` filter pattern is deliberate and NOT interchangeable with `cloud_checks_service.py`'s tenant-isolation-wrapped `db.<collection>` accessor, and that moving this file off `db._db` under the wrong assumption would silently reintroduce a cross-tenant IDOR. This is documentation only — no behavioral change.

## Skipped Issues

### IN-01: Redundant no-op branch around `_encrypt`

**File:** `backend/cloud_accounts_service.py:31`
**Reason:** Code context differs from review — CR-01 (fixed first, since Critical findings are applied before Info findings) replaced the exact line this finding targets (`creds_enc = _encrypt(creds_raw) if creds_raw else creds_raw`) with new preserve-on-omission logic (`if creds_raw: creds_enc = _encrypt(creds_raw) else: creds_enc = existing.get(...)`). The literal "redundant no-op branch" IN-01 describes no longer exists in the post-CR-01 code; the surviving `if/else` now encodes different, necessary logic (fallback to the existing stored value), not a redundant duplicate of `_encrypt`'s own falsy short-circuit. No separate action needed.
**Original issue:** `_encrypt()` already returns its input unchanged when falsy (`if not plain: return plain`), so the call site's own `if creds_raw else creds_raw` check was flagged as duplicated, driftable logic.

### IN-02: Stored, encrypted `credentials_ref` is never read/decrypted anywhere in the codebase

**File:** `backend/cloud_accounts_service.py:118-121`
**Reason:** Informational only — the finding has no **Fix:** section and explicitly frames itself as a flag for awareness ("worth flagging explicitly so it isn't mistaken for a completed feature"), not a defect requiring a code change. There is no decrypt call site to add without a corresponding real provider-credential consumer, which the finding itself says is out of this phase's scope.
**Original issue:** `_encrypt()` is called in `register_account`/`discover_org_accounts` but no `_decrypt` exists anywhere in `backend/`; `credentials_ref` is currently a write-only field.

### IN-04: No platform-admin/cross-tenant visibility for cloud accounts, unlike the sibling check-results API

**File:** `backend/cloud_accounts_service.py:49-51, 80-95`
**Reason:** Informational only — the finding explicitly asks whether the asymmetry with `cloud_checks_service.get_results()`'s `SUPER_AND_ADMIN_ROLES` bypass "is the intended trust boundary rather than an oversight." This is a product/security-policy decision (should platform admins see all tenants' registered cloud accounts, which are more sensitive than check-result summaries?) rather than a code defect with an unambiguous fix, and the finding provides no concrete **Fix:** suggestion. Flagging for human decision rather than guessing at the intended trust boundary.
**Original issue:** `list_accounts`/`get_summary` always filter strictly by the caller's own `tenant_id` with no elevated-role bypass, unlike `cloud_checks_service.get_results()`.

---

_Fixed: 2026-07-04T11:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
