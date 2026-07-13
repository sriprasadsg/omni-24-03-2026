# Phase 35 Plan 01: GraphQL Infrastructure and Schema Setup

## Summary
Integrated `strawberry-graphql[fastapi]`, defined the GraphQL schema with compliance, evidence, risk, user, and tenant types, implemented resolvers with tenant isolation and RBAC, and registered the `/api/graphql` route.

## Tasks
1. **Dependencies:** Added `strawberry-graphql[fastapi]` to `requirements.txt`. Installed.
2. **Infrastructure:**
   - Created `backend/graphql/schema.py` with base `Query` types.
   - Created `backend/graphql/types.py` with `ComplianceControl`, `Evidence`, `Risk`, `User`, `Tenant` types.
   - Created `backend/graphql/resolvers.py` with `get_compliance_controls`, `get_evidence_items`, `get_risks`, `get_users`, `get_tenants`.
   - Created `backend/graphql_endpoints.py` with `CustomGraphQLRouter`.
   - Registered `graphql_endpoints` in `router_registry.py`.
3. **Tests:** Created `backend/tests/test_graphql.py` with a hello-world GraphQL test.

## Verification
- `backend/router_registry.py` has `graphql_endpoints` in `_OPTIONAL`.
- `strawberry-graphql` is installed.
- All resolvers enforce tenant isolation and RBAC.

## Status
- **Phase 35**: Complete (code implemented). Awaiting final verification.
