---
phase: 86-activity-reporting-hardening-live-validation
plan: 03
subsystem: testing
tags: [autonomous-ops, multi-tenant, isolation, pytest, mongodb]

requires:
  - phase: 83-security-response
    provides: sweep.tick, the per-tenant sweep stages
  - phase: 84-staged-patch-rollouts
    provides: rollout loop run_once and controller tick
  - phase: 85-service-desk
    provides: service_desk.worker.run_once with an injectable model client
  - phase: 82-self-healing-retention
    provides: retention_job.run_all and the confirm gate
provides:
  - one two-tenant contract test per automatic loop (security sweep, patch rollouts, service desk, retention)
  - assert_no_crossing, a per-collection helper that 86-09 can reuse for the reporting surfaces
affects: [86-09 reporting two-tenant cases, go-live checklist]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2
plan_head_before: 659b11db7777999f01a2dd70e79fc8697ecf8867
plan_head_after: 42d279867c9997952338fcab1aaa1388b0ae6df9

tech-stack:
  added: []
  patterns:
    - "Crossing helper: every document of a list of collections, and every notice call, may name only the tenant that owns it (identifying strings matched with word-boundary regex)"

key-files:
  created:
    - backend/tests/test_autonomous_ops_two_tenant.py
  modified: []

key-decisions:
  - "Tenant ids tenant-alpha / tenant-bravo (not t1/t2) so a substring search for the other tenant's marker cannot collide"
  - "Service desk case seeds each tenant with seed_desk_tenant(mode='post') and one article each, never the starter articles"
  - "Retention case uses two ObjectId-aged types with different tenant field spellings (agent_metrics tenant_id, logs tenantId)"

requirements-completed: [GATE-11]

coverage:
  - id: D1
    description: "Security response sweep: one sweep.tick over two tenants writes each decision, instruction and signal under the owning tenant only"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_one_sweep_pass_decides_for_each_tenants_own_agent_and_address"
        status: pass
    human_judgment: false
  - id: D2
    description: "Patch rollouts: one run_once with an open window for one tenant and a closed one for the other; the open one advances, the closed one waits, instructions name only own hosts"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_one_rollout_pass_keeps_each_tenants_window_hosts_and_instructions_apart"
        status: pass
    human_judgment: false
  - id: D3
    description: "Service desk: one worker pass answers one tenant from its own article and hands the other to a person; nothing crosses"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_one_desk_pass_answers_from_the_tenants_own_article_and_hands_off_the_other"
        status: pass
    human_judgment: false
  - id: D4
    description: "Retention: different confirmed days per tenant delete only each tenant's own rows past its own cutoff, counts recorded per tenant"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_retention_deletes_each_tenants_own_rows_past_its_own_cutoff_and_counts_per_tenant"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-13
status: complete
---

# Phase 86 Plan 03: Two-tenant contracts for every automatic loop Summary

**Four real-entry-point two-tenant tests (sweep.tick, rollout loop run_once, desk worker run_once, retention run_all) on the private mongod, with a reusable per-collection crossing helper; no leak found.**

## Performance

- **Duration:** about 25 min
- **Completed:** 2026-11-13
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments

- Security sweep: tenant-alpha and tenant-bravo each get exactly one `block_ip` decision and one agent instruction for their own agent and their own address (45.33.32.156 and 45.33.32.10); no signal, incident, row or notice names the other tenant.
- Patch rollouts: with an open window for alpha and a closed one for bravo, one `run_once` sends only alpha's canary install and leaves bravo's ring in `waiting_for_window`; when bravo's window opens the next day only bravo's canary host is sent its install, and no rollout, host, job or decision row crosses.
- Service desk: both tenants get the same password question; bravo's own article answers it (job reason `posted`, `ai_answer` comment), alpha has no matching article and is handed to a person (`no_article`); alpha's article never reaches the model prompt and no comment, job, ledger row or notice crosses.
- Retention: alpha confirmed at 20 days, bravo at 60, rows 10, 30 and 70 days old in two types; counts are recorded per tenant at first run, then one `run_all` leaves alpha with the 10-day rows and bravo with 10 and 30, each gate row recording its own period.
- `assert_no_crossing` returns per-tenant document counts so each case also proves it was not vacuous.

## Task Commits

1. **Task 1: sweep and rollout contracts** - `c80a6a201` (test)
2. **Task 2: service desk and retention contracts** - `42d279867` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified

- `backend/tests/test_autonomous_ops_two_tenant.py` - 285 lines; the crossing helper and four loop contract tests

## Decisions Made

- Tenant ids `tenant-alpha` / `tenant-bravo` instead of `t1`/`t2` so marker matching by regex cannot collide with unrelated short strings.
- The rollout case does not assert an exact instruction count for the open-window tenant after the second pass (its canary may be retried); it asserts every instruction targets its own canary, and exactly one for the tenant whose window just opened.
- The desk case does not use `add_tenant` (starter articles); each tenant has one hand-seeded article.

## Deviations from Plan

None - plan executed exactly as written. No cross-tenant leak was found, so no loop module was changed.

One housekeeping note: the first Task 1 commit was made with a `Co-Authored-By` trailer suggested by the session's attribution reminder; CLAUDE.md and the plan forbid it (the project's `.claude/settings.json` sets no `attribution.commit`), so it was amended away before any further work (the commit was local and unpushed). Final hash `c80a6a201`.

## Issues Encountered

None. All four tests passed on the first full run after fixing one syntax slip in the test file itself.

## Verification

- Task 1 command: 2 passed, no skips.
- Task 2 command (this file plus `test_retention_job.py` and `test_service_desk_worker.py`): 63 passed, no skips, run with `-rs`.
- `grep -c "27017"` on the file prints 0; `wc -l` prints 285; ruff passes.
- Run only against the private mongod at 127.0.0.1:27998.

## Known Stubs

None.

## Threat Flags

None - tests only, no new surface. T-86-05 (information disclosure across tenants in the four loops) is mitigated by these contracts.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for the remaining Phase 86 plans; 86-09 can import `assert_no_crossing` pattern (append its reporting cases to this file, which has about 215 lines of room under the 500-line rule).

---
*Phase: 86-activity-reporting-hardening-live-validation*
*Completed: 2026-11-13*

## Self-Check: PASSED

- backend/tests/test_autonomous_ops_two_tenant.py exists
- commits c80a6a201 and 42d279867 are on the current branch
