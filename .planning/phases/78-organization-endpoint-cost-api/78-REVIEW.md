---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T10:30:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - backend/itam_cost_endpoints.py
  - backend/itam_cost_service.py
  - backend/itam_kpi_endpoints.py
  - backend/itam_reporting_endpoints.py
  - backend/itam_reporting_kpis.py
  - backend/itam_reporting_prebuilt.py
  - backend/itam_tenant_scope.py
  - backend/tests/test_itam_cost_assets.py
  - backend/tests/test_itam_cost_endpoints.py
  - backend/tests/test_itam_cost_isolation.py
  - backend/tests/test_itam_cost_service.py
  - backend/tests/test_itam_custom_report_tenant.py
  - backend/tests/test_itam_kpi_cost_rules.py
  - backend/tests/test_itam_report_cost_rules.py
  - components/itam/ITAMConsole.tsx
  - components/itam/ReportsPanel.tsx
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
  - src/__tests__/ITAMReportsPanelTenantRule.test.tsx
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 78: Code Review Report (review-fix round e828b2d0a..517b219c8)

**Reviewed:** 2026-11-17
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Incremental review of the 8-finding fix round (`git diff bbe3cb55b HEAD`, committed HEAD content only; the user's uncommitted eslint-disable deletions in `ReportsPanel.tsx` and `ITAMConsole.test.tsx` were not reviewed). All 8 prior findings are really addressed in the code. IN-06 is the one exception to "verified": it rests on the user's read-only DB check that the fixer relayed and did not re-run, and I did not re-run it either.

No tenant-isolation regression. The new tenants lookup runs only for an Owner session that supplies a header, after the empty/platform-admin check. `tenants` is in `TENANT_ISOLATION_EXEMPT_COLLECTIONS` (`backend/database.py:33`), so the ambient tenant that `TenantMiddleware` already set from the header cannot hide it. All 13 call sites of `resolve_itam_tenant` are awaited and pass `get_database`. A grep of `backend/` outside tests found no other caller.

Two new defects came out of the fixes:
- The IN-03 change creates a cross-surface disagreement with the per-asset Finance route.
- The IN-08 catch blocks re-throw a stale "Select a tenant" failure into a toast.

### Prior findings re-assessed

| ID | Verdict | Evidence |
|----|---------|----------|
| WR-03 | Fixed (user's "stable markers" decision) | `itam_cost_service.py:322` runs `mark_possible_duplicates(assets)` over every asset `load_tenant_assets` returned (no lifecycle filter, `:130-133`). The markers are applied only to `in_scope` rows (`:323-326`). `compute_asset_cost_detail` (`:348`) goes through the same function, so list (both scopes) and detail agree. The summary pair rule is implemented in `summarize_cost_rows` (`:269-281`): a pair counts once when at least one member is an in-scope row, built from `possibleDuplicateOf`. `test_markers_are_stable_when_the_twin_is_retired` asserts list under both scopes, detail for both ids, and the pair and flag counts. `test_pair_of_two_out_of_scope_assets_is_not_counted_by_default` pins the pair rule. Not tautological. |
| IN-01 | Fixed | `itam_tenant_scope.py:34-53`. `from_header` is true only for an Owner session with a non-blank header. The "Select a tenant" 400 precedes any DB call, then the `tenants.find_one` lookup, then 400 `UNKNOWN_TENANT_DETAIL`. `set_tenant_id` runs only after success. Tenant users and API keys never trigger the lookup. The detail is a fixed string, so the typo id is not echoed (asserted in `test_owner_header_for_an_unknown_tenant_is_400`). No sync caller is left. Tests cover all 7 custom report routes, 3 cost routes, the KPI route, and prebuilt run and export, and assert nothing was written to `itam_reports` or `itam_report_exports`. See IN-11 and IN-13 for edge behaviour. |
| IN-02 | Fixed | `normalize_lifecycle_status` (`itam_cost_service.py:90-93`) is used at `:104`, at `itam_reporting_prebuilt.py:126` and at `itam_reporting_kpis.py:47`. No remaining raw `lifecycleStatus` hashing in the cost, KPI or asset-value paths (the `_dash(...)` renders at `itam_reporting_prebuilt.py:84` and `:222` do not hash; `:222` reads the normalized row). Tests for the list and dict status are meaningful: the report test asserts the exact included tags, the KPI test asserts the counts. |
| IN-03 | Fixed as designed, but see WR-06 | The `model_doc["salvageValueCents"] > raw_cost` guard (`itam_cost_service.py:130-132`) is safe from TypeError: the earlier `_is_cents` terms short-circuit, and `raw_cost` is already proven a non-bool int at that branch. Equal salvage and cost is still valued. The asset stays priced. The golden test pins both the finance figure (unchanged, above cost) and the new unvalued row. The change introduces the cross-surface disagreement in WR-06. |
| IN-06 | Resolved without code, accepted on a claim | No code change. The evidence is the user's check, relayed by the fixer, that live `omni_platform` has no `itam_reports` collection. Neither the fixer nor this review re-ran it. Consistent with the earlier review's own "if zero, record that" branch. |
| IN-07 | Fixed for the stated case, with a residual: IN-10 | `ReportsPanel.tsx:221` bumps `runSeq` and clears `pending` when the pending run is for the deleted report. The test holds `runItamCustomReport`, deletes, then resolves and asserts no rows, no Loading line and no export buttons. Not tautological: a landing late response would paint `IT-GONE`. |
| IN-08 | Fixed for the failure-handled path, with one gap: WR-05 | `takeTenantRejection` (`ReportsPanel.tsx:62-71`) now also bumps `runSeq` and clears `pending` and `shown`. Preview, save and delete route through it (`:184-187`, `:204-206`, `:227`). The 3 new tests plus the "other failure still toasts" test are meaningful, since the blocked note is asserted and `showToast` is not called. Stale failures are not covered: WR-05. |
| IN-09 | Fixed | `ITAMConsole.tsx:85`: `needsTenant = isPlatformView && !tenantId`. The only production caller (`App.tsx:1922`) passes `isPlatformView={isPlatformRoleName(currentUser.role)}`. `isSuperAdminRoleName` implies `isPlatformRoleName` (`utils/permissions.ts:63-79`, `super_admin` is the `owner` tier), so no role loses the block. `isSuperAdminView` is still used by the Lifecycle and Finance tabs (`:136-137`). All 13 test renders now pass `isPlatformView`. |

WR-01, WR-02, WR-04, IN-04 and IN-05: no regression found. The tenant-switch effect and the `tenantEpoch` guards are unchanged. The new `runSeq` bump in `takeTenantRejection` does not affect them.

## Warnings

### WR-05: A stale preview or save failure is re-thrown to the builder toast, rendering the server's "Select a tenant" text for the wrong tenant

**File:** `components/itam/ReportsPanel.tsx:184-188` and `:204-207`
**Issue:** IN-08 added a `catch` that only swallows a "Select a tenant" error when the request is still current:
- Preview: `if (seq === runSeq.current && takeTenantRejection(e)) return; throw e;`
- Save: `if (epoch === tenantEpoch.current && takeTenantRejection(e)) return; throw e;`

When the request is stale, the guard is false and the same error is re-thrown. The builder (`ReportBuilderForm.tsx:141-146` and `:151-156`) turns it into `showToast(e.message, 'error')`. A superseded preview, or a save or preview begun under the previous tenant, that fails with the 400 therefore shows the raw server string "Select a tenant: ITAM figures cover one organization at a time." in a toast, in the new tenant's context. That breaks two things:
- The T-78-07 / T-78-39 rule that the matched detail is never rendered.
- The intent of the guard, which was that a stale failure should not affect the new tenant.

The builder is not unmounted by a tenant switch, so the toast does reach the user. The fixer's tests cover only the current-request path.
**Fix:** Drop a stale failure that matches the tenant message, and re-throw only other errors:
```tsx
} catch (e) {
  if (SELECT_TENANT_RE.test(e instanceof Error ? e.message : '')) {
    if (seq === runSeq.current) takeTenantRejection(e);   // stale: ignore silently
    return;
  }
  throw e;
}
```
Apply the same shape to `handleSaveCustom` with the `epoch` check. Add a test: hold a preview, switch tenant, reject the held preview with the 400, then assert no toast and no blocked note.

### WR-06: Salvage above cost now makes the cost API disagree with the per-asset Finance route for the same asset (parity broken, no test)

**File:** `backend/itam_cost_service.py:126-133`; `backend/itam_finance_endpoints.py:164-180`; `components/itam/FinancePanel.tsx:155`
**Issue:** IN-03 marks such an asset unvalued in the cost service. That feeds the cost list, summary, KPI tile and Asset value report. The per-asset `GET .../{id}/book-value` route has its own copy of the policy check (it does not use the cost service). It still calls `compute_book_value` and returns a figure above the purchase cost (the golden test shows 150000 on a 100000 purchase). The Finance tab therefore shows a book value for an asset that the KPI tile, report totals and cost list exclude as "no policy". `test_itam_cost_parity.py` states "the per-asset book-value route must agree with the list row" (docstring, lines 5-6). Its `MODELS` has no salvage-above-cost case, so the broken invariant is not caught. The fixer treated the finance function as untouchable and did not look at the route. The user-facing totals are internally consistent, but the same asset gets two answers on two screens.
**Fix:** Pick one rule and apply it everywhere:
- Either route the finance endpoint through `itam_cost_service.compute_asset_cost` (or share one predicate, e.g. `policy_fits(model_doc, cost)`) so it also returns `REASON_NO_DEPRECIATION_POLICY`.
- Or revert IN-03 and keep the "never clamps, never marks" rule.

Add a salvage-above-cost row to `MODELS`/the parity table so the route and the list row are compared.

## Info

### IN-10: `handleDeleteConfirm` reads `pending` and `shown` from the render-time closure

**File:** `components/itam/ReportsPanel.tsx:219-222`
**Issue:** The IN-07 check `pending?.kind === 'custom' && pending.key === target.id` runs after `await deleteItamCustomReport(...)`, but `pending` and `shown` are values captured when the confirm handler's render happened. Two consequences:
- If the pending run finished during the delete round trip, the closure still says pending. Bumping `runSeq` is then harmless, but if a run of another report started in that window, the bump drops its result and clears its Loading line.
- A run of the deleted report started during the round trip (if the Run button is reachable under the modal) is not cancelled.

Both windows are narrow, and the `shown` check has the same pre-existing shape.
**Fix:** Keep the in-flight run in a ref (`pendingRef.current = {kind, key}`, set where `setPending` is called) and read the ref after the await.

### IN-11: The new "Unknown tenant" 400 is not treated as a blocked state on the frontend

**File:** `components/itam/ItamKpiPanel.tsx:92` (`SELECT_TENANT_RE = /^Select a tenant/i`), `components/itam/ReportsPanel.tsx:62-71`
**Issue:** `UNKNOWN_TENANT_DETAIL` ("Unknown tenant: ...") does not match `SELECT_TENANT_RE`. An Owner whose selected tenant has been deleted or is stale gets the server string in an error toast on every Reports action. The KPI panel gets its generic error state. The tab stays enabled and keeps retrying. The text is a fixed server string rendered through `showToast` as plain text, so there is no injection risk. It is a UX gap in the new contract, and the fixer's own follow-up list names this contract change.
**Fix:** Either extend the regex to `^(Select a tenant|Unknown tenant)` so both land in the blocked state, or have the app reset `viewingTenantId` on this 400.

### IN-12: The reason code reused for salvage above cost tells the user to fix something that is not wrong

**File:** `backend/itam_cost_service.py:126-133`, `components/itam/FinancePanel.tsx:155`
**Issue:** An asset whose model has a complete policy now reports `no_depreciation_policy_assigned`. The Asset value report prints that raw code, and anything that renders the reason as "No depreciation policy set on this asset's Model" is wrong for this case. The user opens the Model, finds a policy, and cannot tell that the fix is lowering the salvage value. The fixer acknowledged the looseness.
**Fix:** Add a distinct code (for example `salvage_exceeds_cost`) to `REASON_CODES` and the label maps. Or document the overload in the report's Reason column help text.

### IN-13: The existence check accepts any `tenants` row, including partner organizations

**File:** `backend/itam_tenant_scope.py:51`
**Issue:** `tenants.find_one({"id": tenant_id}, ...)` does not filter on `type`. `tenants` also holds `type: "partner"` rows (see `partner_pool.py:53`, `plan_service.py:126`). An Owner header naming a partner organization passes, and custom reports or exports can then be written under an id that is not a customer tenant. The earlier IN-01 concern was a fabricated id. This is the same shape with a real but non-customer id. The impact is small because it is Owner-only and the reports are empty.
**Fix:** Add `"type": {"$ne": "partner"}` to the lookup, as `plan_service.py:126` does. Add a test row for a partner tenant.

---

_Reviewed: 2026-11-17T10:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
