---
phase: 82-platform-self-healing-scheduled-retention
plan: 01
subsystem: infra
tags: [watchdog, fastapi, mongodb, autonomous-ops, ledger, bearer-token, loopback]

requires:
  - phase: 81-autonomous-ops-safety-core
    provides: autonomy_actions ledger (kind rows, ledger._mirror audit chain), platform stop in settings.platform_stop, Activity list views, ACTV-08 banned-term lists
provides:
  - "POST /api/internal/watchdog/sync and /results: loopback-only, bearer-token routes (frozen sync contract v1)"
  - "backend/autonomous_ops/selfheal.py: closed event vocabulary, heartbeat and snapshot singletons, idempotent event ingest, frozen sync response"
  - "backend/autonomous_ops/health_messages.py: server-rendered words, rule ids and chips for every platform-health event kind"
  - "ledger.record_platform_health: kind platform_health rows at platform-admin scope, id PH-<event id>"
  - "views.list_page include_platform_health leak guard and PlatformBucket platform_health filter with counts.platform_health"
  - "migration 025 (platform_health index)"
affects: [82-02 watchdog sync client, 82-07 outbox and test alert, 82-08 platform health status, 82-10 retention run rows]

actuals:
  tokens: 13200
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Watchdog reports structured fields only; the backend renders every user-visible word from a closed table"
    - "Platform-scope rows get their own kind and are excluded from every tenant query by default (opt-in flag on the platform route only)"
    - "Singleton status documents with fixed _id (heartbeat, snapshot) in platform_health"

key-files:
  created:
    - backend/watchdog_ingest_endpoints.py
    - backend/autonomous_ops/selfheal.py
    - backend/autonomous_ops/health_messages.py
    - backend/migrations/025_platform_health.py
    - backend/tests/test_platform_health_sync.py
    - backend/tests/test_platform_health_activity.py
    - backend/tests/test_platform_health_migration.py
  modified:
    - backend/autonomous_ops/ledger.py
    - backend/autonomous_ops/views.py
    - backend/autonomous_ops_platform_endpoints.py
    - backend/router_registry.py
    - backend/tests/test_route_auth_baseline.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "Access check order is 403 (non-loopback or proxy header), then 503 (no credential), then 401 (wrong bearer): a remote caller learns nothing about whether a token is provisioned"
  - "An unreadable platform stop is reported to the watchdog as active (fail closed), matching the gate's treatment of an unreadable stop"
  - "A re-sent event is acknowledged again in acceptedEventIds so the watchdog can clear its spool; an event the ledger could not record is left out of both accepted and dropped so it is re-sent"
  - "retention_run chip defaults to healthy when params.ok is absent (restart and test_alert default to critical)"
  - "Backend-written kinds use source Platform; retention_confirmed uses Super Admin; every watchdog kind uses Watchdog"

patterns-established:
  - "Closed vocabulary: WATCHDOG_EVENT_KINDS vs BACKEND_EVENT_KINDS, PARAM_KEYS scalar-only, strings capped at 300 characters with control characters removed"
  - "Request body read in a bounded stream (413 above 256 KB) before pydantic validation (422)"

requirements-completed: [HEAL-07, HEAL-05]

coverage:
  - id: D1
    description: "A watchdog event posted with the right token becomes exactly one platform_health ledger row (PH-<event id>), idempotent on re-send, with heartbeat firstSeenAt set once and lastSeenAt advancing"
    requirement: HEAL-07
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_sync.py#test_accepted_event_becomes_one_platform_health_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_platform_health_sync.py#test_resending_the_same_event_creates_no_second_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_platform_health_sync.py#test_first_seen_is_set_once_and_last_seen_advances"
        status: pass
    human_judgment: false
  - id: D2
    description: "Sync auth: 503 without credential, 401 wrong or missing bearer, 403 for non-loopback client or proxy headers; routes unreachable through nginx"
    requirement: HEAL-05
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_sync.py#test_no_credential_answers_503 / test_wrong_or_missing_bearer_answers_401 / test_proxy_headers_answer_403_even_with_the_right_token / test_non_loopback_client_answers_403"
        status: pass
    human_judgment: false
  - id: D3
    description: "Closed vocabulary and caps: unknown or backend-only kinds dropped and counted, 50 events (422), 256 KB (413), 300-character strings, unknown params dropped, event time clamped"
    requirement: HEAL-07
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_sync.py#test_unknown_and_backend_only_kinds_are_dropped_and_counted / test_51_events_answer_422 / test_body_over_256_kb_answers_413 / test_error_strings_are_capped_at_300_characters_and_unknown_params_dropped / test_event_time_is_clamped_so_a_replayed_spool_keeps_its_order"
        status: pass
    human_judgment: false
  - id: D4
    description: "Super Admin platform list shows platform_health rows under all and platform_health with counts.platform_health; tenant admin, viewer and Platform Support (including tenantId=platform-admin) never receive them (PROH-82-06)"
    requirement: HEAL-07
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_activity.py (14 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Migration 025 is idempotent; route-auth baseline and ACTV-08 copy lists (JSON, pytest, vitest) cover the new routes and message modules"
    verification:
      - kind: integration
        ref: "backend/tests/test_platform_health_migration.py; backend/tests/test_route_auth_baseline.py; backend/tests/test_autonomous_ops_copy.py; src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
    human_judgment: false
  - id: D6
    description: "The watchdog contract wording (event labels, reason and result text, chips) reads correctly on the Super Admin screen"
    verification: []
    human_judgment: true
    rationale: "Copy quality and the HH:MM display (rendered in UTC without a zone label, as the UI-SPEC wording is verbatim) need a person once the Phase 82 UI plans render these rows"

duration: 17min
completed: 2026-10-27
status: complete
plan_head_before: 636f16e915dc3e09feeb2ce2b558880c7551cf38
plan_head_after: 1500784530cd7f0353f9249de56a2d7181acea00
commits: 3
---

# Phase 82 Plan 01: Watchdog ingest and platform-health ledger rows Summary

**Token-authenticated loopback endpoint that stores the watchdog's heartbeat and snapshot and turns its events into server-worded `platform_health` ledger rows visible only to the Super Admin**

## Performance

- **Duration:** 17 min
- **Started:** 2026-10-27T07:21:51Z
- **Completed:** 2026-10-27T07:39Z
- **Tasks:** 3
- **Files modified:** 15 (7 created, 8 modified)

## Accomplishments

- `POST /api/internal/watchdog/sync` and `/results` accept only a loopback client with no proxy header and the exact bearer token from the systemd credential (`hmac.compare_digest`, read from `$CREDENTIALS_DIRECTORY/omni-watchdog-token` on every call).
- Each valid watchdog event becomes one `autonomy_actions` row (`kind: platform_health`, `tenantId: platform-admin`, `id: PH-<event id>`), mirrored once to the platform-admin audit chain; re-sends are acknowledged but never duplicated.
- `health_messages.render` produces every user-visible word (label, reason, result, rule id, chip) from the UI-SPEC section 8 table; the watchdog can send no free text beyond a 300-character error string.
- Leak guard: `list_page` excludes `platform_health` for every tenant id (including `platform-admin` named by Platform Support) unless the platform route opts in; `bucket_of` classifies these rows before any state lookup (Pitfall 4); `BUCKET_STATES` is untouched.
- Migration 025, route-auth baseline entries and the ACTV-08 lists are in place.

## Frozen sync contract (as built)

Request `POST /api/internal/watchdog/sync`, `Authorization: Bearer <token>`, body `{v, host, sentAt, services, certs, disks, oncall, stop, events, delivered}` (unknown top-level keys ignored; at most 50 events, 32 services/certs/disks, 256 KB).

Response, always exactly this shape:

```json
{"stop": {"active": false, "scope": null, "pressedAt": null},
 "acceptedEventIds": ["<event id>"], "droppedEvents": 0, "outbox": [], "testRequest": null}
```

When a platform stop is on: `stop = {"active": true, "scope": "platform", "pressedAt": "<ISO>"}`. `POST /results` answers `{"ok": true}` (82-07 acts on its contents). Error codes: 403 non-loopback or proxy header, 503 no credential (or storage unavailable), 401 wrong or missing bearer, 413 body over 256 KB, 422 invalid body or more than 50 events.

Rung numbering used by `health_messages` (82-02 must send these): certificates 1 to 4 = 30d, 14d, 7d, 1d/expired; disk 1 to 3 = 80, 90, 95 percent; forecast 1 to 3 = 14, 7, 1 days. Chip by rung: 1 notice, 2 warning, 3 and above critical.

## Task Commits

1. **Task 1: Tracer - sync stores heartbeat and one server-worded platform-health row** - `30b6def1b` (feat)
2. **Task 2: Platform-health rows at platform scope only (bucket, counts, leak guard)** - `dbaacb0cd` (feat)
3. **Task 3: Ingest hardening, migration 025, drift lists** - `150078453` (feat)

**Plan metadata:** committed separately (docs: complete plan).

## Files Created/Modified

- `backend/watchdog_ingest_endpoints.py` - router, `_require_watchdog_token`, bounded body read, `SyncBody`/`ResultsBody`
- `backend/autonomous_ops/selfheal.py` - event enums, `PARAM_KEYS`, heartbeat/snapshot store, `ingest_events`, `sync_response`, `ensure_indexes`
- `backend/autonomous_ops/health_messages.py` - `EVENT_LABELS`, `RULE_IDS`, `render`, `chip_for`
- `backend/autonomous_ops/ledger.py` - `record_platform_health` with event-time clamp
- `backend/autonomous_ops/views.py`, `backend/autonomous_ops_platform_endpoints.py` - bucket, row presentation, `include_platform_health`, `PlatformBucket`
- `backend/migrations/025_platform_health.py`, `backend/router_registry.py` (not in `_REQUIRED_ROUTERS`)
- Tests: `test_platform_health_sync.py`, `test_platform_health_activity.py`, `test_platform_health_migration.py`; lists in `test_route_auth_baseline.py`, `shared/autonomous-ops-banned-terms.json`, `test_autonomous_ops_copy.py`, `autonomousOpsCopy.test.ts`

## How the tests force a loopback client

`httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))` (a different tuple for the non-loopback and `::1` cases), with `CREDENTIALS_DIRECTORY` monkeypatched to a tmp dir holding `omni-watchdog-token`. No module-level loopback set is patched.

## Route walker

The walker did not recognise `_require_watchdog_token` (it is not in the permission patterns), so two entries were added to `REVIEWED_UNAUTHENTICATED` under the "credential checked inside the handler" group. Only those two lines were staged; the user's file-mode change in that file stays uncommitted.

## Decisions Made

See key-decisions above. Also: the Task 3 tests were authored first and kept out of the Task 1 commit so each commit is self-consistent; the caps were then added in Task 3 as the plan sequences them.

## Deviations from Plan

None - plan executed exactly as written. (Test-environment note: see Issues Encountered.)

## Issues Encountered

- **Test database:** the environment forbids writes to the live MongoDB, and `mongo_db` normally uses the live server's port. A private, temporary `mongod` (port 27999, data in the scratchpad, started and stopped by this run, never a service) was used through `MONGO_TEST_URL`; it was shut down afterwards. All real-Mongo tests ran against it.
- **Pre-existing failure, not mine:** `backend/tests/test_catalogue_route_parity.py::test_ledger_ratchets` fails on stale/slack ledger entries for `audit_program_endpoints`, `compliance_*`, `export_report_endpoint`, `reporting_endpoints`, `route_aliases`, `scheduled_reports_endpoints`, `soa_endpoints` (the user's uncommitted work). No watchdog route appears in it. The other 480+ Autonomous Ops, platform-health, copy and route-baseline tests pass (`-k "autonomous_ops or autonomy or platform_health"`: 481 passed; vitest copy test 18 passed).

## Known Stubs

None. `outbox` is always `[]` and `testRequest` always `null` by design (frozen shape); 82-07 fills them. `/results` ignores its content until 82-07.

## Threat Flags

None beyond the plan's register (T-82-01 to T-82-05 all mitigated as specified).

## User Setup Required

None in this plan. The credential `omni-watchdog-token` (systemd `LoadCredential=`) is provisioned by a later plan's install checklist; until it exists the routes answer 503, so nothing is exposed.

## Next Phase Readiness

82-02 can implement the sync client against the frozen contract above. 82-07, 82-08 and 82-10 reuse `selfheal`, `health_messages.render(kind, params, host, at)` and `ledger.record_platform_health` (backend kinds: pass an `actor` for `retention_confirmed`).

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-27*

## Self-Check: PASSED

All 15 plan files exist on disk; commits `30b6def1b`, `dbaacb0cd` and `150078453` are ancestors of HEAD.
