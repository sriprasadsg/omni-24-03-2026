---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T11:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - backend/itam_cost_service.py
  - backend/itam_finance_endpoints.py
  - backend/itam_finance_service.py
  - backend/itam_tenant_scope.py
  - backend/tests/test_itam_cost_parity.py
  - backend/tests/test_itam_cost_service.py
  - backend/tests/test_itam_custom_report_tenant.py
  - components/itam/FinancePanel.tsx
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportsPanel.tsx
  - src/__tests__/FinancePanel.test.tsx
  - src/__tests__/ITAMKpiPanel.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
  - src/__tests__/ITAMReportsPanelTenantRule.test.tsx
findings:
  critical: 0
  warning: 1
  info: 1
  total: 2
status: issues_found
---

# Phase 78: Code Review Report

**Reviewed:** 2026-11-17
**Depth:** standard (incremental: the second review-fix round, 8fcc59a69..042b9a814)
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Scope was `git diff b4e56c386 HEAD` over the 14 listed files, read together with the callers and the other reason-code consumers. `ReportsPanel.tsx` was read from HEAD; the user's one deleted eslint-disable line is not reported. Line numbers for `ReportsPanel.tsx` below are HEAD numbers (the working copy is one line shorter after the `[focusReportKey]` effect).

All six prior findings are really fixed. I ran `tests/test_itam_cost_parity.py` and `tests/test_itam_cost_service.py` in the main checkout: 82 passed.

Checks that came out clean:
- Every consumer of the reason codes. `REASON_CODES` feeds only the summary `coverage.reasons` counters (`itam_cost_service.py:276-281`), and `valued + sum(reasons) == total` still holds because the new key is counted. The only other reader is the Asset value report's Reason column, which prints the raw code (`itam_reporting_prebuilt.py:141`). The KPI tile, the custom-report book-value column (`itam_reporting_filters.py:279`) and the KPI aggregates all go through `compute_asset_cost`, so they inherit the new code. The frontend maps codes in one place only (`FinancePanel.tsx:14-18`).
- `SELECT_TENANT_RE` has exactly two users (`ItamKpiPanel.tsx:120`, `ReportsPanel.tsx:38`). No other string in the ITAM routes starts with "Unknown tenant". The only other backend hit is `role_contents.py:145`, a different surface.
- The widened existence check does not weaken tenant isolation. A partner id now gets the same 400 as an unknown id, before `set_tenant_id`.

One new defect: the per-asset book-value route still has a branch that returns the wrong reason code. The refactor made that branch always wrong. The parity test does not cover it.

## Prior findings re-assessed

| ID | Verdict | Evidence |
|----|---------|----------|
| WR-06 (route vs cost list disagree on salvage above cost) | Fixed for the salvage case. The "one check, cannot disagree" claim is wider than what is true (see WR-07). | The shared predicate is `itam_cost_service.py:92-103`. The cost row calls it at `:142`. The route calls it at `itam_finance_endpoints.py:166-168`, so a model whose salvage exceeds the cost no longer reaches `compute_book_value`. Boundary: `salvage == cost` passes (strict `>`), and `cost == 0` with `salvage > 0` is refused. `test_salvage_above_cost_route_and_row_agree` (`test_itam_cost_parity.py:218-230`) drives the real route function against the real row for `N-SALVAGE` and `N-NOMODEL`. It passes here. |
| IN-12 (reason code reused for salvage above cost) | Fixed. | `REASON_SALVAGE_EXCEEDS_COST` is at `itam_finance_service.py:49`. It is in `REASON_CODES` (`itam_cost_service.py:42`), so `coverage.reasons` counts it. `FinancePanel.tsx:14-18` maps all three codes, and an unknown code falls back to a generic line at `:162`. `ItamBookValue.reason` is typed `string`, so no type change was needed. The Reason column in the Asset value report shows the raw code, as for its siblings. The fixer disclosed this and it is acceptable. |
| WR-05 (stale preview or save tenant rejection re-thrown to the builder toast) | Fixed. | `ReportsPanel.tsx:194-198` and `:216-220`. Any tenant-rejection error is swallowed; only a current one (`seq` or `epoch` unchanged) reaches `takeTenantRejection`. Non-tenant errors still re-throw to the builder toast. The builder's toast is the same `utils/toast` module the tests mock (`ReportBuilderForm.tsx:8,143,152`), so `expect(showToast).not.toHaveBeenCalled()` is a real assertion. |
| IN-10 (delete handler read `pending` and `shown` from the render closure) | Fixed. | `pendingRef` is at `:51-55`. Every former `setPending` call now goes through `setPendingRun` (`:75,126,146,168,185` and the handler). After the await, the handler reads `pendingRef.current` (`:238`) and clears `shown` with a functional `setShown` (`:236`). I traced both orderings of response and delete; neither leaves a stale report or a stuck "Loading". The ref is written synchronously with the state, so it cannot lag the state. |
| IN-11 (new "Unknown tenant" 400 not treated as blocked on the frontend) | Fixed. | `ItamKpiPanel.tsx:94` is now `/^(Select a tenant|Unknown tenant)/i`. Both users pick it up (`:120`, `ReportsPanel.tsx:38`). The server text is still matched only, never rendered. Tests are at `ITAMKpiPanel.test.tsx` (new case) and `ITAMReportsPanelTenantRule.test.tsx` (new case). |
| IN-13 (existence check accepted partner organization rows) | Fixed. | `itam_tenant_scope.py:51` filters `{"id": tenant_id, "type": {"$ne": "partner"}}`, the same filter as `plan_service.py:126`. `partner_store.PARTNER_TYPE` is `"partner"`, so the literal matches. The check still runs before `set_tenant_id`, and for the header case only. The new test covers all 7 report routes plus a cost route, and checks that nothing is written to `itam_reports` or `itam_report_exports`. |

## Warnings

### WR-07: The book-value route maps an unreadable purchase date to "no depreciation policy" and does not guard an unreadable cost

**File:** `backend/itam_finance_endpoints.py:170-179` (comment at `:165`; copy at `components/itam/FinancePanel.tsx:14-18`)
**Issue:** WR-06 put the policy check in one predicate and the comment at `:165` now says the cost list and this route "cannot disagree about one asset". They still can, and the refactor made one branch certainly wrong.
- Once `policy_misfit_reason` has passed, `usefulLifeYears` is a positive int (`_is_life`). The only remaining source of `ValueError` from `compute_book_value` is therefore the unparseable `purchaseDate` (`itam_finance_service.py:93-96`).
- The `except ValueError` at `:178-179` still returns `REASON_NO_DEPRECIATION_POLICY`. The cost row for the same asset says `unreadable_purchase_date` (`itam_cost_service.py:153-154`).
- The Finance tab then shows "No depreciation policy set on this asset's Model." for an asset whose model is fine and whose date is bad. That is the same misdirection IN-12 was fixed for.
- The new `BOOK_VALUE_REASON_COPY` has no entry for `unreadable_purchase_date` or `unreadable_purchase_cost`, so once the route is corrected these codes would fall through to the generic line.
- The cost service also guards a non-integer or negative cost (`REASON_UNREADABLE_COST`, `:138`) and catches `TypeError` (`:153`). The route does neither. `policy_misfit_reason` skips the salvage comparison when the cost is not `_is_cents`, and `compute_book_value` then raises `TypeError` on a string cost, which the route does not catch. That is a 500 where the list shows `unreadable_purchase_cost`.
- The route also has no lifecycle rule: a disposed or retired asset gets a figure here, while the list says `disposed` or `retired`.
- The API models validate the cost as an int `>= 0` and the date as ISO-8601 (`AssetPurchaseUpdate`, `itam_models.py:149-161`). A bad value can only arrive through another write path such as an import, so this is rare. When it happens, the wrong reason or a 500 is what the user sees.

**Fix:** Use the cost service's own reason for the date and make the route's cost guard match:
```python
# itam_finance_endpoints.py
from itam_cost_service import REASON_UNREADABLE_COST, REASON_UNREADABLE_DATE, _is_cents, policy_misfit_reason
...
    cost = asset.get("purchaseCostCents")
    if cost is not None and not _is_cents(cost):
        return {**base, "bookValueCents": None, "reason": REASON_UNREADABLE_COST}
    ...
    except (ValueError, TypeError):
        return {**base, "bookValueCents": None, "reason": REASON_UNREADABLE_DATE}
```
Also add both codes to `BOOK_VALUE_REASON_COPY` ("The purchase date on this asset cannot be read." and similar). Keep the lifecycle difference (a disposed asset still shows its figure on the asset's own tab) only if that is intended, and narrow the `:165` comment to say what is actually shared. A cleaner option is to export a public `is_cents` instead of importing the underscore name.

## Info

### IN-14: The new parity test checks route against row for two assets only, so the remaining disagreements in WR-07 stay invisible

**File:** `backend/tests/test_itam_cost_parity.py:218-230`
**Issue:** `test_salvage_above_cost_route_and_row_agree` compares the route and the list row for `N-SALVAGE` and `N-NOMODEL`. The same seeded set already has `N-BADDATE` (`unreadable_purchase_date`) and `N-MALCOST` (`unreadable_purchase_cost`). Those are exactly the two assets where the route and the list differ (WR-07), and the test skips them. `_expected_book_values` (`:95-100`) also re-implements the `salvage > cost` rule instead of using an independent oracle. That is fine as a golden, but it means the test checks the code against itself on this branch, and the route comparison is the only independent check.
**Fix:** Loop over every non-valued tag in `NOT_TRACKED` and assert the route reason equals the row reason. For the two states the route must not 500, use a known divergence list if the lifecycle difference is kept on purpose. By the code reading in WR-07 such a loop would fail for `N-BADDATE` (and raise or differ for `N-MALCOST`); I did not run it.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
