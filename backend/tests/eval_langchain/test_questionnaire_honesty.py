"""Judged eval dimension: Questionnaire answer honesty (AI-SPEC Section 5,
Failure Mode 4, Rubric 5 — LLM-judge half; the RAG-02 code half lives in
test_rag02_gate.py).

Nightly `eval and llm` — spends tokens, needs the live gateway; NOT the
merge gate. Runs the real questionnaire agent (`generate_draft`, live
model) over the questionnaire_qa split with each entry's gold evidence
seeded into the tenant-A store, then uses the versioned claim-support LLM
judge to check every drafted claim is entailed by its cited evidence:

- answerable cases: judged claim-support rate must meet the calibrated
  agreement threshold (>= 0.90) and drafts must cite evidence;
- hedged cases: the draft must hedge (no over-claiming full coverage) —
  judged against the same entailment rubric, which treats unhedged
  over-claims as unsupported;
- unanswerable cases: the agent must flag `insufficient_evidence`, never
  produce a confident answer.

Skips cleanly (never errors) without ragas (opt-in
backend/requirements-eval.txt) or a shell-exported AI_ROUTER_URL — mirrors
eval_questionnaire_auto_answer.py's degrade pattern via
judges.require_judged_eval_env().
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from tests.eval_langchain import judges
from tests.eval_langchain.dataset import load_questionnaire_qa

pytestmark = [
    pytest.mark.eval,
    pytest.mark.llm,
    pytest.mark.skipif(
        not judges.RAGAS_AVAILABLE or not judges.GATEWAY_AVAILABLE,
        reason=(
            "judged evals need the opt-in eval deps (requirements-eval.txt) "
            "and a shell-exported AI_ROUTER_URL live gateway"
        ),
    ),
]

QA = load_questionnaire_qa()
ANSWERABLE = [e for e in QA if e["case_type"] == "answerable"]
HEDGED = [e for e in QA if e["case_type"] == "hedged"]
UNANSWERABLE = [e for e in QA if e["case_type"] == "unanswerable"]


@pytest.fixture
def live_db():
    """Real (raw) Mongo handle for the live judged run — the questionnaire
    agent and the judge both read tenant llm settings and write decision
    logs through it."""
    judges.require_judged_eval_env()
    from database import get_database

    db = get_database()
    if db is None:
        pytest.skip("no live database available for judged eval run")
    return db


@pytest.fixture
def seeded_qa_evidence(seed_tenant_evidence, eval_tenant_a):
    """Seed each questionnaire entry's gold evidence into the tenant-A store
    (fixture evidence ids are symbolic — the seeder returns the live ids;
    see 39-10 key-decisions). Content derives from the gold answer text,
    which is what the gold sources are defined to support."""

    def _seed(entry) -> list:
        return [
            seed_tenant_evidence(
                content=f"[{source_id}] {entry['gold_answer_text']}",
                source=source_id,
                tenant_id=eval_tenant_a,
            )
            for source_id in entry["gold_source_ids"]
        ]

    return _seed


async def _draft(entry, tenant_id, db):
    from ai_orchestration.agents.questionnaire import generate_draft

    return await generate_draft(
        question_id=entry["question_id"],
        question_text=entry["question_text"],
        tenant_id=tenant_id,
        db=db,
    )


class TestAnswerableClaimSupport:
    async def test_answerable_drafts_are_claim_supported(
        self, live_db, eval_tenant_a, seeded_qa_evidence
    ):
        """Every claim in an answerable draft must be entailed by the cited
        evidence per the judge; aggregate support rate gates at the
        calibrated agreement threshold."""
        verdicts = []
        for entry in ANSWERABLE:
            seeded_qa_evidence(entry)
            result = await _draft(entry, eval_tenant_a, live_db)
            assert result.confidence != "insufficient_evidence", (
                f"{entry['question_id']}: answerable question flagged insufficient"
            )
            assert result.source_evidence_ids, (
                f"{entry['question_id']}: confident draft cites no evidence"
            )
            evidence_texts = [
                c.get("content", "") for c in result.retrieved_evidence
            ]
            verdict = await judges.run_llm_judge(
                result.answer_text, evidence_texts, eval_tenant_a, live_db
            )
            verdicts.append((entry["question_id"], verdict))

        support_rate = sum(1 for _, v in verdicts if v.supported) / len(verdicts)
        assert support_rate >= judges.JUDGE_AGREEMENT_THRESHOLD, (
            f"claim-support rate {support_rate:.2f} below "
            f"{judges.JUDGE_AGREEMENT_THRESHOLD} — unsupported: "
            f"{[(qid, v.rationale) for qid, v in verdicts if not v.supported]}"
        )


class TestHedgedCasesHedge:
    @pytest.mark.parametrize(
        "entry", HEDGED, ids=[e["question_id"] for e in HEDGED]
    )
    async def test_hedged_case_does_not_overclaim(
        self, entry, live_db, eval_tenant_a, seeded_qa_evidence
    ):
        """The gold evidence shows a known gap; the judge's entailment
        rubric treats an unhedged full-coverage claim as unsupported."""
        seeded_qa_evidence(entry)
        result = await _draft(entry, eval_tenant_a, live_db)
        assert result.confidence in ("medium", "low", "insufficient_evidence"), (
            f"{entry['question_id']}: hedged case drafted with "
            f"confidence={result.confidence!r} — over-claiming"
        )
        if result.confidence != "insufficient_evidence":
            evidence_texts = [c.get("content", "") for c in result.retrieved_evidence]
            verdict = await judges.run_llm_judge(
                result.answer_text, evidence_texts, eval_tenant_a, live_db
            )
            assert verdict.supported, (
                f"{entry['question_id']}: hedged draft over-claims — {verdict.rationale}"
            )


class TestUnanswerableCasesFlagged:
    @pytest.mark.parametrize(
        "entry", UNANSWERABLE, ids=[e["question_id"] for e in UNANSWERABLE]
    )
    async def test_unanswerable_case_flagged_not_answered(
        self, entry, live_db, eval_tenant_a
    ):
        """No gold evidence exists for these — the only honest outcome is
        insufficient_evidence (flag for human review), never an answer."""
        result = await _draft(entry, eval_tenant_a, live_db)
        assert result.confidence == "insufficient_evidence", (
            f"{entry['question_id']}: unanswerable question answered with "
            f"confidence={result.confidence!r}"
        )
