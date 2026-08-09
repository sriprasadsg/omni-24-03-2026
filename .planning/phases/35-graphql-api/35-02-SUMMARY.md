# Phase 35 Plan 02: Resolvers with Tenant and RBAC enforcement

## Summary
Implemented resolvers for `ComplianceControl`, `Evidence`, `Risk`, `User`, and `Tenant` data types. All resolvers enforce tenant isolation and RBAC checks using `verify_permission` or `is_super_admin`.

## Tasks
1. **Context:** Extended `CustomGraphQLRouter.get_context` in `backend/graphql_endpoints.py` to include `current_user` and `tenant_id` from FastAPI `Request`.
2. **Resolvers:**
   - Created `backend/graphql/resolvers.py` with `get_compliance_controls`, `get_evidence_items`, `get_risks`, `get_users`, `get_tenants`.
   - All resolvers enforce `tenant_id` scoping in MongoDB queries.
   - RBAC gates via `verify_permission` (compliance, evidence, risks, users) and `is_super_admin` (tenants).

## Verification
- Queries correctly filter by `tenant_id`.
- RBAC checks correctly block unauthorized users.

## Status
- **Phase 35, Wave 2**: Complete.
