"""Phase 39-08 — hermetic unit tests for the create_agent questionnaire
draft generator (ai_orchestration/agents/questionnaire.py) and the
questionnaire_answer_draft_service.py shim.

Convention: hermetic — the agent/model call graph is stubbed
(`create_agent`/`build_model_for_tenant` patched to return canned
structured responses, mirroring test_auditor_agent.py's own convention),
and citation resolution runs for REAL against a small in-memory mocked `db`
so the `validate_citations` wiring is actually exercised, not just mocked
away. No live model/gateway/network/Chroma calls anywhere in this file.

Naming: `-k agent` selects `ai_orchestration.agents.questionnaire` tests,
`-k shim` selects `questionnaire_answer_draft_service.py` tests — matching
this plan's two per-task `<verify>` commands.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.agents.questionnaire import DraftResult, generate_draft
from ai_orchestration.schemas import Citation, CitedAnswer
from ai_orchestration.validators import FAILURE_REASON
from questionnaire_answer_draft_service import draft_answer_for_question


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    """guardrail_service.scan_and_log calls the real get_database() — patch
    it at the source (the same singleton `ai_orchestration.guardrails`
    imports) so scan_input/scan_output run for real without a live Mongo
    connection, mirroring test_auditor_agent.py's convention."""
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_KNOWN_EVIDENCE = [
    {
        "controlId": "AC-1",
        "tenantId": "tenant-a",
        "evidence": [{"id": "cev-1", "name": "mfa-screenshot"}],
    }
]

_RETRIEVED_CHUNKS = [
    {
        "id": "cev-1",
        "content": "MFA is enforced for all administrative accounts.",
        "source": "mfa-policy.pdf",
        "tenantId": "tenant-a",
        "relevance": 0.05,
    }
]


def _cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _make_db(evidence_bundles=None, other_tenants=None):
    """Minimal mocked db satisfying validate_citations' real read path
    (control_evidence.find_one, asset_compliance.find_one),
    cross_tenant_output_scan's db.tenants.find, decision_log's insert_one,
    and models' best-effort system_settings read."""
    evidence_bundles = evidence_bundles if evidence_bundles is not None else _KNOWN_EVIDENCE
    other_tenants = other_tenants if other_tenants is not None else []

    db = MagicMock(
        spec=[
            "control_evidence",
            "asset_compliance",
            "agent_ai_decisions",
            "system_settings",
            "tenants",
        ]
    )

    db.control_evidence = MagicMock()
    db.control_evidence.find_one = AsyncMock(return_value=None)

    def _resolve_asset_evidence(query):
        chunk_id = query.get("evidence.id")
        for bundle in evidence_bundles:
            if any(ev.get("id") == chunk_id for ev in bundle.get("evidence", [])):
                return bundle
        return None

    db.asset_compliance = MagicMock()
    db.asset_compliance.find_one = AsyncMock(side_effect=_resolve_asset_evidence)

    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)

    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)

    db.tenants = MagicMock()
    db.tenants.find = MagicMock(return_value=_cursor(other_tenants))

    return db


def _valid_answer(confidence="high", chunk_id="cev-1", question_id="q1"):
    return CitedAnswer(
        question_id=question_id,
        answer_text="Yes, MFA is enforced for all administrative accounts.",
        confidence=confidence,
        source_evidence_ids=["mfa-policy.pdf"],
        citations=[Citation(source="mfa-policy.pdf", chunk_id=chunk_id)],
    )


def _agent_stub(structured_response, messages=None):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"structured_response": structured_response, "messages": messages or []}
    )
    return agent


def _patched(agent, model_return=None):
    """Patch the two call-graph seams generate_draft uses to reach a model."""
    return (
        patch(
            "ai_orchestration.agents.questionnaire.build_model_for_tenant",
            AsyncMock(return_value=model_return or MagicMock()),
        ),
        patch("ai_orchestration.agents.questionnaire.create_agent", MagicMock(return_value=agent)),
    )


def _patched_rag(chunks):
    return patch(
        "ai_orchestration.agents.questionnaire.rag_service.query",
        MagicMock(return_value=chunks),
    )


# ---------------------------------------------------------------------------
# ai_orchestration/agents/questionnaire.py (-k agent)
# ---------------------------------------------------------------------------


class TestGenerateDraftAgent:
    async def test_happy_path_answerable_question_returns_valid_citedanswer(self):
        db = _make_db()
        agent = _agent_stub(_valid_answer())
        p1, p2 = _patched(agent)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2:
            result = await generate_draft(
                question_id="q1",
                question_text="Do you enforce MFA for admin accounts?",
                tenant_id="tenant-a",
                db=db,
            )

        assert isinstance(result, DraftResult)
        assert result.confidence == "high"
        assert result.source_evidence_ids == ["mfa-policy.pdf"]
        assert result.needs_review is False
        agent.ainvoke.assert_awaited_once()
        db.agent_ai_decisions.insert_one.assert_awaited_once()

    async def test_no_evidence_question_yields_insufficient_evidence_empty_ids(self):
        db = _make_db()
        agent = _agent_stub(_valid_answer())
        p1, p2 = _patched(agent)
        with _patched_rag([]), p1, p2:
            result = await generate_draft(
                question_id="q2",
                question_text="Are you SOC 3 certified?",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "insufficient_evidence"
        assert result.source_evidence_ids == []
        assert result.answer_text == ""
        # No evidence -> never invoke the model at all.
        agent.ainvoke.assert_not_awaited()

    async def test_unresolvable_citation_downgrades_to_insufficient_evidence(self):
        db = _make_db()
        # citation chunk_id "cev-does-not-exist" never resolves against db fixtures
        agent = _agent_stub(_valid_answer(chunk_id="cev-does-not-exist"))
        p1, p2 = _patched(agent)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2:
            result = await generate_draft(
                question_id="q1",
                question_text="Do you enforce MFA for admin accounts?",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "insufficient_evidence"
        assert result.reason is not None
        assert FAILURE_REASON == "citation_validation_failed"

    async def test_input_guardrail_block_skips_agent_invocation(self):
        db = _make_db()
        agent = _agent_stub(_valid_answer())
        p1, p2 = _patched(agent)
        blocked = MagicMock(passed=False, findings=["PII Detected"], reason="input_guardrail_blocked")
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2, patch(
            "ai_orchestration.agents.questionnaire.scan_input", AsyncMock(return_value=blocked)
        ):
            result = await generate_draft(
                question_id="q1",
                question_text="contains PII",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "insufficient_evidence"
        agent.ainvoke.assert_not_awaited()

    async def test_output_guardrail_block_downgrades_answer(self):
        db = _make_db()
        agent = _agent_stub(_valid_answer())
        p1, p2 = _patched(agent)
        blocked = MagicMock(passed=False, findings=["injection"], reason="output_guardrail_blocked")
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2, patch(
            "ai_orchestration.agents.questionnaire.scan_output", AsyncMock(return_value=blocked)
        ):
            result = await generate_draft(
                question_id="q1",
                question_text="Do you enforce MFA for admin accounts?",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "insufficient_evidence"

    async def test_agent_invocation_error_returns_insufficient_evidence_not_raise(self):
        db = _make_db()
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=RuntimeError("gateway down"))
        p1, p2 = _patched(agent)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2:
            result = await generate_draft(
                question_id="q1",
                question_text="Do you enforce MFA for admin accounts?",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "insufficient_evidence"
        assert result.needs_review is False

    async def test_fallback_provenance_confident_answer_flags_needs_review(self):
        db = _make_db()
        agent = _agent_stub(_valid_answer())
        p1, p2 = _patched(agent)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2, patch(
            "ai_orchestration.agents.questionnaire.model_provenance",
            return_value="fallback:llama3.2:3b",
        ):
            result = await generate_draft(
                question_id="q1",
                question_text="Do you enforce MFA for admin accounts?",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "high"
        assert result.model_provenance == "fallback:llama3.2:3b"
        assert result.needs_review is True

    async def test_no_structured_response_yields_insufficient_evidence(self):
        db = _make_db()
        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value={"structured_response": None, "messages": []})
        p1, p2 = _patched(agent)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2:
            result = await generate_draft(
                question_id="q1",
                question_text="Do you enforce MFA for admin accounts?",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.confidence == "insufficient_evidence"


# ---------------------------------------------------------------------------
# questionnaire_answer_draft_service.py shim (-k shim)
class TestReflection:
    async def test_low_confidence_draft_is_revised_when_reflection_enabled(self):
        db = _make_db()
        low = _valid_answer(confidence="low")
        revised = _valid_answer(confidence="medium")
        revised = revised.model_copy(
            update={"answer_text": "Yes — MFA is enforced for all admins per mfa-policy.pdf."}
        )
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=[
            {"structured_response": low, "messages": []},       # initial draft
            {"structured_response": revised, "messages": []},   # reflection regenerate
        ])
        critic_model = MagicMock()
        critic_model.ainvoke = AsyncMock(return_value=MagicMock(content="REVISE: cite the policy id"))
        p1, p2 = _patched(agent, model_return=critic_model)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2, patch(
            "ai_orchestration.agents.questionnaire._REFLECTION_ENABLED", True
        ), patch("ai_orchestration.agents.questionnaire._REFLECTION_MAX_ITERS", 1):
            from ai_orchestration.agents.questionnaire import generate_draft
            result = await generate_draft("q1", "Is MFA enforced?", "tenant-a", db)

        assert result.answer_text == "Yes — MFA is enforced for all admins per mfa-policy.pdf."
        assert agent.ainvoke.await_count == 2  # initial + one revision
        critic_model.ainvoke.assert_awaited_once()

    async def test_low_confidence_draft_not_revised_when_reflection_disabled(self):
        db = _make_db()
        agent = _agent_stub(_valid_answer(confidence="low"))
        p1, p2 = _patched(agent)
        with _patched_rag(_RETRIEVED_CHUNKS), p1, p2, patch(
            "ai_orchestration.agents.questionnaire._REFLECTION_ENABLED", False
        ):
            from ai_orchestration.agents.questionnaire import generate_draft
            await generate_draft("q1", "Is MFA enforced?", "tenant-a", db)
        assert agent.ainvoke.await_count == 1  # no reflection pass


# ---------------------------------------------------------------------------


def _make_shim_db():
    """Mock supporting subscript-based access
    (`db["questionnaire_answer_drafts"]`) used exclusively by the shim."""
    col = MagicMock()
    col.insert_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    return db, col


class TestQuestionnaireServiceShim:
    async def test_answerable_question_writes_pending_review_draft_with_correct_shape(self):
        db, col = _make_shim_db()
        canned = DraftResult(
            answer_text="Yes, MFA is enforced for all administrative accounts.",
            confidence="high",
            source_evidence_ids=["mfa-policy.pdf"],
            model_provenance="primary",
            needs_review=False,
            retrieved_evidence=_RETRIEVED_CHUNKS,
        )
        with patch(
            "questionnaire_answer_draft_service.generate_draft", AsyncMock(return_value=canned)
        ):
            draft = await draft_answer_for_question("q1", "Do you enforce MFA?", "tenant-a", db, "qs-1")

        col.insert_one.assert_awaited_once()
        written = col.insert_one.call_args.args[0]
        expected_keys = {
            "id", "tenantId", "questionSetId", "questionId", "questionText", "answerText",
            "original_answer_text", "confidence", "sourceEvidenceIds", "sourceEvidence",
            "status", "created_at", "updated_at",
        }
        assert expected_keys.issubset(written.keys())
        assert written["status"] == "pending_review"
        assert written["confidence"] == "high"
        assert written["answerText"] == "Yes, MFA is enforced for all administrative accounts."
        assert written["sourceEvidenceIds"] == ["mfa-policy.pdf"]
        assert written["sourceEvidence"] == [
            {"source": "mfa-policy.pdf", "content": "MFA is enforced for all administrative accounts."}
        ]
        assert draft["status"] == "pending_review"
        assert "_id" not in draft

    async def test_no_evidence_question_writes_insufficient_evidence_draft(self):
        db, col = _make_shim_db()
        canned = DraftResult(
            answer_text="",
            confidence="insufficient_evidence",
            source_evidence_ids=[],
            model_provenance="primary",
            needs_review=False,
            retrieved_evidence=[],
            reason="no_evidence_retrieved",
        )
        with patch(
            "questionnaire_answer_draft_service.generate_draft", AsyncMock(return_value=canned)
        ):
            draft = await draft_answer_for_question("q2", "Are you SOC 3 certified?", "tenant-a", db)

        written = col.insert_one.call_args.args[0]
        assert written["status"] == "pending_review"
        assert written["confidence"] == "insufficient_evidence"
        assert written["answerText"] == ""
        assert written["sourceEvidenceIds"] == []
        assert written["sourceEvidence"] == []
        assert written["reason"] == "no_evidence_retrieved"

    async def test_unresolvable_citation_downgrade_written_as_insufficient_evidence(self):
        db, col = _make_shim_db()
        canned = DraftResult(
            answer_text="Yes, MFA is enforced.",
            confidence="insufficient_evidence",
            source_evidence_ids=["mfa-policy.pdf"],
            model_provenance="primary",
            needs_review=False,
            retrieved_evidence=_RETRIEVED_CHUNKS,
            reason="citation chunk_id 'cev-x' does not resolve to tenant evidence",
        )
        with patch(
            "questionnaire_answer_draft_service.generate_draft", AsyncMock(return_value=canned)
        ):
            draft = await draft_answer_for_question("q1", "Do you enforce MFA?", "tenant-a", db)

        written = col.insert_one.call_args.args[0]
        assert written["status"] == "pending_review"
        assert written["confidence"] == "insufficient_evidence"

    async def test_draft_never_written_submitted(self):
        """No path in this module writes status='submitted' — grep-level
        guard exercised as a real assertion against the module source."""
        import inspect

        import questionnaire_answer_draft_service as shim_mod

        source = inspect.getsource(shim_mod)
        assert '"submitted"' not in source

    async def test_endpoint_facing_signature_still_works(self):
        db, col = _make_shim_db()
        canned = DraftResult(
            answer_text="Answer.",
            confidence="medium",
            source_evidence_ids=["src"],
            model_provenance="primary",
            needs_review=False,
            retrieved_evidence=[{"source": "src", "content": "c"}],
        )
        with patch(
            "questionnaire_answer_draft_service.generate_draft", AsyncMock(return_value=canned)
        ):
            # Positional call matching questionnaire_answer_draft_endpoints.py's call site.
            draft = await draft_answer_for_question("q1", "question text", "tenant-a", db, "qs-1")

        assert draft["questionId"] == "q1"
        assert draft["questionSetId"] == "qs-1"
        assert draft["tenantId"] == "tenant-a"

    def test_list_get_update_helpers_still_defined(self):
        import questionnaire_answer_draft_service as shim_mod

        assert callable(shim_mod.list_pending_drafts)
        assert callable(shim_mod.get_draft)
        assert callable(shim_mod.update_draft_status)
        assert callable(shim_mod.list_drafts)
