---
phase: 78-organization-endpoint-cost-api
fixed_at: 2026-11-17T10:05:00Z
review_path: .planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 78: Code Review Fix Report

**Fixed at:** 2026-11-17
**Source review:** `.planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md` (round e828b2d0a..517b219c8: WR-05, WR-06, IN-10, IN-11, IN-12, IN-13). The "Prior findings re-assessed" table was context only and was not re-fixed.
**Iteration:** 1
**Where it ran:** the main checkout on branch `npx` (`workflow.use_worktrees` is `false`, and the user's uncommitted work lives there). No worktree, no temp branch, no sentinel. All tests and the vite build ran in the main checkout, so they include the user's uncommitted work.

**Summary:**
- Findings in scope: 6
- Fixed: 6 (5 commits; WR-06 and IN-12 share one commit because the shared predicate and the new reason code are one change)
- Skipped: 0

## Fixed Issues

### WR-06: Salvage above cost made the cost API disagree with the per-asset Finance route

**Status:** fixed: requires human verification (logic change: which assets are valued)
**Commit:** 8fcc59a69 (shared with IN-12)
**Files modified:** `backend/itam_cost_service.py`, `backend/itam_finance_service.py`, `backend/itam_finance_endpoints.py`, `backend/tests/test_itam_cost_parity.py`, `backend/tests/test_itam_cost_service.py`
**Applied fix:** kept the IN-03 rule and put the policy-fit check in one predicate, `itam_cost_service.policy_misfit_reason(model_doc, purchase_cost)`. It returns a reason code or `None`. `compute_asset_cost` and the per-asset `GET /api/assets/{id}/book-value` route both call it, so they cannot drift. The route's old inline check (`is None` on life and salvage) is gone.
- Behaviour change on the route beyond salvage-above-cost: the route's "no policy" test is now the cost service's stricter one (`usefulLifeYears` must be an int above 0, `salvageValueCents` an int at or above 0, neither a bool). A model with a float or string life or salvage, or a life of 0, now returns `no_depreciation_policy_assigned` from the route, as the cost list already did. Before, the route either computed a figure or hit `compute_book_value`'s own error handling. No existing test relied on the lenient form.
- Parity tests: `test_itam_cost_parity.py` gets a `model-hi` model (salvage 150000) and an `N-SALVAGE` asset (cost 100000), so the KPI tile, report, summary and list all carry it. New `test_salvage_above_cost_route_and_row_agree` compares the route and the list row for `N-SALVAGE` and for `N-NOMODEL`. Per the review's own golden row, the old route returned a book value above cost for this asset, so the new test fails against the pre-fix route.
- The IN-03 golden rows in `test_itam_cost_service.py` now expect the new code.

### IN-12: The reason code reused for salvage above cost told the user to fix something that is not wrong

**Status:** fixed
**Commit:** 8fcc59a69 (shared with WR-06)
**Files modified:** `backend/itam_finance_service.py`, `backend/itam_cost_service.py`, `components/itam/FinancePanel.tsx`, `src/__tests__/FinancePanel.test.tsx` (plus the backend tests listed under WR-06)
**Applied fix:** new code `REASON_SALVAGE_EXCEEDS_COST = "salvage_exceeds_cost"` next to its two siblings in `itam_finance_service.py`, added to `REASON_CODES` in `itam_cost_service.py` after `no_depreciation_policy_assigned` (so the summary's `coverage.reasons` carries a count for it).
- The only frontend place that maps reason codes to copy is `FinancePanel.tsx` (grep of `components`, `services`, `types.ts`, `App.tsx`, `src`). Its two-way ternary is now a `BOOK_VALUE_REASON_COPY` map: `salvage_exceeds_cost` reads "Salvage value on this asset's Model is higher than its purchase cost." A code the map does not know shows "Book value is not available for this asset." (before, any unknown code claimed "No depreciation policy set"). `ItamBookValue.reason` in `types.ts` is `string`, so no type change was needed.
- The Asset value report's Reason column prints the raw code for every reason (`itam_reporting_prebuilt.py`, `_dash(c["reason"])`), and no frontend code maps those cells. I left that as is, so the new code appears raw there like its siblings. Say so if you want the report cells turned into sentences; that would be a separate change.
- `FinancePanel.test.tsx` has a new table test for all three codes plus an unknown code (4 rows).

### IN-13: The existence check accepted partner organizations

**Status:** fixed
**Commit:** 7f2f77728
**Files modified:** `backend/itam_tenant_scope.py`, `backend/tests/test_itam_custom_report_tenant.py`
**Applied fix:** the lookup is now `tenants.find_one({"id": tenant_id, "type": {"$ne": "partner"}}, {"_id": 1})`, as in `plan_service.py`, with the module docstring updated. New test `test_owner_header_for_a_partner_organization_is_400_like_an_unknown_tenant` inserts a `type: "partner"` tenant row and checks all 7 report routes plus a cost route return the same 400 and `UNKNOWN_TENANT_DETAIL`, and that nothing is written to `itam_reports` or `itam_report_exports`. I confirmed it fails with the filter removed, then restored the filter.

### IN-11: The "Unknown tenant" 400 was not a blocked state on the frontend

**Status:** fixed
**Commit:** 7bdc6603f
**Files modified:** `components/itam/ItamKpiPanel.tsx`, `src/__tests__/ITAMKpiPanel.test.tsx`, `src/__tests__/ITAMReportsPanelTenantRule.test.tsx`
**Applied fix:** `SELECT_TENANT_RE` is now `/^(Select a tenant|Unknown tenant)/i`. Its only two users are `ItamKpiPanel.tsx` (the KPI panel's rejected state) and `ReportsPanel.tsx` (`takeTenantRejection`), so both surfaces get the same blocked state with no further change. The backend message text is unchanged. The blocked-state copy still says "Select a tenant ...", which reads correctly for a deleted or stale tenant. New tests: KPI panel shows the Select block and not the failure tiles for an "Unknown tenant" rejection; Reports tab disables Run Report and Create Custom Report, shows the note, raises no toast and never renders the server text.

### WR-05: A stale preview or save failure was re-thrown to the builder toast

**Status:** fixed
**Commit:** 5e1e13a4c
**Files modified:** `components/itam/ReportsPanel.tsx`, `src/__tests__/ITAMReportsPanelTenantRule.test.tsx`
**Applied fix:** a module-level `isTenantRejection(err)` matcher (also used by `takeTenantRejection`). In `handlePreviewCustom` and `handleSaveCustom`, a tenant-rejection error is always swallowed: a current one (`seq` or `epoch` unchanged) goes through `takeTenantRejection`, a stale one is dropped silently; every other error re-throws as before and reaches the builder's toast. Two new tests hold a preview and a save, switch tenant, reject the held call with the 400, and assert no toast, no blocked note and an enabled Run Report. Both failed against the pre-fix code (run before the fix, 2 failed, 31 passed) and pass after.

### IN-10: `handleDeleteConfirm` read `pending` and `shown` from the render-time closure

**Status:** fixed
**Commit:** 042b9a814
**Files modified:** `components/itam/ReportsPanel.tsx`, `src/__tests__/ITAMReportsPanelStaleResponse.test.tsx`
**Applied fix:** the in-flight run lives in `pendingRef`, written together with the state by a new `setPendingRun` helper that replaced every `setPending(...)` call. After the await, the delete handler reads `pendingRef.current` for the IN-07 cancel and clears `shown` with a functional `setShown`. Two deterministic tests, both failing against the pre-fix code (2 failed, 15 passed) and passing after:
- a run of another report started during the delete round trip is kept (the old code bumped `runSeq` and dropped it);
- a run of the deleted report started during the round trip is cancelled (the old code missed it).

## Skipped Issues

None.

## Verification

Run in the main checkout, which includes the user's uncommitted work.

- Backend (the full named list from the brief, plus `test_itam_audit.py` and `test_itam_finance_warranty.py`, which import `itam_finance_endpoints`): **409 passed, 0 skipped** (`-rs` printed no skips). Before the new tests the same list was 363 + 45 passed; the +1 is the IN-13 test, and the WR-06 test replaced no existing one (the parity file counts 8 in its own run, up from 7).
- Frontend: `ITAMKpiPanel`, `ITAMConsole`, `ITAMReportsPanel`, `ITAMReportsPanelStaleResponse`, `ITAMReportsPanelTenantRule` and `FinancePanel`: **6 files, 139 tests passed**.
- Build: `npx vite build --outDir .../scratchpad/vite-78fix --emptyOutDir` built cleanly in 3.34 s. `dist-new/index.html` md5 before and after: `13c235ddca4e2970e5a9fc0260d799ad` (unchanged).
- `test_itam_reporting_export.py` and the other tests wrote nothing I committed; the `backend/static` files in `git status` are the user's or the pre-existing leak.

## User work-in-progress check

- `ReportsPanel.tsx` is the only file I touched that holds user WIP (the deleted `// eslint-disable-next-line react-hooks/exhaustive-deps` above `}, [focusReportKey]);`). For both commits touching it (5e1e13a4c, 042b9a814) I built the index blob from `git show HEAD:components/itam/ReportsPanel.tsx` plus my edits and used `git update-index --cacheinfo`, with the file mode kept. The user's hunk is not in either commit; after each commit `git diff HEAD -- components/itam/ReportsPanel.tsx` shows exactly that one removed line. The working copy of the file has both my edits and the user's deletion.
- Every other file I committed had no uncommitted changes of the user's before my edit, so those were staged normally with `git add <named files>`: the five backend files and `FinancePanel.tsx`, `FinancePanel.test.tsx`, `ItamKpiPanel.tsx`, `ITAMKpiPanel.test.tsx`, `ITAMReportsPanelTenantRule.test.tsx`, `ITAMReportsPanelStaleResponse.test.tsx`, `itam_tenant_scope.py`, `test_itam_custom_report_tenant.py`. `ITAMConsole.test.tsx` and `ITAMReportsPanel.test.tsx` (user WIP) were only run, never edited. `App.tsx`, `services/apiService.ts`, `backend/itam_models.py` and `utils/permissions.ts` were not touched.
- After the last commit: `git diff --cached` is empty; `git diff --numstat | sort` is byte-identical to the snapshot `wip-numstat-before-78fix2.txt` (empty `diff`), including `components/itam/ReportsPanel.tsx` (0 added, 1 deleted) and `src/__tests__/ITAMReportsPanel.test.tsx` (4/3). No stash, checkout, restore, reset, `commit -a`, `--no-verify`, push or Co-Authored-By trailer was used. `git stash list` shows 2 entries that were there before this run.
- The live `omni_platform` database was not touched, no service was restarted, nothing was deployed.

## Needs human verification

1. WR-06 is a logic change: an asset whose model salvage is above its purchase cost now shows "Salvage value on this asset's Model is higher than its purchase cost." on the Finance tab, and no book value, where it used to show a figure above cost. That matches the cost list, KPI tile and report, but the Finance tab number disappearing for such assets is a visible change.
2. The per-asset route now applies the stricter policy-type check (see WR-06). If a live model has a non-integer life or salvage, its Finance tab changes from a figure or an error to "No depreciation policy set". Worth one look at the live `asset_models` data, read-only.
3. The UI changes (FinancePanel copy, blocked state on "Unknown tenant", WR-05, IN-10) are in `dist-new` only after the next UI build and publish, which I did not do.
4. The partner-organization 400 uses the same "Unknown tenant" text as a missing one, as the review's fix suggested.

---

_Fixed: 2026-11-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
