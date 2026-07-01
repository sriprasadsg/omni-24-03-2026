---
phase: "23"
plan: "01"
subsystem: backend
status: complete
tags: [windows, powershell, compliance, evidence, api]
dependency_graph:
  requires: [compliance_evidence_processor, authentication_service, database]
  provides: [POST /api/powershell-evidence/submit]
  affects: [asset_compliance collection, control_evidence collection]
tech_stack:
  added: []
  patterns: [FastAPI router, Pydantic v2 validation, dependency-overrides test pattern]
key_files:
  created:
    - backend/powershell_evidence_endpoints.py
    - backend/tests/test_powershell_evidence.py
  modified:
    - backend/router_registry.py
decisions:
  - Registration key takes auth priority over JWT — headless PS agent needs keyless login
  - Cross-tenant guard applied when both key and JWT present — they must agree unless super admin
  - Empty checks list returns 422 via Pydantic min_length=1 — consistent with FastAPI defaults
  - Tests patch get_database at module level (not via Depends) since endpoint calls it directly
metrics:
  duration: "3m 17s"
  completed: "2026-06-24"
  tasks_completed: 5
  files_created: 2
  files_modified: 1
  tests_passing: 6
---

# Phase 23 Plan 01: PowerShell Evidence Ingestion API Summary

**One-liner:** POST /api/powershell-evidence/submit — batch Windows compliance evidence via registration key or JWT, fed into existing process_automated_evidence() pipeline.

## What Was Done

- Created `backend/powershell_evidence_endpoints.py` — new FastAPI router with `POST /api/powershell-evidence/submit`
- `PSCheck` model validates each check: name (1-200 chars), status (`Pass|Fail|Warning|Error|N/A`), details, optional evidence_content and content_hash
- `PSEvidencePayload` validates hostname (1-253 chars) and requires at least one check (min_length=1)
- Auth resolution: `X-Registration-Key` header looks up `db._db.tenants.find_one({"registrationKey": key})` → if JWT also present, cross-tenant guard fires unless super admin role
- Falls back to JWT bearer (`get_optional_user`) for tenant_id
- Neither auth present → 401
- Calls `process_automated_evidence(hostname, {"checks": [...]}, db, agent_type="powershell", fallback_tenant_id=tenant_id)`
- Returns `{"accepted": N, "hostname": ..., "tenant_id": ...}`
- Wired into `backend/router_registry.py` under Compliance & Governance section
- 6 TDD tests in `backend/tests/test_powershell_evidence.py` — all passing

## TDD Gate Compliance

- RED commit: `b29f30f` — 6 failing tests (ModuleNotFoundError — endpoint not yet created)
- GREEN commit: `5a1fd3b` — implementation + updated tests — all 6 passing
- Deviation: Tests needed `patch("powershell_evidence_endpoints.get_database", ...)` at module level instead of `dependency_overrides` because `get_database()` is called directly in the endpoint body, not via `Depends`. Tests updated accordingly (Rule 1 auto-fix during GREEN phase).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock strategy: get_database patched at module level**
- **Found during:** Task 4 (test run)
- **Issue:** Tests used `app.dependency_overrides[get_database]` but `get_database()` is called as a plain function call inside the endpoint, not as a FastAPI `Depends()` parameter. Overriding a non-dependency has no effect — tests got 500 "Database not connected" errors.
- **Fix:** Updated all 6 tests to use `with patch("powershell_evidence_endpoints.get_database", return_value=mock_db):` — patches the function reference at the module level, which is intercepted at call time.
- **Files modified:** `backend/tests/test_powershell_evidence.py`
- **Commit:** `5a1fd3b`

## Known Stubs

None — endpoint is fully wired; process_automated_evidence handles all 28 Windows check name mappings to control IDs via existing COMPLIANCE_CHECK_MAPPINGS.

## Self-Check: PASSED

- FOUND: backend/powershell_evidence_endpoints.py
- FOUND: backend/tests/test_powershell_evidence.py
- FOUND: .planning/phases/23-windows-powershell-evidence/23-01-SUMMARY.md
- FOUND commit b29f30f: test(23-01): add failing tests for PowerShell evidence ingestion endpoint
- FOUND commit 5a1fd3b: feat(windows): PowerShell evidence ingestion API — POST /api/powershell-evidence/submit (Phase 23-01)

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: unauthenticated-ingestion | backend/powershell_evidence_endpoints.py | Endpoint is reachable with only a static registration key — rate limiting and key rotation are not enforced at this layer. Handled by existing rate_limiter.py middleware; key rotation is an ops concern. |
