---
phase: 44-remediation-sla-escalation
plan: 01
subsystem: api
tags: [python, fastapi, mongodb, motor, pytest, sla, compliance-remediation]

# Dependency graph
requires:
  - phase: 43-remediation-to-ticketing-bridge
    provides: compliance_remediation_tasks schema/service conventions, ticketing_bridge.py raw-db sweep pattern
provides:
  - "compute_remediation_sla() day-scale pure SLA-status compute (ok/at_risk/breached/none)"
  - "compute_escalation_level() tiered escalation level (1/3/7 days past due)"
  - "get_sla_at_risk_window() per-tenant configurable at-risk window, tenant->global->default lookup"
  - "compliance_remediation_tasks task-schema SLA defaults (sla_status/escalated/escalation_level) on create_task"
  - "compliance_remediation_tasks compound indexes (tenantId,due_date,status) and (tenantId,escalated)"
  - "Wave-0 test scaffold (test_compliance_remediation_sla.py) covering all 5 verification-map rows"
affects: [44-02-remediation-sla-escalation, 44-03-remediation-sla-escalation, 44-04-remediation-sla-escalation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure day-scale SLA compute function, cloned defensive-parsing shape only from tickets_helpers._compute_sla(), not its hour-scale threshold"
    - "Per-tenant configurable setting via system_settings tenant-doc -> global-doc -> hardcoded-default lookup, cloned verbatim from evidence_staleness.get_staleness_threshold()"
    - "Wave-0 RED test scaffold: not-yet-existing symbols guarded with try/except ImportError at module import, referenced inside test bodies so collection always succeeds and un-implemented groups fail as normal assertions, not collection errors"

key-files:
  created:
    - backend/compliance_remediation_sla_service.py
    - backend/tests/test_compliance_remediation_sla.py
  modified:
    - backend/compliance_remediation_service.py
    - backend/database.py

key-decisions:
  - "sla_status defaults to 'ok' when due_date is set at creation, 'none' when absent — the 44-02 sweep recomputes it on first pass regardless"
  - "TaskUpdate (compliance_remediation_endpoints.py) reviewed and left unchanged — sla_status/escalated/escalation_level confirmed absent from its writable fields (D-01 system-managed-only)"
  - "_mock_db() wires db._db = db so the get_sla_at_risk_window() dual-call-site unwrap guard (db._db if hasattr(db,'_db') else db) resolves to the same configured mock instead of an auto-generated child MagicMock — MagicMock auto-creates any attribute, so hasattr(db,'_db') is always True"

patterns-established:
  - "Wave-0 scaffold groups named as classes (Test_compute_sla, Test_run_sla_pass, ...) containing the literal -k selector as a substring, guaranteeing -k selector matches regardless of pytest keyword-matching case sensitivity"

requirements-completed: [SLA-01]

coverage:
  - id: D1
    description: "compute_remediation_sla() returns ok/at_risk/breached/none at day-scale boundaries driven by a configurable at-risk window"
    requirement: "SLA-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_compute_sla (11 tests) - pytest tests/test_compliance_remediation_sla.py -k compute_sla -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "New remediation tasks persist sla_status/escalated/escalation_level defaults (D-01) and compliance_remediation_tasks has supporting compound indexes"
    requirement: "SLA-01"
    verification:
      - kind: unit
        ref: "backend/compliance_remediation_service.py create_task dict + backend/database.py create_index calls (verified via inline python -c assertion, see plan verify command)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Wave-0 test scaffold covers all 5 phase verification-map rows (compute_sla, run_sla_pass, raw_db_registration, escalation_history, tenant_scope) and collects cleanly"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py - pytest --collect-only -q (18 items across 5 classes)"
        status: pass
    human_judgment: false

# Metrics
duration: 55min
completed: 2026-07-21
status: complete
---

# Phase 44 Plan 01: SLA Compute Core + Task-Schema Defaults + Wave-0 Scaffold Summary

**New `compliance_remediation_sla_service.py` (day-scale `compute_remediation_sla`, tiered `compute_escalation_level`, configurable `get_sla_at_risk_window`), `create_task` SLA defaults, `compliance_remediation_tasks` compound indexes, and the full 18-test Wave-0 scaffold (`test_compliance_remediation_sla.py`) all five later 44-02/44-03 plans verify against.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-07-21T13:10:00Z
- **Completed:** 2026-07-21T14:05:21Z
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `compute_remediation_sla(task, at_risk_window_days)` — pure day-scale SLA status compute (`ok`/`at_risk`/`breached`/`none`), resolved-task short-circuit, defensive due-date parsing (never raises)
- `compute_escalation_level(days_overdue)` — tiered level per D-04 (`_TIER_DAYS = [1, 3, 7]`)
- `get_sla_at_risk_window(db, tenant_id)` — tenant-doc -> global-doc -> hardcoded-default-3 lookup, cloned from `evidence_staleness.get_staleness_threshold()`, clamped to minimum 1
- `create_task` now persists `sla_status`/`escalated`/`escalation_level` defaults on every new remediation task (D-01)
- Two new compound indexes on `compliance_remediation_tasks` — `(tenantId, due_date, status)` and `(tenantId, escalated)` — closing the full-collection-scan risk (T-44-02)
- `test_compliance_remediation_sla.py`: 18 tests across 5 classes aligned to 44-VALIDATION.md's `-k` selectors; `compute_sla` group is green (11/11), the other 4 groups (`run_sla_pass`, `raw_db_registration`, `escalation_history`, `tenant_scope`) are RED by design, referencing not-yet-existing symbols from 44-02/44-03

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave-0 test scaffold covering all five verification-map rows** - `1237213` (test)
2. **Task 2: SLA compute + tiered level + configurable at-risk-window lookup** - `ba29d32` (feat)
3. **Task 3: Task-schema SLA defaults + compound indexes** - `89fa822` (feat)

_Note: Task 2's commit also includes the `_mock_db()` fix required to make the compute_sla group actually green (see Deviations)._

## Files Created/Modified
- `backend/compliance_remediation_sla_service.py` (NEW) - `compute_remediation_sla`, `compute_escalation_level`, `get_sla_at_risk_window`; no `get_database` calls
- `backend/tests/test_compliance_remediation_sla.py` (NEW) - Wave-0 scaffold, all 5 verification-map groups, 18 tests
- `backend/compliance_remediation_service.py` (MODIFIED) - `create_task` SLA defaults
- `backend/database.py` (MODIFIED) - `compliance_remediation_tasks` compound indexes

## Decisions Made
- `sla_status` at creation: `"ok"` when `due_date` is set, `"none"` when absent — matches the plan's stated either-is-acceptable guidance since the 44-02 sweep recomputes on its first pass regardless.
- `compliance_remediation_endpoints.py`'s `TaskUpdate` was reviewed per Task 3's action and confirmed to NOT expose `sla_status`/`escalated`/`escalation_level` — left unchanged (no edit made to this file this plan, despite it being listed in `files_modified`).
- Escalation tier boundaries kept as the RESEARCH-suggested `[1, 3, 7]` day defaults (Claude's discretion, confirmed reasonable per CONTEXT.md, tunable module constant).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_mock_db()`'s `db._db` unwrap guard resolved to the wrong mock**
- **Found during:** Task 2 verification (`pytest -k compute_sla -x`)
- **Issue:** `get_sla_at_risk_window`'s `raw = db._db if hasattr(db, "_db") else db` guard always took the `db._db` branch against a plain `MagicMock()`, because `MagicMock` auto-creates any accessed attribute — so `hasattr(db, "_db")` is always `True`, and `db._db` resolved to an unconfigured child mock rather than the `db` the test had actually set `system_settings.find_one` on. This caused `TypeError: object MagicMock can't be used in 'await' expression`.
- **Fix:** Added `db._db = db` at the end of `_mock_db()`, matching the existing `test_evidence_lifecycle.py::_make_mock_db()` convention of wiring `db._db` explicitly for this exact reason.
- **Files modified:** `backend/tests/test_compliance_remediation_sla.py`
- **Verification:** `pytest tests/test_compliance_remediation_sla.py -k compute_sla -x` — 11/11 pass
- **Committed in:** `ba29d32` (Task 2 commit)

**2. [Rule 1 - Bug] Module docstring literal text tripped the "no get_database" acceptance check**
- **Found during:** Task 2 verification (`grep -v '^\s*#' ... | grep -c get_database`)
- **Issue:** The module docstring's prose (non-`#`-comment line) said "never call get_database() from this module", which the acceptance grep counted as a real occurrence, returning 1 instead of the required 0.
- **Fix:** Reworded the docstring to describe the constraint without using the literal `get_database` token.
- **Files modified:** `backend/compliance_remediation_sla_service.py`
- **Verification:** `grep -v '^\s*#' backend/compliance_remediation_sla_service.py | grep -c get_database` returns `0`
- **Committed in:** `ba29d32` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — blocking test/verification bugs found while executing Task 2, fixed inline before commit)
**Impact on plan:** Both fixes were required for Task 2's own acceptance criteria to pass; no scope creep, no behavior change outside the two touched files.

## Issues Encountered
None beyond the two auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `compliance_remediation_sla_service.py` is ready for 44-02 to extend with `run_sla_pass`/`start_remediation_sla_scheduler` (this plan intentionally left those symbols absent; the Wave-0 scaffold's `run_sla_pass` and `raw_db_registration` groups are the executable contract 44-02 must satisfy).
- The Wave-0 scaffold's `escalation_history` and `tenant_scope` groups assume a new `backend/compliance_remediation_sla_endpoints.py` module (per 44-PATTERNS.md) exposing `router` with a `GET /api/compliance/remediation-tasks/{task_id}/escalations` route and a module-level `get_database` — 44-03 should target this exact contract.
- `create_task`'s auto-ticketing side effect (critical/high/medium priority) from Phase 43 is unaffected — SLA defaults are additive fields on the same insert.
- No blockers.

---
*Phase: 44-remediation-sla-escalation*
*Completed: 2026-07-21*
