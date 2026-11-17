---
phase: 78-organization-endpoint-cost-api
reviewed: 2026-11-17T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - components/itam/ReportsPanel.tsx
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 78: Code Review Report (incremental, after gap plan 78-11)

**Reviewed:** 2026-11-17
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Incremental re-review of the committed (HEAD) code changed since 2a58a89a5: the `runSeq` request-sequence guard on `runPrebuilt`, `runSavedCustom` and `handlePreviewCustom`, the `running` reset on tenant change, the `resultIsCurrent` / `showingPreview` render gate, and the new tests. The two unrelated user working-tree edits (lint-comment deletions) were not reviewed.

The guard itself is correct. Every late response, late failure and superseded `finally` is dropped for the three run paths, and a tenant switch clears `running`, the result and the preview flag. Both vitest files pass (35 tests). The gate does not make the shown result and its export target agree, though: `result` and `activeKind`/`activeKey` are still written at different times, so a failed or superseded run leaves the previous result on screen under the new run's export buttons (WR-04). Smaller items: export is not bound to the tenant it started under (IN-05), and prior IN-04 is unchanged (below).

## Prior findings re-assessed

- **WR-01 (ReportsPanel stale-response guard): FIXED.** Evidence in `components/itam/ReportsPanel.tsx` at HEAD:
  - `runSeq` is a `useRef` counter (line 88). `runPrebuilt` (107-118) and `runSavedCustom` (133-144) take `++runSeq.current` and drop the result (110, 136), the failure toast (114, 140) and the `setRunning(false)` (117, 143) when superseded.
  - The tenant-change effect (90-100) bumps `runSeq`, resets `running`, `showingPreview`, `result`, `activeKind`, `activeKey` and `page`.
  - The render condition requires `resultIsCurrent` (322). Tests in `ITAMReportsPanelStaleResponse.test.tsx` and `ITAMConsole.test.tsx` cover tenant switch, switch to no tenant, out-of-order resolution, late failure, and same-tenant rerender. The remaining mismatch between `result` and the export target is a different defect and is filed as WR-04, not as a leftover of WR-01.
- **IN-04 (Run button gate; platform tiers fall through to a toast): STILL OPEN, unchanged.** `ReportsPanel` still only honours the `needsTenant` prop (lines 229-247). `components/itam/ITAMConsole.tsx:82` is still `needsTenant = isSuperAdminView && !tenantId` (confirmed by grep; the file is outside this incremental scope), so Platform Support and Billing see enabled Run buttons and get the server's 400 as an error toast. Kept under the original ID with the original fix.

## Prior findings outside this incremental scope

WR-02, WR-03, IN-01, IN-02 and IN-03 concern files that are not in this scope (`backend/itam_reporting_endpoints.py`, `backend/itam_cost_service.py`, `backend/itam_tenant_scope.py`, `backend/itam_reporting_prebuilt.py`). They were not re-reviewed here and stand as recorded in commit 2a58a89a5. They are not counted in this report's frontmatter totals.

## Warnings

### WR-04: The shown result is decoupled from `activeKind`/`activeKey`, so a failed or superseded run leaves the previous report on screen with export buttons for a different report

**File:** `components/itam/ReportsPanel.tsx:102-118, 128-145, 156-172, 220-223, 322-326`
**Issue:** `runPrebuilt` and `runSavedCustom` set `activeKind` and `activeKey` immediately (103-104, 129-130) but only write `result` on success. `resultIsCurrent` (223) is true whenever `activeKind && activeKey` is set, whether or not `result` came from that key. Two paths show a result under the wrong key:
- Run report A (success, result A shown). Click Run on report B. `activeKey` becomes B while `result` is still A. If B fails (114-116), `running` goes false, the toast fires, and the table renders A's rows with A's title (`result.title`, line 325) while `canExport` is true and `handleExport` exports `activeKind/activeKey` = B (206-211). The user downloads a different report than the one on screen. Next/Previous also call `runPrebuilt(B, ...)` with A's `page`.
- The new `handlePreviewCustom` supersedes an in-flight run with `setRunning(false)` (160) but leaves `activeKey` at the abandoned run's key. The previous result becomes visible again, again under the abandoned key's export buttons. If the preview then throws, that state persists. The preview-after-run case is new in this plan.

The gate's comment says it means "the shown result belongs to the current request", and that is not what it checks. No new test covers success-then-failure or run-then-preview-supersede.

**Fix:** Store the displayed result together with its identity and write both only on success, keeping the pending request separate:
```tsx
const [shown, setShown] = useState<{ kind: 'prebuilt' | 'custom' | null; key: string | null; data: ItamReportRunResult } | null>(null);
const [pendingTitle, setPendingTitle] = useState<string | null>(null);
// success path (after the seq check):
setShown({ kind: 'prebuilt', key, data: r }); setPage(targetPage);
// preview success: setShown({ kind: null, key: null, data: r });
// derive: result = shown?.data; activeKind = shown?.kind; activeKey = shown?.key
```
Then `canExport`, the heading, pagination and `handleExport` all follow the displayed result, and a failed run leaves a consistent previous result (or clear `shown` on failure). Add two tests: run A then a failing run B (assert the export click targets A or the result is cleared), and run then builder preview then failure.

## Info

### IN-04: The Run button gate depends only on `isSuperAdminRoleName`; other platform tiers fall through to a toast (still open)

**File:** `components/itam/ITAMConsole.tsx:81-82` (consumer: `components/itam/ReportsPanel.tsx:229-247`)
**Issue:** See "Prior findings re-assessed". Unchanged by 78-11.
**Fix:** Use `isPlatformRoleName(role)` (already in `utils/permissions.ts`) for `needsTenant`, or pass the same `SELECT_TENANT_RE` handling into ReportsPanel.

### IN-05: An export started before a tenant switch is not cancelled and keeps `exportingFormat` set

**File:** `components/itam/ReportsPanel.tsx:205-218` (tenant-change effect at 90-100)
**Issue:** `handleExport` captures `tenantId` from its render closure and runs to completion even after the tenant switch cleared the result. The previous tenant's file still downloads after the switch (the user started it, but it lands while another organization is selected, which R3 tries to avoid). The tenant-change effect also does not reset `exportingFormat`, so the first result in the new tenant shows its export buttons disabled until the old export finishes.
**Fix:** Reset `exportingFormat` in the tenant-change effect and have `handleExport` capture `const seq = runSeq.current` and skip `downloadItamReport` (and the toast) when `seq !== runSeq.current` after the `await generateItamReport(...)`.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
