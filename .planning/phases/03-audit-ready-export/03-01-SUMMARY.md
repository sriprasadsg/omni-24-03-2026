---
phase: 03-audit-ready-export
plan: 01
subsystem: compliance-reporting
tags: [audit, evidence-labelling, tenant-isolation, tdd]
dependency_graph:
  requires: []
  provides:
    - compliance_reporting_data._flatten_evidence with auto_count/manual_count
    - compliance_reporting_data._build_report_data with tenant_id param
    - compliance_reporting_data.STATUS_LEGEND constant
    - compliance_reports_endpoints.py tenant ownership check on legacy download route
    - compliance_reporting_service._generate_csv and _generate_all_csv tenant_id threading
  affects:
    - backend/compliance_reporting_pdf.py (Wave 2 — reads Auto/Manual Evidence columns)
    - backend/compliance_reporting_excel.py (Wave 2 — reads Auto/Manual Evidence columns)
tech_stack:
  added: []
  patterns:
    - TDD red-green cycle with asyncio.run() for async assertion
    - patch.object with create=True for module-attribute monkeypatching
    - fastapi.testclient.TestClient for route-level HTTP assertions
key_files:
  created:
    - backend/tests/test_audit_export.py
  modified:
    - backend/compliance_reporting_data.py
    - backend/compliance_reports_endpoints.py
    - backend/compliance_reporting_service.py
decisions:
  - "STATUS_LEGEND maps internal vocabulary to auditor standard Pass/Fail/Partial/No-Data for Wave 2 renderers"
  - "tenant_id added as trailing optional str=None to _build_report_data, _generate_csv, _generate_all_csv for backward compatibility"
  - "_SUPER_ADMIN_ROLES defined at module level in compliance_reports_endpoints.py (matches authoritative route pattern)"
  - "test_legacy_download_allows_owner asserts status_code != 403; accepts 404 when file absent on disk (correct for unit test)"
metrics:
  duration: "~4m"
  completed: "2026-06-18"
  tasks: 3
  files: 4
---

# Phase 03 Plan 01: Audit Export Data Layer Summary

**One-liner:** Closed AUDIT-03 (auto/manual evidence source labelling) and AUDIT-04 (legacy download tenant isolation) at the data layer, threading tenant_id through the CSV generation chain and adding a STATUS_LEGEND for Wave 2 renderers.

## What Was Built

### Task 0 — Failing-first test scaffold (RED)

Created `backend/tests/test_audit_export.py` with four tests covering AUDIT-03 and AUDIT-04 requirements:

- `test_evidence_source_labelling` — verifies `_flatten_evidence` returns `auto_count`, `manual_count`, and `[Auto]`/`[Manual]` prefixed names
- `test_build_report_data_accepts_tenant_id` — verifies `_build_report_data` signature includes `tenant_id`
- `test_legacy_download_blocks_cross_tenant` — verifies cross-tenant download returns HTTP 403
- `test_legacy_download_allows_owner` — verifies tenant owner is not blocked (not 403)

Three of four tests were RED as expected before production code changes.

### Task 1 — Evidence source bucketing + STATUS_LEGEND (AUDIT-03)

Modified `backend/compliance_reporting_data.py`:

- `STATUS_LEGEND` constant added at module top — maps current internal vocabulary (Compliant/Non-Compliant/Warning/Partially Compliant) to auditor standard vocabulary (Pass/Fail/Partial/No-Data) for Wave 2 renderers
- `_flatten_evidence`: classification rule `is_auto = e.get("systemGenerated") is True or e.get("source") is None`; each name prefixed `[Auto]` or `[Manual]`; `auto_count`/`manual_count` counters tracking named items only (aligned with `count`)
- `_build_report_data`: `tenant_id: str = None` trailing parameter added; both `control_rows.append` branches (no-matching and per-asset) now include `"Auto Evidence": ev["auto_count"]` and `"Manual Evidence": ev["manual_count"]` immediately after `"Evidence Count"`

### Task 2 — Tenant ownership check + tenant_id threading (AUDIT-04)

Modified `backend/compliance_reports_endpoints.py`:

- Added `from database import get_database` import
- Added `_SUPER_ADMIN_ROLES` module-level set matching authoritative route
- Download route now checks `db.compliance_reports.find_one({"filename": filename})`; raises 403 if `tenantId != caller_tenant` for non-super-admin callers

Modified `backend/compliance_reporting_service.py`:

- `_generate_csv(framework_id, reports_dir, tenant_id=None)` — forwards `tenant_id` to `_build_report_data`
- `_generate_all_csv(reports_dir, tenant_id=None)` — forwards `tenant_id` to each `_build_report_data` call (W-3 warning addressed)
- `ComplianceReportingService.generate_report` passes `tenant_id` to `_generate_csv`
- `ComplianceReportingService.generate_all_csv_report` passes `tenant_id` to `_generate_all_csv`

## Verification Results

```
cd backend && ./venv/bin/python -m pytest tests/test_audit_export.py -x -q
4 passed in 1.24s

grep -n "auto_count\|manual_count" compliance_reporting_data.py  -> 9 matches
grep -n "compliance_reports.find_one" compliance_reports_endpoints.py -> line 105
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Plan-Checker Warnings Addressed

**W-3:** `_generate_all_csv` in `compliance_reporting_service.py` was updated to accept and thread `tenant_id` through to `_build_report_data` for full AUDIT-04 coverage (added to Task 2 scope as directed).

**W-4:** `STATUS_LEGEND` constant added to `compliance_reporting_data.py` mapping internal status vocabulary to auditor standard Pass/Fail/Partial/No-Data vocabulary for Wave 2 renderers.

### Pre-existing Test Failure (Out of Scope)

`tests/test_alerts_and_ai.py::TestAlertCreate::test_create_sets_tenant_from_jwt` fails with 422 Unprocessable Entity. Confirmed pre-existing before any plan changes (reproduced on clean stash). Out of scope per deviation rules (scope boundary: only auto-fix issues directly caused by current task changes).

## Known Stubs

None — no stub patterns or placeholder data introduced.

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond those scoped in the plan threat model. The tenant check in the legacy download route closes T-03-01.

## Self-Check: PASSED

- `backend/tests/test_audit_export.py` — FOUND
- `backend/compliance_reporting_data.py` (STATUS_LEGEND, auto_count, Auto Evidence keys) — FOUND
- `backend/compliance_reports_endpoints.py` (compliance_reports.find_one) — FOUND
- `backend/compliance_reporting_service.py` (tenant_id threading) — FOUND
- Commits: 9a90852, 61181f0, 1352fe9 — all present in git log
