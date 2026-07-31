---
phase: 47-agent-scoped-geo-security-detectors
plan: 01
subsystem: api
tags: [ueba, alert-fan-out, python, pytest, tdd, bugfix]

# Dependency graph
requires: []
provides:
  - "ueba_service.persist_security_alert — real, importable public alias of ueba_service._persist_alert"
  - "5 previously-silent heartbeat alert call sites (shadow_ai, ueba_anomaly, fim_violation, pii_detected, runtime_security) now actually fan out to db.security_alerts + streaming broker + blockchain audit"
  - "Regression test proving importability and functional equivalence (backend/tests/test_persist_security_alert.py)"
affects: [47-03, 47-02, GSEC-02, GSEC-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Public alias for a private helper (`name = _private_impl`) rather than rename — preserves all existing internal call sites verbatim while unblocking new external importers"
    - "Hermetic AsyncMock/MagicMock db + monkeypatched streaming_service.broker.publish, asyncio.run() — mirrors test_agent_location_history.py's convention"

key-files:
  created: [backend/tests/test_persist_security_alert.py]
  modified: [backend/ueba_service.py]

key-decisions:
  - "Fixed via alias (persist_security_alert = _persist_alert), not rename — per plan prohibition, preserves the 4 internal _persist_alert call sites (lines 243, 319, 431, 450) untouched"
  - "Logged ueba_service.py's pre-existing >500-line CLAUDE.md violation (572 lines before this plan, 584 after) to deferred-items.md rather than refactoring — out of scope for this minimal prerequisite fix"

patterns-established:
  - "When a plan's own verification says 'reactivating a previously-broken call path may surface newly-visible side effects in unrelated tests,' explicitly diff the change in isolation (temporarily revert just the one file, re-run the suspect tests, restore) rather than assuming any new failure is caused by the change"

requirements-completed: [GSEC-02, GSEC-03]

coverage:
  - id: D1
    description: "ueba_service.persist_security_alert is a real, importable public symbol, identical object to _persist_alert"
    requirement: "GSEC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_persist_security_alert.py::TestPersistSecurityAlertImportable::test_persist_security_alert_importable"
        status: pass
      - kind: unit
        ref: "backend/tests/test_persist_security_alert.py::TestPersistSecurityAlertImportable::test_persist_security_alert_is_alias"
        status: pass
    human_judgment: false
  - id: D2
    description: "Calling persist_security_alert inserts a doc into db.security_alerts carrying the given alert_type/severity — the fan-out actually fires end-to-end"
    requirement: "GSEC-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_persist_security_alert.py::TestPersistSecurityAlertInserts::test_persist_security_alert_inserts"
        status: pass
    human_judgment: false

# Metrics
duration: 5min
completed: 2026-07-29
status: complete
---

# Phase 47 Plan 01: Fix Broken Alert Fan-Out (persist_security_alert) Summary

**Added a public `persist_security_alert` alias in `ueba_service.py` for the previously-nonexistent name, reactivating 5 silently-broken heartbeat alert call sites and unblocking Plan 47-03's GSEC-02/03 wiring.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-29T12:53:05Z
- **Completed:** 2026-07-29T12:57:49Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `backend/ueba_service.py` now exports a real, public `persist_security_alert` name (`= _persist_alert`), fixing the `ImportError` five existing heartbeat call sites (`shadow_ai`, `ueba_anomaly`, `fim_violation`, `pii_detected`, `runtime_security`) have silently swallowed since they were written (47-RESEARCH.md Pitfall 1).
- Added `backend/tests/test_persist_security_alert.py` — 3 hermetic regression tests proving importability, object-identity aliasing, and end-to-end insertion into `db.security_alerts`.
- Confirmed, by isolating the change (temporarily reverting just `ueba_service.py` and re-running the failing tests), that this fix introduces zero new test failures across the full backend suite.

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: Write failing importability + fan-out regression test** - `edc4abe` (test)
2. **Task 2: Add public persist_security_alert alias in ueba_service.py** - `ad0d46e` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/tests/test_persist_security_alert.py` - New hermetic regression test module (3 tests: importable, is-alias, inserts)
- `backend/ueba_service.py` - Added `persist_security_alert = _persist_alert` public alias + explanatory comment after `_persist_alert`'s definition (line ~105-114)

## Decisions Made
- Alias over rename: `persist_security_alert = _persist_alert` placed immediately after the function body, per the plan's explicit prohibition against renaming `_persist_alert` (would require touching its 4 internal call sites at lines 243/319/431/450 — out of scope and riskier than necessary).
- Deferred `ueba_service.py`'s pre-existing 500-line CLAUDE.md overage (572 → 584 lines) to `deferred-items.md` rather than refactoring inline — this plan's `<prohibitions>` scope it strictly to the alias fix, and a file split is unrelated structural work best done alongside a future phase that touches this file again.

## Deviations from Plan

None on task execution — both tasks matched their `<action>`/`<verify>`/`<acceptance_criteria>` blocks with no scope changes.

**One process deviation on state-update mechanics:** this plan's frontmatter lists `requirements: [GSEC-02, GSEC-03]`, but 47-02/47-03/47-04 (and 47-06 for GSEC-03) also carry those same requirement IDs — GSEC-02/GSEC-03 are the full impossible-travel/geo-fence *features*, of which this plan delivers only the prerequisite alert-fan-out fix. Checking off GSEC-02/GSEC-03 in REQUIREMENTS.md now would falsely claim the detectors themselves exist. `requirements.mark-complete` was intentionally NOT invoked for this plan; the checkboxes remain unchecked until the plan(s) that actually implement the detector logic land.

## Issues Encountered

**Verification of "no new failures" required extra diligence.** The plan's own `<verification>` section flagged that reactivating 5 previously-silent alert call sites "may cause tests that asserted 'no alert written' purely because the import failed to now see an alert." A full-suite run turned up 8 failures (vs. the documented 3-failure baseline from project memory). Rather than assume the extra 5 were caused by this change, I:
1. Grepped the 5 unexplained failing test files for any reference to `ueba_service`/`persist_security_alert`/`_persist_alert` — none found.
2. Temporarily restored the pre-change `ueba_service.py` (saved via `git show HEAD:...` before reverting, no destructive git operations used) and re-ran just the 5 unexplained failures — they reproduced identically without this plan's change (RuntimeError: no current event loop in `test_support_admin_to_user.py`; unrelated intent-parsing assertions in `test_webhook_logic.py`).
3. Restored the alias and re-confirmed the regression suite green.

Conclusion: all 8 failures are pre-existing/environmental, none attributable to this plan. The 3 originally-documented baseline fails (`test_e2e_integration.py`, `test_rust_heartbeat_parity.py`, `test_agentic_ai.py` tool_choice) plus 5 additional pre-existing fails (`test_webhook_logic.py` x2, `test_support_admin_to_user.py` x3) accumulated since the 2026-07-22 memory snapshot, unrelated to Phase 47.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

`persist_security_alert` is now a real, importable, functionally-verified public symbol in `ueba_service.py`. Plan 47-03's heartbeat wiring for GSEC-02 (impossible-travel) and GSEC-03 (geo-fence) can now call it directly to reuse the existing alert fan-out (`db.security_alerts` insert + streaming broker publish + blockchain audit block), per 47-RESEARCH.md's Wave-0 prerequisite. No blockers for Plan 47-02.

## Self-Check: PASSED

- FOUND: backend/tests/test_persist_security_alert.py
- FOUND: `persist_security_alert = _persist_alert` alias in backend/ueba_service.py
- FOUND: commit edc4abe (Task 1: test)
- FOUND: commit ad0d46e (Task 2: feat)

---
*Phase: 47-agent-scoped-geo-security-detectors*
*Completed: 2026-07-29*
