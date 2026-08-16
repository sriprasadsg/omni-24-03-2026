# Phase 72: Reporting & Dashboards - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-16
**Phase:** 72-reporting-dashboards
**Areas discussed:** Report builder scope, Pre-built reports catalog, Export mechanics, KPI dashboard placement & content

---

## Report builder scope

| Option | Description | Selected |
|--------|-------------|----------|
| Assets only | Narrowest — asset fields only | |
| Assets + Licenses/Consumables/Components | Covers the entities tracked in the console's other 5 tabs | |
| All ITAM entities incl. Finance (cost/warranty/depreciation) | Widest — joins itam_finance_service data too | ✓ |

**User's choice:** All ITAM entities incl. Finance

| Option | Description | Selected |
|--------|-------------|----------|
| Field + filter picker | User picks columns and filter conditions — a real "custom" builder | ✓ |
| Pick report type, then filter params | Simpler, closer to configuring a pre-built report | |

**User's choice:** Field + filter picker

| Option | Description | Selected |
|--------|-------------|----------|
| Shared tenant-wide | Any tenant user with ITAM access can see/reuse saved reports | ✓ |
| Private per-user | Only the creator sees their saved reports | |

**User's choice:** Shared tenant-wide

| Option | Description | Selected |
|--------|-------------|----------|
| On-screen paginated preview, then export | User sees results before exporting | ✓ |
| Export-only, no preview | Builder configures the report; results only in the exported file | |

**User's choice:** On-screen paginated preview, then export

| Option | Description | Selected |
|--------|-------------|----------|
| Asset-rooted only | Every report starts from the assets collection | ✓ |
| User picks root entity | Report can start from assets, licenses, or consumables independently | |

**User's choice:** Asset-rooted only

| Option | Description | Selected |
|--------|-------------|----------|
| manage:itam admin gate | Matches the Phase 47/48/61 admin-gated pattern | ✓ |
| view:itam (any ITAM viewer) | Wider access | |

**User's choice:** manage:itam admin gate

| Option | Description | Selected |
|--------|-------------|----------|
| Equals/contains + date-range + numeric comparison | Needed for filters like "warranty expiring within 30 days" or "cost > $1000" | ✓ |
| Equals/contains only | Simpler, less precise | |

**User's choice:** Equals/contains + date-range + numeric comparison

| Option | Description | Selected |
|--------|-------------|----------|
| No cap | Unbounded, matches codebase's general pattern | ✓ |
| Cap it (e.g. 50) | Adds a guard rail against runaway growth | |

**User's choice:** No cap

**Notes:** None.

---

## Pre-built reports catalog

| Option | Description | Selected |
|--------|-------------|----------|
| Asset value / depreciation summary | Reads itam_finance_service's existing straight-line calc | ✓ |
| Check-out/check-in activity log | Reads the existing assignment_history ledger | ✓ |
| Warranty expiring | Reads itam_finance_service's warranty/alert-window fields | ✓ |
| License seat utilization | Reads Phase 60's seatsAssigned/seatsAvailable/isExpired fields | ✓ |
| Low-stock consumables | Consumables below a reorder threshold | ✓ |
| Overdue physical audits | Reads Phase 57's overdue-audit query | ✓ |

**User's choice:** All 6 reports selected.

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed, no params | Each pre-built report runs as-is | ✓ |
| Light params (date range / location filter) | Each report accepts 1-2 optional filters | |

**User's choice:** Fixed, no params

| Option | Description | Selected |
|--------|-------------|----------|
| One Reports tab, two sections | Pre-built list + "Create Custom Report" action in the same tab | ✓ |
| Separate tabs for pre-built vs custom | Two distinct tabs | |

**User's choice:** One Reports tab, two sections

**Notes:** None.

---

## Export mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| compliance_reporting_pdf.py/excel.py pattern | reportlab + openpyxl, file written and returned as download | ✓ |
| scheduled_reports_service.py pattern | Inline HTML-to-PDF-bytes, built for scheduled email | |

**User's choice:** compliance_reporting_pdf.py/excel.py pattern

| Option | Description | Selected |
|--------|-------------|----------|
| On-demand only | No scheduling; scheduled_reports_service.py stays a future integration point | ✓ |
| Include scheduled delivery | Wire ITAM reports into the existing scheduler now | |

**User's choice:** On-demand only

| Option | Description | Selected |
|--------|-------------|----------|
| Same data path, CSV is just a different renderer | One report-data function feeds three renderers | ✓ |
| CSV built independently | Separate, simpler code path | |

**User's choice:** Same data path, CSV is just a different renderer

| Option | Description | Selected |
|--------|-------------|----------|
| Both | Every report — pre-built or custom — exports in PDF/CSV/Excel | ✓ |
| Pre-built only | Custom reports stay on-screen only | |

**User's choice:** Both

**Notes:** None.

---

## KPI dashboard placement & content

| Option | Description | Selected |
|--------|-------------|----------|
| 7th tab in ITAMConsole.tsx | Matches the existing 6-tab pattern | ✓ |
| Landing view when opening ITAM Console | Bigger UX change to an already-shipped console | |

**User's choice:** 7th tab in ITAMConsole.tsx

| Option | Description | Selected |
|--------|-------------|----------|
| Total asset value + count by status/lifecycle | Reuses itam_finance_service book-value calc | ✓ |
| License utilization % (seats used/available) | Reuses Phase 60's seat fields | ✓ |
| Upcoming warranty expirations (count/timeline) | Reuses warranty alert-window data | ✓ |
| Overdue check-ins/audits count | Reuses Phase 57's overdue-audit query | ✓ |

**User's choice:** All 4 KPIs selected.

| Option | Description | Selected |
|--------|-------------|----------|
| recharts | Already a dependency, used in CXODashboard.tsx/ExecutiveDashboard.tsx | ✓ |
| Something else | New dependency | |

**User's choice:** recharts

| Option | Description | Selected |
|--------|-------------|----------|
| Clickable, links to the report | Each KPI tile navigates to its corresponding report/filtered list | ✓ |
| Static numbers only | Read-only summary | |

**User's choice:** Clickable, links to the report

**Notes:** None.

---

## Claude's Discretion

- Exact column set exposed by the field picker per entity.
- Exact wording/layout of the two-section Reports tab and the KPI tile grid.
- Whether the shared report-data function lives in a new `itam_reporting_service.py` or extends an existing itam_* service.

## Deferred Ideas

- Scheduled/recurring ITAM report delivery via email — future integration with `scheduled_reports_service.py`.
- Report-builder support for a non-asset-rooted query — revisit if asset-rooted joins prove insufficient.
