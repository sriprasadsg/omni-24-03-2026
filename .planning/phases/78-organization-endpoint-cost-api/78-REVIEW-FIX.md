---
phase: 78-organization-endpoint-cost-api
fixed_at: 2026-11-17T09:35:00Z
review_path: .planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 7
resolved_without_code_change: 1
skipped: 0
status: all_fixed
---

# Phase 78: Code Review Fix Report

**Fixed at:** 2026-11-17
**Source review:** `.planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md` (IN-06..IN-09) plus four older open findings (WR-03, IN-01, IN-02, IN-03) taken from the first review revision (`git show 2a58a89a5:.planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md`)
**Iteration:** 1
**Where it ran:** the main checkout on branch `npx` (`workflow.use_worktrees` is `false`, and the user's uncommitted work lives there). No worktree, no temp branch, no sentinel. Verification ran in the main checkout.

**Summary:**
- Findings in scope: 8 (user chose all)
- Fixed with a commit: 7
- Resolved without a code change: 1 (IN-06, by evidence)
- Skipped: 0

## Fixed Issues

### WR-03: Cost detail route does not return "the list row" when the partner asset is disposed or retired

**Status:** fixed: requires human verification (logic change, user decision "stable markers")
**Files modified:** `backend/itam_cost_service.py`, `backend/tests/test_itam_cost_assets.py`
**Commit:** e828b2d0a
**Applied fix:** `compute_tenant_costs` now runs `mark_possible_duplicates` over ALL of the tenant's assets (active and inactive) and then applies the markers to the in-scope rows. A row shows the same `possibleDuplicateOf` and `possibleDuplicate` flag under `includeDisposed` true or false, and in the detail route. Docstrings of `compute_tenant_costs`, `compute_asset_cost_detail` and `summarize_cost_rows` now state this.
**Summary pair rule (written in the `summarize_cost_rows` docstring):** `possibleDuplicatePairs` counts a pair once when at least one of its two assets is an in-scope row. So an active asset with a retired twin counts 1 pair under both scopes. A pair of two out-of-scope assets counts 0 by default and 1 with `includeDisposed=true` (the population differs there, so that difference is inherent). The `flags.possibleDuplicate` count stays the number of in-scope rows carrying the flag (1 by default, 2 with disposed included, for the retired-twin case).
**Tests:**
- Replaced `test_duplicates_scoped_to_rows_in_scope` (it encoded the old scope-dependent behaviour: default list flagged nothing for an active asset with a disposed twin) with `test_markers_are_stable_when_the_twin_is_retired`. It asserts list (both scopes), detail (both the active and the retired asset) and summary agree.
- Added `test_pair_of_two_out_of_scope_assets_is_not_counted_by_default` for the pair rule.
- `test_itam_cost_parity.py`, `test_itam_cost_service.py`, `test_itam_cost_isolation.py` and `test_itam_cost_endpoints.py` passed unchanged (their duplicate cases have both members in scope).

### IN-01: A fabricated `X-Tenant-ID` from an Owner is accepted and used for writes

**Status:** fixed: requires human verification (behaviour change on every ITAM cost, KPI and report route)
**Files modified:** `backend/itam_tenant_scope.py`, `backend/itam_reporting_endpoints.py`, `backend/itam_cost_endpoints.py`, `backend/itam_kpi_endpoints.py`, `backend/tests/test_itam_custom_report_tenant.py`, `backend/tests/test_itam_cost_endpoints.py`, `backend/tests/test_itam_kpi_cost_rules.py`, `backend/tests/test_itam_report_cost_rules.py`, `backend/tests/test_itam_cost_isolation.py`
**Commit:** 32b027786
**Applied fix:** `resolve_itam_tenant` is now `async` and takes the caller's own `get_database` as a third argument (`await resolve_itam_tenant(request, current_user, get_database)` at all 13 call sites). Only when an Owner session's header names the tenant, it runs `db.tenants.find_one({"id": tenant_id}, {"_id": 1})` and returns 400 with the fixed `UNKNOWN_TENANT_DETAIL` ("Unknown tenant: the selected organization does not exist.") when nothing is found. The collection and id field are the ones the rest of the backend uses (`tenants`, `id`; for example `agent_auth.py`, `platform_endpoints.py`, `plan_service.py`; `tenants` is in the wrapper's unscoped list in `database.py`). Tenant users never trigger the lookup, and an Owner with no header still gets the old "Select a tenant" 400 before any database call (the existing "get_database must not be reached" tests still pass). `tenant_middleware.py` is untouched.
**Why the signature changed:** the resolver was synchronous and could not await a database call. Passing the module's `get_database` (looked up at call time) keeps the per-module test patching working and keeps the "no database before the tenant is resolved" guarantee.
**Tests:** new unknown-tenant 400 tests: all seven custom report routes plus a cost route (asserts nothing written to `itam_reports` or `itam_report_exports`), the three cost routes, the KPI route, and the pre-built run and export. Fixtures that send an Owner header now insert the tenant: `seeded` (custom report tenant tests), `_seed` (cost endpoints), `two_tenants` (cost isolation), the KPI owner-header test; two pre-built report tests set `mock_db.tenants.find_one`; `test_resolver_sets_ambient_tenant` got a small fake db with an async `tenants.find_one`.

### IN-02: Asset value report population filter does not normalize `lifecycleStatus`

**Status:** fixed
**Files modified:** `backend/itam_cost_service.py`, `backend/itam_reporting_prebuilt.py`, `backend/itam_reporting_kpis.py`, `backend/tests/test_itam_report_cost_rules.py`, `backend/tests/test_itam_kpi_cost_rules.py`
**Commit:** 9132161f4
**Applied fix:** new `itam_cost_service.normalize_lifecycle_status(raw)` (a non-string or empty value reads as the default status). Used by `compute_asset_cost` (replacing its inline expression), by the Asset value report population filter, and also by the KPI tile's `_status_breakdown`. The review named only the first two places; the tile had the same `counts.get(<list>)` TypeError (a 500 for the whole KPI payload), so it was fixed with the same helper (and its now-unused `DEFAULT_LIFECYCLE_STATUS` import removed).
**Tests:** a list and a dict `lifecycleStatus` no longer fail the report (200, both read as the default status) and no longer fail the KPI tile (counted under `deployable`).

### IN-03: A salvage value above the purchase cost produces a book value above the purchase cost

**Status:** fixed: requires human verification (logic change, design choice below)
**Files modified:** `backend/itam_cost_service.py`, `backend/tests/test_itam_cost_service.py`
**Commit:** 40d52db0a
**Applied fix:** in `compute_asset_cost`, a model whose `salvageValueCents` is greater than the asset's `purchaseCostCents` is treated like an unusable policy: `reason = REASON_NO_DEPRECIATION_POLICY`, `bookValueCents` and `yearsElapsed` stay `None`, the asset stays priced (its purchase cost still counts in the purchase total). `compute_book_value` is unchanged and nothing is capped, so the module's "never clamps" principle holds; the module docstring now says so.
**Reason code choice:** the existing `no_depreciation_policy_assigned` (reused, no new code). Why: it already means "the model's policy cannot be used to value this asset" in every place that renders it, and no frontend place needs a new label. I confirmed the only frontend reader of cost-service reason codes in the source tree is `components/itam/FinancePanel.tsx` (it maps anything other than `no_purchase_record` to "No depreciation policy set on this asset's Model."), and the Asset value report prints the raw code in its Reason column. A new code would have needed a label in each. The wording is slightly loose (a policy exists but does not fit this asset), which is the trade-off. Salvage equal to cost is still valued (book value = cost).
**Tests:** the old golden row `salvage-above-cost-pinned` (which asserted a valued 150000 book value for salvage 150000 on cost 100000) was removed from `GOLDEN`, and a new golden table `GOLDEN_SALVAGE_ABOVE_COST` (3 rows: salvage far above cost, one cent above, cost zero with salvage 1) asserts two things: the finance function's figure is unchanged and above the price paid (100002 and 2 for the one-cent rows, because floor division of the negative annual depreciation also over-shoots salvage), and the cost row is unvalued with the existing reason. `salvage-equals-cost` stays in the original table.

### IN-07: A run in flight for a report is not cancelled when that report is deleted

**Status:** fixed
**Files modified:** `components/itam/ReportsPanel.tsx`, `src/__tests__/ITAMReportsPanelStaleResponse.test.tsx`
**Commit:** febcb5039
**Applied fix:** after a successful delete, if the pending run is for the deleted custom report, `runSeq.current += 1; setPending(null);` (the review's suggestion, applied as written).
**Test:** a held `runItamCustomReport` for the report, then delete and confirm, then resolve the run: no rows, no Loading line, no export buttons. Checked that this test fails against the pre-fix component.

### IN-08: Save, preview and delete do not route a "Select a tenant" 400 through `takeTenantRejection`

**Status:** fixed
**Files modified:** `components/itam/ReportsPanel.tsx`, `src/__tests__/ITAMReportsPanelTenantRule.test.tsx`
**Commit:** 38c018a15
**Applied fix:** `takeTenantRejection` now also clears the run in flight and the shown report (`runSeq.current += 1; setPending(null); setShown(null)`) when it returns true. `handlePreviewCustom` and `handleSaveCustom` got a `catch` that calls it (guarded by the request sequence and the tenant epoch respectively, so a stale failure does not block the new tenant) and rethrows anything else to the builder's toast as before. `handleDeleteConfirm` calls it first in its catch and closes the dialog without a toast. I added the `runSeq` bump (beyond the review's wording) so a response still in flight cannot repaint a blocked tab.
**Tests:** delete, preview and save rejections each block the tab with no toast (the delete one also asserts the shown report and its export buttons are gone); a save failing for another reason still toasts. Checked that these three fail against the pre-fix component.

### IN-09: `needsTenant` repeats a condition the role helper already covers

**Status:** fixed
**Files modified:** `components/itam/ITAMConsole.tsx`, `src/__tests__/ITAMConsole.test.tsx`
**Commit:** 517b219c8
**Applied fix:** `needsTenant = isPlatformView && !tenantId`. `isSuperAdminView` stays for the Lifecycle and Finance tabs. All 13 `<ITAMConsole isSuperAdminView ...>` renders in `ITAMConsole.test.tsx` now also pass `isPlatformView` (what App.tsx passes for a platform role).

## Resolved without a code change

### IN-06: Custom report definitions saved before this change under the Owner's own tenant become unreachable

**Status:** no code change needed (resolved by evidence); no commit, no script
**Evidence (supplied by the user's read-only check on 2026-11-17, not re-run here):** the live `omni_platform` database has no `itam_reports` collection. 0 documents in total, so 0 with `tenantId` equal to `platform-admin`, null or missing. This is the review's own "if it is zero, record that" branch. I did not connect to the live database.

## Skipped Issues

None.

## Verification

Run in the main checkout, named files only, foreground.

- Backend (the full named list from the task, no skips): `340 passed in 129.55s`, with `-rs` printing no skipped tests. Files: `test_itam_custom_report_tenant`, `test_itam_cost_service`, `test_itam_cost_endpoints`, `test_itam_cost_assets`, `test_itam_kpi_cost_rules`, `test_itam_report_cost_rules`, `test_itam_cost_parity`, `test_itam_cost_isolation`, `test_itam_cost_scale`, `test_itam_reporting_kpis`, `test_itam_reporting_prebuilt`, `test_itam_reporting_builder`, `test_itam_reporting_export`, `test_itam_finance_bookvalue`, `test_catalogue_slice_assets`. No other test file imports `resolve_itam_tenant` (the one grep hit, `test_itam_cost_service.py:453`, is a file-name list in a source scan and passed). One mid-run failure was my own wrong expectation in a new IN-03 test row (floor division, see IN-03); fixed before its commit.
- Frontend: `npx vitest run` on `ITAMKpiPanel`, `ITAMConsole`, `ITAMReportsPanel`, `ITAMReportsPanelStaleResponse`, `ITAMReportsPanelTenantRule`: 5 files, 126 tests passed.
- Build check: `npx vite build --outDir <scratchpad>/vite-78fix --emptyOutDir` built in 5.36s. `dist-new/index.html` is byte-identical before and after (md5 checked). `npm run build` was not run.
- Known pre-existing leak: `test_itam_reporting_export.py` left files in `backend/static/reports`; left alone, not committed.

## User work in progress check

Commits were staged by building the index blob from HEAD plus only my edit (`git update-index --cacheinfo`), never `git add` on a file holding user hunks, no `git commit -a`, no stash, no checkout, restore or reset of a working file (one `git reset -q HEAD -- components/itam/ReportsPanel.tsx`, index entry only, to split IN-07 from IN-08). No `--no-verify`, no `Co-Authored-By`, nothing pushed.

- After the last commit, `git diff --numstat` (whole tree) is identical to the snapshot `scratchpad/wip-numstat-before-78fix.txt` (`diff` reports no difference). The index is empty.
- Files that held user WIP and that I touched still show exactly the user's hunks and nothing of mine as unstaged:
  - `components/itam/ReportsPanel.tsx`: only the deleted `// eslint-disable-next-line react-hooks/exhaustive-deps` line above `}, [focusReportKey]);`.
  - `src/__tests__/ITAMConsole.test.tsx`: only the deleted `// eslint-disable-next-line no-bitwise` line.
  - `src/__tests__/ITAMReportsPanel.test.tsx` (not touched by me): still shows the `ComponentProps` / `type Mock` imports and the `onPreview` / `onSave` type changes.
- `App.tsx`, `services/apiService.ts`, `backend/itam_models.py`, `utils/permissions.ts` were not touched.

## Commits

| Finding | Commit |
|---------|--------|
| WR-03 | e828b2d0a |
| IN-02 | 9132161f4 |
| IN-03 | 40d52db0a |
| IN-01 | 32b027786 |
| IN-07 | febcb5039 |
| IN-08 | 38c018a15 |
| IN-09 | 517b219c8 |
| IN-06 | none (no change needed) |

## Follow-ups for the user

- IN-01 changes a contract: an Owner header naming an unknown tenant now returns 400 with the "Unknown tenant" text on every ITAM cost, KPI, report and custom-report route. The frontend shows that text in a toast on the paths that do not treat it as the "Select a tenant" state; it is a fixed server string. The tenants lookup adds one indexed read per Owner request that carries a header.
- IN-03 can change numbers on the live data: any asset whose model salvage exceeds its purchase cost drops out of the book value total and into the `no_depreciation_policy_assigned` reason count. I did not query the live data.
- Backend and UI changes need a restart and a publish to go live; neither was done.

---

_Fixed: 2026-11-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
