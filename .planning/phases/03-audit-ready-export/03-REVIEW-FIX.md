---
phase: "03"
fixed_at: 2026-07-02T18:35:58Z
review_path: .planning/phases/03-audit-ready-export/03-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 1
skipped: 5
status: partial
---

# Phase 03: Code Review Fix Report — Audit-Ready Export

**Fixed at:** 2026-07-02T18:35:58Z
**Source review:** .planning/phases/03-audit-ready-export/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (3 critical, 3 warning — the 2 Info findings are out of scope for this pass)
- Fixed: 1
- Skipped: 5 (all 5 were already resolved by later, unrelated work — see reasons below)

This review is dated 2026-06-18, one of the earliest in the project. Re-verification against
current source showed the codebase has moved on significantly: 5 of the 6 in-scope findings
were already fixed by subsequent, unrelated commits (a service dispatcher method, a report
metadata write path, and a project-wide tenant-isolation database wrapper). Only WR-01 still
reproduced against current code and required a fix in this pass.

## Fixed Issues

### WR-01: `_flatten_evidence` `count` field is inconsistent with `auto_count + manual_count`

**Files modified:** `backend/compliance_reporting_data.py`
**Commit:** b9573de
**Applied fix:** Moved the `auto_count`/`manual_count` increment outside the `if name:` block in
`_flatten_evidence`, so every deduplicated evidence record (including those with only a URL or
description and no name) is counted toward `auto_count` or `manual_count`. `count` (`len(seen_ids)`)
now always equals `auto_count + manual_count`, matching the fix's first option from REVIEW.md.
Verified against the current file (same logic as reviewed, line numbers shifted slightly) and
against `tests/test_audit_export.py::test_evidence_source_labelling`, which still asserts
`auto_count == 1`, `manual_count == 1`, `count == 2` for two named records — unaffected by the
change since both test records have names. Ran the full `tests/test_audit_export.py` suite
(6 tests) after the fix: all pass.

## Skipped Issues

### CR-01: `generate_all_frameworks_report` does not exist on `ComplianceReportingService`

**File:** `backend/compliance_reporting_service.py`
**Reason:** Already fixed by later work. `ComplianceReportingService.generate_all_frameworks_report(self, tenant_id, format)` now exists (dispatches to `_generate_all_excel` or `_generate_all_csv` based on `format`, then persists report metadata via `_store_report_meta`). The endpoint at `backend/compliance_reports_endpoints.py:81` calls it successfully; no `AttributeError` / 500 reproduces against current code.
**Original issue:** The method was missing, causing every `/api/compliance/reports/generate/all` call to hard-500.

### CR-02: None-tenant bypass in download ownership check

**File:** `backend/compliance_reports_endpoints.py:100-108`
**Reason:** Already fixed by later work. The current ownership check includes an explicit guard — `if not caller_tenant: raise HTTPException(403, "Tenant context required")` — before the DB lookup, so a caller with no tenant context can no longer pass by `None == None` matching an untagged report's `tenantId`.
**Original issue:** `caller_tenant is None` combined with a report stored without `tenantId` allowed the ownership check to pass via `None == None`.

### CR-03: Report metadata is never written to `compliance_reports` collection

**File:** `backend/compliance_reporting_service.py`
**Reason:** Already fixed by later work. A `_store_report_meta(filename, tenant_id)` helper now upserts into `db.compliance_reports` after every report generation, and it is called from all six service methods (`generate_report`, `generate_excel_report`, `generate_pdf_report`, `generate_all_csv_report`, `generate_all_excel_report`, `generate_all_frameworks_report`). The download route's `db.compliance_reports.find_one({"filename": filename})` lookup is now populated, so the ownership check is no longer permanently self-defeating. A `list_compliance_reports` endpoint that reads from the same collection was also added, consistent with this metadata now being reliably written.
**Original issue:** No writer populated `compliance_reports`, so the ownership check always 403'd, including for the legitimate owner.

### WR-02: Unquoted filename in `Content-Disposition` header

**File:** `backend/compliance_reports_endpoints.py:119`
**Reason:** Already fixed by later work. The manual `headers={"Content-Disposition": ...}` override cited in the review no longer exists. The download route now returns `FileResponse(file_path, media_type=media_type, filename=filename)`, relying entirely on FastAPI/Starlette's built-in `Content-Disposition` generation (which quotes/encodes the filename correctly), exactly as REVIEW.md's suggested fix recommended.
**Original issue:** An unquoted, manually-constructed `Content-Disposition` header allowed header injection via an unescaped filename.

### WR-03: `_build_report_data` accepts `tenant_id` but never uses it as a DB filter

**File:** `backend/compliance_reporting_data.py:96`
**Reason:** Already fixed by later, unrelated work — a project-wide tenant-isolation mechanism superseded the need for this function to filter manually. `get_database()` (`backend/database.py`) now returns a `TenantIsolatedDatabase`, whose `TenantIsolatedCollection` wrapper auto-injects a `tenantId` filter (sourced from a per-request `ContextVar` set in `authentication_service.py` from the authenticated caller's tenant, via `Depends(get_current_user)` on every route in `compliance_reports_endpoints.py`) into every `find`/`find_one` call on `asset_compliance`, `compliance_artifacts`, and `assets` — the exact three collections named in this finding. `compliance_frameworks` is explicitly exempted as global reference data (consistent with the review's own caveat: "if multi-tenancy is enforced at the collection level this is benign"). Confirmed via grep that these three collections are NOT in the `TenantIsolatedDatabase` exemption list, and that `set_tenant_id` is called from `authentication_service.py` on every authenticated request. The explicit `tenant_id` parameter passed into `_build_report_data` is now dead code (unused), but poses no data-isolation risk since isolation is enforced one layer down at the database-access layer. Applying the review's literal suggested patch (adding `**({"tenantId": tenant_id} if tenant_id else {})` to each query) would be redundant — `TenantIsolatedCollection._inject_tenant_id` overwrites any `tenantId` key in the filter with the context-derived value regardless.
**Original issue:** `tenant_id` was accepted but silently ignored, flagged as a possible cross-tenant data leak depending on schema.

---

_Fixed: 2026-07-02T18:35:58Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
