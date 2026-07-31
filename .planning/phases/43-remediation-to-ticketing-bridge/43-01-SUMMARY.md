---
phase: 43-remediation-to-ticketing-bridge
plan: 01
subsystem: api
tags: [jira, servicenow, ticketing, asyncio-scheduler, fastapi, pytest]

# Dependency graph
requires:
  - phase: 04-remediation-workflow
    provides: compliance_remediation_service.update_task (reused verbatim for close-loop resolution) and the compliance_remediation_tasks collection shape
affects: [43-02, 43-03, 43-04]
provides:
  - "backend/ticketing_bridge.py — _task_to_alert_shape adapter, create_ticket_for_remediation_task orchestration, get_jira_issue_status/get_servicenow_incident_status, run_close_loop_pass, start_close_loop_scheduler"
  - "backend/tests/test_ticketing_bridge.py — 14 hermetic unit tests covering all 9 required -k selectors"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw-db background scheduler: scheduler functions take db as a passed-in parameter, never resolve it internally (compliance_remediation_tasks is not tenant-isolation-exempt, so a bare asyncio.create_task scheduler calling the request-scoped accessor would silently fail closed)"
    - "Non-fatal external-call error handling: every new function returns a falsy/error dict on failure rather than raising"
    - "not_found (404) branch distinct from generic exception handling — deleted tickets are logged and skipped, never treated as ambiguous-evidence auto-resolve"

key-files:
  created:
    - backend/ticketing_bridge.py
    - backend/tests/test_ticketing_bridge.py
  modified: []

key-decisions:
  - "D-03 (revised 2026-07-21): close-loop scheduler polls every 300s (5 min), matching tickets_escalation_service.py's existing interval — not the original 1200s in 43-PATTERNS.md, which predates the plan revision"
  - "D-06: get_jira_issue_status/get_servicenow_incident_status return {success:False, closed:False, not_found:True} on HTTP 404, and run_close_loop_pass checks not_found before the closed-check so a deleted ticket is skipped, never auto-resolved"

patterns-established:
  - "Alert-shape adapter (_task_to_alert_shape) as the single translation point between a domain document (compliance_remediation_tasks) and the ticketing_service.py connector contract — connectors themselves are never modified"

requirements-completed: [REM-01, REM-02]

# Metrics
duration: 3min
completed: 2026-07-21
status: complete
---

# Phase 43 Plan 01: Ticketing Bridge Adapter, Orchestration, Status Checks, Close-Loop Scheduler Summary

**New `backend/ticketing_bridge.py` module wiring `compliance_remediation_tasks` to the existing Jira/ServiceNow connectors via an alert-shape adapter, with a 5-minute close-loop scheduler that auto-resolves tasks through the reused `update_task`, and 14 passing hermetic unit tests.**

## Performance

- **Duration:** ~3 min (commit-to-commit)
- **Started:** 2026-07-21T12:09:00Z (approx)
- **Completed:** 2026-07-21T12:12:11Z
- **Tasks:** 3/3 completed
- **Files modified:** 2 (both new)

## Accomplishments
- `_task_to_alert_shape` adapts a remediation task into the alert dict shape `create_jira_ticket`/`create_servicenow_incident` already expect — no connector changes needed
- `create_ticket_for_remediation_task` dedup-guards on existing `ticket_ref`, no-ops silently when ticketing isn't configured, and `$set`-persists `ticket_provider`/`ticket_ref`/`ticket_url` only on success
- `get_jira_issue_status`/`get_servicenow_incident_status` classify closed/open provider-agnostically (Jira `statusCategory.key == "done"`, ServiceNow display-value label vs. `_SNOW_CLOSED_LABELS`) and return an explicit `not_found` signal on HTTP 404
- `run_close_loop_pass`/`start_close_loop_scheduler` poll every 300s, resolve closed-ticket tasks via `compliance_remediation_service.update_task(status="resolved")` (re-scan dispatch fires by construction), skip deleted (404) tickets without resolving them, and never call `get_database()` internally
- 14 unit tests in `test_ticketing_bridge.py`; all 9 required `-k` selectors (`adapter`, `create_ticket`, `no_config`, `dedup`, `status_check`, `close_loop_dispatch`, `close_loop_skip`, `raw_db_registration`, `deleted_ticket`) pass individually and as a suite

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ticketing_bridge.py adapter + ticket-creation orchestration + status checks** - `7bfe1db` (feat)
2. **Task 2: Add close-loop scheduler (run_close_loop_pass + start_close_loop_scheduler)** - `1542347` (feat)
3. **Task 3: Create test_ticketing_bridge.py covering adapter/create/no_config/dedup/status/close-loop/raw-db** - `524895c` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/ticketing_bridge.py` - adapter, orchestration, status checks, close-loop scheduler (REM-01/REM-02 core)
- `backend/tests/test_ticketing_bridge.py` - 14 hermetic unit tests, no live Jira/ServiceNow dependency

## Decisions Made
- Followed the plan's revised D-03 (300s/5min poll interval) over the older 1200s value still present in `43-PATTERNS.md`'s code example — the plan frontmatter explicitly flagged this as a post-plan-checker revision
- Followed D-06 (404/not_found handling) exactly as specified in the plan, since `43-PATTERNS.md`'s scheduler snippet predates this addition
- Rephrased two docstring sentences that referenced `get_database()` by name, since a literal grep for that string is one of the plan's acceptance-criteria regression guards (`grep -c get_database backend/ticketing_bridge.py` must return 0) — no behavior change, docstring wording only
- Named all test functions to contain their required `-k` selector token verbatim (e.g. `test_status_check_jira_closed_and_open`) so every acceptance-criteria selector command resolves correctly

## Deviations from Plan

None - plan executed exactly as written (including its own explicit corrections to 43-PATTERNS.md's now-superseded 1200s interval and missing 404 handling).

## Issues Encountered

None. Full backend suite run after all 3 tasks: 1330 passed / 34 skipped / 5 failed — all 5 failures confirmed pre-existing and unrelated to `ticketing_bridge.py`/`test_ticketing_bridge.py` (`test_webhook_logic.py` Jira/Zoho intent parsing event-loop errors, `test_agentic_ai.py` tool_choice kwarg mismatch, `test_e2e_integration.py` golden-path evidence assertion, `test_rust_heartbeat_parity.py` missing `agent_type` — the last two are logged as pre-existing in STATE.md's session history from prior phases, tied to an uncommitted `agent-rust/` tree already present before this plan started). Three additional test-collection errors (`backend/test_ai_service_config.py`, `backend/test_network_endpoint.py`, `backend/test_sbom_api.py`) require live network/server access and are excluded from this run per the project's pre-existing environmental constraints — not files this plan touches.

## User Setup Required

None - no external service configuration required. Live Jira/ServiceNow sandbox verification (auto-create on task creation, real close-loop resolution) remains a manual/UAT gate per `43-VALIDATION.md`, out of scope for this plan's hermetic unit coverage.

## Next Phase Readiness
- `ticketing_bridge.py` exports everything plans 43-02 (auto-create hook + endpoint), 43-03 (frontend), and 43-04 (app-startup scheduler registration) depend on: `create_ticket_for_remediation_task`, `get_jira_issue_status`, `get_servicenow_incident_status`, `start_close_loop_scheduler`
- No blockers. `ticketing_service.py`, `compliance_remediation_service.py`, and `integration_service_ticketing.py` were confirmed unmodified per the plan's scope boundary.

---
*Phase: 43-remediation-to-ticketing-bridge*
*Completed: 2026-07-21*

## Self-Check: PASSED

- FOUND: backend/ticketing_bridge.py
- FOUND: backend/tests/test_ticketing_bridge.py
- FOUND: 7bfe1db (Task 1 commit)
- FOUND: 1542347 (Task 2 commit)
- FOUND: 524895c (Task 3 commit)
