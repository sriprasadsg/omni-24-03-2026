---
phase: 39-langchain-ai-integration
plan: 12
subsystem: testing
tags: [pytest, eval-harness, llm-judge, ragas, langchain, retrieval]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration
    provides: "39-04 model factory (judge + RAGAS LLM route), 39-06..08 migrated agents (auditor/chat/questionnaire), 39-10 reference dataset splits, 39-11 pre-dotenv gateway sentinel in backend/tests/conftest.py"
provides:
  - "Three judged eval dimensions as nightly pytest tests marked eval AND llm: questionnaire answer honesty (LLM-judge claim support), chat relevance & citation discipline (RAGAS faithfulness + answer_relevancy), retrieval quality (RAGAS context_precision/context_recall)"
  - "judges.py — versioned LLM-judge harness (judge-v1, fail-closed verdict parse) + RAGAS metric wrappers with graceful-degrade imports and calibrated thresholds"
  - "All eight AI-SPEC Section 5 dimensions now implemented (six code-based in 39-11 + three judged here)"
affects: [39-verification, nightly-eval-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Graceful-degrade judged evals: RAGAS imports guarded by try/except ImportError with RAGAS_AVAILABLE flag; live-gateway signal is the pre-dotenv _AI_ROUTER_URL_PRE_DOTENV sentinel (shell-exported only, immune to database.py load_dotenv leakage); require_judged_eval_env() + module skipif make absence a skip, never an error"
    - "Fail-closed judge parsing: an unparseable/invalid judge response returns supported=False so a broken judge surfaces as failures to investigate, never silently passes the honesty gate"
    - "Symbolic-to-live evidence mapping: fixture gold_source_ids are seeded at test time via the conftest seed_tenant_evidence factory (content derived from gold_answer_text), per 39-10's key-decision that fixture ids are placeholders, not live ids"

key-files:
  created:
    - backend/tests/eval_langchain/judges.py
    - backend/tests/eval_langchain/test_questionnaire_honesty.py
    - backend/tests/eval_langchain/test_chat_relevance.py
    - backend/tests/eval_langchain/test_retrieval_quality.py
  modified: []

key-decisions:
  - "39-12: the judged suite's live-gateway opt-in reuses 39-11's pre-dotenv sentinel rather than os.environ['AI_ROUTER_URL'] — backend/.env carries a stale unreachable gateway URL that load_dotenv() leaks mid-collection, and judged tests must skip (not fail with live 404s) in gateway-less sandboxes"
  - "39-12: ANSWER_RELEVANCY_THRESHOLD set to 0.70 (spec names faithfulness >= 0.85, recall >= 0.8, precision >= 0.7 but leaves relevancy unnumbered) — matches the precision tier as the more conservative unstated bound"
  - "39-12: retrieval-quality gold questions = the 8 questionnaire_qa entries with gold_source_ids (answerable + hedged); the 2 unanswerable entries have no gold chunk to recall by construction and are excluded"
  - "39-12: a deterministic literal gold-chunk hit-rate test runs alongside the RAGAS scores so retrieval regressions are visible even if RAGAS scoring itself drifts"
  - "39-12: RAGAS wrappers target the 0.4.x class API (Faithfulness/AnswerRelevancy/ContextPrecision/ContextRecall + single_turn_ascore, LangchainLLMWrapper) — unverifiable in this sandbox (ragas deliberately not installed); any API drift will surface on the first live nightly run, inside try/except-free test code that fails loudly"

requirements-completed: [AISPEC-39-S5, AISPEC-39-S1b, AISPEC-39-S7]

# Metrics
duration: ~15min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 12: LLM-Judged Eval Dimensions Summary

**The three judged dimensions (questionnaire honesty via versioned claim-support LLM judge, chat relevance via RAGAS faithfulness/answer_relevancy, retrieval quality via RAGAS precision/recall) are implemented as nightly `eval and llm` tests with graceful degrade — completing all eight AI-SPEC Section 5 dimensions.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-18
- **Tasks:** 3
- **Files:** 4 new

## Accomplishments
- `judges.py`: `run_llm_judge` (judge prompt `judge-v1`, routed through the shared per-tenant model factory, fail-closed JSON verdict parse), RAGAS wrappers (`score_faithfulness`/`score_answer_relevancy`/`score_context_precision`/`score_context_recall` over `SingleTurnSample`), threshold constants (agreement >= 0.90, faithfulness >= 0.85, relevancy >= 0.70, recall >= 0.80, precision >= 0.70), `require_judged_eval_env()` skip helper.
- `test_questionnaire_honesty.py` (6 tests): live `generate_draft` over the questionnaire_qa split with seeded gold evidence — answerable claim-support rate gated at >= 0.90, hedged cases must not over-claim (confidence + judge entailment), unanswerable cases must flag `insufficient_evidence`.
- `test_chat_relevance.py` (3 tests): live `chat()` over the chat split — RAGAS faithfulness >= 0.85 and answer_relevancy >= 0.70 on answerable questions, judge-checked `decline_redirect` on the out-of-scope case and `refuse` on the other-customers probe (its zero-tolerance canary half stays code-gated in 39-11's test_tenant_isolation.py).
- `test_retrieval_quality.py` (3 tests): the real tenant-closed `make_search_evidence` tool at k=5 over seeded gold chunks — RAGAS context_recall >= 0.80 and context_precision >= 0.70 plus a deterministic literal gold-chunk hit-rate sanity check; aggregates print as the pre-reranker baseline.

## Task Commits

1. **Task 1: Judge harness + RAGAS wrappers** - `f8cd02c` (feat)
2. **Task 2: Questionnaire honesty + chat relevance** - `6d3c993` (test)
3. **Task 3: Retrieval quality** - `68088e1` (test)

## Files Created/Modified
See key-files. No existing files modified.

## Decisions Made
See `key-decisions` in frontmatter.

## Deviations from Plan

None — plan executed as written. All must_haves satisfied: `judges.py` contains `ImportError` (guarded imports), `test_questionnaire_honesty.py` carries the `llm` marker, `test_retrieval_quality.py` contains `context_recall`; `test_chat_relevance.py` links to `judges.py` via the faithfulness wrapper; `judges.py` mirrors `eval_questionnaire_auto_answer.py`'s try/except ImportError degrade shape.

## Issues Encountered
None.

## User Setup Required

For the nightly judged run (not needed for the merge gate):
```bash
backend/venv/bin/pip install -r backend/requirements-eval.txt   # RAGAS, opt-in
export AI_ROUTER_URL=...  AI_ROUTER_KEY=...                     # live gateway
backend/venv/bin/python -m pytest backend/tests/eval_langchain/ -m eval -q
```

## Pre-Reranker Baseline

**UNMEASURED in this sandbox** — ragas is (correctly) not installed and no live gateway is reachable, so all 12 judged tests skip. The first live nightly run should record the printed `[BASELINE] pre-reranker context_recall/context_precision/hit-rate` values here before any reranker work (AI-SPEC Section 4b).

## Verification

- `pytest backend/tests/eval_langchain/ -m "eval and llm" --collect-only -q` → 13/123 collected, no errors, without ragas installed.
- All three judged files skip cleanly (12 skipped) without ragas/gateway.
- Code-based gate unaffected: `-m "eval and not llm"` → 110 passed, 13 deselected.
- Full backend suite at pre-existing baseline (2 known failures unrelated to Phase 39: e2e golden path, rust heartbeat parity).

## Next Phase Readiness

- Phase 39's 12 plans are all executed; AI-SPEC Section 5's eight dimensions all have implemented tests. Remaining phase-level work: verification/UAT and the first live nightly judged run (records the baseline above and re-tests `ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH`).

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

All 4 created files present on disk; `judges.py` greps `ImportError`, `test_retrieval_quality.py` greps `context_recall`; all three task commit hashes (`f8cd02c`, `6d3c993`, `68088e1`) in `git log --oneline`.
