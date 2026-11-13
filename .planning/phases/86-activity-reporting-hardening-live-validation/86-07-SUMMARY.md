---
phase: 86-activity-reporting-hardening-live-validation
plan: 07
subsystem: autonomous-ops-golive
tags: [shadow-mode, go-live, audit, append-only, fastapi, pytest, autonomous-ops]
status: complete

requires:
  - phase: 86-01
    provides: reporting package constants (GOLIVE_CHECKS, GOLIVE_CHECK_IDS, SHADOW_DAYS_REQUIRED, NOTE_MIN, NOTE_MAX, SHADOW_STATE), ACTV-08 copy gate registration
provides:
  - reporting/golive.py (clock, ensure_indexes, record_check, latest_checks, observation, lift_blockers, lift_evidence, blocker_sentence, overview)
  - server-side lift gate inside PUT /api/platform/autonomous-ops/tenants/{id}/shadow (409 {detail, reasons})
  - audit events autonomous_ops.shadow_lifted, autonomous_ops.shadow_restored, autonomous_ops.golive_check_recorded
  - GET /api/platform/autonomous-ops/golive and POST /api/platform/autonomous-ops/golive/checks/{check_id}
  - autonomy_golive_checks in PROTECTED_COLLECTIONS, with a structural append-only test
affects: [86-09, 86-12]

actuals:
  tokens: 11034
  tasks: 2
  commits: 4
plan_head_before: ce9ca2182c637f03f953e36fb736d0b16051e0ac
plan_head_after: 8fc28791ae5c6c075f9bf9254477f3c15aed9c6e

tech-stack:
  added: []
  patterns:
    - one accessor (golive._checks) for an append-only evidence collection, enforced by an AST structural test with in-test controls
    - the gate runs in the route before the write (not in the UI), failing closed on any unreadable input
    - module clock seam (golive.clock) so a seven-day boundary can be tested to the second

key-files:
  created:
    - backend/autonomous_ops/reporting/golive.py
    - backend/autonomous_ops_golive_endpoints.py
    - backend/tests/test_autonomous_ops_golive.py
  modified:
    - backend/autonomous_ops_platform_endpoints.py
    - backend/autonomous_ops/__init__.py
    - backend/router_registry.py
    - backend/tests/test_autonomous_ops_ledger.py
    - backend/tests/test_autonomous_ops_endpoints_writes.py
    - backend/tests/test_catalogue_slice_autonomous_ops.py
    - backend/tests/test_autonomous_ops_copy.py
    - shared/autonomous-ops-banned-terms.json
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The lift gate lives in put_shadow itself and applies only when the organization's own flag is on and the request sets it false; a restore and a no-op lift skip it."
  - "Reasons are computed by one pure function over (checks recorded, observation) so the route gate and the Going live overview cannot disagree; a failed read of either input yields the unreadable reason."
  - "A no-op lift (own flag already off) writes no audit event; a restore always does."
  - "daysObserved is the floor of elapsed seconds over 86400 from the first shadow row (createdAt), clamped at 0; naive datetimes read back from Mongo are treated as UTC."
  - "The audit event for a lift carries daysObserved, wouldHaveDone and checksRecorded from a second read just after the flag change (lift_evidence), in the organization's own chain."

patterns-established:
  - "Structural rules written as functions over (path, source) so controls run on in-test sample strings"

requirements-completed: [GATE-09]

coverage:
  - id: D1
    description: "A lift is refused with 409 and plain reasons until five distinct checks are recorded and seven whole days have passed since the first shadow record; exactly 7 days passes, one second short is days_short 6; unreadable input fails closed"
    requirement: GATE-09
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_seven_days_to_the_second_and_one_second_short"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_lift_is_refused_with_nothing_recorded"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_an_unreadable_observation_fails_closed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Restoring shadow and lifting an already-lifted organization are never gated; the deployment-wide switch does not change the gate; lift and restore are audited and add no Activity row"
    requirement: GATE-09
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_restore_is_never_gated_and_lifting_a_lifted_organization_skips_the_gate"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_a_lift_and_a_restore_add_no_row_to_the_activity_list"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_the_deployment_wide_switch_does_not_change_the_gate"
        status: pass
    human_judgment: false
  - id: D3
    description: "Go-live checks are recorded append-only through owner-only, interactive-session-only routes with bounded input and an audit event; the overview lists the checks and every ticked organization"
    requirement: GATE-09
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_recording_a_check_stores_it_and_audits_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_only_the_platform_owner_in_a_session_reaches_the_golive_routes"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_golive.py#test_the_overview_lists_the_checks_and_every_ticked_organization"
        status: pass
    human_judgment: false
  - id: D4
    description: "The evidence collection is protected from retention and only golive.py (plus the constant and migration entries) may name it; no allowed module updates or deletes"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive.py#test_only_the_allowed_modules_name_the_evidence_collection"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive.py#test_no_module_of_the_allowed_set_updates_or_deletes"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_decision_records_sit_outside_every_retention_path"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-11-13
---

# Phase 86 Plan 07: Go-live gate Summary

**No organization can leave shadow mode through any route until five live checks are recorded and seven whole days of shadow records exist: the gate runs inside PUT /tenants/{id}/shadow (409 with plain reasons, fail closed), the evidence is an append-only protected collection behind one accessor, and both routes the Going live card needs are Super Admin and interactive-session only.**

## What was built

- **`reporting/golive.py` (184 lines):** `record_check` validates the id and a 10 to 500 character trimmed note and inserts a `GL-` record; `latest_checks` returns the newest record per check in fixed order; `observation` counts whole days from the first shadow row; `lift_blockers` returns reason dicts (`checks_missing`, `unreadable`, `no_shadow_records`, `days_short`); `blocker_sentence` turns them into the UI-SPEC sentences; `overview` builds the card payload from the sweep's ticked tenants. The module never updates, replaces or deletes.
- **Gate in `put_shadow` (323 lines):** when the flag is on and the request lifts it, `golive.lift_blockers` runs before `set_shadow`; a non-empty result is a 409 `{detail, reasons}` and nothing changes. After a change the route writes `autonomous_ops.shadow_lifted` (with daysObserved, wouldHaveDone, checksRecorded) or `autonomous_ops.shadow_restored` in the organization's chain; an audit failure is logged and the flag change stands.
- **`autonomous_ops_golive_endpoints.py` (81 lines):** GET overview and POST check record (201), both behind `_require_platform_autonomy_control` and `_require_interactive_session`; `check_id` is a `Literal` of the five ids, the note a `StringConstraints` bounded model. The audit event is written to `platform-admin`.
- **Protection and structure:** `autonomy_golive_checks` joined `PROTECTED_COLLECTIONS`; an AST structural test (docstrings and comments excluded) restricts naming of the collection and `GOLIVE_CHECKS` to four modules, keeps `_checks` private to golive.py and bans update, replace, delete, bulk-write, drop and rename calls in those modules, each rule with in-test controls.
- **Wiring:** router registered beside the retention routes; the catalogue slice test, route-auth baseline and the copy gate (JSON list plus both EXPECTED_FILES lists) include the new module.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | RED | 0af427d8f | test(86-07): add failing tests for the shadow lift gate and go-live records |
| 1 | GREEN | 9c064446e | feat(86-07): gate the shadow lift on five go-live checks and seven observed days |
| 2 | RED | 4eceda39a | test(86-07): add failing tests for the go-live routes and the append-only structural rules |
| 2 | GREEN | 8fc28791a | feat(86-07): add the platform go-live routes and register them |

## TDD Gate Compliance

RED then GREEN commits exist for both tasks, in order; no REFACTOR commit (nothing to clean up).

- **Task 1 RED:** 10 failed, 5 errors on the private mongod. `test_lift_is_refused_with_nothing_recorded`, `test_four_distinct_checks_are_not_five_...`, `test_restore_is_never_gated_...` (the lift-gate assertions answered 200 where 409 was planned), `test_only_the_platform_route_lifts_a_tenants_shadow_flag` (the new 409 assertion) and the ledger PROTECTED_COLLECTIONS assertion failed on their planned assertions. The tests that call `golive` directly, or pin its clock, failed with `ModuleNotFoundError` because the module did not exist yet; those are not assertion failures.
- **Task 2 RED:** the five route tests errored in the fixture on the missing `autonomous_ops_golive_endpoints` module (an import fault, not an assertion). The structural tests passed because Task 1 had already added `golive.py`; they are non-vacuous because their controls flag synthetic violations.
- **Semantic assessment:** the gate behaviour (409 vs 200) was RED on its real assertion; the module-absent failures were accepted as RED for new-module unit tests only. `gsd_run check tdd-red-evidence` was not run: pytest console output is not one of its supported report formats and no JUnit run was recorded. This is a process gap, noted rather than hidden.

## Verification

- Task 1 command: 136 passed, 0 skipped (golive, ledger, endpoints_writes, retention_job, endpoints, copy).
- Task 2 commands: 107 passed, 0 skipped (golive, catalogue slice, route auth baseline, copy, structural); `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` 23 passed.
- Plan-level: endpoints_writes, gate, stop: 78 passed, 0 skipped.
- Acceptance greps: lift_blockers 1, event names 2, `autonomy_golive_checks` in `__init__.py` 1, mutating-call grep 0, router/catalogue/banned-terms each 1, guards 3 and 3, `def overview` 1, `reporting/__init__.py` 2, `MUTATORS` 2. Line counts: platform endpoints 323 (under 340), golive.py 184 (under 300), test file 491.
- All backend runs used the private mongod at 127.0.0.1:27998 with MONGO_TEST_URL, MONGODB_URL and MONGO_URI all set; nothing touched 27017.

## Deviations from Plan

**1. [Rule 2 - Missing critical] Audit stub added to the existing shadow-lift test**
- **Found during:** Task 1
- **Issue:** `test_only_the_platform_route_lifts_a_tenants_shadow_flag` now reaches `audit_ledger.event` through the real route; unpatched it would write to whichever database the environment names.
- **Fix:** the test takes `monkeypatch` and stubs `audit_ledger.event` with an AsyncMock (plus the seeded evidence and the 409 assertion the plan asked for).
- **Files modified:** backend/tests/test_autonomous_ops_endpoints_writes.py
- **Commit:** 0af427d8f

**2. [Design addition] `lift_evidence` helper and a public `clock()` seam**
- The plan named the clock seam without a name and the audit fields without a source; `golive.clock` and `golive.lift_evidence` fill both. A no-op lift (own flag already off) writes no audit event because nothing changed; the plan was silent on it.

**Total deviations:** 1 auto-fixed (Rule 2), 1 design clarification. **Impact:** none on scope.

## Known Stubs

None.

## Threat Flags

None: both new routes and the gate are covered by T-86-15 to T-86-18.

## Issues Encountered

None. The sweep-based `overview` and the structural scan both ran against the full backend tree without special handling.

## Next Phase Readiness

86-09 can call `golive.ensure_indexes` from migration 035 (its entry in the allowed set is already held to the no-mutation rule); 86-12's Going live card reads GET /golive and posts to /golive/checks/{id}. Nothing was restarted, published or pushed, and no tenant's shadow mode was lifted.

## Self-Check: PASSED
