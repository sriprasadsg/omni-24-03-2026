---
phase: 39-langchain-ai-integration
plan: 01
subsystem: infra
tags: [langchain, langgraph, langchain-openai, langchain-anthropic, langchain-ollama, openinference, pip, backend/requirements.txt]

# Dependency graph
requires: []
provides:
  - Pinned LangChain 1.x runtime dependency block in backend/requirements.txt
  - 8 packages installed and import-verified in backend/venv
  - Human legitimacy checkpoint approval recorded for all 8 SUS-flagged packages
affects: [39-02, 39-03, 39-04, 39-05, 39-06, 39-07, 39-08, 39-09, 39-10, 39-11, 39-12]

# Tech tracking
tech-stack:
  added: [langchain==1.3.14, langchain-core==1.4.9, langgraph==1.2.9, langchain-openai==1.3.5, langchain-anthropic==1.4.8, langchain-ollama==1.1.0, langgraph-checkpoint-sqlite==3.1.0, openinference-instrumentation-langchain==0.1.67]
  patterns: [exact `==` pin style matching existing openinference-instrumentation-anthropic block in requirements.txt]

key-files:
  created: []
  modified: [backend/requirements.txt]

key-decisions:
  - "langchain-chroma intentionally excluded from this install (rag_service.py stays wrapped, never rewrapped) — Pitfall 2 from 39-RESEARCH.md"
  - "langgraph-checkpoint-sqlite==3.1.0 added even though absent from AI-SPEC's pinned list, per 39-RESEARCH.md Wave 0 Gaps — required for the prod checkpointer"
  - "Human legitimacy checkpoint (Task 1) approved all 8 SUS-flagged packages — checker's SUS verdicts were recency/no-download-count artifacts, not real slopsquat signals"

patterns-established: []

requirements-completed: [AISPEC-39-S2, AISPEC-39-S3]

coverage:
  - id: D1
    description: "8 pinned LangChain-ecosystem packages installed into backend/venv per exact versions in backend/requirements.txt"
    requirement: "AISPEC-39-S2"
    verification:
      - kind: unit
        ref: "backend/venv/bin/pip show langchain (Version: 1.3.14)"
        status: pass
      - kind: other
        ref: "backend/venv/bin/python -c 'import langchain; ...; print(OK, langchain.__version__)' -> OK 1.3.14"
        status: pass
    human_judgment: false
  - id: D2
    description: "Human confirms all 8 registry pages resolve to genuine maintainer org before install (legitimacy checkpoint)"
    requirement: "AISPEC-39-S2"
    verification: []
    human_judgment: true
    rationale: "Requires a human to visually confirm PyPI project pages against the langchain-ai/Arize-ai org — not automatable."

# Metrics
duration: ~12min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 01: LangChain Runtime Dependency Install Summary

**Pinned and installed the 8-package LangChain 1.x/LangGraph runtime stack (langchain 1.3.14, langgraph 1.2.9, langchain-openai/anthropic/ollama, langgraph-checkpoint-sqlite, openinference-instrumentation-langchain) into backend/venv, gated behind a human legitimacy checkpoint.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 (Task 1 checkpoint approved by human in a prior session; Task 2 executed this session)
- **Files modified:** 1 (`backend/requirements.txt`)

## Accomplishments
- Human legitimacy checkpoint (Task 1) approved: all 8 SUS-flagged packages confirmed genuine — no rejections, no langchain-chroma requested.
- Added exact-pinned LangChain/LangGraph block to `backend/requirements.txt`, matching the file's existing `==` pin style (next to the pre-existing `openinference-instrumentation-anthropic` line).
- Installed all 8 packages into `backend/venv` via `backend/venv/bin/pip install`.
- Verified every documented top-level import resolves in a single command: `langchain.agents.create_agent`, `langchain.chat_models.init_chat_model`, `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`, `openinference.instrumentation.langchain.LangChainInstrumentor` — printed `OK 1.3.14`.
- Confirmed `langchain-chroma` absent from `requirements.txt` (`grep -c` returns 0) and `backend/venv/bin/pip show langchain` reports `1.3.14`.
- Ran the full backend test suite after install to confirm no regression; all 12 observed full-suite failures were isolated individually and reproduce identically regardless of the new packages (see Deviations/Issues below) — none are caused by this plan.

## Task Commits

1. **Task 1: Legitimacy checkpoint** - human approval recorded in prior session (no file changes of its own; no commit — approval gates Task 2's install)
2. **Task 2: Pin and install the LangChain runtime block** - `2cfa0d2` (feat)

**Plan metadata:** (this SUMMARY's commit, following)

## Files Created/Modified
- `backend/requirements.txt` - Added an 8-line "LangChain / LangGraph Orchestration (Phase 39)" block with exact version pins, placed in the existing AI & Machine Learning section next to `openinference-instrumentation-anthropic`.

## Decisions Made
- Followed the plan exactly: exact `==` pins, `langgraph-checkpoint-sqlite==3.1.0` included despite being absent from AI-SPEC's list (per RESEARCH.md's Wave 0 Gaps), `langchain-chroma` excluded.
- No architectural changes — additive dependency install only, existing `anthropic` SDK stack untouched.

## Deviations from Plan

None - Task 2 executed exactly as written. The 8 packages installed with all documented imports resolving on the first attempt (`OK 1.3.14`).

### Issues Observed (not deviations — pre-existing, out of scope)

1. **pip dependency-resolver warning (non-fatal):** installing the LangChain block upgraded the transitive `opentelemetry-sdk` from `1.42.1` to `1.44.0`, which pip flagged as incompatible with `opentelemetry-exporter-otlp-proto-grpc==1.42.1`'s pin (`~=1.42.1`). That grpc-exporter package is not referenced by any `.py` file in the codebase (nothing imports `opentelemetry.exporter.otlp.proto.grpc`) and `backend/requirements.txt` only pins the `-http` variant, which stayed compatible. `import app_startup` succeeds cleanly (only the expected dev-mode `JWT_SECRET_KEY` warning) confirming no runtime breakage. No fix applied — logged for awareness only.
2. **12 full-suite test failures, all pre-existing and unrelated to this plan** — logged in detail to `.planning/phases/39-langchain-ai-integration/deferred-items.md`. Summary: 3 files fail at collection due to live-network calls (no internet in this sandbox), 2 more need live external services, 2 need a live MongoDB connection (none running here), 6 in `test_agentic_ai.py` are an order-dependent event-loop flake that passes 8/8 in isolation, and 2 (`test_e2e_integration.py`, `test_rust_heartbeat_parity.py`) reproduce identically in isolation with a pre-existing `agent_type` field bug unrelated to `backend/requirements.txt`. None involve the new LangChain packages; all excluded from this plan's scope per the SCOPE BOUNDARY rule.

## Issues Encountered

None blocking. See "Issues Observed" above for non-blocking, pre-existing findings logged to `deferred-items.md`.

## User Setup Required

None - no external service configuration required. (LLM provider API keys for `langchain-openai`/`langchain-anthropic`/`langchain-ollama` runtime usage are handled by later Phase 39 plans, not this install-only plan.)

## Next Phase Readiness

- `backend/venv` now has the full LangChain 1.x/LangGraph runtime stack available; every downstream Phase 39 plan (39-02 through 39-12) can import `langchain`, `langgraph`, `langchain_openai`, `langchain_anthropic`, `langchain_ollama`, and the `openinference` LangChain instrumentor without further install steps.
- `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver` confirmed importable — unblocks any plan needing a production async checkpointer.
- No blockers for 39-02.

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: backend/requirements.txt
- FOUND: .planning/phases/39-langchain-ai-integration/39-01-SUMMARY.md
- FOUND: .planning/phases/39-langchain-ai-integration/deferred-items.md
- FOUND: commit 2cfa0d2
