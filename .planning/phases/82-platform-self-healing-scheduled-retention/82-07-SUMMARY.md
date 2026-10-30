---
phase: 82-platform-self-healing-scheduled-retention
plan: 07
subsystem: infra
tags: [oncall, outbox, watchdog, fastapi, mongodb, autonomous-ops, test-alert]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-01 sync contract (outbox [] and testRequest null placeholders), selfheal heartbeat, ledger.record_platform_health, health_messages.render"
provides:
  - "backend/autonomous_ops/oncall.py: oncall_outbox (enqueue, pending_outbox, ack_delivered) and test requests (request_test, pending_test, record_test_result, test_view)"
  - "notify() additionally queues every Autonomous Ops notice for on-call"
  - "POST /api/platform/autonomous-ops/health/test-alert"
  - "selfheal.watchdog_state (not_installed / running / silent) with SILENT_AFTER, STARTUP_GRACE, PROCESS_STARTED_AT"
  - "migration 026 (oncall_outbox and oncall_test_requests indexes)"
affects: [82-05 watchdog on-call sender, 82-08 platform health status and dead-man switch, Phase 82 UI plans]

actuals:
  tokens: 21500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "The backend queues, the watchdog (which alone holds the key) delivers: outbox and test request ride the existing sync round trip"
    - "At-most-one pending request enforced by a partial unique index, not by a read-then-insert"
    - "Never-raise side effects: enqueue and ack swallow and log (no content) so a notice or sync is never blocked"

key-files:
  created:
    - backend/autonomous_ops/oncall.py
    - backend/migrations/026_oncall_outbox.py
    - backend/tests/test_platform_health_oncall.py
  modified:
    - backend/autonomous_ops/notify.py
    - backend/autonomous_ops/selfheal.py
    - backend/autonomous_ops/health_messages.py
    - backend/autonomous_ops_platform_endpoints.py
    - backend/watchdog_ingest_endpoints.py

key-decisions:
  - "A delivered entry marks a message delivered whether ok is true or false (deliveredAt set once); a failed delivery is recorded in ok and error, not retried by the backend (the watchdog owns retries within its run)"
  - "One pending test request at a time is enforced by a partial unique index on oncall_test_requests.state (pending); a request nobody picks up for 10 minutes is closed as failed so one lost request cannot block every later test"
  - "The test_alert platform-health row uses event id test-<request id> (row id PH-test-<request id>) and is written with the requester as actor, so re-sent results are idempotent and the audit event names the person"
  - "Credential-like metadata keys (token, key, url, secret, password, routing_key, webhookUrl, heartbeatUrl) are dropped from outbox details; only scalars are kept"
  - "POST /results now needs the database (503 on failure) because it acts on delivered and testResult"

patterns-established:
  - "sync_response reads outbox and testRequest in separate try/except blocks; an unreadable queue reads as empty and never fails the sync"

requirements-completed: [HEAL-05]

coverage:
  - id: D1
    description: "Every notify() notice becomes one oncall_outbox trigger document (severity mapped, summary at most 1,024 characters, 24 h expiry); notify never raises and its in-app post is unchanged"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_oncall.py#test_notify_posts_in_app_and_queues_one_outbox_message / test_notify_still_returns_none_and_posts_in_app_when_enqueue_raises / test_enqueue_never_raises_when_the_insert_fails / test_notify_severity_maps_to_oncall_severity / test_a_long_notice_is_capped_at_1024_characters_in_the_summary"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop.py; backend/tests/test_autonomous_ops_breaker.py; backend/tests/test_autonomous_ops_gate_order.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "The sync response lists up to 20 undelivered, unexpired messages oldest first; a delivered entry in a later sync or in POST /results marks it once with a 300-character error cap; expired messages are never returned"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_oncall.py#test_sync_hands_out_the_message_and_a_delivered_entry_marks_it / test_results_endpoint_marks_a_message_delivered_with_a_capped_error / test_a_second_delivered_entry_changes_nothing / test_an_expired_message_is_never_returned / test_twenty_five_pending_messages_list_twenty_oldest_first"
        status: pass
    human_judgment: false
  - id: D3
    description: "Super Admin test alert: request, one request per click storm, hand-off as testRequest, result closes it once and writes one test_alert platform-health row naming the requester; failed result stores a capped error and a critical chip"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_oncall.py#test_super_admin_requests_a_test_alert_and_a_second_click_gets_the_same_one / test_the_next_sync_carries_the_test_request_and_the_result_closes_it / test_a_repeated_result_writes_no_second_row / test_a_failed_result_stores_the_capped_error_and_a_critical_chip / test_a_request_nobody_picked_up_is_closed_so_a_new_test_can_be_sent"
        status: pass
    human_judgment: false
  - id: D4
    description: "Test-alert guards: 409 Install the watchdog first. with no heartbeat, 409 silent copy, grace after a backend start, 403 for tenant admin, viewer, Platform Support and an API key"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_oncall.py#test_no_heartbeat_ever_answers_409_install_the_watchdog_first / test_a_silent_watchdog_answers_409_with_the_silent_copy / test_a_stale_heartbeat_just_after_a_backend_start_is_accepted / test_non_super_admin_identities_get_403 / test_an_api_key_cannot_request_a_test_alert / test_watchdog_state_not_installed_running_silent_and_grace"
        status: pass
    human_judgment: false
  - id: D5
    description: "Migration 026 is idempotent (outbox: unique id, TTL on expiresAt, deliveredAt; test requests: unique id, requestedAt, one pending)"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_oncall.py#test_migration_creates_the_outbox_and_test_request_indexes / test_migration_twice_leaves_the_same_index_set / test_only_one_request_can_be_pending_at_the_database_level"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-01 / PROH-82-04: no backend module names the on-call secret file or its variables, and no sync response, test-alert response, outbox document or test request carries a routing key, URL or token"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_oncall.py#test_no_backend_module_names_the_oncall_secret_file_or_its_variables / test_no_response_or_document_carries_a_routing_key_or_url / test_metadata_with_credential_like_keys_is_not_stored"
        status: pass
    human_judgment: false
  - id: D7
    description: "Whether Phase 81 notices should page on-call at warning and info severity (A-82-A7) and whether 300 s / 180 s are the right silence and grace values (A-82-A10)"
    verification: []
    human_judgment: true
    rationale: "Both are flagged, not user-confirmed assumptions; each is one mapping or two constants and can be changed without migration"

duration: 42min
completed: 2026-10-30
status: complete
plan_head_before: a958f1ef9bb62d553e3dd7bff6396b387fb33a9a
plan_head_after: 138b3b77029966cff5ae17e0fd6c5b0c2b377446
commits: 3
---

# Phase 82 Plan 07: On-call outbox and test alert Summary

**Backend queue for on-call delivery: every Autonomous Ops notice and every Super Admin test alert is queued in MongoDB and handed to the watchdog in the sync response, outcomes come back through `delivered` and `testResult`, and the backend never sees the on-call key**

## Performance

- **Duration:** 42 min
- **Completed:** 2026-10-30
- **Tasks:** 3
- **Files:** 8 (3 created, 5 modified)

## Accomplishments

- `notify()` keeps its signature and in-app post and now also calls `oncall.enqueue` in its own `try/except`; Phase 81 stop, breaker and rate-limit notices each become one `oncall_outbox` document.
- The sync response fills `outbox` and `testRequest`; `/sync` and `/results` mark delivery (once) and close the test request.
- `POST /api/platform/autonomous-ops/health/test-alert` (Super Admin, interactive session) with the 409 guards driven by the new `selfheal.watchdog_state`.
- Migration 026 and 39 tests (real Mongo through a throwaway mongod on port 27999).

## Exact shapes the sync response returns (82-05 consumes these)

Response of `POST /api/internal/watchdog/sync` (unchanged top-level shape from 82-01):

```json
{"stop": {"active": false, "scope": null, "pressedAt": null},
 "acceptedEventIds": ["<event id>"], "droppedEvents": 0,
 "outbox": [
   {"id": "OB-<32 hex>", "kind": "trigger", "dedupKey": null, "severity": "critical|warning|info",
    "summary": "<title>: <message>  (at most 1,024 characters)",
    "details": {"title": "<=200 chars", "message": "<=1,024 chars", "tenantId": "<tenant id>",
                "<scalar metadata keys from the notice, e.g. scope>": "<=200 chars or number/bool"}}
 ],
 "testRequest": {"id": "TR-<32 hex>", "requestedAt": "<ISO 8601, UTC, whole seconds>"}}
```

- `outbox` holds up to 20 undelivered, unexpired messages, oldest first, and lists the same ones on every sync until they are acknowledged. `kind` is always `trigger` and `dedupKey` always `null` (no automatic resolve, A-82-A7); the watchdog builds its PagerDuty dedup key from the host and the outbox `id`. `testRequest` is `null` when none is pending (and for a request older than 10 minutes, which is closed as failed instead).
- Acknowledge delivered messages in the next sync body or in `POST /results`, whichever comes first: `"delivered": [{"id": "OB-...", "ok": true, "at": "<ISO>"}]` or `{"id": "OB-...", "ok": false, "error": "<capped at 300>"}`. Only the first acknowledgement counts.
- Report the test alert in `POST /results` (or any later body): `{"v": 1, "testResult": {"id": "TR-...", "ok": true, "at": "<ISO>"}}` or `{"id": "TR-...", "ok": false, "error": "<capped at 300>", "at": "<ISO>"}`. `at` becomes the row time and `sentAt` (never later than now); the result is accepted once, from the pending request only. `POST /results` still answers `{"ok": true}`, or 503 when storage is unavailable (the watchdog should retry with the next sync).

Test-alert API: `POST /api/platform/autonomous-ops/health/test-alert` answers `{"testAlert": {"id", "requestedAt", "requestedBy" (display name), "state": "pending", "sentAt": null, "error": null}}`; `oncall.test_view(db)` returns the latest request in the same shape with `state` of `pending`, `delivered` or `failed`. 409 details: `Install the watchdog first.` and `The watchdog is silent, so a test can't be sent until it reports again.` (in `health_messages.API_DETAIL`).

## Task Commits

1. **Task 1: Tracer - notify() queues the notice, sync hands it out, delivered entry marks it** - `2346db073` (feat)
2. **Task 2: Send test alert - request, hand-off, result, Activity row, watchdog-state guard** - `ac00b34ea` (feat)
3. **Task 3: Migration 026, expiry limits and the D-01 secrecy guard** - `138b3b770` (feat)

**Plan metadata:** committed separately (docs: complete plan).

## Decisions Made

See key-decisions above.

## Deviations from Plan

### Auto-fixed / added

**1. [Rule 2 - Missing critical] One pending test request enforced in the database**
- **Found during:** Task 2
- **Issue:** a read-then-insert cannot guarantee "one request per click storm" under concurrent POSTs.
- **Fix:** a third `oncall_test_requests` index, a partial unique index on `state` for `pending`; `request_test` retries the read on a duplicate key. The plan lists unique `id` and `requestedAt` only; both exist, plus this one.
- **Files modified:** backend/autonomous_ops/oncall.py, backend/migrations/026_oncall_outbox.py
- **Commit:** ac00b34ea, 138b3b770

**2. [Rule 2 - Missing critical] A pending request nobody picks up expires**
- **Found during:** Task 2
- **Issue:** with one pending request reused, a request lost while the watchdog was down would block every later test and be sent unprompted whenever the watchdog returned days later.
- **Fix:** `TEST_PENDING_MAX` = 10 minutes: an older pending request is closed as failed (`The watchdog did not pick this request up.`) and is not handed out.
- **Files modified:** backend/autonomous_ops/oncall.py
- **Commit:** ac00b34ea

**3. [Rule 2 - Missing critical] Credential-like metadata keys dropped from outbox details**
- **Found during:** Task 3 (D-01)
- **Fix:** `_DETAIL_BLOCKED` keys (token, key, url, secret, password, routing_key, webhookUrl, heartbeatUrl) are never copied from notice metadata; only scalars are kept.
- **Commit:** 2346db073

**4. [Plan wording] The secrecy scan ignores `SLACK_WEBHOOK_URL`**
- `backend/app_startup.py` and `backend/soar_engine.py` legitimately use `SLACK_WEBHOOK_URL`. The test matches `WEBHOOK_URL` and `HEARTBEAT_URL` only when not preceded by a letter or underscore; `oncall.env` and `PAGERDUTY_ROUTING_KEY` match anywhere. The scan skips every `venv*` directory (two exist under `backend/`, 100k files each).

**5. [Commit shape] Shared file across tasks**
- `oncall.py` was written whole in one pass (outbox, test requests, `ensure_indexes`), so the Task 1 commit already contains the Task 2 and 3 functions of that file, and `selfheal.watchdog_state` landed with Task 1. Each commit is self-consistent and tested.

**Total deviations:** 3 added safeguards (Rule 2), 1 test-scope refinement, 1 commit-shape note. **Impact:** none on the contract above.

## Issues Encountered

- **Test database:** a private throwaway `mongod` on port 27999 (data in the scratchpad) was started and stopped by this run; nothing touched the live MongoDB.
- **Pre-existing, not mine:** `test_catalogue_route_parity.py::test_ledger_ratchets` fails on stale ledger entries from the user's uncommitted work (none names the new route). `test_route_auth_baseline.py` passes and needed no entry for the new route (it reuses `_require_platform_autonomy_control`); the user's file-mode change in that file is untouched.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-82-24 (backend never reads the on-call file; scan and JSON tests), T-82-25 (platform-only permission plus interactive session; 403 tests for tenant admin, viewer, Platform Support, API key) and T-82-26 (one pending request, 20 per sync, 24 h TTL) are mitigated as specified.

## User Setup Required

None. Migration 026 runs with the next backend start; until then the collections are created by their first insert and the code is only live after a backend restart (the user's step).

## Next Phase Readiness

82-05 can drain `outbox` and act on `testRequest` using the shapes above. 82-08 can reuse `selfheal.watchdog_state(heartbeat, now, selfheal.PROCESS_STARTED_AT)` and `selfheal.get_heartbeat(db)` for the dead-man switch and the health summary.

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-30*

## Self-Check: PASSED

All plan files exist on disk; commits `2346db073`, `ac00b34ea` and `138b3b770` are ancestors of HEAD.
