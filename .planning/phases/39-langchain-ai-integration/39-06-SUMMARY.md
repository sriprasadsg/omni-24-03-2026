---
phase: 39-langchain-ai-integration
plan: "06"
subsystem: ai
tags: [langchain, create_agent, audit-finding, citation-validation, guardrails, provenance, ai_orchestration]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration
    plan: "03"
    provides: "backend/ai_orchestration/schemas.py + validators.py — AuditFinding schema + validate_citations/validate_framework_fidelity"
  - phase: 39-langchain-ai-integration
    plan: "04"
    provides: "backend/ai_orchestration/models.py — build_model_for_tenant, model_provenance, ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH; memory.py — make_thread_id; tracing.py — attach_span_attributes"
  - phase: 39-langchain-ai-integration
    plan: "05"
    provides: "backend/ai_orchestration/tools/retrieval.py + tools/evidence.py, prompts.py, guardrails.py, decision_log.py"
provides:
  - "backend/ai_orchestration/agents/auditor.py: evaluate_control() — create_agent auditor with ToolStrategy(AuditFinding) structured output, validate_citations wired in, guardrail hooks, fallback-provenance needs_review escalation, decision logging"
  - "backend/ai_auditor_service.py: LocalAIAuditor/get_auditor() rewritten as a thin shim delegating to evaluate_control, preserving evaluate_evidence()'s exact signature and {verified, reasoning, raw_response, evaluatedAt} return shape"
  - "backend/tests/test_auditor_agent.py: 14 hermetic unit tests (-k agent, -k shim)"
affects: [39-07, 39-08, 39-09, 39-11]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One create_agent per audit surface, built fresh per evaluate_control() call (per-control independent invocation, InMemorySaver checkpointer) rather than a long-lived agent instance — matches AI-SPEC Section 4b's 'each control assessed as an independent agent invocation, fresh context' compaction-by-design guidance"
    - "AuditEvaluationResult dataclass ({finding, model_provenance, citation_validation, needs_review}) as the internal agent-layer return contract, adapted to the legacy {verified, reasoning, raw_response, evaluatedAt} dict only at the shim boundary"
    - "Raw-db unwrap (db._db) before calling shared validators/tools that do their own explicit tenant+global scoping — mirrors models.py's existing unwrap, now established as the pattern every agent-surface plan (39-07..09) must follow when wiring validate_citations/tool factories to a real TenantIsolatedDatabase handle"

key-files:
  created:
    - backend/ai_orchestration/agents/auditor.py
    - backend/tests/test_auditor_agent.py
  modified:
    - backend/ai_auditor_service.py

key-decisions:
  - "db passed to validate_citations/make_get_control_evidence/model-name lookup is unwrapped to the raw Motor handle (db._db) — asset_compliance/control_evidence/system_settings are NOT in database.py's tenant-isolation exemption list, so TenantIsolatedCollection would otherwise inject a second top-level tenantId filter on top of validate_citations' explicit tenant+global $or scope, silently excluding global-KB citations from ever resolving in production. log_ai_decision still receives the original (possibly wrapped) db, since its insert_one relies on that same auto-injection by design (39-05 docstring)."
  - "control_id added as an optional trailing kwarg on evaluate_control/evaluate_evidence (not present in the plan's own illustrative signature) because ai_auditor_endpoints.py's real call site never passes one and is out of this plan's file scope. A caller-supplied control_id is pinned onto the returned finding (model_copy override) — never trusted from the model, on top of the structural validate_citations framework-fidelity check. Absent a caller value, falls back to extract_control_id_tokens(control_desc) then the literal UNSPECIFIED, which correctly fails framework-fidelity resolution and downgrades — 'we don't know which control this is' is itself a fail-closed outcome, never a guess."
  - "Always requests structured output via ToolStrategy(AuditFinding, handle_errors=...), never a bare response_format=AuditFinding, because ai_orchestration/models.py's ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH constant is FAIL (39-02/39-04 decision) — the 9router structured-output passthrough is unverified, so this surface never assumes it works unmodified."
  - "A fallback-provenance (model_provenance.startswith('fallback')) pass finding is NOT downgraded in status — it stays 'pass' in the AuditFinding — but AuditEvaluationResult.needs_review is set True. The shim maps needs_review to verified=False with an explicit NEEDS_REVIEW marker in reasoning, since the legacy {verified: bool} contract has no third 'pending human review' state and ai_auditor_endpoints.py's write path could not be changed. This is the strongest guarantee available without modifying the endpoint (Failure Mode 5: never silently equal to a primary pass)."
  - "Every exit path (input-guardrail block, agent-invocation error, missing structured_response, output/cross-tenant-guardrail block, citation-validation failure) returns a fully-formed AuditFinding via _insufficient_evidence_finding() or validators._downgrade() — evaluate_control() never returns a raw/unvalidated model object and never raises past its own try/except boundaries."

patterns-established:
  - "AuditEvaluationResult as the agent-layer return contract for the auditor surface; 39-07/08/09 will each define their own surface-appropriate result dataclass rather than forcing a shared shape across incompatible surfaces (chat streams, questionnaire has its own RAG-02 gate, narrative has a word budget)"
  - "Fail-closed shim mapping: any agent exception -> verified=False with reasoning string; any needs_review result -> verified=False with an explicit marker — never raise into a caller's background task, never silently present degraded output as equivalent to primary output"

requirements-completed: [AISPEC-39-S4, AISPEC-39-S4b, AISPEC-39-S6, AISPEC-39-S7, RESEARCH-Pat3]

coverage:
  - id: D1
    description: "The compliance auditor evaluates evidence through a create_agent built by the model factory (39-04), with tenant-scoped tools (39-05), not a raw two-line VERDICT/REASONING text parse"
    requirement: "AISPEC-39-S4"
    verification:
      - kind: unit
        ref: "backend/tests/test_auditor_agent.py::TestEvaluateControlAgent::test_happy_path_valid_finding_stays_pass"
        status: pass
      - kind: other
        ref: "grep -c 'create_agent' backend/ai_orchestration/agents/auditor.py -> 3 (import + _response_format doc + call site)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every AuditFinding is validated by the shared validate_citations before it is returned/persisted; an unresolvable citation or unknown control_id downgrades the finding to insufficient_evidence"
    requirement: "AISPEC-39-S6 / RESEARCH-Pat3"
    verification:
      - kind: unit
        ref: "backend/tests/test_auditor_agent.py::TestEvaluateControlAgent::test_unresolvable_citation_downgrades_to_insufficient_evidence, ::test_unknown_control_id_rejected"
        status: pass
      - kind: other
        ref: "grep -c 'validate_citations' backend/ai_orchestration/agents/auditor.py -> 7 (>= 1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "ai_auditor_service.get_auditor()/evaluate_evidence() keep their existing return shape {verified, reasoning, raw_response, evaluatedAt} so ai_auditor_endpoints needs no change"
    requirement: "39-CONTEXT.md (old code disposition)"
    verification:
      - kind: unit
        ref: "backend/tests/test_auditor_agent.py::TestAuditorServiceShim (5 tests)"
        status: pass
      - kind: other
        ref: "cd backend && venv/bin/python -c \"from ai_auditor_service import get_auditor\" -> exit 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "Guardrail input/output hooks wrap the agent ainvoke and the finding carries model_provenance (primary vs fallback)"
    requirement: "AISPEC-39-S4b / AISPEC-39-S7"
    verification:
      - kind: unit
        ref: "backend/tests/test_auditor_agent.py::test_input_guardrail_block_skips_agent_invocation, ::test_output_guardrail_block_downgrades_finding"
        status: pass
      - kind: other
        ref: "The four span attribute names (tenant_id, surface, PROMPT_VERSION, model_provenance) appear in the module — grep confirmed"
        status: pass
    human_judgment: false
  - id: D5
    description: "A fallback-produced pass finding is escalated to human review, never silently equal to a primary pass (Failure Mode 5)"
    requirement: "AISPEC-39-S4b (Failure Mode 5)"
    verification:
      - kind: unit
        ref: "backend/tests/test_auditor_agent.py::test_fallback_provenance_pass_flags_needs_review, ::test_fallback_provenance_pass_flagged_needs_review_never_equals_primary_pass"
        status: pass
    human_judgment: false
  - id: D6
    description: "The agent is invoked with ainvoke only — no bare .invoke, no asyncio.run"
    requirement: "AISPEC-39-S4b (async-first design)"
    verification:
      - kind: other
        ref: "grep -Ec '\\.invoke\\(|asyncio\\.run\\(' backend/ai_orchestration/agents/auditor.py -> 0"
        status: pass
    human_judgment: false

# Metrics
duration: ~25min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 06: Compliance Auditor create_agent Migration Summary

**`ai_orchestration/agents/auditor.py::evaluate_control()` replaces the raw VERDICT/REASONING text parse with a `create_agent`-based auditor requesting `ToolStrategy(AuditFinding)` structured output, running every finding through the shared citation/control-ID validator, wrapping the call in guardrails + a cross-tenant scan, and escalating fallback-model passes to `needs_review` — fronted by a thin `ai_auditor_service.py` shim that keeps `get_auditor()`/`evaluate_evidence()`'s exact contract so `ai_auditor_endpoints.py` needed zero changes.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-18
- **Completed:** 2026-07-18
- **Tasks:** 3/3 completed
- **Files modified:** 3 (2 new, 1 rewritten)

## Accomplishments

- Built `backend/ai_orchestration/agents/auditor.py`: `evaluate_control(framework_name, control_desc, evidence_text, tenant_id, db, control_id=None)` builds a per-tenant `create_agent` from the 39-04 model factory (`build_model_for_tenant`) plus the 39-05 tenant-closed `search_evidence`/`get_control_evidence` tools and versioned `AUDITOR_SYSTEM_PROMPT`, always requesting structured output via `ToolStrategy(AuditFinding, handle_errors=...)` per the `ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"` decision from 39-02/39-04. Guardrail `scan_input` runs before the agent call (short-circuits to `insufficient_evidence` on a block, never invoking the agent); `scan_output` + `cross_tenant_output_scan` run after. Every structured response is passed through `validate_citations` — an unresolved citation or unknown `control_id` returns the validator's own downgraded `insufficient_evidence` copy. Provenance is stamped via `model_provenance()`; a fallback-provenance `pass` sets `AuditEvaluationResult.needs_review = True` without altering the finding's own `status`. Every path (including guardrail blocks and agent exceptions) logs a decision via `log_ai_decision` and attaches the four mandatory span attributes.
- Rewrote `backend/ai_auditor_service.py` as a thin compatibility shim: `get_auditor()`/`LocalAIAuditor.evaluate_evidence(framework_name, control_desc, evidence_text, control_id=None)` keeps its exact pre-existing signature and `{verified, reasoning, raw_response, evaluatedAt}` return shape, resolving the acting tenant/db from ambient request context (`tenant_context.get_tenant_id()`, `database.get_database()`) rather than adding new required parameters. `needs_review` results map to `verified=False` with a `NEEDS_REVIEW` marker in `reasoning`; any agent exception maps to `verified=False` with the exception text — never raises into `ai_auditor_endpoints.py`'s background task. `model_id` is set to the finding's `model_provenance` string each call, so `evaluation_record["model_used"]` keeps working unchanged.
- Wrote `backend/tests/test_auditor_agent.py`: 14 hermetic tests. Unlike a fully-mocked citation validator, these tests stub only the model/agent call graph (`create_agent`/`build_model_for_tenant` patched to return canned `structured_response`s, per the plan's own guidance) while letting `validate_citations` run for real against a small mocked `db` — so the citation/control-ID resolution wiring is actually exercised end-to-end, not just assumed. Covers: happy-path pass, unresolvable-citation downgrade, unknown-control-id rejection, fallback-provenance `needs_review` escalation (both for a `pass` and confirming a non-`pass` fallback does NOT need review), input/output guardrail blocks, agent-invocation error (never raises), caller-supplied `control_id` pinning overriding a model-fabricated one, and the shim's `verified`/`reasoning` mapping across all four outcome classes plus its never-raise exception path.

## Task Commits

Each task was committed atomically:

1. **Task 1: create_agent auditor with citation validation + guardrails + provenance** - `e4e3482` (feat)
2. **Task 2: ai_auditor_service.py compatibility shim** - `bfab5e6` (feat)
3. **Task 3: Auditor agent + shim unit tests** - `d7f048f` (test)

**Plan metadata:** (this SUMMARY's commit, following)

## Files Created/Modified

- `backend/ai_orchestration/agents/auditor.py` - `evaluate_control()`, `AuditEvaluationResult` dataclass, raw-db unwrap helper, control-id pinning, provenance/guardrail/citation-validation orchestration.
- `backend/ai_auditor_service.py` - `LocalAIAuditor`/`get_auditor()` rewritten to delegate to `evaluate_control`, preserving the legacy dict contract.
- `backend/tests/test_auditor_agent.py` - 14 hermetic tests across `TestEvaluateControlAgent` (9) and `TestAuditorServiceShim` (5).

## Decisions Made

See `key-decisions` in frontmatter. Most consequential: the raw-db unwrap before calling `validate_citations`/`make_get_control_evidence` (a latent double-tenant-filter bug this plan is the first to expose, since it's the first to wire a real `TenantIsolatedDatabase` handle into those 39-03/39-05 components), and the `needs_review -> verified=False` shim mapping that makes Failure Mode 5's "never silently equal to a primary pass" guarantee hold at the endpoint's actual observable behavior, not just internally.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Raw-db unwrap before validate_citations/make_get_control_evidence/model-name lookup**
- **Found during:** Task 1 (auditor.py implementation)
- **Issue:** `database.py`'s `TenantIsolatedCollection` auto-injects a top-level `tenantId` equality filter on any collection not in its exemption allowlist. `asset_compliance`, `control_evidence`, and `system_settings` are NOT exempt. `validate_citations`' `_resolve_chunk_id` builds an explicit `{"id": chunk_id, "$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]}` filter — if the wrapped `TenantIsolatedDatabase` handle were passed straight through, the auto-injected top-level `tenantId` equality would additionally require an exact match, silently excluding every `tenantId: "global"` KB citation from ever resolving in production (they'd all incorrectly downgrade to `insufficient_evidence`).
- **Fix:** Added `_raw_db(db)` (`getattr(db, "_db", db)`) and pass the raw handle to `validate_citations`, `make_get_control_evidence`, and the best-effort model-name lookup — mirroring the identical unwrap `ai_orchestration/models.py` already applies to `system_settings` reads for the same reason. `log_ai_decision` still receives the original (possibly wrapped) `db`, since its `insert_one` relies on `TenantIsolatedCollection`'s auto-injection by design.
- **Files modified:** backend/ai_orchestration/agents/auditor.py
- **Verification:** `test_happy_path_valid_finding_stays_pass` resolves a `cev-1` citation correctly through the real (non-`_db`-attributed) mocked db; no regression possible to catch the wrapped-db case hermetically since the mock db has no `_db` attribute (falls through to itself either way) — the fix is a defensive correctness improvement for the real `TenantIsolatedDatabase` production path, not something the hermetic suite alone could have caught.
- **Committed in:** e4e3482 (Task 1 commit)

**2. [Rule 2 - Missing Critical] control_id threaded through as an optional parameter, pinned defense-in-depth**
- **Found during:** Task 1 (auditor.py implementation)
- **Issue:** `ai_auditor_endpoints.py`'s real call site (`await auditor.evaluate_evidence(framework_name=..., control_desc=..., evidence_text=...)`) never passes a `control_id`, even though the loop it's called from has one (`control_id = ac.get("controlId")`). Without it, the model would have to invent a `control_id` for every `AuditFinding` from context alone — directly reintroducing the fabricated-control-ID failure mode (Failure Mode 2) this entire plan exists to close, and undermining the framework-fidelity validation's usefulness.
- **Fix:** Added `control_id: Optional[str] = None` as a trailing kwarg on both `evaluate_control` and the shim's `evaluate_evidence` (additive — the existing 3-arg call site is unaffected). When supplied, the caller's `control_id` is pinned onto the returned finding via `model_copy(update=...)`, overriding whatever the model returned — never trusting a model-fabricated id when the real one is known. When absent, falls back to `extract_control_id_tokens(control_desc)` (reusing the 39-03 validator utility built for exactly this "sweep free text for control-ID-shaped tokens" purpose) and finally the literal `UNSPECIFIED`, which correctly fails `validate_citations`' framework-fidelity check and downgrades — a fail-closed "we don't know" rather than a guess. `ai_auditor_endpoints.py` itself is unchanged (out of this plan's file scope), so its real call path still exercises the fallback path today; a future plan wiring the endpoint to pass `control_id` explicitly is a one-line, purely additive follow-up.
- **Files modified:** backend/ai_orchestration/agents/auditor.py, backend/ai_auditor_service.py
- **Verification:** `test_control_id_pinned_from_caller_overrides_model_output`, `test_unknown_control_id_rejected` (exercises the no-caller-control_id fallback path)
- **Committed in:** e4e3482, bfab5e6 (Task 1/2 commits)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both fixes are structural anti-fabrication corrections directly in scope of this plan's stated purpose ("turn fabricated-finding prevention from a prompt hope into a structural guarantee") and land entirely within the plan's own 3 files. No scope creep — `ai_auditor_endpoints.py` was not touched.

## Issues Encountered

- `guardrail_service.scan_and_log` (called by `guardrails.scan_input`/`scan_output`) calls the real `get_database()` internally and has no db-injection seam, so calling it un-patched in a hermetic test raises `RuntimeError: Database not connected`. Resolved by adding a file-wide autouse pytest fixture patching `guardrail_service.scan_and_log` to a passing result (mirrors `test_ai_orchestration_substrate.py`'s existing convention of patching `guardrail_service` for guardrail-hook tests) — tests that specifically exercise guardrail-block behavior patch `ai_orchestration.agents.auditor.scan_input`/`scan_output` directly instead.
- `tests/test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` fails both in the full suite and in isolation — confirmed unrelated to this plan (touches none of this plan's 3 files; the working tree already had pre-existing unstaged changes to `agent-rust/install-service.ps1` and `agent/installer/Collect-Evidence.ps1` per the sequential-executor briefing). Logged here, not fixed — out of this plan's file scope. `tests/test_e2e_integration.py::test_golden_path_evidence_to_remediation` is the previously-documented pre-existing failure, also excluded per the executor briefing.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `AuditEvaluationResult` and the `_raw_db`/control-id-pinning/`needs_review` patterns established here are the template for 39-07 (chat), 39-08 (questionnaire), 39-09 (narrative) — each will need its own raw-db unwrap when wiring `validate_citations`/tool factories to a real `TenantIsolatedDatabase` handle, since the same non-exempt-collection double-filter risk applies to any surface reading `asset_compliance`/`control_evidence`/`system_settings`.
- `ai_auditor_endpoints.py` still does not pass `control_id` into `evaluate_evidence` — functionally safe (falls back to conservative `UNSPECIFIED`/token-extraction, never a fabricated pass) but means production audits over this endpoint won't get the full benefit of the control-ID pinning defense until a small follow-up threads the already-available `control_id` local variable through. Not blocking; flagged for a future phase-29-style "wire it up" pass.
- Full backend suite: 1063 passed / 23 skipped / 2 failed (both pre-existing and unrelated, see Issues Encountered) — confirmed via direct re-run, not carried over from a stale note.

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: backend/ai_orchestration/agents/auditor.py
- FOUND: backend/ai_auditor_service.py
- FOUND: backend/tests/test_auditor_agent.py
- FOUND: .planning/phases/39-langchain-ai-integration/39-06-SUMMARY.md
- FOUND commit: e4e3482
- FOUND commit: bfab5e6
- FOUND commit: d7f048f
