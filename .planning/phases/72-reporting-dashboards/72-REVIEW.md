---
phase: 72-reporting-dashboards
reviewed: 2026-08-17T12:43:22Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - backend/itam_kpi_endpoints.py
  - backend/itam_models.py
  - backend/itam_reporting_endpoints.py
  - backend/itam_reporting_excel.py
  - backend/itam_reporting_filters.py
  - backend/itam_reporting_kpis.py
  - backend/itam_reporting_pdf.py
  - backend/itam_reporting_prebuilt.py
  - backend/itam_reporting_service.py
  - backend/router_registry.py
  - backend/tests/itam_reporting_test_support.py
  - backend/tests/test_itam_reporting_builder.py
  - backend/tests/test_itam_reporting_export.py
  - backend/tests/test_itam_reporting_kpis.py
  - backend/tests/test_itam_reporting_prebuilt.py
  - components/itam/ITAMConsole.tsx
  - components/itam/itamI18n.tsx
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportBuilderForm.tsx
  - components/itam/ReportsPanel.tsx
  - services/apiService.ts
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMKpiPanel.test.tsx
  - src/__tests__/ITAMReportsPanel.test.tsx
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 72: Code Review Report

**Reviewed:** 2026-08-17T12:43:22Z
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

Reviewed the ITAM reporting/dashboard surface: pre-built report registry, the closed-vocabulary custom report builder (query translation + Python-side re-verification), CSV/PDF/XLSX renderers, the KPI aggregation endpoint, and their React consumers plus backend/frontend tests.

Overall the tenant-isolation story is sound — I traced `TenantIsolatedCollection`/`TenantIsolatedDatabase` (`backend/database.py`) and confirmed every `db.<collection>.find/find_one/insert_one/...` call used by this phase is auto-scoped by the request-context `tenant_id`, including the saved-custom-report CRUD routes that at first glance look unscoped (`list_custom_reports`, `get_custom_report`, `delete_custom_report`) — they are, in fact, scoped by the wrapper, and the dedicated cross-tenant tests in `test_itam_reporting_builder.py`/`test_itam_reporting_kpis.py` back this up. Formula-injection defence (`_sanitize_cell`) and the export-row-count/pagination contract (`build_report_rows` → renderers) are consistently applied.

Found one path-traversal defense weakness that reuses an existing, already-fragile pattern, plus two functional-correctness bugs in the custom report builder's date-range filter and the dashboard's "overdue" KPI total that are reachable through the shipped UI and produce silently wrong output rather than an error.

## Critical Issues

### CR-01: Path-traversal guard uses a prefix `startswith` check without a directory-separator boundary

**File:** `backend/itam_reporting_endpoints.py:141-144`

**Issue:** `download_report` computes containment with:
```python
_safe_dir = Path(_REPORTS_DIR).resolve()
_resolved = (_safe_dir / filename).resolve()
if not str(_resolved).startswith(str(_safe_dir)):
    raise HTTPException(status_code=400, detail="Invalid filename")
```
`str.startswith` on a plain string path is a classic prefix-match escape: it does not require a path separator immediately after the prefix, so a resolved path such as `/…/static/reportsEVIL/secret.txt` would incorrectly pass the check because `"/…/static/reportsEVIL/secret.txt".startswith("/…/static/reports")` is `True`, even though `reportsEVIL` is a sibling directory, not a subdirectory of `reports`. The check should compare against the resolved directory *plus a trailing separator*, or use `Path.is_relative_to()` / `os.path.commonpath()`.

Today this is not exploitable only because no sibling directory under `backend/static/` happens to start with the literal string `reports` (verified: `static/reports` is the only such entry). That is an accident of the current filesystem layout, not a property the code enforces, and the same helper is reused by every future itam report kind. The docstring says this was "cloned verbatim from `compliance_report_endpoints.download_report`" — the same weakness likely exists there, but the copy under review is new code in this phase and is in scope.

**Fix:**
```python
_safe_dir = Path(_REPORTS_DIR).resolve()
_resolved = (_safe_dir / filename).resolve()
try:
    _resolved.relative_to(_safe_dir)
except ValueError:
    raise HTTPException(status_code=400, detail="Invalid filename")
```

## Warnings

### WR-01: Custom-report "between" filter on a date field with reversed bounds silently drops all matching rows

**File:** `backend/itam_reporting_filters.py:198-202` (Mongo fragment) vs. `backend/itam_reporting_filters.py:254-259` (Python re-verification)

**Issue:** `_filters_to_mongo_query`'s `between` branch only normalizes `lo`/`hi` ordering for numeric values:
```python
elif op == "between":
    lo, hi = cond.value, cond.value2
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
        lo, hi = hi, lo
    clauses.append({mongo_field: {"$gte": lo, "$lte": hi}})
```
For a `date`-typed asset field (e.g. `asset.purchaseDate`) with `operator: "between"`, `value`/`value2` are ISO date *strings*, so the `isinstance(..., (int, float))` guard never fires and no swap happens. If the caller supplies `value` later than `value2` (nothing in `FilterCondition`'s validators or in `ReportBuilderForm.tsx` enforces `value <= value2` — the UI just renders two free-form inputs), the emitted Mongo query becomes `{"purchaseDate": {"$gte": "<later>", "$lte": "<earlier>"}}`, which cannot match any document. `run_custom_report` fetches its `assets` list straight from this query (`backend/itam_reporting_filters.py:378-379`), so the asset list is empty *before* the Python-side `_condition_passes` re-verification pass ever runs — and that pass **does** correctly swap reversed date bounds (`_condition_passes`, `field_type == "date"`, `between` branch), but it never gets the chance because there are no candidate rows left to re-check. The user-visible result is a report that silently returns zero rows ("No matching assets") for a perfectly valid, just reverse-ordered date range, instead of the swapped-and-correct result the number path would have produced for the exact same mistake.

**Fix:** Normalize ordering for dates the same way as numbers, e.g. by comparing the parsed values, or simply always emit both directions and let Mongo/re-verification agree:
```python
elif op == "between":
    lo, hi = cond.value, cond.value2
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
        lo, hi = hi, lo
    elif isinstance(lo, str) and isinstance(hi, str) and lo > hi:
        lo, hi = hi, lo
    clauses.append({mongo_field: {"$gte": lo, "$lte": hi}})
```

### WR-02: Overdue KPI's `totalCount` double-counts an asset that is overdue on both axes

**File:** `backend/itam_reporting_kpis.py:246-276`

**Issue:** `_compute_overdue_kpi` computes two independent counts and sums them:
```python
overdue_audit_count = await db.assets.count_documents(_overdue_query(cutoff))
...
overdue_checkin_count = await db.assets.count_documents({
    "lifecycleStatus": LifecycleStatus.DEPLOYED.value,
    "expectedReturnDate": {"$lt": now_iso},
})
...
"totalCount": overdue_audit_count + overdue_checkin_count,
```
`_overdue_query` (imported from `itam_lifecycle_endpoints.py`) is not restricted to any particular `lifecycleStatus` — it only excludes `disposed` assets (see `itam_lifecycle_endpoints.py:451-471`), so a `deployed` asset with a stale `lastAuditedAt`/`createdAt` is counted by `overdue_audit_count`. The exact same asset, if it also has an `expectedReturnDate` in the past, is counted again by `overdue_checkin_count`. A single asset overdue on both fronts (a very plausible real-world case — a long-checked-out laptop nobody has physically re-audited) is therefore counted twice in `totalCount`, which is rendered directly as "`{overdue.totalCount} overdue`" on the dashboard tile (`components/itam/ItamKpiPanel.tsx:204`). This contradicts the module's own stated contract ("never a fabricated 0% or 100%" / KPI-vs-source-tab agreement) — the number shown can be strictly larger than the true count of distinct overdue assets.

**Fix:** Either de-duplicate by asset id (fetch the matching id sets and union them) or clearly relabel `totalCount` as a sum of two independent event counts rather than a count of distinct assets, e.g.:
```python
audit_ids = {d["id"] async for d in db.assets.find(_overdue_query(cutoff), {"_id": 0, "id": 1})}
checkin_ids = {d["id"] async for d in db.assets.find(
    {"lifecycleStatus": LifecycleStatus.DEPLOYED.value, "expectedReturnDate": {"$lt": now_iso}},
    {"_id": 0, "id": 1},
)}
return {
    "hasData": True,
    "overdueAuditCount": len(audit_ids),
    "overdueCheckinCount": len(checkin_ids),
    "totalCount": len(audit_ids | checkin_ids),
    "drilldownReportKey": "overdue_audits",
}
```

### WR-03: `ReportBuilderForm`'s "between" inputs don't validate bound ordering, feeding WR-01 directly

**File:** `components/itam/ReportBuilderForm.tsx:104-119`

**Issue:** `canAddFilter`/`handleAddFilter` only check that both `draftValue`/`draftValue2` are non-empty; nothing enforces `draftValue <= draftValue2` before the condition is added to the definition and sent to the backend. Combined with WR-01, this makes it trivial for a user picking two dates "out of order" in the date pickers to produce a filter that always returns zero rows with no error message explaining why (`No matching assets. Adjust your filters and run the report again.` is the only feedback, which reads as "no data" rather than "you swapped the dates").

**Fix:** Either swap the values before building the condition, or reject/hint in the UI:
```ts
function handleAddFilter() {
  if (!canAddFilter || !draftFieldMeta || !draftOperator) return;
  let v1 = coerceValue(draftFieldMeta.type, draftValue);
  let v2 = draftOperator === 'between' ? coerceValue(draftFieldMeta.type, draftValue2) : undefined;
  if (draftOperator === 'between' && v2 !== undefined && v1 > v2) { [v1, v2] = [v2, v1]; }
  const condition: ItamReportFilterCondition = { field: draftField, operator: draftOperator, value: v1, value2: v2 };
  ...
}
```

## Info

### IN-01: `_dash`/`_EM_DASH` duplicated verbatim across two modules

**File:** `backend/itam_reporting_filters.py:39-44`, `backend/itam_reporting_prebuilt.py:32,47-50`

**Issue:** Both modules independently define an identical `_EM_DASH = "—"` constant and an identical `_dash(value)` helper. Not a bug (both docstrings acknowledge they're duplicated by design to avoid a cross-module dependency), but it is duplicated logic that could drift silently (e.g. one gets updated to render `"N/A"` and the other doesn't).

**Fix:** Consider hoisting to a small shared module (e.g. `itam_reporting_common.py`) both files already could import without creating the import-cycle both docstrings are careful to avoid.

### IN-02: Redundant ternary in `generateItamReport`

**File:** `services/apiService.ts:5629-5636`

**Issue:**
```ts
export const generateItamReport = async (kind: string, reportKey: string, format: string): Promise<ItamReportExportResult> => {
    if (kind !== 'prebuilt' && kind !== 'custom') {
        throw new Error(`Unsupported report kind: ${kind}`);
    }
    const segment = kind === 'prebuilt' ? 'prebuilt' : 'custom';
```
After the guard clause, `kind` can only be `'prebuilt'` or `'custom'`, so `segment` is always equal to `kind` itself — the ternary is dead weight.

**Fix:**
```ts
const segment = kind; // narrowed to 'prebuilt' | 'custom' by the guard above
```

---

_Reviewed: 2026-08-17T12:43:22Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
