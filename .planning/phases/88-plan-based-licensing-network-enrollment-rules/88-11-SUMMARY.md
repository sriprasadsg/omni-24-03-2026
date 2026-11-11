---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 11
subsystem: licensing
tags: [migration, plans, seats, trials, allowed-networks, go-live, mongodb]
status: complete

requires:
  - phase: 88-02
    provides: licensing seat functions (license_of, DEFAULT_MAX_AGENTS, _direct_filter, EXEMPT_TENANT_ID)
  - phase: 88-03
    provides: screen_ceiling.seed_screens and shared/plan-screen-seed.json
  - phase: 88-05
    provides: network_rules (normalize_ip, network_of, entry, contains, MAX_NETWORKS), agent sourceIp
  - phase: 88-06
    provides: plan_trial.new_trial / consumed_trial
  - phase: 88-07
    provides: cross_tenant.ensure_indexes (the sparse hardware indexes; 88-09 added the cross_tenant_reports unique key index to the same function)
provides:
  - backend/migrations/034_plan_licensing.py (DESCRIPTION, up): plans seeded, plan names canonicalised, direct tenants on plan seats with the old number recorded, trials, migrated networks, hardware indexes
  - licensing.adopt_plan_seats and tenant field license.maxAgentsBeforePlans; audit event plan.seats_adopted (before, after, plan)
  - backend/scripts/check_plan_golive.py (check, report, run, main): the read-only go-live check for 88-16
  - backend/tests/test_migration_034_plans.py (17 tests, private mongod)
affects: [88-12, 88-14, 88-16]

actuals:
  tokens: 7400
  tasks: 2
  commits: 4
plan_head_before: 9638d906a3d6d5902c54df6716def5346b0bbe75
plan_head_after: 32faa0ab696421806957c463451931b466493375

tech-stack:
  added: []
  patterns:
    - "every guard of a one-way migration write is the absence of its own record ($exists False), so a second run matches nothing and writes nothing"
    - "the go-live check script imports the app modules lazily, reads only, and exposes check/report as coroutines so tests run them on the private mongod"

key-files:
  created:
    - backend/migrations/034_plan_licensing.py
    - backend/scripts/check_plan_golive.py
    - backend/tests/test_migration_034_plans.py
  modified:
    - backend/licensing.py

key-decisions:
  - "adopt_plan_seats filters through licensing._direct_filter, so even a wrong call can never match a partner customer, a partner organization or the platform (PROH-88-06), in addition to the migration's own selection"
  - "The audit entry is written after the guarded update and only when it changed the tenant; an audit failure is logged and the migration continues (the old number is already on the tenant as maxAgentsBeforePlans)"
  - "A plan whose stored seats are not a usable whole number is treated like Custom: the tenant keeps its current number as an override rather than being given a bad one"
  - "The check script treats a seat number equal to the plan's seats OR to seatOverride as correct, and checks only globally routable publicIp of admitted agents against allowedNetworks (the same data the migration seeded)"

requirements-completed: [LIC-01, LIC-03, LIC-04, LIC-05, LIC-06]

coverage:
  - id: D1
    description: "Migration 034 stores the four plans (Free 5/14 days/Free seed, Pro 50, Enterprise 500, Custom no seats and screens 'all'); a plan document an administrator edited is never overwritten"
    requirement: LIC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_migration_034_plans.py::test_plans_hold_the_four_d03_documents_and_never_overwrite_an_edit"
        status: pass
    human_judgment: false
  - id: D2
    description: "Direct tenants take their plan's seats with the old number recorded first (license.maxAgentsBeforePlans) and one plan.seats_adopted entry each; the platform, partner customers and partner organizations keep their seats; a hand-set number or a Custom tenant keeps its number as license.seatOverride"
    requirement: LIC-01
    verification:
      - kind: integration
        ref: "backend/tests/test_migration_034_plans.py (test_direct_tenants_take_*, test_platform_partner_customer_*, test_a_hand_set_number_*, test_adopt_plan_seats_records_*)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every tenant without a trial gets one (14-day Free trial from go-live, otherwise consumed); every tenant without allowed networks gets the public addresses of its admitted agents; the platform and partner organizations are skipped; no tenant's enabledFeatures changes"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_migration_034_plans.py (test_trials_start_*, test_allowed_networks_hold_*, test_no_tenant_screen_list_moves)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The sparse hardware indexes exist after the migration and a second run changes no document and records no audit entry"
    requirement: LIC-06
    verification:
      - kind: integration
        ref: "backend/tests/test_migration_034_plans.py (test_hardware_indexes_exist_and_are_sparse, test_a_second_run_changes_no_document_and_records_no_audit_entry)"
        status: pass
    human_judgment: false
  - id: D5
    description: "check_plan_golive.py reads the database only, prints one line per tenant, then FAIL lines or OK, and exits 1 on any failure"
    requirement: LIC-05
    verification:
      - kind: integration
        ref: "backend/tests/test_migration_034_plans.py (test_check_*, test_the_check_script_never_writes, test_run_prints_a_line_per_tenant_and_exits_by_the_result)"
        status: pass
    human_judgment: true
    rationale: "Whether the printed lines are the ones the user wants to read after the live restart can only be judged against the live database in 88-16"
---

# Phase 88 Plan 11: Plan-licensing go-live migration Summary

**Migration 034 seeds the four plans, moves every direct tenant onto its plan's seats while recording each overwritten number (license.maxAgentsBeforePlans plus a plan.seats_adopted ledger entry), starts today's Free trials at go-live, allows every public agent address, and creates the hardware indexes; a read-only script proves the result on the live database after the user's restart.**

## Performance

- **Duration:** about 52 min (2026-11-11 06:25 to 07:17 UTC), 38 of them the full backend suite
- **Tasks:** 2 (both TDD: RED commit, then GREEN commit)
- **Files:** 4 (3 created, 1 modified)

## Accomplishments

- `licensing.adopt_plan_seats(db, tenant_id, *, seats, override, previous)` is one update guarded by the direct-tenant filter and by `license.maxAgentsBeforePlans` being absent: it records the previous number, writes the plan's seats (or the override, also kept as `license.seatOverride`), and returns whether anything changed.
- `migrations/034_plan_licensing.py` runs six steps in the planned order: (a) plan documents with `$setOnInsert` (seed screens, Custom `"all"`); (b) missing or miscased `subscriptionTier` set to the canonical key; (c) direct-tenant seats with an audit entry per tenant; (d) trials; (e) allowed networks (`source "migrated"`, one agent's hostname, at most `MAX_NETWORKS`, only parseable globally routable `publicIp`/`sourceIp` of agents not Pending or Rejected); (f) `cross_tenant.ensure_indexes` (both sparse hardware indexes and the `cross_tenant_reports` unique key index that 88-07 and 88-09 required this migration to create). It never names `enabledFeatures`.
- `scripts/check_plan_golive.py` verifies, with reads only: `_migrations` has 034; the four plans exist; each direct tenant has the old-number record and holds its plan's seats or its override; the platform has no such record; every non-platform, non-partner-organization tenant has a trial (Free ones an end); every admitted agent's global public address is inside its tenant's networks; both sparse indexes exist. It prints one line per tenant, then `FAIL ...` lines, then `OK`; exit 1 on failures.
- The tests build the live shapes of 2026-11-10 (Platform, Exafluence, ABC with EILT0197 at 103.174.161.233, shieldforgetech) plus a partner customer, a partner organization, a Pro tenant with 12 seats, a Custom tenant with 40, a lower-case `enterprise` tenant, and agents with private, invalid, missing, Pending and Rejected addresses.

## Task Commits

| Step | Commit | Message |
| ---- | ------ | ------- |
| 1 RED | 306fe5b22 | test(88-11): add failing tests for migration 034 (plans, seats, trials, networks, indexes) |
| 1 GREEN | be63cedf3 | feat(88-11): migration 034 plan licensing go-live and licensing.adopt_plan_seats |
| 2 RED | 2f0f44648 | test(88-11): add failing tests for the read-only go-live check script |
| 2 GREEN | 32faa0ab6 | feat(88-11): read-only go-live check script for migration 034 |

## TDD Gate Compliance

- **RED (task 1):** collection error, `No module named 'migrations.034_plan_licensing'` (the migration did not exist); all 11 tests were blocked by it, a planned failure, not a fixture fault.
- **RED (task 2):** 6 of 17 failed (the script did not exist); the 11 task-1 tests passed.
- **GREEN:** 17 of 17 pass after the script. No REFACTOR commit. Two test mistakes (collection attribute access for `_migrations`, a sync test under the asyncio mark) were found at GREEN and fixed in the same commit.

## Deviations from Plan

None - plan executed exactly as written.

## Acceptance criteria

- Task 1: `ls backend/migrations | grep -c "^034_"` = 1; `grep -c '"enabledFeatures"' backend/migrations/034_plan_licensing.py` = 0; `grep -c maxAgentsBeforePlans backend/licensing.py` = 3; migration 149 lines (under 500).
- Task 2: `grep -c "async def check\|async def report"` = 2; the write-call grep = 0 (an AST test enforces the same list).

## Verification

- Task commands: test_migration_034_plans.py, test_licensing.py, test_partner_license_writers.py: 41 passed, 0 skipped; test_migration_034_plans.py alone 17 passed (private mongod 127.0.0.1:27998).
- Full backend suite (`backend/tests`, 38 min): 7767 passed, 47 skipped, 28 failed, 291 errors. 317 of the failures and errors are `PermissionError: [Errno 13] Permission denied: '/var/lib/omni-platform'` (service-desk and ticket tests, the known environmental failure: test_000_router_smoke, test_tickets, test_ticket_attachment_download, test_ticket_staff_routes_structure, test_sidebar_audit_fixes::test_secure_share_round_trip). One more failure, `test_patch_rollout_boot::test_a_computer_back_on_a_new_boot_is_healthy_and_the_soak_starts_from_the_restart`, is a wall-clock assertion (soak end 08:01 against a fixed 06:48 start plus one hour) in code this plan does not touch; not fixed. Skips are the opt-in judged-eval tests (live AI gateway), none in this plan's tests.

## Notes for later plans and the user

- The migration has NOT been run against the live database (27017); the user's backend restart applies it (88-16). After the restart run `backend/venv/bin/python backend/scripts/check_plan_golive.py` (defaults: mongodb://127.0.0.1:27017, database omni_platform); expected on the live shapes: Exafluence 50 seats (old number 5 recorded), ABC and shieldforgetech 5 seats with 14-day trials starting at the restart, ABC allowed network 103.174.161.233/32, Platform untouched.
- Exafluence's `license.expiresAt` (2026-10-30, already past) is untouched, so its new machines stay held `license_expired` even with 50 seats.
- A tenant that already has an `allowedNetworks` field (even an empty list) is skipped by the network step; only an absent field is seeded, as the plan specifies.
- The check script's network expectation tests the agent-reported `publicIp`, the same field the migration seeded from; a machine that later enrols from a new address is held Pending and is not counted.
- Nothing was pushed, restarted or published. `backend/licensing.py` was clean before this plan, so its commit holds only this plan's 16 lines; the other files are new.

## Known Stubs

None.

## Threat Flags

None. T-88-32 (the overwrite records `maxAgentsBeforePlans` in the same guarded update, one audit entry per tenant, partner customers, partner organizations and the platform excluded by filter, idempotency test) and T-88-33 (only parseable, globally routable addresses of admitted agents; one-time seed) are mitigated. PROH-88-06 and PROH-88-07 hold: the platform and partner customers keep their seats, and no seat number is written without its previous value recorded and no `enabledFeatures` is touched (asserted by test).

## Self-Check: PASSED

Files found: backend/migrations/034_plan_licensing.py, backend/scripts/check_plan_golive.py, backend/tests/test_migration_034_plans.py, backend/licensing.py. Commits found in HEAD ancestry: 306fe5b22, be63cedf3, 2f0f44648, 32faa0ab6.
