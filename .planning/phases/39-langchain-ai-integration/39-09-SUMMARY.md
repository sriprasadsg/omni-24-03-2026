---
phase: 39-langchain-ai-integration
plan: 09
subsystem: ai
tags: [langchain, langgraph, create_agent, pydantic, structured-output, compliance-reports, pdf]

requires:
  - phase: 39-langchain-ai-integration
    provides: "39-03 shared ai_orchestration schemas (NarrativeOutput) + validate_framework_fidelity; 39-04 per-tenant model factory (build_model_for_tenant, model_provenance); 39-05 versioned prompts (NARRATIVE_SYSTEM_PROMPT, PROMPT_VERSION) + guardrail hooks (scan_input/scan_output/cross_tenant_output_scan) + decision_log.log_ai_decision"
provides:
  - "agents/narrative.py: create_agent-based executive-summary and per-framework findings-narrative generation with NarrativeOutput structured output, word-budget validation, framework-fidelity flagging, and a fail-closed fallback"
  - "compliance_narrative_service.py rewritten as a thin shim preserving generate_executive_summary/generate_framework_narrative/enrich_report_data/_render_narratives"
affects: [39-11-eval-code-dimensions, 39-12-eval-llm-judged-dimensions, scheduled-compliance-reports]

tech-stack:
  added: []
  patterns:
    - "Never trust a model's self-reported NarrativeOutput.word_count/.limit — always recompute via NarrativeOutput.from_raw(actual_text, limit=budget) before treating a narrative as validated"
    - "Per-call-site word budget (executive 150, framework 200) threaded through a single shared _generate() helper parameterized by kind/system_prompt/word_budget/fallback_text"

key-files:
  created:
    - backend/ai_orchestration/agents/narrative.py
    - backend/tests/test_narrative_agent.py
  modified:
    - backend/compliance_narrative_service.py
    - backend/tests/test_compliance_narrative_service.py

key-decisions:
  - "generate_executive/generate_framework in agents/narrative.py take tenant_id and db as required positional params (not in the plan's literal signature sketch) since build_model_for_tenant/log_ai_decision require db — mirrors evaluate_control/generate_draft's own db param in 39-06/39-08"
  - "compliance_narrative_service.py's public generate_executive_summary/generate_framework_narrative keep their exact pre-39-09 4-arg signatures, with two new optional trailing tenant_id/db kwargs; enrich_report_data (which already has both as real params) passes them explicitly per RESEARCH Pitfall B, any other caller falls back to ambient tenant_context.get_tenant_id()/database.get_database() resolution, mirroring ai_auditor_service.py's shim (39-06)"
  - "Framework-fidelity check (validate_framework_fidelity) failure is treated fail-closed — falls back to the deterministic narrative, not merely a non-blocking log flag — consistent with this phase's fail-closed posture on every other citation/control-ID validation surface (auditor, questionnaire)"
  - "_FRAMEWORK_SYSTEM_PROMPT (the per-framework findings-narrative system prompt) is defined locally in agents/narrative.py rather than added to prompts.py, since prompts.py's own docstring only migrated the executive-summary prompt and prompts.py was not in this plan's file scope"
  - "Rule 1 fix: retargeted test_compliance_narrative_service.py's 5 pre-existing tests that patched compliance_narrative_service.ai_service (attribute no longer exists) onto the new ai_orchestration.agents.narrative.build_model_for_tenant/create_agent boundary — same precedent as 39-07's test_ai_assistant.py retarget"

requirements-completed: [AISPEC-39-S4, AISPEC-39-S4b, AISPEC-39-S6, AISPEC-39-S7, RESEARCH-Pat3]

duration: ~35min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 09: create_agent narrative generation Summary

**Executive summary and per-framework findings narratives now run through a `create_agent` requesting `NarrativeOutput` structured output, with word-budget validation always recomputed from the actual model text (never a self-reported field), fail-closed fallback on any validation/guardrail/framework-fidelity failure, and the exact pre-existing public API preserved by a thin shim.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-18T09:54:00Z (session continuation from 39-08)
- **Completed:** 2026-07-18T10:10:00Z
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `backend/ai_orchestration/agents/narrative.py` — `generate_executive`/`generate_framework` build a per-tenant `create_agent` (no tools; narrative summarizes caller-supplied data) requesting `NarrativeOutput` via `ToolStrategy` (the 39-02/39-04 router structured-output passthrough is `FAIL`), running guardrails (`scan_input`/`scan_output`/`cross_tenant_output_scan`), the framework-fidelity sweep (`validate_framework_fidelity`, T-39-09-B), span attributes, and `log_ai_decision` on every exit path
- `backend/compliance_narrative_service.py` rewritten as a shim: `generate_executive_summary`/`generate_framework_narrative` keep their exact signatures and `str` return type; `enrich_report_data`, `_render_narratives`, `_sanitise`, and `NarrativeOutput` all preserved (the latter two re-exported from the new canonical locations)
- `backend/tests/test_narrative_agent.py` — 17 new hermetic tests (12 `-k agent`, 5 `-k shim`)
- Retargeted the 5 pre-existing `test_compliance_narrative_service.py` tests whose `compliance_narrative_service.ai_service` mock target no longer exists — all 8 tests in that file pass unchanged in behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: create_agent narrative generation (agents/narrative.py)** - `995f295` (feat)
2. **Task 2: compliance_narrative_service.py shim** - `a8015d7` (feat, includes the Rule 1 test retarget)
3. **Task 3: Narrative agent + shim unit tests** - `db00e30` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/ai_orchestration/agents/narrative.py` - `create_agent`-based narrative generation (366 lines)
- `backend/compliance_narrative_service.py` - thin shim delegating to the agent (224 lines, down from the original hand-rolled implementation)
- `backend/tests/test_narrative_agent.py` - 17 hermetic unit tests (459 lines)
- `backend/tests/test_compliance_narrative_service.py` - 5 tests retargeted onto the new call-graph boundary; all 8 tests still pass

## Decisions Made
See `key-decisions` in frontmatter above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Retargeted test_compliance_narrative_service.py's ai_service mocks**
- **Found during:** Task 2 verification (`pytest backend/tests/test_compliance_narrative_service.py -q -k shim` and the phase-level `test_compliance_narrative_service.py` acceptance criterion)
- **Issue:** 5 of the 8 pre-existing tests patched `compliance_narrative_service.ai_service`, an attribute the rewritten shim no longer has (`AttributeError: ... does not have the attribute 'ai_service'`) — the shim now delegates to `ai_orchestration.agents.narrative`, not `ai_service.generate_text`
- **Fix:** Added a shared `_narrative_agent_patches(text)` helper patching `ai_orchestration.agents.narrative.build_model_for_tenant`/`.create_agent` (stubbed agent returning a canned `structured_response.text`), `guardrail_service.scan_and_log`, `compliance_narrative_service.get_tenant_id`, and `database.get_database` — mirrors `test_auditor_agent.py`'s/`test_ai_assistant.py`'s established retargeting convention. Behavioral assertions (str return, word-budget enforcement, BLOCKED:/Error: fallback) are unchanged.
- **Files modified:** `backend/tests/test_compliance_narrative_service.py`
- **Verification:** `pytest backend/tests/test_compliance_narrative_service.py -q` → 8 passed
- **Committed in:** `a8015d7` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added `db`/`tenant_id` as required params on `agents/narrative.py`'s public functions**
- **Found during:** Task 1 implementation
- **Issue:** The plan's action text sketches `generate_executive(framework_name, score, failing_controls, period, tenant_id)`/`generate_framework(..., tenant_id)` without a `db` parameter, but `build_model_for_tenant(tenant_id, db, surface)` and `log_ai_decision(db, ...)` both require one
- **Fix:** Added `db: Any` as a required trailing positional parameter on both functions, matching `agents/auditor.py::evaluate_control`'s and `agents/questionnaire.py::generate_draft`'s own `(..., tenant_id, db, ...)` shape. `compliance_narrative_service.py`'s shim resolves `db` (and `tenant_id`) itself before calling down, so the public shim signature the must_haves lock (`generate_executive_summary`/`generate_framework_narrative`) is unaffected.
- **Files modified:** `backend/ai_orchestration/agents/narrative.py`
- **Verification:** `pytest backend/tests/test_narrative_agent.py -q` → 17 passed
- **Committed in:** `995f295` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug fix in a pre-existing test file, 1 necessary parameter addition)
**Impact on plan:** Both required for correctness — narrative.py cannot reach a model/log a decision without `db`, and the pre-existing test suite would otherwise fail outright on every re-run. No scope creep beyond what Task 2's own acceptance criteria already mandated.

## Issues Encountered
None beyond the two deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All four AI-surface migrations this phase set out to do (auditor 39-06, chat 39-07, questionnaire 39-08, narrative 39-09) are now complete, sharing the same `create_agent` + structured-output + guardrail + provenance + decision-log pattern
- Full backend suite: 1104 passed / 23 skipped / 2 failed (both pre-existing, unrelated: `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`)
- Remaining for Phase 39: 39-11 (code-based eval dimensions) and 39-12 (LLM-judged eval dimensions), scoring against the 39-10 reference dataset

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

All created/modified files verified present on disk; all 3 task commits (995f295, a8015d7, db00e30) verified present in git log.
