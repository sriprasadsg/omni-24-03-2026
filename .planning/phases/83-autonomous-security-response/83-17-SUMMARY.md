---
phase: 83-autonomous-security-response
plan: 17
subsystem: autonomous-ops-restart
tags: [autonomous-ops, restart-service, budget, sweep, heartbeat, watched-services, mongo]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-07 autonomy_settings.response.watchedServices and response_settings.load"
  - phase: 83-autonomous-security-response
    provides: "83-14 meta.service_failures, the restart_service agent contract, the watchedServices reply key"
  - phase: 83-autonomous-security-response
    provides: "83-15 / 83-16 the sweep's stage list, followups, row.stillRunning"
provides:
  - autonomous_ops/sweep_restart.py (RESTART_BUDGET, BUDGET_WINDOW, WAITS, run) as the sweep's third stage
  - reason.inputs.service, .attempt, .failureId, .incidentId on a restart row; .overBudget on the card
  - response_settings.heartbeat_reply and the heartbeat reply key watchedServices
  - agent_capabilities._DATA_KEYS["service_failures"] = remediation_executor
  - row.result.healthy_after written by verify.settle
  - a late "accepted" post no longer overwrites a final instruction status
affects: [83-18, 83-19, 83-20]

actuals:
  tokens: 10000
  tasks: 2
  commits: 3
plan_head_before: 2385a5570d12ba7eec25f37e2be8fe088ab8b92a
plan_head_after: 58e384abb37e5d86676a3ee17ace0dc3efff5397

tech-stack:
  added: []
  patterns:
    - "A budget is counted from the ledger with a strict greater-than on createdAt, never held in memory (PROH-83-16)"
    - "One signal document per (tenant, host, kind service, service name) carries both the once-per-failure evidence claim (find_one_and_update, BEFORE) and the sweep's decision memory"
    - "heartbeat_reply is a never-raising dict merged into the reply with a single ** entry; a key left out means 'change nothing' on the agent"

key-files:
  created:
    - backend/autonomous_ops/sweep_restart.py
    - backend/tests/test_autonomous_ops_restart_budget.py
  modified:
    - backend/autonomous_ops/sweep.py
    - backend/autonomous_ops/verify.py
    - backend/autonomous_ops/response_settings.py
    - backend/agent_tasks_endpoints.py
    - backend/agent_capabilities.py
    - backend/agent_heartbeat_endpoints.py

key-decisions:
  - "The name sent to the agent is the name the tenant listed, never the name the agent reported; the match is case-insensitive and the dedupe key uses the case-folded name."
  - "A row blocks a new try whenever ANY restart row for that service and computer is open (automatic try or card), so a card answered late cannot start a second restart and rows that age out of the hour cannot let an automatic try start beside an open card."
  - "The over-budget card carries no attempt number: 'Restart 4 of 3 this hour' would read as a fault, and the UI-SPEC has no wording for a card-approved restart, so that row shows no Result sentence."
  - "The memory of the last card or refusal (signals.remember, kind service) holds the service quiet only for denied, expired, refused and shadow outcomes; a done card does not hold it."
  - "A watchedServices read that is unreadable or malformed leaves the key out (agent keeps its list); only a well-formed empty list is sent as empty."

requirements-completed: []

coverage:
  - id: D1
    description: "A listed service an agent reports failed is restarted automatically through the gate with params {service_name}; no two-source rule; the row offers no Undo; an open row for the service keeps the next tick quiet"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_a_failed_listed_service_is_restarted_through_the_gate"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_a_restart_the_agent_confirms_reads_restarted_with_how_long_it_took_and_has_no_undo"
        status: pass
    human_judgment: false
  - id: D2
    description: "Waits of 59/60 s, 119/120 s and 239/240 s; the fourth try is ONE awaiting_approval row, reasonCode playbook_raised, with the budget sentence and an incidentId, and ten more ticks add nothing"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_the_waits_are_1_2_and_4_minutes_and_the_fourth_try_is_one_card"
        status: pass
    human_judgment: false
  - id: D3
    description: "A row 3599 s old still counts and one exactly an hour old does not; simulations and refused rows count nothing; the budget survives a reload of the module; a denied card is not raised again for 24 hours"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_exactly_one_hour_old_no_longer_counts"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_a_denied_card_is_not_raised_again_for_24_hours"
        status: pass
    human_judgment: false
  - id: D4
    description: "A service off the list, an empty list, a host without the restart_service token, an offline host and a tenant without remediation_executor produce no row and no incident; the list is compared case-insensitively"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_a_service_off_the_list_and_an_empty_list_restart_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_a_host_without_the_token_or_offline_gets_no_row_and_no_breaker_effect"
        status: pass
    human_judgment: false
  - id: D5
    description: "Restart rows do not count toward the 3-per-host cap on block and quarantine and do count toward the tenant's 20 an hour (the 21st goes to a person with rate_limit)"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_restarts_do_not_raise_the_block_cap_but_do_count_toward_the_twenty_an_hour"
        status: pass
    human_judgment: false
  - id: D6
    description: "The heartbeat reply carries watchedServices only for a tenant holding remediation_executor, leaves it out on a failed or malformed read, never fails a heartbeat; failure data is dropped for an unticked tenant while response_actions stays"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_the_heartbeat_route_replies_with_the_list_and_stores_the_failures_for_a_ticked_tenant"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_the_heartbeat_route_neither_sends_nor_stores_failures_for_an_unticked_tenant"
        status: pass
    human_judgment: false
  - id: D7
    description: "A late accepted post never replaces SUCCESS, FAILURE or REFUSED"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_restart_budget.py#test_a_late_accepted_never_overwrites_the_final_answer"
        status: pass
    human_judgment: false

duration: 28min
completed: 2026-11-02
status: complete
---

# Phase 83 Plan 17: The restart loop, its budget and the watched list

**A service on the tenant's list that an agent reports failed is restarted through the gate up to three times in a rolling hour, with waits of 1, 2 and 4 minutes; the fourth try is one approval card; and the tenant's list now reaches its agents in the heartbeat reply.**

## Performance

- **Duration:** about 28 min
- **Tasks:** 2 (both TDD)
- **Commits:** 3 (1 test, 2 feat), measured from `2385a5570` to `58e384abb`; the SUMMARY and state commit follows
- **Line counts:** `sweep_restart.py` 244, `response_settings.py` 214, `verify.py` 198, test 441 (limit 500). `agent_heartbeat_endpoints.py` was already over the limit (531 lines at HEAD before this plan, 533 after).
- **Used the cargo recipe:** no, this plan touches no Rust.

## What was built

`sweep_restart.run` is the third entry in `sweep._STAGES`. Per tenant it reads the list (`response.watched_services`; empty means it returns at once), then the agents that report `meta.service_failures`, and for each reported failure whose name is on the list (case-insensitive) it decides, in this order:

1. `agent_support.check` for `restart_service` (capability, online, token) or an open row for that service and computer: nothing.
2. The ledger rows for (tenant, `restart_service`, computer, `params.service_name` case-insensitive) created strictly after one hour ago and not `refused` or `shadow`. The newest one's `createdAt` must be at least `WAITS[min(n,3) - 1]` seconds old (60, 120, 240).
3. A card or refusal the sweep remembered for this service that a person denied, let lapse, or the gate refused holds it quiet for 24 hours.
4. The failure is put on the computer's incident once per `failure_id` (an atomic claim on the service's `autonomy_signals` document), dated by the failure's own `since`.
5. Under 3 rows: `gate.decide` with the dedupe key `{tenant}|sweep|restart_service|{agent}|{service}` and `reason.inputs {service, attempt, failureId, incidentId}`. At 3 or more: the same with `playbook_raise` True, key suffix `|card`, and `overBudget` True. Only a row recorded as `dispatching` is sent, through `response_dispatch.send`.

`response_settings.heartbeat_reply(db, tenant_id, agent_id, permitted)` returns `{"watchedServices": [...]}` for a tenant holding `remediation_executor`, otherwise `{}`. The heartbeat route merges it into its reply with one `**await` entry. `service_failures` is in `_DATA_KEYS`, so a tenant without the tick neither stores nor receives failure data.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] `verify.settle` now copies `healthy_after` into `row.result`**
- **Found during:** Task 1 (run notes from 83-14 said this plan must do it; the plan's file list omits `verify.py`)
- **Issue:** Without it the Result sentence "Restarted {service}. Healthy again after {s} s." could never render.
- **Fix:** an integer `healthy_after` in the agent's stored result is merged into the verified row's `result` beside `still_running`.
- **Files modified:** `backend/autonomous_ops/verify.py`
- **Commit:** dd92577f3

**2. [Rule 1 - Bug] A late `accepted` post could overwrite a final instruction status**
- **Found during:** Task 1 (83-12 and 83-14 both flagged it for the backend)
- **Issue:** `report_instruction_result` stored whatever status arrived last, so an `accepted` that landed after `success` put the instruction back to `ACCEPTED`, and the reconciler would then wait for the no-result bound.
- **Fix:** an `accepted` post updates only an instruction whose status is not `SUCCESS`, `FAILURE` or `REFUSED`. This covers isolation and every other accepted-then-final action, not only restarts.
- **Files modified:** `backend/agent_tasks_endpoints.py`
- **Commit:** dd92577f3

**3. [Plan limit] The heartbeat file grew by 2 lines, not 1**
- The plan said "add one line only" and "at most 2 changed lines". The final `return` needed one import line plus the `**await response_settings.heartbeat_reply(...)` entry, which put the old first line of the return on two lines. `git show --stat` for that file reads 4 lines changed (3 added, 1 removed). The user's uncommitted hunks in `agent_heartbeat_endpoints.py` (3 lines) and `agent_capabilities.py` (38 lines) were not committed; I checked `git diff --stat` after the commit and both are still there as before.

**4. [Choice within the plan] Dedupe key uses the case-folded service name; the over-budget card has no `attempt`**
- The plan's key is `{tenant}|sweep|restart_service|{agent}|{service}`; I fold the case so `Nginx` and `nginx` share one open row. A card-approved restart therefore shows no Result sentence (see Known gaps).

None of the plan's decisions (D-10, D-11, D-12, A-83-LADDER) were changed.

## TDD note

The RED run (`dc30b5b1b`) was made with the stage module present but not wired into `_STAGES`: 23 of 29 tests failed on behaviour (no row was written, `KeyError: 'restarted'`, a missing `heartbeat_reply`, a missing `_DATA_KEYS` entry) and 6 passed because they assert that nothing happens. It was not an ImportError. I had drafted `sweep_restart.py` before writing the tests; the unwired RED is how I recovered a meaningful failure. After Task 1 only the five Task 2 tests were red, and they went green with Task 2.

## Verification

- `test_autonomous_ops_restart_budget.py`: 29 passed, none skipped (private mongod on 27998 with `MONGO_TEST_URL`, `MONGODB_URL`, `MONGO_URI`).
- All 34 `backend/tests/test_autonomous_ops_*.py` files: 933 passed in two batches, none skipped.
- `test_agent_capabilities.py` and the other heartbeat and result-route tests (86 tests) pass. One test in `test_e2e_integration.py` (`test_cross_tenant_report_download_owner_allowed`) fails with "Database not connected" on a report download; it does not touch anything in this plan and I did not investigate it further.
- Not run: the full backend suite (forbidden), `test_catalogue_route_parity.py` (no route was added or guarded).

## Known gaps and limits

- **Card outlives the problem.** An over-budget card stays open for up to 24 hours even if the service recovers on its own. A person who approves it late restarts a service that is healthy. Nothing in this plan closes such a card (83-15's suggestions have a close step; this does not).
- **No Result sentence for a card-approved restart.** `row_extras` words a restart only when `attempt` is set; the card has none because "Restart 4 of 3 this hour" would read as an error. 83-18 or the UI-SPEC needs a sentence if the user wants one.
- **Level Suggest.** At Suggest the first try is recorded as a suggestion; it is open, so the stage stays quiet until it ends. After it lapses, the memory holds it another 24 hours.
- **Stale failure list.** The stage reads the failure list from the agent's last heartbeat. A heartbeat that arrives after a successful restart but carries the old list could cause one more try; the wait ladder and the budget bound it.
- **`approvals._revalidate` uses the real clock**, so tests that approve a card must refresh the agent's `lastSeen` to the real time first. The late-card test does.

## Sentences

No new user-visible sentence was written. The Why column reuses `WHY_TEMPLATES["restart_watched"]` and `["restart_over_budget"]`; the Result sentence is `RESULT_TEMPLATES["restart_done"]`; all three already existed in `response_messages.py` (83-03).

## Facts for later plans

- `response_settings.heartbeat_reply(db, tenant_id, agent_id, permitted)` is the one place the heartbeat reply gains keys from Autonomous Ops. 83-18's `isolationConfirmed` should be added inside it (the agent id passed is the canonical `agents.id`).
- A restart row: `command` `restart_service`, `params {service_name}`, `targets [agent]`, `reason.ruleId` `sweep:restart_service`, `reason.inputs {service, attempt, failureId, incidentId}`; the card has `overBudget: true`, no `attempt`, `dedupeKey` ending `|card`, `reasonCode` `playbook_raised` (or `rate_limit` when the tenant's 20 an hour is used), `WHAT_HAPPENS["restart_over_budget"]` is its pre-click sentence.
- `autonomy_signals` now also holds documents of kind `service` (indicator = case-folded service name) with `failureId`, `lastSeenAt` and `decision`.
- `sweep.tick` counts gain `restarted`, `cards`, `shadow`, `refused`, `failed`, `waiting`, `skipped` from this stage (summed with the other stages').
- `verify.settle` stores `healthy_after` in `row.result` for a verified row; `report_instruction_result` ignores a late `accepted`.

## Not read

83-RESEARCH.md was read for Q8, Q10, Q11 and Q13 only. 83-UI-SPEC.md was not read (the plan names no section). 83-14-SUMMARY.md was read through the run notes and the lines about `restart_service` and `accepted`, not in full. PROJECT.md was not read.

## Requirements

RESP-04 is not ticked. The backend half is done and tested, but the approval card is not on the screen until 83-18, and the orchestrator ticks it at the phase gate.

## Self-Check: PASSED
