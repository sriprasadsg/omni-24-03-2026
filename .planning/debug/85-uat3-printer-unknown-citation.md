---
status: diagnosed
gap_id: G-85-3
phase: 85-first-line-service-desk
found: 2026-11-10 UAT round 3 (test 3, live API on Omniai-copy)
goal: find_root_cause_only
---

# Printer starter answers are always refused (unknown_citation)

## Symptom
ABC ticket "My printer will not print / My printer will not print, jobs just sit in the queue." (type incident,
priority medium) matched only the printer starter (score 0.754) and was handed to a person with
`output_check_failed`. Password tickets drafted fine in the same run.

## Reproduction (read-only, no DB writes)
Same retrieval, `build_prompt`, `OllamaClient().generate` (llama3.2:3b on 127.0.0.1:11434) and `check()` the
pipeline uses, run three times: 3/3 `unknown_citation`. The model reply ends
`..., "cited": [1, 2, 3, 4, 5, 6]}` while only article 1 was given.

## Root cause
1. `backend/service_desk/sanitize.py:160-163` labels articles with bare numbers (`<article id="1" ...>`) and the
   system prompt asks for `"cited": [1]` "numbers of the articles you used". The printer starter
   (`backend/service_desk/starters.py`, key `printer`) is a numbered list 1-6, so the 3B model reads its step
   numbers as article numbers and cites 1..6.
2. `backend/service_desk/checks.py` `check()` fails the whole reply on the first unknown citation
   (`unknown_citation`, order: empty_answer, no_citation, unknown_citation, ...), so an answer that is otherwise
   copied from article 1 is thrown away.
3. `backend/service_desk/pipeline.py:115-116` discards the failing rule name and the model reply on that path
   (`_handoff(..., "output_check_failed")`), so staff and the Activity row only say "Output check failed." and a
   false positive cannot be told from a real one without re-running the model.

## Fix directions (for the planner, not binding)
- Give articles ids that cannot collide with list numbering (for example `A1`, `A2`) in `build_prompt`, the
  system text and `parse_reply`/`check`, or have `check` drop citation numbers that were not given when at least
  one given number remains (the grounding checks then run against the valid cited articles only). Either way
  keep the DESK-03 injection/escalation/retrieval sets green (`backend/scripts/service_desk_eval.py --sets`,
  85-22) and the offline tests that pin the prompt shape.
- Record the failing rule in the ledger reason / staff note (rule name only, never the model text in the
  requester-visible path).
- After the citation fix, confirm the printer answer passes the remaining rules (too_long, too_many_lines, the
  foreign_* rules: the starter mentions the VPN and a restart) with the same reproduction.

## Evidence
- Live run notes: `.planning/phases/85-first-line-service-desk/85-UAT.md` test 3.
- Archived ticket/ledger rows: `~/omni-archives/uat85-test3/run2-*.ejson` (ticket TKT-0002 of run 2).
