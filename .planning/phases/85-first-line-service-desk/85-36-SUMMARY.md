---
phase: 85-first-line-service-desk
plan: 36
subsystem: testing
tags: [gate, pytest, vitest, security-records, validation, gap-closure]

requires:
  - phase: 85-first-line-service-desk
    provides: gap plans 85-30 to 85-35 (manage:tickets staff model, notice audience, ticket guards, scoped lists, staff-only actions and desk routes)
provides:
  - the Phase 85 gate run on the second gap round (backend, UI suite, build)
  - CR-501 and WR-502 recorded fixed; AR-85-01, AR-85-04 and AR-85-09 re-recorded as superseded; D-38 to D-41; validation rows 85-30 to 85-35
affects: [gsd-secure-phase 85, 85 verifier, gsd-verify-work 85]

actuals:
  tokens: 2500
  tasks: 2
  commits: 1
plan_head_before: 7c419b1f6d9f62fc15d53d3a156311020bcdb65c
plan_head_after: 9f3fa68c9d60fa1103e3ae53b01f939f32dd4487
commits: 1

tech-stack:
  added: []
  patterns: ["gate on the private mongod 127.0.0.1:27998 only; clean-HEAD proof in a throwaway worktree when user WIP skews a catalogue test"]

key-files:
  created: []
  modified:
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md
    - .planning/phases/85-first-line-service-desk/85-SECURITY.md
    - .planning/phases/85-first-line-service-desk/85-CONTEXT.md
    - .planning/phases/85-first-line-service-desk/85-VALIDATION.md

key-decisions:
  - "Gate counts recorded honestly: 2694 passed and 2 known-WIP failures on the working tree, 65 of 65 on a clean HEAD for the two catalogue files"
  - "Only the three Accepted Risks Log rows were touched in 85-SECURITY.md (3 insertions, 3 deletions)"

requirements-completed: [DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07]

coverage:
  - id: D1
    description: "The second gap round passes the whole Phase 85 gate, the UI suite and the build without touching the live database"
    requirement: DESK-01
    verification:
      - kind: integration
        ref: "backend gate command (Task 1 verify) on mongodb://127.0.0.1:27998: 2694 passed, 2 known failures, clean-HEAD proof 65 passed"
        status: pass
      - kind: unit
        ref: "npx vitest run src/__tests__: 1876 passed, 0 failed"
        status: pass
      - kind: other
        ref: "npm run build exit 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "Disposition, security acceptances, context decisions and validation rows agree with the code"
    requirement: DESK-01
    verification:
      - kind: other
        ref: "grep -c 'disposition: fixed' = 13; open: 24; SUPERSEDED rows = 3; D-38..D-41 present; rows 85-30..85-35 present"
        status: pass
    human_judgment: true
    rationale: "Wording of the superseded risks and D-38 to D-41 must be confirmed by the user and re-audited by /gsd-secure-phase 85"

duration: 25min
completed: 2026-11-09
status: complete
---

# Phase 85 Plan 36: Second gap round gate and records Summary

**The whole Phase 85 gate is green on the second gap round (2696 of 2696 backend tests on committed code, 1876 UI tests, build 0), and CR-501, WR-502, three superseded risk acceptances, D-38 to D-41 and six validation rows are recorded.**

## Performance

- **Duration:** about 25 min (the backend gate alone took 21 min 05 s)
- **Started:** 2026-11-09T22:51:53Z
- **Completed:** 2026-11-09T23:16Z
- **Tasks:** 2
- **Files modified:** 4 (all planning documents)

## Accomplishments

- Task 1 (tracer) gate, run on the code of 85-30 to 85-35:
  - Backend: `2 failed, 2694 passed in 1265.73s (0:21:05)` out of 2696 collected, 0 skipped, 0 errors, on the private mongod 127.0.0.1:27998. The passed count is above the 2179 floor.
  - The two failures are exactly the known ones: `test_catalogue_route_parity.py::test_unguarded_routers_are_ledgered` and `::test_ledger_ratchets`, both naming only reporting_endpoints (5 unguarded routes). Cause: the user's uncommitted `shared/catalogue-gaps.json` expects their set-aside `reporting_endpoints.py` edits. Nothing else failed.
  - Clean-HEAD proof: in a throwaway `git worktree add --detach` of HEAD (removed afterwards), `test_catalogue_route_parity.py` and `test_catalogue_manifest.py` ran with the main checkout's `backend/venv/bin/python` and the same env vars: `65 passed in 19.25s`. Committed code is therefore 2696 of 2696.
  - UI: `npx vitest run src/__tests__`: Test Files 117 passed (117), Tests 1876 passed (1876), 0 failed. No RetentionPolicyDashboard flake this time.
  - Build: `npm run build` exit 0 (output to `dist-new`, which is untracked/ignored; nothing published).
  - Database hygiene: omni_test_* databases on the live mongod 127.0.0.1:27017 were 0 before and 0 after (read-only listing). The gate used the private mongod only.
- Task 2: `85-REVIEW-DISPOSITION.md` CR-501 fixed (85-31: b7e178bd3, 4f5ad02b9, tests 975d2d5dc) and WR-502 fixed (85-30: 1a0a5d54b; 85-32: fd671c60e; 85-33: 6458b0f62, 59e98958d, 03d6efce5; 85-34: 638d655b7, 283a1b71a; 85-35: 37b7f2890, 3f2045d09); `grep -c "disposition: fixed"` = 13, `open: 24`. `85-SECURITY.md` AR-85-01, AR-85-04 and AR-85-09 re-recorded as SUPERSEDED (AR-85-09 in part), original rationale kept; the commit touches that file with 3 insertions and 3 deletions. `85-CONTEXT.md` gains "UAT amendments (2026-11-09, gap G-85-4, user-approved in 85-UAT.md)" with D-38 to D-41 before Claude's Discretion; no earlier line changed. `85-VALIDATION.md` gains rows 85-30 to 85-35, the Full suite command is the new gate command, runtime note says 2,696 tests, and the Validation Audit gains the gate line; `nyquist_compliant: true`, `status: validated` kept.

## Task Commits

1. **Task 1: gate run (tracer)** - no commit (verification only)
2. **Task 2: records** - `9f3fa68c9` (docs)

**Plan metadata:** the SUMMARY/STATE/ROADMAP commit follows this file.

## Files Created/Modified

- `.planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md` - CR-501, WR-502 fixed with hashes; open 24
- `.planning/phases/85-first-line-service-desk/85-SECURITY.md` - three Accepted Risks Log rows superseded
- `.planning/phases/85-first-line-service-desk/85-CONTEXT.md` - D-38 to D-41
- `.planning/phases/85-first-line-service-desk/85-VALIDATION.md` - six rows, gate command, audit line

## Decisions Made

None beyond the plan. The disposition Source cell for WR-502 lists the code commits only (docs commits of the gap plans omitted).

## Deviations from Plan

None - plan executed exactly as written. No fix was needed to reach green. The two failing catalogue tests are the orchestrator-documented working-tree mismatch (user WIP), proved green on clean HEAD; they are not a gate failure of committed code.

**Total deviations:** 0.

## Issues Encountered

None. The backend gate's final pytest line reports exit 1 on the working tree only because of the two known WIP-caused failures.

## For the user

- **Deployment steps that stay yours:** restart the backend (omni-backend.service) to ship 85-30 to 85-35 (they run from the checkout); publish the UI (the role editor label from 85-30; build output is in `dist-new`); no migration. I did not restart, publish or push.
- **Custom-role users lose staff access to colleagues' tickets** until a tenant admin ticks "Handle tickets as IT staff" (manage:tickets) on the role (A-85-G20, A-85-G30). This includes custom Knowledge Base editor roles: Write article now needs manage:tickets as well, and built-in Knowledge Base roles without it lose the Knowledge gaps tab.
- **Planner's reading of UD-2 to confirm (A-85-G28):** PATCH on a ticket, adding or removing links and deleting an attachment are staff-only; CSAT stays the requester's own on their own resolved ticket.
- **Follow-ups left open:** untagged ticket lifecycle notices still reach every tenant user (A-85-G21, T-85-111); the AI chat `/tickets` skill (`skill_handlers_queries.handle_tickets`) still lists the five newest ticket titles to any chat user (A-85-G27, T-85-118); `components/InternalTicketsDashboard.tsx` (your WIP) still shows staff controls to requesters, who now get a 403 message (A-85-G29); when your uncommitted `tickets_endpoints.py` download route returns, add the requester-404 test for it (T-85-114).
- **Re-run `/gsd-secure-phase 85`** to record T-85-105 to T-85-127 and re-check the three superseded acceptances; then the verifier and `/gsd-verify-work 85` reconcile G-85-4.
- Your uncommitted `shared/catalogue-gaps.json` and the set-aside `reporting_endpoints.py` edits must be restored together, or the two parity tests fail on the working tree.

## Known Stubs

None.

## Threat Flags

None. T-85-126 mitigated (the three rows re-recorded); T-85-127 mitigated (private mongod URLs, omni_test_ count 0 before and 0 after); T-85-SC accepted (no install).

## Next Phase Readiness

Phase 85 is ready for code review, regression, the re-run of `/gsd-secure-phase 85`, the verifier and `/gsd-verify-work 85`. It is not complete until verified.

## Self-Check: PASSED

- FOUND: the four edited planning files, committed in `9f3fa68c9` (verified an ancestor of HEAD)
- Acceptance: fixed count 13, `open: 24`, SUPERSEDED rows 3, SECURITY 3+/3-, D-38 and D-41 present, rows 85-30 to 85-35 present, `git diff --stat` on 85-VERIFICATION.md and 85-UAT.md empty, no Co-Authored-By trailer

---
*Phase: 85-first-line-service-desk*
*Completed: 2026-11-09*
