---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 04
subsystem: api
tags: [fastapi, mongodb, tenant-isolation, audit-log, pydantic]

# Dependency graph
requires:
  - phase: 46-02
    provides: agent_location_history_service.py (record_location_change, get_track_agent_location), the append-only agent_location_history collection, and migration 003's compound indexes
provides:
  - "GET /api/agents/{agent_id}/location-history — tenant-scoped, ascending-sorted, read-time dwell-annotated location-history read surface (GAUD-02)"
  - "GET/PATCH /api/settings/agent-location-tracking — admin-gated track_agent_location toggle (D-02)"
  - "Router registration in router_registry.py so both routes are reachable in the running app"
affects: ["46-05 (heartbeat/register wiring)", "46-07 (frontend AgentLocationHistory panel + apiService client)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GET-only append-only resource: immutability enforced purely by the absence of any PATCH/PUT/DELETE route, verified via router.routes introspection rather than source grepping alone (cloned from compliance_remediation_sla_endpoints.py's SLA-02 pattern)"
    - "Tenant-scoped read + belt-and-braces application-level re-filter after the DB query (never trust the query filter alone)"
    - "Read-time-derived value (dwell_seconds) computed in the GET handler from adjacent rows, never persisted — avoids the append-only/immutability violation that a stored per-row dwell field would create"

key-files:
  created:
    - backend/tests/test_agent_location_history_endpoints.py
  modified:
    - backend/agent_location_history_endpoints.py
    - backend/router_registry.py

key-decisions:
  - "agent_location_history_endpoints.py already existed on disk, untracked, with two real bugs (see Deviations) — repaired and committed rather than rewritten from scratch, since its overall shape already matched the plan's clone-from-SLA-02 design."
  - "dwell field named dwell_seconds (float, via timedelta.total_seconds()) per this plan's own task action text, which explicitly computes and returns it in the GET response — this is a deliberate implementation choice local to 46-04's must_haves, distinct from 46-UI-SPEC.md's separate (and conflicting) note that the frontend should compute dwell client-side and ignore any dwell_seconds field. Flagged for whoever plans the frontend consumer (46-07) to reconcile, not resolved here."

requirements-completed: [GAUD-01, GAUD-02]

coverage:
  - id: D1
    description: "GET /api/agents/{agent_id}/location-history returns only the calling tenant's rows, ascending by timestamp, with a belt-and-braces application-level re-filter"
    requirement: "GAUD-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestTenantScope::test_tenant_scope_cross_tenant_rows_excluded"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestTenantScope::test_tenant_scope_query_anded_with_tenant_id"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestSort::test_sort_ascending_by_timestamp"
        status: pass
    human_judgment: false
  - id: D2
    description: "Response rows carry a read-time-computed dwell_seconds value; last row uses now - timestamp, intermediate rows use gap to next row; never a stored field"
    requirement: "GAUD-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestDwell::test_dwell_intermediate_row_is_gap_to_next"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestDwell::test_dwell_last_row_is_now_minus_timestamp_not_stored"
        status: pass
    human_judgment: false
  - id: D3
    description: "No PATCH/PUT/DELETE route exists anywhere for the location-history resource (immutability via absence of a mutation route, D-10)"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestImmutability::test_no_mutation_route_targets_location_history"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET/PATCH /api/settings/agent-location-tracking toggle; PATCH admin-gated with a Pydantic bool body"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestToggleGet::test_toggle_get_defaults_to_enabled_true"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestTogglePatch::test_toggle_patch_admin_disables_and_get_reflects_it"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_location_history_endpoints.py::TestTogglePatch::test_toggle_patch_forbidden_for_non_admin"
        status: pass
    human_judgment: false
  - id: D5
    description: "Router registered in router_registry.py so routes are reachable in the running app"
    requirement: "GAUD-02"
    verification:
      - kind: unit
        ref: "backend/router_registry.py grep gate: agent_location_history_endpoints registered"
        status: pass
    human_judgment: false

duration: ~15min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 04: Location-History Read Surface + Tracking-Toggle Endpoints Summary

**Tenant-scoped, dwell-annotated GET /api/agents/{agent_id}/location-history and admin-gated GET/PATCH /api/settings/agent-location-tracking, cloned from compliance_remediation_sla_endpoints.py and registered in router_registry.py.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-29T07:35:00Z (approx)
- **Completed:** 2026-07-29T07:42:03Z
- **Tasks:** 2
- **Files modified:** 3 (1 test file created, 2 source files modified)

## Accomplishments
- `GET /api/agents/{agent_id}/location-history` returns tenant-scoped, ascending-sorted rows with a `dwell_seconds` value computed at read time on every row (never persisted).
- `GET`/`PATCH /api/settings/agent-location-tracking` toggle wired to the existing `get_track_agent_location` service function, PATCH admin-gated via `_SETTINGS_ADMIN_ROLES`/`_require_admin` cloned from `compliance_remediation_sla_endpoints.py`.
- Router registered in `router_registry.py`, confirmed reachable via a live route-table print (`/api/agents/{agent_id}/location-history` and `/api/settings/agent-location-tracking` both present).
- Immutability (D-10) verified by route-table enumeration, not source grepping alone — no PATCH/PUT/DELETE route exists anywhere for the location-history path.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write endpoint tests (tenant-scope, sort, dwell, admin PATCH, immutability)** - `23829b2` (test)
2. **Task 2: Implement location-history GET + toggle GET/PATCH endpoints and register router** - `b792db4` (feat)

_Note: 9 tests were written; 6 passed against the pre-existing (untracked) draft endpoints module and 3 failed for real bugs in it — the RED phase reflected repairing a real bug, not a fully-missing module (see Deviations)._

## Files Created/Modified
- `backend/tests/test_agent_location_history_endpoints.py` - tenant-scope, sort, dwell, toggle GET/PATCH (admin/forbidden), and route-table immutability tests
- `backend/agent_location_history_endpoints.py` - GET location-history (tenant-scoped, dwell-at-read-time) + GET/PATCH agent-location-tracking toggle
- `backend/router_registry.py` - added `_load(app, "agent_location_history_endpoints", "router")` registration line

## Decisions Made
- Repaired the pre-existing (untracked, uncommitted) draft `agent_location_history_endpoints.py` in place rather than rewriting it from scratch — its overall shape already matched the SLA-02 clone the plan calls for; only two concrete bugs needed fixing (see Deviations).
- Named the read-time dwell field `dwell_seconds` (a float via `timedelta.total_seconds()`), matching this plan's own task-action text verbatim (`dwell_seconds = timestamp(i+1) - timestamp(i)`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Location-history query used the wrong field name (`agentId` instead of `agent_id`)**
- **Found during:** Task 1 (writing the tenant-scope test) and confirmed in Task 2
- **Issue:** The pre-existing (untracked) draft `agent_location_history_endpoints.py` queried `{"agentId": agent_id}`, but `agent_location_history_service.py._promote` writes rows with the key `agent_id` (also confirmed by migration `003_agent_location_history_indexes.py`'s compound index on `agent_id`). Every real GET request would have silently returned zero rows.
- **Fix:** Changed the query to `{"agent_id": agent_id}`.
- **Files modified:** `backend/agent_location_history_endpoints.py`
- **Verification:** `TestTenantScope::test_tenant_scope_query_anded_with_tenant_id` now passes; live route/DB field alignment confirmed against `agent_location_history_service.py` and migration 003.
- **Committed in:** `b792db4` (Task 2 commit)

**2. [Rule 1 - Bug] Dwell computed as a raw, non-JSON-serializable `timedelta` object stored under a `dwellTime` key**
- **Found during:** Task 1 (writing the dwell tests)
- **Issue:** The pre-existing draft assigned `entries[i]["dwellTime"] = entries[i+1]["timestamp"] - entries[i]["timestamp"]` — a `datetime.timedelta` object, which FastAPI's default JSON encoding cannot serialize the way the plan's contract implies (and doesn't match the plan's own literal `dwell_seconds` naming).
- **Fix:** Renamed the field to `dwell_seconds` and converted the `timedelta` via `.total_seconds()` before attaching it to the row.
- **Files modified:** `backend/agent_location_history_endpoints.py`
- **Verification:** `TestDwell::test_dwell_intermediate_row_is_gap_to_next` and `TestDwell::test_dwell_last_row_is_now_minus_timestamp_not_stored` both pass; confirmed the value round-trips through the real `TestClient` HTTP JSON response (not just the in-process Python object).
- **Committed in:** `b792db4` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - real bugs in a pre-existing, untracked draft file that would have broken the endpoint in production)
**Impact on plan:** Both fixes were necessary for basic correctness (the endpoint would have returned empty history for every agent, and the dwell field would either be dropped or raise a serialization error). No scope creep — no architectural changes, no new files beyond the plan's own file list.

## Issues Encountered
- `backend/agent_location_history_endpoints.py` was already present on disk before this plan ran, untracked by git (`git status` showed `?? backend/agent_location_history_endpoints.py`), presumably scaffolded in a prior, uncommitted session. Task 1's RED expectation ("tests currently fail only on the missing import") did not literally hold since the module already existed; instead, 3 of 9 written tests failed against it for the two real bugs documented above, which is functionally equivalent RED-phase evidence (tests fail against not-yet-correct code) even though the failure mode differed from a missing-module ImportError. Documented here rather than silently treated as a non-deviation.
- A full backend suite run (excluding known-broken-collection files unrelated to this plan: `test_rebac.py`, `test_ai_service_config.py`, `test_network_endpoint.py`, `test_sbom_api.py`, `tests/test_graphql.py` — network/dependency-version issues) showed 1382 passed / 34 skipped / 8 failed. All 8 failures are pre-existing and unrelated to this plan's files (`test_webhook_logic.py` x2, `tests/test_agentic_ai.py` tool_choice test, `tests/test_e2e_integration.py` golden path, `tests/test_rust_heartbeat_parity.py`, `tests/test_support_admin_to_user.py` x3 — an event-loop/asyncio environment issue). None reference `agent_location_history_endpoints.py`, `agent_location_history_service.py`, or `router_registry.py`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The location-history read surface and tracking toggle are both live and registered; 46-05 (heartbeat/register wiring, per STATE.md's wave notes) can call `record_location_change`/`get_track_agent_location` with confidence the read side is already correct and reachable.
- Flag for the frontend consumer plan (46-07 or wherever `AgentLocationHistory.tsx`/`apiService.fetchAgentLocationHistory` land): 46-UI-SPEC.md states dwell should be computed client-side and any `dwell_seconds` field from the backend should be ignored, while this plan's own must_haves require the backend to compute and return `dwell_seconds`. Both can coexist (frontend is free to ignore the field and recompute it locally from `timestamp` values), but this discrepancy between planning documents should be reconciled explicitly when that plan is written.

---
*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files confirmed present on disk; both task commits (`23829b2`, `b792db4`) confirmed in git log.
