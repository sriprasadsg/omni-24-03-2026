"""Judged eval dimension: Retrieval quality (AI-SPEC Section 5, High
priority — RAGAS context_precision / context_recall over the gold question
set; supports all grounding dimensions).

Nightly `eval and llm` (RAGAS scoring makes model calls); NOT the merge
gate. For each gold question (the questionnaire_qa entries that carry gold
sources), the gold-cited chunk content is seeded into the tenant-A store
and the REAL tenant-scoped retrieval tool (39-05 `make_search_evidence`,
k=5 — the exact path every agent surface uses) is run over it. Scores:

- context_recall >= 0.80 — the chunk a domain expert would cite appears in
  the top-k retrieval;
- context_precision >= 0.70 — the retrieved chunks are relevant to the
  question.

AI-SPEC Section 4b: measure these BEFORE adding a reranker dependency —
the aggregate scores printed by the recall/precision tests are the
pre-reranker baseline; record them in the 39-12 SUMMARY when this suite
runs against a live gateway.

Skips cleanly without ragas or a shell-exported AI_ROUTER_URL, and without
a live ChromaDB (the seeder fixture skips itself).
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

# Gold questions = every entry with gold sources (answerable + hedged);
# unanswerable entries have no gold chunk to recall by construction.
GOLD_QUESTIONS = [e for e in load_questionnaire_qa() if e["gold_source_ids"]]
_TOP_K = 5


@pytest.fixture
def live_db():
    judges.require_judged_eval_env()
    from database import get_database

    db = get_database()
    if db is None:
        pytest.skip("no live database available for judged eval run")
    return db


@pytest.fixture
def retrieval_run(seed_tenant_evidence, eval_tenant_a):
    """Seed each gold question's cited chunks, then run the REAL
    tenant-closed retrieval tool (k=5) and return (retrieved_texts,
    gold_texts) for scoring."""
    from ai_orchestration.tools.retrieval import make_search_evidence

    def _run(entry):
        gold_texts = []
        for source_id in entry["gold_source_ids"]:
            content = f"[{source_id}] {entry['gold_answer_text']}"
            seed_tenant_evidence(content=content, source=source_id, tenant_id=eval_tenant_a)
            gold_texts.append(content)
        tool = make_search_evidence(eval_tenant_a, n_results=_TOP_K)
        raw = tool.invoke({"query": entry["question_text"]})
        retrieved_texts = [block for block in raw.split("\n\n") if block.strip()]
        return retrieved_texts, gold_texts

    return _run


class TestContextRecall:
    async def test_context_recall_meets_threshold(
        self, live_db, eval_tenant_a, retrieval_run
    ):
        """RAGAS context_recall across the gold set — the expert-cited chunk
        must be retrievable at k=5. Aggregate is the pre-reranker baseline."""
        scores = []
        for entry in GOLD_QUESTIONS:
            retrieved_texts, _ = retrieval_run(entry)
            sample = judges.build_sample(
                user_input=entry["question_text"],
                response=entry["gold_answer_text"],
                retrieved_contexts=retrieved_texts or [""],
                reference=entry["gold_answer_text"],
            )
            scores.append(
                await judges.score_context_recall(sample, eval_tenant_a, live_db)
            )
        mean_recall = sum(scores) / len(scores)
        print(f"[BASELINE] pre-reranker context_recall={mean_recall:.3f}")
        assert mean_recall >= judges.CONTEXT_RECALL_THRESHOLD, (
            f"context_recall {mean_recall:.2f} < {judges.CONTEXT_RECALL_THRESHOLD} "
            f"(per-question: {list(zip([e['question_id'] for e in GOLD_QUESTIONS], scores))})"
        )


class TestContextPrecision:
    async def test_context_precision_meets_threshold(
        self, live_db, eval_tenant_a, retrieval_run
    ):
        """RAGAS context_precision across the gold set — retrieved chunks
        must be relevant to the asked question."""
        scores = []
        for entry in GOLD_QUESTIONS:
            retrieved_texts, _ = retrieval_run(entry)
            sample = judges.build_sample(
                user_input=entry["question_text"],
                response=entry["gold_answer_text"],
                retrieved_contexts=retrieved_texts or [""],
                reference=entry["gold_answer_text"],
            )
            scores.append(
                await judges.score_context_precision(sample, eval_tenant_a, live_db)
            )
        mean_precision = sum(scores) / len(scores)
        print(f"[BASELINE] pre-reranker context_precision={mean_precision:.3f}")
        assert mean_precision >= judges.CONTEXT_PRECISION_THRESHOLD, (
            f"context_precision {mean_precision:.2f} < {judges.CONTEXT_PRECISION_THRESHOLD}"
        )


class TestGoldChunkStructurallyRetrievable:
    async def test_seeded_gold_chunk_appears_in_top_k(
        self, live_db, eval_tenant_a, retrieval_run
    ):
        """Deterministic sanity alongside the RAGAS scores: the literal
        seeded gold content must appear in the k=5 tool output for at least
        the recall-threshold fraction of gold questions."""
        hits = 0
        for entry in GOLD_QUESTIONS:
            retrieved_texts, gold_texts = retrieval_run(entry)
            combined = "\n".join(retrieved_texts)
            if any(gold in combined for gold in gold_texts):
                hits += 1
        hit_rate = hits / len(GOLD_QUESTIONS)
        print(f"[BASELINE] literal gold-chunk hit rate={hit_rate:.3f}")
        assert hit_rate >= judges.CONTEXT_RECALL_THRESHOLD
