---
phase: 72-reporting-dashboards
plan: 05
subsystem: api
tags: [fastapi, reportlab, openpyxl, itam, reporting, pdf, excel]

# Dependency graph
requires:
  - phase: 72-reporting-dashboards
    provides: "72-01's build_report_rows/RENDERERS registries and the shared {key,title,columns,rows,rowCount,truncated} report-dict contract every renderer reads; 72-03's custom-report kind branch this plan's renderers also serve"
provides:
  - "backend/itam_reporting_pdf.py — the pdf renderer, a structural clone of compliance_reporting_pdf.py adapted to the shared report dict"
  - "backend/itam_reporting_excel.py — the xlsx renderer, reusing compliance_reporting_excel's domain-agnostic worksheet helpers plus a dedicated ITAM status-color table"
  - "RENDERERS now holds csv/pdf/xlsx — every pre-built and custom report reachable in the Reports tab gains PDF and Excel export with no route or client change"
affects: [72-06, 72-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Case-insensitive ITAM status-color lookup (both PDF _find_status_rows and Excel _apply_status_colors normalize the cell value to lowercase before matching) — itam_finance_service.WARRANTY_STATUS_EXPIRING/_EXPIRED/_ACTIVE are lowercase while itam_reporting_prebuilt's license_utilization report emits Title-case for the same concept; a case-sensitive table would silently under-color one of the two"
    - "Renderer status column resolved by name ('Status' in report['columns']), not a hardcoded index — a report with no Status column (checkout_activity, asset_value) simply gets no coloring rather than an IndexError"

key-files:
  created:
    - backend/itam_reporting_pdf.py
    - backend/itam_reporting_excel.py
  modified:
    - backend/itam_reporting_service.py
    - backend/tests/test_itam_reporting_export.py
    - backend/tests/test_itam_reporting_builder.py

key-decisions:
  - "Defined a dedicated ITAM status-color table (_PDF_STATUS_COLORS in itam_reporting_pdf.py, _XL_STATUS_FILLS/_XL_STATUS_FONTS in itam_reporting_excel.py) rather than importing compliance_reporting_pdf/compliance_reporting_excel's own status tables verbatim — those are keyed by the compliance vocabulary (Compliant/Non-Compliant/Partially Compliant/...) which never appears in an ITAM report's Status column. The Excel renderer still imports compliance_reporting_excel's domain-agnostic _xl_header_row/_xl_auto_width helpers directly (no ITAM-specific behavior in either), matching the plan's 'do not write a third styling implementation' instruction at the mechanism level while keeping the color data ITAM-accurate."
  - "Status-color lookup is case-insensitive in both renderers — discovered mid-implementation that itam_finance_service's WARRANTY_STATUS_EXPIRING/_EXPIRED/_ACTIVE constants are lowercase ('expiring'/'expired'/'active', consumed verbatim by the warranty_expiring report's Status column) while itam_reporting_prebuilt._build_license_utilization_rows independently hardcodes Title-case ('Active'/'Expired') for the license_utilization report's own Status column. A case-sensitive table keyed to either casing alone would silently fail to color the other report's cells; normalizing both the lookup keys and the incoming cell value to lowercase makes the renderer correct against both today's real data and the plan's own Title-case-styled vocabulary description."
  - "itam_reporting_service.py imports itam_reporting_pdf/itam_reporting_excel at module scope (not lazily inside generate()) — verified no circular import exists, since neither renderer module imports itam_reporting_service; both import only compliance_reporting_data (and compliance_reporting_excel for the Excel renderer's shared worksheet helpers)."

patterns-established:
  - "A renderer module takes exactly (report: {key,title,columns,rows,rowCount,truncated}, reports_dir, tenant_id) and returns {filename,url,generatedAt,rowCount,truncated} — the same three-argument/five-key contract now proven across csv/pdf/xlsx; a future renderer format should match this shape rather than reading from build_report_rows itself."

requirements-completed: [ITAM-REP-03]

coverage:
  - id: D1
    description: "Exporting any pre-built or custom report with format=pdf writes a real .pdf file (magic bytes verified) carrying the full match set (not just the preview page), and a zero-row report still produces a valid file with headers and no data rows"
    requirement: "ITAM-REP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestWarrantyExpiringPdfExport::test_pdf_export_writes_real_pdf_carrying_full_match_set"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestWarrantyExpiringPdfExport::test_zero_row_pdf_export_returns_200_with_real_file"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestPdfCustomReportExport::test_custom_report_exports_to_pdf_through_same_route"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exporting any pre-built or custom report with format=xlsx writes a real .xlsx file whose header row equals the declared columns and whose data-row count equals the full match set, a zero-row report produces a header-only workbook, and a Status cell carrying a recognized ITAM status value (case-insensitively) receives the corresponding fill"
    requirement: "ITAM-REP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestWarrantyExpiringExcelExport::test_xlsx_export_header_and_full_match_set"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestWarrantyExpiringExcelExport::test_zero_row_xlsx_export_has_header_only"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestWarrantyExpiringExcelExport::test_status_cell_receives_fill_for_expiring"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestXlsxCustomReportExport::test_custom_report_exports_to_xlsx_through_same_route"
        status: pass
    human_judgment: false
  - id: D3
    description: "A PDF/Excel export is recorded in itam_report_exports with the caller's tenant, so the existing download route's ownership check covers both new formats — owning tenant downloads succeed, cross-tenant downloads 403"
    requirement: "ITAM-REP-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestWarrantyExpiringPdfExport::test_pdf_export_recorded_in_exports_and_cross_tenant_403"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every exported cell passes through the existing formula-injection sanitiser before it is written, in both new formats"
    requirement: "ITAM-REP-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_reporting_export.py#TestPdfFormulaInjectionDefused::test_formula_trigger_cell_is_sanitized_before_rendering"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_reporting_export.py#TestXlsxFormulaInjectionDefused::test_formula_trigger_cell_is_written_defused"
        status: pass
    human_judgment: false
  - id: D5
    description: "RENDERERS holds exactly csv, pdf and xlsx, and the same report exported in all three formats reports an identical rowCount"
    requirement: "ITAM-REP-03"
    verification:
      - kind: unit
        ref: "python -c \"import itam_reporting_service as s; print(sorted(s.RENDERERS))\" -> ['csv', 'pdf', 'xlsx']"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_export.py#TestExportFormatsAgree::test_csv_pdf_xlsx_report_identical_row_count"
        status: pass
    human_judgment: false

# Metrics
duration: ~18min
completed: 2026-08-17
status: complete
---

# Phase 72 Plan 05: PDF and Excel Report Export Summary

**Two new RENDERERS entries (pdf via reportlab, xlsx via openpyxl) cloned structurally from the compliance exporters and adapted to the shared {key,title,columns,rows} report dict — every pre-built and custom ITAM report gains PDF/Excel export with zero route or client change, plus a case-insensitive ITAM status-color table that tolerates a real casing inconsistency between the warranty and license reports' own Status columns.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-08-17T08:50:00Z (approx.)
- **Completed:** 2026-08-17T09:08:00Z
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `backend/itam_reporting_pdf.py`: landscape-letter PDF renderer (`_generate_pdf`) built from `compliance_reporting_pdf.py`'s own `SimpleDocTemplate`/`Paragraph`/`TableStyle` mechanics, reading the shared `{key,title,columns,rows,rowCount,truncated}` dict instead of compliance's framework/asset_summary/control_rows tuple; every cell passes through `_sanitize_cell` then `html.escape` before rendering; a truncated report gets a visible truncation line.
- `backend/itam_reporting_excel.py`: one-worksheet XLSX renderer (`_generate_excel`) reusing `compliance_reporting_excel`'s domain-agnostic `_xl_header_row`/`_xl_auto_width` helpers directly, with a dedicated ITAM status-color table (compliance's own table is keyed to a vocabulary — Compliant/Non-Compliant — that never appears in an ITAM report).
- `RENDERERS` now maps `csv`/`pdf`/`xlsx` to their renderers in `itam_reporting_service.py` — no endpoint file changed; the pre-built and custom export routes already dispatch through this registry.
- Discovered and fixed a real cross-report data inconsistency during implementation: `itam_finance_service`'s warranty-status constants are lowercase (`"expiring"`/`"expired"`/`"active"`) while `itam_reporting_prebuilt`'s license-utilization report independently emits Title-case (`"Active"`/`"Expired"`) for the same concept. Both new renderers do a case-insensitive status-color lookup so neither report's Status column silently goes uncolored.
- 26 new tests added to `backend/tests/test_itam_reporting_export.py` (13 PDF, 13 Excel including the cross-format row-count agreement test) plus 2 pre-existing "unregistered format" tests (in this file and in `test_itam_reporting_builder.py`) retargeted from `format=pdf` to `format=xml`, since `pdf` became a real, activated format this plan. Full reporting suite: 105/105 pass. Full backend suite: 2292 passed / 34 skipped / 11 failed — identical to the pre-existing baseline documented in `72-03-SUMMARY.md` (none touch `itam_reporting_*`).

## Task Commits

Each task was committed atomically:

1. **Task 1: PDF renderer registered as the pdf format** - `6c3b709b` (feat)
2. **Task 2: Excel renderer registered as the xlsx format** - `3f86d53d` (feat)

**Plan metadata:** _pending — this commit_

## Files Created/Modified
- `backend/itam_reporting_pdf.py` - `_PDF_STATUS_COLORS`, `_find_status_rows`, `_status_column_index`, `_generate_pdf`
- `backend/itam_reporting_excel.py` - `_XL_STATUS_FILLS`/`_XL_STATUS_FONTS`, `_apply_status_colors`, `_status_column_index`, `_generate_excel`
- `backend/itam_reporting_service.py` - imports and registers `pdf`/`xlsx` into `RENDERERS`
- `backend/tests/test_itam_reporting_export.py` - 26 new tests across PDF/Excel export/download/custom-report/status-fill/formula-defusal/cross-format behaviors; retargeted the "unregistered format" test off `format=pdf`
- `backend/tests/test_itam_reporting_builder.py` - retargeted its own "unregistered format" test off `format=pdf` for the same reason (Rule 1 fix, file outside this plan's declared scope but directly broken by the pdf registration)

## Decisions Made
- Defined ITAM-specific status-color tables in both new renderer modules rather than importing compliance's own tables verbatim — compliance's vocabulary (Compliant/Non-Compliant/Partially Compliant) never appears in an ITAM report's Status column. Only the domain-agnostic Excel worksheet helpers (`_xl_header_row`/`_xl_auto_width`) are imported directly from `compliance_reporting_excel.py`.
- Made both status-color lookups case-insensitive after discovering the real warranty_expiring report emits lowercase status strings (`"expiring"`) while the license_utilization report emits Title-case (`"Active"`/`"Expired"`) — a case-sensitive table keyed to either alone would silently under-color the other report.
- Registered `itam_reporting_pdf`/`itam_reporting_excel` at module scope in `itam_reporting_service.py` (not inside `generate()`) after confirming neither renderer module imports `itam_reporting_service`, so there is no circular-import risk.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Retargeted 2 pre-existing "unregistered format" tests off `format=pdf`**
- **Found during:** Task 1, before running the full reporting suite
- **Issue:** `backend/tests/test_itam_reporting_export.py::TestWarrantyExpiringExport::test_unregistered_format_returns_400` and `backend/tests/test_itam_reporting_builder.py::TestExportCustomReport::test_export_unregistered_format_returns_400` both asserted `format=pdf` returns 400 (unregistered). Registering `pdf` into `RENDERERS` in Task 1 would make both tests fail against real behavior (pdf now returns 200).
- **Fix:** Retargeted both tests to `format=xml` (a genuinely unregistered format), with a comment explaining why.
- **Files modified:** `backend/tests/test_itam_reporting_export.py`, `backend/tests/test_itam_reporting_builder.py`
- **Verification:** Both tests pass; full reporting suite (105 tests) green.
- **Committed in:** `6c3b709b` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1, test correctness caused directly by this plan's own registration change).
**Impact on plan:** No scope creep — the fix was a direct, necessary consequence of Task 1's own change (registering `pdf`), touching one file (`test_itam_reporting_builder.py`) outside this plan's declared `files_modified` list but required to keep the existing suite green.

## Issues Encountered
- The warranty/license status-casing inconsistency described above (a pre-existing data-shape mismatch between two different pre-built reports, not introduced by this plan) — resolved by making both new renderers' status-color lookups case-insensitive rather than attempting to normalize `itam_reporting_prebuilt.py` (out of this plan's file scope).

## User Setup Required
None - no external service configuration required. `reportlab` and `openpyxl` were already installed in `backend/venv` (used by the compliance exporters since v1.0).

## Next Phase Readiness
- `RENDERERS` now holds `csv`/`pdf`/`xlsx` — every pre-built and custom report reachable in the Reports tab has all three D-11 export formats with no route or client change. Plan 72-06/72-07 can build on a stable, fully-populated `RENDERERS` registry.
- The `_generate_pdf`/`_generate_excel` three-argument/five-key contract is stable public surface for any future renderer format.
- Full backend suite confirmed at the identical 11-pre-existing-failure baseline (`test_agentic_ai`, `test_e2e_integration`, `test_itam_audit`, `test_powershell_evidence` x2, `test_rotate_key_wiring`, `test_rust_heartbeat_parity`, `test_secret_manager_service` x4) — none touch this plan's files.

---
*Phase: 72-reporting-dashboards*
*Completed: 2026-08-17*

## Self-Check: PASSED

Both created files (`backend/itam_reporting_pdf.py`, `backend/itam_reporting_excel.py`) found on disk; both task commits (`6c3b709b`, `3f86d53d`) found in git history.
