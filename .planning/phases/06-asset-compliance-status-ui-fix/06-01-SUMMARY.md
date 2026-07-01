---
phase: 06-asset-compliance-status-ui-fix
plan: "01"
subsystem: compliance-status
tags: [compliance, status-override, audit-trail, tenant-isolation]
dependency_graph:
  requires: []
  provides:
    - PATCH /api/assets/{asset_id}/compliance/status endpoint
    - compliance_status_endpoints router registered in router_registry.py
    - STATUS-01 (status persists to asset_compliance collection)
    - STATUS-02 (status_history audit trail with changedBy/changedAt/previous_status)
  affects:
    - backend/router_registry.py
tech_stack:
  added: []
  patterns:
    - FastAPI PATCH endpoint with Pydantic Literal enum validation
    - asyncio.run() unit test pattern (no pytest-asyncio)
    - upsert=True on asset_compliance for first-time override
key_files:
  created:
    - backend/compliance_status_endpoints.py
    - backend/tests/test_compliance_status.py
  modified:
    - backend/router_registry.py
decisions:
  - Extracted to new file — compliance_evidence_endpoints.py at 447 lines; adding inline would breach 500-line CLAUDE.md limit
  - super-admin bypass in tenant guard uses same _SUPER_ROLES set as compliance_evidence_endpoints
  - upsert=True handles both first-time status set and subsequent overrides without separate insert logic
  - asyncio.run() used for async tests (pytest-asyncio not installed); consistent with existing test_evidence_uploads.py pattern
metrics:
  duration: ~1m
  completed_date: "2026-06-19"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 1
status: complete
---

# Phase 06 Plan 01: Compliance Status Endpoint Summary

**One-liner:** PATCH /api/assets/{asset_id}/compliance/status with tenant-isolation guard, immutable audit-history push, and manual_override flag via MongoDB upsert.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create compliance_status_endpoints.py | 4e45dc5 | backend/compliance_status_endpoints.py (new, 82 lines) |
| 2 | Register router in router_registry.py | e541dc8 | backend/router_registry.py (+1 _load line) |
| 3 | Write pytest tests for the new endpoint | 4a04f97 | backend/tests/test_compliance_status.py (new, 122 lines) |

## Implementation Notes

### compliance_status_endpoints.py

- `ComplianceStatusUpdate` Pydantic model uses `Literal["Compliant", "Non-Compliant", "Pending_Evidence"]` — Pydantic rejects any other value at deserialization time (422 without extra code).
- Tenant guard: non-`_SUPER_ROLES` callers must have the asset in `db.assets` matching their `tenant_id`. Returns 403 if not found.
- Previous status fetched from `db.asset_compliance.find_one` before the update — captured in the `status_history` entry and in the response body.
- `$push status_history` entry includes `changedBy`, `changedAt`, `previous_status`, `notes` (STATUS-02).
- `$set manual_override: True`, `overriddenBy`, `overriddenAt` stamped on every successful PATCH (STATUS-01).
- `upsert=True` handles both first-time and subsequent override without extra branching.

### router_registry.py

Single `_load(app, "compliance_status_endpoints", "router")` inserted at line 110, after `compliance_scans_endpoints`, within the Compliance & Governance section.

### Tests

All 3 tests pass using backend venv (`backend/venv/bin/python -m pytest`):
- `test_patch_compliance_status_success`: verifies `ok=True`, `previous_status="Non-Compliant"`, `$set.manual_override`, `$push.status_history.previous_status`
- `test_patch_compliance_status_cross_tenant_403`: `db.assets.find_one` returns `None` → `HTTPException(403)`
- `test_patch_compliance_status_invalid_status_422`: Pydantic raises `ValidationError` for `status="invalid"`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — endpoint fully wired to MongoDB operations; no placeholder or hardcoded return values.

## Threat Flags

None — the new endpoint follows the same tenant-isolation pattern as the existing compliance evidence endpoints. No new trust boundaries introduced beyond what the plan specifies.

## Self-Check: PASSED

- `backend/compliance_status_endpoints.py`: FOUND (82 lines, under 500-line limit)
- `backend/tests/test_compliance_status.py`: FOUND (122 lines)
- `backend/router_registry.py` contains `compliance_status_endpoints`: FOUND (line 110)
- Task 1 commit 4e45dc5: FOUND
- Task 2 commit e541dc8: FOUND
- Task 3 commit 4a04f97: FOUND
- All 3 pytest tests: PASSED (3/3)
