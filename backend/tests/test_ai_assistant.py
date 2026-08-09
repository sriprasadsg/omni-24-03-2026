"""Phase 38 / 39-07 tests — Interactive AI Security Assistant.

- test_assistant_chat_service: chat() grounds answers in RAG + live findings and cites sources
- test_assistant_chat_service_tenant_isolation: cross-tenant RAG chunks never cited or forwarded
- test_assistant_chat_endpoint: POST /api/assistant/chat → 200 with {answer, sources}
- test_assistant_chat_endpoint_empty_query: blank query short-circuits without calling the agent
- test_assistant_chat_streaming: POST /api/assistant/chat/stream → SSE frames ending in [DONE]

Phase 39-07 rewired `ai_assistant_service.chat()` as a thin shim delegating to
`ai_orchestration.agents.chat.chat` (a `create_agent`-based agent) — the
mocking layer below patches at that new boundary (`rag_service`,
`build_model_for_tenant`, `create_agent`, `checkpointer_lifespan` inside
`ai_orchestration.agents.chat`, plus `ai_assistant_service.get_database`)
instead of the old `ai_assistant_service.rag_service`/`.ai_service` module
attributes, which no longer exist on that module. The behavioral contract
these tests assert — the `{answer, sources}` shape, tenant isolation, and
both endpoints' response contracts — is unchanged (39-CONTEXT.md).
"""
import sys
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
from auth_types import TokenData
import ai_assistant_endpoints as ep_mod
from ai_assistant_service import chat


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    """guardrail_service.scan_and_log calls the real get_database() — patch
    it at the source (the same singleton ai_orchestration.guardrails
    imports) so scan_input/scan_output run for real without a live Mongo
    connection, matching test_chat_agent.py's convention."""
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

# Flat shape as returned by rag_service.query()
_RAG_DOCS = [
    {
        "id": "doc1",
        "content": "This is a compliance document snippet.",
        "source": "SOC2 Spec",
        "tenantId": "test-tenant",
        "relevance": 0.1,
    },
    {
        "id": "doc-global",
        "content": "Shared security standard snippet.",
        "source": "NIST 800-53",
        "tenantId": "global",
        "relevance": 0.2,
    },
    {
        "id": "doc-other-tenant",
        "content": "Another tenant's confidential snippet.",
        "source": "Internal",
        "tenantId": "other-tenant",
        "relevance": 0.3,
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
    db = MagicMock(spec=["compliance_evidence", "risks", "agent_ai_decisions", "system_settings", "tenants"])
    db.compliance_evidence = MagicMock()
    db.compliance_evidence.find = MagicMock(return_value=_make_cursor(evidence_docs))
    db.risks = MagicMock()
    db.risks.find = MagicMock(return_value=_make_cursor(risk_docs))
    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)
    db.tenants = MagicMock()
    db.tenants.find = MagicMock(return_value=_make_cursor([]))
    return db


def _agent_stub(answer="Control AC-1 is failing and RISK-1 (Data Breach) is open."):
    """Stub create_agent()'s returned object — mirrors the shape
    `ai_orchestration.agents.chat.chat()` expects back from `.ainvoke`."""
    agent = MagicMock()
    final_message = MagicMock()
    final_message.content = answer
    final_message.response_metadata = {}
    agent.ainvoke = AsyncMock(return_value={"messages": [final_message]})
    return agent


@asynccontextmanager
async def _fake_checkpointer_lifespan():
    yield MagicMock()


def _service_patches(answer="Control AC-1 is failing and RISK-1 (Data Breach) is open."):
    """Patch every seam `ai_assistant_service.chat()` -> `ai_orchestration
    .agents.chat.chat()` traverses to reach a model, without any live
    model/gateway/Chroma/sqlite call."""
    rag = MagicMock()
    rag.query = MagicMock(return_value=_RAG_DOCS)
    db = _make_db(_EVIDENCE_DOCS, _RISK_DOCS)
    agent = _agent_stub(answer)
    return (
        patch("ai_orchestration.agents.chat.rag_service", rag),
        patch("ai_assistant_service.get_database", MagicMock(return_value=db)),
        patch("ai_orchestration.agents.chat.build_model_for_tenant", AsyncMock(return_value=MagicMock())),
        patch("ai_orchestration.agents.chat.create_agent", MagicMock(return_value=agent)),
        patch("ai_orchestration.agents.chat.checkpointer_lifespan", _fake_checkpointer_lifespan),
        agent,
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
    p_rag, p_db, p_model, p_agent, p_ckpt, _agent = _service_patches()
    with p_rag, p_db, p_model, p_agent, p_ckpt:
        result = await chat("What are my failing controls?", "test-tenant")

    assert result["answer"]
    ids = [s["id"] for s in result["sources"]]
    assert "doc1" in ids        # tenant's own RAG chunk
    assert "doc-global" in ids  # shared "global" knowledge is allowed
    assert "AC-1" in ids        # failing compliance control
    assert "RISK-1" in ids      # open critical risk


async def test_assistant_chat_service_tenant_isolation():
    """RAG chunks tagged with another tenant's id must never be cited."""
    p_rag, p_db, p_model, p_agent, p_ckpt, agent = _service_patches()
    with p_rag, p_db, p_model, p_agent, p_ckpt:
        result = await chat("Show my posture", "test-tenant")

    ids = [s["id"] for s in result["sources"]]
    assert "doc-other-tenant" not in ids
    # The other tenant's snippet must not reach the agent either
    forwarded_content = agent.ainvoke.call_args.args[0]["messages"][0]["content"]
    assert "Another tenant's confidential snippet." not in forwarded_content


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

def test_assistant_chat_endpoint():
    """POST /api/assistant/chat returns grounded answer with sources."""
    client = _make_client()
    p_rag, p_db, p_model, p_agent, p_ckpt, _agent = _service_patches()
    p_perms, p_tenant = _endpoint_patches()
    with p_rag, p_db, p_model, p_agent, p_ckpt, p_perms, p_tenant:
        response = client.post("/api/assistant/chat", json={"query": "Show my risks"})

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["sources"]) > 0
    assert any(s["id"] == "RISK-1" for s in data["sources"])


def test_assistant_chat_endpoint_empty_query():
    """Blank query returns a friendly message and never calls the agent."""
    client = _make_client()
    p_rag, p_db, p_model, p_agent, p_ckpt, agent = _service_patches()
    p_perms, p_tenant = _endpoint_patches()
    with p_rag, p_db, p_model, p_agent, p_ckpt, p_perms, p_tenant:
        response = client.post("/api/assistant/chat", json={"query": "   "})

    assert response.status_code == 200
    assert response.json() == {"answer": "No question provided.", "sources": []}
    agent.ainvoke.assert_not_awaited()


def test_assistant_chat_streaming():
    """POST /api/assistant/chat/stream emits SSE chunk/sources frames then [DONE]."""
    client = _make_client()
    p_rag, p_db, p_model, p_agent, p_ckpt, _agent = _service_patches(answer="Two words")
    p_perms, p_tenant = _endpoint_patches()
    with p_rag, p_db, p_model, p_agent, p_ckpt, p_perms, p_tenant:
        response = client.post("/api/assistant/chat/stream", json={"query": "Stream my status"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    content = response.text
    assert '"chunk"' in content
    assert '"sources"' in content
    assert "data: [DONE]" in content
