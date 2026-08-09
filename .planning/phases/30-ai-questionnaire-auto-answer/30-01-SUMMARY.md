# 30-01 Summary: AI Questionnaire Auto-Answer — Prerequisite Fixes

## Overview
Closed critical cross-tenant data leakage in `rag_service.py` (T1) and added generation controls (`temperature`, `max_tokens`) to `ai_service.py` to support high-fidelity, grounded questionnaire drafting.

## Changes
1.  **`rag_service.py`**:
    -   Implemented tenant-scoped RAG via `tenantId` metadata tagging on ingestion.
    -   Updated `query()` to enforce tenant isolation using an `$or` filter (`tenantId` matches user tenant OR `global` sentinel).
    -   Query output now includes `tenantId` for provenance verification.

2.  **`ai_service.py` & `ai_providers.py`**:
    -   Extended `AIProvider.generate` and all provider implementations (`AnthropicProvider`, `GeminiProvider`, `OllamaProvider`, `MockProvider`) to accept `temperature` (float, optional) and `max_tokens` (int, default 1024).
    -   Updated `ai_service.generate_text()` to plumb these parameters through to the provider, ensuring they are used in the Anthropic JSON payload.

3.  **Test Suite**:
    -   Created `backend/tests/test_rag_service_tenant_isolation.py`.
    -   Verified isolation with a real ChromaDB instance in a temporary directory (no mocking).
    -   Confirmed that:
        -   Tenant-specific chunks are isolated.
        -   `global` chunks remain retrievable by all tenants.
        -   `tenantId` is correctly returned in query results.

## Verification
-   `cd backend && python3 -m pytest tests/test_rag_service_tenant_isolation.py -x -v` passed (3/3).
-   Signature inspection verified the addition of new generation parameters.

## Status
-   **T1 (Cross-tenant leak)**: Mitigated and verified with hard-blocking tests.
-   **Generation Control**: Implemented and ready for Phase 30-04.
