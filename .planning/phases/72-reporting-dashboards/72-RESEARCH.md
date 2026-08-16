# Phase 72: Reporting & Dashboards - Research

**Researched:** 2026-08-16
**Domain:** Backend report/query building over an existing MongoDB (Motor, async) ITAM dataset; PDF/Excel/CSV export; React KPI dashboard (recharts)
**Confidence:** HIGH (nearly everything in this phase is disciplined reuse of code already in this repo — verified by direct reads, not inferred)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Custom Report Builder (ITAM-REP-01)**
- D-01: Reports are asset-rooted only — every report starts from the `assets` collection, optionally joining license/consumable/component/finance fields onto asset rows. No independent license-only or consumable-only report root. Reversibility: costly.
- D-02: Builder UX is a field + filter picker (select columns, add filter conditions), not a "pick report type then filter" form.
- D-03: Filter operators: equals/contains for text, date-range (before/after/between) for dates, numeric comparison (>/</between) for numbers.
- D-04: Saved custom report definitions are shared tenant-wide, not private per-creator.
- D-05: No cap on saved reports per tenant.
- D-06: Builder shows an on-screen paginated results preview before export.
- D-07: Report builder access is gated by `manage:itam` (the same admin gate as other ITAM management surfaces — `_require_itam_admin`, Phase 47/48/61/63 pattern), not the wider `view:itam`.

**Pre-built Reports (ITAM-REP-02)**
- D-08: Six pre-built reports ship: Asset value/depreciation summary, Check-out/check-in activity log, Warranty expiring, License seat utilization, Low-stock consumables, Overdue physical audits.
- D-09: Pre-built reports are fixed (code-defined, no user-configurable params).
- D-10: Pre-built and custom reports live in one "Reports" tab with two sections (pre-built list + "Create Custom Report" action), not separate tabs.

**Export (ITAM-REP-03)**
- D-11: Export reuses the `compliance_reporting_pdf.py`/`compliance_reporting_excel.py` pattern (reportlab for PDF, openpyxl for Excel, file written and returned as download) — not `scheduled_reports_service.py`'s inline-HTML-to-bytes pattern.
- D-12: One shared report-data-building function feeds all three renderers (PDF, Excel, CSV) — avoids drift between formats. CSV is the simplest renderer on top of that shared data.
- D-13: Export is on-demand only — no scheduled/recurring delivery in this phase.
- D-14: Export applies to both custom-built AND pre-built reports.

**KPI Dashboard (ITAM-REP-04)**
- D-15: Dashboard is a 7th tab in `ITAMConsole.tsx`, alongside the existing 6 (Catalog, Check-Out/In, Procurement & Finance, Licenses & Consumables, Compliance, Software Inventory) — not a new landing view.
- D-16: Four KPIs: total asset value + count by status/lifecycle stage, license utilization % (seats used/available), upcoming warranty expirations (count/timeline), overdue check-ins/audits count.
- D-17: Chart library is `recharts` — already a dependency, already used in `CXODashboard.tsx`/`ExecutiveDashboard.tsx`/`PatchManagementDashboard.tsx`. No new charting dependency.
- D-18: KPI tiles are clickable and drill into the corresponding pre-built report or a filtered asset list.

### Claude's Discretion
- Exact column set exposed by the field picker per entity (asset/license/consumable/component/finance) — pick from existing model fields, no new fields need to be invented.
- Exact wording/layout of the two-section Reports tab and the KPI tile grid.
- Whether the shared report-data function lives in a new `itam_reporting_service.py` or extends an existing itam_* service — implementation detail for research/planning to resolve against the existing module layout.

### Deferred Ideas (OUT OF SCOPE)
- Scheduled/recurring ITAM report delivery via email — explicitly deferred (D-13); `scheduled_reports_service.py` is the future integration point.
- Report-builder support for a non-asset-rooted query (independent license/consumable reports) — deferred (D-01); revisit if asset-rooted joins prove insufficient in practice.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITAM-REP-01 | Custom Report Builder (build + save) | See "Custom Report Builder Query Model" pattern below — no existing filter-DSL in the codebase, must be built fresh, scoped to a small closed operator set per D-03/D-02. |
| ITAM-REP-02 | Pre-built Reports for asset/license data | See "Pre-built Report Data Sources" table — 5 of 6 reports read straight off existing computed fields/queries; 1 (`Overdue physical audits`) already exists as a full endpoint and can be reused near-verbatim. |
| ITAM-REP-03 | Export support (PDF, CSV, Excel) | See "Export Pattern" — clone `compliance_report_endpoints.py` + `compliance_reporting_pdf/excel.py` structure exactly; `reportlab`/`openpyxl` already installed, no new packages. |
| ITAM-REP-04 | ITAM Dashboard with KPIs/Visualizations | See "KPI Dashboard" pattern — clone `CXODashboard.tsx`'s recharts usage; **the tab count in D-15 is stale, see Pitfall 2**. |
</phase_requirements>

## Summary

This phase is almost entirely disciplined reuse. The export pipeline should be a close structural clone of `backend/compliance_reporting_pdf.py` / `compliance_reporting_excel.py` / `compliance_reporting_service.py` (CSV) / `compliance_report_endpoints.py` (routes) — that existing quartet already implements exactly the shape D-11/D-12 ask for: one `_build_report_data(...)` function returning plain dicts, three renderers that each do nothing but `list(rows[0].keys())` for headers, a `generate/download` route pair with path-traversal-safe filename resolution and tenant-ownership checks on download. The KPI dashboard should clone `CXODashboard.tsx`'s recharts usage (`AreaChart`/`PieChart`/`Tooltip`/`Legend`/`ResponsiveContainer`, all already imported from the already-installed `recharts@^3.5.1`). Five of the six pre-built reports read data that already exists as computed fields or endpoints (`itam_finance_service.compute_book_value`, `itam_license_endpoints._enrich_license_seats_and_expiry`, `itam_lifecycle_endpoints`'s already-shipped `GET /api/assets/reports/overdue-audit` route). The one genuinely new subsystem is the custom report builder's filter engine (ITAM-REP-01) — there is no existing generic query-builder/filter-DSL anywhere in this codebase (verified by grep across `backend/*.py`); it must be built fresh as a small, closed-vocabulary filter-to-MongoDB-query translator per D-03's three operator families.

Two of CONTEXT.md's D-decisions describe the codebase inaccurately and must be corrected before planning locks them in further (see Common Pitfalls 1 and 2): the actual `_require_itam_admin` dependency checks `manage:assets`, not `manage:itam`, and `ITAMConsole.tsx` currently has 10 tabs, not 6 — Reports would be the 11th, not the 7th. Both are easy to plan around once known, but planning against the stale description would produce a plan that a plan-checker or executor would have to silently "fix," which is worse than catching it now.

**Primary recommendation:** Build one new backend module pair — `itam_reporting_service.py` (shared report-data builder + pre-built report queries + custom-filter-to-Mongo translator) and `itam_reporting_endpoints.py` (routes: list pre-built reports, run pre-built report, CRUD saved custom reports, run custom report preview, export any report in csv/pdf/xlsx) — registered in `router_registry.py` next to the other Phase-56/57/59/60/71 ITAM routers, gated by the actual `_require_itam_admin` dependency imported from `itam_asset_endpoints.py`. Build one new frontend `ReportsPanel.tsx` (pre-built list + custom builder UI) and extend `ITAMConsole.tsx`'s tab array by one, following `ReportingDashboard.tsx`'s existing generate→download UX and `CXODashboard.tsx`'s KPI-tile/chart patterns for a new `ItamKpiPanel.tsx`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Custom report filter definition (build + save) | API / Backend | Browser / Client (field+filter picker UI state) | Saved report defs are shared tenant-wide server state (D-04); the picker UI is pure client state until "save." |
| Custom report execution (query assets + joins) | API / Backend | Database / Storage (MongoDB queries/aggregation) | Cross-collection joins and tenant isolation must happen server-side; never trust a client-constructed Mongo query. |
| Pre-built report computation | API / Backend | — | All 6 reports read from existing service-layer computed fields (book value, seat utilization, overdue audit) that already live in the backend. |
| Report preview (paginated) | API / Backend | Browser / Client (render only) | D-06's preview must run the same query the export will run — computed server-side, rendered client-side. |
| PDF/Excel/CSV rendering | API / Backend | — | `reportlab`/`openpyxl`/`csv` are server-side Python libraries; files are generated on disk and served via `FileResponse`, matching the existing compliance-report pattern exactly. |
| KPI computation (4 KPIs) | API / Backend | — | Aggregates (counts, sums, percentages) must be computed server-side against tenant-scoped data, not fetched-then-reduced client-side against a full asset list (existing `CXODashboard.tsx` precedent computes dashboard aggregates via a dedicated `fetchKpiSummary` endpoint rather than raw client reduction — follow that shape). |
| KPI dashboard rendering + drill-down | Browser / Client | — | `recharts` renders in the browser; drill-down (D-18) is client-side tab-state navigation to the Reports tab, not a new route. |
| Report/tab access gating | API / Backend | Browser / Client | Backend `_require_itam_admin` dependency is the real gate (403 on violation); frontend nav-gate is UX-only defense in depth, matching the existing `viewPermissionMap`/`Permission` pattern. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| reportlab | 5.0.0 (installed, `backend/venv`) [VERIFIED: pip show] | PDF report generation | Already the sole PDF library in this codebase (`compliance_reporting_pdf.py`); D-11 explicitly mandates reuse. |
| openpyxl | 3.1.5 (installed, `backend/venv`) [VERIFIED: pip show] | Excel (.xlsx) report generation | Already the sole Excel library in this codebase (`compliance_reporting_excel.py`); D-11 explicitly mandates reuse. |
| `csv` (stdlib) | n/a | CSV report generation | Used by `compliance_reporting_service.py::_generate_csv` — no third-party CSV library needed. |
| recharts | ^3.5.1 (declared, `package.json`) [VERIFIED: package.json + grep import] | KPI dashboard charts | Already used by `CXODashboard.tsx`, `ExecutiveDashboard.tsx`, `PatchManagementDashboard.tsx`; D-17 explicitly mandates reuse, no new dependency. |
| Motor (async MongoDB) | already in use throughout `backend/` | Report queries, joins, aggregation | Existing async DB driver; all ITAM collections (`assets`, `licenses`, `itam_consumables`, `components`, `assignment_history`, `license_assignments`) already use it via `database.get_database()`. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pymongo (`ReturnDocument`) | bundled with Motor | `find_one_and_update(..., return_document=ReturnDocument.AFTER)` | Saved custom-report-definition update route, matching every other ITAM PATCH/PUT route's convention (`itam_license_endpoints.py`, `itam_component_service.py`). |
| FastAPI `FileResponse` | already in use | Serve generated report files as downloads | Clone `compliance_report_endpoints.py::download_report`'s path-traversal-safe pattern exactly. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom filter-to-Mongo translator (hand-built) | A generic query-builder library (e.g. `mongoengine` Q-objects, a JSON-Schema-to-Mongo translator) | No such library is already a dependency in this repo (neither `requirements.txt`/installed packages nor an in-repo pattern) — introducing one for a scoped 3-operator-family filter set (D-03) is disproportionate; a ~150-line closed-vocabulary translator is safer (auditable, no injection surface) and matches this codebase's existing preference for hand-rolled, narrowly-scoped query builders (`_overdue_query`, `get_warranty_alert_window`). |
| Server-side MongoDB `$lookup` aggregation for cross-collection joins | Multiple simple queries + Python-side dict merge | See Pitfall 4 below — `$lookup` sub-pipelines are NOT auto-tenant-scoped by `TenantIsolatedCollection.aggregate()`, only the top-level pipeline match is. Python-side merge (query assets, then batch-query licenses/consumables/components by the ids/keys found on those assets, using the normal tenant-scoped `db.X.find()`) is safer by construction and matches this codebase's existing style of manual per-collection lookups (e.g. `itam_finance_endpoints.get_asset_book_value` looking up `asset_models` by id in a second query rather than a `$lookup`). Recommended default; `$lookup` remains usable IF every sub-pipeline stage explicitly re-asserts `tenantId` equality. |

**Installation:**
```bash
# No new packages — reportlab, openpyxl, recharts are all already installed/declared.
```

**Version verification:** `backend/venv/bin/pip show reportlab openpyxl` confirms 5.0.0 / 3.1.5 installed in the actual backend virtualenv this project uses (not just `requirements.txt` — the real running environment). `grep '"recharts"' package.json` confirms `^3.5.1` declared and `grep recharts components/CXODashboard.tsx` confirms it is actually imported and used, not just declared-but-unused.

## Package Legitimacy Audit

**Not applicable — this phase installs zero new external packages.** `reportlab`, `openpyxl`, and `recharts` are pre-existing dependencies already installed/declared and already used elsewhere in this codebase (verified directly, not via registry lookup). No `package-legitimacy check` run is needed since no new package name is being introduced.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ Browser — ITAMConsole.tsx (new 11th tab: "Reports")                  │
│                                                                        │
│  ReportsPanel.tsx                       ItamKpiPanel.tsx (7th-in-D15 │
│  ┌─────────────────┐ ┌────────────────┐  content, actually 11th tab) │
│  │ Pre-built list    │ │ Custom builder │  ┌──────────────────────┐ │
│  │ (6 fixed cards)   │ │ field+filter   │  │ 4 KPI tiles (click-  │ │
│  │  -> run -> preview │ │ picker -> save │  │ able, drill into a   │ │
│  │  -> export button  │ │ -> preview ->  │  │ Reports-tab pre-built │ │
│  └────────┬───────────┘ │ export button  │  │ report or filtered   │ │
│           │              └───────┬────────┘  │ asset list)          │ │
└───────────┼──────────────────────┼───────────┴──────────┬───────────┘
            │ GET /api/itam/reports/prebuilt/{key}          │ GET /api/itam/kpis
            │ POST /api/itam/reports/custom (save)          │
            │ POST /api/itam/reports/custom/{id}/preview    │
            │ GET  /api/itam/reports/{id}/export?format=pdf │
            ▼                                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Backend — itam_reporting_endpoints.py  (new router)                  │
│  Depends(_require_itam_admin)  [imported from itam_asset_endpoints]  │
│                                                                        │
│  itam_reporting_service.py                                           │
│   ├─ PREBUILT_REPORTS registry (6 fixed, code-defined queries)       │
│   │    -> reads: itam_finance_service.compute_book_value             │
│   │              itam_license_endpoints._enrich_license_seats...     │
│   │              itam_lifecycle_endpoints._overdue_query/_overdue_row│
│   │              db.assignment_history (checkout/checkin log)        │
│   │              db.itam_consumables (low-stock)                     │
│   ├─ run_custom_report(filters) -> asset-rooted Mongo query + joins  │
│   │    -> _filters_to_mongo_query() (new, closed operator set)       │
│   │    -> join license/consumable/component/finance data per-asset   │
│   │       via batched db.X.find({"id": {"$in": [...]}}) calls        │
│   │       (NOT a raw $lookup — see Pitfall 4)                        │
│   ├─ _build_report_rows(...) -> one shared dict-row builder (D-12)   │
│   └─ compute_itam_kpis() -> the 4 KPI aggregates                     │
│                                                                        │
│  itam_reporting_pdf.py / itam_reporting_excel.py  (new, cloned       │
│    structurally from compliance_reporting_pdf.py/excel.py)           │
│  CSV renderer lives alongside the service (clone                     │
│    compliance_reporting_service.py::_generate_csv)                   │
│                                                                        │
│  All queries go through database.get_database() (TenantIsolatedDB)   │
│  -> auto tenantId filter on assets/licenses/itam_consumables/        │
│     components/assignment_history/license_assignments (none of      │
│     these are in database.py's EXEMPTION list — verified)            │
└─────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Database — MongoDB (Motor)                                           │
│  assets (assetSource discriminator) | licenses | itam_consumables    │
│  components | assignment_history | license_assignments | asset_models│
│  itam_reports (NEW — saved custom report definitions, D-04/D-05)     │
└─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── itam_reporting_service.py     # shared report-data builder, pre-built report registry,
│                                  # custom-filter translator, KPI computation (all pure/DB-only, no FastAPI import)
├── itam_reporting_endpoints.py   # routes: prebuilt list/run, custom CRUD+preview, export, KPIs
├── itam_reporting_pdf.py         # reportlab renderer, cloned from compliance_reporting_pdf.py
├── itam_reporting_excel.py       # openpyxl renderer, cloned from compliance_reporting_excel.py
│                                  # (CSV renderer stays inline in itam_reporting_service.py,
│                                  #  mirroring compliance_reporting_service.py's own placement)
components/itam/
├── ReportsPanel.tsx               # 2-section Reports tab (pre-built list + custom builder, D-10)
├── ReportBuilderForm.tsx          # field+filter picker (D-02/D-03) — split out to stay under 500 lines
├── ItamKpiPanel.tsx                # KPI tile grid + recharts visualizations (D-16/D-17/D-18)
```

### Pattern 1: Shared report-data-builder feeding 3 renderers (D-12)
**What:** One async function returns plain-dict rows (list of `{"Display Header": value, ...}`); PDF/Excel/CSV renderers each do nothing but `list(rows[0].keys())` for headers and iterate `row.values()` for cells. This is the exact shape already proven in `compliance_reporting_data.py::_build_report_data` (feeds `compliance_reporting_pdf.py`, `compliance_reporting_excel.py`, `compliance_reporting_service.py::_generate_csv`).
**When to use:** Every pre-built and custom report in this phase (D-14: export applies to both).
**Example:**
```python
# Source: backend/compliance_reporting_pdf.py (verified in this repo)
async def _generate_pdf(framework_id: str, reports_dir: str, tenant_id: str = None) -> dict:
    framework, asset_summary, control_rows = await _build_report_data(framework_id, tenant_id)
    # ... doc = SimpleDocTemplate(...); elements built from asset_summary/control_rows ...
    doc.build(elements)
    return {"filename": filename, "url": f"/static/reports/{filename}",
            "generatedAt": datetime.now().isoformat(), "rowCount": len(control_rows)}

# ITAM equivalent to build, mirroring this exactly:
async def _build_itam_report_rows(report_key: str, filters: dict, tenant_id: str) -> list[dict]:
    """Returns list[{"Asset Tag": ..., "Name": ..., "Book Value": ..., ...}] —
    the single source of truth every renderer (pdf/excel/csv) reads from."""
```

### Pattern 2: Route pair for generate + tenant-safe download (D-11)
**What:** `POST /generate[...]` returns `{filename, url, generatedAt, rowCount}` and persists metadata; `GET /download/{filename}` resolves the path safely (no traversal) and checks the report's persisted `tenantId` against the caller before streaming.
**When to use:** Every export action in this phase.
**Example:**
```python
# Source: backend/compliance_report_endpoints.py (verified in this repo, lines 121-158)
@router.get("/download/{filename}")
async def download_report(filename: str, _current_user: TokenData = Depends(get_current_user)):
    from pathlib import Path as _Path
    _safe_dir = _Path(_REPORTS_DIR).resolve()
    _resolved = (_safe_dir / filename).resolve()
    if not str(_resolved).startswith(str(_safe_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    # ... 404 if not os.path.isfile ...
    # ... tenant-ownership check against a persisted `{filename, tenantId}` metadata doc ...
    return FileResponse(path=file_path, media_type=media_types.get(ext, ...),
                         filename=filename, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```
Clone this exactly for `itam_reporting_endpoints.py`, storing metadata in a new `itam_report_exports` collection (parallel to `compliance_reports`).

### Pattern 3: Frontend generate-then-blob-download (D-11/D-14 frontend half)
**What:** `authFetch` a `POST /generate` route that returns JSON `{filename, ...}`, then a second call blobs the `GET /download/{filename}` response and triggers a synthetic `<a>` click.
**Example:**
```typescript
// Source: services/apiService.ts lines 3636-3699 (verified in this repo)
export const generateComplianceReport = async (frameworkId: string) => {
    const formData = new FormData();
    formData.append('framework_id', frameworkId);
    const res = await authFetch(`${API_BASE}/compliance/reports/generate`, { method: 'POST', body: formData });
    if (!res.ok) { /* throw with err.detail */ }
    return await res.json();
};
export const downloadComplianceReport = async (filename: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/compliance/reports/download/${encodeURIComponent(filename)}`);
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
};
```
Clone this shape verbatim for the new `generateItamReport(reportKeyOrId, format)` / `downloadItamReport(filename)` functions in `apiService.ts`.

### Pattern 4: Admin gate reuse (correcting D-07's exact mechanism)
**What:** Every ITAM management route imports one shared dependency rather than redefining a permission check.
**Example:**
```python
# Source: backend/itam_asset_endpoints.py lines 36-45 (verified in this repo — the actual
# _require_itam_admin definition every other itam_*_endpoints.py file imports)
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="User does not have permission to manage ITAM assets.")
    return current_user

# itam_finance_endpoints.py's own docstring makes the reuse-not-redefine convention explicit:
# "This module reuses `_require_itam_admin` from itam_asset_endpoints.py rather than
#  redefining the manage:assets RBAC gate."
```
`itam_reporting_endpoints.py` should do exactly the same: `from itam_asset_endpoints import _require_itam_admin`. See Common Pitfall 1 for why this checks `manage:assets`, not `manage:itam` as CONTEXT.md's D-07 states.

### Pattern 5: Pre-built report reuse — "Overdue physical audits" already exists
**What:** `GET /api/assets/reports/overdue-audit` (in `itam_lifecycle_endpoints.py`, lines 509-559) already computes exactly D-08's sixth report end-to-end: query, age-basis resolution, sort, and a `{intervalDays, cutoff, count, rows}` response shape.
**When to use:** For this one report, do not rebuild the query — either (a) call the existing route's underlying helpers (`_overdue_query`, `_overdue_row`, `AUDIT_INTERVAL_DAYS`, `_audit_cutoff_iso`, all importable from `itam_lifecycle_endpoints`) from inside `itam_reporting_service.py`'s shared row-builder so it can also feed PDF/Excel/CSV (the existing route only returns JSON), or (b) have the Reports tab's "Overdue physical audits" card link straight to data already fetchable via the existing endpoint and only add the export wrapper around it.
**Example:**
```python
# Source: backend/itam_lifecycle_endpoints.py lines 451-471 (verified in this repo)
def _overdue_query(cutoff: str) -> Dict[str, Any]:
    return {
        "lifecycleStatus": {"$ne": LifecycleStatus.DISPOSED.value},
        "$or": [
            {"lastAuditedAt": {"$lt": cutoff}},
            {"lastAuditedAt": {"$exists": False}, "createdAt": {"$lt": cutoff}},
            {"lastAuditedAt": {"$exists": False}, "createdAt": {"$exists": False}},
        ],
    }
```

### Anti-Patterns to Avoid
- **Recomputing book value in a loop by calling the per-asset REST endpoint N times:** `GET /{asset_id}/book-value` (itam_finance_endpoints.py) is designed for one asset per request. The "Asset value/depreciation summary" report needs all assets — call `itam_finance_service.compute_book_value(...)` directly (it is a pure function, no FastAPI/DB import) in a loop over `db.assets.find(...)` results plus a batched `db.asset_models.find({"id": {"$in": [...]}})` lookup, never N sequential HTTP-shaped calls.
- **Using raw `$lookup` aggregation without an explicit tenantId match in the lookup sub-pipeline:** see Pitfall 4 — this is the single highest-risk mistake available in this phase.
- **Re-deriving the `manage:itam` vs `manage:assets` permission string from CONTEXT.md's prose instead of the actual `_require_itam_admin` import:** see Pitfall 1.
- **Assuming consumable checkout/asset linkage is a real foreign key:** `ConsumableCheckoutRecord.assignedTo`/`assignedToType` is a loose string reference (only "an asset id was recorded here"), not a Mongo relationship the report builder can safely `$lookup` or `$in`-match without also checking `assignedToType == "asset"`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| PDF table styling (status-color rows, header banding, auto column width) | A new PDF layout system | Clone `compliance_reporting_pdf.py`'s `make_table()`/`_find_status_rows()` helpers | Already handles landscape-letter scaling, Paragraph-wrapped cells, and status-color mapping — a new implementation would just re-derive the same reportlab quirks (column-width scaling math, `html.escape` needed inside `Paragraph`). |
| Excel styling (header fill, borders, auto-width, status colors, hyperlinks) | A new openpyxl styling module | Reuse `_xl_header_row`/`_xl_auto_width`/`_apply_status_colors`/`_apply_url_hyperlink` from `compliance_reporting_excel.py` (import directly, or copy into `itam_reporting_excel.py` if cross-module coupling to a non-ITAM file is undesirable) | These are pure `(ws, ...) -> None` helpers with no compliance-specific logic — they operate on generic header lists and status-string-to-color maps. |
| Tenant-safe file download (path traversal defense, tenant-ownership check) | A new download route from scratch | Clone `compliance_report_endpoints.py::download_report` verbatim (path resolution + `startswith` containment check + tenant-ownership lookup against persisted metadata) | Getting path-traversal defense subtly wrong (e.g. skipping `.resolve()` before the `startswith` check) is a real vulnerability class; this exact code has already been through security review in this codebase. |
| Book-value / depreciation math | A new depreciation calculator | `itam_finance_service.compute_book_value(...)` | Already handles whole-year-boundary proration, salvage-value flooring, and invalid-input error handling — reinventing it risks silently diverging from the number `GET /{asset_id}/book-value` shows an operator elsewhere in the same app. |
| Warranty status / seat-utilization math | New computations | `itam_finance_service.compute_warranty_status` / `itam_license_endpoints._enrich_license_seats_and_expiry` | Same "single source of truth" argument — divergence between the report and the live console tab would be a real, user-visible bug. |
| Overdue-audit query | A new query | `itam_lifecycle_endpoints._overdue_query`/`_overdue_row`/`AUDIT_INTERVAL_DAYS` | Already fully implements the report; only the export wrapper is new work. |

**Key insight:** This phase's biggest risk is NOT missing functionality — nearly every number this phase needs to report is already computed somewhere in the Phase 56-71 ITAM backend. The risk is drift: a hand-rolled second implementation of book value, warranty status, or seat utilization inside the new reporting module would silently disagree with what the same tenant sees on the Finance/Licenses tabs the moment either implementation is touched in a future phase. Import and call the existing pure functions; do not reimplement their math.

## Runtime State Inventory

Not applicable — this is a purely additive, greenfield phase (new module pair + new frontend panel + one new tab). No rename/refactor/migration is involved, and no existing runtime state needs to change shape.

## Common Pitfalls

### Pitfall 1: CONTEXT.md's D-07 misdescribes the permission `_require_itam_admin` actually checks
**What goes wrong:** D-07 states the report builder gate should be `manage:itam` ("the same admin gate as other ITAM management surfaces — `_require_itam_admin`"). The actual `_require_itam_admin` function (defined once in `itam_asset_endpoints.py`, imported by `itam_consumable_endpoints.py`, `itam_component_endpoints.py`, `itam_license_endpoints.py`, `itam_finance_endpoints.py`, `itam_lifecycle_endpoints.py`, `itam_catalog_endpoints.py`) checks `verify_permission(current_user, "manage:assets")`, not `manage:itam`. `manage:itam`/`view:itam` are real, separately-defined permission strings (`rbac_utils.py`, `api_key_auth.py`) used elsewhere (frontend nav gating, tenant feature flags) but never by `_require_itam_admin` itself.
**Why it happens:** Both permissions were granted together to the `admin` role in the same Phase 61-01 commit (`rbac_utils.py` DEFAULT_PERMISSIONS), so for the built-in `admin` role the distinction is invisible in practice — but a custom role granted only `manage:itam` and not `manage:assets` (or vice versa) would behave differently than CONTEXT.md's prose implies.
**How to avoid:** Plan the report builder's access gate as `from itam_asset_endpoints import _require_itam_admin` (the real, already-proven pattern every other ITAM management router uses) rather than writing a new dependency that checks `manage:itam` literally. This is consistent with D-07's *intent* ("the same admin gate as other ITAM management surfaces") even though it corrects D-07's stated permission string.
**Warning signs:** A plan or PR that defines a brand-new `_require_itam_manage` checking `"manage:itam"` instead of importing the existing `_require_itam_admin` — that would be the first ITAM router to diverge from the established gate, and would pass for the built-in admin role while silently behaving differently for any custom role.

### Pitfall 2: CONTEXT.md's D-15 undercounts `ITAMConsole.tsx`'s current tab count
**What goes wrong:** D-15 says Reports would be "a 7th tab... alongside the existing 6 (Catalog, Check-Out/In, Procurement & Finance, Licenses & Consumables, Compliance, Software Inventory)." The actual current `ITAMConsole.tsx` (as of this session) has 10 tabs: `catalog`, `lifecycle`, `finance`, `requests`, `licenses`, `compliance`, `software`, `activity`, `data`, `settings`. The extra four (`requests` from Phase 71-03, plus `activity`/`data`/`settings` from later phases) were added after CONTEXT.md's mental model of the console was formed.
**Why it happens:** CONTEXT.md's discuss-phase session referenced an earlier (61-RESEARCH.md-era) description of the console rather than reading the current file.
**How to avoid:** Add the Reports tab as the 11th entry in the `TABS` array and the `Tab` union type in `ITAMConsole.tsx`, immediately after (or wherever logically grouped with) the existing tabs — the exact position is cosmetic (Claude's Discretion territory) but the count claim should not be propagated into the plan as "7th of 7."
**Warning signs:** A plan that lists "insert as the 7th tab" or enumerates only 6 pre-existing tabs — that plan was written against stale context and will produce a diff that doesn't match the real file.

### Pitfall 3: Consumables use a different primary-key shape than every other ITAM entity
**What goes wrong:** `Asset`/`License`/`Component` all mint a prefixed string id (`asset-xxxx`/`lic-xxxx`/`comp-xxxx`) via `default_factory` and store it as the real `_id`. `Consumable` documents are created via `ConsumableCreate.model_dump(by_alias=True)` (which carries no `_id`/`id` key at all), so MongoDB auto-assigns a raw `ObjectId` as `_id` — meaning a consumable's `id` field, once round-tripped through the `Consumable` Pydantic model's `convert_objectid_to_str` validator, is a bare hex ObjectId string with no `con-` prefix, unlike every sibling entity.
**Why it happens:** `itam_consumable_service.py` (Phase 60) never explicitly set an `id`/`_id` on create, unlike `itam_component_service.py`'s explicit `component_id = f"comp-{ObjectId()}"[:20]`.
**How to avoid:** Do not assume consumable ids are format-consistent with asset/license/component ids when displaying them in the field picker or the "Low-stock consumables" report. Display `name` as the primary identifying column for consumables, not raw id, and if any join-by-id logic is added for consumables, confirm whether `db.itam_consumables.find_one({"_id": ...})` needs the string wrapped in `bson.ObjectId(...)` first (the existing `itam_consumable_endpoints.py` passes the path-param string straight through without an explicit `ObjectId()` cast — this may be a pre-existing latent bug in Phase 60, out of scope to fix here, but do not copy the same untested assumption into new report-builder code without verifying it against a live database).
**Warning signs:** A report or filter that tries to join `itam_consumables` to `assets` by an id-equality match and silently returns zero rows.

### Pitfall 4: `TenantIsolatedCollection.aggregate()` does not tenant-scope `$lookup` sub-pipelines
**What goes wrong:** `database.py`'s `TenantIsolatedCollection.aggregate(pipeline)` prepends exactly one `{"$match": {"tenantId": ...}}` stage to the *top-level* pipeline. If that pipeline contains a `$lookup` stage joining to another collection (e.g. `licenses`, `components`, `itam_consumables`), the joined-in documents are matched purely on the `$lookup`'s own `localField`/`foreignField` (or `let`/pipeline) — MongoDB does not know or care about tenant scoping there. Unless the `$lookup`'s own sub-pipeline explicitly re-asserts `tenantId` equality, a report built with `$lookup` could join in another tenant's license/component/consumable rows whenever a local/foreign key value happens to collide (or, worse, whenever the join key is something non-unique).
**Why it happens:** The wrapper's tenant-injection logic (correctly) only guards the collection it is directly called on; it has no visibility into pipeline stages that reference other collections by name.
**How to avoid:** Prefer Python-side joins for this phase's report builder: query `db.assets` (auto-tenant-scoped) first, collect the ids/keys needed (modelId, license assignment targetIds, component parentAssetIds, etc.), then issue separate, also-auto-tenant-scoped `db.licenses.find({"id": {"$in": [...]}})` / `db.components.find({"parentAssetId": {"$in": [...]}})` / `db.itam_consumables.find(...)` calls and merge in application code. If `$lookup` is used anywhere (e.g. for a genuinely large-N report where N+1 queries would be a real performance problem), the `$lookup` MUST use the `pipeline`/`let` form and its sub-pipeline MUST include an explicit `{"$match": {"$expr": {"$eq": ["$tenantId", "$$local_tenant_id"]}}}` (or equivalent) — never a bare `localField`/`foreignField` lookup against a multi-tenant collection.
**Warning signs:** A code review or test that constructs two tenants with the same asset `modelId`/license assignment shape and observes cross-tenant rows in a report's joined output.

### Pitfall 5: No existing generic filter-DSL — the custom report builder's filter engine is genuinely new code, size it accordingly
**What goes wrong:** Underestimating this as "just add a `$or`/`$and` builder" without scoping it to D-03's closed operator set (equals/contains for text; before/after/between for dates; >/</between for numbers) risks either an unsafe fully-generic Mongo-query-from-JSON translator (injection surface — a client-controlled operator like `$where` or `$regex` with a hostile pattern must never reach `db.assets.find()` unfiltered) or an under-scoped one that can't express "warranty expiring within 30 days."
**Why it happens:** "Filter builder" sounds simple in the abstract; the safety requirement (closed operator vocabulary, never passing client-supplied Mongo operator strings straight through) is easy to skip under time pressure.
**How to avoid:** Define an explicit `Literal["equals","contains","before","after","between",">","<"]`-typed Pydantic filter-condition model (each variant validated per field type) and a pure function `_filters_to_mongo_query(conditions: list[FilterCondition]) -> dict` that maps each closed operator to a fixed, hand-written Mongo fragment (`{"$regex": re.escape(value), "$options": "i"}` for `contains`, never an unescaped user string into `$regex`). Never accept a raw Mongo query fragment from the client.
**Warning signs:** A field-picker request body that contains anything shaped like a raw Mongo operator (`$gt`, `$where`, `$regex` as a top-level client-supplied key) rather than the closed `{field, operator, value}` triple.

## Code Examples

### Existing PDF renderer status-color pattern (clone for ITAM reports)
```python
# Source: backend/compliance_reporting_pdf.py lines 20-40 (verified in this repo)
_PDF_STATUS_COLORS = {
    "Compliant":           colors.HexColor("#C6EFCE"),
    "Non-Compliant":       colors.HexColor("#FFC7CE"),
    # ... — for ITAM, remap to e.g. "Expiring"/"Expired"/"Low Stock"/"Overdue"
}

def _find_status_rows(rows_data, col_idx: int):
    cmds = []
    for i, row in enumerate(rows_data[1:], start=1):
        val = str(row[col_idx]) if col_idx < len(row) else ""
        bg = _PDF_STATUS_COLORS.get(val, colors.white)
        if bg != colors.white:
            cmds.append(("BACKGROUND", (col_idx, i), (col_idx, i), bg))
    return cmds
```

### Existing bulk-computed license enrichment (already the "single source of truth" for seat utilization)
```python
# Source: backend/itam_license_endpoints.py lines 24-42, 87-99 (verified in this repo)
def _enrich_license_seats_and_expiry(doc, seats_assigned: int, now) -> dict:
    seat_count = doc.get("seatCount", 0)
    doc["seatsAssigned"] = seats_assigned
    doc["seatsAvailable"] = max(seat_count - seats_assigned, 0)
    # ... daysUntilExpiry / isExpired computed from expiryDate ...
    return doc

@router.get("", response_model=List[Dict[str, Any]])
async def list_licenses(limit: int = Query(200, ge=1, le=500), current_user=Depends(_require_itam_admin)):
    db = get_database()
    licenses = await db.licenses.find({}, {"_id": 0}).limit(limit).to_list(length=limit)
    now = datetime.now(timezone.utc)
    for lic in licenses:
        seats_assigned = await db.license_assignments.count_documents({"licenseId": lic["id"]})
        _enrich_license_seats_and_expiry(lic, seats_assigned, now)
    return licenses
```
This is already bulk-friendly (all licenses in one call, count per license). "License seat utilization" report and the KPI's utilization-% both should call `list_licenses`'s underlying logic (or the function itself) rather than recomputing.

### recharts KPI pattern (clone for `ItamKpiPanel.tsx`)
```tsx
// Source: components/CXODashboard.tsx lines 1-6, 268-364 (verified in this repo)
import { AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
// ...
<ResponsiveContainer width="100%" height={260}>
  <PieChart>
    <Pie data={severityPieData} ... />
    <Tooltip />
    <Legend wrapperStyle={{ fontSize: "10px", fontWeight: "900", textTransform: "uppercase" }} iconType="circle" />
  </PieChart>
</ResponsiveContainer>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| ITAMConsole.tsx had 6 tabs (Catalog/Check-Out-In/Finance/Licenses/Compliance/Software) | ITAMConsole.tsx has 10 tabs (added Requests [71-03], Activity/Data/Settings [Phase 65]) | Phases 65 and 71-03, after 61-RESEARCH.md was written | Any plan referencing "the 6-tab console" (including CONTEXT.md's own D-15) is describing a stale snapshot — see Pitfall 2. |
| No reporting/dashboard surface for ITAM at all | This phase adds the first ITAM-specific Reports tab and KPI surface | This phase (72) | New backend module pair, new frontend panel, new tab. |

**Deprecated/outdated:** None specific to this phase's dependencies — reportlab/openpyxl/recharts are current, actively-used versions already in the repo.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No `reorderThreshold`/`minQuantity` field exists on the `Consumable` model (verified — grepped `itam_models.py` for `reorderThreshold`/`reorder_threshold`/`minQuantity`/`lowStock`, no matches), so the "Low-stock consumables" report needs either (a) a new optional `reorderThreshold` field added to `ConsumableCreate`/`Consumable`/`ConsumableUpdate`, or (b) a fixed heuristic (e.g. `availableQuantity < 0.2 * initialQuantity`). This research recommends (a) with a documented percentage-based fallback for consumables predating the field, but this is a genuine open design decision, not confirmed against a locked user decision. | Pre-built Report Data Sources / D-08 | If planning assumes a field exists that must be added, the plan needs an explicit model-migration task (additive, optional field, no backfill required since it's Optional) — a plan that skips this produces a report with no meaningful "low stock" threshold to filter on. |
| A2 | Recommending a NEW `itam_reporting_service.py`/`itam_reporting_endpoints.py` module pair (rather than extending an existing itam_* file) is this research's judgment call, exercising the discretion CONTEXT.md explicitly leaves open ("Whether the shared report-data function lives in a new `itam_reporting_service.py` or extends an existing itam_* service"). Every existing itam_*_endpoints.py file is already near or over the 500-line CLAUDE.md cap (`itam_lifecycle_endpoints.py` is 534 lines per its own docstring, `asset_endpoints.py` is 511), reinforcing that a new file is the only option that doesn't immediately violate the line cap, but this is a recommendation, not a locked decision. | Recommended Project Structure | Low — this is the module-layout decision CONTEXT.md already delegated to research/planning; a plan choosing differently is not "wrong," just a different valid resolution. |
| A3 | The saved custom report definitions collection name `itam_reports` (and export-metadata collection `itam_report_exports`) are proposed names, not verified against any existing convention beyond the general `itam_*` prefix pattern used by `itam_consumables`/`asset_models`/etc. | System Architecture Diagram / Recommended Project Structure | Low — purely a naming choice; any consistent `itam_*` prefixed name works equally well and does not affect correctness. |

## Open Questions

1. **Does the "Low-stock consumables" report need a real threshold field or a fixed heuristic?**
   - What we know: No threshold field exists today (A1). D-08 requires the report to exist; D-09 says pre-built reports are fixed/non-configurable (which argues for a code-defined default threshold rather than a per-consumable configurable field, simplifying scope).
   - What's unclear: Whether "fixed" (D-09) is meant to preclude even a per-consumable optional field set at catalog-creation time (which wouldn't be report-time-configurable, just data-model-configurable).
   - Recommendation: Add an optional `reorderThreshold: Optional[int] = Field(None, ge=0)` to the Consumable models (additive, non-breaking); the pre-built report treats an unset threshold as a fixed 20%-of-initial-quantity heuristic. This keeps the report itself fixed/non-configurable per D-09 while still letting an admin set a meaningful per-item threshold via the existing consumable edit form if desired. Flag this as a decision to confirm during planning/discuss, not something to silently assume.

2. **Should the custom report builder's "preview" (D-06) and "export" (D-14) share literally the same backend call, or two separate ones?**
   - What we know: D-06 wants an on-screen paginated preview before export; D-12 wants one shared row-building function feeding all renderers.
   - What's unclear: Whether "preview" needs its own lightweight endpoint (e.g. `limit=50` on the same query) versus reusing the full export-shape endpoint with a `preview=true` flag.
   - Recommendation: One `run_custom_report(filters, tenant_id, limit=None)` service function; the preview endpoint calls it with a small `limit` (e.g. 100) and returns JSON, the export endpoints call it with no limit and feed the result into the PDF/Excel/CSV renderers. This keeps D-12's "one shared function" guarantee intact for both preview and export.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| reportlab (Python, `backend/venv`) | PDF export | ✓ | 5.0.0 | — |
| openpyxl (Python, `backend/venv`) | Excel export | ✓ | 3.1.5 | — |
| recharts (npm) | KPI dashboard charts | ✓ | ^3.5.1 | — |
| MongoDB (Motor) | All report queries | ✓ (already running throughout this project) | — | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — every dependency this phase needs is already installed and already in active use elsewhere in the codebase.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest (async, `httpx.AsyncClient`/`ASGITransport`) — existing convention, see `backend/tests/test_itam_finance_bookvalue.py` |
| Backend config/run | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting*.py -x` (must use the project venv — system Python has no pytest, per project memory) |
| Frontend framework | vitest (`"test": "vitest run"` in `package.json`) |
| Frontend config/run | `npx vitest run src/__tests__/ITAMReports*.test.tsx` |
| Existing precedent files | `backend/tests/test_itam_finance_bookvalue.py`, `test_itam_license.py`, `test_itam_lifecycle_history.py` (backend); `src/__tests__/ITAMConsole.test.tsx`, `ITAMActivityLogPanel.test.tsx` (frontend) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-REP-01 | Custom filter build+save, closed operator set, tenant-shared visibility | unit + integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -x` | ❌ Wave 0 |
| ITAM-REP-01 | Custom report gated by admin permission (not accessible to a `view:itam`-only role) | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -k permission -x` | ❌ Wave 0 |
| ITAM-REP-02 | All 6 pre-built reports return correct rows against seeded data, including the reused overdue-audit query | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_prebuilt.py -x` | ❌ Wave 0 |
| ITAM-REP-03 | PDF/CSV/Excel export produces a downloadable file for both custom and pre-built reports; download route rejects path traversal and cross-tenant filenames | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_export.py -x` | ❌ Wave 0 |
| ITAM-REP-04 | 4 KPIs compute correctly against seeded multi-status/multi-license data; tenant isolation on KPI aggregates | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_kpis.py -x` | ❌ Wave 0 |
| ITAM-REP-04 | KPI tile click drills into the correct pre-built report / filtered asset view | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx` | ❌ Wave 0 |
| Cross-tenant join safety (Pitfall 4) | A custom report joining license/component/consumable data never returns another tenant's rows even when ids/keys collide | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -k tenant_isolation -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting*.py -x` (quick, scoped to this phase's new files)
- **Per wave merge:** Full backend suite (`backend/venv/bin/python -m pytest`) + `npx vitest run` + `npm run build`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_itam_reporting_builder.py` — covers ITAM-REP-01 (filter engine, save/list custom reports, admin-gate, cross-tenant join safety)
- [ ] `backend/tests/test_itam_reporting_prebuilt.py` — covers ITAM-REP-02 (all 6 pre-built reports)
- [ ] `backend/tests/test_itam_reporting_export.py` — covers ITAM-REP-03 (pdf/csv/xlsx generation + tenant-safe download)
- [ ] `backend/tests/test_itam_reporting_kpis.py` — covers ITAM-REP-04 backend
- [ ] `src/__tests__/ITAMKpiPanel.test.tsx` — covers ITAM-REP-04 frontend drill-down
- [ ] `src/__tests__/ITAMReportsPanel.test.tsx` — covers Reports tab rendering (pre-built list + custom builder sections, D-10)
- [ ] No shared fixture file exists yet for seeding assets+licenses+consumables+components together in one tenant — a new `backend/tests/itam_reporting_test_support.py` (mirroring `itam_finance_test_support.py`'s existing pattern) is needed to seed cross-entity data for join tests.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (indirect) | Existing `get_current_user`/JWT dependency chain — unchanged by this phase. |
| V3 Session Management | no | No new session concept introduced. |
| V4 Access Control | yes | `_require_itam_admin` (imported, checks `manage:assets` — see Pitfall 1) on every report-builder/pre-built-report/export/KPI route; tenant-ownership check on report file downloads (clone of `compliance_report_endpoints.py::download_report`). |
| V5 Input Validation | yes | Custom filter conditions MUST use a closed, Pydantic-`Literal`-typed operator vocabulary (Pitfall 5) — never accept a raw Mongo query fragment from the client. |
| V6 Cryptography | no | No new crypto surface. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| NoSQL injection via a client-supplied filter operator (e.g. `$where`, unescaped `$regex`) | Tampering | Closed `Literal` operator enum + hand-written Mongo fragments per operator (Pitfall 5); `re.escape()` any user string used in a `contains` `$regex`. |
| Path traversal on report download filename | Tampering / Information Disclosure | `Path(...).resolve()` + `startswith()` containment check, cloned from `compliance_report_endpoints.py::download_report` (already proven in this codebase). |
| Cross-tenant data leakage via `$lookup` in a custom report join | Information Disclosure | Prefer Python-side joins over multiple auto-tenant-scoped `find()` calls; if `$lookup` is used, its sub-pipeline must explicitly re-assert `tenantId` equality (Pitfall 4). |
| Cross-tenant report file access via a guessed/enumerated filename | Information Disclosure | Persisted export-metadata doc's `tenantId` checked against the caller before streaming the file (cloned pattern, not new). |
| Privilege escalation via report builder bypassing the admin gate | Elevation of Privilege | Import the real `_require_itam_admin`, do not redefine a parallel, possibly-looser gate (Pitfall 1). |

## Sources

### Primary (HIGH confidence — read directly from this repository)
- `backend/compliance_reporting_pdf.py`, `compliance_reporting_excel.py`, `compliance_reporting_service.py`, `compliance_report_endpoints.py`, `compliance_reporting_data.py` — the exact export pattern D-11/D-12 mandate reusing.
- `backend/itam_finance_service.py`, `itam_finance_endpoints.py`, `itam_license_service.py`, `itam_license_endpoints.py`, `itam_lifecycle_service.py`, `itam_lifecycle_endpoints.py`, `itam_consumable_service.py`, `itam_consumable_endpoints.py`, `itam_component_service.py`, `itam_component_endpoints.py`, `itam_asset_endpoints.py`, `itam_asset_service.py`, `itam_models.py` — every data source D-08's six pre-built reports read from.
- `backend/database.py` (`TenantIsolatedCollection`/`TenantIsolatedDatabase`, exemption lists) — tenant isolation mechanics, confirming no ITAM collection is exempt and that `aggregate()`'s tenant injection does not extend into `$lookup` sub-pipelines.
- `backend/router_registry.py` — router registration convention and exact insertion point.
- `components/itam/ITAMConsole.tsx`, `components/CXODashboard.tsx`, `components/ExecutiveDashboard.tsx`, `components/ReportingDashboard.tsx` — current tab structure (correcting D-15), recharts usage pattern, generate/download UX precedent.
- `services/apiService.ts` (lines ~3630-3700, ~5480-5610) — existing compliance-report client functions to clone, and the current ~26 ITAM client functions already present.
- `types.ts` (lines 744-933) — full field enumeration for Asset/ItamLicense/ItamConsumable/ItamComponent/ItamBookValue/ItamWarrantyStatus, the source for the report builder's field picker.
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `72-CONTEXT.md` — requirement definitions, project history, locked decisions.

### Secondary (MEDIUM confidence)
- None — no external documentation lookups were needed for this phase; every technical question was answerable directly from the codebase, and no search-provider MCP tools were configured for this session (`brave_search`/`firecrawl`/`exa_search` all `false` in the init context).

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all three libraries (reportlab/openpyxl/recharts) directly version-confirmed in the actual running environment (`pip show`, `package.json` + import grep), not from training-data recall.
- Architecture: HIGH — every pattern cited was read directly from this repository's existing, tested code, not inferred from general framework knowledge.
- Pitfalls: HIGH for Pitfalls 1/2/3/4 (each directly verified by reading the relevant source file and, for Pitfall 1/2, cross-checking against CONTEXT.md's own claim); MEDIUM for Pitfall 5 (the risk pattern itself — NoSQL-injection-via-unscoped-filter — is well-established general knowledge, not verified against a specific exploit in this codebase since the vulnerable code doesn't exist yet).

**Research date:** 2026-08-16
**Valid until:** 30 days (stable internal codebase reuse; no fast-moving external dependency in this phase)
