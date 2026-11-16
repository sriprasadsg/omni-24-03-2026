---
phase: 78-organization-endpoint-cost-api
plan: 10
subsystem: testing
tags: [itam, cost, phase-gate, pytest, mongodb, regression]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: cost service, routes, KPI, report, parity, scale and isolation suites (78-01..78-09)
provides:
  - Backend phase gate for Phase 78: 310 phase tests pass on real MongoDB with 0 skipped, no leftover test database; full backend suite has no phase regression
affects: [phase-78-verification, phase-80]

actuals:
  tokens: 3000
  tasks: 2
  commits: 0
plan_head_before: 92accd1e4fdf5bcb2a41bc09c2a13a9b96fa282c
plan_head_after: 92accd1e4fdf5bcb2a41bc09c2a13a9b96fa282c

tech-stack:
  added: []
  patterns:
    - "Same-instrument regression check: every full-suite failure re-run on a scratchpad worktree of the pre-phase commit with the main venv"

key-files:
  created: []
  modified: []

key-decisions:
  - "No source change: the gate found no phase regression, so no fix commit was made (commits: 0 is the legitimate verification-only count)"
  - "The 14 export files left in backend/static/reports by the unmodified Phase 72/73 export suite were removed by exact name, so the listing is back to its pre-run state; the leak itself is pre-existing and was not fixed (out of scope)"

requirements-completed: [COST-01, COST-02, COST-03, COST-06, COST-07]

coverage:
  - id: D1
    description: "The phase command over all 14 Phase 78 backend suites (new and edited) reports 310 passed, 0 failed, 0 error, 0 skipped on the local mongod"
    requirement: COST-01
    verification:
      - kind: integration
        ref: "backend/venv/bin/python -m pytest <14 phase suites> -q -p no:cacheprovider -rs: 310 passed in 82.12s"
        status: pass
    human_judgment: false
  - id: D2
    description: "The omni_test_* database list is identical before and after the phase command (empty both times) and after the full suite; backend/static/reports ends identical to its start"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "saved vs post-run listings in the session scratchpad (see Task 1 note on export files)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The full backend suite shows no failure introduced by Phase 78: its single failure also fails on the pre-phase commit fd4e00f24 under the same conditions"
    requirement: COST-02
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_a_computer_back_on_a_new_boot_is_healthy_and_the_soak_starts_from_the_restart fails on HEAD and on fd4e00f24 after a 13 minute collection delay"
        status: pass
    human_judgment: false

duration: 54min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 10: Backend phase gate Summary

**Phase 78 backend gate: 310 phase tests pass on real MongoDB with 0 skipped, and the full backend suite (8,532 passed) has no phase regression; its one failure is a Phase 84 wall-clock test that fails identically on the pre-phase commit**

## Performance

- **Duration:** 54 min (21:31 to 22:25 UTC)
- **Tasks:** 2 (tracer + full suite), verification only
- **Files modified:** 0 (no source change, no fix commit)

## Task 1 (tracer): the phase command

`backend/venv/bin/python -m pytest <14 suites> -q -p no:cacheprovider -rs` (the command in 78-VALIDATION.md), mongod ping answered first.

Final line: `======================== 310 passed in 82.12s (0:01:22) ========================` (no failed, no error, no skipped; `-rs` printed no skip lines).

PROH-78-05 comparison:

- **omni_test_* databases:** saved list empty before, empty after the phase command, empty after the full suite. Identical.
- **backend/static/reports:** the listing was NOT identical straight after the phase command. 7 new `itam_report_*` files appeared (`itam_report_rpt-1_*.csv`, `itam_report_rpt-pdf-1_*.pdf`, `itam_report_rpt-xlsx-1_*.xlsx`, four `itam_report_warranty_expiring_*` csv/pdf/xlsx). Cause: `backend/tests/test_itam_reporting_export.py` (a Phase 72/73 suite, unchanged by Phase 78: `git diff fd4e00f24..HEAD` is empty for it) posts real exports and the export route writes them to `backend/static/reports` with no cleanup. Proof it is pre-existing: the same file run in a worktree of fd4e00f24 (19 passed) also added 7 `itam_report_*` files to that worktree's reports directory. The files are gitignored (`.gitignore:37 backend/static/reports/itam_report_*`). The files this gate created (7 from the phase command, 7 more from the full suite, 14 in all, all with timestamps from today's runs) were removed by exact name; the final listing (name and size of every file) equals the one saved before the run, and no pre-existing file was touched. The phase-78 modules write nothing there. The truth "listing the same before and after" therefore holds only after that cleanup; the underlying leak in the unmodified export suite is recorded as a finding, not fixed (see Deferred Issues).

## Task 2: full backend suite

`TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider -rfE` (temp dirs under the scratchpad):

`1 failed, 8532 passed, 49 skipped, 36 warnings in 2144.70s (0:35:44)`, 0 errors.

The earlier-session setup ERROR in `test_service_desk_comments.py::test_a_staff_comment_notice_has_no_text_and_does_not_address_the_reporter` did not recur in this run (that file passed in full); it was seen only in the earlier `-x` broad runs while another executor's tests ran concurrently, so no pre-phase comparison was needed for it.

| Failing test | HEAD (92accd1e4) | Pre-phase fd4e00f24 | Verdict |
|--------------|------------------|---------------------|---------|
| `backend/tests/test_patch_rollout_boot.py::test_a_computer_back_on_a_new_boot_is_healthy_and_the_soak_starts_from_the_restart` | failed in the full run; passes alone (1 passed) | passes alone (1 passed); fails with a 13 minute collection delay (1 failed) | pre-existing, not a phase regression |

Why it fails: `tests/test_patch_rollout_lines.py:30` freezes `NOW = datetime.now(...)` at import (collection) time, and the test expects `soakEndsAt == booted + 1h` where booted is about NOW + 10 minutes. The stand-in agent's install result is stamped by the real clock, and `health.soak_end` takes the later of the install report and the new boot, so once the real clock passes collection time + about 10 minutes (any full-suite run of over ten minutes reaches this test late) the soak end is real-now + 1h instead of booted + 1h. The failing assertion in the full run showed exactly that: actual 22:56:30.94 UTC against expected 21:43 + 1h. To prove same-instrument equivalence, a scratchpad pytest plugin sleeping 780 s after collection was run against both HEAD and a worktree of fd4e00f24; both failed with the identical test and result (`1 failed in 781 s`). Phase 78 touches none of `patch_rollout*`, `autonomous_ops/rollout` or that test file. T-78-25 satisfied: the failure is recorded with its pre-phase result.

The 49 skips are outside the Phase 78 suites (the phase command, which names every Phase 78 file, skipped nothing). They were not itemised because `-rs` was only requested for the phase command.

Worktree cleanup: the fd4e00f24 worktree lived at `<scratchpad>/78-10/prephase`; removed with `git worktree remove --force` and `git worktree prune`. `git worktree list` before and after is identical (main checkout on `npx`, plus `.claude/worktrees/ndr-stage1` on `88.1-stage1`). No test process is running.

## Scale timings

Read from 78-08-SUMMARY.md: at 20,000 assets the summary route took 0.24 to 0.29 s, list page 1 took 0.15 to 0.23 s and the KPI 0.19 to 0.25 s, so the 10 second bound holds by about 40 times. In this gate `test_itam_cost_scale.py` passed inside the 310 with the machine idle (load average about 1.6).

## Task Commits

None. This plan is verification only and found no phase regression, so no source commit was needed (`git rev-list --count 92accd1e4..HEAD` was 0 before this SUMMARY). The SUMMARY and planning-state update is committed separately as `docs(78-10)`.

## Deviations from Plan

None - plan executed exactly as written. Three things the plan left open were handled as follows:

- The post-phase-command reports listing differed because of the unmodified export suite (above); handled as a pre-existing leak with a worktree proof and a by-name cleanup of only the files this gate created.
- The full-suite failure is clock-dependent and passes alone on both commits; the same-instrument comparison was therefore run with an induced collection delay (scratchpad plugin, nothing added to the repository).
- The plan names the pre-phase commit as the parent of the oldest `(78-01)` commit; that is fd4e00f24 (the orchestrator's value matches: first 78-01 commit is 8fe9f982c, its parent fd4e00f24).

## Deferred Issues

Out-of-scope findings, recorded and not fixed:

1. `test_itam_reporting_export.py` writes real export files to `backend/static/reports` and never removes them (the route's output directory is not redirected to a temp dir). Phase 72/73 origin; every run adds 7 files.
2. `test_patch_rollout_boot.py::test_a_computer_back_on_a_new_boot_is_healthy_and_the_soak_starts_from_the_restart` (Phase 84) fails in any suite run longer than about 10 minutes after collection because of the import-time `NOW` in `tests/test_patch_rollout_lines.py`. It makes the documented full-suite command (about 36 minutes here) exit 1 even on the pre-phase commit. A fix would freeze the stand-in agent's report time to the same clock or patch the real-clock stamp.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. T-78-25 and T-78-26 are mitigated as specified (the failing test was re-run on the pre-phase commit; the worktree sat in the scratchpad and was removed and pruned, with `git worktree list` identical before and after). No deploy, backend restart, UI publish or git push.

## Issues Encountered

The full suite took 35 minutes 44 seconds, longer than the plan's estimate of about 11 minutes; this is the measured wall time on this VM and the cause of the clock-dependent failure above.

## Requirements

`requirements.ready-ids` was run after this SUMMARY existed; COST-01, COST-02, COST-03, COST-06 and COST-07 are the plan's requirements and every Phase 78 plan now has a SUMMARY (see the completion commit for the result).

## Next Phase Readiness

Backend gate for Phase 78 is green. Ready for phase verification.

## Self-Check: PASSED

Verified: 78-10-SUMMARY.md present on disk; no commits were expected (commits: 0, verification only); `git worktree list` unchanged; no pytest process running; `omni_test_*` list empty; reports listing equals its saved starting state.
