---
phase: 43-remediation-to-ticketing-bridge
plan: 03
subsystem: api
tags: [jira, servicenow, ticketing, fastapi, pytest, asyncio-scheduler]

# Dependency graph
requires:
  - phase: 43-01
    provides: "ticketing_bridge.create_ticket_for_remediation_task(db, task, tenant_id, provider_override=None) and start_close_loop_scheduler(db)"
  - phase: 43-02
    provides: "compliance_remediation_service.create_task's priority-gated auto-create hook (leaves low-priority tasks for this plan's manual endpoint)"
affects: [43-04]
provides:
  - "POST /api/compliance-remediation/tasks/{task_id}/create-ticket — manual ticket creation with Literal-validated provider, tenant scoping, 404/502 handling"
  - "backend/app_startup.py — close-loop scheduler registered at startup with raw _mdb.db (5th scheduler block)"
  - "backend/tests/test_ticketing_bridge.py — 4 new `endpoint` tests (success/422/404/502), 18/18 total passing"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI TestClient + app.dependency_overrides[get_current_user] for endpoint tests, mirroring test_tickets.py's _app()/_patched() shape"
    - "Route-level patch.object on the imported module (endpoints_mod.svc.get_task, endpoints_mod.ticketing_bridge.create_ticket_for_remediation_task) rather than patching by string path, since compliance_remediation_endpoints imports both by module reference"

key-files:
  created: []
  modified:
    - backend/compliance_remediation_endpoints.py
    - backend/app_startup.py
    - backend/tests/test_ticketing_bridge.py

key-decisions:
  - "No provider_override ambiguity: the manual endpoint always passes body.provider explicitly to create_ticket_for_remediation_task, distinct from the auto-create hook (43-02) which omits it to fall back to the tenant's configured provider"
  - "Scheduler registration cloned tickets_escalation_service's exact try/except shape verbatim (5th scheduler block) rather than introducing a new registration pattern, per plan's explicit instruction not to alter surrounding blocks"

patterns-established: []

requirements-completed: [REM-01, REM-02]

coverage:
  - id: D1
    description: "POST /tasks/{task_id}/create-ticket creates a ticket via ticketing_bridge with Literal-validated provider, tenant-scoped 404, and 502 on bridge failure"
    requirement: "REM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_ticketing_bridge.py#test_endpoint_create_ticket_success_returns_ticket_fields"
        status: pass
      - kind: unit
        ref: "backend/tests/test_ticketing_bridge.py#test_endpoint_create_ticket_invalid_provider_returns_422"
        status: pass
      - kind: unit
        ref: "backend/tests/test_ticketing_bridge.py#test_endpoint_create_ticket_missing_task_returns_404"
        status: pass
      - kind: unit
        ref: "backend/tests/test_ticketing_bridge.py#test_endpoint_create_ticket_bridge_failure_returns_502"
        status: pass
    human_judgment: false
  - id: D2
    description: "Close-loop scheduler registered at app startup with raw _mdb.db (never get_database), non-fatal on failure"
    requirement: "REM-02"
    verification:
      - kind: unit
        ref: "grep -c 'start_close_loop_scheduler(_mdb.db)' backend/app_startup.py == 1"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live Jira/ServiceNow sandbox verification of the manual create-ticket button end-to-end (real ticket in a real provider)"
    verification: []
    human_judgment: true
    rationale: "Requires a configured Jira/ServiceNow sandbox and live credentials — out of scope for hermetic unit coverage, deferred to UAT per 43-VALIDATION.md"

# Metrics
duration: 3min
completed: 2026-07-21
status: complete
---

# Phase 43 Plan 03: Manual Create-Ticket Endpoint + Close-Loop Scheduler Registration Summary

**`POST /tasks/{task_id}/create-ticket` route exposes the manual "Create Ticket" action with Literal-validated provider and tenant scoping, and the close-loop scheduler is now registered at app startup with the raw `_mdb.db` object (5th scheduler block, cloning `tickets_escalation_service`'s exact shape).**

## Performance

- **Duration:** ~3 min (commit-to-commit)
- **Started:** 2026-07-21T17:55:09+05:30 (approx, first commit)
- **Completed:** 2026-07-21T17:56:45+05:30
- **Tasks:** 3/3 completed
- **Files modified:** 3

## Accomplishments
- `CreateTicketRequest` Pydantic model validates `provider: Literal["jira","servicenow"]`, rejecting arbitrary strings with 422 before any bridge branch logic runs
- `POST /api/compliance-remediation/tasks/{task_id}/create-ticket` reuses `_tenant_filter` + `svc.get_task` (404 for foreign/missing task_id, matching existing routes) and returns 502 when `ticketing_bridge.create_ticket_for_remediation_task` fails, else the ticket provider/ref/url dict
- `TaskUpdate` remains untouched — `ticket_provider`/`ticket_ref`/`ticket_url` stay server-controlled, written only inside the bridge's `$set`, never client-writable
- `app_startup.py` registers `start_close_loop_scheduler(_mdb.db)` via `asyncio.create_task`, wrapped in the same non-fatal try/except shape as the 4 existing scheduler blocks, passing the raw db object (never `get_database()`) so cross-tenant polling doesn't fail closed
- 4 new `endpoint`-named tests added to `test_ticketing_bridge.py` (success/422/404/502) using FastAPI `TestClient` + `dependency_overrides`; full file now 18/18 passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add POST /tasks/{task_id}/create-ticket route + CreateTicketRequest model** - `892fff0` (feat)
2. **Task 2: Register close-loop scheduler in app_startup.py with raw mongodb.db** - `f732e40` (feat)
3. **Task 3: Add endpoint test to test_ticketing_bridge.py** - `01c6916` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/compliance_remediation_endpoints.py` - adds `CreateTicketRequest` model and `create_ticket` route (REM-01)
- `backend/app_startup.py` - registers the close-loop scheduler with raw `_mdb.db` (REM-02)
- `backend/tests/test_ticketing_bridge.py` - adds `endpoint` test coverage (success/422/404/502)

## Decisions Made
- Kept the manual endpoint's `provider_override=body.provider` always explicit (unlike the 43-02 auto-create hook, which intentionally omits it) — the manual button lets the admin pick a provider per-task via `CreateTicketRequest`
- Patched `endpoints_mod.svc.get_task` / `endpoints_mod.ticketing_bridge.create_ticket_for_remediation_task` (module-reference patches) rather than string-path patches, since `compliance_remediation_endpoints.py` imports both modules by reference and calls through the module attribute at request time

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. `pytest tests/test_ticketing_bridge.py -q` (18/18) and `pytest tests/test_remediation_workflow.py -q` (5/5) both pass with no regressions after all 3 tasks.

## User Setup Required

None - no external service configuration required. Live Jira/ServiceNow sandbox verification of the manual create-ticket button (a real ticket appearing in a real provider) remains a manual/UAT gate per `43-VALIDATION.md`, out of scope for this plan's hermetic unit coverage.

## Next Phase Readiness
- Plan 43-04 can build on a fully wired backend: manual endpoint (43-03), auto-create hook (43-02), and now scheduler registration (43-03) are all live — 43-04 covers the frontend provider-picker UI (D-02) consuming this endpoint
- No blockers.

---
*Phase: 43-remediation-to-ticketing-bridge*
*Completed: 2026-07-21*

## Self-Check: PASSED

- FOUND: backend/compliance_remediation_endpoints.py
- FOUND: backend/app_startup.py
- FOUND: backend/tests/test_ticketing_bridge.py
- FOUND: 892fff0 (Task 1 commit)
- FOUND: f732e40 (Task 2 commit)
- FOUND: 01c6916 (Task 3 commit)
