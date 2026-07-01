---
phase: "03"
status: findings
depth: standard
reviewed_at: 2026-06-18
files_reviewed: 6
files_reviewed_list:
  - backend/compliance_reporting_data.py
  - backend/compliance_reports_endpoints.py
  - backend/compliance_reporting_service.py
  - backend/compliance_reporting_pdf.py
  - backend/compliance_reporting_excel.py
  - backend/tests/test_audit_export.py
findings:
  critical: 3
  warning: 3
  info: 2
  total: 8
---

# Phase 03: Code Review Report — Audit-Ready Export

**Reviewed:** 2026-06-18
**Depth:** standard
**Files Reviewed:** 6
**Status:** findings

## Summary

Six files from the Phase 3 Audit-Ready Export implementation were reviewed. The tenant_id thread is correctly propagated through endpoint -> service -> all three renderer functions (CSV, Excel, PDF). The path traversal guard in the download route is structurally sound. STATUS_LEGEND is confined to the data module and is not imported by any renderer, so it cannot corrupt data-layer values.

Three critical issues were found: a missing service method that causes a 500 on every "generate all" request, a None-tenant bypass in the download ownership check, and a report-metadata write gap that makes the ownership check permanently useless. Three warnings cover a count/auto+manual mismatch in flattened evidence, an unquoted Content-Disposition filename, and a missing tenant filter in the data layer. Two info items cover a dead export and a test reliability flaw.

---

## Critical Issues

### CR-01: `generate_all_frameworks_report` does not exist on `ComplianceReportingService` — hard 500 on every call

**File:** `backend/compliance_reports_endpoints.py:80`

**Issue:** The `/api/compliance/reports/generate/all` endpoint calls `compliance_reporting_service.generate_all_frameworks_report(tenant_id, format)`. That method does not exist on `ComplianceReportingService`. The class defines `generate_all_csv_report` and `generate_all_excel_report` but no unified dispatcher. Every call to this route raises `AttributeError` inside the `try/except Exception`, which is caught and re-raised as HTTP 500. The feature is completely broken at runtime.

**Fix:**
```python
# In ComplianceReportingService (compliance_reporting_service.py), add:
async def generate_all_frameworks_report(self, tenant_id: str, format: str) -> dict:
    if format == "excel":
        return await _generate_all_excel(self.reports_dir, tenant_id=tenant_id)
    return await _generate_all_csv(self.reports_dir, tenant_id)
```

---

### CR-02: None-tenant bypass in download ownership check

**File:** `backend/compliance_reports_endpoints.py:101-106`

**Issue:** The ownership check is:
```python
caller_tenant = getattr(current_user, "tenant_id", None)
...
if not report_meta or report_meta.get("tenantId") != caller_tenant:
    raise HTTPException(status_code=403, ...)
```

When `caller_tenant` is `None` (unauthenticated or token missing `tenant_id`) and the stored `tenantId` is also `None` or absent, `None == None` evaluates to `True` and the check passes, granting access. A caller with no tenant context can download any report that was stored without a `tenantId`. This contradicts the check's intent.

**Fix:**
```python
caller_tenant = getattr(current_user, "tenant_id", None)
if caller_role not in _SUPER_ADMIN_ROLES:
    if not caller_tenant:                                    # <-- add this guard
        raise HTTPException(status_code=403, detail="Not authorized to access this report")
    db = get_database()
    report_meta = await db.compliance_reports.find_one({"filename": filename})
    if not report_meta or report_meta.get("tenantId") != caller_tenant:
        raise HTTPException(status_code=403, detail="Not authorized to access this report")
```

---

### CR-03: Report metadata is never written to `compliance_reports` collection — ownership check is always a 403

**File:** `backend/compliance_reporting_service.py:127-140` / `backend/compliance_reports_endpoints.py:105`

**Issue:** The download route's ownership check queries `db.compliance_reports.find_one({"filename": filename})`. No code in this phase (or visible elsewhere in the new service/data/renderer files) inserts a record into `compliance_reports` after generating a file. The only writer found in the codebase is in `backend/compliance_report_endpoints.py` (the older endpoint module), which the new routes do not call.

Result: `report_meta` is always `None` for any file generated through the new endpoints, so `not report_meta` is always `True`, and every non-super-admin download returns HTTP 403 — including the owner. The security mechanism is permanently self-defeating until writes are added.

**Fix:** Each `_generate_*` function must insert a metadata record after saving the file:
```python
# At the end of _generate_csv / _generate_excel / _generate_pdf, before returning:
from database import get_database
db = get_database()
await db.compliance_reports.insert_one({
    "filename": filename,
    "tenantId": tenant_id,
    "generatedAt": datetime.now().isoformat(),
    "frameworkId": framework_id,
    "format": "csv",   # or "xlsx" / "pdf"
})
```
Alternatively, the service wrapper methods can perform the insert after the generator returns.

---

## Warnings

### WR-01: `_flatten_evidence` `count` field is inconsistent with `auto_count + manual_count`

**File:** `backend/compliance_reporting_data.py:60-92`

**Issue:** `count` is `len(seen_ids)`, which counts every deduplicated evidence record. `auto_count` and `manual_count` are incremented only when `name` (or `filename`) is non-empty. If an evidence record has a URL or description but no name, it enters `seen_ids` but contributes to neither `auto_count` nor `manual_count`. The exported "Evidence Count" column will exceed `Auto Evidence + Manual Evidence` for such records, which is misleading to auditors and inconsistent with what the [Auto]/[Manual] prefixed names list shows.

**Fix:** Either count all records (not only named ones):
```python
# Move auto/manual increment outside the `if name:` block
if is_auto:
    auto_count += 1
else:
    manual_count += 1
if name:
    names.append(f"{label} {name}")
```
Or redefine `count` as `auto_count + manual_count` so the three fields are always consistent.

---

### WR-02: Unquoted filename in `Content-Disposition` header allows header injection

**File:** `backend/compliance_reports_endpoints.py:122`

**Issue:**
```python
headers={"Content-Disposition": f"attachment; filename={filename}"},
```
The filename is not quoted. Per RFC 6266, filenames containing spaces, non-ASCII characters, or semicolons must be quoted. A `filename` value containing a semicolon (e.g., if `framework_id` were user-controlled and contained one) would inject additional header parameters. FastAPI's `FileResponse` already sets a correct `Content-Disposition` via its own `filename=` argument on line 121; the manual `headers=` override is redundant and incorrectly formatted.

**Fix:** Remove the manual `headers` override entirely and rely on FastAPI's built-in handling:
```python
return FileResponse(
    file_path,
    media_type=media_type,
    filename=filename,
    # Remove: headers={"Content-Disposition": f"attachment; filename={filename}"},
)
```
If a custom header is required, quote the filename: `f'attachment; filename="{filename}"'`.

---

### WR-03: `_build_report_data` accepts `tenant_id` but never uses it as a DB filter

**File:** `backend/compliance_reporting_data.py:96-207`

**Issue:** `tenant_id` is an accepted parameter but is never used in any MongoDB query within `_build_report_data`. All four collections (`compliance_frameworks`, `asset_compliance`, `compliance_artifacts`, `assets`) are queried without any tenant predicate. This means a tenant can generate a report containing data from all other tenants if those collections store cross-tenant data without a tenant discriminator field.

Whether this is a true data-isolation bug depends on the DB schema (single-tenant DB vs. multi-tenant shared collections), but the parameter being silently ignored is a correctness red flag. If multi-tenancy is enforced at the collection level this is benign; if records contain a `tenantId` field this is a data-leak.

**Fix:** Audit whether `compliance_frameworks`, `asset_compliance`, and `compliance_artifacts` have a `tenantId` field. If so, add:
```python
ac_docs = await db.asset_compliance.find(
    {"controlId": {"$in": control_ids}, **({"tenantId": tenant_id} if tenant_id else {})}
).to_list(length=10000)
```

---

## Info

### IN-01: `STATUS_LEGEND` is defined but never imported — dead export

**File:** `backend/compliance_reporting_data.py:9-18`

**Issue:** `STATUS_LEGEND` is defined at module level in `compliance_reporting_data.py` and is not imported by any other module in the reviewed set or found via a codebase-wide search. It is a dead export. Neither the PDF renderer nor the Excel renderer uses it for display (they have their own `_PDF_STATUS_COLORS` and `_STATUS_FILLS` dicts). This answers the scoping question positively: STATUS_LEGEND does not touch data-layer values.

**Fix:** If it is intended for future renderer use, document it. If it is vestigial, remove it to avoid confusion with the live status mappings.

---

### IN-02: `test_legacy_download_allows_owner` does not actually exercise the authorization path

**File:** `backend/tests/test_audit_export.py:108-130`

**Issue:** The test patches `os.path.exists` to return `False`. In the endpoint, `os.path.exists(file_path)` is checked at line 97 and raises HTTP 404 before the tenant ownership check at line 103 is ever reached. The assertion `response.status_code != 403` passes because 404 satisfies it — but the tenant authorization code path for the same-tenant owner is never exercised. The test gives false coverage confidence.

**Fix:** Patch `os.path.exists` to return `True` (consistent with the cross-tenant test) so the request reaches the DB lookup. Also mock `os.path.abspath` or use a filename that won't fail the path traversal check, then assert `response.status_code == 200` (not merely `!= 403`):
```python
with patch.object(compliance_reports_endpoints, "get_database", return_value=mock_db, create=True), \
     patch("os.path.exists", return_value=True), \
     patch("os.path.isfile", return_value=True):
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")

assert response.status_code == 200, (
    f"Owner should receive 200, got {response.status_code}"
)
```

---

_Reviewed: 2026-06-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
