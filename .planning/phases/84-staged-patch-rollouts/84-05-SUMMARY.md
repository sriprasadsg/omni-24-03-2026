---
phase: 84-staged-patch-rollouts
plan: 05
subsystem: maintenance-windows
tags: [maintenance-windows, time-zone, zoneinfo, change-management, tenant-isolation, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: rollout/windows.py (load, parse_window, occurrences, is_open, next_open) from 84-01
provides:
  - zone-aware, typed maintenance window storage with one IANA time zone per tenant
  - PUT /api/maintenance/windows/{id}, GET/PUT /api/maintenance/time-zone, GET /api/maintenance/status
  - GET /api/changes/maintenance-windows (read-only list for Change Management)
  - window sentences in rollout messages.VALIDATION (declared once for the Settings screen plans)
affects: [84-06, 84-12, 84-13, 84-22]

actuals:
  tokens: 22000
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "one stored window shape (startTime/endTime/daysOfWeek ISO/startsAt/endsAt + tenant zone); reading and open/closed maths stay in rollout/windows.py"
    - "a typed pydantic body with extra=ignore; the tenant comes from get_tenant_id() only; every query filters tenantId on the raw handle"
    - "a whole-document replace on edit so the fields of an old-shape row cannot linger beside the new ones"

key-files:
  created:
    - backend/tests/test_maintenance_windows.py
  modified:
    - backend/maintenance_service.py
    - backend/maintenance_endpoints.py
    - backend/change_management_endpoints.py
    - backend/autonomous_ops/rollout/messages.py
    - backend/skill_handlers_queries.py

key-decisions:
  - "Window sentences (name, repeats, days, same time, 24 hours, end before start, window limit, time zone) were not in messages.VALIDATION; they were added there once so 84-12 reads the same wording"
  - "A stored zone always wins; a body timeZone is only used (and stored) when the tenant has none, so a zone change goes through PUT /time-zone only"
  - "list_windows returns scheduleText (short, for Settings cards) and fullScheduleText (with repeat, days and zone); Change Management maps fullScheduleText to its scheduleText"
  - "At most 50 windows per tenant (422 with a sentence), so the create route cannot grow a collection without bound"

patterns-established:
  - "Texts are built with fixed English day and month names, never the process locale"

requirements-completed: [PTCH-05]

coverage:
  - id: D1
    description: "Windows are stored in the tenant's zone, a window past midnight is open the next morning and closed at its end, the Saturday-only window is open on a Saturday, and the New York spring-forward night is 2 hours long"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_weekly_window_past_midnight_stores_the_zone_and_opens_in_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_saturday_only_window_is_open_on_a_saturday_not_a_friday_or_sunday"
        status: pass
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_a_new_york_window_is_two_hours_long_on_the_spring_forward_night"
        status: pass
    human_judgment: false
  - id: D2
    description: "Typed create and edit refuse every bad body with the UI-SPEC sentence; tenantId and unknown fields are ignored; the first window without a stored zone needs a real timeZone"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_a_bad_window_is_refused_with_the_screen_sentence"
        status: pass
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_a_tenant_id_in_the_body_is_ignored_and_other_fields_are_not_stored"
        status: pass
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_the_first_window_without_a_stored_zone_needs_a_time_zone"
        status: pass
    human_judgment: false
  - id: D3
    description: "Edit, delete and list are tenant-scoped (another tenant's id answers 404); the time zone must be in zoneinfo.available_timezones()"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_edit_changes_the_callers_window_and_another_tenant_gets_404"
        status: pass
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_the_time_zone_is_stored_per_tenant_and_must_be_a_real_zone"
        status: pass
    human_judgment: false
  - id: D4
    description: "Legacy callers (is_in_maintenance_window, GET /check) agree with windows.is_open, and every saved window round-trips through windows.load for daily and weekly in a non-UTC zone"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_legacy_callers_answer_from_the_zone_aware_maths"
        status: pass
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_every_saved_window_round_trips_through_load_and_is_open"
        status: pass
    human_judgment: false
  - id: D5
    description: "Change Management lists the caller's windows only, read-only (GET), in the ChangeWindowRow shape"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_maintenance_windows.py#test_change_management_lists_only_the_callers_windows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_maintenance_windows.py#test_the_change_management_route_has_no_write_verb"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-06
status: complete
plan_head_before: 11d9db3ae98497833c8e24c9ecdc487d1a48ea52
commits: 3
plan_head_after: bb4d3544800d35bde5e7b2b15d8a258ad1b0b22e
---

# Phase 84 Plan 05: Maintenance Windows in the Tenant's Time Zone Summary

**Typed, zone-aware maintenance windows (one IANA zone per tenant, ISO weekdays, past-midnight and daylight-saving correct) with tenant-scoped create, edit, delete, status and time-zone routes, plus a read-only window list for Change Management.**

## Performance

- **Duration:** about 10 min
- **Started:** 2026-11-06T15:02Z
- **Completed:** 2026-11-06T15:12Z
- **Tasks:** 2
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments

- Windows are stored in one shape and read through the 84-01 `rollout/windows.py` maths, so the Settings screen, `deployment_service` (via `is_in_maintenance_window`), `GET /check` and the rollout controller all answer from the same code. The old UTC/weekday-off-by-one/never-matching-overnight maths is gone (research C7).
- `POST /windows` and `PUT /windows/{id}` take a typed `WindowBody`; the raw-dict create body is removed. Edit is a whole-document replace, so converting an old-shape row cannot leave its legacy fields behind.
- `GET /windows` returns each window with `scheduleText`, `fullScheduleText`, `nextText` and `openNow` in the tenant zone; `GET /status` returns open, closed or none with the UI-SPEC wording and the zone.
- `GET /api/changes/maintenance-windows` returns `[{id, name, scheduleText, openNow, nextText}]` for the caller's tenant (`view:security`, GET only), declared before `/{change_id}` so the path is not read as a change id.
- 29 new tests on a real private mongod; the 84 rollout suites, `test_catalogue_route_parity` and `test_route_auth_baseline` still pass (193 and 128 passed, 0 skipped).

## Task Commits

1. **Task 1 RED: tests for typed zone-aware windows and the Change Management list** - `b74334478` (test)
2. **Task 1 GREEN: zone-aware typed maintenance windows** - `92c431f6c` (feat)
3. **Task 2: Change Management lists the windows, read-only** - `bb4d35448` (feat)

**Plan metadata:** the docs commit following this summary.

## Files Created/Modified

- `backend/maintenance_service.py` - WindowBody, WindowError, WindowNotFound, zone check, validation, create/update/list/delete, status, `is_in_maintenance_window` (295 lines)
- `backend/maintenance_endpoints.py` - POST/PUT/GET/DELETE windows, GET/PUT time-zone, GET status, GET check
- `backend/change_management_endpoints.py` - one GET route `maintenance-windows`
- `backend/autonomous_ops/rollout/messages.py` - 12 window and time-zone sentences added to `VALIDATION`
- `backend/skill_handlers_queries.py` - the chat `/maintenance` skill reads the new fields (falls back to the old ones)
- `backend/tests/test_maintenance_windows.py` - 29 tests

## Decisions Made

See `key-decisions`. 84-12 (the Settings screen) can take its inline sentences from `messages.VALIDATION` keys `window_*` and `time_zone`, and its schedule line from `scheduleText`. The Change Management screen plan takes `scheduleText` straight from the new route.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Window sentences were not in messages.VALIDATION**
- **Found during:** Task 1
- **Issue:** The plan says to raise errors "using messages.VALIDATION texts", but 84-02's `VALIDATION` only held the rollout and ring sentences.
- **Fix:** Added the UI-SPEC window and time-zone sentences to `VALIDATION` (plus three that the spec does not word: name over 60 characters, bad repeat value, bad start/end time, and the 50-window limit).
- **Files modified:** `backend/autonomous_ops/rollout/messages.py`
- **Commit:** 92c431f6c

**2. [Rule 2 - Missing critical functionality] Window count cap**
- **Found during:** Task 1
- **Issue:** The create route had no upper bound on windows per tenant.
- **Fix:** At most 50 windows; the 51st is refused 422 with a sentence. Covered by a test.
- **Commit:** 92c431f6c

**3. [Rule 1 - Bug caused by this change] Chat skill read the old window fields**
- **Found during:** Task 1 (grep for readers of `maintenance_windows`)
- **Issue:** `skill_handlers_queries.handle_maintenance` projected only `start_time`/`end_time`/`status`, so every window saved by the new shape would show `? -> ?`.
- **Fix:** It projects and shows the new fields first and falls back to the old ones.
- **Files modified:** `backend/skill_handlers_queries.py`
- **Commit:** 92c431f6c

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing critical, 1 bug). **Impact on plan:** none on the truths; all three tighten wording, bounds or consistency.

## Issues Encountered

None. `maintenance_service.py` and `maintenance_endpoints.py` were CRLF in the working tree and LF in the index (`eol=lf`); they were rewritten as LF, matching the index.

## Known Stubs

None. No UI is built in this plan (the Settings screen is 84-12; Change Management's component is a later UI plan).

## Threat Flags

None beyond the plan's threat model. T-84-16 (typed body, whitelisted fields, tenant from context), T-84-17 (every read/update/delete filters tenantId; foreign ids answer 404 for PUT and DELETE) and T-84-18 (only names in `zoneinfo.available_timezones()` are stored) are implemented and tested.

## User Setup Required

None. Nothing was deployed, restarted, migrated or published; no live database was touched; the private test mongod was stopped.

## Next Phase Readiness

- The Settings and Change Management UI plans can build on `/api/maintenance/*` and `/api/changes/maintenance-windows` as specified in UI-SPEC sections 8 and 9.
- Existing windows on live: 0, so no data migration is needed; any old-shape row stays readable through the 84-01 converter and is converted when edited.

## Self-Check: PASSED

- Created/modified files exist (`backend/tests/test_maintenance_windows.py`, `backend/maintenance_service.py`, `backend/maintenance_endpoints.py`, `backend/change_management_endpoints.py`); commits `b74334478`, `92c431f6c`, `bb4d35448` are ancestors of HEAD.
- Acceptance criteria re-run: `@router.put` count 2, `window_data: Dict` count 0, `maintenance-windows` count 1 in change_management_endpoints; the Saturday test asserts `daysOfWeek [6]` open on a Saturday and closed on Friday and Sunday.
- Plan verification: Task 1 command plus Task 2 command (maintenance windows, rollout tracer, catalogue route parity, route auth baseline) - 128 passed, 0 skipped; all `test_patch_rollout_*` and reconciler tests - 193 passed.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
