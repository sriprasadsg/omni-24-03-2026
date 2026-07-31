"""Phase 39-05 — hermetic unit tests for the shared agent substrate.

Covers: tenant-closed @tool factories (tools/retrieval.py, tools/evidence.py),
online guardrail hooks (guardrails.py), and the surface-discriminated
agent_ai_decisions writer (decision_log.py), incl. reader-compat proof that
the existing agentic reader ({"agent_id": ...} filter) never surfaces a
Phase 39 decision doc.

Convention: hermetic — no live model/gateway/network/ChromaDB calls.
Dependency-injected stubs/mocks throughout (mirrors test_ai_assistant.py /
test_agentic_ai.py conventions). asyncio_mode=auto (root pytest.ini) — async
def test_* functions run directly, no @pytest.mark.asyncio needed.

Naming: `-k tools` selects tool tests, `-k guardrails` selects guardrail
tests, `-k decision` selects decision-log tests — matching this plan's three
per-task `<verify>` commands.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_orchestration.tools.retrieval import NO_EVIDENCE_FOUND as NO_RAG_EVIDENCE
from ai_orchestration.tools.retrieval import make_search_evidence
from ai_orchestration.tools.evidence import NO_EVIDENCE_FOUND as NO_CONTROL_EVIDENCE
from ai_orchestration.tools.evidence import make_get_control_evidence
from ai_orchestration.guardrails import (
    GuardrailCheckResult,
    cross_tenant_output_scan,
    scan_input,
    scan_output,
)
from ai_orchestration.decision_log import log_ai_decision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RAG_HITS = [
    {"id": "doc1", "content": "Own tenant evidence chunk.", "source": "SOC2 Spec", "tenantId": "tenant-a"},
    {"id": "doc-global", "content": "Shared standard.", "source": "NIST 800-53", "tenantId": "global"},
    {"id": "doc-other", "content": "Another tenant's confidential snippet.", "source": "Internal", "tenantId": "tenant-b"},
]


def _make_cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


# ---------------------------------------------------------------------------
# tools/retrieval.py (-k tools)
# ---------------------------------------------------------------------------

class TestSearchEvidenceTools:
    def test_returns_source_id_tagged_string_and_closes_over_tenant(self):
        with patch("ai_orchestration.tools.retrieval.rag_service") as rag:
            rag.query = MagicMock(return_value=_RAG_HITS)
            tool_fn = make_search_evidence("tenant-a", n_results=5)
            result = tool_fn.invoke({"query": "access control"})

        assert "[source: SOC2 Spec | id: doc1]" in result
        assert "[source: NIST 800-53 | id: doc-global]" in result
        # Other tenant's chunk must never leak, even though the stub returned it
        assert "Another tenant's confidential snippet." not in result
        # tenant_id was passed through to rag_service.query from the closure
        rag.query.assert_called_once_with("access control", n_results=5, tenant_id="tenant-a")

    def test_returns_empty_result_string_when_no_hits(self):
        with patch("ai_orchestration.tools.retrieval.rag_service") as rag:
            rag.query = MagicMock(return_value=[])
            tool_fn = make_search_evidence("tenant-a")
            result = tool_fn.invoke({"query": "nothing matches"})

        assert result == NO_RAG_EVIDENCE

    def test_returns_empty_result_string_when_only_other_tenant_hits(self):
        with patch("ai_orchestration.tools.retrieval.rag_service") as rag:
            rag.query = MagicMock(return_value=[_RAG_HITS[2]])  # tenant-b only
            tool_fn = make_search_evidence("tenant-a")
            result = tool_fn.invoke({"query": "x"})

        assert result == NO_RAG_EVIDENCE

    def test_model_facing_args_schema_exposes_only_query(self):
        """tenant_id must never be a callable tool argument (T-39-05-A)."""
        tool_fn = make_search_evidence("tenant-a", n_results=5)
        assert set(tool_fn.args.keys()) == {"query"}
        assert "tenant_id" not in tool_fn.args


# ---------------------------------------------------------------------------
# tools/evidence.py (-k tools)
# ---------------------------------------------------------------------------

class TestGetControlEvidenceTools:
    async def test_scopes_read_by_control_and_tenant(self):
        db = MagicMock(spec=["asset_compliance"])
        records = [
            {"_id": "rec1", "assetId": "asset-1", "evidence": [{"name": "screenshot", "content": "evidence text"}]},
        ]
        db.asset_compliance = MagicMock()
        db.asset_compliance.find = MagicMock(return_value=_make_cursor(records))

        tool_fn = make_get_control_evidence("tenant-a", db)
        result = await tool_fn.ainvoke({"control_id": "AC-1"})

        called_filter = db.asset_compliance.find.call_args.args[0]
        assert called_filter == {"controlId": "AC-1", "tenantId": "tenant-a"}
        assert "[id: rec1 | asset: asset-1 | name: screenshot]" in result
        assert "evidence text" in result

    async def test_returns_no_evidence_message_when_empty(self):
        db = MagicMock(spec=["asset_compliance"])
        db.asset_compliance = MagicMock()
        db.asset_compliance.find = MagicMock(return_value=_make_cursor([]))

        tool_fn = make_get_control_evidence("tenant-a", db)
        result = await tool_fn.ainvoke({"control_id": "AC-1"})

        assert result == NO_CONTROL_EVIDENCE

    def test_model_facing_args_schema_exposes_only_control_id(self):
        db = MagicMock()
        tool_fn = make_get_control_evidence("tenant-a", db)
        assert set(tool_fn.args.keys()) == {"control_id"}
        assert "tenant_id" not in tool_fn.args


# ---------------------------------------------------------------------------
# guardrails.py (-k guardrails)
# ---------------------------------------------------------------------------

class TestGuardrailsScanInputOutput:
    async def test_scan_input_blocks_when_scan_not_passed(self):
        fake_result = MagicMock(passed=False, findings=["PII Detected: email"])
        with patch("ai_orchestration.guardrails.guardrail_service") as gs:
            gs.scan_and_log = AsyncMock(return_value=fake_result)
            result = await scan_input("my email is a@b.com", "chat")

        assert isinstance(result, GuardrailCheckResult)
        assert result.passed is False
        assert result.reason == "input_guardrail_blocked"
        gs.scan_and_log.assert_awaited_once_with("my email is a@b.com", "chat_input")

    async def test_scan_input_passes_on_clean_scan(self):
        fake_result = MagicMock(passed=True, findings=[])
        with patch("ai_orchestration.guardrails.guardrail_service") as gs:
            gs.scan_and_log = AsyncMock(return_value=fake_result)
            result = await scan_input("clean text", "chat")

        assert result.passed is True

    async def test_scan_output_blocks_when_scan_not_passed(self):
        fake_result = MagicMock(passed=False, findings=["Prompt Injection Detected: 'ignore previous instructions'"])
        with patch("ai_orchestration.guardrails.guardrail_service") as gs:
            gs.scan_and_log = AsyncMock(return_value=fake_result)
            result = await scan_output("some output", "auditor")

        assert result.passed is False
        assert result.reason == "output_guardrail_blocked"
        gs.scan_and_log.assert_awaited_once_with("some output", "auditor_output")


class TestGuardrailsCrossTenantOutputScan:
    def _db_with_tenants(self, tenants):
        db = MagicMock(spec=["tenants"])
        db.tenants = MagicMock()
        db.tenants.find = MagicMock(return_value=_make_cursor(tenants))
        return db

    async def test_blocks_planted_other_tenant_identifier(self):
        db = self._db_with_tenants([{"id": "tenant-b", "name": "Acme Corp"}])
        text = "Findings for Acme Corp show a failing control."

        result = await cross_tenant_output_scan(text, "tenant-a", db)

        assert result.passed is False
        assert result.reason == "cross_tenant_output_blocked"

    async def test_passes_clean_tenant_only_text(self):
        db = self._db_with_tenants([{"id": "tenant-b", "name": "Acme Corp"}])
        text = "Findings for the current tenant show a failing control."

        result = await cross_tenant_output_scan(text, "tenant-a", db)

        assert result.passed is True


# ---------------------------------------------------------------------------
# decision_log.py (-k decision)
# ---------------------------------------------------------------------------

class TestLogAiDecision:
    async def test_inserts_surface_discriminated_doc_without_forbidden_keys(self):
        db = MagicMock(spec=["agent_ai_decisions"])
        db.agent_ai_decisions = MagicMock()
        db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)

        await log_ai_decision(
            db,
            "auditor",
            outcome="pass",
            prompt_version="39-05.v1",
            model_provenance="primary",
            citation_validation="pass",
            ref={"control_id": "AC-1"},
        )

        db.agent_ai_decisions.insert_one.assert_awaited_once()
        doc = db.agent_ai_decisions.insert_one.call_args.args[0]
        assert doc["surface"] == "auditor"
        assert doc["source"] == "langchain"
        assert doc["control_id"] == "AC-1"
        assert "agent_id" not in doc
        assert "tool_name" not in doc
        assert "tenantId" not in doc

    async def test_swallows_insert_exception_never_raises(self):
        db = MagicMock(spec=["agent_ai_decisions"])
        db.agent_ai_decisions = MagicMock()
        db.agent_ai_decisions.insert_one = AsyncMock(side_effect=RuntimeError("mongo down"))

        # Must not raise.
        await log_ai_decision(
            db, "chat", outcome="pass", prompt_version="39-05.v1",
        )

    async def test_reader_compat_phase39_doc_invisible_to_agent_id_filter(self):
        """Proof: the existing agentic reader's {"agent_id": agent_id} filter
        (agentic_tasks_endpoints.py GET /{agent_id}/agentic-tasks/decisions)
        never matches a Phase 39 decision doc, since it carries no agent_id."""
        captured_docs = []

        async def _capture_insert(doc):
            captured_docs.append(dict(doc))

        db = MagicMock(spec=["agent_ai_decisions"])
        db.agent_ai_decisions = MagicMock()
        db.agent_ai_decisions.insert_one = AsyncMock(side_effect=_capture_insert)

        await log_ai_decision(
            db, "questionnaire", outcome="insufficient_evidence", prompt_version="39-05.v1",
            ref={"question_id": "Q-1"},
        )

        assert len(captured_docs) == 1
        phase39_doc = captured_docs[0]

        # Mirror the existing reader's exact filter shape against a mock
        # collection containing this doc plus an unrelated agentic_ai doc.
        mock_collection = [
            phase39_doc,
            {"_id": "d1", "agent_id": "agent-42", "tool_name": "quarantine_host", "source": "agentic_ai"},
        ]

        def reader_query(agent_id):
            return [d for d in mock_collection if d.get("agent_id") == agent_id]

        assert reader_query("agent-42") == [mock_collection[1]]
        assert phase39_doc not in reader_query("agent-42")
        # No agent_id path-param value (always a non-empty string in the real
        # route) can match the Phase 39 doc, since it carries no agent_id key.
        for candidate_agent_id in ("agent-42", "", "questionnaire"):
            assert phase39_doc not in reader_query(candidate_agent_id)
