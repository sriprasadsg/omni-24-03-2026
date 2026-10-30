---
phase: 82-platform-self-healing-scheduled-retention
plan: 08
subsystem: infra
tags: [watchdog, health, dead-man-switch, fastapi, mongodb, autonomous-ops, platform-status]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-01 heartbeat and snapshot documents, 82-07 selfheal.watchdog_state, oncall_outbox, oncall_test_requests and oncall.test_view, 82-03/82-04 service, certs and disks shapes"
provides:
  - "status.health summary on GET /api/platform/autonomous-ops/status (and the stop and resume answers): {watchdog, lastSeenAt, channel, channelError}"
  - "GET /api/platform/autonomous-ops/health: the full health document (shape below)"
  - "selfheal.channel_status, health_summary, health_document, SERVICE_NAMES, INSTALL_CHECKLIST_PATH, CADENCE_SECONDS"
  - "Dead-man switch: LOCK_NAME autonomous_ops_selfheal, LOCK_TTL_SECONDS 120, LOCK_RENEW_EVERY 30, SWEEP_EVERY 60, silence_sweep, run_sweep_once, selfheal_loop (registered at startup)"
  - "record_heartbeat clears alarmedAt and writes one watchdog_back row"
affects: [82-11 and 82-12 (banner and Watchdog/services, certificate, disk and on-call cards type against the shapes below), 82-05 watchdog sender]

actuals:
  tokens: 21000
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "The health document copies the watchdog snapshot field by field through type-checked accessors; the backend computes no service state, certificate expiry, disk percent or forecast"
    - "Dead-man alarm claimed by a compare-and-set on the very heartbeat that was read (lastSeenAt and alarmedAt null), so a heartbeat landing mid-sweep or a second runner changes nothing"
    - "Channel status = outcome of the newest of three delivery records; every time is normalised to aware UTC before comparing"

key-files:
  created:
    - backend/tests/test_platform_health_status.py
    - backend/tests/test_platform_health_deadman.py
    - backend/tests/_platform_health_world.py
  modified:
    - backend/autonomous_ops/selfheal.py
    - backend/autonomous_ops/views.py
    - backend/autonomous_ops_platform_endpoints.py
    - backend/app_startup.py
    - backend/tests/test_autonomous_ops_endpoints_writes.py

key-decisions:
  - "selfheal._utc now accepts a datetime (naive means UTC, aware is converted to UTC) as well as an ISO string and never raises; this is the single normaliser for channel_status"
  - "A time that cannot be read counts as the oldest; such a record still decides the channel only when nothing else exists"
  - "A test request closed because nobody picked it up (sentAt null) says nothing about the channel and is ignored by channel_status"
  - "Delivery error text shown on screen has any http(s) URL replaced by [url] (a webhook or PagerDuty URL is the secret)"
  - "Certificates sort soonest expiry first; an unreadable certificate (daysLeft null) goes first because it is a warning"
  - "Before the first heartbeat oncall is {type null, heartbeatConfigured false, status not_set_up, last null}; stop is {effective false, source none}; updatedAt and host are null"
  - "The sweep claims with alarmedAt = now (millisecond precision) and gives the episode back (alarmedAt null) if the row or the notification fails, so the next sweep retries; the silent row id is silent-<lastSeenAt ms>, so a retry cannot write a second row"
  - "oncall.type is whitelisted to none, pagerduty, webhook (anything else is null); stop.source to file, database, cache, none"

patterns-established:
  - "Platform status answers carry health on every route that returns platform_status_payload (status, stop, resume): all are control:platform_autonomous_ops holders"

requirements-completed: [HEAL-05]

coverage:
  - id: D1
    description: "status.health summary: not_installed with all-null fields, running plus untested/none/failing/working from the newest of snapshot last delivery, latest test result and latest acknowledged outbox message; a failing health computation returns health null and leaves the stop status intact"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_status.py#test_no_heartbeat_the_summary_says_not_installed / test_after_one_sync_the_watchdog_is_running_and_the_channel_untested / test_oncall_type_none_means_no_channel / test_a_failed_delivery_then_a_later_successful_test / test_an_older_successful_test_does_not_hide_a_newer_failed_delivery / test_the_newest_acknowledged_outbox_message_counts / test_a_failure_computing_health_leaves_the_stop_status_intact"
        status: pass
    human_judgment: false
  - id: D2
    description: "Orchestrator note 1: mixed time forms (string newest vs naive datetime older and the reverse, another UTC offset, unreadable time) compared as UTC and never raising"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_status.py#test_newest_is_a_string_and_the_older_is_a_naive_datetime / test_newest_is_a_naive_datetime_and_the_older_is_a_string / test_a_string_with_another_offset_is_compared_as_the_instant_it_is / test_a_time_that_cannot_be_read_counts_as_oldest_and_never_raises"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /health: four services in fixed order with name and unit, certificates soonest first, disks, on-call status, testAlert equal to oncall.test_view, stale everywhere while silent, not installed document, grace after a backend start"
    requirement: HEAL-01
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_status.py#test_not_installed_the_document_is_honest_about_having_nothing / test_running_services_come_back_in_the_fixed_order_and_certs_soonest_first / test_silent_keeps_every_last_known_value_marked_stale / test_just_after_a_backend_start_an_old_heartbeat_is_not_yet_silent / test_oncall_status_is_derived_from_the_newest_outcome / test_test_alert_equals_the_latest_test_view"
        status: pass
    human_judgment: false
  - id: D4
    description: "Orchestrator note 2: the exact 82-04 certs and disks shapes (disks[].forecast {state, days, rung}, disks[].paths) and the 82-03 service fields POSTed through /api/internal/watchdog/sync come back from GET /health with every value intact; the snapshot depth limit drops nothing"
    requirement: HEAL-03
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_status.py#test_the_real_certs_disks_and_service_shapes_survive_the_sync_door / test_a_second_sync_replaces_the_values_the_backend_shows"
        status: pass
    human_judgment: false
  - id: D5
    description: "T-82-27 / T-82-29: 403 for tenant admin, viewer, analyst, Platform Support and an API key on /health, /status, /stop and /resume; no routing key, URL or token key or value in the document or summary"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_status.py#test_only_the_platform_owner_can_read_health_or_the_status_summary / test_an_api_key_cannot_read_the_health_document / test_no_secret_key_or_value_reaches_the_document_or_the_summary / test_a_delivery_error_never_carries_a_url"
        status: pass
    human_judgment: false
  - id: D6
    description: "PROH-82-13 / D-24: the backend reads no certificate and measures no disk; its values are the watchdog's"
    requirement: HEAL-04
    verification:
      - kind: unit
        ref: "backend/tests/test_platform_health_status.py#test_the_backend_never_reads_a_certificate_or_measures_a_disk"
        status: pass
    human_judgment: false
  - id: D7
    description: "D-05 dead-man: one watchdog_silent row and one platform in-app notification per silence episode after 300 s and 180 s of uptime, armed only after the first heartbeat, the next heartbeat writes one watchdog_back row, a new silence is a new episode, the on-call outbox stays empty, one runner under the renewed lock, a failed alarm is retried"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_deadman.py#test_one_alarm_per_silence_and_nothing_more_while_it_lasts / test_the_next_heartbeat_clears_the_alarm_and_a_later_silence_is_a_new_episode / test_no_heartbeat_ever_never_alarms / test_a_backend_that_just_started_gives_the_watchdog_time / test_two_sweeps_at_once_one_takes_the_lock_and_one_row_is_written / test_a_heartbeat_that_arrives_during_the_sweep_wins / test_a_failed_alarm_is_tried_again_by_the_next_sweep / test_the_sync_door_ends_the_silence_and_the_panel_shows_both_rows / test_the_loop_survives_a_failed_pass_and_keeps_sweeping"
        status: pass
    human_judgment: false
  - id: D8
    description: "On the real server with the watchdog installed: stop the watchdog timer for more than 5 minutes and see the in-app notification and the red banner once, then start it and see Reporting again in Activity"
    verification: []
    human_judgment: true
    rationale: "Needs the watchdog installed and a backend restart (the user's steps); this plan installs and restarts nothing"

duration: 12min
completed: 2026-10-30
status: complete
plan_head_before: dd7c261f6eb2a8f769cbe0a75df1df702f890271
plan_head_after: 2c68cf3e57bfc06d95a605f4a3d14b24aa7869a9
commits: 4
---

# Phase 82 Plan 08: Platform health status and dead-man switch Summary

**What the watchdog reports now reaches the Super Admin: a compact health summary on the shared status poller, the full Platform health document behind GET /health (services, certificates, disks and forecast, on-call state, test alert, stale-aware), and a lock-guarded sweep that raises exactly one in-app alarm per silence once the watchdog has reported at least once**

## Accomplishments

- `GET /api/platform/autonomous-ops/status` (and the stop and resume answers) carry `health: {watchdog, lastSeenAt, channel, channelError}`; a failure computing it logs and returns `health: null`.
- `GET /api/platform/autonomous-ops/health` returns the document below. Super Admin only (`control:platform_autonomous_ops`) plus an interactive session.
- `selfheal_loop` sweeps every 60 s under the `autonomous_ops_selfheal` lock; registered in `run_startup_services` beside the reconciler.
- 42 new tests in `test_platform_health_status.py` (31) and `test_platform_health_deadman.py` (11), on a throwaway mongod.

## Example GET /health response (running; 82-11 and 82-12 type against this)

Fields that can be `null`: `updatedAt`, `host`, `watchdog.lastSeenAt/firstSeenAt` (never reported), every service field except `id`, `name`, `unit`, `stale`, certificate `notAfter/daysLeft/error/path`, disk numeric fields, `forecast.days`, `oncall.type`, `oncall.last`, `testAlert`. `installChecklist.url` is always `null` today. Service `state` is one of `healthy, checking, down, restarting, gave_up, expected_off, unexpected_running` (or `null`). `stop.source` is `file|database|cache|none`. `oncall.status` is `working|not_working|not_tested|not_set_up`; `oncall.type` is `none|pagerduty|webhook|null`. `testAlert` is `{id, requestedAt, requestedBy, state pending|delivered|failed, sentAt, error}`.

```json
{
  "updatedAt": "2026-10-30T19:43:36.624000+00:00",
  "host": "omni",
  "watchdog": {"state": "running", "lastSeenAt": "2026-10-30T19:43:36.624000+00:00",
               "firstSeenAt": "2026-10-28T08:01:12.000000+00:00", "cadenceSeconds": 60, "silentAfterSeconds": 300},
  "installChecklist": {"path": "deploy/omni-watchdog/INSTALL.md", "url": null},
  "stop": {"effective": false, "source": "none"},
  "services": [
    {"id": "mongod", "name": "MongoDB", "unit": "mongod", "state": "healthy", "since": "2026-10-30T10:00:00Z",
     "failedChecks": 0, "restartsInWindow": 0, "nextRestartAt": null, "budgetReturnsAt": null, "pagedAt": null,
     "waitingOn": null, "detail": "", "stale": false},
    {"id": "omni-backend", "name": "Backend", "unit": "omni-backend", "state": "down", "since": "2026-10-30T19:40:00Z",
     "failedChecks": 3, "restartsInWindow": 1, "nextRestartAt": "2026-10-30T19:45:00Z", "budgetReturnsAt": null,
     "pagedAt": null, "waitingOn": "mongod", "detail": "connection refused", "stale": false},
    {"id": "nginx", "name": "nginx", "unit": "nginx", "state": "healthy", "since": "2026-10-30T10:00:00Z",
     "failedChecks": 0, "restartsInWindow": 0, "nextRestartAt": null, "budgetReturnsAt": null, "pagedAt": null,
     "waitingOn": null, "detail": "", "stale": false},
    {"id": "ollama", "name": "Ollama", "unit": "ollama", "state": "expected_off", "since": "2026-10-30T10:00:00Z",
     "failedChecks": 0, "restartsInWindow": 0, "nextRestartAt": null, "budgetReturnsAt": null, "pagedAt": null,
     "waitingOn": null, "detail": "expected_off", "stale": false}
  ],
  "certs": [
    {"path": "/etc/ssl/extra.pem", "notAfter": "2026-11-11T12:00:00Z", "daysLeft": 12.5, "rung": 1, "pinned": false,
     "error": null, "stale": false},
    {"path": "/etc/nginx/ssl/omni.crt", "notAfter": "2028-12-20T00:00:00Z", "daysLeft": 811.25, "rung": 0, "pinned": true,
     "error": null, "stale": false}
  ],
  "disks": [
    {"mount": "/", "paths": ["/", "/var/lib/mongodb"], "usedPct": 69.4, "freeBytes": 30600000000,
     "totalBytes": 100000000000, "rung": 0, "forecast": {"state": "ok", "days": 9.5, "rung": 1}, "stale": false}
  ],
  "oncall": {"type": "pagerduty", "heartbeatConfigured": true, "status": "working",
             "last": {"at": "2026-10-30T11:58:00+00:00", "ok": true, "error": null}},
  "testAlert": null
}
```

Summary on the status poller: `{"watchdog": "running", "lastSeenAt": "<ISO>", "channel": "working", "channelError": null}`; `channel` is `null` while `watchdog` is `not_installed`, otherwise `working|untested|none|failing`; `channelError` is text only when `failing` (URLs replaced by `[url]`, 300 characters at most).

## Task Commits

1. **Task 1: Tracer - status.health summary, channel from the newest of three records** - `2082a989f` (feat)
2. **Task 2: GET /health document** - `4c8c3bdfd` (feat)
3. **Task 3: Dead-man switch, watchdog back, startup registration** - `4c3227b36` (feat)
4. **Existing platform status test updated for the new key** - `2c68cf3e5` (test)

**Plan metadata:** committed separately (docs).

## Deviations from Plan

### Orchestrator additions (applied)

**1. [Orchestrator note 1] Timestamp normalisation in channel_status** - `selfheal._utc` did not handle a datetime directly (it went through `str()`), so it now takes a datetime (naive means UTC) or an ISO string, converts to UTC, never raises; an unreadable time is the oldest. Tests in both directions (string newer, naive older, and the reverse), another UTC offset, an unparseable value, `None` and a nested object. Committed `2082a989f`.

**2. [Orchestrator note 2] Real shapes through the real door** - `test_the_real_certs_disks_and_service_shapes_survive_the_sync_door` posts the 82-04 certs and disks (forecast `{state, days, rung}`, `paths`), the 82-03 service fields and a webhook channel through `POST /api/internal/watchdog/sync`, then asserts every posted field in `GET /health`. `_SNAPSHOT_DEPTH = 4` drops nothing for these shapes (the deepest value is `disks[].forecast.days`, three levels below the block), so the limit is unchanged. A stored-document assertion pins that too.

**3. [Orchestrator note 3] Extra suites** - `test_catalogue_slice_autonomous_ops.py`, `test_route_auth_baseline.py`, `test_platform_role_routes.py`, `test_catalogue_route_parity.py`, `test_watchdog_artifacts.py` and `test_autonomous_ops_copy.py`: 123 passed, 1 failed (the known `test_ledger_ratchets` on stale ledger entries; none names this plan's route or module). `/status`, `/stop` and `/resume` all use `_require_platform_autonomy_control`; a test asserts 403 for tenant admin, viewer, analyst and Platform Support on all of them and on `/health`, so the new `health` key cannot reach Platform Support.

### Auto-fixed

**4. [Rule 1 - Bug] Existing exact-keys assertion** - `test_autonomous_ops_endpoints_writes.py::test_platform_wide_stop_and_resume_and_name_masking` pinned the platform status key set and failed on the new `health` key. Added `"health"` to the expected set. Commit `2c68cf3e5`.

**5. [Rule 2 - Missing critical functionality] URLs stripped from delivery errors** - T-82-29 asks for no secret in any health payload, and a failed HTTP call's error text can contain the request URL, which for a webhook or PagerDuty is the secret. `channel_status` replaces `http(s)://...` by `[url]` before the text reaches the summary or document (the watchdog is expected not to send one, this is the backstop). Test `test_a_delivery_error_never_carries_a_url`.

**6. [Rule 2 - Missing critical functionality] Failed alarm is retried, one row per episode** - the plan only required one alarm per episode. If the row or the notification fails after the claim, the claim is given back so the next sweep retries, and the silent row id (`silent-<lastSeenAt ms>`) makes a retry unable to write a second row. Test `test_a_failed_alarm_is_tried_again_by_the_next_sweep`.

### Plan text interpreted

- **Test file split.** One test file for all three tasks would be about 560 lines, over the CLAUDE.md 500-line limit. The tests are in `test_platform_health_status.py` (Tasks 1-2, 335 lines), `test_platform_health_deadman.py` (Task 3, 213 lines) and the shared fixture module `_platform_health_world.py` (64 lines). The plan's Task 3 verify command names only the status file; run both files (the phase `<verification>` list should include `test_platform_health_deadman.py`).
- **`oncall.last` in the document** is the newest delivery record (a snapshot, test or outbox outcome) as `{at, ok, error}`, not the raw snapshot value, so the card can say "Last delivered {HH:MM}".
- **Notification text** gives the time as `HH:MM UTC` (server-side text has no viewer time zone); the title is exactly `The watchdog has gone silent`.
- **Silent row copy** uses `minutes` = whole minutes since the last heartbeat (`No heartbeat for 5 minutes.` for the first sweep after 301 s).
- **`files_modified`** did not list `test_autonomous_ops_endpoints_writes.py` (item 4) and the two new test modules.

**Total deviations:** 3 orchestrator additions, 1 bug (existing test), 2 safety additions, plus the interpretation notes. **Impact:** none on the contract; `selfheal.py` is 450 lines and `autonomous_ops_platform_endpoints.py` 292.

## Verification

- Plan `<verification>` (plus the new dead-man file): `test_platform_health_status.py`, `test_platform_health_deadman.py`, `test_platform_health_sync.py`, `test_platform_health_oncall.py`, `test_platform_health_activity.py`, `test_platform_health_migration.py`, `test_distributed_lock.py`, `test_autonomous_ops_stop.py`: 160 passed on a private mongod (port 27999, stopped and confirmed closed with `ss`).
- `test_autonomous_ops_endpoints.py`, `test_autonomous_ops_endpoints_writes.py`, `test_watchdog_warnings.py`: 79 passed after item 4.
- Acceptance greps: `health_summary(` in `views.py` 1; `"/health"` in the platform endpoints 1; no `statvfs|openssl|x509` and no `notify(` in `selfheal.py`; `selfheal_loop` in `app_startup.py` 2.
- A mutation check (claim without the `lastSeenAt` guard) made `test_a_heartbeat_that_arrives_during_the_sweep_wins` fail, then the file was restored.

## Known Stubs

None.

## Threat Flags

None beyond the register. T-82-27 (platform-only plus interactive session, 403 tests), T-82-28 (armed after first heartbeat, 180 s grace, compare-and-set, renewed lock) and T-82-29 (whitelisted fields, key and value scan, URL strip) are mitigated as specified. The new `GET /health` route reuses `_require_platform_autonomy_control`, so `test_route_auth_baseline.py` needed no entry.

## Issues Encountered

- **Known, not mine:** `test_catalogue_route_parity.py::test_ledger_ratchets` fails on stale ledger entries from the user's uncommitted work. `test_autonomous_ops_structural` (crash on stray tracked files under `backend/backend/`) was not run.
- **Live effect:** nothing is live until the user restarts the backend: the new route, the `health` key, `alarmedAt` on the heartbeat document and the sweep loop all start with that restart. The loop does nothing until a watchdog has reported.
- HEAL-01, HEAL-03, HEAL-04 are shared with sibling plans; see the requirements note in the metadata commit.

## Next Phase Readiness

82-11 and 82-12 can type against the `health` summary and the `/health` document above. 82-05 (watchdog on-call sender) will fill `oncall.last` as `{at, ok, error, kind}`; this plan already reads it.

## Self-Check: PASSED

Files exist (`selfheal.py`, `views.py`, `autonomous_ops_platform_endpoints.py`, `app_startup.py`, `test_platform_health_status.py`, `test_platform_health_deadman.py`, `_platform_health_world.py`); commits `2082a989f`, `4c8c3bdfd`, `4c3227b36`, `2c68cf3e5` are ancestors of HEAD.
