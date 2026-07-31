"""Phase 39-09 — hermetic unit tests for the create_agent narrative surface
(ai_orchestration/agents/narrative.py) and the compliance_narrative_service.py
shim.

Convention: hermetic — the agent/model call graph is stubbed
(`create_agent`/`build_model_for_tenant` patched to return canned structured
responses, per this plan's own action text), mirroring
test_auditor_agent.py's / test_questionnaire_agent.py's conventions. No live
model/gateway/network/Mongo calls anywhere in this file.

Naming: `-k agent` selects `ai_orchestration.agents.narrative` tests,
`-k shim` selects `compliance_narrative_service.py` tests — matching this
plan's two per-task `<verify>` commands.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.agents.narrative import (
    NarrativeResult,
    _fallback_executive_summary,
    _fallback_framework_narrative,
    generate_executive,
    generate_framework,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_KNOWN_FRAMEWORK = {
    "id": "fw-1",
    "controls": [{"id": "AC-1", "name": "Access Control"}],
}


def _cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _make_db(frameworks=None):
    """Minimal mocked db satisfying validate_framework_fidelity's read path
    (compliance_frameworks.find), decision_log's insert_one, guardrails'
    cross_tenant_output_scan (tenants.find), and models' best-effort
    system_settings read."""
    frameworks = frameworks if frameworks is not None else [_KNOWN_FRAMEWORK]

    db = MagicMock(
        spec=["compliance_frameworks", "tenants", "agent_ai_decisions", "system_settings"]
    )
    db.compliance_frameworks = MagicMock()
    db.compliance_frameworks.find = MagicMock(return_value=_cursor(frameworks))

    db.tenants = MagicMock()
    db.tenants.find = MagicMock(return_value=_cursor([]))

    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)

    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)

    return db


def _structured(text):
    structured = MagicMock()
    structured.text = text
    return structured


def _agent_stub(text, messages=None):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"structured_response": _structured(text), "messages": messages or []}
    )
    return agent


def _patched(agent):
    """Patch the two call-graph seams generate_executive/generate_framework
    use to reach a model."""
    return (
        patch(
            "ai_orchestration.agents.narrative.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("ai_orchestration.agents.narrative.create_agent", MagicMock(return_value=agent)),
    )


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    """guardrail_service.scan_and_log calls the real get_database() — patch
    it at the source so scan_input/scan_output run for real without a live
    Mongo connection, mirroring test_auditor_agent.py's convention."""
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


# ---------------------------------------------------------------------------
# ai_orchestration/agents/narrative.py (-k agent)
# ---------------------------------------------------------------------------


class TestNarrativeAgent:
    async def test_valid_generation_within_budget_returns_text(self):
        db = _make_db()
        agent = _agent_stub("SOC 2 posture is strong across all sampled controls this period.")
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_executive(
                framework_name="SOC 2",
                score=91.2,
                failing_controls=["CC6.1"],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert isinstance(result, NarrativeResult)
        assert result.fallback_used is False
        assert result.text == "SOC 2 posture is strong across all sampled controls this period."
        agent.ainvoke.assert_awaited_once()
        db.agent_ai_decisions.insert_one.assert_awaited_once()

    async def test_over_budget_executive_generation_returns_fallback(self):
        db = _make_db()
        agent = _agent_stub(" ".join(["word"] * 200))  # exceeds 150-word executive budget
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_executive(
                framework_name="SOC 2",
                score=80.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        assert result.text == _fallback_executive_summary("SOC 2", 80.0)
        assert len(result.text.split()) <= 150

    async def test_over_budget_framework_generation_returns_fallback(self):
        db = _make_db()
        agent = _agent_stub(" ".join(["word"] * 250))  # exceeds 200-word framework budget
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_framework(
                framework_name="ISO 27001",
                score=72.0,
                failing_controls=["A.9.4.1"],
                remediation_summary=None,
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        assert result.text == _fallback_framework_narrative("ISO 27001", 72.0)
        assert len(result.text.split()) <= 200

    async def test_framework_budget_allows_more_words_than_executive_budget(self):
        # 180 words: exceeds the 150-word executive budget but is within the
        # 200-word framework budget — proves the two call sites use distinct
        # budgets, not a single shared ceiling.
        db = _make_db()
        text = " ".join(["finding"] * 180)
        agent = _agent_stub(text)
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_framework(
                framework_name="ISO 27001",
                score=72.0,
                failing_controls=[],
                remediation_summary=None,
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is False
        assert result.text == text

    async def test_blocked_output_returns_fallback(self):
        db = _make_db()
        agent = _agent_stub("BLOCKED: PII detected in output")
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_executive(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        assert not result.text.startswith("BLOCKED:")

    async def test_error_output_returns_fallback(self):
        db = _make_db()
        agent = _agent_stub("Error: API timeout")
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_framework(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                remediation_summary=None,
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        assert not result.text.startswith("Error:")

    async def test_unregistered_control_id_token_downgrades_to_fallback(self):
        # "AC-99" is control-ID-shaped but absent from the seeded registry
        # (only AC-1 is known) — framework-fidelity sweep must flag it.
        db = _make_db()
        agent = _agent_stub("Control AC-99 was reviewed and found compliant this period.")
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_executive(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        assert result.text == _fallback_executive_summary("SOC 2", 85.0)

    async def test_known_control_id_token_does_not_trigger_fallback(self):
        # "AC-1" IS in the seeded registry — must not be flagged.
        db = _make_db()
        agent = _agent_stub("Control AC-1 was reviewed and found compliant this period.")
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_executive(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is False
        assert "AC-1" in result.text

    async def test_agent_invocation_error_returns_fallback_not_raise(self):
        db = _make_db()
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=RuntimeError("gateway down"))
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await generate_executive(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        assert result.text == _fallback_executive_summary("SOC 2", 85.0)

    async def test_input_guardrail_block_skips_agent_invocation(self):
        db = _make_db()
        agent = _agent_stub("some narrative text")
        p1, p2 = _patched(agent)
        blocked = MagicMock(passed=False, findings=["PII Detected"], reason="input_guardrail_blocked")
        with p1, p2, patch(
            "ai_orchestration.agents.narrative.scan_input", AsyncMock(return_value=blocked)
        ):
            result = await generate_executive(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True
        agent.ainvoke.assert_not_awaited()

    async def test_output_guardrail_block_returns_fallback(self):
        db = _make_db()
        agent = _agent_stub("some narrative text")
        p1, p2 = _patched(agent)
        blocked = MagicMock(passed=False, findings=["injection"], reason="output_guardrail_blocked")
        with p1, p2, patch(
            "ai_orchestration.agents.narrative.scan_output", AsyncMock(return_value=blocked)
        ):
            result = await generate_framework(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                remediation_summary=None,
                tenant_id="tenant-a",
                db=db,
            )

        assert result.fallback_used is True

    async def test_sanitise_strips_prompt_injection_characters(self):
        from ai_orchestration.agents.narrative import _sanitise

        result = _sanitise("foo<bar>{baz}[qux]\\evil\nnewline")
        for char in "<>{}[]\\":
            assert char not in result
        assert "\n" not in result


# ---------------------------------------------------------------------------
# compliance_narrative_service.py shim (-k shim)
# ---------------------------------------------------------------------------


class TestNarrativeServiceShim:
    async def test_generate_executive_summary_returns_str(self):
        from compliance_narrative_service import generate_executive_summary

        canned = NarrativeResult(text="Exec summary text.", model_provenance="primary", fallback_used=False)
        with patch(
            "compliance_narrative_service.generate_executive",
            AsyncMock(return_value=canned),
        ):
            result = await generate_executive_summary(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=["CC6.1"],
                period="2026-06-01 to 2026-06-23",
                tenant_id="tenant-a",
                db=MagicMock(),
            )

        assert isinstance(result, str)
        assert result == "Exec summary text."

    async def test_generate_framework_narrative_returns_str(self):
        from compliance_narrative_service import generate_framework_narrative

        canned = NarrativeResult(text="Framework narrative text.", model_provenance="primary", fallback_used=False)
        with patch(
            "compliance_narrative_service.generate_framework",
            AsyncMock(return_value=canned),
        ):
            result = await generate_framework_narrative(
                framework_name="ISO 27001",
                score=72.0,
                failing_controls=["A.9.4.1"],
                remediation_summary=None,
                tenant_id="tenant-a",
                db=MagicMock(),
            )

        assert isinstance(result, str)
        assert result == "Framework narrative text."

    async def test_ambient_tenant_and_db_resolved_when_not_supplied(self):
        from compliance_narrative_service import generate_executive_summary

        canned = NarrativeResult(text="Exec summary text.", model_provenance="primary", fallback_used=False)
        fake_db = MagicMock()
        mock_generate_executive = AsyncMock(return_value=canned)
        with patch(
            "compliance_narrative_service.generate_executive", mock_generate_executive
        ), patch(
            "compliance_narrative_service.get_tenant_id", MagicMock(return_value="ambient-tenant")
        ), patch(
            "database.get_database", MagicMock(return_value=fake_db)
        ):
            result = await generate_executive_summary(
                framework_name="SOC 2",
                score=85.0,
                failing_controls=[],
                period="2026-06-01 to 2026-06-23",
            )

        assert result == "Exec summary text."
        mock_generate_executive.assert_awaited_once()
        call_kwargs = mock_generate_executive.await_args
        # Positional args: (framework_name, score, failing_controls, period, tenant_id, db)
        assert call_kwargs.args[4] == "ambient-tenant"
        assert call_kwargs.args[5] is fake_db

    async def test_enrich_report_data_populates_ai_fields(self):
        from compliance_narrative_service import enrich_report_data

        exec_canned = NarrativeResult(text="Exec summary.", model_provenance="primary", fallback_used=False)
        fw_canned = NarrativeResult(text="Framework narrative.", model_provenance="primary", fallback_used=False)

        db = MagicMock()
        db._db = MagicMock()
        db._db.compliance_frameworks = MagicMock()
        db._db.compliance_frameworks.find = MagicMock(return_value=_cursor([_KNOWN_FRAMEWORK]))
        db.asset_compliance = MagicMock()
        db.asset_compliance.find = MagicMock(return_value=_cursor([]))

        data = {
            "frameworks": [{"name": "SOC 2", "score": 88.0}],
            "period_start": "2026-06-01",
            "period_end": "2026-06-23",
        }

        with patch(
            "compliance_narrative_service.generate_executive", AsyncMock(return_value=exec_canned)
        ), patch(
            "compliance_narrative_service.generate_framework", AsyncMock(return_value=fw_canned)
        ):
            await enrich_report_data(data, db, "tenant-a")

        assert data["ai_executive_summary"] == "Exec summary."
        assert data["ai_framework_narratives"] == {"SOC 2": "Framework narrative."}

    async def test_enrich_report_data_falls_back_on_unexpected_exception(self):
        from compliance_narrative_service import enrich_report_data

        db = MagicMock()
        db._db = MagicMock()
        db._db.compliance_frameworks = MagicMock()
        db._db.compliance_frameworks.find = MagicMock(return_value=_cursor([_KNOWN_FRAMEWORK]))
        db.asset_compliance = MagicMock()
        db.asset_compliance.find = MagicMock(return_value=_cursor([]))

        data = {
            "frameworks": [{"name": "SOC 2", "score": 88.0}],
            "period_start": "2026-06-01",
            "period_end": "2026-06-23",
        }

        with patch(
            "compliance_narrative_service.generate_executive",
            AsyncMock(side_effect=RuntimeError("unexpected")),
        ):
            await enrich_report_data(data, db, "tenant-a")

        assert isinstance(data["ai_executive_summary"], str)
        assert data["ai_executive_summary"]
