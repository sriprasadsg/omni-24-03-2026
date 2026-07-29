"""
Unit tests for Phase 13 AI Compliance Narrative Service.
Tests: compliance_narrative_service.py
Pattern: asyncio.run() + AsyncMock (NO pytest-asyncio).
Pattern: asyncio.run() isolates each test from prior event-loop state — order-independent.
           Test 8 fails with AssertionError (_build_pdf does not yet render narrative text).

Phase 39-09 rewired `compliance_narrative_service.py` as a thin shim
delegating to `ai_orchestration.agents.narrative` (a `create_agent`-based
agent) — `compliance_narrative_service.ai_service` no longer exists, so
Tests 1-4/7 below are retargeted onto the new boundary
(`ai_orchestration.agents.narrative.build_model_for_tenant`/`create_agent`,
mirroring `test_auditor_agent.py`'s/`test_ai_assistant.py`'s conventions)
instead of the old `ai_service.generate_text` mock. The behavioral contract
these tests assert — `str` return, word-budget enforcement, fail-closed
fallback on BLOCKED:/Error: output — is unchanged (39-CONTEXT.md).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError


def _stub_cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _stub_db():
    """Minimal mocked db satisfying agents/narrative.py's read path:
    guardrails.cross_tenant_output_scan (tenants.find), decision_log
    (agent_ai_decisions.insert_one), models._tenant_model_names
    (system_settings.find_one — only reached when tenant_id is truthy)."""
    db = MagicMock(spec=["tenants", "agent_ai_decisions", "system_settings"])
    db.tenants = MagicMock()
    db.tenants.find = MagicMock(return_value=_stub_cursor([]))
    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)
    return db


def _narrative_agent_patches(text):
    """Patch the call-graph seams `generate_executive_summary`/
    `generate_framework_narrative` -> `ai_orchestration.agents.narrative`
    traverse to reach a model, without any live model/gateway/Mongo call —
    mirrors test_narrative_agent.py's `_patched`."""
    structured = MagicMock()
    structured.text = text
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"structured_response": structured, "messages": []})
    return (
        patch(
            "ai_orchestration.agents.narrative.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("ai_orchestration.agents.narrative.create_agent", MagicMock(return_value=agent)),
        patch(
            "ai_orchestration.guardrails.guardrail_service.scan_and_log",
            AsyncMock(return_value=MagicMock(passed=True, findings=[])),
        ),
        patch("compliance_narrative_service.get_tenant_id", MagicMock(return_value=None)),
        patch("database.get_database", MagicMock(return_value=_stub_db())),
    )


# ===========================================================================
# Test 1 — AI-05: generate_executive_summary returns str within 150 words
# ===========================================================================

class TestGenerateExecutiveSummary:
    def test_returns_str_on_success(self):
        async def run():
            p1, p2, p3, p4, p5 = _narrative_agent_patches(
                "The SOC 2 compliance posture is sound."
            )
            with p1, p2, p3, p4, p5:
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=["CC6.1"],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.run(run())
        assert isinstance(result, str)
        assert len(result.split()) <= 150


# ===========================================================================
# Test 2 — AI-05: _trim_to_words enforces 150-word budget
# ===========================================================================

class TestWordBudget:
    def test_trims_to_150_words(self):
        async def run():
            p1, p2, p3, p4, p5 = _narrative_agent_patches(" ".join(["word"] * 200))
            with p1, p2, p3, p4, p5:
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=[],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.run(run())
        assert len(result.split()) <= 150


# ===========================================================================
# Test 3 — AI-06: Error: prefix returns fallback, never raises
# ===========================================================================

class TestFallbackOnError:
    def test_returns_fallback_on_error_prefix(self):
        async def run():
            p1, p2, p3, p4, p5 = _narrative_agent_patches("Error: API timeout")
            with p1, p2, p3, p4, p5:
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=[],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.run(run())
        assert isinstance(result, str)
        assert result != "Error: API timeout"


# ===========================================================================
# Test 4 — AI-06: BLOCKED: prefix returns fallback, never raises
# ===========================================================================

class TestFallbackOnBlocked:
    def test_returns_fallback_on_blocked_prefix(self):
        async def run():
            p1, p2, p3, p4, p5 = _narrative_agent_patches("BLOCKED: PII detected in output")
            with p1, p2, p3, p4, p5:
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=[],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.run(run())
        assert isinstance(result, str)
        assert not result.startswith("BLOCKED:")


# ===========================================================================
# Test 5 — AI-06: _sanitise strips prompt-injection characters
# ===========================================================================

class TestSanitise:
    def test_strips_unsafe_chars(self):
        from compliance_narrative_service import _sanitise

        result = _sanitise("foo<bar>{baz}[qux]\\evil")
        assert "<" not in result
        assert ">" not in result
        assert "{" not in result
        assert "}" not in result
        assert "[" not in result
        assert "]" not in result
        assert "\\" not in result


# ===========================================================================
# Test 6 — AI-06: NarrativeOutput.from_raw raises ValidationError on empty
# ===========================================================================

class TestNarrativeOutput:
    def test_from_raw_raises_on_empty(self):
        from compliance_narrative_service import NarrativeOutput

        with pytest.raises(ValidationError):
            NarrativeOutput.from_raw("")


# ===========================================================================
# Test 7 — AI-06: generate_framework_narrative enforces 200-word budget
# ===========================================================================

class TestFrameworkNarrative:
    def test_framework_narrative_within_200_words(self):
        async def run():
            p1, p2, p3, p4, p5 = _narrative_agent_patches(" ".join(["word"] * 250))
            with p1, p2, p3, p4, p5:
                from compliance_narrative_service import generate_framework_narrative
                result = await generate_framework_narrative(
                    framework_name="ISO 27001",
                    score=72.0,
                    failing_controls=["A.9.4.1", "A.12.6.1"],
                    remediation_summary=None,
                )
            return result

        result = asyncio.run(run())
        assert len(result.split()) <= 200


# ===========================================================================
# Test 8 — AI-05/AI-06: _build_pdf delegates narrative rendering to _render_narratives
#
# RED: fails AttributeError — scheduled_reports_service._render_narratives does not
#      exist yet (Task 3 import not wired).
# GREEN (after Task 3): _build_pdf calls _render_narratives twice (executive + frameworks)
#      and returns valid PDF bytes. PDF content is FlateDecode-compressed so text is not
#      directly searchable as raw bytes; call-count is the authoritative assertion.
# ===========================================================================

class TestBuildPdfIntegration:
    def test_narrative_not_in_metrics_table(self):
        from scheduled_reports_service import _build_pdf

        report_data = {
            "report_type": "compliance_summary",
            "report_name": "Test",
            "generated_at": "2026-06-23T00:00:00Z",
            "tenant_id": "t1",
            "period_start": "2026-06-16T00:00:00Z",
            "period_end": "2026-06-23T00:00:00Z",
            "ai_executive_summary": "Exec summary text.",
            "ai_framework_narratives": {"SOC 2": "Framework narrative text."},
            "top_failing_controls": ["CC6.1"],
        }
        with patch("scheduled_reports_service._render_narratives") as mock_render:
            pdf_bytes = _build_pdf(report_data)

        assert pdf_bytes is not None and isinstance(pdf_bytes, bytes)
        assert mock_render.call_count == 2, (
            f"_render_narratives must be called twice in _build_pdf "
            f"(section='executive' before table, section='frameworks' after); "
            f"was called {mock_render.call_count} times"
        )
        sections = [
            c.kwargs.get("section") or (c.args[3] if len(c.args) > 3 else None)
            for c in mock_render.call_args_list
        ]
        assert "executive" in sections
        assert "frameworks" in sections
