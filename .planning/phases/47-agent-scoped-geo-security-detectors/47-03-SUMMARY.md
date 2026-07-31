---
phase: 47-agent-scoped-geo-security-detectors
plan: 03
subsystem: backend-heartbeat-wiring
tags: [geo-security, impossible-travel, geo-fence, heartbeat, ueba, tdd]
dependency-graph:
  requires:
    - "geo_security_service.run_geo_security_detectors (47-02, orchestrator returning alert payloads)"
    - "ueba_service.persist_security_alert (47-01, alias, the single alert fan-out)"
  provides:
    - "Live toggle-gated GSEC-02/GSEC-03 detector call-through in agent_heartbeat_endpoints.py"
  affects:
    - "backend/geo_security_endpoints.py (later plan — admin config surface for the same toggle)"
tech-stack:
  added: []
  patterns:
    - "Detector call-through placed inside the same if public_ip and track_location: block as record_location_change, its own dedicated try/except so a detector fault is logged and never fails the heartbeat (D-04 alert-only)"
key-files:
  created:
    - backend/tests/test_agent_heartbeat_geo_security.py
  modified:
    - backend/agent_heartbeat_endpoints.py
key-decisions:
  - "Call-through gated by the same track_agent_location toggle Phase 46 used for record_location_change — not a separate flag"
  - "existing_agent (the PRE-update doc fetched at the top of the handler) is passed as previous state, never a debounced shadow field"
  - "Removed 3 dead local 'from ueba_service import persist_security_alert' + try/except ImportError re-imports elsewhere in the same function — they shadowed the new module-level import and produced UnboundLocalError on every heartbeat reaching them"
patterns-established:
  - "Alert-only detector call-through: try/except around the orchestrator call + the persist loop, logging a warning on failure, no re-raise"
requirements-completed: [GSEC-02, GSEC-03]
metrics:
  duration: "~20 minutes"
  completed: 2026-07-29
status: complete
---

# Phase 47 Plan 03: Heartbeat Geo Security Detector Wiring Summary

Wired Plan 47-02's pure `run_geo_security_detectors` orchestrator into the live `POST /api/agents/{agent_id}/heartbeat` path, immediately after Phase 46's `record_location_change` call, fanning any returned alert payload out through the existing `persist_security_alert` alert channel — turning the previously inert detector core into real GSEC-02 (impossible-travel) and GSEC-03 (geo-fence) alerts.

## Performance

- **Duration:** ~20 minutes
- **Completed:** 2026-07-29
- **Tasks:** 2/2 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `run_geo_security_detectors` + `persist_security_alert` imported at module level in `agent_heartbeat_endpoints.py` and invoked once per heartbeat, toggle-gated by `track_agent_location` (same gate as `record_location_change`).
- Each returned alert payload dict is unpacked straight into `persist_security_alert(db, **payload)` — no parallel alert channel, no direct `db.security_alerts` write.
- A detector exception is caught, logged as a warning, and never propagates — the heartbeat still returns `{"success": True}` (D-04 alert-only, verified by a dedicated test).
- `agent_heartbeat_endpoints.py` ends at 480 lines (was 480 before this plan too — the 45-line net-zero diff is the new call-through balanced by removing 3 now-redundant local re-imports), comfortably under the 500-line cap.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing heartbeat-wiring test** - `7041c13` (test)
2. **Task 2: Wire the toggle-gated detector call-through after record_location_change** - `5010857` (feat)

_TDD-style plan: RED (Task 1, confirmed 3/3 failing on `AttributeError: ... does not have the attribute 'run_geo_security_detectors'`) then GREEN (Task 2, all 3 pass)._

## Files Created/Modified
- `backend/tests/test_agent_heartbeat_geo_security.py` - New wiring test module (clones `test_agent_location_history_wiring.py`'s TestClient + dependency-override + shared-rate-limiter-reset pattern). 3 tests: one alert payload persisted, empty list skips persist, detector exception never fails the heartbeat.
- `backend/agent_heartbeat_endpoints.py` - Added the 2 module-level imports and the ~9-line toggle-gated try/except call-through after `record_location_change`; removed 3 dead local re-imports of `persist_security_alert` (Rule 1 fix, see below).

## Task Execution

1. **Task 1 (RED)** — Wrote `test_agent_heartbeat_geo_security.py` driving the real heartbeat route via `TestClient` with `verify_agent_key`/`get_database` overridden and `run_geo_security_detectors`/`persist_security_alert` monkeypatched on the `agent_heartbeat_endpoints` module. Confirmed RED: all 3 tests failed with `AttributeError` (the module doesn't expose `run_geo_security_detectors` yet — the wiring is absent). Commit `7041c13`.
2. **Task 2 (GREEN)** — Added the two module-level imports and the toggle-gated call-through inside the existing `if public_ip and track_location:` block, right after the `record_location_change` try/except. Running the wiring tests immediately surfaced a real bug (see Deviations below); fixed it, then all 3 wiring tests + all 24 `test_geo_security_service.py` tests passed (27/27). Commit `5010857`.

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_agent_heartbeat_geo_security.py backend/tests/test_geo_security_service.py -q` → **27 passed**.
- `grep -c "db.security_alerts.insert" backend/agent_heartbeat_endpoints.py` → **0** (no new direct alert writes — fan-out only via `persist_security_alert`).
- `wc -l backend/agent_heartbeat_endpoints.py` → **480** (under the 500-line cap).
- Full backend suite (`backend/tests/`, excluding `test_graphql.py` per the existing pre-existing `strawberry`/`pydantic` incompatibility): **1411 passed, 6 failed, 35 skipped**. All 6 failures are pre-existing and unrelated, confirmed against project memory and re-run in isolation:
  - `test_agentic_ai.py::test_run_calls_anthropic_with_tool_choice_any` — documented baseline fail (agentic `tool_choice`).
  - `test_e2e_integration.py::test_golden_path_evidence_to_remediation` — documented baseline fail (e2e golden-path evidence).
  - `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` — documented baseline fail (rust parity, `agent_type` missing from a `$push.evidence` array — unrelated to this plan's 2 files).
  - 3 in `test_support_admin_to_user.py` — order-dependent flake (`RuntimeError: There is no current event loop`); re-ran `pytest backend/tests/test_support_admin_to_user.py -q` in isolation → **3 passed**, confirming it reproduces identically without this plan's files present (same class of pre-existing test-order pollution noted for `test_geo_security_service.py`'s 47-02 run and `test_auth_mfa.py` in an earlier session).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed 3 dead local `persist_security_alert` re-imports that shadowed the new module-level import**
- **Found during:** Task 2, first test run after adding the call-through.
- **Issue:** `agent_heartbeat_endpoints.py` already had 3 in-function `from ueba_service import persist_security_alert` statements (inside the `ueba`/`fim`/`runtime_security` `meta` blocks, wrapped in `try/except ImportError: pass` — vestigial guards from before Plan 47-01 made the name a real public alias). Python treats any name assigned anywhere in a function body as local to that function for its entire scope, so these local imports made `persist_security_alert` a local variable throughout `report_heartbeat` — causing `UnboundLocalError: cannot access local variable 'persist_security_alert' where it is not associated with a value` at the new call-through, which runs earlier in the function than those local imports.
- **Fix:** Removed the 3 local `from ueba_service import persist_security_alert` statements and their now-pointless `try/except ImportError: pass` wrapping (the public alias has existed since Plan 47-01, so the guard could never fire), relying on the single module-level import added by this plan. A 4th occurrence inside the `_persist_shadow_ai` nested async function was left as-is initially but also updated for consistency (it lives in its own function scope and wasn't the source of the bug, but shared the same now-redundant pattern).
- **Files modified:** `backend/agent_heartbeat_endpoints.py`.
- **Commit:** `5010857` (included in the Task 2 commit, verified before committing).

No other deviations — plan executed as written; no architectural changes, no new packages, no missing critical functionality found.

## Known Stubs

None.

## Threat Flags

None — this plan's threat register (T-47-03-R/D/E/SC) covers the only security-relevant surface introduced, and all three `mitigate` items are satisfied by construction: `persist_security_alert` is the sole write path (verified above), the call-through never rejects/quarantines/blocks (alert-only, verified by `TestDetectorException`), and the try/except means a detector fault degrades to a logged warning rather than a failed heartbeat.

## Self-Check: PASSED

- `backend/tests/test_agent_heartbeat_geo_security.py` — FOUND.
- `backend/agent_heartbeat_endpoints.py` — FOUND, 480 lines.
- Commit `7041c13` — FOUND in `git log --oneline`.
- Commit `5010857` — FOUND in `git log --oneline`.
