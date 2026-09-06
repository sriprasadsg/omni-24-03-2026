---
phase: 70-core-data-audit-customization
fixed_at: 2026-08-12T21:15:00Z
review_path: .planning/milestones/v4.1-phases/65-core-data-audit-customization/65-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 70: Code Review Fix Report

**Fixed at:** 2026-08-12T21:15:00Z
**Source review:** .planning/milestones/v4.1-phases/65-core-data-audit-customization/65-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (WR-01 through WR-06; IN-01/IN-02 excluded by fix_scope=critical_warning)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### WR-01: Tenant-less admin's ITAM settings save is silently unrecoverable

**Files modified:** `backend/itam_customization_endpoints.py`
**Commit:** 00b04682
**Applied fix:** `save_itam_settings` now raises `HTTPException(400, ...)` when
`tenant_id` is falsy, before the upsert, instead of persisting a
`tenantId: null` document that neither the tenant-scoped nor
global-fallback read query could ever retrieve.

### WR-02: CSV import's per-row insert has no `DuplicateKeyError` handling

**Files modified:** `backend/itam_data_endpoints.py`
**Commit:** ccbcee6b
**Applied fix:** Wrapped `db.assets.insert_one(document)` in the import loop
with `try/except DuplicateKeyError` (imported from `pymongo.errors`,
matching `itam_asset_endpoints.create_manual_asset`'s pattern), converting a
race-lost insert into a per-row skip with an error message rather than an
unhandled 500 that discarded the whole request's response.

### WR-03: `itam_audit_service.log_itam_action`'s tenant fallback can mislabel/misplace audit entries

**Files modified:** `backend/itam_audit_service.py`
**Commit:** 23a83b79
**Applied fix:** Changed the fallback tenant id from the fabricated literal
`"default-tenant"` (used as a real seeded tenant id by several test
fixtures) to `"platform-admin"`, the ambient tenant-context sentinel already
used consistently by `authentication_service.py` and `database.py` for
tenant-less admins.

### WR-04: CSV export silently truncates at 10,000 rows with no truncation signal

**Files modified:** `backend/itam_data_endpoints.py`, `backend/app_middleware.py`, `services/apiService.ts`, `components/itam/BulkImportExportPanel.tsx`
**Commit:** 7215f899
**Applied fix:** `export_assets` now sets an `X-Export-Truncated: true`
response header when the result hits `MAX_EXPORT_ROWS`; the header was added
to the CORS `expose_headers` allowlist in `app_middleware.py` so browser JS
can read it. `exportItamAssetsCsv` now returns `{ truncated: boolean }`
(callers that ignore the resolved value, including the existing test
mocks resolving `undefined`, remain safe via optional chaining), and
`BulkImportExportPanel.handleExport` shows a warning toast instead of the
plain success toast when the export was truncated.

### WR-05: Frontend activity-log filter vocabulary has drifted from the backend's

**Files modified:** `components/itam/ActivityLogPanel.tsx`
**Commit:** 3abc68c3
**Applied fix:** Added `'itam_export'` to the local `ITAM_RESOURCE_TYPES`
mirror array so the Activity tab's filter dropdown includes CSV-export
events, matching the backend's `itam_audit_service.ITAM_RESOURCE_TYPES`
frozenset (source of truth).

### WR-06: `GET /api/audit-logs`'s "super-admin sees all tenants" path is unreachable through this route

**Files modified:** `backend/audit_endpoints.py`
**Commit:** 7732bf70
**Applied fix:** `get_audit_logs` now computes
`effective_tenant_id = None if tenant_id == "platform-admin" else tenant_id`
before calling `AuditService.get_logs`, so the ambient tenant sentinel for
tenant-less super-admins is no longer forwarded as a literal `tenantId`
filter — a real super-admin now reaches the `is_super_admin` all-tenants
branch as originally designed.

**Note:** This fix changes the effective query behavior for super-admin
requests (previously an always-empty result set for tenant-less
super-admins, now an unfiltered cross-tenant read). All existing
`test_itam_audit.py` tests pass unchanged (none exercise the
`tenant_id == "platform-admin"` case), but this is a behavioral/logic
change rather than a pure syntax fix — **flagged for human verification**
that unfiltered cross-tenant audit-log access for super-admins is the
intended outcome before this phase proceeds to verification.

## Skipped Issues

None — all 6 in-scope findings were fixed.

---

_Fixed: 2026-08-12T21:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
