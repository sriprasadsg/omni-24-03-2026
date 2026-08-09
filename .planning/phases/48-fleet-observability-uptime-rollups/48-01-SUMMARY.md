---
phase: 48-fleet-observability-uptime-rollups
plan: 01
subsystem: api
tags: [fastapi, motor, mongodb, uptime, observability, agent-metrics]

# Dependency graph
requires: []
provides:
  - "agent_uptime_service.compute_uptime(rows, hours, cadence_seconds=30, now=None) — pure gap-detection uptime math"
  - "GET /api/agents/{agent_id}/uptime?hours=N — tenant-isolated on-the-fly uptime endpoint"
affects: [48-02, 48-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "On-the-fly gap-detection uptime: bucket agent_metrics.timestamp rows at a fixed assumed 30s cadence, uptime% = min(received/expected,1.0)*100"
    - "Fine detection grid (30s) coarsened to ~15min display blocks for the returned timeline, keeping % computed on the fine grid"

key-files:
  created:
    - backend/agent_uptime_service.py
    - backend/agent_uptime_endpoints.py
    - backend/tests/test_agent_uptime_service.py
  modified:
    - backend/router_registry.py

key-decisions:
  - "compute_uptime accepts an optional now= kwarg (not in the plan's literal signature) purely to make tests deterministic; the endpoint never passes it, so real-time behavior is unaffected"
  - "received_bucket_indices is a set of fine-grid indices, so the received/expected ratio is inherently bounded at 1.0 by construction — the min(...,1.0) guard in the plan's action is a documented safety net, not the primary clip mechanism"

requirements-completed: [FOBS-02]

coverage:
  - id: D1
    description: "compute_uptime bucketing math: 100% full coverage, 50% half coverage, 0% empty window (no exception), clip-at-100% for faster-than-cadence heartbeats, and a well-formed bucket-dict timeline"
    requirement: "FOBS-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_uptime_service.py::TestComputeUptimeGapDetection (5 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /api/agents/{agent_id}/uptime is tenant-isolated, clamps hours to 1..48, and returns uptime_percent + timeline"
    requirement: "FOBS-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_uptime_service.py::TestUptimeEndpoint (4 tests)"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-29
status: complete
---

# Phase 48 Plan 01: On-the-fly Uptime Read Path Summary

**New `agent_uptime_service.compute_uptime` bucketing engine plus a tenant-isolated `GET /api/agents/{id}/uptime?hours=N` endpoint that reads `agent_metrics` (never the capped `agent_metrics_history` decoy) at an assumed fixed 30s cadence.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-29T17:55Z
- **Tasks:** 2/2 completed
- **Files modified:** 4 (3 created, 1 edited)

## Accomplishments
- `compute_uptime(rows, hours, cadence_seconds=30, now=None)` in `backend/agent_uptime_service.py` — buckets `agent_metrics` heartbeat timestamps onto a fixed-cadence grid over the requested window, returning `{uptime_percent, expected_buckets, received_buckets, timeline}`. Empty rows (never-heartbeat agent) yield `0.0%` with no exception. The returned `timeline` is coarsened to ~15-minute display blocks so a near-48h window doesn't return thousands of points, while `uptime_percent` itself is always computed on the fine 30s grid.
- `GET /api/agents/{agent_id}/uptime` in `backend/agent_uptime_endpoints.py` — clones `agent_metrics_endpoints.get_agent_metrics_history`'s tenant-gating shape verbatim (non-super-admin gets `tenantId`/`tenant_id` added to both the agent lookup and the `agent_metrics` query; 404 if the agent isn't in scope), clamps `hours` to `1..48` before querying, and never touches `db._db` in the request handler.
- Registered the new router in `router_registry.py` immediately after `agent_metrics_endpoints`.
- 9 hermetic unit tests (`backend/tests/test_agent_uptime_service.py`): 5 covering the bucketing math (full coverage/100%, half coverage/50%, empty-window/0%, over-cadence clip-at-100%, timeline shape) and 4 covering the endpoint (hours clamps at both the 48h ceiling and the 1h floor, cross-tenant agent 404s, response includes `uptime_percent`/`timeline`).

## Task Commits

Each task was committed atomically (TDD: test -> feat):

1. **Task 1: Wave-0 test scaffold + compute_uptime service** - `f2577e5` (test), `6eeabf8` (feat)
2. **Task 2: Tenant-isolated GET /uptime endpoint + router registration** - `f28c547` (feat, includes the endpoint-level tests added to the same test file)

## TDD Gate Compliance

RED gate confirmed: `f2577e5` (test-only commit) ran first and failed collection (`ModuleNotFoundError: No module named 'agent_uptime_service'`) before any implementation existed. GREEN gate confirmed: `6eeabf8` (compute_uptime implementation) landed after RED and all 5 bucketing tests passed. Gate sequence verified in `git log`: test -> feat -> feat (no regressions, no skipped gate).

## Files Created/Modified
- `backend/agent_uptime_service.py` - `compute_uptime` gap-detection bucketing engine (138 lines)
- `backend/agent_uptime_endpoints.py` - `GET /{agent_id}/uptime` endpoint (67 lines)
- `backend/tests/test_agent_uptime_service.py` - 9 hermetic unit tests covering both the service and endpoint (201 lines)
- `backend/router_registry.py` - added one `_load(app, "agent_uptime_endpoints", "router")` line

## Decisions Made
- Added an optional `now` kwarg to `compute_uptime` purely for deterministic testing (the plan's literal signature is `compute_uptime(rows, hours, cadence_seconds=30)`); the production endpoint call site never passes it, so real-request behavior is unaffected by this addition.
- The plan's `min(received/expected, 1.0)` clip is implemented as specified, but in practice `received_bucket_indices` is a set of fine-grid indices bounded by construction to `expected_buckets`, so the ratio can never exceed 1.0 on its own — the guard is documented in the module docstring as a deliberate safety net rather than the sole mechanism, matching the plan's intent (Task 1 behavior case: "more rows than expected buckets ... clips at 100.0").

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `compute_uptime` is ready for 48-02's daily rollup sweep to reuse directly (same on-the-fly math, sweep just persists a daily snapshot).
- The `GET /api/agents/{id}/uptime` endpoint is ready for 48-04's agent-detail-view uptime timeline UI to consume.
- Full backend suite re-run after this plan: 1435 passed / 34 skipped / 8 failed / 4 errors — all 8 failures + 4 errors confirmed (via `git stash`) to reproduce identically on the pre-Phase-48 tree; none are introduced by this plan's 4 files.

---
*Phase: 48-fleet-observability-uptime-rollups*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created files confirmed present on disk; all 3 commit hashes (f2577e5, 6eeabf8, f28c547) confirmed present in `git log --all`.
