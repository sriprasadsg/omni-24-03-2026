---
status: partial
phase: 39-langchain-ai-integration
source: [39-01-SUMMARY.md, 39-02-SUMMARY.md, 39-03-SUMMARY.md, 39-04-SUMMARY.md, 39-05-SUMMARY.md, 39-06-SUMMARY.md, 39-07-SUMMARY.md, 39-08-SUMMARY.md, 39-09-SUMMARY.md, 39-10-SUMMARY.md, 39-11-SUMMARY.md, 39-12-SUMMARY.md]
started: 2026-07-19T18:10:00Z
updated: 2026-07-19T18:20:00Z
---

## Current Test

[testing complete — automatable items resolved; 2 blocked on live gateway]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running backend. Start uvicorn from scratch. Server boots without errors, `/api/health` returns live data.
result: pass
evidence: Booted `venv/bin/python -m uvicorn app:app` cold (no prior server on :5000). Startup completed (~60s, YARA rulesets + data lake init), `GET /api/health` → 200 `{"status":"ok","service":"backend-fastapi","edition":"2030"}`. Zero ERROR lines in startup log. Tracing degrades gracefully by design: openinference-instrumentation-anthropic absent in this sandbox → single WARNING, LangChain instrumentation skipped inside the same guarded block, boot unaffected (app_startup.py:492-508).

### 2. LangChain 1.x Runtime Installed (39-01)
expected: All documented top-level imports resolve in backend venv; langchain reports 1.3.14.
result: pass
evidence: `create_agent`, `init_chat_model`, `AsyncSqliteSaver`, `LangChainInstrumentor` all import; printed `OK 1.3.14`. `import app_startup` exits 0.

### 3. Code-Based Eval Gate — Phase Gate (39-11)
expected: `pytest backend/tests/eval_langchain/ -m "eval and not llm"` passes all six code-based dimensions (traceability, framework fidelity, conservative status, tenant isolation, fallback provenance, RAG-02 gate).
result: pass
evidence: 110 passed, 13 deselected, 5.4s.

### 4. Judged Eval Suite Skips Cleanly Without Live Gateway (39-12)
expected: `pytest -m "eval and llm"` skips cleanly (no failures, no collection errors) when ragas/AI_ROUTER_URL are unavailable.
result: pass
evidence: 13 skipped, 110 deselected, 0 failed.

### 5. Orchestration Infrastructure Suites (39-03/04/05)
expected: Schemas + validators (27), model factory/memory/tracing (25), tools/prompts/guardrails/decision-log (15) all pass hermetically.
result: pass
evidence: 75 passed (test_ai_orchestration_schemas.py, test_ai_orchestration_infra.py, test_ai_orchestration_substrate.py), 10.9s.

### 6. Agent-Surface Migration Suites (39-06/07/08/09) + Dataset (39-10)
expected: Auditor (14), chat (10 + 5 retargeted ai_assistant), questionnaire (14), narrative (17 + 8 shim), eval dataset (23) all pass; shims preserve legacy signatures.
result: pass
evidence: 93 passed across test_auditor_agent.py, test_chat_agent.py, test_questionnaire_agent.py, test_narrative_agent.py, test_ai_assistant.py, test_compliance_narrative_service.py, test_eval_dataset.py, 7.1s.

### 7. Full-Suite Regression Baseline
expected: Full backend suite at pre-39 baseline — no new failures attributable to Phase 39.
result: pass
evidence: 1282 passed / 35 skipped / 3 failed. Two failures are the documented pre-existing baseline (test_e2e_integration golden path, test_rust_heartbeat_parity). Third (test_agentic_ai::TestRunCallsAnthropicWithToolChoiceAny) is stale-test drift from branch commit c4c3401 ("force serial tool use in decide_and_execute" — production now sends `tool_choice={"type": "any", "disable_parallel_tool_use": True}`, test asserts the old exact dict). Reproduces in isolation; unrelated to Phase 39 files. Test needs its assertion updated to match the intentional c4c3401 behavior — tracked outside this phase.

### 8. Live 9router Structured-Output Passthrough Re-Test (39-02 decision)
expected: `test_router_passthrough.py` run with live AI_ROUTER_URL prints `[9ROUTER_PASSTHROUGH_DECISION] result=PASS|FAIL`; PASS would allow revisiting the ToolStrategy-everywhere decision.
result: blocked
blocked_by: server
reason: "No live 9router gateway reachable from this sandbox; skip guard (fca3d14) requires AI_ROUTER_URL exported pre-dotenv. Decision remains conservatively FAIL — downstream agents already built on ToolStrategy, so this is an optimization opportunity, not a defect."

### 9. First Live Nightly Judged Eval Run (39-12)
expected: `pytest -m "eval and llm"` with ragas + live gateway records the pre-reranker retrieval baseline (faithfulness ≥0.85, relevancy ≥0.70, recall ≥0.80, precision ≥0.70, honesty ≥0.90) and re-tests ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH.
result: blocked
blocked_by: third-party
reason: "Needs ragas installed + live model gateway. First nightly run still owed per STATE.md; thresholds and suites verified skip-clean (Test 4)."

## Summary

total: 9
passed: 7
issues: 0
blocked: 2
pending: 0
skipped: 0

## Gaps

[none — 0 issues; 2 blocked items are prerequisite gates (live gateway), not code defects]
