---
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "unknown::scenarios=0"
---

# UAT Report: Phase 35 — GraphQL API

## Overview

Validation of the GraphQL API layer alongside the existing FastAPI REST surface.

## Test Cases

| ID | Description | Result | Notes |
|----|-------------|--------|-------|
| 1 | Hello World Query | Pass | `test_graphql_hello` |
| 2 | Compliance Controls Query | Pass | `test_graphql_compliance_controls_tenant_scoped` — tenant filter asserted |
| 3 | Evidence Items Query | Pass | `test_graphql_evidence_items_tenant_scoped` — tenant filter + `view:compliance` permission asserted |
| 4 | Risks Query | Pass | `test_graphql_risks_tenant_scoped_and_uses_risk_permission` — tenant filter + `view:risk` permission asserted |
| 5 | Users Query | Pass | `test_graphql_users_tenant_scoped_and_password_excluded` — tenant filter, `manage:users` permission, password/hashed_password projected out |
| 6 | Tenants Query | Pass | `test_graphql_tenants_super_admin_only` — tenant Admin gets empty list with no db read; super_admin sees all |
| 7 | Cross-tenant Isolation | Pass | `test_graphql_cross_tenant_isolation` — tenant-b caller queries with tenant-b filter only; plus `test_graphql_unauthenticated_gets_empty_not_data` (no token, no db read) |
| 8 | RBAC Enforcement | Pass | `test_graphql_rbac_denied_gets_empty` + `test_graphql_multi_query_partial_permissions` (per-root enforcement in one request) |

## Verification Gaps

- Human verification with Altair/GraphiQL against a live server not performed (optional; the integration suite covers the same query surface with auth/RBAC/tenant assertions).

## Test Run

- `backend/tests/test_graphql.py` — 10 passed (2026-07-14).
