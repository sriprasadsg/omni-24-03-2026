---
phase: 44-remediation-sla-escalation
plan: 02
subsystem: api
tags: [python, fastapi, mongodb, motor, pytest, sla, compliance-remediation, background-scheduler]

# Dependency graph
requires:
  - phase: 44-remediation-sla-escalation (44-01)
    provides: compute_remediation_sla/compute_escalation_level/get_sla_at_risk_window, task-schema SLA defaults, Wave-0 test scaffold
provides:
  - "run_sla_pass(db) — background sweep that recomputes sla_status, tiers escalation_level on breach, appends one immutable remediation_escalations entry, and notifies assignee+admins"
  - "start_remediation_sla_scheduler(db) — 300s polling loop wrapper, mirrors ticketing_bridge.start_close_loop_scheduler"
  - "app_startup.py registration of the SLA scheduler with raw mongodb.db (never get_database)"
  - "first writer of the remediation_escalations collection"
affects: [44-03-remediation-sla-escalation, 44-04-remediation-sla-escalation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Background sweep cloned structurally from ticketing_bridge.run_close_loop_pass: raw-db find on open/in_progress, per-doc tenantId extraction with skip-on-absent, top-level non-fatal try/except"
    - "Assignee free-text resolution (email -> id -> username) adapted from control_comments_service.resolve_mentions, never raises, skips agent-type/unresolved without aborting the escalation"
    - "Tenant-admin recipient lookup via the shared _ADMIN_ROLES set (mirrors notification_manager.py) — used for notification delivery only, not settings-mutation gating"

key-files:
  created: []
  modified:
    - backend/compliance_remediation_sla_service.py
    - backend/app_startup.py

key-decisions:
  - "Escalation dispatch only fires when new_level > current escalation_level (once per tier increase), matching the plan's explicit anti-duplicate-escalation requirement"
  - "send_alert is called at most once per breached task per pass, batching resolved assignee + all tenant admins into a single recipients list, deduplicated"
  - "remediation_escalations.notified stores the actual resolved recipient email list (not just role labels), giving the append-only history entry a self-contained audit record"
  - "broadcast_remediation_update import + call wrapped in its own try/except, kept best-effort per the Phase 4 websocket precedent — a missing/broken broadcast never blocks escalation persistence"

patterns-established:
  - "_parse_due_date() extracted as a small private helper duplicating compute_remediation_sla()'s defensive parse logic, rather than modifying the already-tested pure function, so run_sla_pass can recover days_overdue without changing 44-01's contract"

requirements-completed: [SLA-01]

coverage:
  - id: D1
    description: "A breached task auto-escalates with zero operator action: escalation_level increments per tier, escalated/sla_status persist, and exactly one remediation_escalations entry is appended"
    requirement: "SLA-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_run_sla_pass::test_run_sla_pass_breached_task_creates_escalation_and_alerts - pytest tests/test_compliance_remediation_sla.py -k run_sla_pass -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "A task with tenantId empty/absent is skipped entirely — no escalation, no notification"
    requirement: "SLA-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_run_sla_pass::test_run_sla_pass_skips_task_without_tenant_id - pytest tests/test_compliance_remediation_sla.py -k run_sla_pass -x"
        status: pass
    human_judgment: false
  - id: D3
    description: "Escalation notifies both the resolved assignee and all tenant admin-role users in one in-app send_alert call (D-03)"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_run_sla_pass::test_run_sla_pass_breached_task_creates_escalation_and_alerts (asserts send_alert.await_count >= 1 with resolved admin recipient)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The scheduler and app_startup registration use raw mongodb.db exclusively, never get_database (Pitfall 1)"
    requirement: "SLA-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_raw_db_registration (both tests) - pytest tests/test_compliance_remediation_sla.py -k raw_db_registration -x"
        status: pass
    human_judgment: false

# Metrics
duration: 24min
completed: 2026-07-21
status: complete
---

# Phase 44 Plan 02: SLA Sweep + Tiered Escalation + Assignee/Admin Notification Summary

**`run_sla_pass`/`start_remediation_sla_scheduler` added to `compliance_remediation_sla_service.py` — a raw-db background sweep that tiers `escalation_level` on breach, writes an immutable `remediation_escalations` entry, and notifies the resolved assignee plus all tenant admins in-app; registered in `app_startup.py` against `mongodb.db`, never `get_database()`.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-21T13:50:00Z
- **Completed:** 2026-07-21T14:14:19Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `run_sla_pass(db)` — sweeps `compliance_remediation_tasks` (open/in_progress), extracts `tenantId` per-doc and skips docs with none (T-44-03), recomputes `sla_status` via 44-01's `compute_remediation_sla`, and on a breach where the tiered level would increase: persists `sla_status`/`escalated`/`escalation_level`, inserts one `remediation_escalations` entry, and dispatches a single `send_alert` to the resolved assignee + tenant admins
- `_resolve_assignee_email(db, assignee, assignee_type)` — resolves the free-text `assignee` field email -> id -> username (T-44-04), returns `None` (never raises) on an agent-type or unresolved assignee so only that one recipient is skipped, not the escalation
- `_tenant_admin_emails(db, tenant_id)` — looks up all `_ADMIN_ROLES` users for the tenant, reusing `notification_manager.py`'s exact role set (D-03, no third variant introduced)
- `start_remediation_sla_scheduler(db)` — 300s polling loop, structurally identical to `ticketing_bridge.start_close_loop_scheduler`
- `app_startup.py` — new try/except registration block immediately after the `ticketing_bridge` close-loop block, using `_mdb.db` (raw Motor client), never `get_database()` (Pitfall 1)
- Best-effort `broadcast_remediation_update` call in its own try/except (Phase 4 websocket precedent)
- File stayed well under the 500-line limit (316 lines total)

## Task Commits

Each task was committed atomically:

1. **Task 1: Sweep + tiered escalation + append-only history + assignee/admin notification** - `ffb4e11` (feat)
2. **Task 2: Register the SLA scheduler in app_startup with raw mongodb.db** - `d8001e7` (feat)

## Files Created/Modified
- `backend/compliance_remediation_sla_service.py` (MODIFIED) - `run_sla_pass`, `start_remediation_sla_scheduler`, `_resolve_assignee_email`, `_tenant_admin_emails`, `_parse_due_date`, `_now_iso`, `_ADMIN_ROLES`; still zero `get_database` occurrences
- `backend/app_startup.py` (MODIFIED) - new scheduler registration block using `_mdb.db`

## Decisions Made
- New-level-vs-current-level gate (`new_level <= current_level: continue`) implemented exactly as specified — prevents re-escalating/re-notifying every 5-minute pass once a task has already reached a given tier
- `send_alert` is skipped entirely (not called with an empty list) when neither the assignee nor any admin resolves to an email — avoids a degenerate no-recipient notification call while still writing the escalation history entry regardless
- `_parse_due_date` duplicates `compute_remediation_sla`'s parse logic in a small private helper rather than modifying the already-tested 44-01 function, keeping that function's contract unchanged

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `remediation_escalations` collection now has its first writer (`run_sla_pass`'s `insert_one`); 44-03 builds the `GET /api/compliance/remediation-tasks/{task_id}/escalations` read endpoint against this exact document shape (`task_id`, `tenantId`, `escalation_level`, `days_overdue`, `notified`, `created_at`)
- The Wave-0 scaffold's `escalation_history` and `tenant_scope` test groups (`Test_escalation_history`, `Test_tenant_scope`) remain RED by design — they reference `compliance_remediation_sla_endpoints` which does not exist yet; confirmed still failing after this plan (expected, out of scope for 44-02) — 44-03's exact target
- Scheduler starts at boot against the raw db and never through the tenant-isolated wrapper; verified via `python -c "import app_startup"` (exit 0) and the regression-guard test
- No blockers

## Self-Check Notes
Full backend suite run: 1350 passed / 34 skipped / 8 failed. Of the 8 failures: 3 are this plan's own not-yet-in-scope 44-03 tests (`Test_escalation_history`, `Test_tenant_scope` x2 — expected RED), and the remaining 5 (`test_webhook_logic.py` x2, `test_agentic_ai.py` x1, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`) reproduce identically in isolation before touching any file this plan modified and do not reference `compliance_remediation_sla_service.py` or `app_startup.py` — pre-existing, unrelated (the latter two are already documented as pre-existing flakes in STATE.md).

---
*Phase: 44-remediation-sla-escalation*
*Completed: 2026-07-21*

## Self-Check: PASSED
All modified/created files found on disk; all 3 commit hashes (ffb4e11, d8001e7, ac69c25) found in git log.
