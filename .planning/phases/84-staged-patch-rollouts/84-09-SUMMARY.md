---
phase: 84-staged-patch-rollouts
plan: 09
subsystem: api
status: complete
tags: [patch-rollout, rollouts-tab, payloads, routes, catalogue, mongodb, python, fastapi]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-03 approval lines and halt; 84-05 maintenance windows; 84-06 rings.save, start.preflight, start.start_rollout and their exceptions; 84-08 ring health rows; 84-02 messages and services/patchRollouts/types.ts"
provides:
  - "rollout/views.py - build_caller, rollout_page, rollout_card, ring_view, host_rows, halt_block, window_strip, rings_summary (the RolloutPage / RolloutCard shapes of types.ts)"
  - "rollout/picker.py - pending_patches (50 per page, search), draft (vulnerability suggestion to name and patch ids, stores nothing), rings_settings"
  - "backend/patch_rollout_endpoints.py - GET/POST /api/patch-rollouts, GET /window, /pending-patches, /draft, /{id}, GET/PUT /rings, POST /preflight, mounted under patchManagement with PATCH_GUARD"
  - "windows.when_text / day_text / clock_text - one date format for the screens and the Start check"
  - "ring field healthCounts {reported, failed} written by the controller beside the health rows"
affects: [84-10, 84-12, 84-13, 84-14, 84-16, 84-17, 84-18]

requirements-completed: [PTCH-01, PTCH-04, PTCH-05, PTCH-07]

actuals:
  tokens: 27500
  tasks: 3
  commits: 5
commits: 5
plan_head_before: 0b0044aa58d3a05280af7898762afea3045f633d
plan_head_after: c32c84fe63400b02d22fa1b6c2aa76034a814cd0

tech-stack:
  added: []
  patterns:
    - "payload builders take a Context (zone, next window, group and service names) built once per page, so a card costs only its own computers"
    - "permissions are computed on the server into flags; the card carries canResume/canCancel/resumeBlockedReason and the page carries canStart/canManageRings/canOpenDecisions"
    - "a halt block counts a revert only from the computers' recorded states (reverted, not_reverted with the agent's reason, reverting)"

key-files:
  created:
    - backend/autonomous_ops/rollout/views.py
    - backend/autonomous_ops/rollout/picker.py
    - backend/patch_rollout_endpoints.py
    - backend/tests/test_patch_rollout_views.py
    - backend/tests/test_patch_rollout_endpoints.py
  modified:
    - backend/autonomous_ops/rollout/messages.py
    - backend/autonomous_ops/rollout/windows.py
    - backend/autonomous_ops/rollout/start.py
    - backend/autonomous_ops/rollout/controller.py
    - backend/router_registry.py
    - backend/catalogue_mounts_devices.py
    - shared/catalogue-access.json
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - backend/tests/test_patch_rollout_messages.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "Pending-patch listing and the draft live in rollout/picker.py, not views.py, to keep every file under 500 lines (views.py is 444)"
  - "Reads and writes sit behind PATCH_GUARD, whose sign-in is get_current_user (session); an API key therefore never reaches these routes in production, and the routes still refuse a key on writes (_require_interactive_session) as a second line"
  - "ring detail for a ring waiting for approval stays the state line; the viewer without access to Autonomous Ops gets waitingText 'Waiting for someone with access to Autonomous Ops.' and decisionsLink false"
  - "The failure-rate percentage is rounded up, so a share is never shown at or under the limit while it halts the ring (halt is failed*100 > limit*reported)"
  - "The first page of computers per ring is 25 rows, problems first (Failed, Not reverted), then Waiting, then by name"
  - "Preflight needs manage:patches (the guard treats POST as a write) but not a signed-in session; Start and PUT rings need both"

patterns-established:
  - "Time text for screens: windows.when_text(moment, zone) gives 'Sat 7 Nov, 03:00' in the tenant's zone; start.py now uses the same function"

coverage:
  - id: D1
    description: "The Rollouts tab list: cards ordered halted, waiting for approval, running, waiting for window, then finished newest first; finished older than 30 days not listed; 10 per page; attentionCount counts halted and waiting-for-approval"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_the_page_orders_halted_then_approval_then_running_then_window_then_finished_newest_first"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_a_finished_rollout_older_than_thirty_days_is_not_listed_and_the_page_pages"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every ring state and computer state reads in the UI-SPEC words, computers ordered problems first, health/failure/soak lines from the stored checks, simulation in the conditional, singular forms"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_each_ring_state_reads_the_way_the_ui_spec_table_says"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_each_computer_state_has_its_result_sentence"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_a_card_carries_every_key_of_the_card_type_and_every_ring_key_of_the_ring_type"
        status: pass
    human_judgment: false
  - id: D3
    description: "The halt block lists only reverts the computers recorded (3 reverted, 1 not reverted with the agent's reason); Resume is disabled with 'Wait for the revert to finish.' while a revert runs"
    requirement: PTCH-04
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_the_halt_block_counts_only_the_reverts_the_computers_recorded"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_a_revert_still_running_says_so_and_blocks_resume"
        status: pass
    human_judgment: false
  - id: D4
    description: "Flags come only from the server: a view-only person gets every flag false, a stop turns canStart off but not canManageRings, platform organization reads an empty page"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_a_view_only_person_gets_every_flag_false"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_a_view_only_person_reads_the_list_with_every_control_off_and_cannot_start_or_save"
        status: pass
    human_judgment: false
  - id: D5
    description: "Window strip open/closed/none in the organization's zone; pending-patch picker with search and paging; rings read and save with the UI-SPEC sentences"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views.py#test_the_window_strip_says_open_closed_or_none_in_the_organizations_zone"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_pending_patches_search_matches_the_id_or_the_title_and_pages_by_fifty"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_rings_save_and_read_back_and_a_bad_value_answers_the_sentence"
        status: pass
    human_judgment: false
  - id: D6
    description: "Start: 201 then listed first; no window answers 422 with the window row and claims nothing; two concurrent Starts give one 201 and one 409 already_in_rollout; the platform organization answers 409; API keys and other organizations are refused"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_two_starts_at_the_same_moment_give_one_rollout_and_one_already_in_rollout"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_with_no_window_preflight_says_so_without_blocking_the_call_and_start_answers_422_with_the_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_an_api_key_holding_manage_patches_still_cannot_start_a_rollout_or_save_rings"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_another_organizations_rollout_and_suggestion_answer_not_found_and_the_tenant_query_is_refused"
        status: pass
    human_judgment: false
  - id: D7
    description: "D-11 draft from a vulnerability suggestion: keeps the patches still pending on its host, counts the dropped ones, stores nothing (PROH-84-01)"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_endpoints.py#test_a_draft_keeps_the_patches_still_pending_on_the_host_and_stores_nothing"
        status: pass
    human_judgment: false
  - id: D8
    description: "/api/patch-rollouts is registered under patchManagement, mounted with PATCH_GUARD; route parity, auth baseline, devices slice and the copy gate (Python and vitest) pass with the new file listed"
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_route_parity.py, test_route_auth_baseline.py, test_catalogue_slice_devices.py, test_autonomous_ops_copy.py"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
    human_judgment: false

duration: about 1h 45m including a usage-limit pause (start time not recorded)
completed: 2026-11-06
---

# Phase 84 Plan 09: Rollouts Tab API Summary

**The Rollouts tab API: server-written cards and page (ring chips, detail lines, health, computer rows, honest halt block, flags decided on the server), window strip, patch picker, preflight/Start/rings routes and the vulnerability-suggestion draft, all under the Patching catalogue.**

## Performance

- **Duration:** about 1h 45m (start not recorded; a usage-limit pause is included)
- **Completed:** 2026-11-06
- **Tasks:** 3 (all `tdd="true"`)
- **Files:** 5 created, 11 modified (backend and shared config; one vitest list line)

## Accomplishments

- `views.rollout_page` / `rollout_card` build exactly the keys of `RolloutPage`, `RolloutCard`, `RingView`, `HostRow`, `HaltBlock`, `WindowStrip` and `RolloutFlags` (a test reads the interfaces out of types.ts and asserts every key is present). Sentences all come from `messages`; the Context shares the zone, next window, group and watched-service names across a page.
- Computers: Failed and Not reverted first, then Waiting, then by name; each state has its Result sentence; an unknown not-reverted reason reads "Not reverted. The patch is still installed." and never as reverted. The halt block counts reverts only from recorded computer states.
- Flags: `canStart` (manage:patches, signed-in session, not the platform organization, no tenant or platform stop), `canManageRings` (same, allowed during a stop), `canOpenDecisions` (view:autonomous_ops and the screen enabled for the organization), `canResume`/`canCancel` (manage and halted; Resume false with "Wait for the revert to finish." while a revert runs).
- Routes: list, window, pending-patches, rings (read, save), preflight, start, draft, one card; static paths resolve before `/{rollout_id}`; `PreflightBlocked` answers 422 `{detail, rows}`, a lost claim race 409 `{code: already_in_rollout}`, a ring error 422 with the UI-SPEC sentence, the platform organization 409 on writes and an empty page on reads.
- The draft returns the suggestion's patches still pending on its computer plus the count dropped and writes nothing (collection counts compared before and after).

## Task Commits

TDD plan. Task 1 and Task 2 have RED then GREEN commits; Task 3 tests passed on arrival.

1. **Task 1 RED** - `092371dd2` (test): 38 failing tests against a skeleton views.py
2. **Task 1 GREEN** - `1dd87ea3b` (feat): payload builders, messages, window time helpers, `healthCounts`
3. **Task 2 RED** - `27e56dc1f` (test): route tests, registrations (router, PATCH_GUARD, catalogue route, copy-gate lists), empty router
4. **Task 2 GREEN** - `88e9aa3ef` (feat): picker.py and the routes
5. **Task 3** - `c32c84fe6` (test): permission, isolation and start-flow tests

## Decisions Made

See `key-decisions` above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] The ring stores `healthCounts`**
- **Found during:** Task 1 (failure-rate line)
- **Issue:** The card's "{f} of {n} computers failed" line needs the numbers the gate judged. `health_rows` stores only per-signal k and n, so a halt on an inventory failure would have read "0 of 10 failed" next to a halt.
- **Fix:** `controller._check` stores `healthCounts {reported, failed}` (the same sets `ring_verdict` uses) next to `health`; the view falls back to host states when absent.
- **Files modified:** backend/autonomous_ops/rollout/controller.py
- **Commit:** 1dd87ea3b

**2. [Rule 3 - Blocking] 500-line cap: patch picker and draft in `picker.py`**
- views.py is 444 lines; adding the picker, draft and rings payload would pass 500, so they live in `rollout/picker.py` (115 lines, in the already-scanned copy-gate directory). Commit 88e9aa3ef.

**3. [Rule 3 - Blocking] One date format**
- `windows.when_text/day_text/clock_text` added; `start._when` now calls it, so the Start dialog and the cards cannot drift. Commit 1dd87ea3b.

**4. [Rule 3 - Blocking] Messages added and one pin updated**
- Added WINDOW_STRIP, RINGS_SUMMARY, DRAFT_NAME, HOST_RESULT["reverting"], NOT_REVERTED_OTHER, REVERT_SUMMARY["could_not_other"] and API_DETAIL["suggestion_not_found"]. `test_patch_rollout_messages.py` pinned the API_DETAIL key set, so it now lists the new key. Commits 1dd87ea3b, 88e9aa3ef.

**5. [Plan text vs messages.py] Revert line wording**
- The plan example ends the singular could-not line with "The patch is still installed."; `REVERT_SUMMARY` (fixed by UI-SPEC in 84-02) says "The patch is still installed on it." / "on them.". The view uses messages.py, as the plan says no sentence is written in views. 84-13 tests of this line should expect the messages.py wording.

**6. [Plan contract note] PATCH_GUARD authenticates with `get_current_user`**
- The plan says reads go through `get_current_user_or_api_key`. The Patching guard uses the session sign-in, so a key cannot reach these routes at all; the routes still use `_require_interactive_session` on writes. Tests override both sign-in dependencies.

**Total deviations:** 1 missing-critical, 3 blocking, 2 notes. **Impact:** none on the plan's truths.

## Issues Encountered

- `seed_window` stores timeZone "UTC", so the strip reports `timeZone: "UTC"` (not null) in tests; null is returned only when the organization has no zone saved (covered by a separate test).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model: T-84-29 (every query filters the tenant; foreign rollout and suggestion ids 404, `tenantId` refused for tenant roles), T-84-30 (manage:patches plus signed-in session on Start and rings; key refused), T-84-31 (strict bodies with length caps; ids pass `installable_patch_id` in start), T-84-32 (flags computed on the server) are implemented and tested. PROH-84-01: the draft route stores nothing and only `POST /api/patch-rollouts` creates a rollout.

## User Setup Required

None. Nothing was deployed, restarted, published or pushed; the private test mongod (port 27998) was stopped. The new router loads on the next backend restart, which is the user's.

## Next Phase Readiness

- 84-10 can use `rollout.views.build_caller` and `Context`; 84-12/14/17/18 read the payload shapes and routes above.
- 84-13 fills the revert fields the halt block already reads: host states `reverting`, `reverted`, `not_reverted` with `notRevertedReason`, optional `revertedAt` and `revertRebootNeeded`.
- 84-16 adds `closesAt`, `neverReachedCount`, `cancelledAt` and the resume/cancel routes; the card already reads those fields.

## TDD Gate Compliance

RED `092371dd2` / GREEN `1dd87ea3b` (Task 1) and RED `27e56dc1f` / GREEN `88e9aa3ef` (Task 2). RED was a skeleton module plus tests, so every RED failure was an assertion or a missing payload key on the planned behavior (38 of 38; 9 of 10, the tenth being a 404 that the empty router also gives). The `gsd_run check tdd-red-evidence` classifier was not run (pytest console output is not a supported report format; the plan is `type: execute`). Task 3 has no RED commit: its behaviors were delivered by Task 2's routes and the 84-06 Start, so the tests passed on arrival; the concurrency test was re-run four times without a failure.

## Verification

- Final run on a private mongod: all `test_autonomous_ops_*.py`, `test_patch_rollout_*.py`, `test_catalogue_slice_devices.py`, `test_catalogue_route_parity.py`, `test_route_auth_baseline.py`: 1403 passed, 0 skipped (8 min 1 s). `npx vitest run src/__tests__/autonomousOpsCopy.test.ts`: 23 passed. ruff clean.
- Acceptance: views.py 444 lines, patch_rollout_endpoints.py 249 (both under 500); `/api/patch-rollouts` count in catalogue-access.json 1; `patch_rollout_endpoints` in catalogue_mounts_devices.py 1 and router_registry.py 1; 21 `def test_` in test_patch_rollout_endpoints.py (at least 8); the views test asserts each key of RolloutCard.

## Self-Check: PASSED

- Created files exist: views.py, picker.py, patch_rollout_endpoints.py, both test files; commits 092371dd2, 1dd87ea3b, 27e56dc1f, 88e9aa3ef, c32c84fe6 are ancestors of HEAD.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
