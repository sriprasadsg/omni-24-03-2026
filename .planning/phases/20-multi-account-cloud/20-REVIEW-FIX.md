---
phase: 20-multi-account-cloud
fixed_at: 2026-07-04T12:05:27Z
review_path: .planning/phases/20-multi-account-cloud/20-REVIEW.md
iteration: 3
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 20: Code Review Fix Report

**Fixed at:** 2026-07-04T12:05:27Z
**Source review:** .planning/phases/20-multi-account-cloud/20-REVIEW.md
**Iteration:** 3

**Summary:**
- Findings in scope: 2 (WR-01, IN-01 — fix_scope: all)
- Fixed: 2
- Skipped: 0

This is iteration 3 (final allowed iteration) of the fix loop for phase 20. Both findings from this pass's `20-REVIEW.md` were fixed, including the Info item (fix_scope: all).

## Fixed Issues

### WR-01: `register_account`'s `environment` field is still silently reset to `"dev"` on re-registration when omitted — the WR-06 fix covered `account_name`/`region` but missed this third sibling field with the identical defect

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** 85a0ad9
**Applied fix:** `register_account`'s `doc` literal set `"environment": data.get("environment", "dev")` with no fallback to the previously-stored value, unlike its siblings `account_name`/`region`/`credentials_ref`, which WR-06/CR-01 had already fixed to preserve the existing value when the field is omitted. Applied the identical preserve-on-omission pattern: `data.get("environment") or (existing.get("environment", "dev") if existing else "dev")`. I confirmed the bug was live before the fix (re-registering a `"prod"` account while omitting `environment` — exactly what the shipped `CloudAccountsDashboard.tsx` form does when a user never touches the Environment select — silently flipped the stored value to `"dev"`), and confirmed the fix closes it by temporarily reverting the line and re-running the new IN-01 regression test, which failed as expected (`assert 'dev' == 'prod'`), then restoring the fix and re-running, which passed. Verified with `python3 -c "import ast; ast.parse(...)"` (syntax OK) and the full `backend/tests/test_cloud_accounts.py` suite (13/13 passed before the IN-01 tests were added; 15/15 after).

### IN-01: WR-05 (`get_summary` truncation fix) and WR-06 (`account_name`/`region` preservation fix) both shipped with no direct regression test

**Files modified:** `backend/tests/test_cloud_accounts.py`
**Commit:** 7b3188d
**Applied fix:** Added `test_summary_total_accounts_reflects_count_accounts_not_capped_list`, which mocks `count_documents` to return `150` while `find` returns only 5 account docs, and asserts `GET /api/cloud-accounts/summary`'s `total_accounts` equals `150` (the `count_accounts()` value) rather than `5` (the length of the account list used for the by_provider/by_environment breakdown) — this is the direct regression guard WR-05 shipped without. Added `test_register_preserves_account_name_region_environment_when_omitted`, which registers an account with `account_name="Custom Name"`, `region="eu-west-1"`, `environment="prod"`, then re-registers the same `(tenantId, provider, account_id)` omitting all three fields (mocking `find_one` to return the first stored doc) and asserts all three values are preserved from the stored doc — extending the pattern `test_register_preserves_credentials_ref_when_omitted` already used for `credentials_ref`, and additionally covering `environment` since WR-01 (this same iteration) extended the preserve-on-omission fix to that field. Verified: `pytest tests/test_cloud_accounts.py -q` — 15 passed (13 pre-existing + 2 new). Additionally confirmed the new field-preservation test is not a false-positive guard by temporarily reverting the WR-01 fix and observing the test fail with the expected assertion (`environment` regressed to `"dev"`), then restoring and re-confirming the pass.

## Skipped Issues

None — both in-scope findings were fixed.

---

_Fixed: 2026-07-04T12:05:27Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 3_
