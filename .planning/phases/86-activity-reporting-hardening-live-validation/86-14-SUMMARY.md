---
phase: 86-activity-reporting-hardening-live-validation
plan: 14
subsystem: autonomous-ops-golive-gate
tags: [go-live, shadow-mode, test-organization, audit, fail-closed, copy-gate, runbook, autonomous-ops]
status: complete

requires:
  - phase: 86-07
    provides: golive.py gate (lift_blockers, lift_evidence, overview), go-live routes, the append-only structural test
  - phase: 86-10
    provides: docs/autonomous-ops-go-live.md and its open-decision stopgap
  - phase: 86-12
    provides: the Going live card that reads GET /golive (the new fields are additive)
provides:
  - backend/autonomous_ops/reporting/golive_test_org.py (current, mark, clear, AlreadyMarked)
  - POST and DELETE /api/platform/autonomous-ops/golive/test-organization
  - golive.lift_blockers exemption for the one marked organization, read fail closed
  - testOrganization on lift_evidence, on GET /golive and on each organization row
  - runbook steps that replace the database-flip stopgap
affects: [86-15]

actuals:
  tokens: 10000
  tasks: 2
  commits: 3
plan_head_before: 56452b5ecea4ed947de5a0ad89436b80f42f09b8
plan_head_after: bcd51236e5aba75ee127a36a1d115496acd4ab0c

tech-stack:
  added: []
  patterns:
    - one platform document with a fixed _id so "at most one" holds by construction (a second insert raises DuplicateKeyError)
    - the mark is read through golive_test_org.current inside a try; any failure means no exemption
    - the test-organization module never names the evidence collection, so the 86-07 structural allowed set is unchanged

key-files:
  created:
    - backend/autonomous_ops/reporting/golive_test_org.py
    - backend/tests/test_autonomous_ops_golive_test_org.py
  modified:
    - backend/autonomous_ops/reporting/__init__.py
    - backend/autonomous_ops/reporting/golive.py
    - backend/autonomous_ops_golive_endpoints.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts
    - docs/autonomous-ops-go-live.md

key-decisions:
  - "The exemption returns no reasons at all for the marked organization (no checks_missing, no_shadow_records, days_short, and no unreadable), so a failed shadow-records read never blocks it; every other organization keeps the unchanged D-15/D-16 gate."
  - "Clearing names the organization by tenantId and answers 404 when that organization is not the marked one (and when nothing is marked), 409 'Turn shadow mode back on for {name} first.' while its own shadow flag is not on; an unreadable settings document also refuses (only an explicit True clears)."
  - "lift_evidence always carries testOrganization (true or false) so the shadow_lifted audit event states which kind of lift it was."

requirements-completed: [GATE-09]

coverage:
  - id: D1
    description: "A Super Admin marks one ticked organization as the test organization by typing its exact name; wrong name 422, platform organization 409, unticked or unknown 404, a second mark 409 naming the current one; the mark is one fixed-id document"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_marking_with_the_exact_name_stores_the_mark_and_audits_it"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_a_second_mark_is_refused_and_names_the_current_organization"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_two_marks_racing_for_the_single_slot_leave_one"
        status: pass
    human_judgment: false
  - id: D2
    description: "The mark can be cleared only while that organization's own shadow flag is on; marked and cleared events go to the platform audit chain, and an audit failure is logged and never undoes the mark"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_clearing_works_only_while_the_organizations_shadow_flag_is_on"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_an_audit_failure_is_logged_and_never_undoes_the_mark"
        status: pass
    human_judgment: false
  - id: D3
    description: "The test organization lifts with no checks and no shadow records and its lift is audited with testOrganization true; any other organization with the same evidence still gets 409; after clearing, the organization is gated again"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_the_test_organization_lifts_with_no_checks_and_no_records_others_do_not"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_after_the_mark_is_cleared_the_organization_is_gated_again"
        status: pass
    human_judgment: false
  - id: D4
    description: "An unreadable mark exempts nobody (lift gated, overview shows no test organization)"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_an_unreadable_mark_exempts_nobody"
        status: pass
    human_judgment: false
  - id: D5
    description: "GET /golive shows testOrganization and a per-row testOrganization; canLift for the test organization follows its shadow flag"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_the_overview_shows_the_mark_and_flags_only_that_row"
        status: pass
    human_judgment: false
  - id: D6
    description: "Platform Support, Platform Billing, tenant roles and an API key are refused on POST and DELETE"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive_test_org.py#test_only_the_platform_owner_in_a_session_can_mark_or_clear"
        status: pass
    human_judgment: false
  - id: D7
    description: "The new module is scanned by the copy gate on both sides, never names the evidence collection (86-07 structural tests pass unchanged), and the runbook has the D-23 steps with no hand edit of autonomy_settings"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_golive.py#test_only_the_allowed_modules_name_the_evidence_collection"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
    human_judgment: false
  - id: D8
    description: "The runbook procedure reads correctly to an operator and works against the live server"
    requirement: GATE-09
    verification: []
    human_judgment: true
    rationale: "Wording and the live walk of checks 1, 2 and 5 are an operator judgment; nothing was run against the live server, restarted or published."

duration: ~25min
completed: 2026-11-13
---

# Phase 86 Plan 14: Go-live test organization (server side) Summary

**One Super Admin-marked test organization can leave shadow mode before the five live checks and the seven days, audited as a test-organization lift, while every customer organization keeps the full gate and an unreadable mark exempts nobody.**

## What was built

- **`golive_test_org.py` (53 lines):** `current` (find by the fixed id, no `_id`), `mark` (`insert_one` with `_id: "current"`, so a second mark raises `DuplicateKeyError`, translated to `AlreadyMarked` carrying the existing mark) and `clear` (deletes only `{_id: "current", tenantId}`). Raw handle, explicit fields, no mention of the evidence collection or `GOLIVE_CHECKS`.
- **`reporting/__init__.py`:** `GOLIVE_TEST_ORG = "autonomy_golive_test_org"` and `TEST_ORG_DOC_ID = "current"`.
- **`golive.py`:** `_read` also returns whether the organization is the marked one (the mark read in a try, failure means no); `_reasons(..., exempt)` returns nothing for the exempt organization; `lift_evidence` adds `testOrganization`; `overview` adds the top-level `testOrganization {id, name, markedBy, markedAt}` (or null) and a per-row `testOrganization`. The file still only inserts, reads and indexes the evidence collection.
- **`autonomous_ops_golive_endpoints.py`:** `POST /test-organization` (201, `{tenantId, confirmName}`) and `DELETE /test-organization?tenantId=` with the same owner-permission and interactive-session dependencies; the organization is resolved from `tenants`, must be ticked (`sweep._ticked_tenants`) and not the platform organization; the typed name is compared after trimming; the audit events `autonomous_ops.golive_test_org_marked` and `..._cleared` go to the platform chain after the store and a failure is logged.
- **Runbook:** the "Open decision" database-flip paragraph is replaced by mark, lift, walk checks 1, 2 and 5, turn shadow back on, clear the mark; the lift section notes the exception; no `autonomy_settings` instruction remains; the five `Summary:` lines are byte-identical.
- **Copy gate:** `golive_test_org.py` is listed once in the JSON list, the pytest `EXPECTED_FILES` and the vitest `EXPECTED_FILES`.

## TDD

- **RED** (`156cbe2c4`): 16 tests; 15 failed on the planned assertions (404 where 201 expected, missing `testOrganization` key, 404 instead of 403) and 1 (the evidence-collection naming test) passed. A constants-only edit and an unimplemented module skeleton were committed with the tests so the failures are assertion failures, not import errors. Semantic assessment: every failure was the behavior under test being absent.
- **GREEN** (`954e17341`): 16 passed; the combined verify set (golive_test_org, golive, endpoints_writes, ledger, catalogue slice, plus structural and copy suites) passed 147 of 147 on the private mongod at 27998, 0 skipped.
- No REFACTOR commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - adapt to real code] Copy-gate registration is redundant with the directory entry**
- **Found during:** Task 2
- **Issue:** `backend/autonomous_ops/reporting` is already in the copy gate's `directories` list, so `golive_test_org.py` was scanned the moment it existed.
- **Fix:** also listed the file explicitly once in each of the three files as the plan's acceptance criteria require; the frontend `FRONTEND_FILES` length assertion (24) is unaffected because the entry is a backend path.
- **Commit:** bcd51236e

**2. [Plan gap] Clear of an organization that is not the marked one**
- **Issue:** the plan did not say what DELETE answers for an unmarked organization.
- **Fix:** 404 "That organization is not the test organization." and nothing changes; also covers "nothing is marked".
- **Commit:** 954e17341

**3. [Scope note] test_catalogue_slice_autonomous_ops.py not edited**
- Its route assertion is a superset check (`>=`) and it passes with the two new routes present; adding them to the expected set was left out because the file is not in the plan's `files_modified`.

**Total deviations:** 1 adaptation, 1 plan gap filled, 1 scope note. **Impact:** none on D-23 behavior.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model: the two new routes are platform-owner, interactive-session only (T-86-14-01) and covered by the role-matrix test.

## Issues Encountered

None. Nothing was run against 127.0.0.1:27017; no restart, publish or push; no real tenant was marked or lifted. The Going live card (86-15) does not yet show or set the mark, so until then the mark is set through the API route; the runbook says so.

## Self-Check: PASSED

Both created files exist; commits 156cbe2c4, 954e17341 and bcd51236e are on HEAD; the working tree has no leftover changes to this plan's files.
