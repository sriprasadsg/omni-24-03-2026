---
phase: 55-advanced-threat-detection
plan: 05
subsystem: api
tags: [virustotal, threat-intel, httpx, fastapi, gap-closure]

# Dependency graph
requires:
  - phase: 55-advanced-threat-detection (plan 01)
    provides: SiemEngine.correlate_native_findings() and the /correlate-native route wiring
provides:
  - "get_virustotal_client() factory + VirusTotalClient (scan_ip/scan_domain/scan_url/scan_file_hash) in backend/virustotal_client.py"
  - "enrich_file_hashes(hashes) bulk helper"
  - "POST /api/threat-intel/correlate-native reachable (200) through the now-mounted router"
affects: [threat_intel_endpoints, threat_endpoints, soar_engine, agent_security_endpoints]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Synchronous httpx.Client wrapped in a _lookup() helper shared by all scan_* methods; callers invoke via asyncio.to_thread/run_in_executor so a slow VT call never blocks the event loop"
    - "Key-absent / request-failure graceful degrade: always {\"error\": ...} with no fabricated verdict field, never a hard-fail at import/construction"

key-files:
  created:
    - backend/tests/test_threat_intel_correlate_native_route.py
    - backend/tests/test_virustotal_client.py
  modified:
    - backend/virustotal_client.py

key-decisions:
  - "Rewrote virustotal_client.py from scratch rather than patching BaseCapability — the dead VirusTotalScanCapability class was unreferenced (grep-confirmed) and referenced 7 undefined names; deleting it and building the real get_virustotal_client() factory the 4 real callers actually import was the only viable fix."
  - "get_virustotal_client() is a plain factory (fresh VirusTotalClient() per call), not a cached singleton, to avoid stale-API-key state across the process (and across tests that monkeypatch VIRUSTOTAL_API_KEY)."
  - "scan_domain/scan_url/scan_file_hash and enrich_file_hashes were implemented in Task 1's single _lookup()-backed rewrite rather than split across Task 1/Task 2 as the plan's task boundaries suggested — the shared helper made a partial (stub-only) Task-1 implementation artificial. Task 2 became a test-only commit; see Deviations."

patterns-established:
  - "VT v3 result-dict contract: verdict/detectionRatio/malicious/suspicious/harmless/undetected/scanDate/reputation/details on success, {\"error\": ...} on failure/key-absent — reusable for any future threat-intel provider client."

requirements-completed: [INT-04]

coverage:
  - id: D1
    description: "backend/virustotal_client.py imports cleanly (no NameError); get_virustotal_client() factory + scan_ip/scan_domain/scan_url/scan_file_hash + enrich_file_hashes exist and match the four real callers' exact interface"
    requirement: "INT-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_threat_intel_correlate_native_route.py#test_import_virustotal_client_and_threat_intel_endpoints_clean"
        status: pass
      - kind: unit
        ref: "backend/tests/test_virustotal_client.py#TestScanMethodsContract"
        status: pass
      - kind: unit
        ref: "backend/tests/test_virustotal_client.py#TestEnrichFileHashes"
        status: pass
    human_judgment: false
  - id: D2
    description: "POST /api/threat-intel/correlate-native is reachable (200, not 404) through the now-mounted router, delegating to SiemEngine.correlate_native_findings()"
    requirement: "INT-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_threat_intel_correlate_native_route.py#test_correlate_native_route_returns_200_through_mounted_router"
        status: pass
      - kind: unit
        ref: "backend/tests/test_threat_intel_correlate_native_route.py#test_fresh_app_import_no_longer_logs_router_load_failure"
        status: pass
    human_judgment: false
  - id: D3
    description: "API-key-absent behavior is graceful degrade — never a fabricated Harmless/Clean verdict, never an import/startup hard-fail"
    requirement: "INT-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_virustotal_client.py#TestGracefulDegrade"
        status: pass
    human_judgment: false
  - id: D4
    description: "POST /api/threat-intel/scan round-trips 200 (success) and 500 (error) with scan_ip patched"
    verification:
      - kind: integration
        ref: "backend/tests/test_virustotal_client.py#TestScanEndpointRoundTrip"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-08-04
status: complete
---

# Phase 55 Plan 05: VirusTotal Client Rewrite + Correlate-Native Route Gap Closure Summary

**Rewrote the abandoned `backend/virustotal_client.py` (undefined-`BaseCapability` NameError) into a real synchronous VirusTotal API v3 client behind `get_virustotal_client()`, closing 55-VERIFICATION.md gap #1 and making `POST /api/threat-intel/correlate-native` reachable (200) for the first time.**

## Performance

- **Duration:** ~6 min (2026-08-04T00:25:50+05:30 to 2026-08-04T00:31:11+05:30)
- **Started:** 2026-08-03T19:20:00Z (session start)
- **Completed:** 2026-08-03T19:01:11Z
- **Tasks:** 2 (both `tdd="true"`)
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments
- `backend/virustotal_client.py` rewritten: dead `VirusTotalScanCapability(BaseCapability)` class deleted, replaced with `get_virustotal_client()` factory + `VirusTotalClient` (`scan_ip`/`scan_domain`/`scan_url`/`scan_file_hash`, all backed by a shared `_lookup()` helper) + `enrich_file_hashes(hashes)` bulk helper.
- `virustotal_client.py` and `threat_intel_endpoints.py` now import cleanly — `python -c "import app"` no longer logs `[Router] Failed to load threat_intel_endpoints`.
- `POST /api/threat-intel/correlate-native` verified reachable (200) via a live `TestClient` against the real `app` module (using the documented `_fastapi_app` escape hatch to avoid triggering the real Mongo-connecting `lifespan`).
- All four `scan_*` methods return the exact result-dict contract (`verdict`/`detectionRatio`/`malicious`/`suspicious`/`harmless`/`undetected`/`scanDate`/`reputation`/`details`) the four real callers (`threat_intel_endpoints.py`, `threat_endpoints.py`, `soar_engine.py`, `agent_security_endpoints.py`) already read.
- Key-absent and API-error paths always return `{"error": ...}` with no fabricated verdict (T-55-04); artifact values are URL-encoded/base64url-encoded into a fixed `virustotal.com` path, never the host (T-55-02).

## Task Commits

Each task was committed atomically (both tasks used `tdd="true"`, RED/GREEN cycle):

1. **Task 1: Tracer — get_virustotal_client() + scan_ip end-to-end, correlate-native route reachable**
   - `8c32082` (test — RED): add failing test for correlate-native route reachability
   - `766e3ca` (feat — GREEN): implement get_virustotal_client() factory + real VT v3 client
2. **Task 2: Expansion — scan_domain/scan_url/scan_file_hash + enrich_file_hashes, full result-dict contract tests**
   - `f7c9992` (test): full contract tests for scan_domain/url/hash + enrich_file_hashes (no separate `feat` commit needed — see Deviations)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/virustotal_client.py` - Rewritten: `get_virustotal_client()` factory, `VirusTotalClient` class (`scan_ip`/`scan_domain`/`scan_url`/`scan_file_hash` via shared `_lookup()`), `enrich_file_hashes()` bulk helper; dead `VirusTotalScanCapability` class removed
- `backend/tests/test_threat_intel_correlate_native_route.py` - New: live `TestClient` test proving `/correlate-native` mounts and returns 200; import-cleanliness assertions; grep-pinned router-load-failure-string absence check
- `backend/tests/test_virustotal_client.py` - New: full result-dict contract tests for all four `scan_*` methods, graceful-degrade, error path, `enrich_file_hashes` keying/omission, and a `/api/threat-intel/scan` 200/500 round-trip

## Decisions Made
- Rewrote `virustotal_client.py` from scratch instead of patching in a `BaseCapability` base class — the dead class was unreferenced anywhere in the codebase (grep-confirmed) and additionally called 7 more undefined names (`requests`/`psutil`/`hashlib`/`socket`/`subprocess`/`re`/`logger`); repairing it would have been strictly more work than deleting it, per the plan's own "Dead class fate = delete" design decision.
- `get_virustotal_client()` returns a fresh `VirusTotalClient()` on every call rather than caching a module-level singleton — avoids a stale `VIRUSTOTAL_API_KEY` snapshot surviving env-var changes across the process lifetime (and across tests that `monkeypatch.setenv`).
- All four `scan_*` methods share one `_lookup(path)` helper mapping `last_analysis_stats`/`reputation`/`last_analysis_date` into the caller contract — implementing `scan_domain`/`scan_url`/`scan_file_hash` as "stubs" per the plan's literal Task 1 wording would have meant writing the identical logic twice, so all four (plus `enrich_file_hashes`) were implemented together in Task 1's single commit. See Deviations below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, scope-adjacent] Task 1/Task 2 implementation boundary collapsed into Task 1**
- **Found during:** Task 1 (tracer)
- **Issue:** The plan's Task 1 action explicitly asked for "method STUBS for scan_domain/scan_url/scan_file_hash... Task 2 hardens/tests them", implying the full implementation should land in Task 2. Because all four `scan_*` methods are trivial wrappers around one shared `_lookup()` helper, writing "stub" versions and then a separate "hardened" version in Task 2 would have meant either (a) two near-identical passes over the same 15 lines of logic, or (b) an artificially incomplete Task 1 that would fail Task 1's own acceptance criteria if the stubs didn't actually call the VT API correctly.
- **Fix:** Implemented the full `_lookup()`-backed client (`scan_ip`/`scan_domain`/`scan_url`/`scan_file_hash`) plus `enrich_file_hashes` in Task 1's `feat` commit (`766e3ca`). Task 2 became purely a test-authoring task: `test_virustotal_client.py` (RED-checked by first confirming it references no not-yet-defined symbol, then run — all 11 tests passed immediately since the implementation was already complete) plus running the full documented combined-suite acceptance check.
- **Files modified:** backend/virustotal_client.py (Task 1 commit only), backend/tests/test_virustotal_client.py (Task 2 commit)
- **Verification:** All of Task 1's AND Task 2's acceptance criteria (grep counts, contract-dict assertions, 200/500 round-trip, `wc -l < 500`, combined 21-test suite) independently confirmed passing.
- **Committed in:** `766e3ca` (Task 1 feat), `f7c9992` (Task 2 test)

---

**Total deviations:** 1 auto-fixed (Rule 1 — scope-adjacent implementation-ordering collapse, no behavior/contract difference from the plan's intent)
**Impact on plan:** No functional change to what shipped — every acceptance criterion in both tasks is met and independently verified. Only the internal task-boundary bookkeeping (which commit introduced which method) differs from the plan's literal wording.

## Issues Encountered
None - the RED/GREEN TDD cycle worked as expected for Task 1 (test failed against the original broken `virustotal_client.py`, passed after the rewrite). Task 2's tests passed on first run because Task 1's implementation was already complete (see Deviations); this was independently confirmed to not be a stale-passing-test false positive by verifying every individual acceptance-criteria grep/assertion the plan specifies.

## User Setup Required

None - no external service configuration required. `VIRUSTOTAL_API_KEY` remains optional (graceful degrade); if a real key is later configured in `.env`/environment, all four `scan_*` methods will make real outbound `https://www.virustotal.com/api/v3/*` calls with no further code change.

## Next Phase Readiness

- 55-VERIFICATION.md gap #1 (INT-04) is closed: `POST /api/threat-intel/correlate-native` is reachable and returns the `SiemEngine.correlate_native_findings()` summary.
- Full backend regression suite re-run (`tests/` directory, excluding the 4 pre-existing environment-drift collection errors documented in `deferred-items.md` item 2): **1547 passed / 35 skipped / 3 failed** — the 3 failures (`test_agentic_ai.py`, `test_e2e_integration.py`, `test_rust_heartbeat_parity.py`) are the same pre-existing, unrelated failures documented in project memory and `deferred-items.md`; no new regressions introduced by this plan.
- Phase 55 (advanced-threat-detection) has no further known gaps after this plan; a final `/gsd-execute-phase 55` re-verification pass can now confirm the phase is fully closed.

---
*Phase: 55-advanced-threat-detection*
*Completed: 2026-08-04*

## Self-Check: PASSED

All created files confirmed present (`backend/virustotal_client.py`,
`backend/tests/test_threat_intel_correlate_native_route.py`,
`backend/tests/test_virustotal_client.py`, this SUMMARY.md). All 4 commit
hashes (`8c32082`, `766e3ca`, `f7c9992`, `c01e91c`) confirmed present in
`git log --oneline --all`.
