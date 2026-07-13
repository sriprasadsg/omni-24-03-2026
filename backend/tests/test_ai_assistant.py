"""Phase 38 tests — Interactive AI Security Assistant.

- test_assistant_chat_service: chat() grounds answers in RAG + live findings and cites sources
- test_assistant_chat_service_tenant_isolation: cross-tenant RAG chunks never cited
- test_assistant_chat_endpoint: POST /api/assistant/chat → 200 with {answer, sources}
- test_assistant_chat_endpoint_empty_query: blank query short-circuits without calling the LLM
- test_assistant_chat_streaming: POST /api/assistant/chat/stream → SSE frames ending in [DONE]
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
from auth_types import TokenData
import ai_assistant_endpoints as ep_mod
from ai_assistant_service import chat


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_RAG_DOCS = [
    {
        "id": "doc1",
        "content": "This is a compliance document snippet.",
        "metadata": {"tenantId": "test-tenant", "source": "SOC2 Spec"},
    },
    {
        "id": "doc-other-tenant",
        "content": "Another tenant's confidential snippet.",
        "metadata": {"tenantId": "other-tenant", "source": "Internal"},
    },
]

_EVIDENCE_DOCS = [
    {"controlId": "AC-1", "title": "Access Control", "framework": "SOC2", "status": "FAILED"},
]

_RISK_DOCS = [
    {"id": "RISK-1", "title": "Data Breach", "severity": "Critical", "status": "Open"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cursor(docs):
    """Motor-style cursor: find() is sync, to_list() is awaited."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _make_db(evidence_docs, risk_docs):
    db = MagicMock()
    db.compliance_evidence.find = MagicMock(return_value=_make_cursor(evidence_docs))
    db.risks.find = MagicMock(return_value=_make_cursor(risk_docs))
    return db


def _service_patches(answer="Control AC-1 is failing and RISK-1 (Data Breach) is open."):
    rag = MagicMock()
    rag.query = MagicMock(return_value=_RAG_DOCS)
    ai = MagicMock()
    ai.generate_text = AsyncMock(return_value=answer)
    db = _make_db(_EVIDENCE_DOCS, _RISK_DOCS)
    return (
        patch("ai_assistant_service.rag_service", rag),
        patch("ai_assistant_service.get_database", MagicMock(return_value=db)),
        patch("ai_assistant_service.ai_service", ai),
        ai,
    )


def _make_client():
    app = FastAPI()
    app.include_router(ep_mod.router)
    user = TokenData(
        username="user@test.com", role="Admin", tenant_id="test-tenant", mfa_verified=True
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _endpoint_patches():
    perms = patch.object(
        ep_mod.rbac_service, "get_user_permissions", AsyncMock(return_value=["*"])
    )
    tenant = patch("ai_assistant_endpoints.get_tenant_id", MagicMock(return_value="test-tenant"))
    return perms, tenant


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

async def test_assistant_chat_service():
    """chat() returns an answer with RAG, control, and risk sources cited."""
    p_rag, p_db, p_ai, _ = _service_patches()
    with p_rag, p_db, p_ai:
        result = await chat("What are my failing controls?", "test-tenant")

    assert result["answer"]
    ids = [s["id"] for s in result["sources"]]
    assert "doc1" in ids       # RAG knowledge-base chunk
    assert "AC-1" in ids       # failing compliance control
    assert "RISK-1" in ids     # open critical risk


async def test_assistant_chat_service_tenant_isolation():
    """RAG chunks tagged with another tenant's id must never be cited."""
    p_rag, p_db, p_ai, ai = _service_patches()
    with p_rag, p_db, p_ai:
        result = await chat("Show my posture", "test-tenant")

    ids = [s["id"] for s in result["sources"]]
    assert "doc-other-tenant" not in ids
    # The other tenant's snippet must not reach the prompt either
    prompt = ai.generate_text.call_args.args[0]
    assert "Another tenant's confidential snippet." not in prompt


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

def test_assistant_chat_endpoint():
    """POST /api/assistant/chat returns grounded answer with sources."""
    client = _make_client()
    p_rag, p_db, p_ai, _ = _service_patches()
    p_perms, p_tenant = _endpoint_patches()
    with p_rag, p_db, p_ai, p_perms, p_tenant:
        response = client.post("/api/assistant/chat", json={"query": "Show my risks"})

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["sources"]) > 0
    assert any(s["id"] == "RISK-1" for s in data["sources"])


def test_assistant_chat_endpoint_empty_query():
    """Blank query returns a friendly message and never calls the LLM."""
    client = _make_client()
    p_rag, p_db, p_ai, ai = _service_patches()
    p_perms, p_tenant = _endpoint_patches()
    with p_rag, p_db, p_ai, p_perms, p_tenant:
        response = client.post("/api/assistant/chat", json={"query": "   "})

    assert response.status_code == 200
    assert response.json() == {"answer": "No question provided.", "sources": []}
    ai.generate_text.assert_not_awaited()


def test_assistant_chat_streaming():
    """POST /api/assistant/chat/stream emits SSE chunk/sources frames then [DONE]."""
    client = _make_client()
    p_rag, p_db, p_ai, _ = _service_patches(answer="Two words")
    p_perms, p_tenant = _endpoint_patches()
    with p_rag, p_db, p_ai, p_perms, p_tenant:
        response = client.post("/api/assistant/chat/stream", json={"query": "Stream my status"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    content = response.text
    assert '"chunk"' in content
    assert '"sources"' in content
    assert "data: [DONE]" in content
