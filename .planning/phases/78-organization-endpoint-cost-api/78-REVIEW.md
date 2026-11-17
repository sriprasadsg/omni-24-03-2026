---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - App.tsx
  - backend/itam_reporting_endpoints.py
  - backend/itam_tenant_scope.py
  - backend/tests/test_itam_custom_report_tenant.py
  - components/itam/ITAMConsole.tsx
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportResultView.tsx
  - components/itam/ReportsPanel.tsx
  - services/apiService.ts
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMReportsPanel.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
  - src/__tests__/ITAMReportsPanelTenantRule.test.tsx
findings:
  critical: 0
  warning: 0
  info: 4
  total: 4
status: issues_found
---

# Phase 78: Code Review Report (incremental, after gap round 2: plans 78-12..78-15)

**Reviewed:** 2026-11-17
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Incremental review of the committed (HEAD) changes since c16cdf34c for gap round 2. The user's uncommitted hunks (password-modal work in `App.tsx` and `services/apiService.ts`, the removed lint comment in `ReportsPanel.tsx`, test typing tweaks) were not reviewed and are not reported.

All five targeted findings (WR-01, WR-02, WR-04, IN-04, IN-05) are now fixed. No new critical issue and no new warning was found.

- Backend: all seven custom report routes call `resolve_itam_tenant` before any database access and filter by `{"tenantId": tenant_id, ...}`. Cross-tenant ids return the same 404 as unknown ids, and an Owner with no tenant gets 400. The export record and file carry the resolved tenant.
- Frontend: `ReportsPanel` now keeps the shown report and its identity in one `ShownReport` value, which is written only by the request that is still current. The run in flight is held apart as `pending`. `tenantEpoch` binds saves, deletes and exports to the tenant they started in.
- Tests: the two-tenant backend suite uses a real database and covers every route, spoofed headers, Support and Billing, and concurrent requests. The new frontend tests cover the success-then-failure, run-then-preview-supersede and export-across-tenant-switch cases. I found no missing assertions or flaky patterns.

What is left is four Info items. They are small robustness and compatibility gaps, not defects in the targeted fixes.

## Prior findings re-assessed

| ID | Status | Evidence |
|----|--------|----------|
| WR-01 (stale-response guard) | FIXED (unchanged, still correct) | `runSeq` guards `runPrebuilt` (123-137), `runSavedCustom` (146-160) and `handlePreviewCustom` (171-183). The tenant-change effect (109-121) bumps it. The result view has no result gate left to get wrong. |
| WR-02 (custom report routes not tenant-resolved) | FIXED | `backend/itam_reporting_endpoints.py`: save (231-232), list (258-263), preview (276-279), get (293-296), delete (307-310), run (326-329), export (353-362) all resolve the tenant first and filter by it. `backend/tests/test_itam_custom_report_tenant.py` proves 400 for an Owner without a tenant (both `None` and `platform-admin` header), own-tenant-only data for an Owner with a header, identical 404 for foreign and unknown ids, ignored header spoof for tenant admins, and 403/400 for Support/Billing. The client sends `X-Tenant-ID` on list, save, preview, run and delete (`services/apiService.ts` 6045-6095), and export already did. |
| WR-04 (shown result decoupled from export target) | FIXED | `ReportsPanel.tsx` 44-48: `shown` carries kind, key, page and data together and is written only after the `seq` check (129, 152, 179). A failed or superseded run leaves `shown` intact. `ReportResultView.tsx` 44-47 derives title, `canExport` and pagination from `shown`, and hides them while a run is in flight. `handleExport` fixes its target from `shown` at click time (221-222). Covered by three new tests in `ITAMReportsPanelStaleResponse.test.tsx` (failed run, preview supersede then fail, pagination after a failed run). |
| IN-04 (Run gate only honoured Owner) | FIXED | `App.tsx` passes `isPlatformView={isPlatformRoleName(currentUser.role)}`. `ITAMConsole.tsx:85` is `needsTenant = (isSuperAdminView \|\| isPlatformView) && !tenantId`. `ReportsPanel` also treats a server "Select a tenant" 400 as the same blocked state (`tenantRejected`, 56-67). Covered by `ITAMConsole.test.tsx` "platform tiers" block and `ITAMReportsPanelTenantRule.test.tsx`. |
| IN-05 (export not bound to its tenant) | FIXED | `tenantEpoch` (107) moves only on a tenant switch. `handleExport` (219-236) skips download, toast and `exportingFormat` reset when the epoch moved, and the tenant-change effect resets `exportingFormat`. Covered by "an export started before a tenant switch..." and "an export in the same tenant still downloads when a new run starts". |
| IN-01 (fabricated `X-Tenant-ID` from an Owner accepted) | STILL OPEN, wider than before | Neither `tenant_middleware.py:196-206` nor `resolve_itam_tenant` checks that the header names an existing tenant. Custom report save now stores a definition under whatever string an Owner sends (`itam_reporting_endpoints.py:232-246`), so an Owner typo creates an orphan `itam_reports` document in a tenant that does not exist. Fix as before: validate the header against the tenant collection in `resolve_itam_tenant` and return 400 for an unknown id. |
| WR-03 (cost detail route differs from the list row when the partner asset is disposed or retired) | STILL OPEN | `backend/itam_cost_service.py` and `backend/itam_cost_endpoints.py` have no change since c16cdf34c (confirmed with `git diff --stat`). Not re-reviewed in depth. |
| IN-02 (Asset value report population filter does not normalize `lifecycleStatus`) | STILL OPEN | `backend/itam_reporting_prebuilt.py` unchanged since c16cdf34c. |
| IN-03 (salvage above purchase cost gives book value above purchase cost) | STILL OPEN | `backend/itam_cost_service.py` unchanged since c16cdf34c. |

WR-03, IN-02 and IN-03 are outside this incremental file scope and are not counted in the frontmatter totals. IN-01 is re-assessed above for the same reason and not counted again.

## Info

### IN-06: Custom report definitions saved before this change under the Owner's own tenant become unreachable

**File:** `backend/itam_reporting_endpoints.py:231-246` (previous behaviour stored `current_user.tenant_id`)
**Issue:** Before plan 78-12, an Owner's save wrote `tenantId = current_user.tenant_id`, which for an Owner is `platform-admin`. Every route now resolves a real tenant and returns 400 for `platform-admin`, so any definition saved that way cannot be listed, run, exported or deleted by anyone. Documents with no `tenantId` are likewise invisible. Nothing is deleted, but there is no migration and no operator note. The test file asserts only that new saves leave zero `platform-admin` documents (`test_owner_save_lands_in_the_chosen_tenant_and_is_shared_there`), not that existing ones are handled. Whether any exist on the live database was not checked.
**Fix:** Count them once (`db.itam_reports.count_documents({"tenantId": {"$in": ["platform-admin", None]}})`). If the count is nonzero, add a one-off script that either reassigns them to a named tenant or archives them (archive, do not delete). If it is zero, record that in the phase summary.

### IN-07: A run in flight for a report is not cancelled when that report is deleted

**File:** `components/itam/ReportsPanel.tsx:201-217`
**Issue:** `handleDeleteConfirm` clears `shown` only if it is the deleted report (209, read from the render closure). A `runSavedCustom` for the same report that is still in flight stays current (the delete does not bump `runSeq`), so its response lands afterwards and shows the deleted report with working export buttons. Export then returns 404 and the user gets the generic export toast. The window is small and the effect is cosmetic, but a stale `shown` for a report that no longer exists is exactly what WR-04 set out to avoid.
**Fix:** After a successful delete, also drop the pending run for that report:
```tsx
if (pending?.kind === 'custom' && pending.key === target.id) { runSeq.current += 1; setPending(null); }
```

### IN-08: Save, preview and delete do not route a "Select a tenant" 400 through `takeTenantRejection`

**File:** `components/itam/ReportsPanel.tsx:171-216` (handled paths for comparison: 88-92, 130-133, 153-156, 229-232)
**Issue:** List, run and export put the tab into the blocked state on that 400 and show no toast. Preview and save rethrow to `ReportBuilderForm`, which toasts the server's message text. Delete shows `e.message` directly (214). The result is two behaviours for the same server answer, and the server text is rendered on those paths even though the handled paths treat it as match-only (T-78-07). The text is a fixed server string, so this is not a security issue. `takeTenantRejection` also leaves a previously shown report on screen with live export buttons.
**Fix:** Call `takeTenantRejection(e)` in the delete catch and let `handlePreviewCustom` and `handleSaveCustom` catch, check it, and rethrow otherwise. Clear `shown` and `pending` inside `takeTenantRejection` when it returns true.

### IN-09: `needsTenant` repeats a condition the role helper already covers

**File:** `components/itam/ITAMConsole.tsx:85`
**Issue:** `isSuperAdminRoleName` is a subset of `isPlatformRoleName` (`utils/permissions.ts` `PLATFORM_TIERS` includes `super_admin`), so `(isSuperAdminView || isPlatformView)` is equivalent to `isPlatformView` for every role App.tsx passes. The two props can now disagree in tests or other callers (the older `isSuperAdminView` is still used by the Lifecycle and Finance tabs), which makes the intent harder to read.
**Fix:** Compute `needsTenant = isPlatformView && !tenantId` in the console and keep passing `isSuperAdminView` only to the panels that use it. Existing tests that render `<ITAMConsole isSuperAdminView />` without `isPlatformView` would need `isPlatformView` added.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
