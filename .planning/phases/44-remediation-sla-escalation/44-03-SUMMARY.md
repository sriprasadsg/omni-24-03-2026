---
phase: 44-remediation-sla-escalation
plan: 03
subsystem: api
tags: [python, fastapi, mongodb, motor, pytest, sla, compliance-remediation]

# Dependency graph
requires:
  - phase: 44-remediation-sla-escalation (44-01)
    provides: compute_remediation_sla, get_sla_at_risk_window, Wave-0 test scaffold (escalation_history/tenant_scope groups)
  - phase: 44-remediation-sla-escalation (44-02)
    provides: run_sla_pass first writer of remediation_escalations, document shape (task_id/tenantId/escalation_level/days_overdue/notified/created_at)
provides:
  - "GET /api/compliance/remediation-tasks/{task_id}/escalations — tenant-scoped, append-only escalation history read (SLA-02)"
  - "GET/PATCH /api/settings/remediation-sla — per-tenant at-risk window config (D-02), PATCH admin-gated with Field(ge=1, le=365)"
  - "No mutation route for the remediation_escalations resource anywhere in the codebase — immutability by omission"
  - "compliance_remediation_sla_endpoints router registered in router_registry.py, reachable in the live app"
affects: [44-04-remediation-sla-escalation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Settings GET/PATCH pair cloned verbatim from compliance_evidence_lifecycle_endpoints.py's STALE-02 shape (tenant/global system_settings doc split, _SETTINGS_ADMIN_ROLES gate, Field(ge=1, le=365) bounds)"
    - "Tenant-scoped audit-trail read endpoint cloned from the same file's COC-02 shape (query AND'd with tenantId at read time)"
    - "Belt-and-braces application-layer tenant filter on top of the DB query filter — never trust the query alone to have been honored"

key-files:
  created:
    - backend/compliance_remediation_sla_endpoints.py
  modified:
    - backend/router_registry.py

key-decisions:
  - "Added an in-code post-fetch tenantId filter on the escalation-history entries (in addition to the AND'd query) — required by the tenant_scope test, which mocks find() without applying the query filter, and matches T-44-06's 'never rely solely on write-time/query-time correctness' intent"
  - "_SETTINGS_ADMIN_ROLES kept as this file's own convention (not cross-wired with notification_manager.py's _ADMIN_ROLES, which is reserved for escalation notification recipients per 44-02)"

patterns-established: []

requirements-completed: [SLA-02]

coverage:
  - id: D1
    description: "A compliance admin can read a task's append-only escalation history via GET; the query is AND'd with tenantId so a cross-tenant read returns empty"
    requirement: "SLA-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_tenant_scope (2 tests) - pytest tests/test_compliance_remediation_sla.py -k tenant_scope -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "No PATCH/DELETE/PUT route exists for the escalations resource — immutability by omission (SLA-02)"
    verification:
      - kind: unit
        ref: "backend/tests/test_compliance_remediation_sla.py::Test_escalation_history::test_escalation_history_route_is_get_only_no_mutation_verbs - pytest tests/test_compliance_remediation_sla.py -k escalation_history -x"
        status: pass
    human_judgment: false
  - id: D3
    description: "The per-tenant at-risk window is readable (GET) and admin-gated writable (PATCH) with Field(ge=1, le=365) bounds (D-02)"
    verification:
      - kind: unit
        ref: "Manual route-table + import checks in Task 2 verify; PATCH admin gate reuses the already-tested _require_admin/_SETTINGS_ADMIN_ROLES pattern from compliance_evidence_lifecycle_endpoints.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Router registered and reachable (Pitfall 5 avoided)"
    verification:
      - kind: unit
        ref: "python -c \"import router_registry,inspect; s=inspect.getsource(router_registry); assert 'compliance_remediation_sla_endpoints' in s\"; python -c \"import app_startup\" (exit 0)"
        status: pass
    human_judgment: false

# Metrics
duration: 8min
completed: 2026-07-21
status: complete
---

# Phase 44 Plan 03: Escalation-History GET + At-Risk-Window Settings + Router Registration Summary

**New `compliance_remediation_sla_endpoints.py` exposing a tenant-scoped, read-only GET for the append-only escalation history (SLA-02) and an admin-gated GET/PATCH pair for the per-tenant at-risk window (D-02), registered in `router_registry.py` so it's reachable in the live app.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-21T14:17:00Z
- **Completed:** 2026-07-21T14:25:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `GET /api/compliance/remediation-tasks/{task_id}/escalations` — tenant-scoped read of `remediation_escalations`, sorted by `created_at` ascending, `_id` projected out; cross-tenant reads return an empty `entries` list
- `GET /api/settings/remediation-sla` — no admin gate (non-sensitive config), returns `{"windowDays": ...}` via 44-01's `get_sla_at_risk_window`
- `PATCH /api/settings/remediation-sla` — admin-gated via `_require_admin`/`_SETTINGS_ADMIN_ROLES`, body `SlaWindowUpdate.windowDays: Field(ge=1, le=365)`, upserts the tenant/global `system_settings` doc exactly per STALE-02's split
- No PATCH/DELETE/PUT route defined anywhere for the escalations resource — confirmed via route-table introspection (`GET` only on the `/escalations` path)
- `router_registry.py` now loads `compliance_remediation_sla_endpoints` alongside the existing `compliance_remediation_endpoints`/`compliance_evidence_lifecycle_endpoints` registrations
- File is 143 lines, well under the 500-line CLAUDE.md limit

## Task Commits

Each task was committed atomically:

1. **Task 1: Escalation-history GET + at-risk-window GET/PATCH endpoints** - `f21d892` (feat)
2. **Task 2: Register the new endpoints router** - `2abeba2` (feat)

## Files Created/Modified
- `backend/compliance_remediation_sla_endpoints.py` (NEW) - `GET /api/compliance/remediation-tasks/{task_id}/escalations`, `GET/PATCH /api/settings/remediation-sla`, `_require_admin`, `_SETTINGS_ADMIN_ROLES`, `SlaWindowUpdate`
- `backend/router_registry.py` (MODIFIED) - adds the `compliance_remediation_sla_endpoints` registration line

## Decisions Made
- Added a belt-and-braces post-fetch `tenantId` filter on the escalation-history entries list (in addition to the query-level `tenantId` AND), rather than relying on the DB query filter alone. Required by `Test_tenant_scope::test_tenant_scope_cross_tenant_escalations_excluded`, whose mock `find()` stub returns the configured doc regardless of query contents (mirroring T-44-06's "never rely solely on write-time correctness" — extended here to also cover query-time trust).
- `_SETTINGS_ADMIN_ROLES` kept file-local and distinct from `notification_manager.py`'s `_ADMIN_ROLES` (used for escalation notification recipients in 44-02) — per 44-PATTERNS.md's explicit instruction not to cross-wire the two sets.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Escalation-history read did not exclude cross-tenant entries under the test's mock**
- **Found during:** Task 1 verification (`pytest -k tenant_scope -x`)
- **Issue:** The initial implementation relied solely on the Mongo query (`query["tenantId"] = tenant_id`) to filter results. `Test_tenant_scope::test_tenant_scope_cross_tenant_escalations_excluded` stubs `remediation_escalations.find()` to always return a fixed cursor regardless of the query dict passed in (the mock doesn't simulate server-side filtering), so a cross-tenant doc was returned to the caller and the test failed (`entries == []` assertion).
- **Fix:** Added an explicit application-layer filter (`entries = [e for e in entries if e.get("tenantId") == tenant_id]`) after fetching, so tenant scoping is enforced twice — once at the query level (verified by the sibling `test_tenant_scope_read_query_and_with_tenant_id` test) and once in code.
- **Files modified:** `backend/compliance_remediation_sla_endpoints.py`
- **Verification:** `pytest tests/test_compliance_remediation_sla.py -k "escalation_history or tenant_scope" -x` — 3/3 pass
- **Committed in:** `f21d892` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — blocking test bug found while executing Task 1, fixed inline before commit)
**Impact on plan:** Strengthens the SLA-02 tenant-isolation guarantee beyond the plan's literal wording (query-level AND only) to also cover application-layer double-checking; no scope creep, single file touched.

## Issues Encountered
None beyond the one auto-fixed deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `compliance_remediation_sla_endpoints.py` is complete and registered; both the escalation-history read and the at-risk-window settings pair are live in the router table
- 44-04 (frontend: SLA badge on `RemediationDashboard.tsx`, escalation-history panel on `RemediationTaskModal.tsx`, `apiService.ts` client functions) can now call `GET /api/compliance/remediation-tasks/{task_id}/escalations`, `GET/PATCH /api/settings/remediation-sla` against this exact contract
- Full backend suite re-run after this plan: 1353 passed / 34 skipped / 5 failed — the same 5 pre-existing, unrelated failures documented in 44-02-SUMMARY.md's Self-Check Notes (`test_webhook_logic.py` x2, `test_agentic_ai.py` x1, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`) — none reference this plan's 2 files. (Full-suite collection also errors on 3 unrelated live-server-dependent scripts — `test_ai_service_config.py`, `test_network_endpoint.py`, `test_sbom_api.py` — excluded via `--ignore`, same pre-existing environmental issue noted in earlier sessions.)
- No blockers.

---
*Phase: 44-remediation-sla-escalation*
*Completed: 2026-07-21*

## Self-Check: PASSED
All created/modified files found on disk; both commit hashes (f21d892, 2abeba2) found in git log.
