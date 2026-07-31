"""Phase 39-06 — hermetic unit tests for the create_agent auditor
(ai_orchestration/agents/auditor.py) and the ai_auditor_service.py shim.

Convention: hermetic — the agent/model call graph is stubbed
(`create_agent`/`build_model_for_tenant` patched to return canned
structured responses, per this plan's own action text), and citation/
control-ID resolution runs for REAL against a small in-memory mocked `db`
(mirrors test_ai_orchestration_schemas.py's dependency-injected `db`
convention) so the citation-validation wiring is actually exercised, not
just mocked away. No live model/gateway/network/Chroma calls anywhere in
this file.

Naming: `-k agent` selects `ai_orchestration.agents.auditor` tests,
`-k shim` selects `ai_auditor_service.py` tests — matching this plan's two
per-task `<verify>` commands.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ai_orchestration.agents.auditor import AuditEvaluationResult, evaluate_control
from ai_orchestration.schemas import AuditFinding, Citation
from ai_orchestration.validators import FAILURE_REASON
from ai_auditor_service import get_auditor


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    """guardrail_service.scan_and_log calls the real get_database() — patch
    it at the source (the same singleton `ai_orchestration.guardrails`
    imports) so scan_input/scan_output run for real without a live Mongo
    connection, mirroring test_ai_orchestration_substrate.py's convention of
    patching `guardrail_service` for guardrail tests, applied file-wide here
    since most tests exercise the real (non-blocking) guardrail path."""
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_KNOWN_FRAMEWORK = {
    "id": "fw-1",
    "controls": [{"id": "AC-1", "name": "Access Control", "description": "MFA required"}],
}
_KNOWN_EVIDENCE = [
    {
        "controlId": "AC-1",
        "tenantId": "tenant-a",
        "evidence": [{"id": "cev-1", "name": "mfa-screenshot"}],
    }
]


def _cursor(docs):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def _make_db(frameworks=None, evidence_bundles=None):
    """Minimal mocked db satisfying validate_citations' real read path
    (compliance_frameworks.find, control_evidence.find_one,
    asset_compliance.find_one) plus decision_log's insert_one and models'
    best-effort system_settings read."""
    frameworks = frameworks if frameworks is not None else [_KNOWN_FRAMEWORK]
    evidence_bundles = evidence_bundles if evidence_bundles is not None else _KNOWN_EVIDENCE

    db = MagicMock(
        spec=[
            "compliance_frameworks",
            "control_evidence",
            "asset_compliance",
            "agent_ai_decisions",
            "system_settings",
        ]
    )
    db.compliance_frameworks = MagicMock()
    db.compliance_frameworks.find = MagicMock(return_value=_cursor(frameworks))

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

    return db


def _valid_finding(status="pass", control_id="AC-1", chunk_id="cev-1"):
    return AuditFinding(
        control_id=control_id,
        status=status,
        rationale="MFA is enforced per the screenshot evidence.",
        citations=[Citation(source="mfa-screenshot", chunk_id=chunk_id)],
    )


def _agent_stub(structured_response, messages=None):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"structured_response": structured_response, "messages": messages or []}
    )
    return agent


def _patched(agent, model_return=None):
    """Patch the two call-graph seams evaluate_control uses to reach a model."""
    return (
        patch(
            "ai_orchestration.agents.auditor.build_model_for_tenant",
            AsyncMock(return_value=model_return or MagicMock()),
        ),
        patch("ai_orchestration.agents.auditor.create_agent", MagicMock(return_value=agent)),
    )


# ---------------------------------------------------------------------------
# ai_orchestration/agents/auditor.py (-k agent)
# ---------------------------------------------------------------------------


class TestEvaluateControlAgent:
    async def test_happy_path_valid_finding_stays_pass(self):
        db = _make_db()
        agent = _agent_stub(_valid_finding())
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required for admin access",
                evidence_text="MFA screenshot attached",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert isinstance(result, AuditEvaluationResult)
        assert result.finding.status == "pass"
        assert result.citation_validation == "pass"
        assert result.needs_review is False
        agent.ainvoke.assert_awaited_once()
        db.agent_ai_decisions.insert_one.assert_awaited_once()

    async def test_unresolvable_citation_downgrades_to_insufficient_evidence(self):
        db = _make_db()
        # citation chunk_id "cev-DOES-NOT-EXIST" never resolves against db fixtures
        agent = _agent_stub(_valid_finding(chunk_id="cev-does-not-exist"))
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required for admin access",
                evidence_text="claims MFA is enforced",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.status == "insufficient_evidence"
        assert result.citation_validation == "blocked"
        # The underlying block reason is validators.FAILURE_REASON — asserted
        # directly against the shared constant (39-03) this module wires in.
        assert FAILURE_REASON == "citation_validation_failed"

    async def test_unknown_control_id_rejected(self):
        db = _make_db()
        # control_id "ZZ-99" is not in the seeded framework registry
        agent = _agent_stub(_valid_finding(control_id="ZZ-99"))
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="Some control never registered",
                evidence_text="evidence text",
                tenant_id="tenant-a",
                db=db,
                # Caller does NOT know the real control_id here — otherwise
                # this module's own control_id-pinning would silently
                # overwrite the model's fabricated "ZZ-99" with a real id.
                control_id=None,
            )

        assert result.finding.status == "insufficient_evidence"
        assert result.citation_validation == "blocked"

    async def test_fallback_provenance_pass_flags_needs_review(self):
        db = _make_db()
        agent = _agent_stub(_valid_finding())
        p1, p2 = _patched(agent)
        with p1, p2, patch(
            "ai_orchestration.agents.auditor.model_provenance",
            return_value="fallback:llama3.2:3b",
        ):
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required for admin access",
                evidence_text="MFA screenshot attached",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.status == "pass"
        assert result.model_provenance == "fallback:llama3.2:3b"
        assert result.needs_review is True

    async def test_fallback_provenance_non_pass_does_not_need_review(self):
        db = _make_db()
        agent = _agent_stub(_valid_finding(status="fail"))
        p1, p2 = _patched(agent)
        with p1, p2, patch(
            "ai_orchestration.agents.auditor.model_provenance",
            return_value="fallback:llama3.2:3b",
        ):
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required for admin access",
                evidence_text="no MFA found",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.status == "fail"
        assert result.needs_review is False

    async def test_input_guardrail_block_skips_agent_invocation(self):
        db = _make_db()
        agent = _agent_stub(_valid_finding())
        p1, p2 = _patched(agent)
        blocked = MagicMock(passed=False, findings=["PII Detected"], reason="input_guardrail_blocked")
        with p1, p2, patch(
            "ai_orchestration.agents.auditor.scan_input", AsyncMock(return_value=blocked)
        ):
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="contains PII",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.status == "insufficient_evidence"
        agent.ainvoke.assert_not_awaited()

    async def test_output_guardrail_block_downgrades_finding(self):
        db = _make_db()
        agent = _agent_stub(_valid_finding())
        p1, p2 = _patched(agent)
        blocked = MagicMock(passed=False, findings=["injection"], reason="output_guardrail_blocked")
        with p1, p2, patch(
            "ai_orchestration.agents.auditor.scan_output", AsyncMock(return_value=blocked)
        ):
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="MFA screenshot attached",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.status == "insufficient_evidence"

    async def test_control_id_pinned_from_caller_overrides_model_output(self):
        db = _make_db()
        # Model fabricates a different (wrong) control_id in its structured output.
        agent = _agent_stub(_valid_finding(control_id="FABRICATED-1"))
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required for admin access",
                evidence_text="MFA screenshot attached",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.control_id == "AC-1"
        assert result.finding.status == "pass"

    async def test_agent_invocation_error_returns_insufficient_evidence_not_raise(self):
        db = _make_db()
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=RuntimeError("gateway down"))
        p1, p2 = _patched(agent)
        with p1, p2:
            result = await evaluate_control(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="MFA screenshot attached",
                tenant_id="tenant-a",
                db=db,
                control_id="AC-1",
            )

        assert result.finding.status == "insufficient_evidence"
        assert result.needs_review is False


# ---------------------------------------------------------------------------
# ai_auditor_service.py shim (-k shim)
# ---------------------------------------------------------------------------


class TestAuditorServiceShim:
    async def test_happy_path_pass_finding_maps_to_verified_true(self):
        from ai_orchestration.agents.auditor import AuditEvaluationResult

        canned = AuditEvaluationResult(
            finding=_valid_finding(),
            model_provenance="primary",
            citation_validation="pass",
            needs_review=False,
        )
        with patch(
            "ai_orchestration.agents.auditor.evaluate_control", AsyncMock(return_value=canned)
        ), patch("database.get_database", MagicMock(return_value=MagicMock())), patch(
            "tenant_context.get_tenant_id", MagicMock(return_value="tenant-a")
        ):
            auditor = get_auditor()
            result = await auditor.evaluate_evidence(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="MFA screenshot attached",
            )

        assert result["verified"] is True
        assert result["reasoning"] == canned.finding.rationale
        assert "evaluatedAt" in result
        assert auditor.model_id == "primary"

    async def test_insufficient_evidence_finding_maps_to_verified_false(self):
        from ai_orchestration.agents.auditor import AuditEvaluationResult

        canned = AuditEvaluationResult(
            finding=_valid_finding(status="insufficient_evidence"),
            model_provenance="primary",
            citation_validation="blocked",
            needs_review=False,
        )
        with patch(
            "ai_orchestration.agents.auditor.evaluate_control", AsyncMock(return_value=canned)
        ), patch("database.get_database", MagicMock(return_value=MagicMock())), patch(
            "tenant_context.get_tenant_id", MagicMock(return_value="tenant-a")
        ):
            auditor = get_auditor()
            result = await auditor.evaluate_evidence(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="no evidence",
            )

        assert result["verified"] is False

    async def test_fallback_provenance_pass_flagged_needs_review_never_equals_primary_pass(self):
        from ai_orchestration.agents.auditor import AuditEvaluationResult

        canned = AuditEvaluationResult(
            finding=_valid_finding(status="pass"),
            model_provenance="fallback:llama3.2:3b",
            citation_validation="pass",
            needs_review=True,
        )
        with patch(
            "ai_orchestration.agents.auditor.evaluate_control", AsyncMock(return_value=canned)
        ), patch("database.get_database", MagicMock(return_value=MagicMock())), patch(
            "tenant_context.get_tenant_id", MagicMock(return_value="tenant-a")
        ):
            auditor = get_auditor()
            result = await auditor.evaluate_evidence(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="MFA screenshot attached",
            )

        # Never silently equal to a primary pass (Failure Mode 5).
        assert result["verified"] is False
        assert "NEEDS_REVIEW" in result["reasoning"]
        assert auditor.model_id == "fallback:llama3.2:3b"

    async def test_exception_path_returns_verified_false_with_reasoning_no_raise(self):
        with patch(
            "ai_orchestration.agents.auditor.evaluate_control",
            AsyncMock(side_effect=RuntimeError("boom")),
        ), patch("database.get_database", MagicMock(return_value=MagicMock())), patch(
            "tenant_context.get_tenant_id", MagicMock(return_value="tenant-a")
        ):
            auditor = get_auditor()
            result = await auditor.evaluate_evidence(
                framework_name="SOC 2",
                control_desc="MFA required",
                evidence_text="MFA screenshot attached",
            )

        assert result["verified"] is False
        assert isinstance(result["reasoning"], str)
        assert "boom" in result["reasoning"]

    def test_get_auditor_returns_singleton(self):
        assert get_auditor() is get_auditor()
