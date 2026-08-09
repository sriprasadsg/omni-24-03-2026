"""Eval dimension: Fallback provenance (AI-SPEC Section 5, Failure Mode 5).

Code check: force the primary route to resolve to the local fallback model
and assert every surface's output carries a machine-readable
`model_provenance` beginning `"fallback:"`, and that a fallback-produced
`pass` finding is flagged `needs_review` — fallback output must never be
indistinguishable from primary-model output downstream.

Deterministic (`not llm`): `.with_fallbacks([...])` resolves silently, so
the ONLY signal the real code has is the resolved model name in the
response's `response_metadata` — this suite stubs the agent to return
messages whose metadata names the tenant's configured Ollama fallback model
(exactly what a with_fallbacks-resolved local response carries) while the
tenant's `system_settings` name a different primary, and lets the REAL
`model_provenance()` helper and each surface's real stamping/escalation
logic run unmodified.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from ai_orchestration.agents.auditor import evaluate_control
from ai_orchestration.agents.chat import chat
from ai_orchestration.agents.narrative import generate_executive
from ai_orchestration.agents.questionnaire import generate_draft
from ai_orchestration.models import model_provenance
from ai_orchestration.schemas import AuditFinding, CitedAnswer, Citation

from tests.eval_langchain.conftest import EVAL_TENANT_A_ID

pytestmark = pytest.mark.eval

_PRIMARY_MODEL = "claude-sonnet-4-6"
_FALLBACK_MODEL = "llama3.2:3b"
_LLM_SETTINGS = {"model": _PRIMARY_MODEL, "ollamaModel": _FALLBACK_MODEL}


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
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


def _make_db():
    """Mocked db: tenant llm settings name a primary + Ollama fallback (the
    comparison basis for the real `model_provenance()` call), registry/
    evidence seeded so a happy-path finding validates."""
    db = MagicMock(
        spec=[
            "system_settings",
            "compliance_frameworks",
            "control_evidence",
            "asset_compliance",
            "compliance_evidence",
            "risks",
            "tenants",
            "agent_ai_decisions",
        ]
    )
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=dict(_LLM_SETTINGS))
    db.compliance_frameworks = MagicMock()
    db.compliance_frameworks.find = MagicMock(
        return_value=_cursor([{"id": "fw-1", "controls": [{"id": "AC-1"}]}])
    )
    db.control_evidence = MagicMock()
    db.control_evidence.find_one = AsyncMock(return_value=None)
    db.asset_compliance = MagicMock()
    db.asset_compliance.find_one = AsyncMock(
        return_value={"controlId": "AC-1", "evidence": [{"id": "cev-1"}]}
    )
    db.asset_compliance.find = MagicMock(return_value=_cursor([]))
    db.compliance_evidence = MagicMock()
    db.compliance_evidence.find = MagicMock(return_value=_cursor([]))
    db.risks = MagicMock()
    db.risks.find = MagicMock(return_value=_cursor([]))
    db.tenants = MagicMock()
    db.tenants.find = MagicMock(return_value=_cursor([]))
    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)
    return db


def _fallback_messages(content="generated text"):
    """What a with_fallbacks-resolved local-model response carries: the
    fallback model's name in response_metadata."""
    return [
        SimpleNamespace(content=content, response_metadata={"model_name": _FALLBACK_MODEL})
    ]


def _agent_stub(structured_response, messages):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"structured_response": structured_response, "messages": messages}
    )
    return agent


class TestModelProvenanceHelper:
    def test_fallback_model_name_yields_fallback_marker(self):
        response = SimpleNamespace(response_metadata={"model_name": _FALLBACK_MODEL})
        assert model_provenance(response, _PRIMARY_MODEL, _FALLBACK_MODEL) == (
            f"fallback:{_FALLBACK_MODEL}"
        )

    def test_primary_model_name_yields_primary(self):
        response = SimpleNamespace(response_metadata={"model_name": _PRIMARY_MODEL})
        assert model_provenance(response, _PRIMARY_MODEL, _FALLBACK_MODEL) == "primary"

    def test_unknown_resolved_model_treated_as_fallback(self):
        response = SimpleNamespace(response_metadata={"model_name": "mystery-model"})
        assert model_provenance(response, _PRIMARY_MODEL, None).startswith("fallback:")


class TestAuditorFallbackProvenance:
    async def test_fallback_finding_carries_fallback_marker(self):
        finding = AuditFinding(
            control_id="AC-1",
            status="pass",
            rationale="MFA enforced per evidence.",
            citations=[Citation(source="mfa", chunk_id="cev-1")],
        )
        with patch(
            "ai_orchestration.agents.auditor.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.auditor.create_agent",
            MagicMock(return_value=_agent_stub(finding, _fallback_messages())),
        ):
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="MFA screenshot",
                tenant_id=EVAL_TENANT_A_ID,
                db=_make_db(),
                control_id="AC-1",
            )
        assert result.model_provenance == f"fallback:{_FALLBACK_MODEL}"
        # Failure Mode 5 escalation: a fallback-produced pass requires review.
        assert result.needs_review is True
        assert result.finding.status == "pass"

    async def test_fallback_non_pass_finding_not_escalated(self):
        finding = AuditFinding(
            control_id="AC-1",
            status="fail",
            rationale="No MFA observed.",
            citations=[Citation(source="mfa", chunk_id="cev-1")],
        )
        with patch(
            "ai_orchestration.agents.auditor.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.auditor.create_agent",
            MagicMock(return_value=_agent_stub(finding, _fallback_messages())),
        ):
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="no evidence of MFA",
                tenant_id=EVAL_TENANT_A_ID,
                db=_make_db(),
                control_id="AC-1",
            )
        assert result.model_provenance.startswith("fallback:")
        assert result.needs_review is False


class TestQuestionnaireFallbackProvenance:
    async def test_fallback_confident_draft_carries_marker_and_needs_review(self):
        answer = CitedAnswer(
            question_id="q-1",
            answer_text="Yes, MFA is enforced org-wide.",
            confidence="high",
            source_evidence_ids=["cev-1"],
        )
        retrieved = [{"id": "cev-1", "source": "mfa", "content": "MFA enforced."}]
        with patch(
            "ai_orchestration.agents.questionnaire.rag_service",
            SimpleNamespace(query=MagicMock(return_value=retrieved)),
        ), patch(
            "ai_orchestration.agents.questionnaire.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.questionnaire.create_agent",
            MagicMock(return_value=_agent_stub(answer, _fallback_messages())),
        ):
            result = await generate_draft(
                question_id="q-1",
                question_text="Is MFA enforced?",
                tenant_id=EVAL_TENANT_A_ID,
                db=_make_db(),
            )
        assert result.model_provenance == f"fallback:{_FALLBACK_MODEL}"
        assert result.needs_review is True


class TestChatFallbackProvenance:
    async def test_fallback_answer_stamps_fallback_in_decision_log(self):
        """chat() returns `{answer, sources}` without a provenance field —
        its provenance surface is the decision-log document (and the trace
        span); assert the logged `model_provenance` carries the marker."""
        db = _make_db()
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_checkpointer():
            yield MagicMock()

        with patch(
            "ai_orchestration.agents.chat.rag_service",
            SimpleNamespace(query=MagicMock(return_value=[])),
        ), patch(
            "ai_orchestration.agents.chat.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.chat.create_agent",
            MagicMock(
                return_value=MagicMock(
                    ainvoke=AsyncMock(
                        return_value={"messages": _fallback_messages("Here is your answer.")}
                    )
                )
            ),
        ), patch(
            "ai_orchestration.agents.chat.checkpointer_lifespan", _fake_checkpointer
        ):
            result = await chat(
                query="What is our posture?", tenant_id=EVAL_TENANT_A_ID, db=db
            )
        assert result["answer"] == "Here is your answer."
        db.agent_ai_decisions.insert_one.assert_awaited_once()
        logged = db.agent_ai_decisions.insert_one.await_args.args[0]
        assert logged["model_provenance"] == f"fallback:{_FALLBACK_MODEL}"


class TestNarrativeFallbackProvenance:
    async def test_fallback_narrative_carries_marker(self):
        structured = SimpleNamespace(
            text="The organization maintains a strong compliance posture overall."
        )
        with patch(
            "ai_orchestration.agents.narrative.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.narrative.create_agent",
            MagicMock(return_value=_agent_stub(structured, _fallback_messages())),
        ):
            result = await generate_executive(
                framework_name="SOC 2",
                score=87.5,
                failing_controls=["Access reviews overdue"],
                period="Q2 2026",
                tenant_id=EVAL_TENANT_A_ID,
                db=_make_db(),
            )
        assert result.model_provenance == f"fallback:{_FALLBACK_MODEL}"
        assert result.text == structured.text
