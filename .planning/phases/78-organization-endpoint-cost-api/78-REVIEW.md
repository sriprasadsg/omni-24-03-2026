---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - App.tsx
  - backend/catalogue_mounts_assets.py
  - backend/itam_cost_endpoints.py
  - backend/itam_cost_service.py
  - backend/itam_kpi_endpoints.py
  - backend/itam_reporting_endpoints.py
  - backend/itam_reporting_filters.py
  - backend/itam_reporting_kpis.py
  - backend/itam_reporting_prebuilt.py
  - backend/itam_tenant_scope.py
  - backend/router_registry.py
  - backend/tests/test_catalogue_slice_assets.py
  - backend/tests/test_itam_cost_assets.py
  - backend/tests/test_itam_cost_endpoints.py
  - backend/tests/test_itam_cost_isolation.py
  - backend/tests/test_itam_cost_parity.py
  - backend/tests/test_itam_cost_scale.py
  - backend/tests/test_itam_cost_service.py
  - backend/tests/test_itam_kpi_cost_rules.py
  - backend/tests/test_itam_report_cost_rules.py
  - backend/tests/test_itam_reporting_kpis.py
  - components/itam/ITAMConsole.tsx
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportsPanel.tsx
  - services/apiService.ts
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMKpiPanel.test.tsx
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 78: Code Review Report

**Reviewed:** 2026-11-17
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Scope: the Phase 78 diff (`fd4e00f24..HEAD`) of the cost service, cost routes, tenant resolver, the KPI / Asset value report rewiring, and the ITAM console UI. The large pre-existing files (App.tsx, apiService.ts, ReportsPanel.tsx) were reviewed only where the phase touched them. The user's uncommitted working-tree hunks were not reviewed.

The core is sound:
- The resolver reads `X-Tenant-ID` itself, Owner-only and session-only, and refuses a platform or empty tenant with 400 before any read.
- `require_tenant` plus the explicit `tenantId` filters keep every read to one tenant.
- Cost math is delegated to `compute_book_value` unchanged.
- The 404 body is identical for unknown and foreign ids.
- Money stays integer cents, with `None` plus a reason code instead of a fabricated zero.

I found no security vulnerability and no data-loss risk. I confirmed the UI-audit lead as a real bug (WR-01). The Owner-with-tenant flow also leaves the custom-report routes unscoped (WR-02), and the detail route contradicts its own "equals the list row" claim (WR-03).

## Warnings

### WR-01: ReportsPanel `runPrebuilt` has no stale-response guard; the tenant-switch reset does not clear `running` (confirms the 78-UI-REVIEW lead)

**File:** `components/itam/ReportsPanel.tsx:81-107` (render condition at 296 and 332-339)
**Issue:** `runPrebuilt` awaits `runItamPrebuiltReport(key, page, size, tenantId)` and then calls `setResult(r)` unconditionally. Nothing compares the response against the tenant that issued it.
- The tenant-change effect (81-90) clears `result`, `activeKind`, `activeKey` and `page`, but not `running`, and cannot cancel the in-flight request.
- An Owner who runs a report for tenant A and switches to tenant B before it returns gets A's rows written into state after the reset.
- The result block renders on `(running || result)` (line 296) with no `activeKind` check, so A's figures show under tenant B. Only the Export button is disabled, because `canExport` needs `activeKind`.
- This is the exact cross-organization mix-up the R3 comment says must not happen.
- The same pattern applies within one tenant: two quick page clicks can resolve out of order, and the first request's `finally` sets `running=false` while the second is still in flight.

**Fix:** Add a request counter and drop out-of-date responses. Bump it in the tenant-change effect, and also reset `running` there.
```tsx
const runSeq = useRef(0);
// in the tenant-change effect:
runSeq.current += 1;
setRunning(false);
// in runPrebuilt (and runSavedCustom):
const seq = ++runSeq.current;
...
const r = await runItamPrebuiltReport(key, targetPage, PAGE_SIZE, tenantId);
if (seq !== runSeq.current) return;
setResult(r); setPage(targetPage);
...
finally { if (seq === runSeq.current) setRunning(false); }
```
Also make the result block require `activeKind && activeKey`.

### WR-02: Custom report routes are not tenant-resolved, so an Owner gets cross-tenant book values while the cost surfaces return 400

**File:** `backend/itam_reporting_endpoints.py:228, 266, 307, 337` (with `backend/itam_reporting_filters.py:270-285`, `ReportsPanel.tsx:109-120, 218-226`)
**Issue:** Phase 78 routes only `/prebuilt/*/run` and `/prebuilt/*/export` through `resolve_itam_tenant`. The `/custom/preview`, `/custom/{id}/run` and `/custom/{id}/export` routes still use `current_user.tenant_id`.
- For a Platform Owner that is the platform tenant. The database wrapper then skips scoping, because the auth dependency resets the ambient tenant (the trap 78-RESEARCH describes), so the `X-Tenant-ID` the UI never sends could not help anyway.
- `_compute_finance_result` now feeds the `bookValue` column from `compute_asset_cost`, so a custom report is the same cost figure the phase says "covers one organization at a time". For an Owner it returns every tenant's assets blended.
- The UI makes this reachable: `needsTenant` disables only the pre-built Run buttons. Saved-report Run and the builder preview stay enabled.
- The scoping gap predates the phase. The phase made custom reports share the cost computation but left the one-tenant rule (D-13) off this path, so SC3 / D-13 is not met for them.

**Fix:** Call `tenant_id = resolve_itam_tenant(request, current_user)` first in the four custom handlers, with `request: Request` added. Make `runSavedCustom` and the builder preview pass `tenantId`, and disable them while `needsTenant`. If custom reports are intentionally out of scope, record that as an accepted gap in 78-SECURITY.md, because the Owner view currently differs between surfaces.

### WR-03: The cost detail route does not return "the list row"; its duplicate markers differ when the partner asset is disposed or retired

**File:** `backend/itam_cost_service.py:326-338` (claim in the docstring and in 78-03-SUMMARY, A-78-12)
**Issue:** `compute_asset_cost_detail` runs `compute_tenant_costs(include_inactive=True)`. The duplicate marking is done only over in-scope assets, "so pairs follow includeDisposed" (78-03-PLAN).
- An active hand-entered asset whose agent twin is retired therefore has `possibleDuplicateOf: [twin]` and the flag `possibleDuplicate` in the detail response.
- The default list (`includeDisposed=false`) shows `[]` and no flag for that same asset.
- The summary's `possibleDuplicatePairs` also differs by `includeDisposed`.
- The docstring says the detail was built whole-tenant so the markers "equal the list row's". That is false for exactly this case.

**Fix:** Decide the intended contract and make code and docs agree. Either compute markers over all assets and keep them stable across scopes (`marks = mark_possible_duplicates(assets)`, only the rows filtered), or correct the docstring and plan text to say the detail row reflects `includeDisposed=true`. Add a test with a retired twin.

## Info

### IN-01: A fabricated `X-Tenant-ID` from an Owner is accepted and used for writes

**File:** `backend/itam_tenant_scope.py:30-40`; `backend/itam_reporting_endpoints.py:100-130`
**Issue:** The header value is never checked against an existing tenant. A typo or bogus id returns empty 200 figures. The export route (a POST) also writes a report file and an `itam_report_exports` record under that nonexistent `tenantId`. Only the Owner can do this, and no data from a real tenant is exposed.
**Fix:** After choosing the header tenant, confirm it exists (`db.tenants.find_one({"id": header})`) and return 404 / 400 if not. Alternatively, accept that the Owner is trusted and note it.

### IN-02: Asset value report population filter does not normalize `lifecycleStatus` the way `compute_asset_cost` does

**File:** `backend/itam_reporting_prebuilt.py:128-134` (compare `itam_cost_service.py:99-100`)
**Issue:** `compute_asset_cost` deliberately handles a non-string or unhashable stored status ("a list or dict would not even hash"). The report's pre-filter does `(a.get("lifecycleStatus") or DEFAULT) not in INACTIVE_STATUSES`. A list or dict value raises `TypeError: unhashable type`, which `run_prebuilt_report` converts into a 500 for the whole report, and one bad document breaks the export. The two surfaces therefore disagree on malformed data, against the single-computation intent.
**Fix:** Use the same rule in both places, for example a shared `status_of(asset)` helper in `itam_cost_service`.

### IN-03: A salvage value above the purchase cost produces a book value above the purchase cost

**File:** `backend/itam_cost_service.py:130-141` (with `itam_finance_service.compute_book_value:106-109`)
**Issue:** The salvage value lives on the model and the cost on the asset, so they can be inconsistent. If salvage is greater than cost, the annual depreciation goes negative and `max(book, salvage)` returns the salvage. The tile and totals then count a book value higher than the price paid. The module says it "never clamps"; this case is not covered by a reason code.
**Fix:** Either treat `salvage > cost` as `REASON_NO_DEPRECIATION_POLICY` (or a new reason), or cap at `purchaseCostCents` in this module with a comment and a test.

### IN-04: The Run button gate depends only on `isSuperAdminRoleName`; other platform tiers fall through to a toast

**File:** `components/itam/ITAMConsole.tsx:81-82`
**Issue:** `needsTenant = isSuperAdminView && !tenantId`. Platform Support and Billing never get `needsTenant`, so they see enabled Run buttons. The server answers 400 "Select a tenant", and ReportsPanel surfaces it as an error toast. The KPI panel does handle it with `tenantRejected`. The two panels therefore behave differently.
**Fix:** Use `isPlatformRoleName(role)` (already in `utils/permissions.ts`) for `needsTenant`, or pass the same `SELECT_TENANT_RE` handling into ReportsPanel.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
