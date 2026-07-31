"""LLM-judge harness + RAGAS metric wrappers for the judged eval dimensions
(39-12, AI-SPEC Section 5: questionnaire honesty, chat relevance, retrieval
quality — the dimensions with no deterministic oracle).

Graceful degrade contract (T-39-12-B, mirrors
`eval_questionnaire_auto_answer.py`): every RAGAS import is wrapped in
try/except with a module-level `RAGAS_AVAILABLE` flag; RAGAS lives in
`backend/requirements-eval.txt` (opt-in, never the runtime image), so its
absence must SKIP judged tests, never error them. The live-gateway signal is
the pre-dotenv `_AI_ROUTER_URL_PRE_DOTENV` sentinel captured by
`backend/tests/conftest.py` — same opt-in semantics as the router smoke
test: only a shell-exported AI_ROUTER_URL means "a live gateway is really
reachable"; a value leaked from backend/.env by `database.py`'s
load_dotenv() does not.

Judge verdicts are nightly/flywheel signals, not the merge gate
(T-39-12-A): the judge prompt is versioned (`JUDGE_PROMPT_VERSION`) and must
be calibrated against >= 20 human-labeled drafts to
`JUDGE_AGREEMENT_THRESHOLD` agreement before any judged metric gates a
change.
"""
import json
import os
import re
from dataclasses import dataclass
from typing import Any, List, Optional

# --- Guarded eval-only imports (requirements-eval.txt) ---------------------
try:  # pragma: no cover - exercised only with the opt-in eval deps installed
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    SingleTurnSample = None
    LangchainEmbeddingsWrapper = LangchainLLMWrapper = None
    AnswerRelevancy = ContextPrecision = ContextRecall = Faithfulness = None

# Live-gateway opt-in: shell environment only (see module docstring).
LIVE_GATEWAY_URL = os.environ.get("_AI_ROUTER_URL_PRE_DOTENV") or os.environ.get(
    "AI_ROUTER_URL"
)
GATEWAY_AVAILABLE = bool(LIVE_GATEWAY_URL)

# --- Versioning + calibrated thresholds (AI-SPEC Section 5) ----------------
JUDGE_PROMPT_VERSION = "judge-v1"
# Judge-vs-human calibration bar: judged metrics gate nothing until the
# judge agrees with >= 20 human-labeled drafts at this rate.
JUDGE_AGREEMENT_THRESHOLD = 0.90
# Chat relevance dimension.
FAITHFULNESS_THRESHOLD = 0.85
ANSWER_RELEVANCY_THRESHOLD = 0.70
# Retrieval quality dimension (measure BEFORE adding a reranker).
CONTEXT_RECALL_THRESHOLD = 0.80
CONTEXT_PRECISION_THRESHOLD = 0.70


def require_judged_eval_env() -> None:
    """pytest-skip unless the judged-eval environment is complete: RAGAS
    installed (opt-in eval deps) AND a live gateway exported in the shell.
    Import pytest lazily so this module stays importable outside pytest."""
    import pytest

    if not RAGAS_AVAILABLE:
        pytest.skip(
            "ragas not installed — judged evals need the opt-in eval deps "
            "(backend/requirements-eval.txt); never installed into runtime"
        )
    if not GATEWAY_AVAILABLE:
        pytest.skip(
            "AI_ROUTER_URL not set in the shell environment — judged evals "
            "spend tokens and need the live 9router gateway"
        )


# --- LLM judge (questionnaire claim support / behavior checks) -------------

_CLAIM_SUPPORT_JUDGE_PROMPT = f"""You are a strict compliance-evidence auditor (judge prompt {JUDGE_PROMPT_VERSION}).
Given a CLAIM from a drafted questionnaire answer and the cited EVIDENCE
excerpts, decide whether every factual assertion in the claim is directly
entailed by the evidence. Hedged language ("in progress", "compensating
control") is acceptable ONLY when the evidence shows the gap it hedges.
Over-claiming (asserting more coverage, speed, or certainty than the
evidence shows) is NOT supported.

Respond with raw JSON only: {{"supported": true|false, "rationale": "<one sentence>"}}"""


@dataclass
class JudgeVerdict:
    """Structured verdict from one `run_llm_judge` call."""

    supported: bool
    rationale: str
    prompt_version: str = JUDGE_PROMPT_VERSION


def _parse_verdict(raw: str) -> JudgeVerdict:
    """Fail-closed parse: an unparseable judge response is NOT supported —
    a broken judge must surface as failures to investigate, never silently
    pass the honesty gate."""
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return JudgeVerdict(supported=False, rationale=f"unparseable judge output: {raw[:120]}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return JudgeVerdict(supported=False, rationale=f"invalid judge JSON: {raw[:120]}")
    return JudgeVerdict(
        supported=bool(data.get("supported", False)),
        rationale=str(data.get("rationale", ""))[:500],
    )


async def run_llm_judge(
    claim: str,
    evidence_texts: List[str],
    tenant_id: Optional[str],
    db: Any,
    judge_prompt: str = _CLAIM_SUPPORT_JUDGE_PROMPT,
) -> JudgeVerdict:
    """Ask the judge model (via the shared per-tenant model factory, routed
    through the live gateway) whether `claim` is entailed by
    `evidence_texts`. Returns a fail-closed `JudgeVerdict`."""
    from ai_orchestration.models import build_model_for_tenant

    evidence_block = "\n\n".join(
        f"[evidence {i}]\n{text[:1500]}" for i, text in enumerate(evidence_texts)
    ) or "(no evidence cited)"
    model = await build_model_for_tenant(tenant_id, db, surface="auditor")
    response = await model.ainvoke(
        [
            {"role": "system", "content": judge_prompt},
            {"role": "user", "content": f"CLAIM:\n{claim}\n\nEVIDENCE:\n{evidence_block}"},
        ]
    )
    return _parse_verdict(getattr(response, "content", "") or "")


# --- RAGAS metric wrappers -------------------------------------------------


def build_sample(
    user_input: str,
    response: str,
    retrieved_contexts: List[str],
    reference: Optional[str] = None,
):
    """Build a RAGAS SingleTurnSample (mirrors
    eval_questionnaire_auto_answer.py's usage)."""
    kwargs = {
        "user_input": user_input,
        "response": response,
        "retrieved_contexts": retrieved_contexts,
    }
    if reference is not None:
        kwargs["reference"] = reference
    return SingleTurnSample(**kwargs)


async def _ragas_llm(tenant_id: Optional[str], db: Any):
    from ai_orchestration.models import build_model_for_tenant

    return LangchainLLMWrapper(await build_model_for_tenant(tenant_id, db, surface="auditor"))


async def _score(metric_cls, sample, tenant_id: Optional[str], db: Any, **metric_kwargs) -> float:
    metric = metric_cls(llm=await _ragas_llm(tenant_id, db), **metric_kwargs)
    return float(await metric.single_turn_ascore(sample))


async def score_faithfulness(sample, tenant_id: Optional[str], db: Any) -> float:
    """RAGAS faithfulness: response claims entailed by retrieved contexts."""
    return await _score(Faithfulness, sample, tenant_id, db)


async def score_answer_relevancy(sample, tenant_id: Optional[str], db: Any, embeddings=None) -> float:
    """RAGAS answer relevancy: response addresses the asked question."""
    kwargs = {}
    if embeddings is not None:
        kwargs["embeddings"] = LangchainEmbeddingsWrapper(embeddings)
    return await _score(AnswerRelevancy, sample, tenant_id, db, **kwargs)


async def score_context_precision(sample, tenant_id: Optional[str], db: Any) -> float:
    """RAGAS context precision: retrieved chunks relevant to the question."""
    return await _score(ContextPrecision, sample, tenant_id, db)


async def score_context_recall(sample, tenant_id: Optional[str], db: Any) -> float:
    """RAGAS context recall: the gold-cited chunk appears in the retrieval."""
    return await _score(ContextRecall, sample, tenant_id, db)
