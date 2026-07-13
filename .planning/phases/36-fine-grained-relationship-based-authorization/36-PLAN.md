# Phase 36: Fine-Grained Relationship-Based Authorization - Plan

**Goal:** Evaluate OpenFGA/Zanzibar-style ReBAC against current RBAC and prototype a migration for one high-value resource.

**Requirements:** REBAC-01, REBAC-02

**Waves:** 3
- **Wave 1:** Analysis and Design Doc.
- **Wave 2:** Prototype Migration for one resource type.
- **Wave 3:** Verification and Comparative Analysis.

---
## Plan 36-01: Analysis and Design Doc

**Goal:** Research and design ReBAC architecture.

**Tasks:**

1.  **Research & Recommendation (`REBAC-01`):**
    -   Research OpenFGA vs SpiceDB in 2026 contexts.
    -   Compare performance, deployment, and library maturity for Python/FastAPI.
    -   Write `36-DESIGN.md`:
        -   Current RBAC summary.
        -   Decision matrix for OpenFGA/SpiceDB/RBAC.
        -   Recommendation for this phase.
        -   Proposed architecture (sidecar or service interaction).

**Verification:**
-   Design doc completed and approved.

---
## Plan 36-02: Prototype Migration

**Goal:** Implement ReBAC for one resource type.

**Tasks:**

1.  **Service Setup:**
    -   Install selected ReBAC engine (e.g., OpenFGA/SpiceDB client).
    -   Create `backend/rebac_service.py` to interface with the engine.

2.  **Resource Migration:**
    -   Select one resource (e.g., `ComplianceControl`).
    -   Update `ComplianceControl` model to include relationships.
    -   Update `compliance_endpoints.py` to check permissions via `rebac_service` instead of (or alongside) `rbac_service`.

**Verification:**
-   Prototype works for the chosen resource.
-   No regression in existing RBAC for other resources.

---
## Plan 36-03: Verification and Comparative Analysis

**Goal:** Verify and conclude.

**Tasks:**

1.  **Integration Tests (`backend/tests/test_rebac.py`):**
    -   Implement unit and integration tests for ReBAC checks.
    -   Verify parity with old RBAC logic.

2.  **Comparative Analysis:**
    -   Document findings: complexity, performance, development effort.
    -   Final recommendation for full-scale adoption.

**Verification:**
-   Tests pass.
-   Comparative analysis documented.
