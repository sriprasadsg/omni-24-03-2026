---
phase: 82-platform-self-healing-scheduled-retention
plan: 05
subsystem: infra
tags: [oncall, pagerduty, webhook, watchdog, dedup, outbox, test-alert, heartbeat, stdlib]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-03 incident store and restart budget, 82-04 certificate/disk incidents, 82-07 outbox + testRequest + /results, 82-08 /health and the channel status"
provides:
  - "deploy/omni-watchdog/omni_watchdog/paging.py: SEVERITY_MAP, pagerduty_event, webhook_message, compose, send, page_incidents, deliver_outbox, send_test, test_event, ping_heartbeat, oncall_block, Budget"
  - "run_once pages incidents, syncs, delivers the backend outbox and test request, posts results, pings the external heartbeat"
  - "sync.post_results(http, base_url, token, delivered, test_result)"
  - "state.json: incidents[].pageKey/sent/sentAt/failedError, delivered (last 500 outbox ids), deliveredErrors, pendingDelivered, pendingTest, oncallLast"
affects: [82-06 install checklist (oncall.env), 82-09 and later Platform health UI plans]

actuals:
  tokens: 17600
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "The watchdog is the only sender; the backend queues and the sync round trip carries the work and the outcome"
    - "Persist the pageKey before the send and set sent after it: a crash leans to one duplicate trigger that the dedup key collapses"
    - "Contract test bridge: the watchdog's http seam is served by the real routers on the test's own event loop (run_once in a worker thread, requests handed to the loop)"

key-files:
  created:
    - deploy/omni-watchdog/omni_watchdog/paging.py
    - backend/tests/test_watchdog_oncall.py
    - backend/tests/test_watchdog_contract.py
    - backend/tests/_watchdog_oncall_world.py
  modified:
    - deploy/omni-watchdog/omni_watchdog/run.py
    - deploy/omni-watchdog/omni_watchdog/sync.py

key-decisions:
  - "A page_failed event is emitted once per incident group and distinct error, not once per minute of a lasting failure; oncallLast still updates on every attempt so the panel stays truthful"
  - "A connection failure is retried like a 429/5xx (1 s then 3 s); the plan lists status codes only, but an outbox failure is final on the backend (it records ok false and does not offer the message again), so a network blip should not lose a notice"
  - "With ONCALL_TYPE none paging does nothing and leaves the incident store exactly as the restart plan wrote it (existing restart tests pin that shape); outbox messages are neither sent nor acknowledged and expire on the backend after 24 h"
  - "The watchdog's test_alert event id is test-<request id>, the id the backend uses for the row it writes from testResult, so the Activity list shows each test once and names the requester"
  - "A test result that /results did not accept is kept in state.pendingTest and re-posted without sending a second alert while the backend still lists the request"
  - "An incident that clears before it was ever paged is forgotten (no resolve for something the channel never saw)"

patterns-established:
  - "Send budget: at most 10 messages per run and no new send after 28 s of the 45 s unit timeout; what does not fit waits for the next run"

requirements-completed: [HEAL-05, HEAL-02]

coverage:
  - id: D1
    description: "A newly opened incident is one PagerDuty trigger (dedup omni:<host>:<key>, severity critical|warning|info, summary at most 1,024) and one resolve with the same dedup key when it clears; a service that gave up produces exactly one trigger across many runs (HEAL-02)"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_watchdog_oncall.py#test_a_gave_up_service_sends_exactly_one_trigger_over_many_runs / test_a_service_healthy_for_an_hour_resolves_the_page_once_with_the_same_dedup_key / test_the_state_is_saved_with_the_page_key_before_the_trigger_leaves"
        status: pass
    human_judgment: false
  - id: D2
    description: "Incidents opened in one run are one grouped trigger keyed by a critical member; the group resolves only when every member has cleared; a ladder move resolves the old key before the new trigger"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_watchdog_oncall.py#test_three_incidents_of_one_run_are_one_trigger_keyed_by_a_critical_member / test_the_group_resolves_only_when_every_member_has_cleared / test_a_ladder_move_resolves_the_old_key_before_it_triggers_the_new_one"
        status: pass
    human_judgment: false
  - id: D3
    description: "Webhook channel posts json, slack and teams bodies; 429/5xx retried twice (1 s, 3 s), other 4xx never; a failed page emits one page_failed, stays unsent and is retried as the same incident"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_watchdog_oncall.py#test_the_json_webhook_body_has_the_documented_fields / test_the_slack_and_teams_webhook_bodies_are_just_text / test_a_503_twice_then_202_is_one_delivery_after_waits_of_1_and_3_seconds / test_a_400_or_other_4xx_is_never_retried / test_a_failed_page_emits_one_page_failed_leaves_the_incident_unsent_and_is_retried_next_run"
        status: pass
    human_judgment: false
  - id: D4
    description: "Outbox messages are delivered once, reported through /results in the same run, never re-sent, at most 10 per run; a failed results call leaves delivered for the next sync body"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_watchdog_oncall.py#test_every_outbox_message_is_delivered_once_and_reported_through_results_in_the_same_run / test_an_outbox_id_that_comes_back_is_not_sent_again / test_at_most_ten_messages_go_out_in_one_run_and_the_rest_wait / test_a_results_call_that_fails_leaves_delivered_for_the_next_sync_body"
        status: pass
    human_judgment: false
  - id: D5
    description: "A test request is a trigger then a resolve with the same dedup key and routing key, reported as testResult and one test_alert event; no channel is a failed result with the documented error and no HTTP call"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_watchdog_oncall.py#test_a_test_request_is_a_trigger_then_a_resolve_with_the_same_key_and_is_reported / test_a_test_request_with_no_channel_is_a_failed_result_and_makes_no_http_call / test_a_test_result_that_could_not_be_posted_is_posted_again_without_a_second_alert"
        status: pass
    human_judgment: false
  - id: D6
    description: "HEARTBEAT_URL gets one GET per run (5 s) and a failure changes nothing and logs no URL; no key, webhook URL or heartbeat URL appears in any body sent to the backend, any event, any error or state.json; paging.py builds no unverified SSL context"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_watchdog_oncall.py#test_the_heartbeat_url_gets_one_get_per_run_with_a_5_second_timeout / test_a_failing_heartbeat_changes_nothing_and_logs_no_url / test_no_secret_appears_in_any_body_sent_to_the_backend_in_an_event_or_in_the_state_file / test_the_pager_uses_the_default_verified_ssl_context_only"
        status: pass
    human_judgment: false
  - id: D7
    description: "End to end: a real watchdog run against the real ingest and platform routes on a throwaway database delivers a notify() notice and a Super Admin test alert to the PagerDuty recorder once each; GET /health shows the test delivered and the channel working; one Activity row names the requester; the next runs send nothing"
    requirement: HEAL-05
    verification:
      - kind: e2e
        ref: "backend/tests/test_watchdog_contract.py#test_a_queued_notice_reaches_the_channel_once_and_is_marked_delivered / test_a_super_admin_test_alert_is_delivered_resolved_and_shown_on_the_health_view / test_the_next_run_sends_nothing_new_to_the_channel / test_a_channel_failure_is_shown_as_not_working_and_the_message_is_not_resent"
        status: pass
    human_judgment: false
  - id: D8
    description: "Outbound HTTPS from the VM to events.pagerduty.com and the webhook host works with the real key (A-82-A11), the alert arrives and resolves, and the no-working-channel banner clears"
    verification: []
    human_judgment: true
    rationale: "Only the live test alert proves outbound reachability and the real routing key; the plan lists it as the end-of-phase operator step"

duration: 16min
completed: 2026-10-30
status: complete
plan_head_before: abcf252dc309acef3ceb045b756449dfb9de53e9
plan_head_after: 9523ec8ce70ce406cb7f70c472ee8bdc7fd07a2a
commits: 3
---

# Phase 82 Plan 05: Watchdog on-call sender Summary

**The watchdog is now the only sender of on-call messages: grouped, deduplicated PagerDuty/webhook pages for its own incidents with a matching resolve, once-only delivery of the backend's queued notices, a trigger-plus-resolve test alert, an external heartbeat ping, and an end-to-end test of a real run against the real backend routes**

## Performance

- **Duration:** 16 min
- **Started:** 2026-10-30T20:06:00Z
- **Completed:** 2026-10-30T20:22:00Z
- **Tasks:** 3
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments

- `paging.py` (standard library only): `page_incidents` sends one trigger per run for the incidents opened in it (dedup key = the highest-severity member's key, `pageKey` recorded on every member and saved before the send, `sent` set after), the group's resolve only when every member has cleared, resolves before triggers so a ladder move resolves the old key first, and a failed delivery leaves the incident unsent to be retried as the same group.
- `send` implements the delivery rules: default verified SSL context, 2xx is success, 429/5xx/connection failures retried after 1 s and 3 s, other 4xx final, errors one capped line naming only the status or exception class; `Budget` caps a run at 10 messages and 28 s of sending.
- `deliver_outbox` (remembers the last 500 ids, re-reports a re-offered id instead of re-sending), `send_test` (trigger then resolve, same dedup key), `ping_heartbeat`, `oncall_block`.
- `run_once` order is now: checks, restart decision, warnings, spool, save, page, save, sync, deliver outbox and test request, post results, heartbeat, save. `sync.post_results` carries `delivered` and `testResult`; a failed results call keeps `pendingDelivered` / `pendingTest` for the next run.
- 38 unit tests (`test_watchdog_oncall.py`) and 5 end-to-end tests (`test_watchdog_contract.py`).

## Contract check (end-to-end test result)

The end-to-end test found no mismatch between the watchdog's shapes and the backend routers as built in 82-01/82-07/82-08 (sync body, `outbox`, `testRequest`, `delivered`, `testResult` and the `/health` and Activity views all line up). It did pin one cross-side hazard that is handled on the **watchdog side**: the backend writes the test-alert Activity row from `testResult` with id `PH-test-<request id>`, and the watchdog's own `test_alert` event would have written a second row (random event id, no requester). The watchdog's event id is therefore `test-<request id>`, the same id; the backend's duplicate-key handling keeps the first row, the one naming the requester. Removing that line makes `test_a_super_admin_test_alert_is_delivered_resolved_and_shown_on_the_health_view` fail with two rows (checked). No backend code changed.

## Task Commits

1. **Task 1: Tracer - gave-up service paged once, resolved when healthy** - `9a4e16dae` (feat). Carries the whole of `paging.py` and the run/sync wiring, because the outbox, test alert and heartbeat functions share the module and the run sequence (same commit-shape note as 82-07).
2. **Task 2: Grouped pages, webhook shapes, retries, outbox, test alert, heartbeat, secrecy** - `63babf1db` (test)
3. **Task 3: End-to-end contract** - `9523ec8ce` (test)

**Plan metadata:** committed separately (docs: complete plan).

## Files Created/Modified

- `deploy/omni-watchdog/omni_watchdog/paging.py` - the on-call sender
- `deploy/omni-watchdog/omni_watchdog/run.py` - paging stage, delivery stage, heartbeat, oncall block
- `deploy/omni-watchdog/omni_watchdog/sync.py` - `post_results(http, base_url, token, delivered, test_result)`
- `backend/tests/test_watchdog_oncall.py`, `backend/tests/_watchdog_oncall_world.py` - unit and run-level tests, shared fake rig
- `backend/tests/test_watchdog_contract.py` - the end-to-end bridge and scenarios, plus the real urllib client against a loopback server

## Decisions Made

See key-decisions above.

## Deviations from Plan

### Auto-fixed / added

**1. [Rule 2 - Missing critical] Connection failures are retried like 429/5xx**
- **Issue:** the backend marks an outbox message delivered once the watchdog reports it, even with `ok: false`, and never offers it again, so a single network blip would lose a notice.
- **Fix:** a refused or timed-out connection takes the same two retries (1 s, 3 s) inside the window. 4xx other than 429 is still never retried.
- **Files:** paging.py. **Commit:** 9a4e16dae

**2. [Rule 2 - Missing critical] page_failed is rate limited per incident group and error**
- **Issue:** a lasting failure (wrong routing key, 400) is retried every minute by design; one event per attempt would write 1,440 Activity rows a day.
- **Fix:** one `page_failed` per group and distinct error text; the retry and `oncallLast` (which drives the panel's channel status) still happen every run.
- **Files:** paging.py. **Commit:** 9a4e16dae

**3. [Rule 2 - Missing critical] A test result that /results did not accept is not lost or re-sent**
- **Issue:** the sync body has no `testResult` field; losing the post would leave the request pending and the next run would send a second alert.
- **Fix:** `state.pendingTest` is re-posted each run until accepted, and a listed request with the same id is not sent again.
- **Files:** run.py. **Commit:** 9a4e16dae

**4. [Plan wording] Contract test bridge uses httpx `ASGITransport` and a worker thread, not `TestClient`**
- Starlette's `TestClient` runs the app on its own event loop, while the throwaway database handle (Motor) belongs to the test's loop. `run_once` runs in `asyncio.to_thread` and the bridge hands each backend request to the test loop with `run_coroutine_threadsafe`. The client address is still forced to 127.0.0.1 and the token still comes from a tmp `CREDENTIALS_DIRECTORY`.

**5. [Plan wording] `send(http, oncall, message, ...)` takes the already composed body**
- `compose(oncall, action, ...)` builds the message for the channel type and `send` posts it (the URL comes from the oncall type). Same behaviour as the plan, one more small function.

**6. [Process] Tests were written after the implementation**
- The module was written whole before its tests, so there is no separate RED commit. Mutation spot checks confirm the tests bite: leaving `sent` unset fails 5 tests, echoing the response body into an error fails 6 (including the secrecy test), dropping the `test-` event id fails the Activity test.

**Total deviations:** 3 added safeguards (Rule 2), 3 plan-wording or process notes. **Impact:** none on the contract the plan lists.

## Issues Encountered

- **Test database:** the end-to-end tests (and the 82-07 tests) use `tests/_mongo_test_db.py`, which creates a uniquely named database on whatever server `MONGO_TEST_URL` points to, defaulting to the live mongod on 27017. This run started a private mongod on port 27999 (data under the session scratchpad) and ran everything with `MONGO_TEST_URL=mongodb://127.0.0.1:27999`; the live database was not touched. The private mongod was left running for the session and can be stopped with `pkill -f 'mongod --dbpath .*mongo-data --port 27999'`.
- **Verification without the variable:** the plan's `<verification>` command as written would create (and drop) its `omni_test_*` databases on the live server; run it with `MONGO_TEST_URL` set to keep that off the live instance.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-82-16 (no secret in logs, events, the sync body, results or state.json: `test_no_secret_appears_in_any_body_sent_to_the_backend_in_an_event_or_in_the_state_file` with a hostile 400 that echoes the key and URL), T-82-17 (default verified SSL context, structural check in `test_the_pager_uses_the_default_verified_ssl_context_only`), T-82-18 (grouped trigger, `sent` persisted before and after, 500-id memory, 10 messages per run) and T-82-19 (24 h backend TTL, remembered ids) are mitigated as specified.

Known limit: a run killed in the middle of an HTTP call that the channel did accept, followed by that incident clearing before the next run, leaves an unresolved PagerDuty alert (the pager forgets an incident that cleared unsent). Too narrow to design around; the dedup key means a later trigger for the same key joins that alert.

## User Setup Required

None for the repo. Operator steps (not done here): fill `/etc/omni-watchdog/oncall.env` with the real routing key or webhook URL and `HEARTBEAT_URL`, press Send test alert in the Platform health panel, confirm exactly one alert arrives and resolves and the no-working-channel banner clears (A-82-A11).

## Next Phase Readiness

The on-call path is complete end to end (incident pages, backend notices, test alert, external heartbeat). The remaining Phase 82 plans do not depend on anything unfinished here.

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-30*

## Self-Check: PASSED

All plan files exist on disk (`paging.py`, `test_watchdog_oncall.py`, `test_watchdog_contract.py`, `_watchdog_oncall_world.py`); commits `9a4e16dae`, `63babf1db` and `9523ec8ce` are ancestors of HEAD; all task acceptance criteria re-run (`events.pagerduty.com/v2/enqueue` count 1, no unverified context, `def post_results` count 1, `load_watchdog` count 2); plan verification: 189 passed.
