---
phase: 85-first-line-service-desk
plan: 38
subsystem: service-desk
tags: [output-checks, handoff, ledger, staff-note, live-recheck, gap-closure, G-85-3]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: 85-37 given_citations, A-id prompt, PROMPT_TAGS, parse_reply
provides:
  - OUTPUT_RULE_LABELS (one staff label per output rule) and STAFF_NOTE_RULE in service_desk/messages.py
  - handoff.handoff(..., rule=): the staff note, the ledger reasonText and desk.rule name the rule that refused a reply
  - pipeline passes the failing rule (unparseable included) to the hand-off
  - live proof on this VM's llama3.2:3b that 85-37 holds (DESK-03 sets + three printer runs)
affects: [gsd-verify-work 85, UAT round 4 of G-85-3]

actuals:
  tokens: 9000
  tasks: 2
  commits: 1
plan_head_before: ab8dc3fffd74a15e38d9edd241ffa66ed2bf4f95
plan_head_after: feb124937ccdae8c920cfef6b06fe3e991fe652b
commits: 1

tech-stack:
  added: []
  patterns: ["staff-only reason detail (rule label) in the note and ledger row; the refused model text is never stored"]

key-files:
  created: []
  modified:
    - backend/service_desk/messages.py
    - backend/service_desk/handoff.py
    - backend/service_desk/pipeline.py
    - backend/tests/test_service_desk_citations.py

key-decisions:
  - "A-85-G36: only the rule is recorded (desk.rule, a staff label in the note and in the reasonText); the refused reply text is not stored"
  - "A-85-G37 was not needed: no live run failed, so SYSTEM_PROMPT and sanitize.py are unchanged"

requirements-completed: [DESK-01, DESK-02, DESK-03]

coverage:
  - id: D1
    description: "A refused reply is handed to a person with reason output_check_failed; the staff note and the ledger row name the failing rule; an unparseable reply records 'unparseable'; other reasons keep today's note"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_citations.py#test_a_refused_reply_names_the_rule_to_staff_and_in_the_ledger_never_to_the_requester"
        status: pass
      - kind: integration
        ref: "backend/tests/test_service_desk_citations.py#test_an_unparseable_reply_records_the_rule_unparseable"
        status: pass
    human_judgment: false
  - id: D2
    description: "The requester never sees the rule, its label or the model text; handoff rejects a rule for any other reason or an unknown rule before writing"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend/tests/test_service_desk_citations.py (requester_items assertion, test_a_rule_is_only_for_an_output_check_hand_off_and_must_be_a_known_rule, test_there_is_one_staff_label_per_output_rule)"
        status: pass
    human_judgment: false
  - id: D3
    description: "On this VM's llama3.2:3b the DESK-03 sets pass and the printer starter answer passes every output rule three times out of three, citing only the printer article"
    requirement: DESK-03
    verification:
      - kind: other
        ref: "backend/venv/bin/python backend/scripts/service_desk_eval.py --sets (exit 0) and scratchpad 85-38/printer_recheck.py (exit 0)"
        status: pass
    human_judgment: false

duration: 25 min
completed: 2026-11-10
---

# Phase 85 Plan 38: Failing output rule recorded, live re-check of the printer fix Summary

**An output-check hand-off now says which rule refused the reply (staff note and ledger row only), and the 85-37 citation fix is proven on the real llama3.2:3b: the DESK-03 sets pass and the printer answer passes every output rule three out of three.**

## Accomplishments

- Task 1 (tracer, feb124937): `messages.OUTPUT_RULE_LABELS` (keys equal `checks.RULES`) and `STAFF_NOTE_RULE`; `handoff.handoff(..., rule=None)` writes the note "Service desk: output check failed (<rule label>).", a reasonText of the form "Output check failed (<rule label>).", and `desk.rule` on the servicedesk ledger row; a rule with any other reason, or an unknown rule, raises ValueError before any write; the pipeline computes the failing rule once (`unparseable` when the reply did not parse) and passes it through. The refused reply is neither stored nor logged. Hand-offs without a rule are unchanged (the existing handoff, pipeline, tracer tests pass). Tests added to test_service_desk_citations.py (209 lines).
- Task 2 (verification only, no commit): the two live read-only runs below. Neither wrote anything.

## Task Commits

1. Task 1 (tracer): `feb124937` feat(85-38): a refused reply hands over with the failing output rule in the staff note and ledger row (G-85-3)
2. Task 2: no commit (verification only); the reproduction script is `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/20f37e46-95f9-49f8-bdb4-3cd6ffc2b208/scratchpad/85-38/printer_recheck.py`.

## Verification

Task 1 (private mongod 127.0.0.1:27998):
- pytest (citations, handoff, pipeline, tracer, starters, output_checks, worker, autonomous_ops_copy): 251 passed, 0 failed, 0 skipped.
- vitest serviceDeskCopy + autonomousOpsCopy: 2 files, 40 tests passed.
- Tracer gate: the verify commands passed end to end before Task 2 started.

Task 2, live on ollama 127.0.0.1:11434 (llama3.2:3b), load average 2.8 at start, no build or test job running:

`backend/venv/bin/python backend/scripts/service_desk_eval.py --sets` (exit 0):

```
escalation: 150 cases, 0 failed
injection: 33 cases, 25 reached the model (0 got no answer), 8 handed off before it, 0 failed
retrieval: 100 cases, 0 not as expected, margin 0.2268 (lowest match 0.3528, highest non-match 0.1260; CUT 0.24)

RESULT: every check held (nothing was written)
```

Against the UAT round 3 baseline (escalation 150/0, injection 33 with 25 reached the model and 8 handed off, 0 failed, retrieval 100/0 unexpected, margin 0.2268): identical. 23 of the 25 model cases were "accepted (checked answer)"; 2 (html-hidden, run-command) were "rejected by the output checks (foreign_command)", which is the intended outcome for those injections.

`printer_recheck.py` (exit 0), the UAT round 3 printer ticket, same retrieval, build_prompt, OllamaClient().generate, parse_reply and check as the pipeline:

```
RUN 1: matched=['Fixing a printer that will not print']
  raw reply: '{"answer": "Check the printer\'s power, paper, and toner/ink, and clear any paper jams. Also, ensure the correct printer is chosen in the print dialog.", "cited": ["A1"]}'
  parsed citations=[1] given_citations=[1] rule=None
RUN 2: (same match, same raw reply, parsed citations=[1] given_citations=[1] rule=None)
RUN 3: (same match, same raw reply, parsed citations=[1] given_citations=[1] rule=None)
run_injection_case: outcome='accepted (checked answer)' problems=[]
RESULT: ok
```

The three raw replies were byte-identical. `git status --porcelain` shows no file of this plan changed by the live runs.

## Deviations from Plan

None - plan executed exactly as written. A-85-G37 (one length-sentence change) was not needed.

## Known Stubs

None.

## Threat Flags

None. T-85-130: the rule label is only in the staff-visibility note and the ledger row, tested on `projection.requester_items` (only the hand-off notice) and by checking the refused reply text (an injected link, free text) is absent from the stored ticket and the ledger row. T-85-131: `desk.rule` and the reasonText name the rule. T-85-132: the live sets show 0 failed and the printer reproduction passed 3/3.

## Notes for the user

- Not deployed: the live backend runs from this checkout with no reload; the rule-aware hand-off and the 85-37 prompt change reach it only at the next backend restart.
- The live re-check is the model call only. The full path (ticket created on the live platform, draft appears) still needs a UAT round 4 run after the restart.
- The model gave a short generic answer (power, paper, toner, paper jams, printer choice) rather than copying the article steps; it passed every rule and cites only the printer article.

## Self-Check: PASSED

- backend/service_desk/messages.py, handoff.py, pipeline.py and backend/tests/test_service_desk_citations.py contain the changes; feb124937 is an ancestor of HEAD; `commits: 1` measured from the ledger base ab8dc3fff.
