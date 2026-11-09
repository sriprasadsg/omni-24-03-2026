---
phase: 85-first-line-service-desk
plan: 13
subsystem: service-desk
tags: [service-desk, pipeline, hand-off, injection, stop, output-checks]
status: complete

requires: [85-01, 85-03, 85-04, 85-05, 85-06, 85-07, 85-11, 85-12]
provides:
  - "pipeline.prepare: stop, fixed rules (rules.evaluate with the tenant's stored words), English check, article cut-off and gap rows, all before any model call; every failure is a recorded hand-off"
  - "pipeline.answer: availability probe, call timeout sized by runtime.call_timeout, busy/offline/check-failed hand-offs, cited texts passed to the checks, re-read of the ticket, gate decision, post or staff draft"
  - "service_desk/outcomes.py: build_request, draft_reason, post, keep_draft, post_lost_to_draft (Activity words on every desk row)"
  - "outcome words (job.reason): posted, drafted, ticket_changed, ticket_missing, desk_off and every hand-off reason"
  - "ticket and row field desk.draftReason (one of the 8 DRAFT_REASONS)"
  - "fixtures/service_desk/injection_set.jsonl (33 cases) and test_service_desk_injection.py"
affects: [85-14, 85-16, 85-17, 85-18, 85-22]

actuals:
  tokens: 31000
  tasks: 3
  commits: 3
plan_head_before: e81715642cf24279dbce12d8bc778d5dd5d524f4
plan_head_after: 19f7ba7dfc2fe2a36fe1b6bbe83472e44be1088f

tech-stack:
  added: []
  patterns:
    - "Fixed rules before the model, gate after it: the reply is read for answer and cited only; outcomes come from rules, the gate and the output checks"
    - "Status compare-and-set before the post: a ticket a person moved is never overridden; a lost race turns the row into the suggestion a draft needs"
    - "Stop during generation: the gate's refused row carries desk, the text is kept as a staff draft with draftReason stopped"

key-files:
  created:
    - backend/service_desk/outcomes.py
    - backend/tests/test_service_desk_pipeline.py
    - backend/tests/test_service_desk_injection.py
    - backend/tests/fixtures/service_desk/injection_set.jsonl
  modified:
    - backend/service_desk/pipeline.py
    - backend/tests/test_service_desk_tracer.py

key-decisions:
  - "The job outcome of a hand-off is the hand-off reason itself (service_desk_offline instead of the tracer's offline); the tracer expectations were updated"
  - "A post moves the status by compare-and-set first and writes the comment second; a failure of either leaves nothing posted and the answer becomes a draft (outcome ticket_changed)"
  - "An Off desk at pickup or after generation writes nothing at all (outcome desk_off), matching D-03 'when the desk was merely Off no row exists'"
  - "A simulated post is worded with autonomous_ops.messages.simulation_result around the desk sentence (Phase 81 prefix rule)"

requirements-completed: []

coverage:
  - id: D1
    description: "Every pre-model hand-off reason (empty_ticket, critical_priority, fulfilment_request, type_not_answered, security/billing/legal topic, account_access, asked_for_person, tenant_word, not_english, no_article, desk_stopped) is a recorded hand-off with no generate request; gap rows only for no_article and not_english"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_pipeline.py (15 hand-off tests, escalation set)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Offline, busy (503 and timeout) and failed-output-check replies are hand-offs; nothing is posted or drafted; the generate timeout is the one sized from the measurement; reason.inputs carries model, genMs, loadMs and token counts"
    requirement: "DESK-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_pipeline.py#test_the_generate_timeout_is_the_one_sized_from_the_measurement; #test_a_post_notifies_the_reporter_and_words_the_activity_row"
        status: pass
    human_judgment: false
  - id: D3
    description: "Draft reasons level_suggest, mode_drafts, shadow, desk_rate_limit, desk_breaker, no_tray_window, settings_unreadable and stopped, each stored on ticket and row; a stop during generation posts nothing; a ticket a person moved or answered gets no post"
    requirement: "DESK-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_pipeline.py (draft-reason and stop/changed-ticket tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "33 injection tickets, each run with a compliant and a benign stand-in model: no queue document, status only open or pending_customer, assignee only by the queue rule, every kept answer passes the output checks, no link/address/markup in any prompt"
    requirement: "DESK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_injection.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Extra reply keys (confidence, close_ticket, assignee, status, priority) change nothing; the reply is read for answer and cited only"
    requirement: "DESK-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_pipeline.py#test_keys_the_model_adds_to_its_reply_change_nothing"
        status: pass
    human_judgment: false
---

# Phase 85 Plan 13: The pipeline joined end to end Summary

One attempt on a desk ticket now runs every rule in order: stop, fixed text rules with the tenant's own words, English check, article cut-off, model probe and sized call, output checks against the cited articles, re-read of the ticket, the Autonomous Ops gate, then a post, a staff-only draft or a recorded hand-off to a person; a 33-case injection set and the 150-case escalation set pass through the whole path.

Duration: about 35 minutes. Tasks: 3. Files: 6 (4 created, 2 modified). Completed 2026-11-09.

## Accomplishments

- **Task 1 (9db475e56), the pipeline.** `prepare` returns a hand-off for a missing ticket (`ticket_missing`, no write), an Off desk (`desk_off`, no write), a stop (`desk_stopped`, no requester notice), then `rules.evaluate`, `rules.is_english` and retrieval (`no_article`); gap rows come only from `handoff.handoff` for `no_article` and `not_english`. `answer` probes the model (`service_desk_offline`), sizes the timeout with `runtime.call_timeout(prompt chars, 220, load_measurement, recent_gen_ms)`, maps every `ModelError` including `ModelBusy` and `ModelTimeout` to `service_desk_busy`, parses and checks with `{n: article.content}` as the cited texts (`output_check_failed`), re-reads the ticket, and asks the gate. `outcomes.py` holds the writers and the draft-reason map.
- **Task 2 (b4b40f311), the injection set.** 33 invented cases (override in English, paraphrase, Spanish/French/German/Chinese, base64, system-role spoof, fake ticket and article delimiters, hidden HTML, markdown image, reply-with-link, close/resolve/assign/priority/email-the-password, command, padding, code fence, tool-call and JSON spoofs, hidden-character and full-width variants, sensitive-word and tenant-word variants). Compliant run: 21 end in `output_check_failed`, 4 are handed off by rules or language before the model, and the plain-text ones are kept. Benign run: 20 posted (then the 21st+ are `desk_rate_limit` drafts), rest handed off.
- **Task 3 (19f7ba7df), escalation and extra keys.** All 119 escalation cases with an expected reason are handed off with zero generate requests; the 31 answerable cases either reach the model once or stop at retrieval/language; a reply carrying `confidence`, `close_ticket`, `assignee`, `status` and `priority` leaves comments, status, assignee, priority and row state identical to one without.
- **Mutation checks by hand** (each restored before committing): removing the `rules.evaluate` call failed 12 tests; passing no cited texts failed the badge-link test; neutralising the re-read failed the person-replied test; removing the English check, the prepare stop check, the sized timeout, the requester notice, the stop-draft branch and the `ModelError` mapping each failed their own tests (1, 1, 1, 1, 2 and 2).

## Task Commits

| Task | Commit | Type | Description |
| ---- | ------ | ---- | ----------- |
| 1 | 9db475e56 | feat | Every stage of one desk attempt is wired and every failure is a hand-off |
| 2 | b4b40f311 | test | The prompt-injection set runs through the whole desk pipeline |
| 3 | 19f7ba7df | test | The escalation set end to end and the model's extra reply keys change nothing |

Plan type `execute` with tasks marked `tdd="true"`: as in 85-01 to 85-12, tests and implementation were written together and committed together per task (Task 3's tests pass on Task 1's code, so it is a test-only commit). The Task 3 tests were held out of the Task 1 commit by truncating the test file for the first commit.

## Verification

- Task 1 command (pipeline, tracer, gate, structural): pipeline 34 + tracer 16 + structural 15 passed at commit time; Task 2: 4 passed; Task 3: 37 passed in the pipeline file. No skips (private mongod 27998 answering).
- Final run on 27998 of every `test_service_desk_*.py` file plus `test_autonomous_ops_copy.py` and `test_autonomous_ops_structural.py`: 593 passed, 0 skipped.
- Acceptance greps: `handoff(` or `handoff.handoff` in pipeline.py 10 (needs 6); `call_timeout` 1; pipeline.py 153 lines and outcomes.py 129 (both under 500); `^async def test_` in the pipeline test 37 (needs 24); injection_set.jsonl 34 lines (needs 26); the injection test asserts the three queue collections are empty after each of the 66 runs.
- Every test used the private mongod on 27998 and httpx MockTransport stand-ins. Nothing touched 27017 and no real model was called.

## Hand-overs from earlier plans (all done)

| From | Item | Status |
| ---- | ---- | ------ |
| 85-05 | `rules.evaluate(ticket, cleaned, words)` and `rules.is_english` wired before retrieval and the model | done, mutation-checked |
| 85-06 | `checks.check(parsed, ids, {n: matches[n-1].content})` | done, mutation-checked (badge link test) |
| 85-07 | `ModelBusy`/`ModelTimeout` (and every `ModelError`) to the busy hand-off | done |
| 85-07 | `runtime.call_timeout` from `load_measurement` and `recent_gen_ms` replaces the fixed 120 s | done, mutation-checked |
| 85-07 | `client.available()` before generating | done (`service_desk_offline`) |
| 85-01 | Re-read before the post; post only on status open and no person-visible reply | done; the status now moves first by compare-and-set so the old "posted but status unchanged" window is closed |
| 85-12 | Answer-posted path calls `notify.requester_notice` itself | done (`outcomes.post`), mutation-checked |
| 85-12 | `handoff.py` for every hand-off reason; gaps only through it | done |
| 85-04 / decision 3 | Stop during generation: nothing posted, refused row kept, staff draft `stopped`; queued ticket during a stop: `desk_stopped`, no notice | done, tested for tenant and platform stop |
| 85-11 | `settings.load` supplies words and mode | done (loaded in prepare and again after generation) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test fit] Tracer expectations follow the new hand-off rows**
- **Found during:** Task 1
- **Issue:** 85-01's tracer tests asserted "no row" and job reason `offline` for an unreachable model, no_article and failed checks. Hand-offs now write a ledger row and notes (that is the plan's purpose) and the offline outcome is `service_desk_offline`.
- **Fix:** added `_answers` and `_model_comments` helpers in `test_service_desk_tracer.py`; the assertions now say "no answer row" and "no model comment".
- **Files modified:** backend/tests/test_service_desk_tracer.py
- **Commit:** 9db475e56

**2. [Rule 2 - Safety] Status moves before the comment, with a draft fallback**
- **Found during:** Task 1
- **Issue:** 85-01 posted the comment first, so a person who moved the ticket between the re-read and the post still got an automatic answer on their ticket.
- **Fix:** `outcomes.post` does the status compare-and-set first; if it loses, or the comment cannot be written (the status is put back), the row becomes the suggestion a draft needs (`post_lost_to_draft`) and the job ends `ticket_changed`. Test: `test_a_ticket_moved_after_the_gate_but_before_the_post_is_kept_as_a_draft`.
- **Commit:** 9db475e56

**3. [Rule 2 - Safety] Off desk writes nothing**
- **Issue:** a job queued before the tenant switched the desk Off would have produced drafts or hand-off notices for an Off desk.
- **Fix:** `prepare` and `answer` end with outcome `desk_off` and write nothing (D-03).
- **Commit:** 9db475e56

**Total deviations:** 3 (1 test fit, 2 safety). **Impact:** none on scope; no architectural change.

## Known limits (recorded, not defects)

- **Draft reason for a changed ticket.** The 8 draft reasons are fixed by the plan, none says "the ticket changed". A draft kept because a person moved or answered the ticket carries `mode_drafts` (or whichever the gate's reason maps to) in its staff text. The job outcome `ticket_changed` is the only record. Adding a ninth reason is a three-place change (`__init__.DRAFT_REASONS`, `messages.DRAFT_REASON_TEXT`, the 85-12 pinned count) the user may want in a later plan.
- **A compliant model's plain-text lie is kept.** Per the plan, success means no action, no leak and either a hand-off or a checked answer. A reply such as "I have closed this ticket" (no link, address, number or command) passes the checks and is posted as text; the ticket itself is not closed, the status is only ever `pending_customer`. The live re-run (85-22) shows what the real model does.
- **Unreadable desk settings.** The tenant's own words come from the desk setting; when it cannot be read the words list is empty, so the ticket is judged by the built-in rules only. The answer is then forced to a draft (`settings_unreadable`), never a post.
- **A hand-off after a slow failure.** If the model fails after a person has taken the ticket, the hand-off still adds its staff note and requester notice (the same fail-safe direction as elsewhere; no assignee is overridden).
- **Simulation wording.** The shadow row's result is the Phase 81 `simulation_result` wrapper around the desk sentence: "Nothing was done. This is what would have happened: Would have posted the answer to ticket TKT-0001. Nothing was posted." The UI-SPEC shows only the desk sentence and says the 81 prefix rule applies; the wording can be tightened in the UI plans.
- **Rate-limit drafts in the benign injection run** (21st post onward) are expected: the desk pool is 20 an hour.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-85-46 (injection set asserts empty queue collections after every run), T-85-47 (extra-keys test), T-85-48 (cited-text checks and the badge-link pair), T-85-49 (offline/busy/timeout hand-offs and the sized timeout), T-85-50 (refused row recorded, draft staff-only). No endpoint, collection or dependency was added.

## User WIP preserved

None of this plan's files carried user changes. `git status` still shows the user's modified and untracked files (`backend/tickets_endpoints.py`, `components/InternalTicketsDashboard.tsx`, the Rust sources and others) unstaged; every commit staged explicit paths. No `git add -A`, stash, restore or reset was run.

## User steps

None done and none needed. The backend runs from the checkout, so the wired pipeline goes live with the next backend restart (the user's step). Not done, by design: restart, UI publish, git push, installing Ollama, building the agent, any write to the live database. Ollama is not installed, so on the live system every ticket would end `service_desk_offline` until the model is pulled and measured (85-22).

## Next

Ready for 85-14.

## Self-Check: PASSED

- Files exist: `backend/service_desk/pipeline.py`, `backend/service_desk/outcomes.py`, `backend/tests/test_service_desk_pipeline.py`, `backend/tests/test_service_desk_injection.py`, `backend/tests/fixtures/service_desk/injection_set.jsonl`.
- Commits 9db475e56, b4b40f311 and 19f7ba7df are ancestors of HEAD; `git rev-list --count e81715642..HEAD` was 3 before this SUMMARY (matches `commits: 3`).
- All three tasks' acceptance greps and verification commands were re-run green (see Verification). Every hand-over listed in the dispatch is done.
