---
phase: 43-remediation-to-ticketing-bridge
plan: 02
subsystem: api
tags: [ticketing, jira, servicenow, fastapi, pytest, asyncio]

# Dependency graph
requires:
  - phase: 43-01
    provides: "ticketing_bridge.create_ticket_for_remediation_task(db, task, tenant_id, provider_override=None)"
affects: [43-03, 43-04]
provides:
  - "compliance_remediation_service.create_task — priority-gated (critical/high/medium) auto-create-ticket hook, non-blocking on ticketing failure"
  - "backend/tests/test_remediation_workflow.py::test_autocreate_nonfatal — regression coverage for D-01 (revised)/D-04"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Conditional non-blocking side-effect after insert_one, cloned from create_task's sibling update_task/dispatch_rescan shape already in this file"

key-files:
  created: []
  modified:
    - backend/compliance_remediation_service.py
    - backend/tests/test_remediation_workflow.py

key-decisions:
  - "Followed the plan's revised D-01 threshold (critical/high/medium) rather than 43-PATTERNS.md's stale high/critical-only code example — the plan frontmatter explicitly flagged this as a post-plan-checker revision dated 2026-07-21"
  - "No provider_override passed from the auto-create hook — auto-create always falls back to the tenant's configured provider (config[\"provider\"]), matching Pattern 3 from 43-PATTERNS.md"

patterns-established: []

requirements-completed: [REM-01]

coverage:
  - id: D1
    description: "create_task auto-creates a ticket via ticketing_bridge for critical/high/medium priority tasks, in a try/except that never blocks task creation"
    requirement: "REM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_remediation_workflow.py#test_autocreate_nonfatal"
        status: pass
      - kind: unit
        ref: "backend/tests/test_remediation_workflow.py (full file, 5/5 passing)"
        status: pass
    human_judgment: false

# Metrics
duration: 5min
completed: 2026-07-21
status: complete
---

# Phase 43 Plan 02: Priority-Gated Auto-Create Ticket Hook Summary

**`create_task` now auto-creates a Jira/ServiceNow ticket for critical/high/medium priority remediation tasks via `ticketing_bridge`, wrapped in a non-blocking try/except so a ticketing outage never prevents task creation.**

## Performance

- **Duration:** ~5 min (commit-to-commit)
- **Started:** 2026-07-21T12:16:00Z (approx)
- **Completed:** 2026-07-21T12:21:14Z
- **Tasks:** 2/2 completed
- **Files modified:** 2

## Accomplishments
- `compliance_remediation_service.create_task` gains a priority-gated hook (D-01, revised 2026-07-21 to include `medium`) that lazily imports `ticketing_bridge` and calls `create_ticket_for_remediation_task(db, task, tenantId)` after the task is persisted via `insert_one`
- The hook is wrapped in `try/except Exception`, logging a warning and never re-raising, so a ticketing failure cannot block or alter `create_task`'s return contract (D-04)
- `low` priority tasks remain excluded from auto-create — they still only get a ticket via the manual "Create Ticket" button (Plan 03)
- New `test_autocreate_nonfatal` test proves: (1) critical/medium priority tasks still return a valid persisted task even when `ticketing_bridge.create_ticket_for_remediation_task` raises, and (2) low priority tasks never invoke the auto-create path at all

## Task Commits

Each task was committed atomically:

1. **Task 1: Add priority-gated auto-create hook to create_task** - `2bb4d65` (feat)
2. **Task 2: Add autocreate_nonfatal test to test_remediation_workflow.py** - `1099e61` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/compliance_remediation_service.py` - `create_task` now auto-creates a ticket for critical/high/medium priority tasks, non-blocking
- `backend/tests/test_remediation_workflow.py` - adds `test_autocreate_nonfatal` covering the non-fatal auto-create path and the low-priority exclusion

## Decisions Made
- Applied the plan's explicit revision of D-01's threshold (critical/high/medium, not the older high/critical example still present in `43-PATTERNS.md`) since the plan frontmatter and objective both call this out as a post-plan-checker correction dated 2026-07-21
- Kept `provider_override` unset in the auto-create call so it always resolves via the tenant's configured `ticketing_configs` provider, per Pattern 3 in `43-PATTERNS.md`

## Deviations from Plan

None - plan executed exactly as written (including its explicit correction to `43-PATTERNS.md`'s now-superseded high/critical-only threshold).

## Issues Encountered

None. Full `test_remediation_workflow.py` file (5 tests) and `test_ticketing_bridge.py` (14 tests) both pass after the change — no regressions in either file.

## User Setup Required

None - no external service configuration required. Live Jira/ServiceNow sandbox verification of the auto-create trigger remains a manual/UAT gate per `43-VALIDATION.md`, out of scope for this plan's hermetic unit coverage.

## Next Phase Readiness
- `create_task`'s auto-create hook is in place for Plan 03 (manual "Create Ticket" endpoint/button) and Plan 04 (app-startup close-loop scheduler registration) to build on without further changes to `compliance_remediation_service.py`
- No blockers.

---
*Phase: 43-remediation-to-ticketing-bridge*
*Completed: 2026-07-21*

## Self-Check: PASSED

- FOUND: backend/compliance_remediation_service.py
- FOUND: backend/tests/test_remediation_workflow.py
- FOUND: 2bb4d65 (Task 1 commit)
- FOUND: 1099e61 (Task 2 commit)
