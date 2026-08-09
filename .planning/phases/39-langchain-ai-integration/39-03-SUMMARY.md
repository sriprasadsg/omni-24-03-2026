---
phase: 39-langchain-ai-integration
plan: "03"
subsystem: ai
tags: [pydantic, langchain, validators, citations, control-id, tenant-isolation, ai_orchestration]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration
    plan: "01"
    provides: LangChain 1.x/LangGraph runtime stack installed and import-verified in backend/venv
provides:
  - "backend/ai_orchestration/ package: schemas.py (Citation, AuditFinding, CitedAnswer, NarrativeOutput) + validators.py (validate_citations, validate_framework_fidelity)"
  - "One shared async citation/control-ID resolution validator callable from every AI surface (auditor, questionnaire, chat) instead of per-surface ad-hoc checks"
  - "27 hermetic unit tests proving schema invariants and validator resolution/downgrade/tenant-scoping behavior"
affects: [39-06, 39-07, 39-08, 39-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One shared Pydantic schema set (backend/ai_orchestration/schemas.py) as response_format= target for create_agent, replacing 4 independent hand-rolled JSON-extraction/validator implementations"
    - "One shared async validate_citations(obj, tenant_id, db) resolving citations/control_id against real tenant-scoped (+global) collections, never a hardcoded map — one validator, three call sites"
    - "Block + downgrade pattern: unresolved citation/control_id returns a failing CitationValidationResult plus a downgraded (insufficient_evidence) copy of the object, never a silent pass"

key-files:
  created:
    - backend/ai_orchestration/__init__.py
    - backend/ai_orchestration/schemas.py
    - backend/ai_orchestration/validators.py
    - backend/tests/test_ai_orchestration_schemas.py
  modified: []

key-decisions:
  - "CitedAnswer keeps citations as an additive field (default empty list, no min_length) alongside the pre-existing source_evidence_ids grounding field from AnswerDraft — only AuditFinding.citations carries min_length=1, per the plan's explicit must_haves scope (AuditFinding, not every schema, requires at least one citation)"
  - "validate_citations is duck-typed over any object exposing .citations (+ optional .control_id) rather than a Union[AuditFinding, CitedAnswer] type — keeps it usable from future surfaces without widening the validator's own signature"
  - "Framework-fidelity control-ID token regex requires the digit run to directly follow the letter code (hyphen or no separator) — deliberately does NOT match a bare '<letters> <space> <number>' shape (e.g. 'SOC 2', 'ISO 27001') so a narrative merely naming a framework never false-positives as a fabricated control ID, while 'CC9.9'/'CIS-5.2' still match"
  - "control_id and citation chunk_id resolution both query only db.compliance_frameworks / db.control_evidence / db.asset_compliance (RESEARCH Pattern 3) — no Chroma/rag_service lookup in this validator, per the plan's explicit resolution-target list"

patterns-established:
  - "ai_orchestration/ as the shared package root for every later Phase 39 agent-surface plan (39-06 through 39-09) to import schemas.py/validators.py from, rather than each surface defining its own Pydantic models or citation checks"

requirements-completed: [AISPEC-39-S4b, AISPEC-39-S5, AISPEC-39-S6, RESEARCH-Pat3]

coverage:
  - id: D1
    description: "Shared Pydantic schema set (Citation, AuditFinding, CitedAnswer, NarrativeOutput) rejects empty/BLOCKED/Error strings; AuditFinding.citations requires min_length=1"
    requirement: "AISPEC-39-S4b"
    verification:
      - kind: unit
        ref: "backend/tests/test_ai_orchestration_schemas.py::TestAuditFindingSchema, ::TestCitedAnswerSchema, ::TestNarrativeOutputSchema"
        status: pass
    human_judgment: false
  - id: D2
    description: "Shared async validate_citations resolves every citation chunk_id against tenant-scoped (+global) control_evidence/asset_compliance and control_id against compliance_frameworks; unresolved id fails with reason citation_validation_failed and returns a downgraded (insufficient_evidence) object copy"
    requirement: "AISPEC-39-S6"
    verification:
      - kind: unit
        ref: "backend/tests/test_ai_orchestration_schemas.py::TestValidateCitationsValidator"
        status: pass
    human_judgment: false
  - id: D3
    description: "Validator never queries evidence without a tenant scope — every control_evidence/compliance_frameworks query carries the acting-tenant + global $or clause"
    requirement: "AISPEC-39-S6"
    verification:
      - kind: unit
        ref: "backend/tests/test_ai_orchestration_schemas.py::TestValidateCitationsValidator::test_never_queries_evidence_without_tenant_scope"
        status: pass
    human_judgment: false
  - id: D4
    description: "Framework-fidelity helper regex-extracts control-ID-shaped tokens from free text and validates each against the compliance_frameworks registry, without false-positiving on bare framework-name mentions"
    requirement: "AISPEC-39-S5"
    verification:
      - kind: unit
        ref: "backend/tests/test_ai_orchestration_schemas.py::TestFrameworkFidelityValidator"
        status: pass
    human_judgment: false

# Metrics
duration: ~20min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 03: Shared AI-Orchestration Schemas + Citation Validator Summary

**One shared Pydantic schema set (Citation, AuditFinding, CitedAnswer, NarrativeOutput) with mandatory citations, plus one shared async `validate_citations` resolving every citation and control_id against real tenant-scoped evidence and the seeded framework registry — collapsing four hand-rolled per-surface JSON-extraction/validation implementations onto a single reusable guardrail.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3/3 completed
- **Files modified:** 4 (all new)

## Accomplishments

- Built `backend/ai_orchestration/schemas.py`: `Citation` (source, chunk_id), `AuditFinding` (control_id, status Literal, rationale, `citations: list[Citation] = Field(min_length=1)`, optional suggested_action), `CitedAnswer` (generalizes `questionnaire_answer_draft_service.AnswerDraft`'s grounded-or-flagged invariant, plus a `citations` field), and `NarrativeOutput` (generalizes `compliance_narrative_service.NarrativeOutput`'s within-budget invariant) — all four reject empty strings and the `BLOCKED:`/`Error:` guardrail sentinel prefixes.
- Built `backend/ai_orchestration/validators.py`: async `validate_citations(obj, tenant_id, db)` resolves every `Citation.chunk_id` against `db.control_evidence`/`db.asset_compliance` (tenant + `global` scope) and `control_id` against `db.compliance_frameworks` (the same `controls_map` shape `ai_auditor_endpoints.py` already builds) — never a hardcoded map. On any unresolved id, returns `CitationValidationResult(ok=False, reason="citation_validation_failed")` plus a downgraded copy of the object (`status`/`confidence` forced to `insufficient_evidence`).
- Added `validate_framework_fidelity` + `extract_control_id_tokens`: a regex sweep of free narrative/rationale text for control-ID-shaped tokens (`CIS-5.2`, `CC6.1`, `AC-2`), checked against the same registry — tuned to skip bare framework-name mentions (`SOC 2`, `ISO 27001`) so a narrative that merely names a framework doesn't false-positive as inventing a control ID.
- Wrote `backend/tests/test_ai_orchestration_schemas.py`: 27 hermetic unit tests (10 selected by `-k validator`) covering every schema invariant plus validator resolution, downgrade, tenant-scope enforcement, and the framework-fidelity false-positive guard — using an explicit mocked `db` handle (dependency-injection convention), no live model/gateway/network dependency.
- Confirmed the code-review guardrail rule from AI-SPEC Section 4b (`\.invoke\(|asyncio\.run\(` is a rejected diff in `ai_orchestration/`) holds: zero matches in `validators.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Shared validated-output schemas (schemas.py)** - `3d29b1f` (feat)
2. **Task 2: Shared citation + control-ID validator (validators.py)** - `4eaf04b` (feat)
3. **Task 3: Unit tests for schemas + validator** - `784c994` (test)

**Plan metadata:** (this SUMMARY's commit, following)

## Files Created/Modified

- `backend/ai_orchestration/__init__.py` - Package marker with a docstring pointing at the schema/validator contract.
- `backend/ai_orchestration/schemas.py` - `Citation`, `AuditFinding` (citations `min_length=1`), `CitedAnswer`, `NarrativeOutput` — plain Pydantic models, no LangChain import, consumed as `response_format=` targets.
- `backend/ai_orchestration/validators.py` - `validate_citations` (async), `validate_framework_fidelity` (async), `extract_control_id_tokens`, `CitationValidationResult`, `FAILURE_REASON` constant.
- `backend/tests/test_ai_orchestration_schemas.py` - 27 hermetic tests across `TestAuditFindingSchema`, `TestCitedAnswerSchema`, `TestNarrativeOutputSchema`, `TestValidateCitationsValidator`, `TestFrameworkFidelityValidator`.

## Decisions Made

- Kept `CitedAnswer.citations` additive (no `min_length=1`) — the plan's must_haves scope the mandatory-citation invariant to `AuditFinding` specifically; `CitedAnswer`'s existing `source_evidence_ids` field (from `AnswerDraft`) remains the grounding invariant enforced by `grounded_or_flagged`.
- `validate_citations` is duck-typed (any object with `.citations` + optional `.control_id`) rather than a `Union[AuditFinding, CitedAnswer]` — future surfaces (chat, questionnaire) can pass their own schema instances without widening the validator.
- Tightened the framework-fidelity token regex to require the digit run to directly follow the letter code (`CIS-5.2`, `CC6.1`) rather than allowing a whitespace separator — this was discovered during implementation (see Deviations) to avoid flagging ordinary framework-name mentions like "SOC 2" as fabricated control IDs.
- Resolution targets are exactly `compliance_frameworks` / `control_evidence` / `asset_compliance` (RESEARCH Pattern 3) — no Chroma/`rag_service` query in this validator, matching the plan's explicit instruction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Framework-fidelity regex initially false-positived on bare framework-name mentions**
- **Found during:** Task 2 (writing `validate_framework_fidelity`), caught by manual sanity-check before Task 3's tests were written
- **Issue:** The first regex draft (`[A-Z]{2,8}[-\s]?\d+(?:\.\d+)*`) matched a whitespace separator between the letter code and the digit run, so ordinary narrative text like "the SOC 2 framework scored 85%" extracted `"SOC 2"` as a control-ID-shaped token — which would then fail registry lookup and incorrectly flag every SOC 2-mentioning narrative as inventing a control ID.
- **Fix:** Tightened the regex to two alternatives — `[A-Z]{2,8}-\d+(?:\.\d+)*` (hyphen-separated) or `[A-Z]{2,8}\d+(?:\.\d+)*` (no separator) — which still matches `CIS-5.2`, `AC-2`, `CC6.1`, and the adversarial bait example `CC9.9`, but no longer matches bare `<letters> <space> <number>` framework-name mentions.
- **Files modified:** `backend/ai_orchestration/validators.py`
- **Verification:** Added `TestFrameworkFidelityValidator::test_extract_control_id_tokens_ignores_bare_framework_names` (asserts `"SOC 2"` is excluded while `CIS-5.2`/`CC6.1` are included) plus positive/negative fidelity-check tests.
- **Committed in:** `4eaf04b` (Task 2 commit — regex was corrected before commit, not as a follow-up fix)

---

**Total deviations:** 1 auto-fixed (1 bug, caught and corrected during implementation before commit)
**Impact on plan:** No scope creep — the fix stayed inside `validators.py`'s own regex constant and was verified with an added test case in Task 3.

## TDD Gate Compliance

Task 1 (`schemas.py`) carries `tdd="true"` in the plan frontmatter, but the plan's own task sequencing places the actual test file (`test_ai_orchestration_schemas.py`) in Task 3, after both Task 1's `schemas.py` and Task 2's `validators.py` commits. This means Task 1's commit order was `feat` (schemas) then, two commits later, `test` — not the strict RED-before-GREEN ordering `tdd_execution` describes for a single task. This is a structural consequence of the plan's task breakdown (one consolidated test file at the end covering both schemas and the validator), not an executor deviation from the plan as written; each task's own `<verify>` command was still satisfied once Task 3 landed, and all three tasks' acceptance criteria pass in the final state. Flagging here per the `tdd_execution` instruction to surface a gap rather than silently proceed.

## Issues Encountered

None blocking.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `backend/ai_orchestration/schemas.py` and `validators.py` are ready for 39-06 through 39-09 (auditor, questionnaire, chat, narrative agent migrations) to import directly as their `response_format=` schemas and shared post-generation guardrail — no per-surface re-implementation needed.
- `validate_citations`/`validate_framework_fidelity` are duck-typed over any `.citations`/`.control_id`-bearing object, so `CitedAnswer`-based surfaces (questionnaire, chat) can call the same functions as the `AuditFinding`-based auditor surface without modification.
- No blockers for 39-06.

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: backend/ai_orchestration/__init__.py
- FOUND: backend/ai_orchestration/schemas.py
- FOUND: backend/ai_orchestration/validators.py
- FOUND: backend/tests/test_ai_orchestration_schemas.py
- FOUND: .planning/phases/39-langchain-ai-integration/39-03-SUMMARY.md
- FOUND: commit 3d29b1f
- FOUND: commit 4eaf04b
- FOUND: commit 784c994
