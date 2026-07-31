"""Eval dimension: Conservative status calls / false-pass rate (AI-SPEC
Section 5, Failure Mode 3, Rubric 2).

Code check against gold labels: a **false pass** is the model saying `pass`
where the gold label is `fail` or `insufficient_evidence`. Gate:
false_pass == 0 on Critical/High-severity gold controls and < 5% overall.
The gold fixtures carry no per-entry severity field, so every gold control
is treated as Critical/High — the strict superset (0 tolerance everywhere),
which subsumes the < 5% overall bar; both are still asserted explicitly to
match the spec's two-tier rule.

Deterministic path (`not llm`): the auditor's model call graph is stubbed
with a canned finding built from each gold record and run through the REAL
`evaluate_control` pipeline (citation validation included), so the status
that reaches the false-pass computation is the post-validation status a
caller would actually persist. The live judged variant belongs to 39-12.
Includes the 2 context-dependent trap cases whose gold label is
`insufficient_evidence` — auto-scoring them `pass` is a failure — plus a
tripwire proving the metric detects an inflated (optimistic) model.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from ai_orchestration.agents.auditor import evaluate_control
from ai_orchestration.schemas import AuditFinding, Citation

from tests.eval_langchain.conftest import EVAL_TENANT_A_ID
from tests.eval_langchain.dataset import load_gold_controls
from tests.eval_langchain.test_traceability import canned_finding, make_gold_db

pytestmark = pytest.mark.eval

GOLD_CONTROLS = load_gold_controls()
CONTEXT_DEPENDENT_TRAPS = [
    e for e in GOLD_CONTROLS if e["case_type"] == "trap_context_dependent"
]
# Gold statuses a model `pass` would falsely contradict.
_FALSE_PASS_GOLD_LABELS = {"fail", "insufficient_evidence"}


@pytest.fixture(autouse=True)
def _stub_guardrail_service():
    passing = MagicMock(passed=True, findings=[])
    with patch(
        "ai_orchestration.guardrails.guardrail_service.scan_and_log",
        AsyncMock(return_value=passing),
    ):
        yield


def false_pass_count(pairs) -> int:
    """Count of (gold_status, model_status) pairs where the model claims
    `pass` against a gold `fail`/`insufficient_evidence` label."""
    return sum(
        1
        for gold, model in pairs
        if model == "pass" and gold in _FALSE_PASS_GOLD_LABELS
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


async def _evaluated_status(entry, db, finding=None) -> str:
    """Run one gold control through the real evaluate_control pipeline with
    a canned structured response; return the post-validation status."""
    p1, p2 = _patched_agent(finding if finding is not None else canned_finding(entry))
    with p1, p2:
        result = await evaluate_control(
            framework_name=entry["framework"],
            control_desc=f"Control {entry['control_id']} requirement",
            evidence_text="\n".join(ev["content"] for ev in entry["evidence"]) or "none",
            tenant_id=EVAL_TENANT_A_ID,
            db=db,
            control_id=entry["control_id"],
        )
    return result.finding.status


def _inflated_finding(entry) -> AuditFinding:
    """An optimistic model's output: `pass` on a trap control, citing the
    entry's own (resolvable) evidence so citation validation cannot save us
    — only the false-pass gate catches this."""
    evidence_by_id = {ev["id"]: ev for ev in entry["evidence"]}
    citations = [
        Citation(source=evidence_by_id[cid]["source"], chunk_id=cid)
        for cid in entry["gold_citations"]
    ]
    return AuditFinding(
        control_id=entry["control_id"],
        status="pass",
        rationale="Everything looks fine.",
        citations=citations,
    )


class TestFalsePassGate:
    async def test_false_pass_is_zero_on_critical_high_controls(self):
        """No severity field in the fixtures — all 20 gold controls are
        treated as Critical/High, so the zero-tolerance bar applies to the
        entire gold set."""
        db = make_gold_db()
        pairs = [
            (entry["gold_status"], await _evaluated_status(entry, db))
            for entry in GOLD_CONTROLS
        ]
        assert false_pass_count(pairs) == 0, (
            f"false-pass detected on Critical/High gold controls: {pairs}"
        )

    async def test_false_pass_rate_under_5_percent_overall(self):
        db = make_gold_db()
        pairs = [
            (entry["gold_status"], await _evaluated_status(entry, db))
            for entry in GOLD_CONTROLS
        ]
        rate = false_pass_count(pairs) / len(pairs)
        assert rate < 0.05, f"overall false-pass rate {rate:.1%} >= 5%"

    async def test_statuses_match_gold_labels_exactly(self):
        """Canned-from-gold statuses must survive the pipeline unchanged —
        a downgrade here would mean the harness itself distorts the metric."""
        db = make_gold_db()
        for entry in GOLD_CONTROLS:
            status = await _evaluated_status(entry, db)
            assert status == entry["gold_status"], (
                f"{entry['control_id']}: pipeline returned {status!r}, "
                f"gold is {entry['gold_status']!r}"
            )


class TestContextDependentTraps:
    """The 2 trap cases whose signal looks alarming-but-ambiguous (gold =
    insufficient_evidence): auto-scoring them `pass` is a failure."""

    def test_exactly_two_context_dependent_traps_exist(self):
        assert len(CONTEXT_DEPENDENT_TRAPS) == 2
        assert all(
            e["gold_status"] == "insufficient_evidence" for e in CONTEXT_DEPENDENT_TRAPS
        )

    @pytest.mark.parametrize(
        "entry",
        CONTEXT_DEPENDENT_TRAPS,
        ids=[e["control_id"] for e in CONTEXT_DEPENDENT_TRAPS],
    )
    async def test_context_dependent_trap_never_scores_pass(self, entry):
        status = await _evaluated_status(entry, make_gold_db())
        assert status == "insufficient_evidence"

    @pytest.mark.parametrize(
        "entry",
        CONTEXT_DEPENDENT_TRAPS,
        ids=[e["control_id"] for e in CONTEXT_DEPENDENT_TRAPS],
    )
    async def test_pass_on_context_dependent_trap_counts_as_false_pass(self, entry):
        status = await _evaluated_status(entry, make_gold_db(), _inflated_finding(entry))
        assert false_pass_count([(entry["gold_status"], status)]) == 1


class TestFalsePassTripwire:
    async def test_inflated_model_is_detected_by_the_metric(self):
        """Prove the gate is real: an optimistic model that scores every
        trap/fail control `pass` (with resolvable citations, so traceability
        alone cannot block it) must register a nonzero false-pass count."""
        db = make_gold_db()
        inflatable = [
            e
            for e in GOLD_CONTROLS
            if e["gold_status"] in _FALSE_PASS_GOLD_LABELS and e["gold_citations"]
        ]
        assert inflatable, "gold set must contain citing fail/insufficient controls"
        pairs = [
            (entry["gold_status"], await _evaluated_status(entry, db, _inflated_finding(entry)))
            for entry in inflatable
        ]
        assert false_pass_count(pairs) == len(inflatable)
