---
phase: 85-first-line-service-desk
plan: 29
subsystem: service-desk-backend-tests
tags: [wr-203, wr-301, wr-302, wr-303, knowledge-gaps, test-hygiene, phase-gate, gap-closure]

requires:
  - phase: 85-first-line-service-desk
    provides: "85-24 to 85-28 gap-closure plans (CR-101, WR-101..103, WR-201, WR-202, CR-401); 85-15 gap list and write-article route"
provides:
  - "API_DETAIL['gap_article_not_helpdesk'] and the 422 refusal in write_article, raised before any gap row is claimed"
  - "backend/tests/service_desk_support.desk_indexes_without_ttl: desk indexes without the two 90-day TTL indexes, used by the worker, hand-off and knowledge-gap fixtures"
  - "--sets test that proves no database is opened (client factory and open_database replaced by raising recorders) and asserts the exact generate count"
  - "85-REVIEW-DISPOSITION.md: 11 findings fixed, 17 open; 85-VALIDATION.md: one row per gap plan"
  - "The Phase 85 gate on the code of 85-24 to 85-29: 2179 backend tests, 1873 UI tests, build exit 0"
affects: [85-SECURITY re-run, 85-VERIFICATION re-run]

actuals:
  tokens: 30000
  tasks: 3
  commits: 3
plan_head_before: 53bb90e479a9bec8130dbefdf0000ae51f1c2a84
plan_head_after: 523fe3f6fdc5d4502db3cceeb8a4730ca2bf0942
commits: 3

tech-stack:
  added: []
  patterns:
    - "Fixtures that stamp rows from fixed clocks build the desk indexes without the TTL indexes; migration 032's own test keeps covering them"
    - "A 'makes no database connection' claim is tested by replacing both the client factory and the opener with raising recorders"

key-files:
  created: []
  modified:
    - backend/service_desk/messages.py
    - backend/knowledge_helpdesk_endpoints.py
    - backend/tests/test_service_desk_knowledge_gaps.py
    - backend/tests/service_desk_support.py
    - backend/tests/service_desk_worker_support.py
    - backend/tests/test_service_desk_handoff.py
    - backend/tests/test_service_desk_worker.py
    - backend/tests/test_service_desk_eval_script.py
    - backend/tests/test_service_desk_lifecycle.py
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md
    - .planning/phases/85-first-line-service-desk/85-VALIDATION.md
    - .planning/phases/85-first-line-service-desk/deferred-items.md

key-decisions:
  - "A-85-G16 kept: the TTL indexes are dropped in the fixtures rather than deriving the clocks from real time (the return tests pin weekdays)"
  - "A-85-G17 kept: ArticleEditDialog.tsx is not changed; unticking Help desk while writing from a gap now gets the server's 422 sentence"
  - "The lifecycle clock failure was fixed in the test only: the ticket's hold start is set an hour before the test's fixed NOW after the answer run"

requirements-completed: [DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07]

coverage:
  - deliverable: "WR-203: an article written from a gap must be a Help desk article (422 before any claim)"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_knowledge_gaps.py#test_an_article_from_a_group_must_be_a_help_desk_article_or_nothing_is_claimed"
        status: pass
    human_judgment: false
  - deliverable: "WR-301: fixtures leave out the 90-day TTL indexes; the 100-day row is asserted stored"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_worker.py#test_the_fixtures_and_the_worker_leave_out_the_90_day_ttl_indexes"
        status: pass
      - kind: test
        ref: "backend/tests/test_service_desk_knowledge_gaps.py#test_only_open_no_article_rows_of_the_last_90_days_for_this_tenant_are_listed"
        status: pass
    human_judgment: false
  - deliverable: "WR-302: the runner test no longer pins 032 as the highest migration"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_worker.py#test_the_runner_finds_migration_032_and_it_follows_031"
        status: pass
    human_judgment: false
  - deliverable: "WR-303: --sets opens no database; exact generate count"
    verification:
      - kind: test
        ref: "backend/tests/test_service_desk_eval_script.py#test_sets_make_no_database_connection_and_no_request_but_the_model_ones"
        status: pass
      - kind: test
        ref: "backend/tests/test_service_desk_eval_script.py#test_sets_with_a_benign_model_exit_0_with_a_summary_line_per_set"
        status: pass
    human_judgment: false
  - deliverable: "Phase gate on the gap round (backend 2179 passed, UI 1873 passed, build exit 0)"
    verification:
      - kind: command
        ref: "the 85-23 backend pytest list on 127.0.0.1:27998; npx vitest run src/__tests__; npm run build"
        status: pass
    human_judgment: false
status: complete
---

# Phase 85 Plan 29: writing from a gap needs a Help desk article, tests that hold over time, and the gap-round gate (WR-203, WR-301, WR-302, WR-303) Summary

A knowledge gap now leaves the list only when an article the desk can cite answers it, the desk tests no longer depend on the calendar, the migration count or a live database, and the whole Phase 85 gate is green on the code of the gap round.

## Accomplishments

- **WR-203 (tracer, `9cbe72e1b`).** `write_article` answers 422 with `API_DETAIL["gap_article_not_helpdesk"]` when `gapGroupId` is set and `helpdesk` is not true. The refusal sits after `_validated` and before `gaps.find_group` and the claim (line 288 against line 293), so nothing is saved and every member of the group stays open and listed. Helpdesk true with a group still marks the group written (the existing test); helpdesk false without a group still saves an ordinary article with `helpdesk False`. RED observed: the new test got 200 instead of 422 before the code.
- **WR-301, WR-302, WR-303 (`57325f0e7`).** `desk_indexes_without_ttl(db)` builds the desk indexes and drops `finished_ttl` and `created_ttl`; the worker world, hand-off world and knowledge-gap kb fixtures use it. A new worker test pins that after the fixture and one `run_once` the jobs collection has `one_attempt_per_ticket` and `state_created` but no `finished_ttl`, and the gaps collection has no `created_ttl`. The 90-day list test asserts the 100-day-old row N2 is still stored after the list call. The `max(found) == "032"` assertion is gone. The `--sets` test deletes `MONGODB_URL`, `MONGO_URI` and `MONGODB_URI`, replaces `motor.motor_asyncio.AsyncIOMotorClient` and the loaded script's `open_database` with raising recorders, and asserts exit 0 and both recorders empty; the benign `--sets` run asserts `generates == reaching_the_model(script)`, computed from the script's own `_rule_reason`, `_cleaned_question`, `starter_docs` and `retrieval` over `injection_set.jsonl` (no number typed into the test, and at least 1).
- **Bookkeeping (`523fe3f6f`).** 85-REVIEW-DISPOSITION.md: WR-203 fixed (9cbe72e1b), WR-301, WR-302 and WR-303 fixed (57325f0e7); `grep -c "disposition: fixed"` = 11, `disposition: open` = 17, YAML `open: 17`. 85-VALIDATION.md has rows 85-24 to 85-29 and a gap-round line in the Validation Audit; `nyquist_compliant: true` and `status: validated` unchanged. 85-SECURITY.md and 85-VERIFICATION.md are untouched.

## Task Commits

1. Task 1 (tracer): `9cbe72e1b` fix - the 422 rule, its sentence and the behavior test
2. Task 2: `57325f0e7` test - fixture index helper, index-set test, 90-day assertion, WR-302, WR-303, lifecycle clock fix, deferred item resolved
3. Task 3: `523fe3f6f` docs - disposition and VALIDATION rows (after the gate)

## Verification

- Task 1 command (`test_service_desk_knowledge_gaps.py`, `test_service_desk_knowledge.py`, `test_autonomous_ops_copy.py`): 71 passed, 0 failed, 0 skipped.
- Task 2 command plus the lifecycle file: 317 passed, 0 failed, 0 skipped.
- **Task 3 backend gate** (the 85-23 list, private mongod 127.0.0.1:27998, `TICKET_ATTACHMENT_DIR` and `FILE_SHARE_DIR` temp dirs): `2179 passed in 971.92s (0:16:11)`, 0 failed, 0 errors, 0 skipped (log: scratchpad `85-29/gate.log`).
- **Vitest** `npx vitest run src/__tests__`: `Test Files 117 passed (117)`, `Tests 1873 passed (1873)`.
- **Build** `npm run build`: exit 0 (writes `dist-new/`, nothing copied to /var/www).
- After the gate, a read-only listing of the live mongod on 27017 shows no `omni_test_*` database (`[]`): nothing in this plan's runs reached the live database.

## Deviations from Plan

**1. [Rule 1 - Bug, added scope from the orchestrator] A test that failed only because the real clock passed its pinned date**
- **Found during:** Task 2 (recorded in deferred-items.md by 85-25).
- **Issue:** `test_service_desk_lifecycle.py::test_this_fixed_it_resolves_the_ticket_and_only_this_does` confirms the ticket at the fixed `NOW = 2026-11-09 14:30 UTC`, but the answer run stamps `hold_started_at` from the real clock, so `total_hold_duration` was negative (-8756.9 s observed as RED).
- **Fix:** test-only. After `_posted`, the test sets the ticket's `hold_started_at` to `NOW - 1 hour`; the assertion `total_hold_duration >= 0` is unchanged. GREEN: all 32 lifecycle tests pass. Production code untouched. deferred-items.md marks the item resolved.
- **Files modified:** backend/tests/test_service_desk_lifecycle.py (488 lines), .planning/phases/85-first-line-service-desk/deferred-items.md
- **Commit:** 57325f0e7

**2. [Note] WR-301 RED was not shown separately.** The index-set test and the TTL-free fixtures landed in one commit; the new index test would fail against the old `store.ensure_indexes` fixtures by construction (it asserts the TTL indexes are absent), but I did not run it against the old fixtures. No other clock-dependent test failed in the gate.

**Total deviations:** 1 auto-fixed (Rule 1, orchestrator-added), 1 note. **Impact:** none on production behavior.

## Known Stubs

None.

## Threat Flags

None. T-85-102 (422 before the claim, tested), T-85-103 (client factory and `open_database` replaced by raising recorders, `MONGODB_URI` deleted, exit 0 asserted) and T-85-104 (TTL-free fixtures, 100-day row asserted present, migration test keeps the TTL coverage) are mitigated. Residual: A-85-G17 - the Write article dialog sends its Help desk toggle with `gapGroupId`; unticking it now shows the server's 422 sentence (dialog unchanged, out of scope).

## Self-Check: PASSED

- Files exist: backend/tests/service_desk_support.py (`async def desk_indexes_without_ttl`), backend/service_desk/messages.py and backend/knowledge_helpdesk_endpoints.py (`gap_article_not_helpdesk`).
- Commits 9cbe72e1b, 57325f0e7 and 523fe3f6f are on the branch `npx`.
- `grep -n 'max(found)' backend/tests/test_service_desk_worker.py` prints nothing; the three fixtures call `desk_indexes_without_ttl`; the `--sets` test deletes `MONGODB_URI` and patches `motor.motor_asyncio.AsyncIOMotorClient`.
- 85-SECURITY.md and 85-VERIFICATION.md unchanged (`git diff --stat` empty). The user's WIP files were never staged.
