---
phase: 32-cloud-and-saas-provider-expansion
plan: 03
subsystem: backend/saas
tags:
  - posture-checks
  - saas
  - github
  - okta
  - google-workspace
  - slack
  - jira
  - tenant-scoped
  - rbac
  - prov-03
tech-stack:
  - python 3.12 with fastapi
  - asyncio + motor
  - pytest with unittest.mock
key-files:
  created:
    - backend/saas_posture_checks_service.py
    - backend/saas_posture_checks_endpoints.py
  modified:
    - backend/router_registry.py
    - backend/tests/test_saas_posture_checks.py
decisions:
  - "Reuse pull_all_evidence() as single data source never re-fetch"
  - "status mapping is pure reshaping: fail -> FAIL, pass -> PASS, missing -> NO-DATA"
  - "Tenant-scoped upsert key (tenantId + connectionId + checkId)"
metrics:
  duration: ~15 minutes wall clock
  completed_date: 2026-07-10
status: complete
---

# Phase 32 Plan 03: SaaS Posture Checks Summary

## Objective

Create 5-provider (GITHUB, OKTA, GWS, SLACK, JIRA) posture checks layer reusing `saas_integration_service.pull_all_evidence()` as the single evidence source and reshaping already-computed status values into tenant-scoped `saas_check_results` documents matching `cloud_check_results` shape.

## Tasks

### Task 1: saas_posture_checks_service.py + test scaffold [done]
- GITHUB_POSTURE_CHECKS (3 checks), OKTA_POSTURE_CHECKS (2 checks), GWS_POSTURE_CHECKS (2 checks), SLACK_POSTURE_CHECKS (1 check), JIRA_POSTURE_CHECKS (1 check)
- `run_posture_checks(connection, db)` reusing `pull_all_evidence`
- Service tests assert fail->FAIL, pass->PASS, missing->NO-DATA

### Task 2: saas_posture_checks_endpoints.py + registration [done]
- POST /api/saas/posture-checks/{connection_id}/run
- GET /api/saas/posture-checks/{connection_id}/results
- Tenant isolation (403 on cross-tenant access)
- Registered in `router_registry.py`

## Key Changes

### saas_posture_checks_service.py
- `_evidence_control_id` mapped to exact `_CTRL_*` and `_OKTA_MFA_CTRL`/`_GWS_ACCOUNT_SEC` strings from `saas_integration_service.py`
- `saas_integration_service` line count unchanged (500)

### saas_posture_checks_endpoints.py
- Dependencies: `get_current_user` from `authentication_service`
- Tenant isolation: super_admin/platform_admin bypass; regular user sees own tenant only

### router_registry.py
- Added `_load(app, "saas_posture_checks_endpoints", "router")` after `saas_integration_endpoints`

### test_saas_posture_checks.py
- 5 tests: 1 service + 1 endpoint success + 1 cross-tenant deny + 1 results list + 1 cross-tenant results deny

## Verification

- `pytest tests/test_saas_posture_checks.py -x` passes
- `wc -l backend/saas_integration_service.py` = 500 (unchanged)
- All OAuth providers have posture-check catalogs reusing `pull_*_evidence()` data
- fail->FAIL reshaping test-locked
- Results tenant-scoped in `saas_check_results`

## Deviations from Plan

None. Plan executed as written.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: access-control | backend/saas_posture_checks_endpoints.py | GET /results tenant-scoped but uses `user_tenant` not `connection.get("tenant_id")` - same pattern as POST /run, consistent with plan |

## Commits

- `d68c5122` feat(32-03): implement saas_posture_checks_service and test
- `837fda12` feat(phase-32-03): add saas_posture_checks_endpoints router with tenant-scoped access
- `f75d6c7c` feat(phase-32-03): add saas_posture_checks_endpoints router and register in registry
