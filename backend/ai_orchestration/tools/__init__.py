"""Phase 39-05 — Tenant-closed LangChain @tool factories.

Every tool factory in this package takes `tenant_id` (and any DB handle) as a
closed-over factory argument, never a model-fillable tool parameter — the
structural mitigation for cross-tenant leakage (RESEARCH.md Pitfall B,
AI-SPEC Section 3). See `retrieval.py` (search_evidence) and `evidence.py`
(get_control_evidence).
"""
