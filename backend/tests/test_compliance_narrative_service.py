"""
Unit tests for Phase 13 AI Compliance Narrative Service.
Tests: compliance_narrative_service.py
Pattern: asyncio.get_event_loop().run_until_complete() + AsyncMock (NO pytest-asyncio).
RED phase: Tests 1-7 fail with ImportError (compliance_narrative_service.py does not exist yet).
           Test 8 fails with AssertionError (_build_pdf does not yet render narrative text).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError


# ===========================================================================
# Test 1 — AI-05: generate_executive_summary returns str within 150 words
# ===========================================================================

class TestGenerateExecutiveSummary:
    def test_returns_str_on_success(self):
        async def run():
            with patch("compliance_narrative_service.ai_service") as mock_svc:
                mock_svc.generate_text = AsyncMock(
                    return_value="The SOC 2 compliance posture is sound."
                )
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=["CC6.1"],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert isinstance(result, str)
        assert len(result.split()) <= 150


# ===========================================================================
# Test 2 — AI-05: _trim_to_words enforces 150-word budget
# ===========================================================================

class TestWordBudget:
    def test_trims_to_150_words(self):
        async def run():
            with patch("compliance_narrative_service.ai_service") as mock_svc:
                mock_svc.generate_text = AsyncMock(
                    return_value=" ".join(["word"] * 200)
                )
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=[],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert len(result.split()) <= 150


# ===========================================================================
# Test 3 — AI-06: Error: prefix returns fallback, never raises
# ===========================================================================

class TestFallbackOnError:
    def test_returns_fallback_on_error_prefix(self):
        async def run():
            with patch("compliance_narrative_service.ai_service") as mock_svc:
                mock_svc.generate_text = AsyncMock(return_value="Error: API timeout")
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=[],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert isinstance(result, str)
        assert result != "Error: API timeout"


# ===========================================================================
# Test 4 — AI-06: BLOCKED: prefix returns fallback, never raises
# ===========================================================================

class TestFallbackOnBlocked:
    def test_returns_fallback_on_blocked_prefix(self):
        async def run():
            with patch("compliance_narrative_service.ai_service") as mock_svc:
                mock_svc.generate_text = AsyncMock(
                    return_value="BLOCKED: PII detected in output"
                )
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=[],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
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
            with patch("compliance_narrative_service.ai_service") as mock_svc:
                mock_svc.generate_text = AsyncMock(
                    return_value=" ".join(["word"] * 250)
                )
                from compliance_narrative_service import generate_framework_narrative
                result = await generate_framework_narrative(
                    framework_name="ISO 27001",
                    score=72.0,
                    failing_controls=["A.9.4.1", "A.12.6.1"],
                    remediation_summary=None,
                )
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert len(result.split()) <= 200


# ===========================================================================
# Test 8 — AI-05/AI-06: _build_pdf embeds narrative, not in metrics table
#
# RED: fails AssertionError — _build_pdf does not yet render ai_executive_summary
#      (b"Exec summary text." assertion fails until Task 3 wires _render_narratives).
# GREEN (after Task 3): pdf contains narrative text and narrative key is NOT a table row.
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
        pdf_bytes = _build_pdf(report_data)
        assert pdf_bytes is not None
        assert isinstance(pdf_bytes, bytes)
        # Narrative key must NOT appear as a metrics table row label
        assert b"Ai Executive Summary" not in pdf_bytes
        # Narrative text MUST appear in the PDF as a rendered narrative section
        assert b"Exec summary text." in pdf_bytes
