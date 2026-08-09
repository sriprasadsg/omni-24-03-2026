---
phase: 39-langchain-ai-integration
plan: 10
subsystem: testing
tags: [pytest, json-fixtures, eval-harness, langchain, rag, tenant-isolation]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration
    provides: "39-02 eval harness scaffold (two seeded eval tenants, canary constants, data/README.md target layout); 39-03 AuditFinding/CitedAnswer schema shapes the gold labels mirror"
provides:
  - "48-example reference dataset (AI-SPEC Section 5) as four JSON fixtures under backend/tests/eval_langchain/data/"
  - "Fail-loud typed dataset loader (backend/tests/eval_langchain/dataset.py) exposing load_gold_controls/load_questionnaire_qa/load_chat_questions/load_adversarial_inputs"
  - "23 deterministic eval-marked consistency tests (backend/tests/test_eval_dataset.py)"
affects: [39-11-code-based-eval-dimensions, 39-12-llm-judged-eval-dimensions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail-loud fixture loaders: raise (FileNotFoundError/ValueError) on missing file, invalid JSON, empty array, missing required keys, or out-of-vocabulary enum value -- never return an empty list, so a broken dataset can never silently pass the eval gate (T-39-10-A)"
    - "data_dir optional override parameter on every load_* function enables hermetic malformed-fixture tests via pytest tmp_path without monkeypatching module globals"

key-files:
  created:
    - backend/tests/eval_langchain/data/gold_controls.json
    - backend/tests/eval_langchain/data/questionnaire_qa.json
    - backend/tests/eval_langchain/data/chat_questions.json
    - backend/tests/eval_langchain/data/adversarial_inputs.json
    - backend/tests/eval_langchain/dataset.py
    - backend/tests/test_eval_dataset.py
  modified: []

key-decisions:
  - "39-10: gold_controls.json 20-entry composition locked at 8 clean pass / 4 clear fail / 8 traps (2 stale, 2 partial, 2 zero-evidence, 2 context-dependent) -- traps carry insufficient_evidence (6) or partial (2) status, satisfying the >=8 trap-label acceptance bar exactly"
  - "39-10: gold_controls evidence/citation ids are self-contained per entry (cev-NNN) rather than pre-seeded against a live conftest seeder -- the conftest's seed_tenant_evidence fixture generates real ChromaDB ids dynamically at seed time, so 39-11 is expected to map fixture evidence content to real seeded ids at consumption time, not reuse these symbolic ids verbatim"
  - "39-10: questionnaire_qa.json and chat_questions.json use their own self-contained evidence-id namespace (qev-*, cev-* reused loosely for narrative continuity) -- no cross-file FK integrity is enforced or tested, only gold_controls.json's internal citation-to-evidence consistency (matches Task 3's stated scope)"
  - "39-10: adversarial_inputs.json's 3 leakage-probing types (prompt_injection, cross_tenant_probe, tool_arg_bypass) each carry a canary_strings field drawn verbatim from conftest.CANARY_STRINGS; the 2 non-leakage types (fabricated_control_id, skip_citations) intentionally carry an empty canary_strings list since they test a different failure mode"
  - "39-10: dataset.py's structural/enum validation lives in the loader itself (not just the test file) -- belt-and-braces so a malformed fixture fails immediately for any caller, including future 39-11/39-12 code, not only this plan's own tests"

requirements-completed: [AISPEC-39-S5, AISPEC-39-S1, AISPEC-39-S1b]

# Metrics
duration: ~12min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 10: Reference Dataset Summary

**48-example AI-SPEC Section 5 reference dataset (20 gold controls, 10 questionnaire Q&A, 8 chat, 10 adversarial) as JSON fixtures with a fail-loud typed loader and 23 deterministic consistency tests.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-07-18
- **Tasks:** 3
- **Files modified:** 6 (all new)

## Accomplishments
- Authored `gold_controls.json` (20 entries: 8 clean pass, 4 clear fail, 8 traps -- stale/partial/zero-evidence/context-dependent -- each with real-shaped evidence records, gold status, gold citations, and rationale)
- Authored `questionnaire_qa.json` (10 entries: 5 answerable, 3 hedged with "in progress"/compensating-control language, 2 unanswerable flagged `insufficient_evidence`) and `chat_questions.json` (8 entries: posture lookups, score explanation, one out-of-scope decline, one other-customers refusal)
- Authored `adversarial_inputs.json` (10 entries across all 5 attack types -- prompt injection, cross-tenant probe, tool-arg bypass, fabricated-control-ID bait, skip-citations -- with tenant-B canary strings embedded in the 3 leakage-probing types) and `dataset.py`, a fail-loud typed loader exposing all four splits
- Wrote `test_eval_dataset.py` (23 tests, `eval`-marked only, no live model): split counts, gold citation/control-ID internal consistency, trap-label composition, adversarial canary alignment with `conftest.CANARY_STRINGS`, and loader robustness against missing/malformed/invalid-enum fixtures

## Task Commits

Each task was committed atomically:

1. **Task 1: Gold control + questionnaire + chat fixtures** - `3bc92c5` (feat)
2. **Task 2: Adversarial fixtures + dataset loader** - `e596801` (feat)
3. **Task 3: Dataset loader + consistency test** - `692a573` (test)

_Note: verification for all three tasks' `<verify>` commands (`-k splits`, `-k loader`, `-m eval -q`) requires `test_eval_dataset.py` (Task 3) to exist, so all three tasks were authored together before the first commit and each was verified against the complete, final state before being split into its own atomic commit in task order._

## Files Created/Modified
- `backend/tests/eval_langchain/data/gold_controls.json` - 20 gold-labeled control assessments (auditor-surface oracle)
- `backend/tests/eval_langchain/data/questionnaire_qa.json` - 10 questionnaire Q&A pairs (questionnaire-surface oracle)
- `backend/tests/eval_langchain/data/chat_questions.json` - 8 chat questions (chat-surface oracle)
- `backend/tests/eval_langchain/data/adversarial_inputs.json` - 10 adversarial inputs (security-engineer-authored red-team set)
- `backend/tests/eval_langchain/dataset.py` - typed, fail-loud split loaders (`load_gold_controls`, `load_questionnaire_qa`, `load_chat_questions`, `load_adversarial_inputs`)
- `backend/tests/test_eval_dataset.py` - 23 deterministic `eval`-marked consistency + loader-robustness tests

## Decisions Made
See `key-decisions` in frontmatter. Summary: dataset composition locked exactly to AI-SPEC Section 5's counts and trap breakdown; evidence/citation IDs are self-contained per fixture file (no forced cross-file FK, matching Task 3's actual scope); canary strings are embedded only in the 3 attack types that genuinely probe cross-tenant leakage; loader enforces structural and enum validation directly (not deferred entirely to the test suite).

## Deviations from Plan

None - plan executed exactly as written. All `must_haves.truths`, `artifacts`, and `key_links` from the plan frontmatter are satisfied: `gold_controls.json` has `control_id`, `adversarial_inputs.json` contains `canary` (20 occurrences via `grep -c`), `dataset.py` exports `load_gold_controls`/`load_adversarial_inputs` (plus the other two), and the loader raises on missing/malformed input as asserted by 5 dedicated `TestDatasetLoader` tests.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The reference dataset is a stable oracle 39-11 (code-based eval dimensions) and 39-12 (LLM-judged eval dimensions) can import directly via `dataset.py`'s four loader functions.
- 39-11 will need to seed the gold-control evidence content into the real tenant-A ChromaDB/`asset_compliance` store at test time (via the conftest's `seed_tenant_evidence` fixture) and map the resulting live-generated ids back onto this fixture's `gold_citations` -- the fixture's `cev-*` ids are symbolic placeholders, not live-seeded ids, by design (see key-decisions).
- No blockers. Full `eval and not llm` suite for `backend/tests/eval_langchain/` + `test_eval_dataset.py` is green (23 passed, 1 deselected -- the live 9router passthrough smoke test correctly skips without `AI_ROUTER_URL`).

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*

## Self-Check: PASSED

All 6 created files confirmed present on disk (4 JSON fixtures + dataset.py + test_eval_dataset.py) and all 3 task commit hashes (3bc92c5, e596801, 692a573) confirmed present in `git log --oneline --all`.
