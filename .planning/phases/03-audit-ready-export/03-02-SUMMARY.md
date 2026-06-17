---
phase: 03-audit-ready-export
plan: 02
subsystem: compliance-reporting
tags: [audit, pdf, xlsx, tenant-header, evidence-columns, tdd]
dependency_graph:
  requires:
    - compliance_reporting_data._build_report_data with tenant_id param (03-01)
    - compliance_reporting_data._flatten_evidence with auto_count/manual_count (03-01)
    - compliance_reporting_data.STATUS_LEGEND constant (03-01)
  provides:
    - compliance_reporting_pdf._generate_pdf with tenant_id param and tenant header
    - compliance_reporting_excel._generate_excel with tenant_id param and tenant header
    - compliance_reporting_excel._generate_all_excel with tenant_id param and tenant header
    - Auto Evidence / Manual Evidence columns rendered in PDF and XLSX (AUDIT-03)
  affects:
    - compliance_reporting_service.py (caller forwards tenant_id to all generators)
tech_stack:
  added: []
  patterns:
    - TDD red-green cycle; signature-inspection tests for generator params
    - tenant name resolved via db.tenants.find_one with fallback to tenant_id / "Unknown Tenant"
    - det_widths list extended with 0.6-inch slots for two new numeric columns
key_files:
  created: []
  modified:
    - backend/compliance_reporting_pdf.py
    - backend/compliance_reporting_excel.py
    - backend/compliance_reporting_service.py
    - backend/tests/test_audit_export.py
decisions:
  - "tenant_id added as trailing optional str=None to _generate_pdf, _generate_excel, _generate_all_excel for backward compatibility"
  - "tenant name lookup via db.tenants.find_one({'id': tenant_id}); fallback chain: tenant_doc.name -> tenant_id -> 'Unknown Tenant'"
  - "det_widths list now has 15 entries covering all 15 control_rows columns including Auto Evidence and Manual Evidence at 0.6 inch each"
  - "_generate_all_excel param order: reports_dir, tenant_id=None, db=None (tenant_id before db to keep positional safety)"
  - "STATUS_LEGEND surface deferred to Wave 3 per w4_resolution — vocabulary mapping added to plan but not rendered in this wave"
metrics:
  duration: "~3m"
  completed: "2026-06-18"
  tasks: 2
  files: 4
---

# Phase 03 Plan 02: Audit Export Generators (PDF + XLSX) Summary

**One-liner:** Surfaced tenant name, export date, and Auto/Manual evidence columns in both PDF and XLSX generators by threading tenant_id through the generator signatures and adding a db.tenants lookup.

## What Was Built

### RED phase — failing test scaffold

Added two tests to `backend/tests/test_audit_export.py`:

- `test_pdf_header_fields`: inspects `_generate_pdf` signature for `tenant_id` param (default `None`)
- `test_xlsx_header_fields`: inspects `_generate_excel` and `_generate_all_excel` signatures for `tenant_id` param

Both tests were RED as expected before production changes.

### Task 1 — PDF tenant header and evidence columns (AUDIT-01, AUDIT-03)

Modified `backend/compliance_reporting_pdf.py`:

- `_generate_pdf` signature changed to `(framework_id: str, reports_dir: str, tenant_id: str = None)`
- Tenant name resolved at function top: `db.tenants.find_one({"id": tenant_id})` with fallback to `tenant_id` or `"Unknown Tenant"`
- `_build_report_data` called with `tenant_id` argument for tenant-scoped data
- PDF subtitle paragraph updated to include `Tenant: {tenant_name}` and `Export Date: {YYYY-MM-DD}` segments before the existing `Generated:` field (AUDIT-01)
- `det_widths` extended from 13 to 15 entries: two `0.6`-inch slots inserted at positions 8 and 9 (immediately after `Evidence Count`) for `Auto Evidence` and `Manual Evidence` columns

Modified `backend/compliance_reporting_service.py`:

- `generate_pdf_report` now calls `_generate_pdf(framework_id, self.reports_dir, tenant_id)`

### Task 2 — XLSX tenant header and evidence columns (AUDIT-02, AUDIT-03)

Modified `backend/compliance_reporting_excel.py`:

- `_generate_excel` signature changed to `(framework_id: str, reports_dir: str, tenant_id: str = None)`
- Tenant name resolved identically to PDF generator
- `_build_report_data` called with `tenant_id`
- ws1 header block gains two new rows after the title: `Tenant: {tenant_name}` and after `Generated:` row: `Export Date: {YYYY-MM-DD}` (AUDIT-02)
- Control Details sheet (ws2) inherits `Auto Evidence`/`Manual Evidence` columns automatically — `headers2 = list(control_rows[0].keys())` requires no changes
- `_apply_status_colors`/`_apply_url_hyperlink` index lookups on named keys are unaffected (the new columns are numeric and use different names)
- `_generate_all_excel` signature changed to `(reports_dir: str, tenant_id: str = None, db=None)` (`tenant_id` before `db` to preserve backward-compatible keyword call)
- Overview sheet gains `Tenant: {tenant_name}` row after the title
- `_build_report_data(fw_id, tenant_id)` called in the per-framework loop

Modified `backend/compliance_reporting_service.py`:

- `generate_excel_report` now calls `_generate_excel(framework_id, self.reports_dir, tenant_id)`
- `generate_all_excel_report` now calls `_generate_all_excel(self.reports_dir, tenant_id=tenant_id)`

## Verification Results

```
cd backend && ./venv/bin/python -m pytest tests/test_audit_export.py -x -q
6 passed in 1.35s

grep -n "tenants.find_one" compliance_reporting_pdf.py compliance_reporting_excel.py
compliance_reporting_pdf.py:47:        tenant_doc = await db.tenants.find_one({"id": tenant_id})
compliance_reporting_excel.py:85:        tenant_doc = await db.tenants.find_one({"id": tenant_id})
compliance_reporting_excel.py:160:        tenant_doc = await db.tenants.find_one({"id": tenant_id})

grep -nc "Tenant:" compliance_reporting_excel.py
2

wc -l compliance_reporting_pdf.py compliance_reporting_excel.py compliance_reporting_service.py
151 / 263 / 143 — all under 500 lines
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no stub patterns or placeholder data introduced.

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond those scoped in the plan threat model. Tenant lookup reads only the caller's own tenant document (T-03-04: accepted per plan).

## Self-Check: PASSED

- `backend/compliance_reporting_pdf.py` contains `tenant_id` param and `tenants.find_one` — FOUND
- `backend/compliance_reporting_excel.py` contains `tenant_id` param and `tenants.find_one` — FOUND
- `backend/compliance_reporting_service.py` forwards `tenant_id` to all four generator methods — FOUND
- `backend/tests/test_audit_export.py` contains `test_pdf_header_fields` and `test_xlsx_header_fields` — FOUND
- Commits: f8ff894 (RED test), 146e793 (PDF GREEN), baf713f (XLSX GREEN) — all present in git log
