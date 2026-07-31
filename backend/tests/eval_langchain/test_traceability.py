"""Eval dimension: Evidence traceability (AI-SPEC Section 5, Failure Mode 2).

Zero-tolerance code check: every `AuditFinding.citations[].chunk_id` on the
gold set must resolve to a seeded tenant-A evidence record and every
`control_id` must exist in the seeded framework registry — 100% pass
required, gating the phase under `-m "eval and not llm"`.

Deterministic path (this file, `not llm`): the auditor agent's model call
graph is stubbed (`create_agent`/`build_model_for_tenant` patched, per
39-11-PLAN Task 1) with a canned finding built from each gold record, while
the shared `validate_citations` (39-03) runs for REAL against a mocked db
seeded from the gold fixtures — the citation/control-ID resolution wiring is
exercised end-to-end through `evaluate_control`, not mocked away. The
live-model judged variant belongs to 39-12.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from ai_orchestration.agents.auditor import evaluate_control
from ai_orchestration.schemas import AuditFinding, Citation
from ai_orchestration.validators import validate_citations

from tests.eval_langchain.conftest import EVAL_TENANT_A_ID
from tests.eval_langchain.dataset import load_gold_controls

pytestmark = pytest.mark.eval

GOLD_CONTROLS = load_gold_controls()
CITED_GOLD_CONTROLS = [e for e in GOLD_CONTROLS if e["gold_citations"]]


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    """`guardrail_service.scan_and_log` reaches for the real database —
    patch it at the singleton (same convention as test_auditor_agent.py) so
    the guardrail hooks run non-blocking without live Mongo."""
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


def make_gold_db(entries=None):
    """Mocked db seeded from the gold fixtures: the framework registry holds
    every gold `control_id` (grouped by framework, `tenantId: "global"`) and
    `asset_compliance` resolves every gold evidence id for tenant A — the
    same read shapes `validate_citations` performs against real Mongo."""
    entries = entries if entries is not None else GOLD_CONTROLS
    by_framework: dict = {}
    for entry in entries:
        by_framework.setdefault(entry["framework"], []).append({"id": entry["control_id"]})
    fw_docs = [
        {"id": name, "tenantId": "global", "controls": controls}
        for name, controls in by_framework.items()
    ]
    evidence_index = {
        ev["id"]: entry for entry in entries for ev in entry["evidence"]
    }

    def _resolve_asset_evidence(query):
        chunk_id = query.get("evidence.id")
        if chunk_id in evidence_index:
            entry = evidence_index[chunk_id]
            return {
                "controlId": entry["control_id"],
                "tenantId": EVAL_TENANT_A_ID,
                "evidence": entry["evidence"],
            }
        return None

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
    db.compliance_frameworks.find = MagicMock(return_value=_cursor(fw_docs))
    db.control_evidence = MagicMock()
    db.control_evidence.find_one = AsyncMock(return_value=None)
    db.asset_compliance = MagicMock()
    db.asset_compliance.find_one = AsyncMock(side_effect=_resolve_asset_evidence)
    db.agent_ai_decisions = MagicMock()
    db.agent_ai_decisions.insert_one = AsyncMock(return_value=None)
    db.system_settings = MagicMock()
    db.system_settings.find_one = AsyncMock(return_value=None)
    return db


def canned_finding(entry) -> AuditFinding:
    """Deterministic canned-from-gold finding standing in for the live
    model's structured response (39-11-PLAN Task 1 `not llm` path)."""
    evidence_by_id = {ev["id"]: ev for ev in entry["evidence"]}
    citations = [
        Citation(source=evidence_by_id[cid]["source"], chunk_id=cid)
        for cid in entry["gold_citations"]
    ]
    if not citations:
        # Zero-evidence traps mirror the agent's own fail-closed placeholder.
        citations = [Citation(source="ai_orchestration.agents.auditor", chunk_id="n/a")]
    return AuditFinding(
        control_id=entry["control_id"],
        status=entry["gold_status"],
        rationale=entry["gold_rationale"] or "insufficient_evidence: zero evidence collected",
        citations=citations,
    )


def _patched_agent(structured_response):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"structured_response": structured_response, "messages": []}
    )
    return (
        patch(
            "ai_orchestration.agents.auditor.build_model_for_tenant",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("ai_orchestration.agents.auditor.create_agent", MagicMock(return_value=agent)),
    )


async def _evaluate(entry, db):
    p1, p2 = _patched_agent(canned_finding(entry))
    with p1, p2:
        return await evaluate_control(
            framework_name=entry["framework"],
            control_desc=f"Control {entry['control_id']} requirement",
            evidence_text="\n".join(ev["content"] for ev in entry["evidence"]) or "none",
            tenant_id=EVAL_TENANT_A_ID,
            db=db,
            control_id=entry["control_id"],
        )


class TestGoldSetCitationResolution:
    """100% of gold citations must resolve through the real validator."""

    @pytest.mark.parametrize(
        "entry", CITED_GOLD_CONTROLS, ids=[e["control_id"] for e in CITED_GOLD_CONTROLS]
    )
    async def test_every_gold_citation_resolves(self, entry):
        result = await _evaluate(entry, make_gold_db())
        assert result.citation_validation == "pass", (
            f"{entry['control_id']}: gold citations {entry['gold_citations']} "
            f"failed to resolve against seeded tenant-A evidence"
        )
        # Resolution must not have downgraded the gold status.
        assert result.finding.status == entry["gold_status"]

    async def test_gold_set_pass_rate_is_100_percent(self):
        db = make_gold_db()
        results = [await _evaluate(entry, db) for entry in CITED_GOLD_CONTROLS]
        passed = sum(1 for r in results if r.citation_validation == "pass")
        assert passed == len(CITED_GOLD_CONTROLS), (
            f"traceability pass rate {passed}/{len(CITED_GOLD_CONTROLS)} — "
            "zero tolerance: 100% required (AI-SPEC Section 5)"
        )


class TestGoldSetControlIdResolution:
    @pytest.mark.parametrize(
        "entry", GOLD_CONTROLS, ids=[e["control_id"] for e in GOLD_CONTROLS]
    )
    async def test_every_gold_control_id_exists_in_registry(self, entry):
        """`validate_citations` resolves each gold `control_id` against the
        seeded `compliance_frameworks` registry (duck-typed obj, no
        citations — isolates control-ID resolution)."""
        obj = SimpleNamespace(control_id=entry["control_id"], citations=[])
        result, _ = await validate_citations(obj, EVAL_TENANT_A_ID, make_gold_db())
        assert result.ok, f"{entry['control_id']} not resolvable in seeded registry"


class TestTraceabilityTripwire:
    """Negative controls: the gate must actually catch fabrication."""

    async def test_fabricated_citation_is_blocked_and_downgraded(self):
        entry = dict(CITED_GOLD_CONTROLS[0])
        finding = canned_finding(entry).model_copy(
            update={"citations": [Citation(source="made-up", chunk_id="cev-FABRICATED")]}
        )
        p1, p2 = _patched_agent(finding)
        with p1, p2:
            result = await evaluate_control(
                framework_name=entry["framework"],
                control_desc="requirement",
                evidence_text="evidence",
                tenant_id=EVAL_TENANT_A_ID,
                db=make_gold_db(),
                control_id=entry["control_id"],
            )
        assert result.citation_validation == "blocked"
        assert result.finding.status == "insufficient_evidence"

    async def test_unknown_control_id_is_blocked(self):
        obj = SimpleNamespace(control_id="ZZ-99", citations=[])
        result, _ = await validate_citations(obj, EVAL_TENANT_A_ID, make_gold_db())
        assert not result.ok
