---
phase: 48-fleet-observability-uptime-rollups
plan: 03
subsystem: api
tags: [fastapi, motor, mongodb, fleet, observability, version-drift]

# Dependency graph
requires: ["48-01"]
provides:
  - "GET /api/fleet/observability — fleet-wide offline_agents + version_drift aggregate"
affects: [48-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fleet aggregate endpoint reuses monitor_agent_status()'s status=='Offline' set and agent_auto_update_service._parse_ver/_LATEST_AGENT_VERSION — no new offline heuristic, no new version parser"

key-files:
  created:
    - backend/agent_fleet_observability_endpoints.py
    - backend/tests/test_agent_fleet_observability.py
  modified:
    - backend/router_registry.py

key-decisions:
  - "Version-drift compare treats an unparseable or missing reported version as fail-closed excluded (not a crash, not flagged as drift) — matches T-48-08's accept disposition (informational fleet-health, not a security gate)"
  - "Response fields: latest_version, offline_agents, offline_count, version_drift, drift_count — each agent entry projected to id/hostname/status/version/tenantId"

requirements-completed: [FOBS-03]

coverage:
  - id: D1
    description: "Super-admin sees agents across all tenants; tenant-admin query gains a tenantId filter"
    requirement: "FOBS-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_fleet_observability.py::TestFleetObservabilityEndpoint (test_super_admin_sees_agents_across_all_tenants, test_tenant_admin_scoped_to_own_tenant)"
        status: pass
    human_judgment: false
  - id: D2
    description: "version_drift includes only agents whose _parse_ver(version) is not None and < _parse_ver(_LATEST_AGENT_VERSION); malformed/missing version excluded without crash"
    requirement: "FOBS-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_fleet_observability.py::TestFleetObservabilityEndpoint (test_version_drift_includes_only_older_parseable_versions, test_malformed_or_missing_version_excluded_without_crash)"
        status: pass
    human_judgment: false
  - id: D3
    description: "offline_agents sourced from the existing status=='Offline' field (monitor_agent_status()'s set), not a new heuristic"
    requirement: "FOBS-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_fleet_observability.py::TestFleetObservabilityEndpoint::test_offline_set_read_from_status_field_not_new_heuristic"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-29
status: complete
---

# Phase 48 Plan 03: Fleet Observability Aggregate Endpoint Summary

**New admin GET /api/fleet/observability endpoint returning the fleet's offline agents and version-drift list, reusing the existing offline-status field and `_parse_ver`/`_LATEST_AGENT_VERSION` compare — tenant-scoped for non-super-admins.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-29
- **Tasks:** 2/2 completed
- **Files modified:** 3 (2 created, 1 edited)

## Accomplishments

- `backend/agent_fleet_observability_endpoints.py` — new `router = APIRouter(prefix="/api/fleet", tags=["Fleet Observability"])` with `GET /observability`. Clones `agent_core_endpoints.get_agents`'s `is_super_admin(current_user.role)` tenant-gating shape verbatim: super-admins get no tenant filter, non-super-admins get `tenantId` added to the query. Reads exclusively through the request-scoped wrapped `db` from `get_database()` — never `db._db` (Pitfall 5 / T-48-07).
- Offline set: agents whose `status == "Offline"` (the field `monitor_agent_status()` maintains in the background — no new freshness heuristic added).
- Version-drift: imports `_parse_ver` and `_LATEST_AGENT_VERSION` from `agent_auto_update_service` unchanged (Don't Hand-Roll). An agent is in `version_drift` only when its parsed version is not `None` and strictly less than the parsed latest version; a malformed or absent version is silently excluded rather than raising (T-48-08 fail-closed).
- Response shape: `{latest_version, offline_agents, offline_count, version_drift, drift_count}`, each agent entry projected to `{id, hostname, status, version, tenantId}`.
- Registered in `router_registry.py` immediately after `agent_uptime_endpoints` (the "line 279 area" the plan pointed at had shifted slightly since 48-01 landed its own entry there — appended alongside it, not clobbering it). Confirmed no `/api/fleet` prefix collision via grep.
- 5 hermetic unit tests (`backend/tests/test_agent_fleet_observability.py`): super-admin fleet-wide visibility (and that the query filter has no `tenantId`), tenant-admin scoping (query filter carries the caller's `tenantId`), version-drift inclusion/exclusion by parsed-version comparison, malformed/missing-version fail-closed exclusion, and offline-set sourced from the existing `status` field.

## Task Commits

Each task was committed atomically (TDD: test -> feat):

1. **Task 1: Wave-0 test scaffold + fleet aggregate endpoint** - `1a31f64` (test), `0e9d2b9` (feat)
2. **Task 2: Register the fleet router** - `c8d394d` (feat)

## TDD Gate Compliance

RED gate confirmed: `1a31f64` (test-only commit) ran first; all 5 tests failed at collection with `ModuleNotFoundError: No module named 'agent_fleet_observability_endpoints'` before any implementation existed. GREEN gate confirmed: `0e9d2b9` (endpoint implementation) landed after RED and all 5 tests passed. Gate sequence verified in `git log`: test -> feat -> feat (registration). No REFACTOR commit needed.

## Files Created/Modified

- `backend/agent_fleet_observability_endpoints.py` — `GET /observability` fleet aggregate endpoint (79 lines)
- `backend/tests/test_agent_fleet_observability.py` — 5 hermetic unit tests (169 lines)
- `backend/router_registry.py` — added one `_load(app, "agent_fleet_observability_endpoints", "router")` line, next to `agent_uptime_endpoints`

## Decisions Made

- Response includes both `offline_count`/`drift_count` alongside the full `offline_agents`/`version_drift` lists so the future Fleet Observability nav page (48-05) can render summary tiles without recomputing `len()` client-side.
- Malformed/missing version handling: treated identically (both parse to `None` via the existing `_parse_ver`), simply excluded from `version_drift` — no separate "unknown version" bucket, since the plan's must-haves only require it not crash and not be counted as drift.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `GET /api/fleet/observability` is ready for 48-05's admin-gated Fleet Observability nav page to consume directly.
- Full backend suite re-run after this plan (excluding 4 known-unrunnable collection errors — `test_ai_service_config.py`, `test_network_endpoint.py`, `test_sbom_api.py`, `tests/test_graphql.py` — pre-existing environment issues unrelated to this plan's files, matching prior-session notes): **1447 passed / 34 skipped / 8 failed** — all 8 failures confirmed pre-existing and unrelated to this plan's 3 files (`test_webhook_logic.py` x2, `tests/test_agentic_ai.py` tool_choice, `tests/test_e2e_integration.py` golden path, `tests/test_rust_heartbeat_parity.py`, `tests/test_support_admin_to_user.py` x3).

---
*Phase: 48-fleet-observability-uptime-rollups*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created files confirmed present on disk; all 3 commit hashes (1a31f64, 0e9d2b9, c8d394d) confirmed present in `git log --all`.
