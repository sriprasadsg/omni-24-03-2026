---
phase: 78-organization-endpoint-cost-api
fixed_at: 2026-11-17T11:30:00Z
review_path: .planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 78: Code Review Fix Report

**Fixed at:** 2026-11-17
**Source review:** .planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0

`workflow.use_worktrees` is `false` in this project, so edits, commits and all verification ran in the main checkout (no worktree, no temp branch, no recovery sentinel).

## Fixed Issues

### WR-07: The book-value route maps an unreadable purchase date to "no depreciation policy" and does not guard an unreadable cost

**Files modified:** `backend/itam_finance_endpoints.py`, `backend/itam_cost_service.py`, `components/itam/FinancePanel.tsx`, `src/__tests__/FinancePanel.test.tsx`
**Commit:** 5700878cb
**Status:** fixed (a logic change; the route's reason order is worth a human glance)
**Applied fix:**
- `get_asset_book_value` now returns `unreadable_purchase_cost` when the stored cost is not a non-negative integer. The check runs before the no-purchase-record check and before the policy check, in the same order the cost row uses (`itam_cost_service.compute_asset_cost`). A cost of `"abc"` with no date therefore reads `unreadable_purchase_cost` on both surfaces.
- The `except` around `compute_book_value` now catches `(ValueError, TypeError)` and returns `unreadable_purchase_date` instead of `no_depreciation_policy_assigned`. The route no longer 500s on a bad cost or date.
- `itam_cost_service._is_cents` is now the public `is_cents` (nothing else in the repo used the underscore name, so no alias was kept). The route imports `REASON_UNREADABLE_COST`, `REASON_UNREADABLE_DATE` and `is_cents`; the unused `REASON_NO_DEPRECIATION_POLICY` import was dropped.
- The comment at the shared-check call now says exactly what is shared (the policy check and the unreadable cost and date reasons) and what is not (the lifecycle rule).
- `BOOK_VALUE_REASON_COPY` has "The purchase cost on this asset cannot be read." and "The purchase date on this asset cannot be read."; the FinancePanel table test has both rows.
- The lifecycle difference was left as it is: a disposed or retired asset still shows its figure on its own Finance tab.

### IN-14: The new parity test checks route against row for two assets only, so the remaining disagreements in WR-07 stay invisible

**Files modified:** `backend/tests/test_itam_cost_parity.py`
**Commit:** 78aff2770
**Status:** fixed
**Applied fix:**
- `test_salvage_above_cost_route_and_row_agree` is replaced by `test_route_reason_matches_row_for_every_unvalued_asset`. It derives the unvalued set from the list rows, asserts it equals `NOT_TRACKED` (so a new unvalued seed asset must name its reason), then for each of the five (`N-AGENT`, `N-NOMODEL`, `N-MALCOST`, `N-BADDATE`, `N-SALVAGE`) asserts the route returns no figure and the same reason as the row.
- New `test_route_and_row_differ_only_for_disposed_and_retired` keeps the lifecycle divergence as a commented, explicit known difference. For `X-DISPOSED` and `X-RETIRED` it asserts the route returns the real depreciated figure (computed independently with `compute_book_value`) and the list row, read with inactive assets included, has no figure and the status as its reason.
- `test_book_value_route_matches_list` no longer skips the string-cost asset (its comment, "not a well-typed input for the per-asset route", is now false) and compares the route with the row for every active asset, `N-MALCOST` included.
- **Widened test fails on the pre-fix route, passes after.** Against the unmodified route the new test failed with `TypeError: unsupported operand type(s) for -: 'str' and 'int'` for `N-MALCOST`. With only the cost guard applied and the date branch still returning the old reason, it failed with `assert 'no_depreciation_policy_assigned' == 'unreadable_purchase_date'` for `N-BADDATE`. With the full fix it passes. No temporary HEAD copy file was needed; the pre-fix route was the working copy before editing, so nothing was left to delete.

## Verification

Run in the main checkout, foreground, named files only.

- Backend, the 13 named files: **312 passed, 0 skipped, 0 failed** (`-q -p no:cacheprovider -rs`). Every test file that imports `itam_cost_service` or `itam_finance_endpoints` is in that list (checked with grep).
- `backend/tests/test_itam_cost_parity.py` alone: 9 passed (was 8 passed before this round plus the two new tests replacing one).
- Frontend, `npx vitest run src/__tests__/FinancePanel.test.tsx`: **9 passed**, 1 file. It is the only test file that references FinancePanel.
- Build: `npx vite build` to the scratchpad `vite-78fix` dir succeeded. `dist-new/index.html` md5 is still `13c235ddca4e2970e5a9fc0260d799ad`.
- Leaked `backend/static/reports` files were left alone and not committed.
- No live `omni_platform` access, restart or deploy.

## User-WIP check

- Before staging each commit, `git diff HEAD --numstat` on the files I staged showed only my hunks (none of the five files held user WIP). Staging was by explicit path, no `commit -a`, no stash, checkout, restore or reset.
- After both commits, `git diff --cached` is empty, and `git diff --numstat` of the working tree is byte-identical to the snapshot `wip-numstat-before-78fix3.txt` (saved as `wip-numstat-after-78fix3.txt`; `diff` printed no difference).
- The first WR-07 commit briefly carried a `Co-Authored-By` trailer; it was amended off before anything else happened (commit message only, nothing pushed), per the project's no-trailer rule. The hash in this report, 5700878cb, is the amended commit.

## Needs human verification

- The route now puts the unreadable-cost check before the no-purchase-record check, so a non-integer cost with no date reads `unreadable_purchase_cost` (the same as the list row). The review's sketch checked it only after. This is a choice of order, not a change of scope.
- The disposed/retired figure on the Finance tab (kept on purpose) is now pinned by a test. If the intent later changes, that test is the one to edit.

---

_Fixed: 2026-11-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
