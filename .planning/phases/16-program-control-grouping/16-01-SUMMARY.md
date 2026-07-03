---
phase: 16-program-control-grouping
plan: 01
subsystem: compliance
tags: [fastapi, mongodb, react, pydantic, rbac]

requires: []
provides:
  - ProgramService (create, get, list, update_controls, delete, status rollup)
  - POST/GET/PUT/DELETE /api/programs and /api/programs/{id}/controls endpoints
  - ProgramsDashboard.tsx — program cards with status rollup, control-count, progress bar, Manage Controls modal
affects: [compliance-dashboard, control-evidence]

tech-stack:
  added: []
  patterns:
    - "Status rollup thresholds: compliant (passing>=80% AND failing==0), at_risk (failing>0), else in_progress"
    - "Pending_Evidence counted toward not_assessed, not failing (avoids false at_risk)"

key-files:
  created:
    - backend/program_service.py
    - backend/program_endpoints.py
    - backend/tests/test_program_service.py
  modified:
    - backend/router_registry.py
    - components/ProgramsDashboard.tsx

key-decisions:
  - "Raw db._db.asset_compliance access (not TenantIsolatedCollection) used consistently for status-rollup queries so the explicit tenant_id argument stays load-bearing (WR-01 fix)"
  - "Latest-per-control result selected via .sort(lastUpdated desc) + first-seen dedupe, not arbitrary cursor order (WR-02 fix)"
  - "Control-mutation request bodies validated with Pydantic schemas instead of raw dict Body(...) (WR-03 fix)"
  - "Manage Controls picker modal implemented inline in ProgramsDashboard.tsx rather than a new component file, per CLAUDE.md file-creation guidance"

patterns-established:
  - "Program document schema: {id, tenantId, name, description, framework_id, owner, control_ids, created_at, updated_at}"

requirements-completed: [PROG-01, PROG-02, PROG-03]

coverage:
  - id: D1
    description: "POST /api/programs creates a named program; PUT /api/programs/{id}/controls manages control membership"
    requirement: "PROG-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_create_program"
        status: pass
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_add_controls_to_program"
        status: pass
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_remove_controls_from_program"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#1 Create a new program"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#3 Manage Controls picker modal"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /api/programs/{id} and GET /api/programs return status_rollup {total, passing, failing, not_assessed, status} with compliant/at_risk/in_progress thresholds"
    requirement: "PROG-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_status_rollup_compliant"
        status: pass
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_status_rollup_at_risk"
        status: pass
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_list_programs_includes_rollup"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#2 status rollup/control count/progress bar"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#4 compliant badge"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#5 at_risk badge"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#6 Pending_Evidence counted as in_progress not at_risk"
        status: pass
    human_judgment: false
  - id: D3
    description: "DELETE /api/programs/{id} removes only the program document; control_evidence/compliance data untouched; destructive delete requires UI confirmation"
    requirement: "PROG-03"
    verification:
      - kind: manual_procedural
        ref: "16-UAT.md#7 delete requires confirmation, evidence not deleted"
        status: pass
    human_judgment: false
  - id: D4
    description: "Programs are tenant-isolated"
    verification:
      - kind: unit
        ref: "backend/tests/test_program_service.py#test_tenant_isolation"
        status: pass
      - kind: manual_procedural
        ref: "16-UAT.md#8 tenant isolation"
        status: pass
    human_judgment: false

duration: unknown (retroactively documented)
completed: 2026-07-04
status: complete
---

# Phase 16: Program Control Grouping Summary

**Named-program control grouping (ProgramService + /api/programs) with live status_rollup (compliant/at_risk/in_progress), a Manage Controls picker modal, and full compliance-score wiring — closes the Probo/OpenLane Core parity gap for grouping controls by security domain instead of framework-flat lists.**

## Performance

- **Duration:** unknown — implementation commit predates this documentation pass; retroactively summarized after execution, code review, fix cycle, and UAT were confirmed complete via git history and a full conversational UAT session
- **Completed:** 2026-07-04
- **Files modified:** 5 (program_service.py, program_endpoints.py, test_program_service.py, router_registry.py, ProgramsDashboard.tsx)

## Accomplishments
- `ProgramService` (create, get, list, update_controls, delete, `_compute_status_rollup`) with tenant-isolated program documents
- `/api/programs` CRUD + `/api/programs/{id}/controls` membership management, registered in `router_registry.py`
- `ProgramsDashboard.tsx`: program cards with status badge, control count, progress bar, create/edit/delete actions, and a Manage Controls modal (search + select control picker)
- 7/7 unit tests passing (`test_create_program`, `test_add_controls_to_program`, `test_remove_controls_from_program`, `test_status_rollup_compliant`, `test_status_rollup_at_risk`, `test_list_programs_includes_rollup`, `test_tenant_isolation`)
- Full code review cycle: 7 critical + 6 warning findings (16-REVIEW.md), all 13 fixed and independently re-verified (16-REVIEW-FIX.md)
- Full conversational UAT: 9/9 tests passed (16-UAT.md), including the WR-04 Pending_Evidence-not-at_risk regression check and the WR-06 delete-confirmation check

## Task Commits

Implementation landed in a single commit that was mislabeled in git history (message says "feat(phase-16)" but the commit's actual diff spans multiple unrelated phases — a pre-existing repo-history quirk, not specific to this phase): `e52393a`.

Code review fixes, each committed atomically:
1. **CR-01** import TestClient from fastapi.testclient - `4eb56be`
2. **CR-02** override stable get_current_user dependency - `c8bbd91`
3. **CR-03** add missing status-rollup tests, replace tautological assertions - `aa2c728`
4. **CR-04** strip mutated ObjectId before returning created program - `89af48a`
5. **CR-05** project out ObjectId before control update - `9071d39`
6. **CR-06** check response.ok before reporting create/delete success - `4c96695`
7. **CR-07** implement Manage Controls modal with search/select and PUT wiring - `cec30cd`
8. **WR-01** read asset_compliance via raw db._db so tenant_id argument is load-bearing - `eedeb17`
9. **WR-02** sort by lastUpdated for deterministic latest-result dedupe - `7909bc6`
10. **WR-03** validate program-mutation request bodies with Pydantic schemas - `8093652`
11. **WR-04** count Pending_Evidence toward not_assessed instead of failing - `15f6682`
12. **WR-05** rename local fetch callback to loadPrograms - `bfe78f5`
13. **WR-06** confirm before destructive program delete - `22d04cf`

## Files Created/Modified
- `backend/program_service.py` - ProgramService: CRUD + status rollup computation
- `backend/program_endpoints.py` - router at /api/programs
- `backend/tests/test_program_service.py` - 7-test TDD suite
- `backend/router_registry.py` - registers program_endpoints
- `components/ProgramsDashboard.tsx` - program list UI with status rollup, control count, progress bar, Manage Controls modal

## Decisions Made
- WR-01: raw `db._db.asset_compliance` access used consistently (not `TenantIsolatedCollection`) so the explicit `tenant_id` argument stays load-bearing rather than silently overridden by the tenant_context contextvar
- WR-02: latest-per-control result selected via `.sort("lastUpdated", -1)` + first-seen dedupe for deterministic rollup status
- WR-04: `Pending_Evidence` status counted toward `not_assessed`, not `failing`, so awaiting-evidence controls don't produce a false "At Risk" badge
- CR-07: Manage Controls modal implemented inline in `ProgramsDashboard.tsx` rather than as a new component file (file stayed well under the 500-line limit)

## Deviations from Plan

None beyond the standard code-review fix cycle (13 findings, all fixed — see Task Commits). Plan executed as specified; IN-01 (plan doc referencing the wrong collection name, `compliance_results` vs actual `asset_compliance`) was noted in the review as a documentation-only correction, not a code deviation.

## Issues Encountered

This phase's `SUMMARY.md` was not created at execution time — the executing session ended without writing it, which caused this phase to appear "not executed" to downstream tooling (`/gsd-progress --next`'s safe-resume gate, `/gsd-code-review`'s SUMMARY-based file scoping, `/gsd-secure-phase`'s state detection) despite the implementation, code review, and fix cycle all being complete and committed. This SUMMARY.md was retroactively authored after independently verifying the implementation via git history, re-running the test suite, and completing a full conversational UAT session (9/9 passed) — closing the gap so downstream GSD tooling can correctly recognize the phase as complete.

## Next Phase Readiness
Phase 16 fully implemented, reviewed, fixed, and UAT-verified. Ready for `/gsd-secure-phase 16` (in progress) and subsequent phase advancement.

---
*Phase: 16-program-control-grouping*
*Completed: 2026-07-04*
