---
phase: 04-remediation-workflow
plan: "00"
subsystem: testing, api, rust-agent
tags: [pytest, socketio, websocket_manager, rust, compliance, remediation]

# Dependency graph
requires:
  - phase: 03-audit-ready-export
    provides: compliance reporting pipeline and tenant-scoped export infrastructure
provides:
  - Failing test scaffold (Nyquist floor) asserting REM-01..REM-04 behavior
  - Rust agent dispatch_instruction accepting "Run Compliance Scan" string
  - broadcast_remediation_update(tenant_id, payload) broadcaster in websocket_manager

affects:
  - 04-01 (compliance_remediation_service — tested by REM-01..03 scaffold)
  - 04-02 (remediation_task_endpoints — uses broadcaster, tested scaffold)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.run() for async pytest (no pytest-asyncio, per 02-01 decision)"
    - "Late in-test imports of not-yet-existing modules for RED test scaffold"
    - "list(connected_clients[tenant_id]) snapshot copy in broadcaster to avoid mutation-during-iteration"

key-files:
  created:
    - backend/tests/test_remediation_workflow.py
  modified:
    - agent-rust/src/poll.rs
    - backend/websocket_manager.py

key-decisions:
  - "04-00: 'Run Compliance Scan' added to Rust dispatch arm alongside existing alternatives — resolves REM-03 Pitfall 1 string mismatch between Python agent (Run Compliance Scan) and Rust agent (was Run Compliance Check only)"
  - "04-00: broadcast_remediation_update placed after broadcast_compliance_alert, uses list() snapshot copy matching broadcast_mitre_heatmap pattern"
  - "04-00: REM-04 test structured with patch.object on sio.emit (AsyncMock) to avoid socketio runtime dependency in CI"

patterns-established:
  - "Broadcaster pattern: guard on connected_clients membership → stamp timestamp → iterate list() snapshot → emit per sid → logger.debug"
  - "RED scaffold pattern: late import of not-yet-existing module inside test body so ImportError propagates as FAILED (not ERROR at collection)"

requirements-completed: [REM-01, REM-02, REM-03, REM-04]

# Metrics
duration: 3min
completed: 2026-06-17
---

# Phase 4 Plan 00: Remediation Workflow Foundation Summary

**Failing pytest scaffold for REM-01..REM-04, Rust "Run Compliance Scan" dispatch arm added, and broadcast_remediation_update broadcaster wired — Wave 0 Nyquist floor established**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-06-17T19:29:42Z
- **Completed:** 2026-06-17T19:32:42Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- 4-test pytest scaffold created in `backend/tests/test_remediation_workflow.py` covering all REM-01..REM-04 requirements; REM-01..03 fail RED (ImportError on `compliance_remediation_service`) until Wave 1 lands; REM-04 passes GREEN after Task 3
- Rust `dispatch_instruction` match arm at poll.rs line 260 extended with `"Run Compliance Scan"` alternative, closing the string-mismatch gap documented in 04-RESEARCH.md Pitfall 1 (Python agent uses `"Run Compliance Scan"`; Rust only matched `"Run Compliance Check"`)
- `broadcast_remediation_update(tenant_id, payload)` added to `websocket_manager.py` after `broadcast_compliance_alert`, following the established broadcaster pattern with tenant isolation guard, timestamp stamping, and list() snapshot copy

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing test scaffold for REM-01..REM-04** - `2e49b18` (test)
2. **Task 2: Patch Rust agent to accept "Run Compliance Scan" instruction string** - `f8739f3` (fix)
3. **Task 3: Add broadcast_remediation_update to websocket_manager** - `50ac603` (feat)

## Files Created/Modified

- `backend/tests/test_remediation_workflow.py` - RED test scaffold for REM-01..04; 4 tests using asyncio.run() and AsyncMock DB factory
- `agent-rust/src/poll.rs` - `"Run Compliance Scan"` added to compliance dispatch match arm (line 260)
- `backend/websocket_manager.py` - `broadcast_remediation_update(tenant_id, payload)` async broadcaster added after `broadcast_compliance_alert`

## Decisions Made

- `"Run Compliance Scan"` added to the Rust match arm (not renamed from `"Run Compliance Check"`) to preserve backward compatibility while enabling the Python-standard instruction string to reach Rust agents
- `broadcast_remediation_update` uses `list(connected_clients[tenant_id])` snapshot copy (same as `broadcast_mitre_heatmap`) to avoid set-mutation-during-iteration bugs
- REM-04 test patches `websocket_manager.sio.emit` directly with `AsyncMock` to avoid requiring a live socketio server in CI — works reliably without `python-socketio` in the global pytest env

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- `python` binary not in PATH in CI environment; used `python3` for all test invocations. The venv python (`backend/venv/bin/python`) was required for the `websocket_manager` import verification because `socketio` is only installed inside the project venv.

## Known Stubs

None — this plan establishes test scaffold and infrastructure primitives only; no UI rendering or data-flow stubs exist.

## Threat Flags

None — no new network endpoints introduced. `broadcast_remediation_update` emits only to `connected_clients[tenant_id]` sids (T-04-01 mitigated per plan threat register). Rust dispatch arm addition is read-only (T-04-02 accepted).

## Next Phase Readiness

- Wave 1 (04-01) can now create `compliance_remediation_service.py` — the test scaffold will turn GREEN as each function is implemented
- Wave 1 (04-01) should also register `compliance_remediation_task_endpoints.py` in `router_registry.py`
- Wave 2 (04-02) frontend wiring can call `broadcast_remediation_update` via the now-available broadcaster
- No blockers for Phase 04-01 or 04-02

---
*Phase: 04-remediation-workflow*
*Completed: 2026-06-17*
