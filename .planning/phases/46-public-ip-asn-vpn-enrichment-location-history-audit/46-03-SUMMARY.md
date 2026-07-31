---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 03
subsystem: infra
tags: [retention, mongodb, data-lifecycle, privacy, python]

# Dependency graph
requires:
  - phase: 46-02
    provides: agent_location_history collection (append-only, native datetime timestamp field)
provides:
  - RetentionService.cleanup_agent_location_history(retention_days=365)
  - run_cleanup() wiring — agent_location_history_deleted key in the returned report
  - agent_location_history entry in retention_endpoints.py's _POLICY_DEFAULTS (365 days)
affects: [47-agent-scoped-geo-security-detectors, 48-fleet-observability-uptime-rollups, retention-module-future-work]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Native datetime cutoff comparison ({\"timestamp\": {\"$lt\": cutoff}}) for BSON Date fields, distinct from the module's 3 pre-existing cleanup_* methods which compare against .isoformat() strings"

key-files:
  created:
    - backend/tests/test_retention_agent_location_history.py
  modified:
    - backend/retention_service.py
    - backend/retention_endpoints.py

key-decisions:
  - "Retention-enforcement trigger locked as manual-trigger-only (POST /api/retention/run), matching the existing module's actual (no-scheduler) precedent; an automatic sweep is explicitly deferred, not built here"
  - "cleanup_agent_location_history compares against a native datetime cutoff, never .isoformat(), since agent_location_history.timestamp is a real BSON Date (unlike the other 3 cleanup_* methods' string-typed fields)"
  - "365-day retention is a deliberate, pre-implementation decision (D-01/D-04) resolved before agent_location_history data accumulates, not inherited from the 30-day agent_metrics_history convention"

requirements-completed: [GAUD-01]

coverage:
  - id: D1
    description: "cleanup_agent_location_history(retention_days=365) deletes a 366-day-old row and retains a 1-day-old row, using a native datetime cutoff comparison"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_retention_agent_location_history.py#TestCleanupAgentLocationHistory::test_366_day_old_row_deleted_1_day_old_row_retained"
        status: pass
      - kind: unit
        ref: "backend/tests/test_retention_agent_location_history.py#TestCleanupAgentLocationHistory::test_cutoff_uses_native_datetime_not_isoformat_string"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_cleanup() is wired to call cleanup_agent_location_history and include its count under agent_location_history_deleted in the returned report"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_retention_agent_location_history.py#TestRunCleanupWiring::test_run_cleanup_report_includes_location_history_deletion_key"
        status: pass
      - kind: unit
        ref: "backend/tests/test_retention_agent_location_history.py#TestRunCleanupWiring::test_run_cleanup_defaults_agent_location_history_to_365_when_no_policy_passed"
        status: pass
    human_judgment: false
  - id: D3
    description: "agent_location_history policy default (365 days) present in retention_endpoints.py's _POLICY_DEFAULTS, feeding /run's policies dict"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "grep -c 'agent_location_history' backend/retention_endpoints.py (>= 1)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 03: Route 365-Day Location-History Retention Through the Existing Retention Module Summary

**Added `cleanup_agent_location_history()` to `RetentionService` with a native-datetime cutoff comparison, wired it into `run_cleanup()`'s report dict, and seeded the matching 365-day policy default — closing the D-01 gap where a policy doc alone (the `security_events`/`alerts` seed-only pattern) would not have actually enforced retention.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-29T07:31:00Z (approx, per commit history)
- **Completed:** 2026-07-29T07:33:08Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `RetentionService.cleanup_agent_location_history(retention_days=365)` deletes `agent_location_history` rows via `delete_many({"timestamp": {"$lt": cutoff}})`, comparing against a real `datetime` object — never `.isoformat()` — because the field is a genuine BSON Date (per 46-02's write-path contract), unlike the module's 3 pre-existing `cleanup_*` methods which compare ISO strings.
- `run_cleanup()` now reads `policies.get("agent_location_history", 365)`, calls the new method, and surfaces the count under `agent_location_history_deleted` in its returned report dict — so the retention decision is actually enforced end-to-end via `/api/retention/run`, not merely documented as a policy row (the exact gap `security_events`/`alerts` fell into, called out explicitly in 46-RESEARCH.md).
- `retention_endpoints.py`'s `_POLICY_DEFAULTS` carries `"agent_location_history": {"retention_days": 365, ...}`, so `/run`'s policies dict (built from the seeded `retention_policies` collection) feeds 365 days into `run_cleanup` by default.
- 4 new hermetic unit tests (`backend/tests/test_retention_agent_location_history.py`) exercise the real 365-day boundary behavior (366-day row deleted, 1-day row retained) via a small in-memory fake collection that genuinely evaluates the `$lt` filter — not just asserting the filter's shape — since `mongomock` is not installed in this environment.
- Retention-enforcement trigger locked per the plan's objective: manual-trigger parity via the existing `POST /api/retention/run` endpoint; no background scheduler added (explicitly deferred, not built here).

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the 365-day retention sweep test (real cutoff)** - `7db59fd` (test) — RED, all 4 tests failed solely on `AttributeError: 'RetentionService' object has no attribute 'cleanup_agent_location_history'`.
2. **Task 2: Add cleanup_agent_location_history + policy default + run_cleanup wiring** - `530314e` (feat) — GREEN, all 4 tests pass.

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `backend/tests/test_retention_agent_location_history.py` - 4 hermetic tests: 365-day boundary deletion behavior, native-datetime cutoff assertion, run_cleanup report key presence, and the default-365-when-no-policy-passed case
- `backend/retention_service.py` - Added `cleanup_agent_location_history(retention_days=365)`; wired its call and count into `run_cleanup()`
- `backend/retention_endpoints.py` - `_POLICY_DEFAULTS["agent_location_history"]` = 365-day policy default (this line already existed uncommitted in the working tree at plan start, from a prior partial session; confirmed correct and committed as part of Task 2)

## Decisions Made
- Retention-enforcement trigger: manual-trigger-only via existing `POST /api/retention/run`, matching the existing module's actual (no-scheduler) precedent — an automatic sweep is explicitly deferred per the plan's locked objective, not built in this plan.
- Cutoff comparison uses a native `datetime` object directly (`{"timestamp": {"$lt": cutoff}}`), never `.isoformat()`, since `agent_location_history.timestamp` is a real BSON Date written by 46-02 — distinct from the other 3 existing `cleanup_*` methods, which compare against ISO-string-typed fields in their respective collections (unchanged, out of scope).
- Test hermeticity: since `mongomock` is not installed in this backend environment, wrote a small in-memory fake collection whose `delete_many()` genuinely evaluates the `$lt` filter against seeded native-datetime rows, so the 365-day boundary behavior is actually exercised rather than only asserted on the filter's shape (per 46-RESEARCH.md's caution about TTL/expiry claims needing real behavioral verification, not mock-shape-only assertions).

## Deviations from Plan

None - plan executed exactly as written. (The `_POLICY_DEFAULTS` entry was found already present, uncommitted, in the working tree at plan start — verified it exactly matched the plan's required shape and committed it as part of Task 2's atomic commit; no code change was needed for that piece.)

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The 365-day location-history retention decision (D-01) is now fully routed through the existing `/api/retention/*` module: a real cleanup method wired into `run_cleanup()`'s report, plus the matching policy default — closing success criterion 4 (a deliberate, pre-implementation-resolved decision, not a silent 30-day inheritance).
- `security_events`/`alerts` remain a pre-existing, out-of-scope gap (policy docs with no cleanup implementation) — unchanged by this plan, not newly introduced.
- No blockers for phase 46's remaining plans (46-04 through 46-07).

---
*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files and both task commit hashes verified present on disk and in git history.
