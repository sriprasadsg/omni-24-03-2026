---
phase: 82-platform-self-healing-scheduled-retention
plan: 03
subsystem: infra
tags: [watchdog, stdlib, systemd, restart-budget, incidents, polkit]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "plan 82-02 watchdog package (seams run/http/now, run_once, state, spool, resolve_stop); plan 82-06 polkit rule (restart/start/reset-failed of mongod, omni-backend, nginx)"
provides:
  - "restart.decide: the D-07 restart budget (waits 60/120/240 s, 3 per 30 min), one gave_up per episode, D-08 re-arm after 3,600 s healthy"
  - "MongoDB before the backend (D-09) including the demo-mode backend; stop pause (D-11); Ollama only where expected"
  - "incidents.py: the state[incidents] store that 82-04 and 82-05 use (shape below)"
  - "One shared polling allowance per run (POLL_BUDGET = 30 s) so a run with several restarts fits TimeoutStartSec=45"
affects: [82-04 cert and disk warnings (incident store), 82-05 paging (svc incidents), 82-08 backend rendering of restart events]

actuals:
  tokens: 14000
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Restart decision is one function over the whole state dict with every effect injected (run, clock, sleep, recheck, persist); tests drive a fake host (World/Rig) on a fake clock"
    - "A restart is recorded in state and persisted before polling, so a run killed while polling cannot repeat it"
    - "gave_up is a sticky flag (gaveUp), not a count read from the 30-minute window"

key-files:
  created:
    - deploy/omni-watchdog/omni_watchdog/incidents.py
    - backend/tests/_watchdog_restart_world.py
    - backend/tests/test_watchdog_restart_order.py
  modified:
    - deploy/omni-watchdog/omni_watchdog/restart.py
    - deploy/omni-watchdog/omni_watchdog/checks.py
    - deploy/omni-watchdog/omni_watchdog/run.py
    - deploy/omni-watchdog/omni_watchdog/services.py
    - backend/tests/test_watchdog_restart.py
    - backend/tests/test_watchdog_checks.py
    - backend/tests/test_watchdog_sync.py

key-decisions:
  - "gave_up is sticky: state carries gaveUp, and a given-up service is not restarted even after its restarts age out of the 30-minute window (otherwise the window would give the budget back at about 31 minutes, against PROH-82-09)"
  - "Incident kinds for svc:<id>: service_gave_up (budget used up) and service_down (down while restarts are paused by a stop); a pause incident is cleared when the service is healthy again, a gave-up incident only at re-arm"
  - "The restart-event seconds value is the poll time at which health was seen (2 s granularity), so a service that comes back after 3 s is reported as 4 s"
  - "Backend waitingOn mongod is set from this run's raw mongod check; a mongod restarted and healthy inside the same run still blocks the backend until the next run (the plan's 'only mongod.service is restarted in that run')"

patterns-established:
  - "Incident store: one dict per key in state[incidents], opened once, cleared with clearedAt, never deleted by the producer"

requirements-completed: [HEAL-01, HEAL-02]

coverage:
  - id: D1
    description: "A service down on two checks is restarted with exactly [systemctl, restart, --no-block, <unit>] from UNITS (reset-failed first only when is-active said failed), polled every 2 s for up to 20 s, and reported as a restart event with ok and seconds"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_mongod_failing_two_checks_is_restarted_and_reported_healthy_in_the_sync_body"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_a_unit_that_answers_failed_is_reset_before_it_is_restarted"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_restart_unit_refuses_a_unit_outside_the_fixed_list"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-07 / A1 timeline: restarts at +60, +120, +240 s, gave_up at +480 s with exactly one gave_up event and one open critical svc incident; no restart after that, including after the window ages out; never more than 3 restarts in any 30 minutes (seeded property test, 3 seeds x 200 runs)"
    requirement: HEAL-02
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_the_a1_timeline_restarts_at_60_120_240_and_gives_up_at_480"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_gave_up_is_reported_once_and_no_restart_follows_even_after_the_window_ages_out"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_property_at_most_three_restarts_in_any_window_and_none_between_gave_up_and_rearm"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-08 re-arm: budget returns at exactly 3,600 s healthy (not at 3,599 s) with one budget_rearmed event and the svc incident cleared; a gave-up service that is down again stays gave up and the hour starts over"
    requirement: HEAL-02
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_an_hour_of_health_returns_the_budget_exactly_at_3600_seconds_not_at_3599"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_a_gave_up_service_that_is_down_again_stays_gave_up_and_the_hour_starts_over"
        status: pass
    human_judgment: false
  - id: D4
    description: "A restart refused by polkit (non-zero exit) is a restart event ok false with the error capped at 300 characters, counts toward the budget and ends in gave_up and one incident"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_a_refused_restart_is_a_failed_attempt_that_ends_in_gave_up_and_one_incident"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart.py#test_the_error_text_of_a_refusal_is_capped_at_300_characters"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-09: with mongod and the backend down in one run only mongod.service is restarted, the backend carries waitingOn mongod and spends no budget; the next run restarts a demo-mode backend under its own budget; nginx is restarted"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_mongod_and_backend_down_in_one_run_only_mongod_is_restarted_and_the_backend_waits"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_next_run_a_backend_stuck_in_demo_mode_is_restarted_under_its_own_budget"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_nginx_down_twice_is_restarted_with_mongod_and_backend_healthy"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-11: with a stop from the STOP file, the cached database value or the database value passed to decide, no restart is issued, one restart_skipped per down episode, counters untouched, checks, events and the svc incident continue; clearing the stop restarts normally"
    requirement: HEAL-02
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_a_stop_file_pauses_restarts_but_not_checks_events_or_the_incident"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_decide_issues_no_restart_for_any_stop_source_and_keeps_the_counters"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_when_the_stop_is_cleared_a_service_that_is_still_down_is_restarted_normally"
        status: pass
    human_judgment: false
  - id: D7
    description: "PROH-82-01: Ollama is never started where it is expected off; restarted under the same budget where expected on; restart.py names no ollama.service literal"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_ollama_expected_off_is_never_started_or_restarted"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_ollama_expected_on_and_down_twice_is_restarted_under_the_same_budget"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_restart_source_has_no_hard_coded_ollama_unit"
        status: pass
    human_judgment: false
  - id: D8
    description: "Orchestrator decision: mongod, nginx and an expected Ollama all restart in one run, total polling stays within POLL_BUDGET (30 s), every restart event is returned, the unconfirmed one is judged on the next run"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_three_services_restarted_in_one_run_share_the_polling_allowance_and_all_events_are_returned"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_restart_order.py#test_a_restart_the_allowance_could_not_cover_is_judged_on_the_next_run"
        status: pass
    human_judgment: false
  - id: D9
    description: "On a real server: stop mongod and the backend, MongoDB is restarted first and the backend after it within about 2 minutes, and mongod still shows GLIBC_TUNABLES after the watchdog's restart; polkit actually allows the verbs the code issues"
    verification: []
    human_judgment: true
    rationale: "Needs the watchdog, polkit rule and drop-ins installed on the server, which is the operator's step (INSTALL.md); this plan and the executor install nothing and restart nothing."

duration: 40min
completed: 2026-10-30
status: complete
plan_head_before: fe0240b86730b34715028483e0e17d46accfaa1b
plan_head_after: 889faa6c16e3accbc79fcbb2d6dad49137adcdd4
commits: 4
---

# Phase 82 Plan 03: Restart budget, ordering, stop pause and incident store Summary

**The watchdog restarts failed services (mongod, backend, nginx; Ollama only where expected) through systemctl with a 3-per-30-minute budget it cannot exceed, gives up once with one critical incident, gets the budget back after an hour healthy, restarts MongoDB before the backend, honours the stop for restarts only, and fits all of it inside the 45 s unit timeout.**

## Performance

- **Duration:** about 40 min for this continuation (Task 1 was built and committed by an earlier executor stopped by a usage limit)
- **Completed:** 2026-10-30
- **Tasks:** 3 (Task 1 by the earlier executor, Tasks 2 and 3 here)
- **Files:** 10 code and test files (3 new)
- **commits: 4** measured from the ledger base `fe0240b86`: `d246a1eca` (Task 1), the orchestrator's resume note `20817ae2e`, `07b72dc30` (Task 2), `889faa6c1` (Task 3). Three are task commits.

## Accomplishments

- `restart.py` `decide` runs after `services.observe`: wait, give up, pause for a stop, or restart. Constants `WAITS = (60, 120, 240)`, `BUDGET = 3`, `WINDOW = 1800`, `REARM_AFTER = 3600`, `POLL_EVERY = 2`, `POLL_FOR = 20`, `POLL_BUDGET = 30`.
- `incidents.py`: `open_incident`, `clear_incident`, `open_incidents`, `is_open`.
- 44 tests in `test_watchdog_restart.py` and `test_watchdog_restart_order.py`; with the other watchdog suites 95 pass (115 passed, 2 skipped including `test_watchdog_artifacts.py`).

### Exact incident dict shape (82-04 and 82-05 consume it)

`state["incidents"]` is `{key: incident}`. All times are epoch seconds (float). A real one, as saved after a gave-up (asserted verbatim by `test_gave_up_opens_exactly_one_critical_incident_with_the_documented_shape`):

```json
{"key": "svc:mongod", "severity": "critical", "kind": "service_gave_up", "target": "mongod",
 "params": {"restarts": 3}, "openedAt": 1800000480.0, "pageKey": null, "sent": false, "clearedAt": null}
```

- `open_incident(state, key, severity, kind, target, params, now)` returns the new dict, or `None` if the key is already open (no second open). Severity must be `info|warning|critical` (else `ValueError`). Opening a cleared key replaces it with a fresh incident.
- `clear_incident(state, key, now)` sets `clearedAt` and returns the dict, or `None` if it was not open. Cleared incidents stay in the store so the pager (82-05) can send the resolve; the producer never deletes them.
- `open_incidents(state)` lists open ones, oldest `openedAt` first.
- `pageKey` and `sent` are written only by the pager (82-05). Persisting the state before any page is sent is the caller's job: `decide` calls its `persist` callback right after opening an incident.
- Kinds this plan writes, both for key `svc:<id>`, severity `critical`: `service_gave_up` (params `{"restarts": 3}`) and `service_down` (params `{}`, service down while restarts are paused by a stop). If a `service_down` incident is open when the budget runs out, it is upgraded in place to `service_gave_up` (no second page).
- The service entry also gets `pagedAt` (epoch) when the svc incident is first opened, and `None` again at re-arm.

### Observed timeline (A1, from `TIMELINE` in the test; time in seconds after the first run, MongoDB never comes back)

| t | restarts issued | mongod state | events |
|---|-----------------|--------------|--------|
| 0 | 0 | checking | none |
| 60 | 1 | restarting | service_down, restart (attempt 1) |
| 120 | 1 | restarting | restart (attempt 2) |
| 180 | 0 | restarting | none |
| 240 | 1 | restarting | restart (attempt 3) |
| 300, 360, 420 | 0 | restarting | none |
| 480 | 0 | gave_up | gave_up (one, with incident svc:mongod) |
| 540 ... 5400 | 0 | gave_up | none (also at 1860 and later, after the restarts left the 30-minute window) |

Re-arm (service healthy from t = 540): `budgetReturnsAt = 540 + 3600`; at 540 + 3599 no `budget_rearmed`, gaveUp still true, incident open; at 540 + 3600 exactly one `budget_rearmed`, incident `clearedAt` set, restarts empty; the next failure is attempt 1 again. A gave-up service that fails again before the hour is over stays `gave_up` (after the one debounce run `checking`) and the hour starts over from its new recovery.

## Task Commits

1. **Task 1: Tracer - mongod fails two checks, restarted through systemctl, reported healthy** - `d246a1eca` (feat, earlier executor, not redone)
2. **Task 2: Restart budget, window, gave up once, re-arm, refused restarts** - `07b72dc30` (feat)
3. **Task 3: MongoDB before the backend, demo mode, stop pause, Ollama registry, polling allowance** - `889faa6c1` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## Deviations from Plan

### From Task 1 (earlier executor, kept)

- `restart.decide` has the signature `decide(state, health, stop, now, config, *, run, clock, sleep, recheck, persist=None)`: it takes the whole state dict, not `service_states`, because the incident store lives in state. `persist` saves the state after a restart is recorded and before polling, so a run killed during the poll cannot repeat the restart.
- `checks.py` gained `check_one(sid, run, http, config)`, shared by `check_all` and the restart poll (not in the plan's `files_modified`).
- `run.real_run` appends stderr on a non-zero exit, so a polkit refusal is readable.
- `test_watchdog_checks.py` and `test_watchdog_sync.py` gained an autouse fixture that stubs `restart.decide`, so those suites stay about checks and sync (not in `files_modified`).
- `services.observe` carries every field except `state`, `failedChecks`, `detail` and `since`.

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality, safety] One shared polling allowance per run (orchestrator decision)**
- **Found during:** Task 3 (raised by the orchestrator; 82-RESEARCH considered a single restart)
- **Issue:** each restart polled up to 20 s and `decide` returns its events only at the end, so a run restarting two or three services could be killed by `TimeoutStartSec=45` before any restart event reached the spool; the saved state would remember the restarts but the events would be lost.
- **Fix:** `POLL_BUDGET = 30`. Each restart may poll for `min(POLL_FOR, POLL_BUDGET - elapsed since decide began)` seconds (elapsed includes the restart commands). A single service still gets its exact 20 s. With less than one poll step left, the restart is recorded as issued and reported with `ok: false` and error `NOT_CONFIRMED` ("Restart issued; not yet confirmed. Checked again on the next run."), counted in the budget and judged by the next run's checks (recovered then, or the next wait applies). The shorter allowance also shows in the error text ("Not healthy 10 s after the restart.").
- **Files modified:** `deploy/omni-watchdog/omni_watchdog/restart.py`, `backend/tests/test_watchdog_restart_order.py`
- **Verification:** `test_three_services_restarted_in_one_run_share_the_polling_allowance_and_all_events_are_returned` (mongod 20 s, nginx 10 s, expected Ollama none; elapsed between 20 and 30 s; three restart events in the sync body) and `test_a_restart_the_allowance_could_not_cover_is_judged_on_the_next_run`.
- **Committed in:** `889faa6c1`

**2. [Rule 1 - Bug] The plan's sliding window alone would have returned the budget to a given-up service**
- **Found during:** Task 2
- **Issue:** with the budget counted only from restarts in the last 30 minutes, a service still down would drop below 3 restarts at about 31 minutes and be restarted again, contradicting the truth "no restart is ever issued after that while the service stays down" (PROH-82-09).
- **Fix:** `gaveUp` is a sticky flag on the service entry, cleared only by the D-08 re-arm.
- **Files modified:** `restart.py`. **Verification:** `test_gave_up_is_reported_once_and_no_restart_follows_even_after_the_window_ages_out` (runs at 1860, 1920, 2400, 3000, 3600, 5400). **Committed in:** `07b72dc30`

**3. [Rule 3 - Blocking] CLAUDE.md 500-line limit forced a test split**
- **Found during:** Task 3
- **Issue:** one `test_watchdog_restart.py` for all three tasks reached 728 lines.
- **Fix:** the fake host (`World`, `Rig`, `rig` fixture) moved to `backend/tests/_watchdog_restart_world.py` (137 lines); Task 3 tests are in `backend/tests/test_watchdog_restart_order.py` (266 lines); `test_watchdog_restart.py` keeps Tasks 1 and 2 plus the incident store tests (349 lines). The plan's task-3 acceptance ("test_watchdog_restart.py contains tests for ...") is met by the pair of files. Run both: `pytest backend/tests/test_watchdog_restart.py backend/tests/test_watchdog_restart_order.py`.

### Notes on plan text that did not match reality

- **82-06 polkit rule:** it allows `restart`, `start` and `reset-failed` of `mongod.service`, `omni-backend.service` and `nginx.service` only. `ollama.service` is NOT allowed (INSTALL.md gives the one-line addition). The code only issues `is-active` (no polkit needed), `reset-failed` and `restart --no-block`, all inside the allowed verbs. On a server with `ollama_expected = true` but without the rule addition, Ollama's restart is refused, which ends in three failed attempts, one `gave_up` and one page (tested by `test_ollama_expected_on_without_a_polkit_grant_ends_in_one_gave_up`). I did not edit the rule.
- **"or one with restarts in its window" (D-08 truth):** unreachable for a service that is not given up, because the 30-minute window is shorter than the 3,600 s re-arm: such restarts age out on their own (`test_restarts_age_out_of_the_window_without_a_gave_up`). Only a given-up service emits `budget_rearmed`, and `budgetReturnsAt` is reported only for it.
- **Stop "database" source:** `run_once` resolves the stop before the sync from the STOP file or the value cached by the last good sync, so inside a real run the source reads `file`, `cache` or `none`; `database` is only produced by the post-sync refresh. The database source is therefore pinned by calling `decide` directly with `{"effective": True, "source": "database"}`.
- `run.py` and `services.py` needed no change in Tasks 2 and 3 (the wiring and the states were done in Task 1).

**Total deviations:** 1 safety addition (orchestrator decision), 1 bug (sticky gave-up), 1 blocking (file size), plus the Task 1 notes. **Impact:** no scope change; HEAL-01 and HEAL-02 behaviours are as specified.

## Verification

`backend/venv/bin/python -m pytest backend/tests/test_watchdog_restart.py backend/tests/test_watchdog_restart_order.py backend/tests/test_watchdog_checks.py backend/tests/test_watchdog_sync.py -q -p no:cacheprovider`: 95 passed. Adding `test_watchdog_artifacts.py`: 115 passed, 2 skipped. Acceptance greps: `"--no-block"` 1, `WAITS = (60, 120, 240)` 1, `def open_incident` 1, no `ollama.service` literal in `restart.py`. Every test runs on fakes: no `systemctl restart` was ever executed on this machine, nothing was installed, no MongoDB was touched.

## Known Stubs

None.

## Threat Flags

None. The restart path adds no network endpoint or file access; it uses only the existing `run` seam with unit names from `UNITS`.

## Issues Encountered

- Plan 82-03 was interrupted by a usage limit after Task 1; resumed from the orchestrator's note.
- HEAL-01 and HEAL-02 are left unchecked in REQUIREMENTS.md on purpose: sibling plans (82-05 and others) declare them too and have no SUMMARY yet (`requirements.ready-ids` returned 0 ready). A premature `mark-complete` was reverted before the metadata commit.
- An accidental plain `git reset` (index only, nothing staged at the time) was run once before staging Task 3; no working-tree change was affected.

## Next Phase Readiness

Ready for 82-04 (certificate and disk warnings use `incidents.open_incident`/`clear_incident`) and 82-05 (pages `svc:<id>` incidents; the matching resolve is sent when the incident is cleared at re-arm or, for `service_down`, at recovery). The end-of-phase operator step in Task 3's `<human-check>` (stop mongod and the backend on the server after installing per INSTALL.md) is still outstanding.

## Self-Check: PASSED

Files exist (`incidents.py`, `restart.py`, `_watchdog_restart_world.py`, `test_watchdog_restart.py`, `test_watchdog_restart_order.py`); commits `d246a1eca`, `07b72dc30`, `889faa6c1` are ancestors of HEAD.
