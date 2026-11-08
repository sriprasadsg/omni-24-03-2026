---
phase: 85-first-line-service-desk
plan: 05
subsystem: service-desk
tags: [service-desk, rules, sanitiser, prompt-injection, escalation, language-check, fixtures]
status: complete

requires: [85-01, 85-02]
provides:
  - "service_desk.sanitize: hardened clean_text, new normalize_for_match and neutralise_delimiters, SYSTEM_PROMPT that says ticket text is data that may try to instruct, build_prompt that neutralises forged delimiters in ticket and article text"
  - "service_desk.rules: evaluate(ticket, cleaned_text, words) returns None or the first hand-off reason in the fixed order; is_english(text) standard-library language check"
  - "service_desk.phrases: SECURITY, BILLING, LEGAL, ACCOUNT_ACCESS, ASK_FOR_PERSON and the English and five foreign word sets (rules re-exports the five phrase lists)"
  - "tests/fixtures/service_desk/escalation_set.jsonl (150 cases) and language_set.jsonl (64 cases)"
affects: [85-06, 85-07, 85-13, 85-22]

actuals:
  tokens: 20500
  tasks: 3
  commits: 3
plan_head_before: 02d503c0b625e74bdf8e70033566f7fe76a5b263
plan_head_after: a756dbf4c05ee0d996aec0034819ffebbf84733b

tech-stack:
  added: []
  patterns:
    - "Phrase lists are plain tuples, normalised once and compiled as one escaped, word-bounded alternation; tenant words are escaped and compiled per call, empty ones dropped; ticket text is never a pattern"
    - "Every sanitiser pattern is bounded or anchored; hostile 20,000-character inputs clean in well under a second"
    - "A fixture row per case, loaded whole: the test lists every mismatching id, so a retuned list is a visible fixture diff"

key-files:
  created:
    - backend/service_desk/rules.py
    - backend/service_desk/phrases.py
    - backend/tests/fixtures/service_desk/escalation_set.jsonl
    - backend/tests/fixtures/service_desk/language_set.jsonl
    - backend/tests/test_service_desk_sanitize.py
    - backend/tests/test_service_desk_rules.py
  modified:
    - backend/service_desk/sanitize.py

key-decisions:
  - "Phrase lists and the language word sets live in phrases.py, not rules.py (the plan's own fallback for the 450-line limit; rules.py is 140 lines, phrases.py 165)"
  - "SECURITY names device and company compromise cases one by one and has no bare hacked or compromised; the bare words sit at the end of ACCOUNT_ACCESS, so an account compromise reports account_access (D-32) and an unclassified compromise still goes to a person"
  - "Any whitespace-delimited token with an @ inside it is removed as an address, so nothing address-like reaches the prompt even when it touches punctuation or a link"
  - "normalize_for_match also joins apostrophes inside a word and turns every other punctuation mark into a space, so 'can't' and 'cant' and 'an agent, not a bot' match their phrases"
  - "The English check gives no credit for words English shares with the other languages (no, a, in, me, do, as, um) or for bare acronyms such as VPN; that is what makes 'VPN no funciona' not English while 'no internet' stays English"

requirements-completed: [DESK-02, DESK-03]

coverage:
  - id: D1
    description: "No HTML, script or style content, link, image, email address, hidden or bidi character, full-width look-alike or forged ticket or article delimiter in a ticket reaches the prompt; the prompt tells the model the ticket is data that may try to instruct"
    requirement: "DESK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_sanitize.py (25 tests: markup, entities, adjacency, hidden characters, full-width, caps, bounded time, normalize_for_match, 8 hostile prompts, forged delimiters, system prompt)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Critical priority, a ticket type outside task, bug and incident, the install and hardware templates (stored or legacy title prefix), the security and account-access templates, the security, billing, legal and account-access lists, asking for a person and tenant words each hand off with their own reason in a fixed order before the model; an empty ticket never reaches the model"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_rules.py (escalation_set.jsonl 150 cases; order, template, priority, type, empty, encoding, whole-word, tenant-word tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A self-service password how-to stays answerable while unlock, MFA, access, permission and compromise phrasings hand off as account_access (D-32)"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_rules.py#test_a_password_how_to_is_answerable; #test_unlock_mfa_access_permission_and_compromise_hand_off_as_account_access; #test_the_set_holds_the_six_self_service_password_phrasings_and_they_stay_answerable"
        status: pass
    human_judgment: false
  - id: D4
    description: "Tenant words are matched as escaped whole-word literals; regular-expression text, empty and non-string entries and a 5,000-character hostile ticket neither match everything nor hang"
    requirement: "DESK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_rules.py#test_tenant_words_are_whole_word_literals_never_patterns; #test_tenant_words_are_capped_and_hostile_ones_run_in_bounded_time; #test_ticket_text_is_never_compiled_as_a_pattern"
        status: pass
    human_judgment: false
  - id: D5
    description: "is_english passes all 64 language_set cases, including short English tickets and mixed non-English ones, with no new dependency"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_rules.py (language_set.jsonl, short English, short mixed, script share, determinism, imports)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-11-08
---

# Phase 85 Plan 05: The fixed text rules Summary

Ticket text is now cleaned of markup, links, addresses, hidden characters and forged prompt delimiters before it can reach the model, and fixed rules (critical priority, ticket type, tray template, security, billing, legal, account-access, ask-for-a-person and tenant-word lists, empty text) plus a dependency-free English check decide hand-offs by code, pinned by two invented fixture sets.

Duration: about 12 minutes (19:43 to 19:55 UTC). Tasks: 3. Files: 7 (6 created, 1 modified). Completed 2026-11-08.

## Accomplishments

- **Task 1, the sanitiser (bf16fe66d).** `clean_text` folds NFKC and removes hidden characters first (so `<scr` + zero-width space + `ipt>` still drops its contents), parses markup with a space at every tag boundary and drops script, style, head, template and noscript contents, decodes entities and parses once more (double-encoded tags), then removes markdown images and links (keeping link text), scheme, `www.`, `javascript:` and `mailto:` links, any token containing an `@`, and bare `domain.tld` or `host/path` links, then neutralises the prompt's own tags. `normalize_for_match` is the one folded form (NFKC, casefold, no diacritics, no hidden characters, `Wi-Fi Café` becomes `wifi cafe`). Every pattern is bounded or anchored: seven hostile 20,000 to 40,000-character inputs clean in under a second together. 25 tests.
- **Task 2, the rules (6f75a2251).** `rules.evaluate` runs: empty text, critical priority (D-37), type (security, feature, unknown), template (stored, else legacy title prefix), security, billing, legal, account access, asking for a person, tenant words. 150 escalation cases pin it, including the six self-service password how-tos (D-32), hidden and full-width variants, ordering (11 two-rule tickets) and tenant-word safety (`.*`, `(a+)+$`, empty and non-string entries).
- **Task 3, English only (a756dbf4c).** `rules.is_english`: more than 30% non-Latin letters is not English; otherwise two distinct foreign function words, or one with no English word, is not English; no letters is English. 64 cases (35 English, 29 not, ten scripts and languages, short and mixed tickets) pin it.

Final list sizes: SECURITY 77, BILLING 35, LEGAL 39, ACCOUNT_ACCESS 77, ASK_FOR_PERSON 47 phrases; English 324 words; Spanish 68, French 67, German 55, Portuguese 44, Italian 42 (323 English and 266 foreign tokens after normalising and removing overlap). Fixtures: escalation_set.jsonl has 150 cases (15 security, 11 billing, 10 legal, 17 account access, 18 asked-for-person, 11 fulfilment, 6 critical, 5 type, 11 tenant word, 4 empty, 11 ordering, 5 tenant-word negatives and 26 answerable); language_set.jsonl 64.

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | bf16fe66d | feat | Ticket text cannot reach the model as markup, a link, a hidden character or a forged delimiter |
| 2 | 6f75a2251 | feat | Sensitive, fulfilment, critical, ask-for-a-person and tenant-word tickets go to a person by fixed rules |
| 3 | a756dbf4c | feat | Non-English tickets are recognised by a pinned, dependency-free check |

Plan type `execute` with tasks marked `tdd="true"`: as in 85-01 to 85-04, tests and implementation were written together and committed together per task (no separate RED commit, so no RED evidence record). Mutation checks by hand: dropping `locked out` and `2fa` from ACCOUNT_ACCESS in memory failed acc-02 and acc-04 and nothing else, so the fixture is sensitive to individual phrases.

## Verification

- Task commands: `test_service_desk_sanitize.py` 25 passed; `test_service_desk_rules.py` 55 passed (no skips, none "no tests ran").
- Plan-level run: sanitize, rules, `test_autonomous_ops_copy.py` (ACTV-08 scan covers the new `rules.py` and `phrases.py`), tracer, starters, gate, ledger, tray contract and `test_autonomous_ops_registry.py`: 234 passed plus 8 passed. The tracer run proves the new `clean_text` and `build_prompt` did not change 85-01's behaviour.
- Acceptance greps: `def normalize_for_match` 1; test functions in the sanitise file 18 plus parametrised cases (needs 8); escalation_set.jsonl 151 lines (needs 93); `def evaluate` 1 and `def is_english` 1; language_set.jsonl 65 lines (needs 41); every file under 500 lines (largest rules.py 140, phrases.py 165, sanitize.py 145, tests 290).
- No database was touched by the new tests (pure); the DB-backed regression runs used the private mongod on 27998. No import of httpx, an LLM module or any new dependency in the new files (a test pins the imports of `rules.py`).

## Deviations from Plan

None that changed behaviour. Notes that are choices inside the plan's latitude:

- `phrases.py` is a new file not named in `files_modified`. The plan allows it ("move them to backend/service_desk/phrases.py in this plan"); it was created up front rather than moved, because the language word sets were certain to push `rules.py` past 450 lines. `rules.SECURITY` and the other four lists are re-exported, so the artifact names in the plan hold.
- `neutralise_delimiters` is a public helper in `sanitize.py` (used for ticket text and article text); the plan named the behaviour, not the function.
- The prompt's article text still keeps URLs that a tenant wrote in its own article; only tags and quote characters are neutralised there. The plan's "no http in the prompt" holds for ticket text; 85-06's output check allows only what the cited article says, and the starter articles contain no URL.

## Known limits (recorded, not defects)

- `is_english` knows five Latin-script languages. A Dutch, Polish, Turkish or Swedish ticket with no English or listed foreign word passes as English and is then judged by retrieval. A German or Spanish ticket with exactly one listed word and one English word (for example "ich habe a problem") also passes.
- A tenant word is matched in its folded form: "Project-Falcon" and "Project Falcon" are different words ("projectfalcon" and "project falcon"), and a word is never matched inside a longer word ("payroll" does not match "payrollsystem") nor in another inflection ("payrolls").
- `evaluate` does not yet run anywhere: `pipeline.py` was left untouched (the plan names no pipeline hook). 85-13 wires `rules.evaluate` and `rules.is_english` into `pipeline.prepare` before retrieval, and 85-06 and 85-07 build on the sanitised prompt. Until 85-13, a sensitive ticket still reaches the model on the tracer path.

## Known Stubs

None.

## Authentication Gates

None.

## Threat Flags

None beyond the plan's register: T-85-16 (injection through ticket text) mitigated and tested by 8 hostile prompts, forged-delimiter and hidden-character tests; T-85-17 (sensitive tickets reaching the model) mitigated by the rules and the escalation set, in force once 85-13 wires them; T-85-18 (regular expressions) mitigated by escaped literals, bounded patterns and a bounded-time test; T-85-SC accepted (nothing installed). No endpoint, collection or dependency was added.

## User steps

None done and none needed. No restart, publish, push, install or agent build was done; the backend runs from the checkout, so these modules go live with the next backend restart, but nothing calls them until 85-13.

## Notes

- The user's uncommitted work (`backend/tickets_endpoints.py`, `components/InternalTicketsDashboard.tsx`, `shared/catalogue-gaps.json`, the Rust `Cargo.toml` and `Cargo.lock`, `App.tsx`, `backend/requirements.txt` and the other modified files) was not touched and is still unstaged. None of this plan's files carried user changes; every commit staged explicit paths.
- Requirement IDs DESK-02 and DESK-03 are not marked Complete (the phase is not finished, and 85-13 and later plans also touch them).

## Self-Check: PASSED

Created files `rules.py`, `phrases.py`, `escalation_set.jsonl`, `language_set.jsonl`, `test_service_desk_sanitize.py` and `test_service_desk_rules.py` exist and `sanitize.py` is modified; commits bf16fe66d, 6f75a2251 and a756dbf4c are ancestors of HEAD (3 commits measured from plan_head_before); every task's acceptance greps and the plan-level verification commands were re-run green.
