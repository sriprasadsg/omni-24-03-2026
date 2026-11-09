---
phase: 85-first-line-service-desk
plan: 24
subsystem: service-desk
tags: [output-checks, unicode-fold, nfkc, exfiltration, loopback, httpx, trust_env]

requires:
  - phase: 85-first-line-service-desk
    provides: "85-06 output checks (checks.py), 85-07 loopback model client (model.py), 85-05 input cleaning (sanitize.py)"
provides:
  - "sanitize.fold_text: the one fold of the desk (NFKC, hidden characters removed, NFKC again, IDNA dots to a full stop) used for ticket text, phrase matching and every output-check comparison"
  - "checks.parse_reply returns the folded answer; check()/_norm fold answer and cited article alike, so the stored text is the checked text"
  - "Look-alike / IDN domain rule (a dotted token with a non-ASCII letter is a link fragment)"
  - "OllamaClient._http with trust_env=False (environment proxies cannot carry ticket text off the server)"
affects: [85-29 phase gate, 85-VERIFICATION gap 1 re-verification]

actuals:
  tokens: 6850
  tasks: 3
  commits: 6
plan_head_before: c9e32ae76de651cdeb7bd4c9a1cca9ad72457db9
plan_head_after: a79affebbf49cc0f8ad0ff87e6382e437573c91d
commits: 6

tech-stack:
  added: []
  patterns:
    - "One public fold (fold_text) shared by input cleaning and output checks; idempotent"
    - "Strip-then-check: hidden characters are removed, the folded text is checked, stored and shown (no new rule name)"

key-files:
  created:
    - backend/tests/test_service_desk_output_fold.py
  modified:
    - backend/service_desk/sanitize.py
    - backend/service_desk/checks.py
    - backend/service_desk/model.py
    - backend/tests/test_service_desk_model.py
    - backend/tests/test_service_desk_output_checks.py
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md

key-decisions:
  - "A-85-G01: hidden characters are stripped by the fold and the folded text checked/stored; checks.RULES unchanged, no new messages.py sentence"
  - "A-85-G02: the existing _fold is extended (Cn, Cs, default-ignorable code points) and recomposed with a second NFKC; input cleaning gains the same coverage"
  - "A-85-G03: a dotted token with a non-ASCII letter is a link fragment and must occur in a cited article (fails closed)"
  - "A-85-G04: Drafts go through the same fold and checks as posts; keep_draft stores parsed.answer"

requirements-completed: [DESK-01, DESK-03, DESK-04]

coverage:
  - id: D1
    description: "CR-101: no reviewer string or grid variant (18 hidden characters x 7 templates, full-width, ideographic dots, look-alike domains) passes check(); verdict() of the raw JSON folds too"
    requirement: "DESK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_output_fold.py#test_a_hidden_character_never_hides_a_foreign_fragment"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_output_fold.py#test_the_reviewers_strings_are_refused"
        status: pass
    human_judgment: false
  - id: D2
    description: "The pipeline hands a hidden-character link to a person at Post answers and at Drafts only, and posts or drafts an accepted reply in the folded form the checks saw"
    requirement: "DESK-03"
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_output_fold.py#test_a_hidden_character_link_is_handed_off_not_posted"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_output_fold.py#test_an_accepted_reply_is_posted_in_the_folded_form"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_output_fold.py#test_an_accepted_reply_is_kept_as_a_folded_staff_draft_in_drafts_mode"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-101: the desk's loopback httpx client ignores HTTP_PROXY / HTTPS_PROXY / ALL_PROXY (control client proves the environment is read)"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_model.py#test_the_loopback_client_ignores_environment_proxies"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_model.py#test_every_async_client_of_the_desk_model_ignores_the_environment_and_redirects"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-11-09
status: complete
---

# Phase 85 Plan 24: Output fold and loopback proxy gap closure Summary

**One shared Unicode fold (sanitize.fold_text) now runs on every model answer and cited article before the D-19 output checks and is what gets posted or drafted (CR-101), and the loopback Ollama client ignores environment proxies (WR-101).**

## Performance

- **Duration:** about 45 min
- **Started:** 2026-11-09T15:25Z (approx.)
- **Completed:** 2026-11-09T16:10Z
- **Tasks:** 3
- **Files modified:** 7 (1 created)

## Accomplishments
- `sanitize.fold_text` (NFKC, hidden characters removed, NFKC again, IDNA dots U+3002/U+FF0E/U+FF61 to ".") is the single fold; `clean_text` and `normalize_for_match` use it too, so the input side gains the same coverage. `_fold` now also drops Cn, Cs and the default-ignorable code points that are not Cf (`_IGNORABLE`).
- `checks.parse_reply` returns the folded answer, `check()` folds the answer and `_norm` folds the article text, so equality is fold-to-fold and the text posted/stored by `pipeline.answer` (`text=parsed.answer`) is exactly what the checks accepted. `pipeline.py` and `outcomes.py` are unchanged.
- Look-alike/IDN domains (`_take_idn`): a dotted token with a non-ASCII letter is a link unless a cited article holds it.
- Regression suite: the five reviewer strings, 18 hidden characters x 7 templates (126 cases) plus controls, full-width/ideographic-dot rows, look-alike rows, idempotence, pinned NFKC dot facts, and four pipeline tests (hand-off at Post answers and Drafts only; folded post and folded staff draft).
- `OllamaClient._http` builds `httpx.AsyncClient(..., follow_redirects=False, trust_env=False)`; a transport-level test (with a control client that does map the URL to an `AsyncHTTPProxy`) and an AST test pin it.
- 85-REVIEW-DISPOSITION.md: CR-101 and WR-101 recorded fixed with their commits, open count 26.

## Task Commits

1. **Task 1 (tracer): one folded answer from reply through checks to the stored ticket** - `791831738` (feat)
2. **Task 2: grid, extended hidden-character set, look-alike domains** - `7c3dcab2d` (test, RED: 19 failing cases on U+034F, U+3164, U+FE0F and the three look-alike domains), `94afd4eea` (feat, GREEN)
3. **Task 3: loopback client ignores environment proxies** - `3fe980d67` (test, RED: both new tests failed on trust_env), `cf422f817` (fix, GREEN); disposition flip `a79affebb` (docs)

**Plan metadata:** the SUMMARY/STATE/ROADMAP docs commit follows this file.

TDD RED notes (pytest output is not a format the `check tdd-red-evidence` classifier reads, so the semantic assessment is recorded here): Task 2 RED ran the new file and reported "19 failed, 151 passed", each failure on the planned assertion (the verdict was None or a different rule for the three default-ignorable characters and the look-alike domains); Task 3 RED reported "2 failed", the proxy test failing on `assert not isinstance(desk..._pool, AsyncHTTPProxy)` (the control assertion before it passed) and the AST test failing on the missing `trust_env` keyword. Both are the intended behavior, not load, import or fixture faults.

## Files Created/Modified
- `backend/service_desk/sanitize.py` - `fold_text`, `IDNA_DOTS`, `_IGNORABLE`, extended `_fold`
- `backend/service_desk/checks.py` - folded `parse_reply`/`check`/`_norm`, `_IDN_DOMAIN` and `_take_idn`, docstring
- `backend/service_desk/model.py` - `trust_env=False`
- `backend/tests/test_service_desk_output_fold.py` - new CR-101 regression, fold-property and pipeline tests
- `backend/tests/test_service_desk_model.py` - proxy and AST tests
- `backend/tests/test_service_desk_output_checks.py` - purity test allows the `.sanitize` import
- `.planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md` - CR-101, WR-101 fixed

## Decisions Made
Followed the plan's A-85-G01..G04 (strip-then-check, one extended fold, non-ASCII dotted token is a link, drafts folded and checked like posts). The orchestrator's claim about NFKC and the dots was not trusted; `test_what_nfkc_does_to_the_three_dots_is_pinned` records what `unicodedata` does (U+FF0E to ".", U+FF61 to U+3002, U+3002 unchanged) and `fold_text` maps all three to ".".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Purity test rejected the new `.sanitize` import**
- **Found during:** Task 1
- **Issue:** `test_checks_are_pure_and_import_no_model_no_settings_no_network` (test_service_desk_output_checks.py) pins checks.py's imports to an allow-list that did not include the stdlib-only `.sanitize` module the plan requires checks.py to import.
- **Fix:** added `".sanitize"` to the allow-list with a one-line comment (the file was clean; not in the plan's `files_modified`).
- **Files modified:** backend/tests/test_service_desk_output_checks.py
- **Verification:** the file's tests pass (236 with the fold tests)
- **Committed in:** 791831738

**2. [Plan convention - TDD commits] Tasks 2 and 3 carry separate test and implementation commits**
- Tasks 2 and 3 are `tdd="true"`, so each has a `test(85-24)` RED commit and a `feat`/`fix` GREEN commit (plan `commits` 6, not 3).

---

**Total deviations:** 1 auto-fixed (Rule 3), 1 convention note
**Impact on plan:** none on scope; the allow-list entry is the minimum the plan's own import required.

## Issues Encountered
None. `checks.py` no longer imports `unicodedata` (the fold lives in sanitize), so that name stays in the purity test's allow-list only as an upper bound.

## Known Stubs
None.

## Threat Flags
None. T-85-87, T-85-88 and T-85-89 are mitigated as planned; no new endpoint, auth path or schema.

## Verification
- Task commands: 501 passed, 0 skipped, on the private mongod (27998) across test_service_desk_model/output_fold/output_checks/sanitize/rules/injection/retrieval/eval_script/structural/pipeline and test_autonomous_ops_copy.
- `git diff --stat -- backend/service_desk/pipeline.py backend/service_desk/outcomes.py` prints nothing; user WIP untouched; checks.py 202, sanitize.py 164, model.py 226, new test file 225 lines (all under 500).
- Not run (by plan): the whole backend suite (85-29), restarts, publishes, push.

## Self-Check: PASSED
Files present: sanitize.py, checks.py, model.py, test_service_desk_output_fold.py, test_service_desk_model.py, 85-REVIEW-DISPOSITION.md. Commits present: 791831738, 7c3dcab2d, 94afd4eea, 3fe980d67, cf422f817, a79affebb.
