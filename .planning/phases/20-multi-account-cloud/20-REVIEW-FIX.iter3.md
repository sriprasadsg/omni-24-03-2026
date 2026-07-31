---
phase: 20-multi-account-cloud
fixed_at: 2026-07-04T11:55:42Z
review_path: .planning/phases/20-multi-account-cloud/20-REVIEW.md
iteration: 2
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 20: Code Review Fix Report

**Fixed at:** 2026-07-04T11:55:42Z
**Source review:** .planning/phases/20-multi-account-cloud/20-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 4 (WR-05, WR-06, IN-05, IN-06 — fix_scope: all)
- Fixed: 4
- Skipped: 0

This is iteration 2 of the fix loop for phase 20. All findings from this pass's `20-REVIEW.md` were fixed, including both Info items (fix_scope: all).

## Fixed Issues

### WR-05: `get_summary`'s `total_accounts`/`by_provider`/`by_environment` still silently truncate at 100 accounts

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** bf7eda0
**Applied fix:** `get_summary()` previously called `list_accounts(db, tenant_id)` with no `skip`/`limit`, silently capping the account list (and therefore `total_accounts`, `by_provider`, `by_environment`) at the default `limit=100` — the same truncation bug WR-03 fixed for `GET /api/cloud-accounts`, left open in this sibling function. Changed `get_summary` to compute `total_accounts` via the unbounded `count_accounts()` and fetch the account list with `limit=max(total_accounts, 1)` so the breakdown is never capped below the true count. Verified with `python3 -c "import ast; ast.parse(...)"` (syntax OK) and the full `backend/tests/test_cloud_accounts.py` suite (all tests passed before and after this change).

### WR-06: `register_account`'s preserve-on-omission fix only covered `credentials_ref` — `account_name`/`region` still silently reset to defaults

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** ed23a7a
**Applied fix:** Applied the same preserve-on-omission pattern already used for `credentials_ref`/`last_scan`/`scan_status`/`created_at` to `account_name` and `region`: `data.get("account_name") or (existing.get("account_name", "") if existing else "")` and the equivalent for `region`. A re-registration call that omits these fields (e.g. a script, a partial-update client, a retry) no longer blanks a previously-set display name or resets a custom region to `"us-east-1"`. Verified via syntax check and full test suite pass (13/13 after IN-05's new tests were later added).

### IN-05: The CR-01 credential-preservation fix and the WR-03 `total_count` behavior shipped with no direct regression test

**Files modified:** `backend/tests/test_cloud_accounts.py`
**Commit:** dc78955
**Applied fix:** Added `test_register_preserves_credentials_ref_when_omitted`, which registers an account with `credentials_ref` set, captures the encrypted value written by the first `update_one` call, then re-registers the same `(tenantId, provider, account_id)` without resending `credentials_ref` (mocking `find_one` to return the first stored doc, as a real re-registration would) and asserts the second `update_one` call's stored `credentials_ref` equals the first. Added `test_list_accounts_total_count_reflects_count_accounts`, which mocks `count_documents` to return `137` and asserts `GET /api/cloud-accounts`'s `total_count` reflects that value independent of the (empty, mocked) page's `count`. Both fixes (CR-01, WR-03) previously relied entirely on manual review; they now have automated regression guards. Verified: `pytest tests/test_cloud_accounts.py -q` — 13 passed (11 pre-existing + 2 new).

### IN-06: No mechanism to explicitly clear or rotate a stored `credentials_ref` to empty

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** 9a81152
**Applied fix:** This is a design trade-off note rather than a concrete code defect (the review explicitly frames CR-01's behavior as "a reasonable trade-off... worth noting explicitly since it wasn't called out"). Added a comment directly above the `creds_enc = existing.get(...)` fallback line documenting that every falsy `credentials_ref` (omitted, `""`, or `null`) is currently treated as "don't touch," that there is no way to intentionally clear a stored credential today, and that an explicit sentinel value would be needed to distinguish "clear" from "don't touch" if that capability is required later. No behavior change; verified via syntax check and full test suite pass.

## Skipped Issues

None — all 4 in-scope findings were fixed.

---

_Fixed: 2026-07-04T11:55:42Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
