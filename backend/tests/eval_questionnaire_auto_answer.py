#!/usr/bin/env python3
"""
Opt-in eval harness for Phase 30 (AI Questionnaire Auto-Answer).
This script is NOT part of the blocked pytest suite.
Run with: python -m backend.tests.eval_questionnaire_auto_answer --dataset path/to/fixtures.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Guarded imports for eval tooling
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation import _BUNDLED_INSTRUMENTATIONS
    from opentelemetry.instrumentation.chromadb import ChromaDBInstrumentor
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
    OTEL_AVAILABLE = True
except Exception:
    OTEL_AVAILABLE = False
    trace = None

try:
    import ragas
    from ragas.metrics import faithfulness, answer_relevancy, context_precision
    RAGAS_AVAILABLE = True
except Exception:
    RAGAS_AVAILABLE = False
    ragas = None
    faithfulness = answer_relevancy = context_precision = None

# Local imports (these should be available)
from rag_service import rag_service
from ai_service import ai_service
from tenant_context import set_tenant_id

if not OTEL_AVAILABLE:
    print("[WARN] OpenTelemetry not available — tracing disabled", file=sys.stderr)

if not RAGAS_AVAILABLE:
    print("[WARN] Ragas not available — metric computation disabled", file=sys.stderr)


def setup_tracing():
    """Configure OpenTelemetry tracing to console if available."""
    if not OTEL_AVAILABLE:
        return None
    provider = TracerProvider()
    processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    # Auto-instrument ChromaDB and OpenAI (anthropic) if available
    ChromaDBInstrumentor().instrument()
    OpenAIInstrumentor().instrument()
    return trace.get_tracer(__name__)


def load_dataset(path: Path):
    """Load JSON fixture file."""
    with path.open() as f:
        return json.load(f)


async def evaluate_one(tracer, question_id: str, question_text: str, tenant_id: str, db, gold_answer: str = ""):
    """Run retrieval + generation for a single question, return dict with traces/metrics."""
    set_tenant_id(tenant_id)
    # Instrumented span for rag + ai calls
    with tracer.start_as_current_span("questionnaire.eval") as span:
        span.set_attribute("question.id", question_id)
        span.set_attribute("question.text", question_text[:120])
        # Retrieve
        with tracer.start_as_current_span("rag.query") as rag_span:
            retrieved = rag_service.query(question_text, n_results=5, tenant_id=tenant_id)
            rag_span.set_attribute("evidence.count", len(retrieved))
            for i, ev in enumerate(retrieved):
                rag_span.set_attribute(f"evidence.{i}.source", ev.get("source", "")[:80])
                rag_span.set_attribute(f"evidence.{i}.content", ev.get("content", "")[:120])
        # Generation prompt (mirrors draft_answer_for_question)
        evidence_block = "\n".join(
            f"[{i}] (source: {e['source']}) {e['content']}" for i, e in enumerate(retrieved)
        )
        system_part = (
            "You are a security questionnaire response assistant. Answer using ONLY "
            "the evidence provided below. Cite the evidence indices you used. If the "
            "evidence does not support a confident answer, say so explicitly — do not "
            "invent claims. Respond as raw JSON: {\"answer_text\": str, "
            "\"confidence\": \"high\"|\"medium\"|\"low\"|\"insufficient_evidence\", "
            "\"cited_indices\": [int]}"
        )
        user_part = f"<evidence>\n{evidence_block}\n</evidence>\n\nQUESTION: {question_text}"
        prompt = f"{system_part}\n\n{user_part}"
        with tracer.start_as_current_span("ai.generate") as ai_span:
            raw = await ai_service.generate_text(prompt, source="questionnaire_eval")
            ai_span.set_attribute("prompt.length", len(prompt))
            ai_span.set_attribute("raw.output", raw[:120])
        # Very lightweight parsing — try to get answer_text
        answer_text = ""
        confidence = ""
        try:
            import json as pyjson
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            data = pyjson.loads(cleaned)
            answer_text = data.get("answer_text", "")
            confidence = data.get("confidence", "")
        except Exception:
            answer_text = ""
            confidence = ""
        return {
            "question_id": question_id,
            "retrieved": retrieved,
            "raw": raw,
            "answer_text": answer_text,
            "confidence": confidence,
        }


async def main():
    parser = argparse.ArgumentParser(description="Run Phase 30 eval harness")
    parser.add_argument("--dataset", required=True, help="Path to questionnaire_eval_set.json")
    parser.add_argument("--tenant-id", default="eval-tenant", help="Tenant ID to use for retrieval")
    args = parser.parse_args()

    fixture_path = Path(args.dataset)
    if not fixture_path.is_file():
        print(f"[ERROR] Dataset not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)

    dataset = load_dataset(fixture_path)
    tracer = setup_tracing() if OTEL_AVAILABLE else None

    # Get a mock DB handle (in real test this would be patched)
    # For this scaffold we just show the structure; actual Verify phase will inject mocks
    class MockDB:
        class MockCollection:
            def insert_one(self, doc):
                pass
        questionnaire_answer_drafts = MockCollection()
    db = MockDB()

    results = []
    import asyncio
    for entry in dataset:
        res = await evaluate_one(
            tracer,
            entry["id"],
            entry["question_text"],
            args.tenant_id,
            db,
            entry.get("gold_answer", "")
        )
        results.append(res)
        print(f"[INFO] {entry['id']}: conf={res['confidence']} ans={len(res['answer_text'])} chars")

    # If Ragas available, compute metrics (requires gold answers)
    if RAGAS_AVAILABLE and all(r["answer_text"] for r in results):
        try:
            import numpy as np
            from ragas.dataset_schema import SingleTurnSample
            samples = []
            for r, entry in zip(results, dataset):
                if r["answer_text"] and entry["gold_answer"]:
                    samples.append(SingleTurnSample(
                        user_input=entry["question_text"],
                        response=r["answer_text"],
                        reference=entry["gold_answer"],
                        retrieved_contexts=[e["content"] for e in r["retrieved"]]
                    ))
            if samples:
                faithfulness_score = np.mean([faithfulness(samples)])
                answer_relevancy_score = np.mean([answer_relevancy(samples)])
                context_precision_score = np.mean([context_precision(samples)])
                print(f"[METRIC] faithfulness={faithfulness_score:.3f}")
                print(f"[METRIC] answer_relevancy={answer_relevancy_score:.3f}")
                print(f"[METRIC] context_precision={context_precision_score:.3f}")
        except Exception as e:
            print(f"[WARN] Ragas metric computation failed: {e}", file=sys.stderr)

    # Write results for inspection
    out_path = fixture_path.parent / "eval_results.json"
    with out_path.open("w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"[INFO] Results written to {out_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())