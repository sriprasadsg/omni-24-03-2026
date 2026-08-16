# Phase 72: Reporting & Dashboards - Context

**Gathered:** 2026-08-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver ITAM reporting and a KPI dashboard, scoped strictly to ITAM asset/license/consumable/component/finance data (not security/compliance reporting — those already have separate, established systems: `compliance_reporting_pdf.py`/`excel.py`, `oscal_endpoints.py`, `sbom_endpoints.py`).

Four requirements: ITAM-REP-01 (custom report builder, build+save), ITAM-REP-02 (pre-built reports), ITAM-REP-03 (PDF/CSV/Excel export), ITAM-REP-04 (KPI dashboard with visualizations).

</domain>

<decisions>
## Implementation Decisions

### Custom Report Builder (ITAM-REP-01)
- **D-01:** Reports are asset-rooted only — every report starts from the `assets` collection, optionally joining license/consumable/component/finance fields onto asset rows. No independent license-only or consumable-only report root. — **Reversibility:** costly — adding a non-asset root later means a second query path through the builder UI and backend, not just a data addition.
- **D-02:** Builder UX is a field + filter picker (select columns, add filter conditions), not a "pick report type then filter" form — this is what makes it "custom" per ITAM-REP-01's wording.
- **D-03:** Filter operators: equals/contains for text, date-range (before/after/between) for dates, numeric comparison (>/</between) for numbers — needed for filters like "warranty expiring within 30 days" or "cost > $1000".
- **D-04:** Saved custom report definitions are shared tenant-wide (any user with builder access can see/reuse them), not private per-creator.
- **D-05:** No cap on saved reports per tenant.
- **D-06:** Builder shows an on-screen paginated results preview before the user exports — catches a bad filter before generating a file.
- **D-07:** Report builder access is gated by `manage:itam` (the same admin gate as other ITAM management surfaces — `_require_itam_admin`, Phase 47/48/61/63 pattern), not the wider `view:itam`.

### Pre-built Reports (ITAM-REP-02)
- **D-08:** Six pre-built reports ship: Asset value/depreciation summary, Check-out/check-in activity log, Warranty expiring, License seat utilization, Low-stock consumables, Overdue physical audits.
- **D-09:** Pre-built reports are fixed (code-defined, no user-configurable params) — contrast with the custom builder, which already covers configurability.
- **D-10:** Pre-built and custom reports live in one "Reports" tab with two sections (pre-built list + "Create Custom Report" action), not separate tabs.

### Export (ITAM-REP-03)
- **D-11:** Export reuses the `compliance_reporting_pdf.py`/`compliance_reporting_excel.py` pattern (reportlab for PDF, openpyxl for Excel, file written and returned as download) — not `scheduled_reports_service.py`'s inline-HTML-to-bytes pattern, which is built for the scheduled-email use case.
- **D-12:** One shared report-data-building function feeds all three renderers (PDF, Excel, CSV) — avoids drift between formats. CSV is the simplest renderer on top of that shared data.
- **D-13:** Export is on-demand only — no scheduled/recurring delivery in this phase. `scheduled_reports_service.py` exists as a generic scheduler a future phase could wire ITAM reports into; lifecycle/warranty alerts are already covered separately by Phase 71's ITAM-PRO-05.
- **D-14:** Export applies to both custom-built AND pre-built reports — ITAM-REP-03's wording doesn't distinguish the two.

### KPI Dashboard (ITAM-REP-04)
- **D-15:** Dashboard is a 7th tab in `ITAMConsole.tsx`, alongside the existing 6 (Catalog, Check-Out/In, Procurement & Finance, Licenses & Consumables, Compliance, Software Inventory) — not a new landing view replacing the console's current entry tab.
- **D-16:** Four KPIs: total asset value + count by status/lifecycle stage, license utilization % (seats used/available), upcoming warranty expirations (count/timeline), overdue check-ins/audits count.
- **D-17:** Chart library is `recharts` — already a dependency, already used in `CXODashboard.tsx`/`ExecutiveDashboard.tsx`/`PatchManagementDashboard.tsx`. No new charting dependency.
- **D-18:** KPI tiles are clickable and drill into the corresponding pre-built report or a filtered asset list — not static read-only numbers.

### Claude's Discretion
- Exact column set exposed by the field picker per entity (asset/license/consumable/component/finance) — pick from existing model fields, no new fields need to be invented.
- Exact wording/layout of the two-section Reports tab and the KPI tile grid.
- Whether the shared report-data function lives in a new `itam_reporting_service.py` or extends an existing itam_* service — implementation detail for research/planning to resolve against the existing module layout.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & gap analysis
- `.planning/REQUIREMENTS.md` — ITAM-REP-01..04 definitions and traceability table
- `.planning/codebase/ITAM-VS-SNIPE.md` §7 (Reporting & Analytics) — the Snipe-IT parity gap this phase closes; also §9/§10 for adjacent out-of-scope items (scheduled reports, webhooks) not to pull in
- `.planning/ROADMAP.md` Phase 72 section — goal, requirements, success criteria

### Existing export/report patterns to reuse
- `backend/compliance_reporting_pdf.py` — reportlab PDF generation pattern (status-color rows, tenant header) to clone for ITAM reports
- `backend/compliance_reporting_excel.py` — openpyxl Excel generation pattern (header styling, auto-width, status colors, hyperlinks) to clone
- `backend/scheduled_reports_service.py` — existing generic report scheduler; NOT used this phase (D-13) but the integration point for a future scheduling phase

### Existing ITAM backend to build on
- `backend/itam_finance_service.py` — book-value/depreciation calc and warranty/alert-window fields (feeds D-08's Asset value and Warranty Expiring reports, and D-16's KPIs)
- `backend/itam_license_service.py` — Phase 60's `seatsAssigned`/`seatsAvailable`/`isExpired` computed fields (feeds License seat utilization report + KPI)
- `backend/itam_lifecycle_service.py` — `assignment_history` append-only ledger (feeds Check-out/check-in activity log) and overdue-audit query (feeds Overdue physical audits report)
- `backend/itam_consumable_service.py` — consumable quantity data (feeds Low-stock consumables report)
- `backend/itam_asset_service.py` / `backend/itam_models.py` — the single `assets` collection with `assetSource` discriminator this phase's report builder queries (D-01)

### Existing frontend to build on
- `components/itam/ITAMConsole.tsx` — 6-tab console shell; Reports becomes the 7th tab (D-15)
- `components/CXODashboard.tsx`, `components/ExecutiveDashboard.tsx` — recharts KPI-dashboard precedents to follow (D-17)
- `services/apiService.ts` — existing ~26 ITAM client functions to extend

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compliance_reporting_pdf.py`/`compliance_reporting_excel.py` helpers (`_xl_header_row`, `_xl_auto_width`, `_apply_status_colors`, `_find_status_rows`) — directly reusable for ITAM report tables
- `itam_finance_service.py`'s straight-line depreciation calc, `itam_license_service.py`'s seat-availability computation, `itam_lifecycle_service.py`'s overdue-audit query — all pre-built reports read these, none need new business logic
- `recharts` (already in `package.json`) — no new dependency for the KPI dashboard

### Established Patterns
- `_require_itam_admin` — the `manage:itam` gate used across `itam_consumable_endpoints.py`/`itam_component_endpoints.py`/etc. (Phase 47/48/61/63 precedent) — applies to the report builder (D-07)
- Single `assets` collection with `assetSource` discriminator (v4.0's central architectural decision) — reports must query this, never a parallel collection (D-01)
- Tenant-isolation via raw `_mdb.db` + explicit `set_tenant_id` for any background/scheduled work — not applicable this phase since export is on-demand only (D-13), but relevant if a future phase adds scheduling

### Integration Points
- New Reports tab registers in `ITAMConsole.tsx`'s existing tab array, same nav-gate pattern as the other 6 tabs
- Report/KPI drill-down (D-18) navigates to either a pre-built report view or a filtered asset list within the same console — no new route needed, tab-internal state

</code_context>

<specifics>
## Specific Ideas

No specific UI mockups or exact wording were given — standard approach expected, following the console's existing tab/table/toast conventions.

</specifics>

<deferred>
## Deferred Ideas

- Scheduled/recurring ITAM report delivery via email — explicitly deferred (D-13); `scheduled_reports_service.py` is the future integration point.
- Report-builder support for a non-asset-rooted query (independent license/consumable reports) — deferred (D-01); revisit if asset-rooted joins prove insufficient in practice.

### Reviewed Todos (not folded)
None — no pending todos matched this phase (`todo.match-phase` returned 0 matches).

</deferred>

---

*Phase: 72-reporting-dashboards*
*Context gathered: 2026-08-16*
