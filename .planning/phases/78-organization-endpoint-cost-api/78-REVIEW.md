---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T12:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/itam_cost_service.py
  - backend/itam_finance_endpoints.py
  - backend/tests/test_itam_cost_parity.py
  - components/itam/FinancePanel.tsx
  - src/__tests__/FinancePanel.test.tsx
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 78: Code Review Report

**Reviewed:** 2026-11-17
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Incremental review of the third review-fix round: 5700878cb (WR-07) and 78aff2770 (IN-14), read from `git diff 27b9a67ca HEAD` plus the surrounding code. No tests were run (read-only, as instructed).

Both prior findings are really fixed. The route now has the same reason precedence as `compute_asset_cost`, the rename left no stale caller, every reason code the route can return has copy in the panel, and the widened parity test is meaningful and deterministic. The one new defect is a data-echo gap that the WR-07 change makes reachable: for an unreadable cost the route echoes the raw stored value, and `FinancePanel` pre-fills the cost input from it.

## Prior findings re-assessed

| ID | Verdict | Evidence |
|----|---------|----------|
| WR-07 | Fixed | `backend/itam_finance_endpoints.py:159-163` returns `unreadable_purchase_cost` for a non-None, non-`is_cents` cost, before the no-purchase-record check, matching `backend/itam_cost_service.py:138-141`. `:181-182` catches `(ValueError, TypeError)` and returns `unreadable_purchase_date`, matching `itam_cost_service.py:153-154`. The no-record condition `cost is None or purchaseDate is None` (`:162`) equals the row's `raw_cost is None or raw_date is None` (`itam_cost_service.py:140`). The policy check (`:169`) is the shared `policy_misfit_reason`. The route no longer 500s on a string cost. Fixer's account in 78-REVIEW-FIX.md matches the diff. |
| IN-14 | Fixed | `backend/tests/test_itam_cost_parity.py:213-228` derives the unvalued set from the list rows, asserts it equals `NOT_TRACKED` (line 222), then checks each of the five assets for no figure and for route reason == row reason == the literal in `NOT_TRACKED`. Not tautological: the literals are independent of the code under test, and the set-equality assert forces a new unvalued seed asset to name its reason. `:230-246` pins the disposed/retired divergence correctly: the route figure is compared with `compute_book_value` computed independently at `FIXED` and asserted non-None, and the row (read with `include_inactive=True`) has no figure and the status as its reason. The seed values (cost 90000 and 70000, model-ok salvage 10000) mean salvage does not exceed cost, so the figure is truly non-None. |

Other checks requested:

- **Check order, route vs row:** identical except the deliberate lifecycle rule (inactive status). unreadable cost, then no record, then policy misfit, then depreciation with unreadable date.
- **Callers of the renamed `_is_cents`:** grep over the whole repo outside venv and node_modules (py, ts, tsx, including tests) finds no `_is_cents` left. All five uses are `is_cents` in `itam_cost_service.py` and `itam_finance_endpoints.py`. No regression.
- **Reason codes the route can now return:** `no_purchase_record`, `no_depreciation_policy_assigned`, `salvage_exceeds_cost`, `unreadable_purchase_cost`, `unreadable_purchase_date`. `BOOK_VALUE_REASON_COPY` in `FinancePanel.tsx:14-20` maps all five, with an unknown-code fallback, and `FinancePanel.test.tsx:98-103` covers the two new ones. The only other consumer of the route is FinancePanel (grep of `fetchAssetBookValue` and `book-value`), so nothing else is unmapped.
- **Determinism of the widened tests:** `compute_book_value` is whole-year granular. The route reads `datetime.now()` while the row is computed at the captured `FIXED`; no seeded purchase date sits near an anniversary of `FIXED`, so the comparison is stable. No finding.
- **Regression of WR-01..WR-06, IN-01..IN-13:** none seen.

## Warnings

### WR-08: Book-value route echoes the raw unreadable cost, and FinancePanel pre-fills the Purchase Cost field from it

**File:** `backend/itam_finance_endpoints.py:151-157` (consumed at `components/itam/FinancePanel.tsx:61`)
**Issue:** `base["purchaseCostCents"]` is `asset.get("purchaseCostCents")`, unsanitised. The cost row sanitises the same value (`itam_cost_service.py:126`: `raw_cost if is_cents(raw_cost) else None`), but the route does not. Before WR-07 an unreadable cost made this route 500, so `loadFinance` never got a response. Now the route returns 200 with `reason: unreadable_purchase_cost` and the garbage value, and `FinancePanel.tsx:61` does `String(bv.purchaseCostCents / 100)` into the form. For a non-numeric string, dict or list the field becomes `"NaN"`. A number input renders that as blank, but the form state is the truthy string `"NaN"`. If the operator then fixes only the date and presses Save, `handleSave` (`:78`) sends `Math.round(Number("NaN") * 100)`, which is `NaN`, serialised as `null`, in the very record the new copy ("The purchase cost on this asset cannot be read.") tells them to correct. A negative int or float is pre-filled as a plausible-looking value (for example 12345.5 becomes 123.455), so the operator may save a figure they never saw as invalid. The type contract (`types.ts:1143`, `number | null`) is also broken for the string and object cases.
**Fix:** Echo only a well-typed cost, as the row does:

```python
cost = asset.get("purchaseCostCents")
base = {
    ...
    "purchaseCostCents": cost if is_cents(cost) else None,
    ...
}
```

(move the `cost = ...` line above `base`). The reason code still tells the operator the stored cost is unreadable, and the form field stays empty so they enter a fresh value. Add a case to `test_route_reason_matches_row_for_every_unvalued_asset` asserting `result["purchaseCostCents"] is None` for `N-MALCOST`. The `/ 100` pre-fill is then safe for every shape the route can return.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
