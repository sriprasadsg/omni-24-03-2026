"""Phase 39-07 — hermetic unit tests for the create_agent chat surface
(ai_orchestration/agents/chat.py) and the ai_assistant_service.py shim.

Convention: hermetic — the agent/model call graph is stubbed
(`create_agent`/`build_model_for_tenant`/`checkpointer_lifespan` patched to
avoid any live model/gateway/Chroma/sqlite call), mirroring
test_auditor_agent.py's convention. RAG/live-findings queries run through
the real `_rag_context`/`_live_findings` helpers against mocked
`rag_service`/`db` objects so the tenant-isolation logic those helpers
implement is actually exercised, not mocked away.

Naming: `-k agent` selects `ai_orchestration.agents.chat` tests, `-k shim`
selects `ai_assistant_service.py` tests — matching this plan's two per-task
`<verify>` commands.
"""
import os
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.agents.chat import astream_chat, chat
from ai_assistant_service import chat as shim_chat

# ---------------------------------------------------------------------------
# Fixture data (mirrors test_ai_assistant.py's pre-existing shapes)
# ---------------------------------------------------------------------------

_RAG_DOCS = [
    {
        "id": "doc1",
        "content": "This is a compliance document snippet.",
        "source": "SOC2 Spec",
        "tenantId": "tenant-a",
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
        "tenantId": "tenant-b",
        "relevance": 0.3,
    },
]

_EVIDENCE_DOCS = [
    {"controlId": "AC-1", "title": "Access Control", "framework": "SOC2", "status": "FAILED"},
]

_RISK_DOCS = [
    {"id": "RISK-1", "title": "Data Breach", "severity": "Critical", "status": "Open"},
]


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    """guardrail_service.scan_and_log calls the real get_database() — patch
    it at the source so scan_input/scan_output run for real, without a live
    Mongo connection, mirroring test_auditor_agent.py's convention."""
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


def _cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _make_db(evidence_docs=None, risk_docs=None):
    """Minimal mocked db satisfying: _live_findings (compliance_evidence.find,
    risks.find), _tenant_model_names (system_settings.find_one),
    log_ai_decision (agent_ai_decisions.insert_one), and
    cross_tenant_output_scan (tenants.find). `spec=` (no `_db` attribute)
    ensures `_raw_db`'s `getattr(db, "_db", db)` unwrap returns this same
    mock, matching how the real TenantIsolatedDatabase-vs-exempt-collection
    unwrap behaves for non-exempt collections."""
    evidence_docs = _EVIDENCE_DOCS if evidence_docs is None else evidence_docs
    risk_docs = _RISK_DOCS if risk_docs is None else risk_docs

    db = MagicMock(spec=["compliance_evidence", "risks", "agent_ai_decisions", "system_settings", "tenants"])
    db.compliance_evidence = MagicMock()
    db.compliance_evidence.find = MagicMock(return_value=_cursor(evidence_docs))
    db.risks = MagicMock()
    db.risks.find = MagicMock(return_value=_cursor(risk_docs))
    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)
    db.tenants = MagicMock()
    db.tenants.find = MagicMock(return_value=_cursor([]))
    return db


def _agent_stub(answer_text="Control AC-1 is failing and RISK-1 (Data Breach) is open."):
    """Stub `create_agent()`'s returned object — `.ainvoke` returns a canned
    final AI message; captures the invoke config for thread_id assertions."""
    agent = MagicMock()
    final_message = MagicMock()
    final_message.content = answer_text
    final_message.response_metadata = {}
    agent.ainvoke = AsyncMock(return_value={"messages": [final_message]})

    async def _astream(*_args, **_kwargs):
        chunk = MagicMock()
        chunk.content = answer_text
        yield (chunk, {})

    agent.astream = _astream
    return agent


@asynccontextmanager
async def _fake_checkpointer_lifespan():
    """No real sqlite file I/O in hermetic tests."""
    yield MagicMock()


def _patched(agent, rag_docs=None):
    """Patch every call-graph seam `chat()`/`astream_chat()` uses to reach a
    model, matching test_auditor_agent.py's `_patched` convention."""
    rag = MagicMock()
    rag.query = MagicMock(return_value=_RAG_DOCS if rag_docs is None else rag_docs)
    return (
        patch("ai_orchestration.agents.chat.rag_service", rag),
        patch("ai_orchestration.agents.chat.build_model_for_tenant", AsyncMock(return_value=MagicMock())),
        patch("ai_orchestration.agents.chat.create_agent", MagicMock(return_value=agent)),
        patch("ai_orchestration.agents.chat.checkpointer_lifespan", _fake_checkpointer_lifespan),
        rag,
    )


# ---------------------------------------------------------------------------
# ai_orchestration/agents/chat.py (-k agent)
# ---------------------------------------------------------------------------


class TestChatAgent:
    async def test_happy_path_returns_answer_and_sources(self):
        db = _make_db()
        agent = _agent_stub()
        p1, p2, p3, p4, _rag = _patched(agent)
        with p1, p2, p3, p4:
            result = await chat("What are my failing controls?", "tenant-a", db=db)

        assert result["answer"]
        ids = [s["id"] for s in result["sources"]]
        assert "doc1" in ids          # tenant's own RAG chunk
        assert "doc-global" in ids    # shared "global" knowledge is allowed
        assert "AC-1" in ids          # failing compliance control
        assert "RISK-1" in ids        # open critical risk
        agent.ainvoke.assert_awaited_once()
        db.agent_ai_decisions.insert_one.assert_awaited_once()

    async def test_cross_tenant_rag_chunk_never_cited_or_forwarded(self):
        db = _make_db()
        agent = _agent_stub()
        p1, p2, p3, p4, _rag = _patched(agent)
        with p1, p2, p3, p4:
            result = await chat("Show my posture", "tenant-a", db=db)

        ids = [s["id"] for s in result["sources"]]
        assert "doc-other-tenant" not in ids
        forwarded_content = agent.ainvoke.call_args.args[0]["messages"][0]["content"]
        assert "Another tenant's confidential snippet." not in forwarded_content

    async def test_thread_id_is_tenant_prefixed_and_distinct_per_tenant(self):
        db = _make_db()
        agent_a = _agent_stub()
        agent_b = _agent_stub()

        p1, p2, p3, p4, _rag = _patched(agent_a)
        with p1, p2, p3, p4:
            await chat("Same question", "tenant-a", conversation_id="conv-1", db=db)
        thread_a = agent_a.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

        p1, p2, p3, p4, _rag = _patched(agent_b)
        with p1, p2, p3, p4:
            await chat("Same question", "tenant-b", conversation_id="conv-1", db=db)
        thread_b = agent_b.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

        assert thread_a == "tenant-a:conv-1"
        assert thread_b == "tenant-b:conv-1"
        assert thread_a != thread_b

    async def test_input_guardrail_block_skips_agent_invocation(self):
        db = _make_db()
        agent = _agent_stub()
        p1, p2, p3, p4, _rag = _patched(agent)
        blocked = MagicMock(passed=False, findings=["PII Detected"], reason="input_guardrail_blocked")
        with p1, p2, p3, p4, patch(
            "ai_orchestration.agents.chat.scan_input", AsyncMock(return_value=blocked)
        ):
            result = await chat("my SSN is 123-45-6789", "tenant-a", db=db)

        assert result["sources"] == []
        assert "flagged" in result["answer"]
        agent.ainvoke.assert_not_awaited()

    async def test_output_guardrail_block_returns_safe_message(self):
        db = _make_db()
        agent = _agent_stub()
        p1, p2, p3, p4, _rag = _patched(agent)
        blocked = MagicMock(passed=False, findings=["injection"], reason="output_guardrail_blocked")
        with p1, p2, p3, p4, patch(
            "ai_orchestration.agents.chat.scan_output", AsyncMock(return_value=blocked)
        ):
            result = await chat("Show my risks", "tenant-a", db=db)

        assert result["sources"] == []
        assert "flagged" in result["answer"]

    async def test_agent_invocation_error_returns_error_answer_not_raise(self):
        db = _make_db()
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=RuntimeError("gateway down"))
        p1, p2, p3, p4, _rag = _patched(agent)
        with p1, p2, p3, p4:
            result = await chat("Show my risks", "tenant-a", db=db)

        assert "Error generating response" in result["answer"]
        assert result["sources"] == []

    async def test_astream_yields_chunks_then_sources(self):
        db = _make_db()
        agent = _agent_stub("Two words")
        p1, p2, p3, p4, _rag = _patched(agent)
        with p1, p2, p3, p4:
            frames = [f async for f in astream_chat("Stream my status", "tenant-a", db=db)]

        assert any("chunk" in f for f in frames)
        assert any("sources" in f for f in frames)


# ---------------------------------------------------------------------------
# ai_assistant_service.py shim (-k shim)
# ---------------------------------------------------------------------------


class TestAssistantServiceShim:
    async def test_shim_delegates_and_preserves_contract(self):
        canned = {"answer": "Delegated answer", "sources": [{"type": "rag", "id": "x", "title": "t", "snippet": "s"}]}
        with patch(
            "ai_orchestration.agents.chat.chat", AsyncMock(return_value=canned)
        ), patch("ai_assistant_service.get_database", MagicMock(return_value=MagicMock())):
            result = await shim_chat("What is my status?", "tenant-a", history=[{"role": "user", "content": "hi"}])

        assert result == canned

    async def test_shim_error_path_returns_answer_sources_never_raises(self):
        with patch(
            "ai_orchestration.agents.chat.chat", AsyncMock(side_effect=RuntimeError("boom"))
        ), patch("ai_assistant_service.get_database", MagicMock(return_value=MagicMock())):
            result = await shim_chat("What is my status?", "tenant-a")

        assert isinstance(result["sources"], list)
        assert result["sources"] == []
        assert "boom" in result["answer"]

    def test_shim_still_exposes_async_chat_with_default_history(self):
        import inspect

        assert inspect.iscoroutinefunction(shim_chat)
        sig = inspect.signature(shim_chat)
        assert list(sig.parameters) == ["query", "tenant_id", "history"]
        assert sig.parameters["history"].default is None
