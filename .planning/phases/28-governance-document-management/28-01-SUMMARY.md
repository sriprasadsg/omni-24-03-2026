# 28-01 Summary: Governance Document Management — Versioned Documents

## Overview
Built the backend surface for versioned governance (policy/procedure) documents with a draft → pending_approval → approved → published state machine, delegating approval to the existing `approval_service.py` engine.

## Changes
1.  **`backend/governance_document_service.py`**: GovernanceDocument model with embedded versions array, status lifecycle (`draft` → `pending_approval` → `approved` → `published`), and approval delegation to `approval_service.py`.
2.  **`backend/governance_document_endpoints.py`**: `POST /api/governance/documents` (create), `POST /{id}/versions` (create version), `POST /{id}/submit-for-approval`, `PATCH /{id}/publish`, `GET /{id}`, `GET /` (list). All tenant-isolated.
3.  **Router Registration**: `governance_document_endpoints` registered in `router_registry.py`.
4.  **Tests**: `backend/tests/test_governance_documents.py` covering create, version creation, approval delegation, publish gating, tenant isolation.

## Verification
-   `pytest backend/tests/test_governance_documents.py -x` passes.
-   Documents cannot reach `published` without `approved` status from `approval_service.py`.

## Status
-   **DOC-01**: Complete. Ready for Plan 28-02 (e-signature) and 28-03 (dashboard).