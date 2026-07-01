---
phase: 04-remediation-workflow
plan: "01"
subsystem: compliance
tags: [fastapi, mongodb, pydantic, socketio, typescript, remediation, websocket]

requires:
  - phase: 04-00
    provides: test scaffold (REM-01..04), broadcast_remediation_update in websocket_manager, Rust dispatch arm for "Run Compliance Scan"

provides:
  - backend/compliance_remediation_service.py with create_task/list_tasks/get_task/update_task/dispatch_rescan
  - backend/compliance_remediation_endpoints.py router at /api/compliance-remediation with POST/GET/PATCH /tasks and POST /tasks/{id}/suggest
  - ai_service.IncidentAnalyzer.suggest_remediation (5-line method routing through generate_text with guardrails)
  - REM-04 broadcast hook in agent_tasks_endpoints.report_instruction_result
  - RemediationTask TypeScript interface and AppView 'remediationWorkflow' in types.ts
  - createRemediationTask/getRemediationTasks/updateRemediationTask/suggestRemediation in services/apiService.ts

affects: [04-02-wave2-ui, 05-integration-e2e]

tech-stack:
  added: []
  patterns:
    - "svc.* service-module pattern: pure async DB logic separated from endpoint layer (mirrors mdr_service / mdr_endpoints split)"
    - "dispatch_rescan two-hop resolution: agent_id from task else asset.agentId; non-fatal on missing agent"
    - "_tenant_filter(user): returns {} for super-admins, {tenantId: ...} for tenants — copy from mdr_endpoints"
    - "broadcast_remediation_update called in two places: PATCH /tasks (optimistic) and report_instruction_result (evidence-complete)"

key-files:
  created:
    - backend/compliance_remediation_service.py
    - backend/compliance_remediation_endpoints.py
  modified:
    - backend/ai_service.py
    - backend/agent_tasks_endpoints.py
    - backend/router_registry.py
    - types.ts
    - services/apiService.ts

key-decisions:
  - "compliance_remediation_tasks collection name avoids collision with remediation_tasks (continuous_compliance_service)"
  - "Router prefix /api/compliance-remediation avoids collision with /api/remediation (vulnerability domain)"
  - "suggest_remediation fits in 5 lines (def + docstring + 2-line f-string + return) keeping ai_service.py at 499 lines"
  - "broadcast_remediation_update in report_instruction_result wrapped in try/except so a broadcast failure never breaks result posting"
  - "compliance_remediation_endpoints registered in REQUIRED block (not _OPTIONAL) so import errors are surfaced"

patterns-established:
  - "Two-stage broadcast: PATCH endpoint broadcasts on dispatch (optimistic UI); agent result endpoint broadcasts on evidence (data-complete)"
  - "to_list(length=500) DoS cap on all list queries over compliance_remediation_tasks"

requirements-completed: [REM-01, REM-02, REM-03, REM-04]

duration: ~4min
completed: 2026-06-17
---

# Phase 04 Plan 01: Compliance Remediation Workflow — Backend + Contracts Summary

**Tenant-scoped CRUD over compliance_remediation_tasks, AI-suggested steps via guardrail-wrapped LLM, agent rescan dispatch on Resolve, real-time remediation_update broadcasts, and TypeScript contracts for Wave 2 UI**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-17T19:36:47Z
- **Completed:** 2026-06-17T19:40:24Z
- **Tasks:** 3
- **Files modified:** 7 (2 new, 5 modified)

## Accomplishments

- Created `compliance_remediation_service.py` with full tenant-scoped CRUD and `dispatch_rescan` that resolves agent_id via two-hop asset lookup and inserts "Run Compliance Scan" to `agent_instructions`
- Added `suggest_remediation` to `IncidentAnalyzer` (5 lines, ai_service.py stays at 499 lines); routes through `generate_text(source='remediation_suggestion')` for input/output guardrail scanning
- Wired REM-04: `report_instruction_result` broadcasts `remediation_update` events for open tasks matching compliance check control IDs after evidence is processed
- All 4 test cases (REM-01, REM-02, REM-03, REM-04) pass with venv python

## Task Commits

1. **Task 1: Service module + AI suggestion method** - `54539ac` (feat)
2. **Task 2: HTTP router + registration + REM-04 broadcast hook** - `9ad9b49` (feat)
3. **Task 3: Frontend RemediationTask type + apiService helpers** - `0177dba` (feat)

## Files Created/Modified

- `backend/compliance_remediation_service.py` — Pure async DB logic for compliance_remediation_tasks; exports create_task/list_tasks/get_task/update_task/dispatch_rescan (165 lines)
- `backend/compliance_remediation_endpoints.py` — APIRouter at /api/compliance-remediation with POST/GET /tasks, PATCH /tasks/{id}, POST /tasks/{id}/suggest (166 lines)
- `backend/ai_service.py` — Added suggest_remediation to IncidentAnalyzer (499 lines total)
- `backend/agent_tasks_endpoints.py` — Added REM-04 broadcast block in report_instruction_result (340 lines)
- `backend/router_registry.py` — Added _load line for compliance_remediation_endpoints in Compliance & Governance block (283 lines)
- `types.ts` — Added RemediationTask interface and 'remediationWorkflow' to AppView union
- `services/apiService.ts` — Added createRemediationTask/getRemediationTasks/updateRemediationTask/suggestRemediation

## Decisions Made

- `compliance_remediation_tasks` collection name chosen to avoid collision with `remediation_tasks` (continuous_compliance_service per 04-RESEARCH.md Anti-Pattern)
- Router prefix `/api/compliance-remediation` chosen to avoid collision with `/api/remediation` (vulnerability domain owned by `remediation_endpoints.py`)
- `suggest_remediation` kept to 5 lines with a 2-part f-string prompt to stay within the 7-line constraint and preserve ai_service.py under 500 lines
- REM-04 broadcast wrapped in `try/except` so broadcast failures are non-fatal to the result-posting flow
- Registered in REQUIRED section of router_registry (not _OPTIONAL) so import errors surface

## Deviations from Plan

None — plan executed exactly as written. The broadcast hook in `report_instruction_result` queries `compliance_remediation_tasks.find()` per control_id rather than a single bulk lookup; this is consistent with correctness (per-control matching) and within the `to_list(length=50)` safety cap.

## Issues Encountered

- `python3` (system Python, no venv) lacks `socketio` module, causing REM-04 to fail under system Python. All 4 tests pass under `backend/venv/bin/python3`. This is the same environment constraint as prior phases (04-00 noted this for REM-04). The 3 plan-new tests (REM-01/02/03) pass under both system and venv Python.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Wave 2 (04-02) can import RemediationTask from types.ts and call all four apiService helpers
- Backend CRUD is fully wired; compliance_remediation_tasks collection will be auto-created by MongoDB on first insert
- broadcast_remediation_update in websocket_manager is ready for the UI's Socket.IO event listener

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond those in the plan's threat model. T-04-03 through T-04-07 mitigations applied:
- `_tenant_filter` applied to all queries
- Pydantic `Field(min_length, max_length)` on title and description
- `to_list(length=500)` DoS cap on list queries
- `generate_text(source='remediation_suggestion')` routes through guardrail_service

## Self-Check: PASSED
