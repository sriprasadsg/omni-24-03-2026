# Phase 03 — UI Review

**Audited:** 2026-07-05
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured — no frontend surface exists for this phase to screenshot

---

## Scope Finding: This Phase Has No Frontend Surface

Phase 03 (`audit-ready-export`) is a backend-only data-layer and export-generator change. Both plans (03-01, 03-02) modified exclusively:

- `backend/compliance_reporting_data.py`
- `backend/compliance_reports_endpoints.py`
- `backend/compliance_reporting_service.py`
- `backend/compliance_reporting_pdf.py`
- `backend/compliance_reporting_excel.py`
- `backend/tests/test_audit_export.py`

No `.tsx`/`.jsx`/`.css`/`.scss` file was created or modified by either plan (confirmed via SUMMARY.md `files_modified` lists and a repo-wide grep for the new fields — `Auto Evidence`, `Manual Evidence`, `Tenant:` — inside `src/`, which returned zero matches). There is no React component, route, button label, or visual state introduced by this phase. The "UI" produced by this phase is exclusively the visual layout of generated PDF/XLSX files (reportlab paragraphs, openpyxl cell rows), which is out of scope for a Tailwind/React 6-pillar audit and is not screenshot-able via a dev-server browser session.

Applying the 6-pillar rubric (Copywriting, Visuals, Color, Typography, Spacing, Experience Design) to this phase would produce fabricated scores against code that does not exist in the audited layer. Rather than force scores, this review documents the scope mismatch and gives a narrower, honest assessment of the artifact that does exist: the generated document layout.

---

## Pillar Scores (N/A — no frontend code in scope)

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | N/A | No React/JSX strings introduced; document copy ("Tenant:", "Export Date:", "Auto Evidence", "Manual Evidence") lives in PDF/XLSX generator Python code, not UI components |
| 2. Visuals | N/A | No component tree, no visual hierarchy elements in scope |
| 3. Color | N/A | No Tailwind/CSS classes touched |
| 4. Typography | N/A | No `text-*`/`font-*` classes touched |
| 5. Spacing | N/A | No `p-*`/`m-*`/`gap-*` classes touched |
| 6. Experience Design | 2/4 | See finding below — download-route error handling was extended, but no loading/empty/disabled states exist because there is no frontend trigger for this feature |

**Overall: N/A/24 — this phase is out of the frontend audit's jurisdiction**

---

## Detailed Findings

### Experience Design (2/4) — the one pillar with real evaluable surface

**BLOCKER-adjacent gap:** `backend/compliance_reports_endpoints.py` now raises HTTP 403 for cross-tenant download attempts (03-01 Task 2), but grep across `src/` found no component that calls the legacy `/api/compliance/reports/download/{filename}` route and handles a 403 response. If any existing frontend code does call this endpoint, a 403 will surface as an unhandled fetch rejection or a raw error toast rather than a scoped "You don't have access to this report" message — there is no evidence of dedicated error-state copy for this new failure mode.

**WARNING:** The new `Auto Evidence`/`Manual Evidence` columns and `Tenant:`/`Export Date:` header lines added to the PDF/XLSX outputs (03-02) are consumed only by opening the downloaded file — no frontend preview, indicator, or column legend exists in `src/` to tell a user before download that the export now contains source-labelled evidence counts. This is a silent contract change from the user's perspective: existing downloaded reports get new columns with no announcement in the UI (e.g., no "New: evidence source breakdown" badge on the export button).

**Not evaluable:** loading/skeleton states, empty states, and disabled states for the report-generation trigger itself are outside this phase's diff — whatever exists there predates this phase and was not touched.

---

## Recommendation

Do not force a 6-pillar score on this phase. Recommend the orchestrator either:
1. Skip UI review for backend-only phases in future roadmap sequencing (flag phase type as `backend` vs `frontend` at plan time), or
2. If a frontend consumer of this export feature is added in a later phase (e.g., a "Download Audit Report" button that surfaces the new Tenant/Export Date/Auto-Manual columns), route the UI review to that later phase instead of this one.

## Top Priority Fixes (scoped to the one real gap found)

1. **No frontend 403 handling for the new tenant-ownership check** — a cross-tenant download attempt will now fail with a raw 403 instead of a clear message — locate the frontend caller of `/api/compliance/reports/download/{filename}` (if any) and add a scoped error state ("You don't have access to this report") rather than letting the raw HTTP error surface.
2. **No UI announcement of new export columns** — users downloading PDF/XLSX reports get new Auto/Manual Evidence columns and Tenant/Export Date header lines with zero indication in the app that the export format changed — consider a changelog note or tooltip on the export/download button.
3. **Verify no other legacy download call sites break** — since 03-01 added a hard tenant check to a previously open route, audit all frontend call sites of the legacy download endpoint (if any exist) to confirm they always pass a same-tenant JWT; if any admin/reporting tool calls this route cross-tenant intentionally, it will now break with 403.

---

## Files Audited

- `.planning/phases/03-audit-ready-export/03-01-SUMMARY.md`
- `.planning/phases/03-audit-ready-export/03-02-SUMMARY.md`
- `.planning/phases/03-audit-ready-export/03-01-PLAN.md`
- `.planning/phases/03-audit-ready-export/03-02-PLAN.md`
- `backend/compliance_reporting_data.py` (referenced, not directly re-read)
- `backend/compliance_reporting_pdf.py` (referenced, not directly re-read)
- `backend/compliance_reporting_excel.py` (referenced, not directly re-read)
- `backend/compliance_reports_endpoints.py` (referenced, not directly re-read)
- Repo-wide grep of `src/` for new field names (`Auto Evidence`, `Manual Evidence`, `Tenant:`) — zero matches
- Repo-wide grep of `src/` for export/download route consumers — zero matches
