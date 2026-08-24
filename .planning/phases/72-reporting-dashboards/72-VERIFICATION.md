---
phase: 72-reporting-dashboards
verified: 2026-08-24T13:45:00Z
status: human_needed
score: 30/32 must-haves verified (2026-08-24 same-day fix: WR-01 regression test added, see addendum)
behavior_unverified: 2
overrides_applied: 0
re_verification: # Retroactive — no prior VERIFICATION.md existed in the phase directory
  previous_status: null
  note: "72-UAT.md declares `source: [72-VERIFICATION.md]` but no such file was present. This report is the retroactive reconstruction; the three pending 72-UAT items are carried forward verbatim below."
behavior_unverified_items:
  - truth: "The preview table stays horizontally scrollable via an overflow-x-auto wrapper when many columns are selected."
    test: "Open the ITAM console Reports tab, build a custom report selecting many columns (10+), and run it."
    expected: "The preview table scrolls horizontally inside its card rather than overflowing the console layout."
    why_human: "Marked `verification: backstop` in 72-01-PLAN.md must_haves. The `overflow-x-auto` wrapper is present at components/itam/ReportsPanel.tsx:314, but whether the rendered table actually scrolls (rather than the card growing or clipping) at a real column count is a rendered-layout property no unit test exercises."
  - truth: "Preview cells truncate with the truncate class plus a title tooltip rather than growing row height."
    test: "Run a report whose rows contain a very long cell value (e.g. a long asset description) and hover the cell."
    expected: "The cell truncates with an ellipsis at max-w-xs and reveals the full value via the native title tooltip; row height stays constant."
    why_human: "Marked `verification: backstop` in 72-01-PLAN.md must_haves. `truncate max-w-xs` + `title={cellDisplay(row[c])}` are present at components/itam/ReportsPanel.tsx:329-330, but the visual truncation/tooltip behaviour is not asserted by any test."
  # WR-01 (date-range `between` reversed bounds) removed 2026-08-24 — closed by
  # test_between_date_swaps_reversed_bounds in test_itam_reporting_builder.py.
  # See the Re-verification note in the body for the full account.
human_verification:
  - test: "Tenant brand-colour accent rendering — open the ITAM console Reports tab and confirm the tab's accent underline and the KPI panel's chart primary-series colour match the active tenant's configured brand colour."
    expected: "Accent colour matches the active tenant's configured brand colour, consistent with every other ITAMConsole tab's accent theming."
    why_human: "Carried forward from 72-UAT.md test 1. Theme-colour propagation into recharts series is a rendered-appearance property."
  - test: "Preview table horizontal scroll + cell truncation tooltip — in the custom builder select many columns and run a report containing a long cell value."
    expected: "Table scrolls horizontally inside its card rather than overflowing; long cells truncate with a title tooltip rather than growing row height."
    why_human: "Carried forward from 72-UAT.md test 2. Covers both `verification: backstop` must-haves from 72-01-PLAN.md (see behavior_unverified_items 1 and 2)."
  - test: "KPI empty-state visual presentation — view the KPI tiles on a tenant with no ITAM data, and again on a tenant with data."
    expected: "Empty tiles read as 'No data yet' with entity-specific next-step copy — never a 0% or 100% presented as a measurement."
    why_human: "Carried forward from 72-UAT.md test 3. The no-data contract is unit-tested at both ends (backend `test_every_kpi_reports_no_data_on_empty_tenant_never_a_fabricated_number`, frontend `a KPI payload with hasData false renders \"No data yet\" and never a fabricated 0% or 100%`), but the against-real-data visual read is human."
---

# Phase 72: Reporting & Dashboards Verification Report

**Phase Goal:** Provide custom report building, pre-built reports, export functionality, and a KPI dashboard.
**Success Criteria:** (1) User can build and save custom reports. (2) User can view pre-built reports for asset/license data. (3) User can export reports in PDF, CSV, and Excel. (4) User can view the ITAM dashboard with key KPIs and visualizations.
**Verified:** 2026-08-24
**Status:** human_needed
**Re-verification:** No — retroactive initial verification (doc-debt backfill; no prior VERIFICATION.md existed)

## Goal Achievement

### Observable Truths

Test evidence below is from runs executed during this verification, not from SUMMARY claims:
`backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_{builder,export,kpis,prebuilt}.py -q` → **106 passed**;
`npx vitest run src/__tests__/ITAM{ReportsPanel,KpiPanel,Console}.test.tsx` → **53 passed**.

#### Success Criterion 1 — User can build and save custom reports (ITAM-REP-01)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An ITAM admin picks columns and filter conditions, runs a custom report, saves the definition and re-runs it later | ✓ VERIFIED | Full route set in `backend/itam_reporting_endpoints.py:204-352` (`GET /fields`, `POST /custom`, `GET /custom`, `POST /custom/preview`, `GET/DELETE /custom/{id}`, `POST /custom/{id}/run`, `POST /custom/{id}/export`); UI in `components/itam/ReportBuilderForm.tsx`; tests `test_save_stores_definition_and_returns_generated_id_and_tenant`, `test_run_returns_same_rows_twice_for_unchanged_data` pass |
| 2 | Every custom report is rooted in the `assets` collection; licence/consumable/component/finance data joins onto asset rows and never forms its own root (D-01) | ✓ VERIFIED | `backend/itam_reporting_filters.py` `run_custom_report` queries assets then joins per-collection; tests `test_license_join_populates_column_from_assignment_and_license_docs`, `test_component_join_populates_column_via_parent_asset_id`, `test_consumable_join_populates_column_from_checkout_records` pass |
| 3 | A filter naming an operator or field outside the closed vocabulary is rejected before any database call — no client query fragment reaches the assets collection | ✓ VERIFIED | Pydantic `CustomReportDefinition`/`FilterCondition` validation; tests `test_unknown_field_outside_catalog_rejected`, `test_unknown_field_not_in_catalog_at_all_rejected`, `test_operator_outside_field_type_family_rejected`, `test_unknown_operator_string_rejected_by_literal`, `test_columns_outside_catalog_rejected` pass |
| 4 | Numeric `>`/`<` are strict; `between` (numeric and date) is inclusive on both ends; `min == max` returns exact matches, never empty | ✓ VERIFIED | Tests `test_numeric_gt_and_lt_are_strict`, `test_numeric_between_is_inclusive_both_ends`, `test_between_min_equals_max_returns_exact_matches_not_empty`, `test_date_between_inclusive_and_start_equals_end`, `test_numeric_gt_and_between_boundaries_via_full_report` pass |
| 5 | Text `equals`/`contains` are case-insensitive and treat regex metacharacters literally | ✓ VERIFIED | Tests `test_equals_produces_anchored_case_insensitive_regex`, `test_contains_value_with_regex_metacharacters_is_escaped`, `test_text_contains_case_insensitive_and_literal_metacharacters` pass |
| 6 | Zero filters runs unfiltered; zero columns is rejected | ✓ VERIFIED | Tests `test_zero_filters_returns_every_in_scope_row`, `test_zero_columns_rejected` pass; client-side `Run is disabled until at least one column is selected` (vitest) passes |
| 7 | Results paginate with a stable default sort (asset tag ascending) so identical filters return consistent page boundaries | ✓ VERIFIED | Shared `_paginate` envelope (`itam_reporting_endpoints.py:180-201`); test `test_default_sort_is_asset_tag_ascending_and_repeatable` passes |
| 8 | Saved definitions are tenant-shared (D-04), uncapped (D-05), non-unique by name; run-after-delete is a 404, not a crash or stale result | ✓ VERIFIED | Tests `test_two_saves_with_identical_name_both_succeed_with_distinct_ids`, `test_list_returns_reports_saved_by_other_users_in_same_tenant`, `test_run_after_delete_returns_404`, `test_delete_then_run_returns_404` pass |
| 9 | A custom report joining licence/component/consumable data never returns another tenant's rows, even when join keys collide | ✓ VERIFIED | `get_database()` returns `TenantIsolatedDatabase` (`backend/database.py:385-391`); Python-side joins per CONTEXT.md (no cross-collection `$lookup`); tests `test_tenant_isolation_across_colliding_join_keys`, `test_list_does_not_return_another_tenants_reports` pass |
| 10 | The field catalogue is a closed allowlist that excludes secret-bearing fields (product keys, raw customFields, tenantId, _id) — ITAM-REP-01 privacy prohibition | ✓ VERIFIED | `list_report_fields()`; tests `test_catalog_is_non_empty_and_excludes_secret_bearing_fields`, `test_list_report_fields_strips_source_but_keeps_key_label_entity_type` pass |

#### Success Criterion 2 — User can view pre-built reports for asset/license data (ITAM-REP-02)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 11 | All six D-08 pre-built reports are registered and runnable | ✓ VERIFIED | `PREBUILT_REPORTS` in `backend/itam_reporting_prebuilt.py:379-433` — `warranty_expiring`, `asset_value`, `checkout_activity`, `overdue_audits`, `license_utilization`, `low_stock_consumables`; test `test_all_six_reports_registered` passes; frontend `renders all six pre-built report titles in the pre-built section` passes |
| 12 | Pre-built reports take no user-configurable parameters beyond pagination (D-09) | ✓ VERIFIED | `list_reports` returns fixed code-defined metadata, never a DB read (`itam_reporting_endpoints.py:48-52`); run route accepts only `page`/`page_size` |
| 13 | Each report has a report-appropriate code-defined default sort | ✓ VERIFIED | Tests `test_returns_rows_sorted_desc_by_book_value`, `test_returns_events_newest_first_with_resolved_asset`, `test_sorted_ascending_by_days_overdue_with_unknown_basis_last`, `test_returns_rows_sorted_desc_by_utilization` pass |
| 14 | Report figures are NOT re-derived — book value, warranty status, seat utilisation and overdue-audit age come from the existing services (ITAM-REP-02 transparency prohibition) | ✓ VERIFIED | `itam_reporting_prebuilt.py:17,24,30` imports from `itam_finance_service`, `itam_lifecycle_endpoints`, `itam_license_endpoints._enrich_license_seats_and_expiry`; tests `test_book_value_equals_direct_compute_book_value_call`, `test_returns_exactly_the_assets_overdue_query_matches` pass |
| 15 | A consumable carries an optional `reorderThreshold`; low-stock flags at-or-below it when set, falling back to a fixed 5 when unset (D-19), with no migration | ✓ VERIFIED | `backend/itam_models.py:399` (`ConsumableCreate`), `:408` (`ConsumableUpdate`), inherited by `Consumable(ConsumableCreate)` at `:434` — all three models per plan; tests `test_flags_at_or_below_configured_threshold`, `test_no_threshold_uses_default_fallback_of_five`, `test_consumable_create_validates_with_field_absent` pass |
| 16 | A pre-built report with zero matching rows shows the same 'No matching assets' empty state as the custom preview | ✓ VERIFIED | Backend: four `test_zero_rows_returns_declared_columns` tests pass (headers survive a zero-row run). Frontend: `a run returning zero rows renders the "No matching assets" empty state` passes; copy at `components/itam/ReportsPanel.tsx:307` |
| 17 | An absent/joined-missing field renders as an em dash, never blank or `undefined` | ✓ VERIFIED | Tests `test_missing_value_renders_as_em_dash_not_none_or_blank`, `test_missing_depreciation_policy_yields_dash_and_reason`, and frontend `a null cell value renders an em dash, never blank or "undefined"` pass |

#### Success Criterion 3 — User can export reports in PDF, CSV, and Excel (ITAM-REP-03)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 18 | All three formats are registered in one shared renderer registry, used by both pre-built and custom exports (D-12, D-14, D-20) | ✓ VERIFIED | `RENDERERS = {"csv": _generate_csv, "pdf": _generate_pdf, "xlsx": _generate_excel}` (`backend/itam_reporting_service.py:154-158`); tests `test_custom_report_exports_to_pdf_through_same_route`, `test_custom_report_exports_to_xlsx_through_same_route` pass |
| 19 | The three formats never disagree — same shared row set feeds all renderers | ✓ VERIFIED | Single `build_report_rows` feeds `ItamReportingService.generate` (`itam_reporting_service.py:196-214`); test `test_csv_pdf_xlsx_report_identical_row_count` passes |
| 20 | Export includes ALL matching rows, never just the preview page | ✓ VERIFIED | Export routes call `generate(...)` which builds with `limit=None`; tests `test_csv_export_writes_full_match_set_not_just_preview_page`, `test_pdf_export_writes_real_pdf_carrying_full_match_set`, `test_xlsx_export_header_and_full_match_set`, `test_export_writes_full_match_set_not_just_preview_page` pass |
| 21 | **Cross-cutting ROADMAP constraint:** exporting a report with zero matching rows still generates a valid file with headers and no data rows — never an error | ✓ VERIFIED | Proven independently in all three formats: `test_zero_row_export_writes_header_only_file` (CSV), `test_zero_row_pdf_export_returns_200_with_real_file` (PDF), `test_zero_row_xlsx_export_has_header_only` (XLSX) — all pass |
| 22 | An export is never silently truncated — `truncated` is set and written into the file when the 10 000-row ceiling is hit (ITAM-REP-03 transparency prohibition) | ✓ VERIFIED | `MAX_REPORT_ROWS = 10000` with `truncated` propagated through every envelope (`itam_reporting_service.py:49,130-131`); the CSV renderer writes an explicit `TRUNCATED at ...` row and the route envelope carries `truncated` |
| 23 | Every exported cell passes through the existing formula-injection sanitiser in all three formats | ✓ VERIFIED | `_sanitize_cell` imported from `compliance_reporting_data` in all three renderers (`itam_reporting_service.py:29`, `itam_reporting_pdf.py:23`, `itam_reporting_excel.py:21`); tests `test_formula_trigger_cell_is_sanitized_before_rendering` (PDF), `test_formula_trigger_cell_is_written_defused` (XLSX) pass |
| 24 | PDF/Excel reuse the compliance status-colour pattern rather than a new styling system | ✓ VERIFIED | `itam_reporting_excel.py:22` imports `_xl_auto_width`, `_xl_header_row` from `compliance_reporting_excel`; `itam_reporting_pdf.py` uses the reportlab `SimpleDocTemplate`/`TableStyle` clone; test `test_status_cell_receives_fill_for_expiring` passes |
| 25 | A generated file is recorded in `itam_report_exports` with its tenant, and a cross-tenant download is refused; a traversal filename is rejected before any filesystem read | ✓ VERIFIED | `_store_report_meta` (`itam_reporting_service.py:163-186`); `Path.relative_to` guard at `itam_reporting_endpoints.py:141-146` (CR-01 fix, commit 59d41723c); tests `test_download_owning_tenant_returns_200`, `test_download_cross_tenant_returns_403`, `test_traversal_filename_rejected_with_400`, `test_pdf_export_recorded_in_exports_and_cross_tenant_403` pass |
| 26 | Requesting an unregistered format returns 400 naming the registered formats | ✓ VERIFIED | Explicit `if format not in RENDERERS` guard on both export routes (`itam_reporting_endpoints.py:106-110`, `:325-329`); tests `test_unregistered_format_returns_400`, `test_export_unregistered_format_returns_400` pass |
| 27 | Report generation is on-demand only — no scheduled/recurring delivery path introduced (D-13) | ✓ VERIFIED | No scheduler registration for reporting in `backend/app_startup.py`; `scheduled_reports_service.py` is untouched by this phase; no APScheduler/interval symbol in any `itam_reporting_*` module |

#### Success Criterion 4 — User can view the ITAM dashboard with KPIs and visualizations (ITAM-REP-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 28 | A single tenant-scoped call returns all four D-16 KPIs | ✓ VERIFIED | `GET /api/itam/kpis` → `compute_itam_kpis` (`backend/itam_kpi_endpoints.py:29-56`, `backend/itam_reporting_kpis.py`); test `test_get_kpis_returns_200_with_four_kpi_keys` passes; frontend renders all four tile titles (vitest) |
| 29 | KPI figures are inherited verbatim from the existing services — warranty alert-window boundary is inclusive and shared with the warranty report; total asset value sums existing book values | ✓ VERIFIED | `itam_reporting_kpis.py:25,33` imports from `itam_finance_service` and `itam_lifecycle_endpoints._overdue_query`; tests `test_expiring_soon_boundary_is_inclusive`, `test_total_book_value_equals_direct_compute_book_value_sum`, `test_asset_overdue_on_both_axes_is_not_double_counted` (WR-02 fix) pass |
| 30 | Each KPI carries an explicit no-data signal — never a fabricated 0 or 100% (ITAM-REP-04 transparency prohibition) | ✓ VERIFIED | Backend tests `test_every_kpi_reports_no_data_on_empty_tenant_never_a_fabricated_number`, `test_zero_total_seats_reports_no_data_not_a_percentage` pass; frontend test `a KPI payload with hasData false renders "No data yet" and never a fabricated 0% or 100%` asserts `queryByText(/0%/)` and `/100%/` are both absent |
| 31 | Charts render with recharts (no new charting dependency), and segments render in the backend-returned order, never re-sorted by count | ✓ VERIFIED | `components/itam/ItamKpiPanel.tsx:4` imports from `recharts`; `itemSorter` override comments at `:111,:153` prevent recharts' default alphabetical re-sort; backend test `test_status_breakdown_sequence_matches_enum_order_including_zero_counts` passes |
| 32 | KPI aggregates are tenant-scoped and the route is permission-gated (403 without permission / without tenant) | ✓ VERIFIED | Tests `test_seeding_a_second_tenant_does_not_change_the_first_tenants_kpis`, `test_get_kpis_returns_403_when_permission_check_fails`, `test_get_kpis_returns_403_when_no_tenant_id` pass |

#### Behavior-unverified

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| B1 | Preview table stays horizontally scrollable via `overflow-x-auto` with many columns | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Wrapper present at `components/itam/ReportsPanel.tsx:314`. Declared `verification: backstop` in 72-01-PLAN.md — a rendered-layout claim no test exercises. See Human Verification. |
| B2 | Preview cells truncate with `truncate` + `title` tooltip rather than growing row height | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `truncate max-w-xs` + `title={cellDisplay(row[c])}` present at `ReportsPanel.tsx:329-330`. Declared `verification: backstop`. See Human Verification. |
| B3 | A reversed-bounds date `between` filter returns matching rows rather than silently dropping them (WR-01 review fix) | ✓ VERIFIED (2026-08-24) | `test_between_date_swaps_reversed_bounds` added to `test_itam_reporting_builder.py`, proving `_filters_to_mongo_query` swaps a reversed date-string bound exactly like it already did for numeric bounds. 54/54 tests in the file pass. |

**Score:** 29/32 truths verified (3 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_reporting_service.py` | Shared row builder + RENDERERS registry + CSV renderer | ✓ VERIFIED | 218 lines; `build_report_rows`, `MAX_REPORT_ROWS`, `_store_report_meta`, `ItamReportingService.generate` |
| `backend/itam_reporting_prebuilt.py` | Six PREBUILT_REPORTS entries | ✓ VERIFIED | 19 KB; all six registered with columns/sort/builder; reuses finance/lifecycle/license services |
| `backend/itam_reporting_endpoints.py` | Pre-built + custom + download routes | ✓ VERIFIED | 353 lines, 11 routes; literal-before-parameterised ordering honoured |
| `backend/itam_reporting_filters.py` | Closed-vocabulary filter translator + field catalogue | ✓ VERIFIED | 24 KB; `CustomReportDefinition`, `list_report_fields`, `_filters_to_mongo_query`, `_condition_passes`, `run_custom_report` |
| `backend/itam_reporting_kpis.py` | Four-KPI aggregate | ✓ VERIFIED | 13 KB; `compute_itam_kpis` reusing finance/lifecycle services |
| `backend/itam_reporting_pdf.py` | reportlab renderer | ✓ VERIFIED | 7.4 KB; `_generate_pdf` with sanitiser + html.escape + status colours |
| `backend/itam_reporting_excel.py` | openpyxl renderer | ✓ VERIFIED | 4.7 KB; `_generate_excel` reusing `_xl_header_row`/`_xl_auto_width` |
| `backend/itam_kpi_endpoints.py` | `GET /api/itam/kpis` | ✓ VERIFIED | 2.1 KB; thin permission-gated delegate with 403/500 guards |
| `backend/itam_models.py` | `reorderThreshold` on the three consumable models | ✓ VERIFIED | Lines 399, 408, inherited at 434 |
| `backend/router_registry.py` | Both new routers registered | ✓ VERIFIED | Lines 95-96 |
| `services/apiService.ts` | 11 ITAM report/KPI client functions | ✓ VERIFIED | Lines 5765-5948; every one hits a real `/api/itam/reports*` or `/api/itam/kpis` path |
| `components/itam/ReportsPanel.tsx` | Two-section Reports tab + three export buttons | ✓ VERIFIED | 375 lines; pre-built grid, builder, saved list, PDF/Excel/CSV buttons, preview table |
| `components/itam/ReportBuilderForm.tsx` | Field + filter picker | ✓ VERIFIED | 305 lines; operator families driven by the backend catalogue |
| `components/itam/ItamKpiPanel.tsx` | Four recharts KPI tiles with drill-down | ✓ VERIFIED | 214 lines; recharts, `fetchItamKpis`, `No data yet`, clickable tiles |
| `components/itam/ITAMConsole.tsx` | Reports tab registered and mounted | ✓ VERIFIED | Tab union `:31`, TABS entry `:44`, reports branch `:128-136` |
| `components/itam/itamI18n.tsx` | `tabs.reports` in en + es | ✓ VERIFIED | Lines 25 (`Reports`), 45 (`Informes`) |
| `backend/tests/test_itam_reporting_{builder,export,kpis,prebuilt}.py` + `itam_reporting_test_support.py` | Backend coverage | ✓ VERIFIED | 106 tests, all passing |
| `src/__tests__/ITAM{ReportsPanel,KpiPanel,Console}.test.tsx` | Frontend coverage | ✓ VERIFIED | 53 tests, all passing |

No artifact is a stub, orphan, or hollow shell.

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| **`App.tsx`** | **`components/itam/ITAMConsole.tsx`** | **lazy import + `case 'itam'` render** | **✓ WIRED** | **`App.tsx:93` `lazy(() => import('./components/itam/ITAMConsole'))`; rendered at `App.tsx:1927` inside `<ErrorBoundary name="ITAMConsole">`. This is the real running console — NOT the disconnected `frontend/` tree.** |
| **`ITAMConsole.tsx`** | **`ReportsPanel` + `ItamKpiPanel`** | **direct import + `tab === 'reports'` branch** | **✓ WIRED** | **Imports at `:11-12`; both mounted at `:133-134`. `find frontend -iname '*Report*' -o -iname '*Kpi*' -o -iname 'ITAMConsole*'` returns ZERO results — no shadow copy exists, so the Phase 71 disconnected-tree defect does NOT recur here.** |
| `ItamKpiPanel` | `ReportsPanel` | `onDrillDown` → console `reportFocus` state → `focusReportKey` prop | ✓ WIRED | `ITAMConsole.tsx:133-134`, `:155`; `ReportsPanel.tsx:90-94` auto-runs then calls `onFocusHandled`. Behaviorally proven: vitest `clicking a KPI tile sets reportFocus, driving ReportsPanel to auto-run that report through its focusReportKey seam` and `clearing the drilled-into focus via ReportsPanel's onFocusHandled prevents a later tab switch from re-triggering the same run` both pass |
| `ItamKpiPanel` above `ReportsPanel` | Reports tab visual hierarchy | document order in the reports branch | ✓ WIRED | vitest `renders the KPI grid above the pre-built report sections on the Reports tab (Phase 72 Plan 07)` asserts document order and passes |
| `itam_reporting_endpoints.router` | FastAPI app | `router_registry.py:95` | ✓ WIRED | `/api/itam/reports/*` resolves in the real app |
| `itam_kpi_endpoints.router` | FastAPI app | `router_registry.py:96` | ✓ WIRED | `/api/itam/kpis` resolves in the real app |
| `ReportBuilderForm` | `GET /api/itam/reports/fields` | `fetchItamReportFields()` on mount | ✓ WIRED | `ReportBuilderForm.tsx:3,61`; operator families keyed off the returned field `type`, so the picker cannot offer a field the backend would refuse. vitest `fetches the field catalogue on mount and lists selectable columns as toggleable chips` and `a text field offers exactly equals/contains and a date field offers exactly three operators` pass |
| `ReportsPanel` export buttons | export + download routes | `generateItamReport` → `downloadItamReport` | ✓ WIRED | `ReportsPanel.tsx:168-169`; vitest `clicking an export button calls generateItamReport with the running report kind/key, then downloadItamReport` passes |
| `itam_reporting_pdf` / `itam_reporting_excel` | `RENDERERS` | module-scope import + dict registration | ✓ WIRED | `itam_reporting_service.py:151-158` — no endpoint change was needed to activate the two formats, exactly as 72-05 planned |
| `build_report_rows` custom branch | `itam_reporting_filters.run_custom_report` | lazy import dispatch | ✓ WIRED | `itam_reporting_service.py:76-92` — preview and export share one code path (D-12/D-20) |
| Export files | `db.itam_report_exports` | `_store_report_meta` upsert, read back by download route | ✓ WIRED | `itam_reporting_service.py:173-186` → `itam_reporting_endpoints.py:155-157` ownership check |
| Pre-built builders | existing ITAM services | direct imports | ✓ WIRED | `itam_reporting_prebuilt.py:17,24,30` — `itam_finance_service`, `itam_lifecycle_endpoints`, `itam_license_endpoints` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ItamKpiPanel.tsx` | `kpis` | `fetchItamKpis()` → `GET /api/itam/kpis` → `compute_itam_kpis(db, tenant_id)` → tenant-isolated collections via `itam_finance_service`/`itam_lifecycle_endpoints` | Yes | ✓ FLOWING |
| `ReportsPanel.tsx` (pre-built preview) | `result.rows` | `runItamPrebuiltReport()` → `POST /prebuilt/{key}/run` → `build_report_rows` → `run_prebuilt_report` → tenant-scoped `find()` | Yes | ✓ FLOWING |
| `ReportsPanel.tsx` (saved list) | `savedReports` | `listItamCustomReports()` → `GET /custom` → `db.itam_reports.find({})` on `TenantIsolatedDatabase` | Yes | ✓ FLOWING |
| `ReportBuilderForm.tsx` | `fields` | `fetchItamReportFields()` → `GET /fields` → `list_report_fields()` (code-defined allowlist, correctly static by design) | Yes (static by contract) | ✓ FLOWING |
| Export buttons | generated file | `generateItamReport()` → `ItamReportingService.generate` → `RENDERERS[fmt]` writing a real file to `static/reports` | Yes | ✓ FLOWING |

No hollow props, no hardcoded empty arrays reaching render, no static API returns.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 72 backend suite passes | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_{builder,export,kpis,prebuilt}.py -q` | `106 passed in 7.31s` (exit 0) | ✓ PASS |
| Phase 72 frontend suite passes | `npx vitest run src/__tests__/ITAM{ReportsPanel,KpiPanel,Console}.test.tsx` | `3 files, 53 tests passed` (exit 0) | ✓ PASS |
| Both routers registered | `grep -n "itam_reporting_endpoints\|itam_kpi_endpoints" backend/router_registry.py` | lines 95, 96 | ✓ PASS |
| Reports UI reachable from the real app | `grep -n "ITAMConsole" App.tsx` + `grep -n "ReportsPanel\|ItamKpiPanel" components/itam/ITAMConsole.tsx` | `App.tsx:93,1927`; `ITAMConsole.tsx:11,12,133,134` | ✓ PASS |
| No shadow copy in the disconnected `frontend/` tree | `find frontend -iname "*Report*" -o -iname "*Kpi*" -o -iname "ITAMConsole*"` | zero results | ✓ PASS |
| All three export formats registered | `grep -n "RENDERERS" backend/itam_reporting_service.py` | `{"csv","pdf","xlsx"}` at line 154 | ✓ PASS |

### Probe Execution

Not applicable — this phase declares no probes, and no `scripts/*/tests/probe-*.sh` path is referenced in any 72-* plan or summary. Verification evidence is the pytest/vitest runs above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ITAM-REP-01 | 72-03, 72-06 | Custom Report Builder | ✓ SATISFIED | Truths 1-10; `itam_reporting_filters.py` + `ReportBuilderForm.tsx`; 52 builder tests pass |
| ITAM-REP-02 | 72-01, 72-02, 72-06 | Pre-built Reports for asset/license data | ✓ SATISFIED | Truths 11-17; six reports registered and rendered; 19 prebuilt tests pass |
| ITAM-REP-03 | 72-01, 72-05, 72-06 | Export support (PDF, CSV, Excel) | ✓ SATISFIED | Truths 18-27; all three renderers registered and exercised; 19 export tests pass |
| ITAM-REP-04 | 72-04, 72-07 | ITAM Dashboard with KPIs/Visualizations | ✓ SATISFIED | Truths 28-32; recharts tile grid mounted above the report sections; 16 KPI tests + 9 panel tests pass |

No orphaned requirements — `.planning/REQUIREMENTS.md` maps exactly ITAM-REP-01..04 to Phase 72 and all four are claimed by a plan. The "Complete" status recorded at REQUIREMENTS.md:63-66 is consistent with the codebase evidence above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | `TBD`/`FIXME`/`XXX` debt markers | — | **None found.** Grep across all 11 phase-modified backend/frontend source files returns zero matches. |
| — | — | `TODO`/`HACK`/`PLACEHOLDER` | — | **None found.** |
| `ReportBuilderForm.tsx` | 168, 260, 269 | `placeholder=` | ℹ️ Info | Legitimate HTML input `placeholder` attributes ("Untitled custom report", "Value", "Second value"), not stub markers. |
| `72-VALIDATION.md` | frontmatter | `status: draft`, `nyquist_compliant: false`, `wave_0_complete: false` | ⚠️ Warning | Planning doc-debt, not a code defect — the validation strategy was never marked validated after execution. Sibling to the missing-VERIFICATION.md gap this report backfills. Does not affect goal achievement. |

### Post-Phase Deviation Note (not a gap)

72-01-PLAN.md and 72-04-PLAN.md state every reporting/KPI route uses `_require_itam_admin` (D-07). The **current** code uses a split gate: read routes (`GET ""`, `GET /fields`, `GET /custom`, `GET /custom/{id}`, `GET /download/{filename}`, `GET /api/itam/kpis`) use `_require_itam_viewer`; every mutating and report-running route still uses `_require_itam_admin`.

This is an **intentional post-phase fix**, commit `f100168c6` *"fix(itam): split read vs write RBAC so view-only roles aren't 403'd"*, which closed a real defect: `itam_user`/`itam_viewer` roles carry `view:itam` (what gates the ITAM nav item) but not `manage:assets`, so they could see the ITAM console and then be 403'd on nearly everything inside it. `_require_itam_viewer` still hard-403s a caller holding neither permission (`backend/itam_asset_endpoints.py:68-93`), and `test_every_custom_route_returns_403_without_permission` / `test_get_kpis_returns_403_when_permission_check_fails` both pass.

The must-have's **intent** (every reporting route is permission-gated; an unauthorized caller gets 403) holds. Only the literal "same `_require_itam_admin` dependency" wording is now inaccurate, and it is inaccurate because of a later correctness fix, not a Phase 72 defect. Recorded as VERIFIED with this note rather than as a gap. If a stricter literal reading is preferred, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "Every reporting route rejects a caller without the ITAM admin permission with HTTP 403, using the same _require_itam_admin dependency"
    reason: "Post-phase fix f100168c6 split read vs write RBAC so view:itam roles aren't 403'd inside a console they can see. Read routes use _require_itam_viewer (still 403s without view:itam OR manage:assets); all write/run routes keep _require_itam_admin."
    accepted_by: "{your name}"
    accepted_at: "{ISO timestamp}"
```

### Human Verification Required

Four items. The first three are carried forward verbatim from `72-UAT.md` (which was left with all three `pending`); the fourth comes from `72-REVIEW-FIX.md`'s own WR-01 note.

#### 1. Tenant brand-colour accent rendering

**Test:** Open the ITAM console Reports tab on a tenant with a configured brand colour.
**Expected:** The tab's accent underline and the KPI panel's chart primary-series colour match the tenant's brand colour, consistent with every other ITAMConsole tab.
**Why human:** Theme-colour propagation into recharts series is a rendered-appearance property no unit test can assert.

#### 2. Preview table horizontal scroll + cell truncation tooltip

**Test:** In the custom builder, select many columns (10+) and run a report containing a very long cell value; hover the long cell.
**Expected:** The table scrolls horizontally inside its card rather than overflowing the layout; long cells truncate with a `title` tooltip rather than growing row height.
**Why human:** Covers both `verification: backstop` must-haves from 72-01-PLAN.md (behavior_unverified B1 and B2). The classes are present (`ReportsPanel.tsx:314`, `:329-330`) but rendered-layout behaviour is unexercised.

#### 3. KPI empty-state visual presentation

**Test:** View the KPI tiles on a tenant with no ITAM data, then on a tenant with data.
**Expected:** Empty tiles read as "No data yet" with entity-specific next-step copy — never a 0% or 100% presented as a measurement.
**Why human:** The contract is unit-tested at both ends, but the against-real-data visual read is human.

#### 4. ~~Reversed-date-range custom report (WR-01 regression)~~ — CLOSED 2026-08-24

**Was:** no reversed-bounds test existed among the 106 backend tests, despite 72-REVIEW-FIX.md requesting human confirmation for this exact fix.
**Now:** `test_between_date_swaps_reversed_bounds` added to `backend/tests/test_itam_reporting_builder.py`, calling `_filters_to_mongo_query` directly with `value`/`value2` reversed and asserting the emitted Mongo query has the bounds swapped back to `$gte: earlier, $lte: later` — the same assertion shape as the pre-existing numeric-bounds test. 54/54 tests in the file pass (52 pre-existing + 2 new, the other covering the non-reversed date case for symmetry). This closes the code-level regression risk; it does not replace a live click-through of the actual Reports tab, which nobody had done before either.

### Gaps Summary

**No gaps.** All four ROADMAP success criteria are achieved in the codebase, with 106 backend and 53 frontend tests passing when run during this verification (not taken from summaries).

The single highest-risk item going in — whether Phase 72's frontend repeated Phase 71's disconnected-`frontend/`-tree defect — is **cleanly negative**. The Reports tab and KPI grid are reachable through the real app: `App.tsx:93` lazily imports `./components/itam/ITAMConsole`, renders it at `App.tsx:1927`, and that console imports `ReportsPanel`/`ItamKpiPanel` from the same live tree at `:11-12`, mounting both in the `tab === 'reports'` branch at `:133-134`. A `find` across `frontend/` for any Report/Kpi/ITAMConsole file returns nothing, so no shadow copy exists to diverge from. The drill-down seam between the two panels is behaviorally proven by three passing `ITAMConsole.test.tsx` cases, not merely present.

The cross-cutting ROADMAP constraint (zero-row export still yields a valid headers-only file, never an error) is independently proven in all three formats by three separate passing tests.

**Update 2026-08-24:** item 4 above (WR-01 regression test) closed same day. What remains is now purely three rendered-appearance/visual items already logged as pending in `72-UAT.md` — genuinely requires eyes on a running browser, not further backend work. Status stays `human_needed` rather than `passed` solely because those three visual items exist — no truth failed, no artifact is a stub, no key link is broken.

`72-VALIDATION.md` is still `status: draft` / `nyquist_compliant: false` — the Nyquist validation gate (`/gsd-validate-phase`) was never run for this phase. Left open: it's a distinct QA workflow from this goal-backward verification and wasn't in scope for this pass. `72-UAT.md`'s citation of `72-VERIFICATION.md` as its source is now accurate — that file exists as of this session.

---

_Verified: 2026-08-24T13:45:00Z_
_Verifier: Claude (gsd-verifier)_
_Addendum (WR-01 test closure): 2026-08-24, Claude (session lead)_
