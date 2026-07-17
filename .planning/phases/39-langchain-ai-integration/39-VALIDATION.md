---
phase: 39
slug: langchain-ai-integration
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-17
updated: 2026-07-17
---

# Phase 39 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Regenerated against the final 12-plan set (39-01..39-12) after the revision pass.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (run via `backend/venv/bin/python -m pytest` — never bare `pytest`; asyncio_mode=auto) |
| **Config file** | `pytest.ini` (root) — `eval`/`llm` markers registered by plan 39-02 Task 2 |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/ -m "eval and not llm" -q` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests/ -q` (baseline 946 passed / 22 skipped, 2026-07-16) |
| **Estimated runtime** | quick: ~30s · full: ~3-4 min |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` verify command (per-task map below) plus the quick run command once `eval_langchain/` exists (wave 2+).
- **After every plan wave:** Run the full suite command — must stay green against the 946/22 baseline.
- **Before `/gsd-verify-work`:** Full suite green AND `-m "eval and not llm"` suite green. The judged suite (`-m "eval and llm"`) is nightly, not a phase gate.
- **Max feedback latency:** ~30s (quick command); per-task commands are all sub-file-scoped and faster.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 39-01-01 | 01 | 1 | AISPEC-39-S2 | T-39-SC | No [SLOP]/unverified package installed; human confirms 8 registry pages | checkpoint (manual) | — (blocking human-verify; see Manual-Only table) | n/a | ⬜ pending |
| 39-01-02 | 01 | 1 | AISPEC-39-S2/S3 | T-39-01-A | Exact pins only; langchain-chroma absent | smoke | `backend/venv/bin/python -c "import langchain; import langchain_core; import langgraph; import langchain_openai; import langchain_anthropic; import langchain_ollama; from langchain.agents import create_agent; from langchain.chat_models import init_chat_model; from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; from openinference.instrumentation.langchain import LangChainInstrumentor; print('OK', langchain.__version__)"` | ❌ W0 (installs) | ⬜ pending |
| 39-02-01 | 02 | 2 | RESEARCH-OQ3 / AISPEC-39-S3 | T-39-02-A | Passthrough decision recorded; skip (not error) without gateway; no sync invoke/asyncio.run | eval (llm) | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_router_passthrough.py -m "eval and llm" -q --no-header 2>&1 \| tail -5` | ❌ W0 | ⬜ pending |
| 39-02-02 | 02 | 2 | AISPEC-39-S5 / RESEARCH-PitE | T-39-02-B | Markers real (no silent 0-test pass); two-tenant canary fixtures | config/collect | `backend/venv/bin/python -m pytest -W error::pytest.PytestUnknownMarkWarning backend/tests/eval_langchain/ --collect-only -m eval -q >/dev/null 2>&1 && echo MARKERS_OK` | ❌ W0 | ⬜ pending |
| 39-03-01 | 03 | 2 | AISPEC-39-S4b | T-39-03-A | AuditFinding rejects empty citations; error-string sentinel rejected | unit (tdd) | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_schemas.py -q -k schema` | ❌ W0 | ⬜ pending |
| 39-03-02 | 03 | 2 | AISPEC-39-S6 | T-39-03-A/B/C | Citations resolve tenant-scoped; unknown control_id rejected; no unfiltered evidence reads | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_schemas.py -q -k validator` | ❌ W0 | ⬜ pending |
| 39-03-03 | 03 | 2 | AISPEC-39-S5 | T-39-03-A | Hermetic coverage of schema + validator invariants | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_schemas.py -q` | ❌ W0 | ⬜ pending |
| 39-04-01 | 04 | 3 | AISPEC-39-S4 / RESEARCH-Pat1 | T-39-04-B | Single provider cache (no second _tenant_providers); provenance helper | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_infra.py -q -k models` | ❌ W0 | ⬜ pending |
| 39-04-02 | 04 | 3 | AISPEC-39-S4 | T-39-04-A | Tenant-prefixed thread_id mandatory; no in-process session dict | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_infra.py -q -k memory` | ❌ W0 | ⬜ pending |
| 39-04-03 | 04 | 3 | AISPEC-39-S5/S7 / RESEARCH-PitC | T-39-04-C | Tracing degrades gracefully; never blocks startup | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_infra.py -q -k tracing` | ❌ W0 | ⬜ pending |
| 39-05-01 | 05 | 3 | AISPEC-39-S4 / RESEARCH-PitB | T-39-05-A | tenant_id closed over; tool args schema exposes only query; no langchain-chroma | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_substrate.py -q -k tools` | ❌ W0 | ⬜ pending |
| 39-05-02 | 05 | 3 | AISPEC-39-S6/S7 / RESEARCH-PitD | T-39-05-B/D | Guardrail hooks reuse scan_and_log; decision docs carry no agent_id (reader-compat by construction) | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_substrate.py -q -k guardrails` | ❌ W0 | ⬜ pending |
| 39-05-03 | 05 | 3 | AISPEC-39-S6/S7 | T-39-05-A/B/D | Canary block + reader-unaffected + never-raise audit write covered hermetically | unit | `backend/venv/bin/python -m pytest backend/tests/test_ai_orchestration_substrate.py -q` | ❌ W0 | ⬜ pending |
| 39-10-01 | 10 | 3 | AISPEC-39-S5 | T-39-10-B | Gold labels conservative (traps = insufficient_evidence); no real PII | eval (code) | `backend/venv/bin/python -m pytest backend/tests/test_eval_dataset.py -q -k splits` | ❌ W0 | ⬜ pending |
| 39-10-02 | 10 | 3 | AISPEC-39-S5/S1 | T-39-10-A | Loader fails loud on malformed fixtures; adversarial canaries wired to conftest | eval (code) | `backend/venv/bin/python -m pytest backend/tests/test_eval_dataset.py -q -k loader` | ❌ W0 | ⬜ pending |
| 39-10-03 | 10 | 3 | AISPEC-39-S5 | T-39-10-A | Dataset internally consistent (48 examples; citation/ID coherence) | eval (code) | `backend/venv/bin/python -m pytest backend/tests/test_eval_dataset.py -m eval -q` | ❌ W0 | ⬜ pending |
| 39-06-01 | 06 | 4 | AISPEC-39-S4/S4b/S6/S7 | T-39-06-A/C/D | Citation-validated findings; downgrade on failure; fallback pass -> needs_review; log_ai_decision | unit (tdd) | `backend/venv/bin/python -m pytest backend/tests/test_auditor_agent.py -q -k agent` | ❌ W0 | ⬜ pending |
| 39-06-02 | 06 | 4 | AISPEC-39-S4 (CONTEXT shim decision) | T-39-06-B | Fail-closed shim: exceptions return verified False, never fabricated pass | unit | `backend/venv/bin/python -m pytest backend/tests/test_auditor_agent.py -q -k shim` | ❌ W0 | ⬜ pending |
| 39-06-03 | 06 | 4 | AISPEC-39-S5 | T-39-06-A/B/D | Hermetic downgrade + escalation + shim coverage | unit | `backend/venv/bin/python -m pytest backend/tests/test_auditor_agent.py -q` | ❌ W0 | ⬜ pending |
| 39-07-01 | 07 | 4 | AISPEC-39-S4/S6/S7 | T-39-07-A/B/C | Tenant-prefixed thread memory; input scan before external model; log_ai_decision | unit | `backend/venv/bin/python -m pytest backend/tests/test_chat_agent.py -q -k agent` | ❌ W0 | ⬜ pending |
| 39-07-02 | 07 | 4 | AISPEC-39-S4 (CONTEXT shim decision) | T-39-07-B | {answer, sources} contract preserved; error path never raises | unit | `backend/venv/bin/python -m pytest backend/tests/test_chat_agent.py -q -k shim` | ❌ W0 | ⬜ pending |
| 39-07-03 | 07 | 4 | AISPEC-39-S5 | T-39-07-A/B | Thread isolation + contract coverage; existing test_ai_assistant.py stays green | unit | `backend/venv/bin/python -m pytest backend/tests/test_chat_agent.py -q` | ❌ W0 | ⬜ pending |
| 39-08-01 | 08 | 4 | AISPEC-39-S4/S4b/S5/S6/S7 | T-39-08-A/C | CitedAnswer grounded-or-flagged; no direct drafts-collection write from agent; log_ai_decision | unit (tdd) | `backend/venv/bin/python -m pytest backend/tests/test_questionnaire_agent.py -q -k agent` | ❌ W0 | ⬜ pending |
| 39-08-02 | 08 | 4 | AISPEC-39-S6 (RAG-02) | T-39-08-B | Always pending_review; zero "submitted" writes in module | unit | `backend/venv/bin/python -m pytest backend/tests/test_questionnaire_agent.py -q -k shim` | ❌ W0 | ⬜ pending |
| 39-08-03 | 08 | 4 | AISPEC-39-S5 | T-39-08-A/B | Mongo doc shape + gate coverage | unit | `backend/venv/bin/python -m pytest backend/tests/test_questionnaire_agent.py -q` | ❌ W0 | ⬜ pending |
| 39-09-01 | 09 | 4 | AISPEC-39-S4/S4b/S6/S7 | T-39-09-A/B | Word-budget validated; fail-closed fallback; _sanitise preserved; log_ai_decision | unit (tdd) | `backend/venv/bin/python -m pytest backend/tests/test_narrative_agent.py -q -k agent` | ❌ W0 | ⬜ pending |
| 39-09-02 | 09 | 4 | AISPEC-39-S4 (CONTEXT shim decision) | T-39-09-C | Report pipeline never hard-fails; signatures preserved | unit | `backend/venv/bin/python -m pytest backend/tests/test_narrative_agent.py -q -k shim` | ❌ W0 | ⬜ pending |
| 39-09-03 | 09 | 4 | AISPEC-39-S5 | T-39-09-A/C | Fallback + enrich_report_data coverage; existing narrative suite stays green | unit | `backend/venv/bin/python -m pytest backend/tests/test_narrative_agent.py -q` | ❌ W0 | ⬜ pending |
| 39-11-01 | 11 | 5 | AISPEC-39-S5 (traceability, fidelity) | T-39-11-B | 100% citation/control-ID resolution; fabricated-ID bait flagged | eval (code) | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_traceability.py backend/tests/eval_langchain/test_framework_fidelity.py -m "eval and not llm" -q` | ❌ W0 | ⬜ pending |
| 39-11-02 | 11 | 5 | AISPEC-39-S5 (conservative status) | T-39-11-B | 0 false-pass on Critical/High; <5% overall; traps stay insufficient_evidence | eval (code) | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_conservative_status.py -m "eval and not llm" -q` | ❌ W0 | ⬜ pending |
| 39-11-03 | 11 | 5 | AISPEC-39-S5/S6/S7 (isolation, provenance, RAG-02) | T-39-11-A/C | Zero canary hits in outputs + tool args; fallback marker + needs_review; no submitted without approver | eval (code) | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_tenant_isolation.py backend/tests/eval_langchain/test_fallback_provenance.py backend/tests/eval_langchain/test_rag02_gate.py -m "eval and not llm" -q` | ❌ W0 | ⬜ pending |
| 39-12-01 | 12 | 5 | AISPEC-39-S5 (judge harness) | T-39-12-A/B | RAGAS/judge imports degrade gracefully; thresholds encoded | collect/eval | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/ -m "eval and llm" --collect-only -q >/dev/null 2>&1 && echo JUDGE_COLLECT_OK` | ❌ W0 | ⬜ pending |
| 39-12-02 | 12 | 5 | AISPEC-39-S5 (honesty, chat relevance) | T-39-12-A | Claim-support judged; refusal on out-of-scope/other-customers; skips without ragas/gateway | eval (llm, nightly) | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_questionnaire_honesty.py backend/tests/eval_langchain/test_chat_relevance.py -m "eval and llm" -q --no-header 2>&1 \| tail -5` | ❌ W0 | ⬜ pending |
| 39-12-03 | 12 | 5 | AISPEC-39-S5 (retrieval quality) | T-39-12-A | recall >= 0.8, precision >= 0.7 baseline recorded pre-reranker | eval (llm, nightly) | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_retrieval_quality.py -m "eval and llm" -q --no-header 2>&1 \| tail -5` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. "❌ W0" in File Exists = the test file is created by that plan's own tasks (test-with-implementation within the plan), not missing infrastructure.*

---

## Wave 0 Requirements

All RESEARCH.md "Wave 0 Gaps" are owned by wave-1/2 plans — no unowned gaps:

- [x] `pytest.ini` markers (`eval`, `llm`) — owned by **39-02 Task 2** (verified by MARKERS_OK collect gate)
- [x] `backend/tests/eval_langchain/` directory + `data/` + `conftest.py` (two-tenant canary fixtures) — owned by **39-02 Tasks 1-2**; `data/` populated by **39-10**
- [x] LangChain framework install (8 pinned packages, human-gated) — owned by **39-01**
- [x] Eval graceful-degrade pattern (RAGAS optional) — owned by **39-12 Task 1** (mirrors `eval_questionnaire_auto_answer.py`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Package legitimacy confirmation (8 PyPI packages) | AISPEC-39-S2 / T-39-SC | Package-legitimacy protocol: SUS-flagged installs require a blocking human-verify checkpoint (never auto-approvable) | 39-01 Task 1: open the 8 registry URLs listed in the task, confirm langchain-ai / Arize-ai maintainer org on each, type "approved" |

All other phase behaviors have automated verification.

---

## Regression Guards (per wave merge)

- `backend/venv/bin/python -m pytest backend/tests/ -q` — full suite vs. 946/22 baseline
- Contract-preservation re-runs after shim rewrites: `test_ai_assistant.py` (39-07), `test_compliance_narrative_service.py` (39-09), Phase 30 questionnaire review tests (39-08 / 39-11 RAG-02)
- Code-review grep gates (enforced via plan acceptance criteria): `\.invoke\(|asyncio\.run\(` == 0 in `backend/ai_orchestration/` agents; `get_tenant_id` == 0 in tool bodies; `agent_id` == 0 in `decision_log.py`

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (35 tasks: 34 automated, 1 human checkpoint listed under Manual-Only)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (only 39-01-01 is manual; its successor 39-01-02 is automated)
- [x] Wave 0 covers all MISSING references (markers/scaffold/install owned by 39-01/39-02/39-10/39-12)
- [x] No watch-mode flags (all commands single-shot `-q`; no `--watch`/`-f`)
- [x] Feedback latency ≈ 30s for the quick gate command; per-task commands faster
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-17 (regenerated against final plan set 39-01..39-12, revision iteration 2)
