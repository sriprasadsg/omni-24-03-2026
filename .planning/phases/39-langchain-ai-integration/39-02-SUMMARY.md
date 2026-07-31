---
phase: 39-langchain-ai-integration
plan: 02
subsystem: testing
tags: [pytest, langchain, langgraph, eval-harness, tenant-isolation, 9router]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration
    plan: "01"
    provides: LangChain 1.x/LangGraph runtime stack installed and import-verified in backend/venv
provides:
  - Live 9router tools/response_format passthrough smoke test with a recorded PASS/FAIL decision + downstream path
  - Registered eval/llm pytest markers (root pytest.ini) — silences PytestUnknownMarkWarning
  - backend/tests/eval_langchain/ scaffold package + conftest.py two-tenant canary fixtures
  - backend/tests/eval_langchain/data/README.md reference-dataset layout doc for 39-10/39-11/39-12
affects: [39-06, 39-07, 39-08, 39-09, 39-10, 39-11, 39-12]

# Tech tracking
tech-stack:
  added: []
  patterns: [pytest markers section registers eval/llm without global --strict-markers, graceful try/except ImportError around langchain/rag_service imports mirroring backend/tests/eval_questionnaire_auto_answer.py]

key-files:
  created:
    - backend/tests/eval_langchain/__init__.py
    - backend/tests/eval_langchain/test_router_passthrough.py
    - backend/tests/eval_langchain/conftest.py
    - backend/tests/eval_langchain/data/README.md
  modified:
    - pytest.ini

key-decisions:
  - "9router passthrough decision: UNRESOLVED-IN-THIS-SANDBOX (no live network to AI_ROUTER_URL here, consistent with 39-01-SUMMARY.md's documented sandbox limitation) — test skips cleanly rather than erroring. Per this plan's own context_notes guidance, downstream agent plans (39-06/39-07/39-08/39-09) should adopt the documented fallback path conservatively (native langchain-anthropic ChatAnthropic direct route, or ToolStrategy tool-call emulation, AI-SPEC Section 4b/Pitfall 6) until this smoke test is re-run in an environment with live AI_ROUTER_URL access and produces a real PASS."
  - "Force-added backend/tests/eval_langchain/data/README.md with git add -f — root .gitignore has a blanket data/ rule (intended for runtime dirs like chroma_db) that would otherwise silently exclude this plan-mandated test-fixture doc"
  - "Did not add --strict-markers globally (plan explicitly forbids it — would break the wider suite's existing ad-hoc marks); registering eval/llm in pytest.ini markers= is sufficient to silence PytestUnknownMarkWarning for just these two"

patterns-established:
  - "Eval harness tests live under backend/tests/eval_langchain/, marked `eval` (code-based/judged, cheap) and additionally `llm` (spends tokens / needs a live model) — CI gate is `-m \"eval and not llm\"`"
  - "Tenant-scoped eval fixtures: eval_tenant_a (subject) / eval_tenant_b (canary source) + canary_strings tuple + seed_tenant_evidence factory fixture in conftest.py, for reuse by every later eval plan"

requirements-completed: [AISPEC-39-S3, AISPEC-39-S5, RESEARCH-OQ3, RESEARCH-PitE]

# Metrics
duration: ~15min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 02: 9router Passthrough Smoke Test + Eval Harness Scaffold Summary

**Live `create_agent(response_format=...)` + tool-call smoke test against the 9router gateway (skips cleanly, no live network in this sandbox), registered `eval`/`llm` pytest markers, and a two-tenant canary-fixture eval harness scaffold at `backend/tests/eval_langchain/`.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2/2 completed
- **Files modified:** 5 (2 created for Task 1, 3 for Task 2)

## Accomplishments

- Built `backend/tests/eval_langchain/test_router_passthrough.py`: a live smoke test using `init_chat_model(model_provider="openai", base_url=AI_ROUTER_URL)` + `create_agent` to probe (a) bound-tool-call passthrough (`echo` tool) and (b) `response_format` structured-output passthrough (`EchoResponse` two-field Pydantic schema) through the 9router gateway — the exact go/no-go check RESEARCH Open Question 3 called for.
- Test uses `ainvoke` exclusively (no bare `.invoke(`, no `asyncio.run(`), decorated `eval` + `llm`, and `pytest.mark.skipif(not AI_ROUTER_URL or not LANGCHAIN_AVAILABLE, ...)` so a gateway-less environment skips cleanly instead of failing collection.
- On success/failure the test prints a machine-readable line (`[9ROUTER_PASSTHROUGH_DECISION] result=PASS|FAIL downstream_path=...`) so future runs in an environment with `AI_ROUTER_URL` reachable surface the decision directly in pytest output.
- Registered `eval`/`llm` markers in root `pytest.ini` (no `--strict-markers` added, per plan) — confirmed `PytestUnknownMarkWarning` promoted to a hard error still collects cleanly (`MARKERS_OK`) and `--collect-only -m eval` selects the 1 passthrough test (non-zero, closing RESEARCH Pitfall E's silent-no-op gap).
- Built `backend/tests/eval_langchain/conftest.py`: session fixtures `eval_tenant_a` (`eval-tenant-subject-a`), `eval_tenant_b` (`eval-tenant-canary-b`), a `canary_strings` tuple of synthetic sentinel values, a `seed_tenant_evidence` factory fixture (wraps `rag_service.ingest_text`, self-cleans via `collection.delete`), and a `canary_probe_id` per-test UUID helper.
- Documented the AI-SPEC Section 5 reference-dataset target layout (48 examples: 20 gold controls, 10 questionnaire Q&A, 8 chat questions, 10 adversarial inputs) in `backend/tests/eval_langchain/data/README.md` for 39-10 to populate and 39-11/39-12 to consume.

## Task Commits

1. **Task 1: Live 9router passthrough smoke test + fallback decision record** - `009a13f` (feat)
2. **Task 2: Register eval/llm markers + two-tenant eval fixtures** - `4d96aff` (feat)

**Plan metadata:** (this SUMMARY's commit, following)

## Files Created/Modified

- `backend/tests/eval_langchain/__init__.py` - New package marker with a docstring pointing at the marker-registration/eval-strategy docs.
- `backend/tests/eval_langchain/test_router_passthrough.py` - Live tool-call + `response_format` passthrough smoke test against the 9router gateway; skips cleanly when `AI_ROUTER_URL` is unset.
- `backend/tests/eval_langchain/conftest.py` - Two-tenant (`eval_tenant_a`/`eval_tenant_b`) + canary-string + evidence-seeding fixtures shared by all later eval plans.
- `backend/tests/eval_langchain/data/README.md` - Reference-dataset (48-example) target layout and labeling-ownership doc.
- `pytest.ini` - Added `[pytest] markers =` section registering `eval` and `llm`.

## Decisions Made

- **9router passthrough decision (RESEARCH Open Question 3): UNRESOLVED-IN-THIS-SANDBOX, treated conservatively as FAIL for now.** `AI_ROUTER_URL` is unset in this execution environment (no live network to external services, consistent with 39-01-SUMMARY.md's documented sandbox limitation) — the smoke test skips rather than running live, so no PASS could be produced this session. Per the plan's own `context_notes` instruction ("if the live smoke test cannot reach the gateway, record the documented fallback decision... rather than failing the plan"), the recorded downstream decision is: **agent-migration plans 39-06/39-07/39-08/39-09 should build against the documented fallback path** (native `langchain-anthropic` `ChatAnthropic` direct route, or `ToolStrategy` tool-call emulation — AI-SPEC Section 4b / Pitfall 6) rather than assuming `create_agent(response_format=...)` works unmodified through the gateway, **until this test is re-run in an environment with live `AI_ROUTER_URL` access and prints a PASS**. The test itself requires no code changes to re-run live — just execute `backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_router_passthrough.py -m "eval and llm" -q` with `AI_ROUTER_URL`/`AI_ROUTER_KEY` set in the environment.
- **Force-added `data/README.md` past `.gitignore`'s blanket `data/` rule.** The repo's root `.gitignore` excludes any directory literally named `data/` anywhere (intended for runtime dirs like `data/chroma_db`), which silently swallowed this plan-mandated test-fixture doc. Used `git add -f` for this one file rather than editing `.gitignore` (out of scope — the blanket rule likely protects other runtime data dirs and editing it wasn't part of this plan).
- Followed the plan's explicit instruction not to add `--strict-markers` globally.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.gitignore`'s blanket `data/` rule silently excluded the required `data/README.md`**
- **Found during:** Task 2 (pre-commit `git status` check)
- **Issue:** `git status --short` showed no entry for `backend/tests/eval_langchain/data/README.md` after `git add`; `git check-ignore -v` confirmed the root `.gitignore` line `data/` matches this path even though it was written for runtime data directories, not test fixtures.
- **Fix:** `git add -f backend/tests/eval_langchain/data/README.md` to force-track this specific plan-mandated file; did not modify `.gitignore` itself (out of scope for this plan).
- **Files modified:** none beyond the intended `data/README.md` (no `.gitignore` edit)
- **Verification:** `git status --short` confirmed the file staged as `A` before commit; `git show 4d96aff --stat` confirms it landed in the commit.
- **Committed in:** `4d96aff` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — gitignore force-add)
**Impact on plan:** Necessary to satisfy the plan's own `files_modified`/`must_haves.artifacts` contract for `data/README.md`. No scope creep — no other files touched, `.gitignore` left as-is.

## Issues Encountered

None blocking. The 9router gateway being unreachable in this sandbox was anticipated by the plan's own `context_notes` and handled per its documented fallback-decision instruction (see Decisions Made above) — not an unplanned problem.

## User Setup Required

None for this plan. To actually resolve the 9router passthrough PASS/FAIL decision, a future session needs `AI_ROUTER_URL`/`AI_ROUTER_KEY` set to a reachable 9router gateway and to re-run:
```bash
backend/venv/bin/python -m pytest backend/tests/eval_langchain/test_router_passthrough.py -m "eval and llm" -q
```

## Next Phase Readiness

- `pytest.ini` markers are real; `pytest --collect-only -m eval` selects a non-zero count (currently 1 — will grow as 39-10/39-11/39-12 add code-based eval tests).
- `backend/tests/eval_langchain/conftest.py`'s `eval_tenant_a`/`eval_tenant_b`/`canary_strings`/`seed_tenant_evidence` fixtures are ready for 39-10 (reference dataset) and 39-11/39-12 (code-based and judged eval dimensions) to build on directly — no re-scaffolding needed.
- **Blocker/open item for 39-06 through 39-09:** the 9router `tools`/`response_format` passthrough question remains genuinely unresolved (sandbox has no live network). Those plans should either (a) implement against the documented fallback path defensively, or (b) re-run this plan's smoke test first in an environment with gateway access before committing to the direct `response_format` approach.
- CI code-based gate `pytest backend/tests/eval_langchain/ -m "eval and not llm" -q` currently selects 0 tests (expected — the only test in this scaffold is `llm`-marked; code-based dimension tests are Wave-later per `39-RESEARCH.md`'s Phase Requirement Support Map, all marked `❌ Wave 0`).

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: backend/tests/eval_langchain/__init__.py
- FOUND: backend/tests/eval_langchain/test_router_passthrough.py
- FOUND: backend/tests/eval_langchain/conftest.py
- FOUND: backend/tests/eval_langchain/data/README.md
- FOUND: pytest.ini
- FOUND: .planning/phases/39-langchain-ai-integration/39-02-SUMMARY.md
- FOUND: commit 009a13f
- FOUND: commit 4d96aff
