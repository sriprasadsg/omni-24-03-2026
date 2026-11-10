---
phase: 85-first-line-service-desk
plan: 37
subsystem: service-desk
tags: [citations, output-checks, prompt, injection, gap-closure, G-85-3]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: output checks (85-06), the desk pipeline and prompt builder, UAT round 3 gap G-85-3
provides:
  - given_citations(): citations the desk did not give are dropped; unknown_citation only when none was given
  - grounding rules compare only against the given articles the reply cites
  - prompt articles labelled A1..An, PROMPT_TAGS shared pattern, A-id reply parser, string-typed cited schema
affects: [85-38 live re-check with the real model, gsd-verify-work 85]

actuals:
  tokens: 10000
  tasks: 2
  commits: 2
plan_head_before: 7916e185ba524b2bd45cd0d0d26c08e171b63bf1
plan_head_after: 61cc6c11bbf24769636d939fbf06c6ba928cd9a6
commits: 2

tech-stack:
  added: []
  patterns: ["drop-not-punish for unverifiable citations, refuse only when no given article is named", "article ids of a form (A1) that cannot collide with an article's own numbered steps"]

key-files:
  created:
    - backend/tests/test_service_desk_citations.py
  modified:
    - backend/service_desk/checks.py
    - backend/service_desk/pipeline.py
    - backend/service_desk/sanitize.py
    - backend/service_desk/model.py
    - backend/scripts/service_desk_eval.py
    - backend/tests/fixtures/service_desk/output_checks.jsonl
    - backend/tests/test_service_desk_sanitize.py
    - backend/tests/test_service_desk_injection.py
    - backend/tests/test_service_desk_eval_script.py
    - backend/tests/test_service_desk_output_checks.py

key-decisions:
  - "A-85-G33: citations that were not given are dropped, and articles are relabelled A1..An; D-19 (cite at least one given article) still holds, T-85-05/T-85-20 now read: only given ids are stored, a reply naming no given article is refused"
  - "A-85-G34: the schema lists cited items as strings (no enum/pattern); the parser also accepts bare integers, an integer not given is dropped like any other unknown citation"
  - "A-85-G35: the system text asks for at most ANSWER_MAX_LINES short lines, built from the constant; too_long and too_many_lines rules unchanged"

requirements-completed: [DESK-01, DESK-03]

coverage:
  - id: D1
    description: "A printer ticket whose reply cites its step numbers ([1..6], one article given) is drafted citing exactly the printer article, not handed off"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_citations.py#test_the_printer_ticket_is_drafted_citing_only_the_printer_article"
        status: pass
    human_judgment: false
  - id: D2
    description: "No D-19 rule is loosened: a reply naming no given article is refused; grounding uses only given cited articles"
    requirement: DESK-03
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_citations.py (refusal and grounding tests) + output_checks.jsonl uc-01..uc-06; tracer cited [7] still output_check_failed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Articles reach the model as A1..An; the parser reads those ids; DESK-03 injection, sanitiser and eval-script shape tests stay green"
    requirement: DESK-03
    verification:
      - kind: integration
        ref: "backend gate (492 tests, 0 failed, 0 skipped): citations, sanitize, injection, eval_script, output_checks, output_fold, model, pipeline, tracer, retrieval, rules"
        status: pass
    human_judgment: false
  - id: D4
    description: "The real model (llama3.2:3b) now answers the printer ticket with a draft"
    requirement: DESK-01
    human_judgment: true
    rationale: "Only the offline httpx stand-in ran here; the live re-check with the real model is plan 85-38"

duration: 10 min
completed: 2026-11-10
---

# Phase 85 Plan 37: Printer answers refused with unknown_citation Summary

**Citations the desk did not give are now dropped instead of failing the whole reply, and prompt articles are labelled A1..An so an article's numbered steps cannot be read as article numbers.**

## Accomplishments

- Task 1 (tracer, efcd248d0): `checks.given_citations(reply, given_ids)`; `check()` returns `unknown_citation` only when none of the cited numbers was given; `_cited_text` and the pipeline's stored citations use only the given ones. A printer ticket with the stand-in replying cited `(1,2,3,4,5,6)` is drafted (Drafts only mode) with exactly one citation, the printer article copy, one `/api/generate` call, and no staff_note or handoff_notice. Retrieval is asserted to match exactly one article first. Fixture: uc-02 now passes, new rows uc-04 (printer pass), uc-05 (foreign_link), uc-06 (foreign_phone); uc-01 and uc-03 still give unknown_citation. The existing cited `[7]` tracer test still ends output_check_failed.
- Task 2 (61cc6c11b): `build_prompt` writes `<article id="A<n>" ...>`; SYSTEM_PROMPT names the id form with an example and asks for at most `ANSWER_MAX_LINES` short lines; `sanitize.PROMPT_TAGS` is the single pattern for the prompt's own tags and replaces the copies in the eval script and the injection test; `parse_reply` maps `A<n>` (any case, trimmed) and bare integers to article numbers, any other string to 0 (unknown citation), and keeps booleans, floats, nulls, objects, lists and non-list `cited` unparseable; the schema sent to Ollama lists `cited` items as strings; the eval script builds `cited_text` from `given_citations`.

## Task Commits

1. Task 1 (tracer): `efcd248d0` fix(85-37): drop citations the desk did not give instead of refusing the grounded answer (G-85-3)
2. Task 2: `61cc6c11b` feat(85-37): label prompt articles A1..An and read those ids back (G-85-3)

## Verification

- Task 1 command (citations, output_checks, output_fold, pipeline, tracer): 297 passed, 0 skipped. Tracer gate: re-run of the verify passed before expansion ("Tracer verified end-to-end - expanding").
- Task 2 command (11 service desk test files): 492 passed, 0 failed, 0 skipped. All commands ran against the private mongod 127.0.0.1:27998; nothing reached the live mongod or the real Ollama.
- Acceptance criteria of both tasks re-checked (greps for `def given_citations`, `given_citations(`, uc-02 expect pass, at least two unknown_citation rows, `PROMPT_TAGS` in the eval script and injection test, `id="A` in the sanitiser test, string-typed `cited` in `_REPLY_SCHEMA`): all pass.

## Deviations from Plan

**1. [Rule 1 - Bug] Existing parser expectations contradicted the new A-id rule**
- **Found during:** Task 2
- **Issue:** fixture row un-04 (`cited: ["1"]`, expect unparseable) and the parse test in test_service_desk_output_checks.py assumed any string item is unparseable; under the plan's rule a string that is not an A-id is an unknown citation (0), not unparseable.
- **Fix:** un-04 now uses `cited: [true]` (still unparseable, so the rule keeps at least two rows); two cases (`[null]`, non-list `"A1"`) added to the parser test. The `"1"` string case is covered in the new citations test (becomes unknown_citation).
- **Files modified:** backend/tests/fixtures/service_desk/output_checks.jsonl, backend/tests/test_service_desk_output_checks.py (neither listed in Task 2's files)
- **Commit:** 61cc6c11b

**2. [Execution note] Task 2 TDD cycle committed as one commit**
The plan requires the prompt change and the pinned shape-test updates to land in one commit to keep DESK-03 green, so tests were written and shown failing/updated locally and committed together with the implementation instead of a separate RED commit.

**3. [Execution note] Printer test uses Drafts only mode explicitly**
The shared `world` fixture seeds mode "post", under which the same reply is posted (the plan allows "or a post where the gate allows"); the test re-seeds the tenant with mode "drafts" to pin the documented default outcome.

**Total deviations:** 1 auto-fixed (Rule 1), 2 execution notes. **Impact:** none on scope; no D-19 rule loosened.

## Known Stubs

None.

## Threat Flags

None. T-85-128 (mixed given/not-given citations) is mitigated by `given_citations` plus the fixture rows and pipeline test; T-85-129 (A-id prompt weakening injection defences) by the unchanged `_DELIMITER` neutralisation, the shared `PROMPT_TAGS` and the green offline injection set; the live `--sets` run is plan 85-38.

## Next

Plan 85-38 re-checks the printer ticket and the injection set with the real model and changes the failing-rule text in the ledger and staff note.

## Self-Check: PASSED

- backend/tests/test_service_desk_citations.py exists; efcd248d0 and 61cc6c11b are ancestors of HEAD; `commits: 2` measured from the ledger base 7916e185b.
