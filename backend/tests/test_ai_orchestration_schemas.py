"""Unit tests for Phase 39 ai_orchestration shared schemas + validator.

Tests: backend/ai_orchestration/schemas.py, backend/ai_orchestration/validators.py

Convention: hermetic — an explicit mock db handle is passed to
`validate_citations`/`validate_framework_fidelity` (no module-level
patching, no live model/gateway/network), mirroring the project's
dependency-injected `db`/`get_database`-override convention seen in
test_compliance_narrative_service.py. `pytest.ini` sets asyncio_mode=auto,
so `async def test_*` functions run without extra decoration.

Naming: schema-behavior tests live in classes/functions containing
"schema" so `-k schema` selects them; validator tests contain "validator"
so `-k validator` selects them.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from ai_orchestration.schemas import AuditFinding, Citation, CitedAnswer, NarrativeOutput
from ai_orchestration.validators import (
    FAILURE_REASON,
    extract_control_id_tokens,
    validate_citations,
    validate_framework_fidelity,
)


# ===========================================================================
# Schema tests (-k schema)
# ===========================================================================

class TestAuditFindingSchema:
    def test_valid_finding_round_trips(self):
        finding = AuditFinding(
            control_id="CIS-5.2",
            status="pass",
            rationale="Evidence confirms MFA is enforced for all admin accounts.",
            citations=[Citation(source="mfa-policy.pdf", chunk_id="cev-1")],
        )
        dumped = finding.model_dump()
        reloaded = AuditFinding(**dumped)
        assert reloaded == finding

    def test_empty_citations_raises(self):
        with pytest.raises(ValidationError):
            AuditFinding(
                control_id="CIS-5.2",
                status="pass",
                rationale="Some rationale text.",
                citations=[],
            )

    def test_status_rejects_out_of_set_value(self):
        with pytest.raises(ValidationError):
            AuditFinding(
                control_id="CIS-5.2",
                status="maybe",
                rationale="Some rationale text.",
                citations=[Citation(source="s", chunk_id="c1")],
            )

    @pytest.mark.parametrize("prefix", ["BLOCKED:", "Error:"])
    def test_error_prefixed_rationale_raises(self, prefix):
        with pytest.raises(ValidationError):
            AuditFinding(
                control_id="CIS-5.2",
                status="fail",
                rationale=f"{prefix} guardrail suppressed this rationale",
                citations=[Citation(source="s", chunk_id="c1")],
            )

    def test_empty_control_id_raises(self):
        with pytest.raises(ValidationError):
            AuditFinding(
                control_id="   ",
                status="pass",
                rationale="Some rationale text.",
                citations=[Citation(source="s", chunk_id="c1")],
            )


class TestCitedAnswerSchema:
    def test_grounded_answer_is_valid(self):
        answer = CitedAnswer(
            question_id="q1",
            answer_text="Yes, encryption at rest is enabled.",
            confidence="high",
            source_evidence_ids=["cev-1"],
            citations=[Citation(source="kms-policy.pdf", chunk_id="cev-1")],
        )
        assert answer.confidence == "high"

    def test_no_evidence_and_confident_raises(self):
        with pytest.raises(ValidationError):
            CitedAnswer(
                question_id="q1",
                answer_text="Yes, we are fully compliant.",
                confidence="high",
                source_evidence_ids=[],
            )

    def test_no_evidence_but_insufficient_evidence_confidence_is_valid(self):
        answer = CitedAnswer(
            question_id="q1",
            answer_text="Insufficient evidence to answer this question.",
            confidence="insufficient_evidence",
            source_evidence_ids=[],
        )
        assert answer.source_evidence_ids == []

    @pytest.mark.parametrize("prefix", ["BLOCKED:", "Error:"])
    def test_error_prefixed_answer_text_raises(self, prefix):
        with pytest.raises(ValidationError):
            CitedAnswer(
                question_id="q1",
                answer_text=f"{prefix} guardrail suppressed this answer",
                confidence="insufficient_evidence",
                source_evidence_ids=[],
            )

    def test_empty_answer_text_raises(self):
        with pytest.raises(ValidationError):
            CitedAnswer(
                question_id="q1",
                answer_text="   ",
                confidence="insufficient_evidence",
                source_evidence_ids=[],
            )


class TestNarrativeOutputSchema:
    def test_within_budget_is_valid(self):
        narrative = NarrativeOutput.from_raw("Compliance posture is strong.", limit=150)
        assert narrative.word_count <= 150

    def test_over_budget_raises(self):
        with pytest.raises(ValidationError):
            NarrativeOutput(text=" ".join(["word"] * 250), word_count=250, limit=200)

    @pytest.mark.parametrize("prefix", ["BLOCKED:", "Error:"])
    def test_error_prefixed_text_raises(self, prefix):
        with pytest.raises(ValidationError):
            NarrativeOutput(text=f"{prefix} narrative blocked", word_count=3, limit=200)

    def test_empty_text_raises(self):
        with pytest.raises(ValidationError):
            NarrativeOutput(text="   ", word_count=0, limit=200)


# ===========================================================================
# Validator tests (-k validator)
# ===========================================================================

_TENANT_ID = "tenant-a"
_FRAMEWORK_FIXTURE = [
    {"id": "fw-cis", "tenantId": _TENANT_ID, "controls": [{"id": "CIS-5.2"}, {"id": "AC-2"}]},
    {"id": "fw-global", "tenantId": "global", "controls": [{"id": "CC6.1"}]},
]


def _make_mock_db(
    frameworks=None,
    control_evidence_doc=None,
    asset_compliance_doc=None,
):
    """Hermetic mock db: dependency-injected into validate_citations /
    validate_framework_fidelity rather than patching a module-level db."""
    db = MagicMock()
    db.compliance_frameworks.find = MagicMock(return_value=AsyncMock())
    db.compliance_frameworks.find.return_value.to_list = AsyncMock(
        return_value=frameworks if frameworks is not None else _FRAMEWORK_FIXTURE
    )
    db.control_evidence.find_one = AsyncMock(return_value=control_evidence_doc)
    db.asset_compliance.find_one = AsyncMock(return_value=asset_compliance_doc)
    return db


def _valid_finding(control_id="CIS-5.2", chunk_id="cev-1"):
    return AuditFinding(
        control_id=control_id,
        status="pass",
        rationale="Evidence confirms this control is satisfied.",
        citations=[Citation(source="policy.pdf", chunk_id=chunk_id)],
    )


class TestValidateCitationsValidator:
    async def test_resolves_valid_citation_and_control_id(self):
        db = _make_mock_db(control_evidence_doc={"id": "cev-1", "tenantId": _TENANT_ID})
        finding = _valid_finding()

        result, output = await validate_citations(finding, _TENANT_ID, db)

        assert result.ok is True
        assert output.status == "pass"

    async def test_resolves_citation_via_asset_compliance_evidence_array(self):
        db = _make_mock_db(
            control_evidence_doc=None,
            asset_compliance_doc={"controlId": "CIS-5.2", "tenantId": _TENANT_ID,
                                   "evidence": [{"id": "cev-1"}]},
        )
        finding = _valid_finding()

        result, output = await validate_citations(finding, _TENANT_ID, db)

        assert result.ok is True
        assert output.status == "pass"

    async def test_unresolvable_citation_id_fails_and_downgrades(self):
        db = _make_mock_db(control_evidence_doc=None, asset_compliance_doc=None)
        finding = _valid_finding(chunk_id="does-not-exist")

        result, output = await validate_citations(finding, _TENANT_ID, db)

        assert result.ok is False
        assert result.reason == FAILURE_REASON
        assert output.status == "insufficient_evidence"

    async def test_unknown_control_id_fails_and_downgrades(self):
        db = _make_mock_db(control_evidence_doc={"id": "cev-1", "tenantId": _TENANT_ID})
        finding = _valid_finding(control_id="SOC 2 CC9.9")

        result, output = await validate_citations(finding, _TENANT_ID, db)

        assert result.ok is False
        assert result.reason == FAILURE_REASON
        assert output.status == "insufficient_evidence"

    async def test_never_queries_evidence_without_tenant_scope(self):
        db = _make_mock_db(control_evidence_doc={"id": "cev-1", "tenantId": _TENANT_ID})
        finding = _valid_finding()

        await validate_citations(finding, _TENANT_ID, db)

        # Every call into control_evidence/asset_compliance must carry the
        # tenant-scope $or clause (acting tenant + "global"), never a bare
        # unfiltered find/find_one.
        for call in db.control_evidence.find_one.call_args_list:
            query = call.args[0]
            assert "$or" in query
            assert {"tenantId": _TENANT_ID} in query["$or"]
            assert {"tenantId": "global"} in query["$or"]
        for call in db.compliance_frameworks.find.call_args_list:
            query = call.args[0]
            assert "$or" in query

    async def test_cited_answer_downgrades_confidence_on_failure(self):
        db = _make_mock_db(control_evidence_doc=None, asset_compliance_doc=None)
        answer = CitedAnswer(
            question_id="q1",
            answer_text="Yes, we enforce this control.",
            confidence="high",
            source_evidence_ids=["cev-missing"],
            citations=[Citation(source="policy.pdf", chunk_id="cev-missing")],
        )

        result, output = await validate_citations(answer, _TENANT_ID, db)

        assert result.ok is False
        assert result.reason == FAILURE_REASON
        assert output.confidence == "insufficient_evidence"


class TestFrameworkFidelityValidator:
    def test_extract_control_id_tokens_ignores_bare_framework_names(self):
        tokens = extract_control_id_tokens(
            "The SOC 2 framework scored well; CIS-5.2 and CC6.1 were reviewed."
        )
        assert "CIS-5.2" in tokens
        assert "CC6.1" in tokens
        assert "SOC 2" not in tokens

    async def test_unknown_token_fails(self):
        db = _make_mock_db()
        result = await validate_framework_fidelity(
            "Assess us against SOC 2 CC9.9 as well.", _TENANT_ID, db
        )
        assert result.ok is False
        assert result.reason == FAILURE_REASON

    async def test_known_tokens_pass(self):
        db = _make_mock_db()
        result = await validate_framework_fidelity(
            "CIS-5.2 and CC6.1 were both satisfied.", _TENANT_ID, db
        )
        assert result.ok is True

    async def test_no_tokens_passes_trivially(self):
        db = _make_mock_db()
        result = await validate_framework_fidelity(
            "This narrative mentions no control identifiers at all.", _TENANT_ID, db
        )
        assert result.ok is True
