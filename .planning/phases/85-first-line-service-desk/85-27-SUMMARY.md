---
phase: 85-first-line-service-desk
plan: 27
subsystem: service-desk-backend
tags: [wr-102, wr-103, write-order, outcomes, send-draft, repudiation, gap-closure]

requires:
  - phase: 85-first-line-service-desk
    provides: "85-13 outcomes.post/keep_draft and worker._to_a_person; 85-14 lifecycle.send_draft; 85-17 worker passes"
provides:
  - "outcomes._step/_FAILED: guarded, logged follow-up writes after a visible answer or draft, with one re-attempt of the desk phase and the executed move"
  - "worker._desk_wrote_answer: a desk ai_answer/ai_draft on the ticket counts as answered for _fail and the stale-job recovery even while desk.phase is queued"
  - "lifecycle.send_draft: status compare-and-set first, visible turn second, status put back to its origin when the turn is lost"
  - "backend/tests/test_service_desk_write_order.py: 15 injected-failure tests"
  - "WR-102 and WR-103 recorded fixed in 85-REVIEW-DISPOSITION.md (open 25 -> 23)"
affects: [85-28, 85-29 phase gate, 85-VERIFICATION re-verification]

actuals:
  tokens: 14000
  tasks: 3
  commits: 6
plan_head_before: 4f137be21d9dc51e1a65c78e22581db1dbf49a18
plan_head_after: 59a7eb40aab468de011a0f44d6f2a71458b753e9
commits: 6

tech-stack:
  added: []
  patterns:
    - "Guarded post-commit steps: _step logs and returns a sentinel; a try/finally re-attempts the two writes other parts of the desk depend on"
    - "Compare-and-set the status before the visible change, and put it back from the ticket's own history when the visible change loses"

key-files:
  created:
    - backend/tests/test_service_desk_write_order.py
  modified:
    - backend/service_desk/outcomes.py
    - backend/service_desk/worker.py
    - backend/service_desk/lifecycle.py
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md

key-decisions:
  - "A-85-G11: a desk write that keeps failing after the answer is visible leaves the answer in pending_customer with desk.phase queued and an error log naming the ticket; no hand-off is attempted (tested)"
  - "A-85-G12: a ticket a person already set to pending_customer still gets its draft sent, with no status move and nothing to put back (tested)"
  - "The put-back after a lost turn is skipped when the winner already sent the answer (a sender that skipped the move because the ticket was already pending_customer must keep that status) and returns to the status read from the ticket's own history, not the stale first read"

requirements-completed: [DESK-01, DESK-05]

coverage:
  - id: D1
    description: "WR-102 post: a desk write, executed move, Activity words or notice that fails after the answer is posted never hands the ticket off; the ticket ends pending_customer with one requester-visible ai_answer, desk.phase posted, the row executed and the job reason posted"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_failed_desk_write_after_the_answer_is_repaired_and_never_handed_off"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_failed_executed_transition_is_repaired_and_never_handed_off"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_failed_activity_words_and_notice_never_hand_the_ticket_off"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_desk_write_that_keeps_failing_leaves_the_visible_answer_and_no_hand_off"
        status: pass
    human_judgment: false
  - id: D2
    description: "WR-102 belt: _to_a_person(only_if_unanswered=True) treats a desk ai_answer or ai_draft on the ticket as answered while desk.phase is still queued"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_crash_after_the_comment_is_never_followed_by_a_hand_off"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-102 keep_draft and post_lost_to_draft: after the draft is written every step is guarded, draftWaiting is re-attempted, and a failed suggested move is retried"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_failed_desk_write_after_the_draft_is_repaired_and_keeps_the_draft_waiting"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_failed_suggested_move_after_a_lost_post_still_ends_with_the_staff_draft"
        status: pass
    human_judgment: false
  - id: D4
    description: "WR-103 / D-09 / D-31: send_draft moves the status first, refuses with the fresh ticket's code when the move is lost, puts the status back when the turn is lost, and two sends at once give one winner and one status change"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_a_lost_status_move_refuses_the_send_and_the_comment_stays_a_draft"
        status: pass
      - kind: unit
        ref: "backend/tests/test_service_desk_write_order.py#test_two_people_sending_at_once_give_one_winner_one_status_change_and_one_notice"
        status: pass
    human_judgment: false

duration: "about 1h"
completed: 2026-11-09
status: complete
---

# Phase 85 Plan 27: write order after a visible answer (WR-102, WR-103) Summary

A failure after the requester can already read a desk answer or draft no longer produces a "service desk busy" hand-off, a row stuck at dispatching or a draft hidden from the draft panel, and a person-sent draft becomes visible only on a ticket that really moved to pending_customer.

## Accomplishments

- **WR-102 post (tracer, `3a1937b7d`).** `outcomes.post` guards every step after the comment through `_step` (desk fields, the dispatching -> executed move, the Activity words, the requester notice), logs each failure with the ticket, and in a final `try/finally` re-attempts the desk phase and the executed move once. It returns True and never raises after the comment. `worker._to_a_person(only_if_unanswered=True)` (used by `_fail` and the stale-job recovery) now also treats a desk-written `ai_answer`/`ai_draft` comment as answered, so a crash between the comment and the desk write cannot add a contradicting hand-off. The belt was mutation-checked: with the new condition replaced by `False` the crash test fails.
- **WR-102 keep_draft and post_lost_to_draft (`881e0f590` RED, `86cd504bd`).** After the draft comment (the one unguarded write: nothing is visible if it raises) the desk fields, the row's desk fields and the Activity words are guarded and the desk write (`draftWaiting`, `draftReason`) is re-attempted in a `finally`. `post_lost_to_draft` logs and retries a failed suggested move, so the staff draft that follows is always written.
- **WR-103 send_draft (`390c166eb` RED, `ec308e6d9`).** Status compare-and-set to pending_customer first (skipped when a person already set it, A-85-G12); a lost move refuses with the code the fresh ticket gives (`ticket_closed` with its state, `person_replied`, `no_requester`) or `already_handled`, leaving the comment a staff-only draft; the visible turn follows; a lost turn puts the status back to the one the send moved from (read from the ticket's history) unless the winner already sent the answer. The status only ever returns to open, in_progress or on_hold (PROH-85-04).
- **Disposition (`59a7eb40a`).** WR-102 fixed (3a1937b7d, 86cd504bd) and WR-103 fixed (ec308e6d9); open count 25 -> 23.

## Task Commits

1. Task 1 (tracer): `3a1937b7d` feat - post guarded steps, worker belt, 5 tests
2. Task 2: `881e0f590` test (RED, 4 failing) -> `86cd504bd` feat
3. Task 3: `390c166eb` test (RED, 3 failing) -> `ec308e6d9` feat; `59a7eb40a` docs (disposition)

## Verification

- Plan-level run (write_order, pipeline, worker, gate, lifecycle, portal_routes, withdraw, returns) against the private mongod on 127.0.0.1:27998: 222 passed, 1 failed, 0 skipped.
- The one failure is the known pre-existing `test_service_desk_lifecycle.py::test_this_fixed_it_resolves_the_ticket_and_only_this_does`, failing with the same assertion (`total_hold_duration >= 0`, a negative value because the file pins `NOW` at 2026-11-09 14:30 UTC while the hold start uses the real clock). It failed identically on HEAD before any edit of this plan (reproduced first: 1 failed, 31 passed). Not touched here; 85-29 fixes it.
- Acceptance greps: `_FAILED`, `async def _step(` and `finally:` in outcomes.py; `SYSTEM_AUTHOR` imported in worker.py; send_draft's `move_status` (line 118) sits before its `_turn_draft` call (line 123). outcomes.py 172 lines, lifecycle.py 322, the new test file 359, all under 500.

## Deviations from Plan

None - plan executed as written. Two small additions inside the plan's scope: the put-back reads the ticket again and (a) skips when the winner already sent the answer, (b) uses the status from the ticket's own history, because a stale first read or a concurrent sender that skipped the move could otherwise have the put-back revert a status that a visible answer relies on (extra test `test_the_put_back_returns_to_the_status_the_send_moved_from`). `post_lost_to_draft` keeps its three-argument signature (pipeline.py untouched); its failure log names the action id since the ticket id is not passed in.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema change. T-85-96 and T-85-97 are mitigated as planned; PROH-85-15 and PROH-85-04 hold for the paths covered by the tests above.

## Self-Check: PASSED

- `backend/tests/test_service_desk_write_order.py` exists; the six commits (3a1937b7d, 881e0f590, 86cd504bd, 390c166eb, ec308e6d9, 59a7eb40a) are ancestors of HEAD.
- Only this plan's files were staged in each commit (checked with `git diff --cached --name-only` before each commit); no user WIP file was touched.
