---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backend/itam_finance_endpoints.py
  - backend/tests/test_itam_cost_parity.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: issues_found
---

# Phase 78: Code Review Report (incremental, commit 6b9351f63, WR-08 fix)

**Reviewed:** 2026-11-17
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Scope is `git diff c8aa70cbf HEAD` for the two files (10 insertions, 4 deletions). The WR-08 fix is correct and complete for the field it targets. The only new finding is an Info item: the same route still echoes a raw `purchaseDate` where the cost row sanitizes it. Nothing currently consumes that field, so it is not a blocker or warning. Parity tests re-run once in the foreground: 9 passed.

## Prior findings re-assessed

| ID | Verdict | Evidence |
|----|---------|----------|
| WR-08 (route echoes raw unreadable cost; FinancePanel pre-fills Purchase Cost from it) | Fixed | `backend/itam_finance_endpoints.py:151` reads `cost` before `base` is built. `:156` sets `"purchaseCostCents": cost if is_cents(cost) else None`, the same predicate as the cost row (`backend/itam_cost_service.py:126`). `:161` still returns `REASON_UNREADABLE_COST`, so the operator is told the cost is unreadable. The `/ 100` pre-fill at `components/itam/FinancePanel.tsx:61` is guarded by `!= null` and now only ever receives `number \| null`, matching `ItamBookValue` in `types.ts:1143`. A zero cost (`N-ZERO`) is still echoed as `0`, as in the row. The valued path at `:177` reads `asset["purchaseCostCents"]` directly, but that value is the same `cost`, already proven `is_cents` by the checks at `:161` and `:163`. No regression. |
| Test coverage of the fix | Not weakened or tautological | `test_itam_cost_parity.py:212` and `:229` compare the route value to the list row's value for every active and every unvalued asset. The explicit `:232` assertion (`N-MALCOST` gives `None`) is independent of the row, so it would catch a shared regression. The fixer's fails-then-passes claim is plausible: the seeded `N-MALCOST` cost is the string `"1000"` (`:60`), which the old route echoed. |
| WR-01..WR-07, IN-01..IN-14 | Not regressed | The reason-code logic at `:161-172` is unchanged. The 9 parity tests pass. |

## Info

### IN-15: Book-value route still echoes a raw non-string purchaseDate that the cost row sanitizes

**File:** `backend/itam_finance_endpoints.py:157`
**Issue:** The cost row emits `"purchaseDate": raw_date if isinstance(raw_date, str) else None` (`itam_cost_service.py:127`). `get_asset_book_value` still emits `asset.get("purchaseDate")` unfiltered. A stored non-string date, such as a number, list or dict, is passed through, which breaks the `purchaseDate?: string | null` contract in `types.ts`. This is the same class of defect as WR-08. It is Info rather than a warning because no consumer reads it. `FinancePanel.tsx:62` pre-fills the date from the warranty response (`w.purchaseDate`), not `bv`, and no other `bookValue.purchaseDate` reader exists. The parity tests also never cover a non-string date (`N-BADDATE` is the string `"31/12/2020"`, which is echoed identically by both and so passes).
**Fix:**
```python
raw_date = asset.get("purchaseDate")
...
"purchaseDate": raw_date if isinstance(raw_date, str) else None,
```
Optionally add a `purchaseDate` parity assertion to the two route-versus-row tests. The existing `N-BADDATE` string case would still pass, so a non-string seed would be needed for it to bite.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
