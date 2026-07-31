---
phase: 43-remediation-to-ticketing-bridge
verified: 2026-07-21T13:12:05Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 43: Remediation-to-Ticketing Bridge Verification Report

**Phase Goal:** Wire `compliance_remediation_service` task create/update to the existing Jira/ServiceNow connectors in `ticketing_service.py` through an explicit field adapter (reuse, don't rebuild — connectors currently only serve security-alert tickets), and close the loop when the external ticket resolves.
**Verified:** 2026-07-21T13:12:05Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A compliance admin can create a Jira/ServiceNow ticket directly from a remediation task in the task view, with real fields (not "N/A") populated via an explicit adapter | ✓ VERIFIED | `backend/ticketing_bridge.py::_task_to_alert_shape` (lines 31-55) maps `control_id`/`priority`/`description`/`hostname` from the task doc — `mitre_technique` is the only explicit "N/A" (non-mappable field, by design). `test_adapter_maps_task_fields_to_alert_shape` asserts `alert["description"] != "N/A"` and passes live. Frontend `RemediationTaskModal.tsx` renders a "Create Ticket" button + provider picker (lines 279-358) wired to `POST /tasks/{id}/create-ticket`. Human checkpoint (43-04 Task 3) approved; session's live HTTP tests confirmed 502/422/404 correctness against a fresh backend. |
| 2 | The created ticket's provider, reference ID, and URL are visible on the remediation task afterward | ✓ VERIFIED | `create_ticket_for_remediation_task` `$set`-persists `ticket_provider`/`ticket_ref`/`ticket_url` onto the task (ticketing_bridge.py:86-89). `RemediationTaskModal.tsx` lines 280-307 render the read-only block (provider badge, ref, outbound link) when `task.ticket_ref` is truthy. `types.ts` lines 1704-1706 carry the three fields. Human checkpoint confirmed visually. |
| 3 | When the linked external ticket is closed, the remediation task automatically transitions to Resolved without manual intervention | ✓ VERIFIED (behavioral test) | `run_close_loop_pass` (ticketing_bridge.py:156-207) calls `svc.update_task(db, task_id, {"status": "resolved"}, {"tenantId": tenant_id}, created_by="system:ticket-close-loop")` when `get_jira_issue_status`/`get_servicenow_incident_status` report `closed: True`. `test_close_loop_dispatch_resolves_task_when_ticket_closed` (backend/tests/test_ticketing_bridge.py:276-301) exercises this exact transition and passes live (confirmed by direct run in this session). Scheduler polls every 300s (confirmed `asyncio.sleep(300)` at ticketing_bridge.py:217, no `asyncio.sleep(1200)` anywhere in the file, `grep -c get_database` returns 0). |
| 4 | Resolving a task via ticket closure triggers the existing re-scan dispatch, matching manual-resolution behavior | ✓ VERIFIED | `compliance_remediation_service.update_task` (lines 108-130) dispatches `dispatch_rescan(db, task, created_by)` whenever `updates.get("status") == "resolved"` — this is the exact same code path used for manual resolution (no branching by caller). `run_close_loop_pass` calls this identical function/signature, so re-scan dispatch fires by construction, not by reimplementation. Confirmed by reading the shared function in this session. |

**Score:** 4/4 roadmap success criteria verified.

### PLAN Frontmatter Must-Haves (all 4 plans)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 5 | Adapting a task produces an alert-shaped dict whose mappable fields are never "N/A" | ✓ VERIFIED | See #1 above; `test_adapter_maps_task_fields_to_alert_shape` passes. |
| 6 | `create_ticket_for_remediation_task` creates a real ticket and `$set`-persists ticket fields | ✓ VERIFIED | ticketing_bridge.py:60-91; `test_create_ticket_for_remediation_task_persists_and_returns_fields` passes. |
| 7 | A task with existing `ticket_ref` never gets a second ticket (dedup guard) | ✓ VERIFIED | ticketing_bridge.py:66-67; `test_dedup_task_with_existing_ticket_never_gets_second` passes — asserts `get_ticketing_config`/`create_jira_ticket` never called. |
| 8 | Ticketing not configured → silent no-op | ✓ VERIFIED | ticketing_bridge.py:69-71; `test_no_config_returns_none_and_does_not_raise` passes — asserts `update_one` not called. |
| 9 | Status-check functions classify closed/open without hardcoding SNOW numeric state codes | ✓ VERIFIED | `get_jira_issue_status` uses `statusCategory.key == "done"` (line 118-119); `get_servicenow_incident_status` compares lowercased display-value label against `_SNOW_CLOSED_LABELS = {"closed","resolved"}` (lines 148-149) — no numeric literal present. `test_status_check_jira_closed_and_open`/`test_status_check_servicenow_closed_and_open` pass. |
| 10 | A deleted (404) linked ticket is logged and skipped by the close-loop scheduler, never auto-resolved (D-06) | ✓ VERIFIED (behavioral test) | Both status functions return `{"success": False, "closed": False, "not_found": True}` on `status_code == 404` (lines 112-116, 142-146), distinct from the generic `except` path (no `not_found` key on exception, lines 120-121, 150-151). `run_close_loop_pass` checks `result.get("not_found")` and `continue`s *before* the closed-check (lines 183-189) — a not_found result structurally cannot reach `update_task`. `test_close_loop_deleted_ticket_is_skipped_not_resolved` and `test_close_loop_deleted_ticket_servicenow_variant` both pass live in this session, asserting `mock_update_task.assert_not_called()`. |
| 11 | Close-loop scheduler polls every 5 minutes (D-03 revised) | ✓ VERIFIED | `asyncio.sleep(300)` confirmed present (ticketing_bridge.py:217); `asyncio.sleep(1200)` confirmed absent from the file. |
| 12 | Creating a task at critical/high/medium priority auto-creates a ticket (D-01 revised), non-fatal on failure (D-04) | ✓ VERIFIED | `compliance_remediation_service.py::create_task` lines 71-79 gate on `task.get("priority") in ("critical", "high", "medium")` (confirmed exact tuple in source), wrapped in try/except logging a warning, never re-raising. `test_autocreate_nonfatal` passes live in this session, and this session's live HTTP test confirmed the medium-priority auto-create firing against a fresh backend. |

**Combined score:** 12/12 must-haves verified (4 roadmap SCs + 8 plan-frontmatter truths, deduplicated against overlapping SCs).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/ticketing_bridge.py` | Adapter, orchestration, status-check, close-loop scheduler | ✓ VERIFIED | 217 lines. Exports `_task_to_alert_shape`, `create_ticket_for_remediation_task`, `get_jira_issue_status`, `get_servicenow_incident_status`, `_SNOW_CLOSED_LABELS`, `run_close_loop_pass`, `start_close_loop_scheduler`. Zero `get_database` references. |
| `backend/tests/test_ticketing_bridge.py` | Unit coverage for all 9 `-k` selectors + `endpoint` | ✓ VERIFIED | 18 tests, all pass live (`pytest tests/test_ticketing_bridge.py -q` → 18 passed). |
| `backend/compliance_remediation_service.py` | Auto-create hook in `create_task` | ✓ VERIFIED | Priority-gated hook present, non-blocking try/except, `create_task` still returns persisted task unchanged. |
| `backend/tests/test_remediation_workflow.py` | `autocreate_nonfatal` coverage | ✓ VERIFIED | `test_autocreate_nonfatal` passes live; full file 5/5 passing. |
| `backend/compliance_remediation_endpoints.py` | `POST /tasks/{task_id}/create-ticket` route + `CreateTicketRequest` | ✓ VERIFIED | `CreateTicketRequest.provider: Literal["jira","servicenow"]` present; route uses `_tenant_filter`+`svc.get_task` (404), `ticketing_bridge.create_ticket_for_remediation_task` with `provider_override=body.provider`, 502 on falsy result. `TaskUpdate` model contains none of `ticket_provider`/`ticket_ref`/`ticket_url`. |
| `backend/app_startup.py` | Close-loop scheduler registration with raw `_mdb.db` | ✓ VERIFIED | `start_close_loop_scheduler(_mdb.db)` present via `asyncio.create_task`, wrapped in try/except, non-fatal warning log, matches sibling scheduler block pattern. |
| `types.ts` | `ticket_provider`/`ticket_ref`/`ticket_url` on `RemediationTask` | ✓ VERIFIED | Lines 1704-1706, all optional. |
| `services/apiService.ts` | `createTicketForRemediationTask` + `getTicketingConfig` wrappers | ✓ VERIFIED | Lines 4535-4555. POST throws on non-2xx; GET is safe-default (try/catch returns `{}`). |
| `components/RemediationTaskModal.tsx` | Ticketing section (button, picker, display block) | ✓ VERIFIED | `handleCreateTicket` (lines 98-111) clones `handleSuggest`'s async-action+toast shape exactly. Three-state render (lines 279-358) matches UI-SPEC: ticket_ref truthy → read-only block; unsaved/unconfigured → hidden; otherwise → button (+ picker only when both configured). `hasJira`/`hasServiceNow` derived from a `getTicketingConfig()` effect on modal open (lines 68-76). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `ticketing_bridge.py::create_ticket_for_remediation_task` | `ticketing_service.py::create_jira_ticket`/`create_servicenow_incident` | adapted alert-shaped payload | ✓ WIRED | Confirmed at ticketing_bridge.py:77,80 — `ticketing_service.py` connectors imported and called unmodified (git log confirms no phase-43 commits touched `ticketing_service.py`). |
| `ticketing_bridge.py::run_close_loop_pass` | `compliance_remediation_service.py::update_task` | reused verbatim, lazy import | ✓ WIRED | ticketing_bridge.py:192-196; `update_task`'s existing `dispatch_rescan` call (lines 129-130) fires by construction, not reimplementation. |
| `compliance_remediation_endpoints.py::create_ticket` | `ticketing_bridge.py::create_ticket_for_remediation_task` | `provider_override=body.provider` | ✓ WIRED | endpoints.py:196-198. |
| `app_startup.py` | `ticketing_bridge.py::start_close_loop_scheduler` | `asyncio.create_task(start_close_loop_scheduler(_mdb.db))` | ✓ WIRED | app_startup.py:611-614. |
| `compliance_remediation_service.py::create_task` | `ticketing_bridge.py::create_ticket_for_remediation_task` | priority-gated try/except, lazy import | ✓ WIRED | compliance_remediation_service.py:71-79. |
| `RemediationTaskModal.tsx::handleCreateTicket` | `apiService.ts::createTicketForRemediationTask` | `await api.createTicketForRemediationTask(task.id, provider)` | ✓ WIRED | RemediationTaskModal.tsx:102. |
| `apiService.ts::createTicketForRemediationTask` | `POST /api/compliance-remediation/tasks/{id}/create-ticket` | `authFetch` | ✓ WIRED | apiService.ts:4539. |

### Behavioral Spot-Checks (this session, live)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Close-loop resolves task on ticket closed (state transition) | `pytest tests/test_ticketing_bridge.py -k close_loop_dispatch -q` (part of full-file run) | passed | ✓ PASS |
| Deleted ticket (404) skipped, never auto-resolved (D-06 invariant) | `pytest tests/test_ticketing_bridge.py -k deleted_ticket -v` | 2 passed | ✓ PASS |
| Auto-create hook non-fatal + widened threshold (D-01 revised) | `pytest tests/test_remediation_workflow.py -k autocreate_nonfatal -v` | 1 passed | ✓ PASS |
| Full ticketing_bridge suite | `pytest tests/test_ticketing_bridge.py -q` | 18 passed | ✓ PASS |
| Full remediation_workflow suite (regression) | `pytest tests/test_remediation_workflow.py -q` | 5 passed | ✓ PASS |
| Frontend build | `npm run build` | built in 4.62s, no type errors | ✓ PASS |
| D-06 404 handling present in both status functions | `grep -n "status_code == 404" backend/ticketing_bridge.py` | 2 matches, distinct from generic except | ✓ PASS |
| D-03 revised poll interval | `grep -n "asyncio.sleep(300)" backend/ticketing_bridge.py`; `grep -c "asyncio.sleep(1200)"` | 300 present, 1200 absent | ✓ PASS |
| D-01 revised priority gate | `grep -n 'in ("critical", "high", "medium")' backend/compliance_remediation_service.py` | present verbatim | ✓ PASS |
| No `get_database` in scheduler module | `grep -c get_database backend/ticketing_bridge.py` | 0 | ✓ PASS |
| `ticketing_service.py` unmodified by this phase | `git log --oneline -- backend/ticketing_service.py` shows no 43-0x commits | confirmed | ✓ PASS |

Note: This session's own live HTTP verification (documented in the task instructions) additionally confirmed 502/422/404 endpoint behavior and D-01's medium-priority auto-create firing against a fresh, non-stale backend instance — corroborating the static/unit evidence above rather than substituting for it.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REM-01 | 43-01, 43-02, 43-03, 43-04 | Create a Jira/ServiceNow ticket from a remediation task with correctly-mapped fields via an explicit adapter | ✓ SATISFIED | Adapter (ticketing_bridge.py), auto-create hook (compliance_remediation_service.py), manual endpoint (compliance_remediation_endpoints.py), frontend UI (RemediationTaskModal.tsx) all confirmed present and wired. |
| REM-02 | 43-01, 43-03 | Closed external ticket auto-resolves the remediation task and triggers the existing re-scan dispatch | ✓ SATISFIED | Close-loop scheduler (ticketing_bridge.py), reused `update_task` (dispatch_rescan fires on status=resolved), scheduler registered at app startup with raw db. |

No orphaned requirements — REQUIREMENTS.md maps only REM-01/REM-02 to Phase 43, and both are declared in plan frontmatter `requirements:` fields.

### Anti-Patterns Found

None. Scanned all 9 phase-modified files (`backend/ticketing_bridge.py`, `backend/compliance_remediation_service.py`, `backend/compliance_remediation_endpoints.py`, `backend/app_startup.py`, `backend/tests/test_ticketing_bridge.py`, `backend/tests/test_remediation_workflow.py`, `types.ts`, `services/apiService.ts`, `components/RemediationTaskModal.tsx`) for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` — zero matches.

### Human Verification Required

None. The one item requiring human judgment (Success Criteria 1-2, visual/interaction confirmation of the frontend Ticketing UI) was already completed as a blocking `checkpoint:human-verify` gate in 43-04 (Task 3) and approved by the user during execution, per 43-04-SUMMARY.md and this session's task instructions. The behavior-dependent truth (Success Criterion 3, auto-resolve state transition) is covered by a passing named behavioral test (`test_close_loop_dispatch_resolves_task_when_ticket_closed`), independently re-run and confirmed passing in this verification session — so it resolves to VERIFIED, not PRESENT_BEHAVIOR_UNVERIFIED.

### Gaps Summary

No gaps found. All 4 ROADMAP success criteria and all plan-frontmatter must-haves are verified against the actual codebase (not SUMMARY.md claims) via direct source reading and live test execution in this session. `ticketing_service.py`'s connectors were confirmed unmodified (reuse, not rebuild, per the phase goal). The D-01/D-03/D-06 mid-phase revisions were confirmed actually implemented in source — `asyncio.sleep(300)` (not 1200), the widened `("critical","high","medium")` priority gate (not `("high","critical")`), and the 404/`not_found` handling in both status-check functions with `run_close_loop_pass` never calling `update_task` on a `not_found` result.

---

*Verified: 2026-07-21T13:12:05Z*
*Verifier: Claude (gsd-verifier)*
