"""
Unit tests for Phase 12 Agentic AI integration.

Tests: agentic_service.py and agentic_tasks_endpoints.py
Test pattern: synchronous TestClient + AsyncMock (NO pytest-asyncio).
Async unit tests on AgenticService use asyncio.get_event_loop().run_until_complete().

All 8 tests must FAIL (ImportError) before implementation files exist (RED phase).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ===========================================================================
# Test 1 — AI-02: TOOLS list and TOOL_REGISTRY completeness
# ===========================================================================

class TestToolRegistryComplete:
    """All five security capability tools must be present in TOOLS and TOOL_REGISTRY."""

    def test_tool_registry_complete(self):
        from agentic_service import TOOLS, TOOL_REGISTRY

        # Exactly 5 tools
        assert len(TOOLS) == 5, f"Expected 5 tools, got {len(TOOLS)}"

        required_names = {
            "run_compliance_check",
            "run_vulnerability_scan",
            "run_threat_hunt",
            "run_persistence_scan",
            "collect_processes",
        }

        # Each tool dict has required keys
        for tool in TOOLS:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool missing 'description': {tool}"
            assert "input_schema" in tool, f"Tool missing 'input_schema': {tool}"

        # TOOLS names match required set
        tools_names = {t["name"] for t in TOOLS}
        assert tools_names == required_names, f"TOOLS names mismatch: {tools_names}"

        # TOOL_REGISTRY keys exactly match TOOLS names
        assert set(TOOL_REGISTRY.keys()) == required_names, (
            f"TOOL_REGISTRY keys mismatch: {set(TOOL_REGISTRY.keys())}"
        )

        # Each name in required set is a key in TOOL_REGISTRY
        for name in required_names:
            assert name in TOOL_REGISTRY, f"Missing from TOOL_REGISTRY: {name}"


# ===========================================================================
# Test 2 — AI-01: run() calls AsyncAnthropic with tool_choice={"type": "any"}
# ===========================================================================

class TestRunCallsAnthropicWithToolChoiceAny:
    """AgenticService.run() must call messages.create twice (Turn 1 + Turn 2)
    with tool_choice={"type": "any"} on Turn 1."""

    def test_run_calls_anthropic_with_tool_choice_any(self):
        # Build Turn 1 mock response
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.id = "tu-abc"
        tool_use_block.name = "run_compliance_check"
        tool_use_block.input = {"agent_id": "agt-1"}

        turn1_response = MagicMock()
        turn1_response.stop_reason = "tool_use"
        turn1_response.content = [tool_use_block]

        # Build Turn 2 mock response
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Compliance evidence is stale."

        turn2_response = MagicMock()
        turn2_response.content = [text_block]

        mock_create = AsyncMock(side_effect=[turn1_response, turn2_response])
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = mock_create

        mock_anthropic_cls = MagicMock(return_value=mock_client_instance)

        # Mock db
        mock_db = MagicMock()
        mock_db.agent_ai_decisions.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="fake-id")
        )
        mock_db.agent_instructions.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="fake-id")
        )

        with patch("agentic_service.AsyncAnthropic", mock_anthropic_cls), \
             patch("agentic_service.get_database", return_value=mock_db):
            from agentic_service import AgenticService
            svc = AgenticService(api_key="test")

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                svc.run("agt-1", {"agent_id": "agt-1", "findings": []})
            )

        # messages.create called twice
        assert mock_create.call_count == 2, (
            f"Expected 2 calls to messages.create, got {mock_create.call_count}"
        )

        # First call had tool_choice={"type": "any"}
        first_call_kwargs = mock_create.call_args_list[0].kwargs
        assert first_call_kwargs.get("tool_choice") == {"type": "any"}, (
            f"Expected tool_choice={{'type': 'any'}}, got {first_call_kwargs.get('tool_choice')}"
        )

        # Result has correct tool_name
        assert result["tool_name"] == "run_compliance_check", (
            f"Expected tool_name='run_compliance_check', got {result.get('tool_name')}"
        )


# ===========================================================================
# Test 3 — AI-01, AI-04: stop_reason != "tool_use" triggers fallback
# ===========================================================================

class TestStopReasonGuardTriggersFallback:
    """When Turn 1 returns stop_reason='end_turn', rule-based fallback activates."""

    def test_stop_reason_guard_triggers_fallback(self):
        # Turn 1: stop_reason="end_turn" (no tool_use)
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I recommend running a compliance check."

        turn1_response = MagicMock()
        turn1_response.stop_reason = "end_turn"
        turn1_response.content = [text_block]

        mock_create = AsyncMock(return_value=turn1_response)
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = mock_create

        mock_anthropic_cls = MagicMock(return_value=mock_client_instance)

        # Mock db — capture insert_one call
        mock_insert = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
        mock_db = MagicMock()
        mock_db.agent_ai_decisions.insert_one = mock_insert
        mock_db.agent_instructions.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="fake-id")
        )

        with patch("agentic_service.AsyncAnthropic", mock_anthropic_cls), \
             patch("agentic_service.get_database", return_value=mock_db):
            from agentic_service import AgenticService
            svc = AgenticService(api_key="test")

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                svc.run("agt-1", {"agent_id": "agt-1", "findings": []})
            )

        # Must be rule_based_fallback
        assert result["source"] == "rule_based_fallback", (
            f"Expected source='rule_based_fallback', got {result.get('source')}"
        )

        # audit write called once with source=rule_based_fallback
        assert mock_insert.call_count == 1, (
            f"Expected 1 insert_one call, got {mock_insert.call_count}"
        )
        inserted_doc = mock_insert.call_args[0][0]
        assert inserted_doc.get("source") == "rule_based_fallback", (
            f"Expected doc source='rule_based_fallback', got {inserted_doc.get('source')}"
        )


# ===========================================================================
# Test 4 — AI-02: Hallucinated tool name triggers fallback
# ===========================================================================

class TestHallucinatedToolRejected:
    """A tool name not in TOOL_REGISTRY must cause rule-based fallback (not 500)."""

    def test_hallucinated_tool_rejected(self):
        # Turn 1: stop_reason="tool_use" but hallucinated name
        bad_block = MagicMock()
        bad_block.type = "tool_use"
        bad_block.id = "tu-bad"
        bad_block.name = "run_malware_scan"
        bad_block.input = {"agent_id": "agt-1"}

        turn1_response = MagicMock()
        turn1_response.stop_reason = "tool_use"
        turn1_response.content = [bad_block]

        mock_create = AsyncMock(return_value=turn1_response)
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = mock_create

        mock_anthropic_cls = MagicMock(return_value=mock_client_instance)

        mock_db = MagicMock()
        mock_db.agent_ai_decisions.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="fake-id")
        )
        mock_db.agent_instructions.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="fake-id")
        )

        with patch("agentic_service.AsyncAnthropic", mock_anthropic_cls), \
             patch("agentic_service.get_database", return_value=mock_db):
            from agentic_service import AgenticService
            svc = AgenticService(api_key="test")

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                svc.run("agt-1", {"agent_id": "agt-1"})
            )

        assert result["source"] == "rule_based_fallback", (
            f"Expected source='rule_based_fallback' for hallucinated tool, got {result.get('source')}"
        )


# ===========================================================================
# Test 5 — AI-02: Pydantic validation rejects bad tool_name
# ===========================================================================

class TestPydanticValidationRejectsBadInput:
    """AgenticDecision must reject tool names not in the Literal enum."""

    def test_pydantic_validation_rejects_bad_input(self):
        from pydantic import ValidationError
        from agentic_service import AgenticDecision

        # Bad tool name must raise ValidationError
        with pytest.raises(Exception) as exc_info:
            AgenticDecision.model_validate({"tool_name": "run_malware_scan", "agent_id": "agt-1"})
        # Must be a pydantic ValidationError
        assert "ValidationError" in type(exc_info.value).__name__ or isinstance(
            exc_info.value, ValidationError
        ), f"Expected ValidationError, got {type(exc_info.value)}"

        # Valid tool name must succeed
        decision = AgenticDecision.model_validate(
            {"tool_name": "run_compliance_check", "agent_id": "agt-1"}
        )
        assert decision.tool_name == "run_compliance_check"


# ===========================================================================
# Test 6 — AI-03: _log_decision() writes all required fields
# ===========================================================================

class TestLogDecisionWritesRequiredFields:
    """_log_decision() must write a doc with all required non-null fields."""

    def test_log_decision_writes_required_fields(self):
        mock_insert = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
        mock_db = MagicMock()
        mock_db.agent_ai_decisions.insert_one = mock_insert

        mock_anthropic_cls = MagicMock()
        mock_anthropic_cls.return_value = MagicMock()

        with patch("agentic_service.AsyncAnthropic", mock_anthropic_cls), \
             patch("agentic_service.get_database", return_value=mock_db):
            from agentic_service import AgenticService
            svc = AgenticService(api_key="test")

            result_payload = {
                "tool_name": "run_threat_hunt",
                "tool_input": {"agent_id": "agt-1"},
                "rationale": "threat detected",
                "source": "agentic_ai",
            }
            started = datetime.datetime.utcnow()

            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                svc._log_decision(
                    decision_id="d-1",
                    agent_id="agt-1",
                    result=result_payload,
                    started_at=started,
                )
            )

        # insert_one was called
        assert mock_insert.call_count == 1, "Expected _log_decision to call insert_one"
        doc = mock_insert.call_args[0][0]

        required_fields = [
            "_id", "agent_id", "tool_name", "tool_input",
            "rationale", "model", "started_at", "completed_at", "source",
        ]
        for field in required_fields:
            assert field in doc, f"Missing required field in decision doc: {field}"
            assert doc[field] is not None, f"Field '{field}' is None in decision doc"


# ===========================================================================
# Test 7 — AI-03: _log_decision() failure is logged at ERROR, not suppressed
# ===========================================================================

class TestAuditWriteFailureIsLoggedNotSuppressed:
    """_log_decision() must log 'AUDIT WRITE FAILURE' at ERROR and NOT re-raise."""

    def test_audit_write_failure_is_logged_not_suppressed(self):
        mock_insert = AsyncMock(side_effect=Exception("mongo down"))
        mock_db = MagicMock()
        mock_db.agent_ai_decisions.insert_one = mock_insert

        mock_error_log = MagicMock()
        mock_anthropic_cls = MagicMock()
        mock_anthropic_cls.return_value = MagicMock()

        with patch("agentic_service.AsyncAnthropic", mock_anthropic_cls), \
             patch("agentic_service.get_database", return_value=mock_db), \
             patch("agentic_service.logger.error", mock_error_log):
            from agentic_service import AgenticService
            svc = AgenticService(api_key="test")

            result_payload = {
                "tool_name": "run_threat_hunt",
                "tool_input": {"agent_id": "agt-1"},
                "rationale": "test",
                "source": "agentic_ai",
            }
            started = datetime.datetime.utcnow()

            loop = asyncio.get_event_loop()
            # Must NOT raise — exception swallowed internally
            loop.run_until_complete(
                svc._log_decision(
                    decision_id="d-fail",
                    agent_id="agt-1",
                    result=result_payload,
                    started_at=started,
                )
            )

        # logger.error was called with "AUDIT WRITE FAILURE"
        assert mock_error_log.called, "Expected logger.error to be called on audit write failure"
        # Check any call contains "AUDIT WRITE FAILURE"
        found = any(
            "AUDIT WRITE FAILURE" in str(call_args)
            for call_args in mock_error_log.call_args_list
        )
        assert found, (
            f"Expected 'AUDIT WRITE FAILURE' in logger.error calls, "
            f"got: {mock_error_log.call_args_list}"
        )


# ===========================================================================
# Test 8 — AI-04: CircuitBreakerOpen activates rule-based fallback
# ===========================================================================

class TestCircuitBreakerOpenActivatesFallback:
    """When agentic_breaker is OPEN, run() must activate rule-based fallback."""

    def test_circuit_breaker_open_activates_fallback(self):
        from circuit_breaker import CircuitBreakerOpen

        mock_insert = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
        mock_db = MagicMock()
        mock_db.agent_ai_decisions.insert_one = mock_insert
        mock_db.agent_instructions.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="fake-id")
        )

        mock_anthropic_cls = MagicMock()
        mock_anthropic_cls.return_value = MagicMock()

        # Patch agentic_breaker.__aenter__ to raise CircuitBreakerOpen
        mock_breaker = MagicMock()
        mock_breaker.__aenter__ = AsyncMock(side_effect=CircuitBreakerOpen("agentic_ai"))
        mock_breaker.__aexit__ = AsyncMock(return_value=False)

        with patch("agentic_service.AsyncAnthropic", mock_anthropic_cls), \
             patch("agentic_service.get_database", return_value=mock_db), \
             patch("agentic_service.agentic_breaker", mock_breaker):
            from agentic_service import AgenticService
            svc = AgenticService(api_key="test")

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                svc.run("agt-1", {"agent_id": "agt-1"})
            )

        # Must be rule_based_fallback
        assert result["source"] == "rule_based_fallback", (
            f"Expected source='rule_based_fallback' when circuit open, got {result.get('source')}"
        )

        # insert_one called with source=rule_based_fallback
        assert mock_insert.call_count == 1, (
            f"Expected 1 insert_one (audit log) call, got {mock_insert.call_count}"
        )
        doc = mock_insert.call_args[0][0]
        assert doc.get("source") == "rule_based_fallback", (
            f"Expected audit doc source='rule_based_fallback', got {doc.get('source')}"
        )
