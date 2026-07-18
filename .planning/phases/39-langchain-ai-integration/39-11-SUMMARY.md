---
phase: 39-langchain-ai-integration
plan: 11
subsystem: testing
tags: [pytest, eval-harness, langchain, tenant-isolation, guardrails, provenance]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration
    provides: "39-03 validators (validate_citations/validate_framework_fidelity), 39-05 tenant-closed tools + guardrails, 39-06..09 migrated agents (auditor/chat/questionnaire/narrative), 39-10 reference dataset + loaders + eval tenants/canaries"
provides:
  - "Six code-based eval dimensions as pytest gates under -m 'eval and not llm' (deterministic, zero token spend): evidence traceability, framework fidelity, conservative status (false-pass), tenant confidentiality (adversarial canary), fallback provenance, RAG-02 approval gate"
  - "The CI gate command from AI-SPEC Section 5 is real: pytest backend/tests/eval_langchain/ -m 'eval and not llm' selects 110 tests, all green"
affects: [39-12-llm-judged-eval-dimensions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Canned-from-gold deterministic eval: stub only the model call graph (create_agent/build_model_for_tenant) with structured responses built from gold records, run the REAL validation/guardrail/provenance pipeline (evaluate_control, validate_citations, model_provenance) against a mocked db seeded from the fixtures"
    - "Malicious-model adversarial harness: the create_agent stub actively parrots injected instructions into the REAL tenant-closed tools against a tenant-filter-honoring fake RAG store seeded with tenant-B canaries whose reachability-as-tenant-B is sanity-proved — a broken closure would leak, and the assertion is zero canary hits plus closed-over tenant filters in every captured tool-call arg"
    - "Metric tripwire tests: each gate ships a negative control proving it detects the failure it exists for (fabricated citation blocked, inflated pass counted as false-pass, canaries reachable as tenant B)"

key-files:
  created:
    - backend/tests/eval_langchain/test_traceability.py
    - backend/tests/eval_langchain/test_framework_fidelity.py
    - backend/tests/eval_langchain/test_conservative_status.py
    - backend/tests/eval_langchain/test_tenant_isolation.py
    - backend/tests/eval_langchain/test_fallback_provenance.py
    - backend/tests/eval_langchain/test_rag02_gate.py
  modified:
    - backend/tests/conftest.py
    - backend/tests/eval_langchain/test_router_passthrough.py
    - backend/tests/test_agentic_ai.py

key-decisions:
  - "39-11: gold fixtures carry no per-entry severity field, so the false-pass zero-tolerance bar is applied to ALL 20 gold controls (strict superset of 'Critical/High only'); the < 5% overall bar is still asserted separately to match the spec's two-tier rule"
  - "39-11: the tool-call-args half of AISPEC-39-S7 is asserted against in-process captured call args (fake RAG store call log + asset_compliance filter capture) on the deterministic path — the Phoenix-trace variant of the same assertion belongs to the live 39-12 run"
  - "39-11: zero-evidence trap controls (no gold citations) are exercised through control-ID-only resolution plus the agent's own n/a-citation fail-closed path rather than fabricating citations for them — 'we cannot cite' correctly remains a blocked/insufficient outcome"
  - "39-11: fallback forcing simulates what .with_fallbacks resolution actually leaves behind (the fallback model's name in response_metadata, vs the tenant's configured primary in system_settings) so the real model_provenance() helper and each surface's real stamping/escalation logic run unmodified"

requirements-completed: [AISPEC-39-S5, AISPEC-39-S6, AISPEC-39-S1, AISPEC-39-S7]

# Metrics
duration: ~35min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 11: Code-Based Eval Dimensions Summary

**Six deterministic, zero-token eval dimensions now gate the phase under `-m "eval and not llm"` (110 tests green): traceability 100%, framework-fidelity bait flagged, false-pass 0, zero canary hits with closed-over tenant filters, fallback provenance on all four surfaces, and the RAG-02 no-approver-no-submit state machine.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-18
- **Tasks:** 3 (+1 unplanned regression fix)
- **Files:** 6 new eval test files, 3 modified (regression fixes)

## Accomplishments
- `test_traceability.py` (41 tests): every gold citation resolves through the REAL `validate_citations` wired into `evaluate_control` (100% pass asserted as an aggregate plus per-control), all 20 gold control IDs resolve in the seeded registry, and tripwires prove fabricated citations/unknown control IDs are blocked and downgraded.
- `test_framework_fidelity.py` (29 tests): `extract_control_id_tokens` + `validate_framework_fidelity` flag the adversarial fabricated-control-ID baits ("SOC 2 CC9.9", "ISO27001-A.99.9") while every real registry ID and all 20 gold rationales pass; framework names alone ("SOC 2", "ISO 27001") never false-positive.
- `test_conservative_status.py` (9 tests): `false_pass_count` against gold labels — 0 on all controls (severity superset) and < 5% overall; both context-dependent `insufficient_evidence` traps covered; tripwire proves an optimistic model with resolvable citations still registers as false-pass (citation validation alone cannot save it).
- `test_tenant_isolation.py` (15 tests): the full 10-entry adversarial suite runs as tenant A across auditor/chat/questionnaire with a malicious model stub parroting injections into the REAL tenant-closed tools; zero canary hits in any output surface, every captured retrieval/evidence call carries the closed-over tenant-A filter, tool schemas structurally expose no tenant parameter, and canary reachability as tenant B is sanity-proved.
- `test_fallback_provenance.py` (8 tests): forced-fallback response metadata drives the real `model_provenance()`; auditor/questionnaire/narrative outputs carry `fallback:<model>`, chat stamps it into the decision log, and a fallback-produced `pass` finding is flagged `needs_review` (non-pass is not).
- `test_rag02_gate.py` (8 tests): drafts always land `pending_review` regardless of confidence; `submitted` is only reachable from `approved` via `mark_submitted` with a mandatory `submitted_by` identity; `"submitted"` is not a valid reviewer decision; approval stops at `approved` — no auto-advance path.

## Task Commits

1. **Task 1: Traceability + framework fidelity** - `fafcb39` (test)
2. **Task 2: Conservative-status false-pass gate** - `8fac231` (test)
3. **Task 3: Tenant isolation, fallback provenance, RAG-02 gate** - `e11eb69` (test)
4. **Regression fix (unplanned): collection-order fragilities** - `fca3d14` (fix)

## Files Created/Modified
- 6 new files under `backend/tests/eval_langchain/` (see key-files)
- `backend/tests/test_agentic_ai.py` — deprecated `asyncio.get_event_loop()` → `asyncio.new_event_loop()` (6 sites)
- `backend/tests/conftest.py` — pre-dotenv `_AI_ROUTER_URL_PRE_DOTENV` sentinel
- `backend/tests/eval_langchain/test_router_passthrough.py` — skip guard reads the sentinel

## Decisions Made
See `key-decisions` in frontmatter.

## Deviations from Plan

**[Rule 1 - Bug] Fixed two pre-existing collection-order fragilities the new suite exposed (commit `fca3d14`, 3 files outside the plan's `files_modified` list):**
1. `test_agentic_ai.py`'s sync tests called deprecated `asyncio.get_event_loop()`, which only worked while no pytest-asyncio test ran earlier in collection order — the new `eval_langchain` tests (alphabetically first) left no loop set on MainThread, failing 6 unrelated tests.
2. `test_router_passthrough.py`'s skip guard read `os.environ` at import time, but the new eval modules transitively import `database.py`, whose module-level `load_dotenv()` leaks `backend/.env`'s stale `AI_ROUTER_URL` into the environment mid-collection — un-skipping the live 9router smoke test in this gateway-less sandbox (it then failed with a live 404 against the unreachable gateway). The guard now reads a sentinel captured in `backend/tests/conftest.py` before any test module imports, so only a shell-exported `AI_ROUTER_URL` opts in; the sentinel lives in `os.environ` (not a module attribute) because pytest and test code import conftest under different module names, which re-executes module-level code.

Both verified: full backend suite returns to the parent-commit baseline (2 pre-existing failures: `test_e2e_integration::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity::test_rust02_and_rust03_db_calls` — identical on the parent commit, unrelated to Phase 39).

## Issues Encountered
None beyond the deviation above.

## User Setup Required

None.

## Next Phase Readiness

- 39-12 (LLM-judged eval dimensions) can reuse this plan's canned-from-gold and adversarial harness patterns, swapping the model stubs for live gateway calls under the `llm` marker; the tool-call-args assertion should move to Phoenix trace attributes there.
- CI gate command verified exactly as AI-SPEC Section 5 specifies: `backend/venv/bin/python -m pytest backend/tests/eval_langchain/ -m "eval and not llm" -q` → 110 passed, 1 deselected (the live router smoke, correctly `llm`-marked).

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

- All 6 created files present on disk; `test_traceability.py` contains `validate_citations`, `test_tenant_isolation.py` contains `canary` (grep >= 1), `test_conservative_status.py` contains `false_pass`.
- Task commits `fafcb39`, `8fac231`, `e11eb69`, `fca3d14` present in `git log --oneline`.
- Verification commands: eval gate 110 passed / 1 deselected (exit 0, non-zero count); full backend suite at pre-existing baseline.
