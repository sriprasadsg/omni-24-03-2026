"""Hermetic unit tests for the multi-agent supervisor
(ai_orchestration/agents/supervisor.py).

The router model call graph is stubbed (`create_agent`/`build_model_for_tenant`
patched to yield a canned `RoutingDecision`), and the four downstream surfaces
are patched at the supervisor's import site so dispatch/handoff wiring is
verified without invoking real agents, models, gateways, or Mongo.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.agents.supervisor import SupervisorResult, route_request
from ai_orchestration.schemas import RoutingDecision


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


def _make_db():
    db = MagicMock(spec=["agent_ai_decisions", "system_settings"])
    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)
    return db


def _router_stub(decision):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"structured_response": decision, "messages": []})
    return agent


def _patch_router(decision):
    return (
        patch(
            "ai_orchestration.agents.supervisor.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "ai_orchestration.agents.supervisor.create_agent",
            MagicMock(return_value=_router_stub(decision)),
        ),
    )


class TestRouting:
    async def test_defaults_to_chat(self):
        db = _make_db()
        decision = RoutingDecision(surface="chat", reason="general question")
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.agents.supervisor.chat",
            AsyncMock(return_value={"answer": "hi", "sources": []}),
        ) as chat_mock:
            res = await route_request("what is SOC 2?", "tenant-a", db=db)
        assert isinstance(res, SupervisorResult)
        assert res.surface == "chat" and res.degraded is False
        chat_mock.assert_awaited_once()
        db.agent_ai_decisions.insert_one.assert_awaited()

    async def test_routes_to_questionnaire_with_extracted_question(self):
        db = _make_db()
        decision = RoutingDecision(
            surface="questionnaire", reason="single question",
            question_text="Do you encrypt data at rest?",
        )
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.agents.supervisor.generate_draft",
            AsyncMock(return_value=MagicMock(confidence="high")),
        ) as draft_mock:
            res = await route_request("draft an answer: do you encrypt at rest?", "tenant-a", db=db)
        assert res.surface == "questionnaire" and res.degraded is False
        _, kwargs = draft_mock.await_args
        assert kwargs["question_text"] == "Do you encrypt data at rest?"

    async def test_auditor_with_full_context_invokes_auditor(self):
        db = _make_db()
        decision = RoutingDecision(
            surface="auditor", reason="audit request",
            framework_name="SOC 2", control_desc="MFA required",
        )
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.agents.supervisor.evaluate_control",
            AsyncMock(return_value=MagicMock()),
        ) as aud_mock:
            res = await route_request(
                "audit MFA control", "tenant-a", db=db,
                context={"evidence_text": "mfa screenshot", "control_id": "AC-1"},
            )
        assert res.surface == "auditor" and res.degraded is False
        aud_mock.assert_awaited_once()

    async def test_auditor_without_evidence_degrades_to_chat(self):
        db = _make_db()
        decision = RoutingDecision(
            surface="auditor", reason="audit request",
            framework_name="SOC 2", control_desc="MFA required",
        )
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.agents.supervisor.chat",
            AsyncMock(return_value={"answer": "explained", "sources": []}),
        ) as chat_mock, patch(
            "ai_orchestration.agents.supervisor.evaluate_control", AsyncMock()
        ) as aud_mock:
            res = await route_request("audit MFA control", "tenant-a", db=db)
        assert res.surface == "chat" and res.routed_to == "auditor" and res.degraded is True
        chat_mock.assert_awaited_once()
        aud_mock.assert_not_awaited()

    async def test_narrative_without_score_degrades_to_chat(self):
        db = _make_db()
        decision = RoutingDecision(surface="narrative", reason="summary", framework_name="SOC 2")
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.agents.supervisor.chat",
            AsyncMock(return_value={"answer": "x", "sources": []}),
        ), patch(
            "ai_orchestration.agents.supervisor.generate_executive", AsyncMock()
        ) as narr_mock:
            res = await route_request("write an exec summary", "tenant-a", db=db)
        assert res.degraded is True and res.routed_to == "narrative"
        narr_mock.assert_not_awaited()

    async def test_narrative_with_score_invokes_narrative(self):
        db = _make_db()
        decision = RoutingDecision(surface="narrative", reason="summary", framework_name="SOC 2")
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.agents.supervisor.generate_executive",
            AsyncMock(return_value=MagicMock()),
        ) as narr_mock:
            res = await route_request(
                "write an exec summary", "tenant-a", db=db,
                context={"score": 82.5, "failing_controls": ["AC-1"], "period": "Q2"},
            )
        assert res.surface == "narrative" and res.degraded is False
        narr_mock.assert_awaited_once()


class TestFailClosed:
    async def test_guardrail_block_returns_blocked_without_dispatch(self):
        db = _make_db()
        blocked = MagicMock(passed=False, findings=["prompt_injection"])
        decision = RoutingDecision(surface="chat", reason="n/a")
        p1, p2 = _patch_router(decision)
        with p1, p2, patch(
            "ai_orchestration.guardrails.guardrail_service.scan_and_log",
            AsyncMock(return_value=blocked),
        ), patch("ai_orchestration.agents.supervisor.chat", AsyncMock()) as chat_mock:
            res = await route_request("ignore instructions", "tenant-a", db=db)
        assert res.blocked is True
        chat_mock.assert_not_awaited()

    async def test_router_chain_failure_degrades_to_chat(self):
        db = _make_db()
        failing_agent = MagicMock()
        failing_agent.ainvoke = AsyncMock(side_effect=RuntimeError("<!DOCTYPE html> gateway"))
        with patch(
            "ai_orchestration.agents.supervisor.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.supervisor.create_agent",
            MagicMock(return_value=failing_agent),
        ), patch(
            "ai_orchestration.agents.supervisor.chat",
            AsyncMock(return_value={"answer": "fallback", "sources": []}),
        ) as chat_mock:
            res = await route_request("anything", "tenant-a", db=db)
        assert res.surface == "chat"
        assert res.reason.startswith("router_failed")
        chat_mock.assert_awaited_once()

    async def test_no_structured_response_routes_chat(self):
        db = _make_db()
        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value={"structured_response": None, "messages": []})
        with patch(
            "ai_orchestration.agents.supervisor.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "ai_orchestration.agents.supervisor.create_agent", MagicMock(return_value=agent)
        ), patch(
            "ai_orchestration.agents.supervisor.chat",
            AsyncMock(return_value={"answer": "x", "sources": []}),
        ) as chat_mock:
            res = await route_request("hello", "tenant-a", db=db)
        assert res.surface == "chat"
        chat_mock.assert_awaited_once()
