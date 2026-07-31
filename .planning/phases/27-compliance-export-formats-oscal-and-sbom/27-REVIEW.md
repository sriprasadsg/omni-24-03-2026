---
phase: 27-compliance-export-formats-oscal-and-sbom
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backend/oscal_endpoints.py
  - backend/container_scanner_endpoints.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-07-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 27 adds read-only OSCAL 1.1.2 assessment-results export and a CycloneDX 1.6 SBOM export for container scans. Both are export-only, no injection surface (JSON built via stdlib, no template/eval). OSCAL is correctly tenant-scoped via `_build_report_data(framework_id, tenant_id)` with a 403 on missing tenant. Two Warnings concern the SBOM route's raw-DB access that bypasses the tenant-isolation wrapper and fails open when tenant context is absent.

## Warnings

### WR-01: SBOM route bypasses tenant-isolation wrapper and fails open on null tenant

**File:** `backend/container_scanner_endpoints.py:62-68`
**Issue:** `container_result_sbom` queries `db._db.container_scan_results` — the raw, un-wrapped Motor collection — instead of the `TenantIsolatedDatabase` handle, relying solely on the explicit `{"scan_id": scan_id, "tenantId": tenant_id}` filter. If `get_tenant_id()` returns `None` (an authenticated principal carrying `view:dashboard` but no tenant context), the filter becomes `{"tenantId": None}`, which matches any legacy/untenanted scan document rather than matching nothing — a cross-boundary read. The tenant-isolation wrapper exists precisely to prevent this class of raw-filter mistake.
**Fix:** Fail closed on missing tenant before querying: `if not tenant_id: raise HTTPException(403, "Tenant context required")`, and prefer the wrapped `db.container_scan_results` handle over `db._db` unless there is a documented reason to bypass it.

### WR-02: `view:dashboard` is an over-broad gate for evidence export

**File:** `backend/container_scanner_endpoints.py:62`
**Issue:** SBOM export (an audit-evidence artifact potentially fed to the trust center) is gated only by `view:dashboard`, the broadest read permission. Any dashboard viewer can export the full component/vulnerability inventory of any scan in their tenant.
**Fix:** Confirm this matches the intended data-sensitivity policy; if SBOMs are treated as export/evidence artifacts elsewhere, gate on the same `view:compliance`/export permission used by the other report exporters.

## Info

### IN-01: OSCAL status default silently downgrades unknown states to "partial"

**File:** `backend/oscal_endpoints.py:54-56`
**Issue:** `status = row.get("Control Status", "Warning")` and `_IMPL_STATUS.get(status, "partial")` mean any unmapped or malformed control status is exported as `partial`/implemented-ish rather than surfaced. For a compliance-evidence export consumed by auditors, silently coercing unknown states can misrepresent posture.
**Fix:** Map unknown statuses to `planned` (conservative) or add the status verbatim to `remarks` so the ambiguity is visible in the export.

### IN-02: Unbounded control_rows in a single export

**File:** `backend/oscal_endpoints.py:83, 49-72`
**Issue:** `_build_findings` iterates all control rows with no cap; a framework with a very large control set builds the entire OSCAL document in memory. Not a v1-scope perf finding, noted for maintainability.
**Fix:** None required now; consider streaming/pagination if framework sizes grow.

---

_Reviewed: 2026-07-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
