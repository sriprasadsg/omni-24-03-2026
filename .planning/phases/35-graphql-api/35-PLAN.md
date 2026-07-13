# Phase 35: GraphQL API - Plan

**Goal:** Stand up a GraphQL layer alongside the existing FastAPI REST surface for the core compliance/evidence/risk data model, enforcing the same tenant-isolation and RBAC checks.

**Requirements:** GQL-01, GQL-02

**Waves:** 3
- **Wave 1:** GraphQL Infrastructure and Schema Setup (Strawberry).
- **Wave 2:** Resolvers with Tenant and RBAC enforcement.
- **Wave 3:** Integration Tests and Verification.

---
## Plan 35-01: GraphQL Infrastructure and Schema Setup

**Goal:** Integrate `strawberry-graphql` and define the initial schema.

**Tasks:**

1.  **Dependencies:**
    -   Add `strawberry-graphql[fastapi]` to `backend/requirements.txt`.

2.  **Infrastructure:**
    -   Create `backend/graphql/schema.py` to define the base `Query` object.
    -   Register the `/api/graphql` route in `backend/app.py` or via `router_registry.py` if possible.
    -   Add `strawberry` configuration to disable introspection in production if desired.

3.  **Schema (Core Models):**
    -   Create `backend/graphql/types.py` for Strawberry type definitions (e.g., `ComplianceControl`, `Evidence`, `Risk`).
    -   Map existing Pydantic models/MongoDB documents to Strawberry types.

**Verification:**
- `/api/graphql` is reachable.
- Basic "hello world" query returns data.

---
## Plan 35-02: Resolvers with Tenant and RBAC enforcement

**Goal:** Implement resolvers that enforce security constraints.

**Tasks:**

1.  **Context:**
    -   Extend Strawberry's `Info.context` to include `current_user` and `tenant_id` by extracting them from the FastAPI `Request` object.

2.  **Resolvers:**
    -   Create `backend/graphql/resolvers.py` for query handlers.
    -   Implement resolvers for compliance, evidence, risk data.
    -   Enforce constraints in resolvers:
        -   `get_current_user` (for auth).
        -   Pass `context.tenant_id` to MongoDB queries (`db.collection.find({"tenantId": context.tenant_id, ...})`).
        -   Use `rbac_service.check_rbac` (or equivalent) in resolvers before executing queries.

**Verification:**
- Queries correctly filter by `tenant_id`.
- RBAC checks correctly block unauthorized users.

---
## Plan 35-03: Integration Tests and Verification

**Goal:** Verify security and compliance with the REST API.

**Tasks:**

1.  **Tests (`backend/tests/test_graphql.py`):**
    -   Create `backend/tests/test_graphql.py`.
    -   Implement integration tests:
        -   Cross-tenant isolation (user A cannot query tenant B's data).
        -   RBAC enforcement (user without required role cannot query).
        -   Successful queries for authorized user.

2.  **Human Verification:**
    -   Use a GraphQL client (e.g., Altair or GraphiQL) to test queries.
    -   Verify the results match REST API outcomes for the same queries.

**Verification:**
- All tests pass.
- No auth bypass found in GQL resolvers.
