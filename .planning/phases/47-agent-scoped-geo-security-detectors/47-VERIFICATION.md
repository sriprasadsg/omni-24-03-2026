---
phase: 47-agent-scoped-geo-security-detectors
verified: "2026-07-29T20:15:00Z"
status: passed
score: 6/6 must-haves verified (0 behavior-unverified)
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - "test: "Load an agent card (AgentList.tsx) for an agent whose public IP resolves to a known VPN/hosting AS-org (vpn_heuristic === true on agent.geo)"
  - "test: "As a tenant admin, open the new 'Geo Security' panel (Sidebar -> Management & Settings -> Geo Security). Toggle 'Impossible-Travel Detection' off then on. Toggle 'Geo-Fence Detection' on. Add a country code (e.g. US), confirm it appears as a chip, then remove it. Reload the page and confirm settings persisted. Attempt the same as a non-admin and confirm the panel/mutation is inaccessible."

---

# Phase 47: Agent-Scoped Geo Security Detectors Verification Report

**Phase Goal:** Give tenant admins alert-only location-based security signal on their fleet — impossible-travel detection and geo-fence violations, both alert-only — informed by a heuristic VPN/hosting flag so admins aren't drowning in corporate-VPN false positives.
**Verified:** 2026-07-29T20:15:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `ueba_service.persist_security_alert` is a real, importable alias of `_persist_alert` and the reused fan-out actually fires (no parallel alert path) | VERIFIED | `backend/ueba_service.py:114` — `persist_security_alert = _persist_alert`. 3 tests in `test_persist_security_alert.py` (importable, is-alias, inserts) pass. `grep -c persist_security_alert backend/geo_security_service.py` = 0 (no parallel write path). |
| 2 | Impossible-travel fires (haversine/elapsed-hours > 1000 km/h) with VPN suppression (`is True` only), 15-min elapsed floor, and no fire on first check-in (GSEC-02, D-01/D-02/D-08) | VERIFIED | `backend/geo_security_service.py:55-104` `evaluate_impossible_travel`. 12+ dedicated unit tests in `test_geo_security_service.py` (`TestImpossibleTravel`, `TestVpnSuppression`, `TestFirstCheckin`, `TestElapsedFloor`) all pass, directly exercising each guard (positive/below-speed, vpn-true-either-side, vpn-None-does-not-suppress, missing-geo, 10min-suppress/20min-fires, clock-skew). |
| 3 | Geo-fence fires when `country_code` is outside the tenant allowlist (case-insensitive ISO 3166 alpha-2); does not fire when allowed, empty, or missing (GSEC-03, D-03) | VERIFIED | `backend/geo_security_service.py:107-117` `evaluate_geo_fence`. `TestGeoFence` (6 tests) covers violation, case-insensitivity, clean-in-allowlist, empty country, None country, empty allowlist — all pass. |
| 4 | Dedup fires exactly once on the clean→violating transition and re-fires after the 6h cooldown while still violating; a clean call clears state (D-05/D-07 state-transition invariant) | VERIFIED (behavioral) | `test_geo_security_service.py::TestDedupCooldown::test_dedup_cooldown_transition_then_suppress_then_refire_then_clear` directly exercises: fire on transition → suppress within cooldown → re-fire after `lastAlertedAt` > 6h stale → clear on clean call. All 4 phases asserted and passing. This is the exact state-transition/cooldown invariant Step 3 requires behavioral evidence for, and a passing named test provides it. |
| 5 | On a heartbeat, `run_geo_security_detectors` runs against the RAW `existing_agent` (pre-update) + newly-resolved geo, and each returned alert payload reaches `persist_security_alert` (reused fan-out); empty payloads persist nothing; a detector exception is caught/logged and never fails the heartbeat (GSEC-02/03, D-04 alert-only) | VERIFIED (behavioral) | `backend/agent_heartbeat_endpoints.py:162-174` — call-through inside `if public_ip and track_location:`, wrapped in try/except, using `existing_agent` (fetched line 65, before the `update_one` at line 146) as previous state. `test_agent_heartbeat_geo_security.py`'s 3 tests directly assert: (a) one payload → `persist_security_alert` awaited once with matching kwargs, (b) empty list → never called, (c) detector raises → heartbeat still returns `{"success": True}` and persist never called. All 3 pass — this is a genuine behavioral proof of the cancellation/no-crash invariant, not presence alone. |
| 6 | A tenant admin can define allowed regions via admin-gated GET/PATCH `/api/settings/geo-security`, with ISO-3166 alpha-2 input validation and non-admin rejection (GSEC-03 config half) | VERIFIED | `backend/geo_security_endpoints.py` — router registered in `router_registry.py:173`. 5 tests in `test_geo_security_endpoints.py` pass: admin gate (non-admin → 403), GET defaults, PATCH persists tenant-scoped doc, malformed country code rejected, lowercase normalized to uppercase. |

**Score:** 6/6 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/ueba_service.py` | Public `persist_security_alert` alias | VERIFIED | Line 114, `persist_security_alert = _persist_alert`; 4 internal `_persist_alert` call sites untouched (lines 243/319/431/450) |
| `backend/tests/test_persist_security_alert.py` | Regression test for fan-out | VERIFIED | 3 tests, all pass |
| `backend/geo_security_service.py` | Detector core (5 exported functions) | VERIFIED | 278 lines; `evaluate_impossible_travel`, `evaluate_geo_fence`, `get_geo_security_settings`, `dedup_and_maybe_alert`, `run_geo_security_detectors` all present and correct; imports `_haversine_km` from `ueba_service` (no re-copy) |
| `backend/tests/test_geo_security_service.py` | Hermetic unit tests | VERIFIED | 24 tests, all pass |
| `backend/agent_heartbeat_endpoints.py` | Toggle-gated detector call-through | VERIFIED | 480 lines (< 500 cap); imports + call-through at lines 14-15, 166-174; `existing_agent` (pre-update) used as prior state |
| `backend/tests/test_agent_heartbeat_geo_security.py` | Wiring regression test | VERIFIED | 3 tests, all pass |
| `backend/geo_security_endpoints.py` | Admin-gated settings endpoints | VERIFIED | 109 lines; GET/PATCH, `_require_admin`, `field_validator` for country codes |
| `backend/router_registry.py` | Router registration | VERIFIED | `_load(app, "geo_security_endpoints", "router")` at line 173 |
| `backend/tests/test_geo_security_endpoints.py` | Endpoint tests | VERIFIED | 5 tests, all pass |
| `types.ts` | `GeoLocation.vpn_heuristic?`/`asn?` | VERIFIED | Lines 695-705; both optional, correctly typed |
| `components/AgentList.tsx` | Amber heuristic badge | VERIFIED | Lines 227-232; guarded `=== true`; wording "likely VPN/hosting"; `grep -i detected` returns no matches in this file |
| `services/apiService.ts` | Geo-security settings API clients | VERIFIED | Lines 4658-4690; `GeoSecuritySettings`, `getGeoSecuritySettings`, `setGeoSecuritySettings` targeting `/settings/geo-security` |
| `components/SecuritySettingsDashboard.tsx` | Admin config panel | VERIFIED | 196 lines; loads on mount, persists toggles + allowlist edits, explicitly labeled alert-only/no-blocking |
| `App.tsx` / `components/Sidebar.tsx` | Panel registration | VERIFIED | `geoSecurity` lazy import + view case + `viewPermissionMap` entry in App.tsx; nav entry gated `manage:settings` in Sidebar.tsx; dedicated `SecuritySettingsDashboard-*.js` chunk confirmed emitted by `npm run build` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `agent_heartbeat_endpoints.py` | `geo_security_service.py` | `run_geo_security_detectors(...)` call after `record_location_change` | WIRED | Confirmed at lines 168-170; uses raw `existing_agent` + newly resolved `geo` |
| `agent_heartbeat_endpoints.py` | `ueba_service.py` | `persist_security_alert(db, **payload)` per returned alert | WIRED | Confirmed at line 172; behavioral test proves it fires with correct kwargs and is skipped when payloads are empty |
| `geo_security_service.py` | `ueba_service.py` | `from ueba_service import _haversine_km` | WIRED | Line 38; no re-copied formula |
| `geo_security_endpoints.py` | `geo_security_service.py` | `get_geo_security_settings` for GET resolution | WIRED | Line 20 import, called at line 75 |
| `router_registry.py` | `geo_security_endpoints.py` | `_load(app, "geo_security_endpoints", "router")` | WIRED | Line 173, immediately after `agent_location_history_endpoints` |
| `components/AgentList.tsx` | `types.ts` | reads `agent.geo.vpn_heuristic` (typed `GeoLocation`) | WIRED | Type-checks under `tsc --noEmit` for this file; no `any` |
| `components/SecuritySettingsDashboard.tsx` | `services/apiService.ts` | `getGeoSecuritySettings`/`setGeoSecuritySettings` | WIRED | Import at line 2, called in `load()`/`persist()` |
| `services/apiService.ts` | `backend/geo_security_endpoints.py` | GET/PATCH `/settings/geo-security` | WIRED | Path strings match on both sides |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Fan-out alias importable + fires | `pytest backend/tests/test_persist_security_alert.py -q` | 3 passed | PASS |
| Detector core (all guards + dedup/cooldown state machine) | `pytest backend/tests/test_geo_security_service.py -q` | 24 passed | PASS |
| Heartbeat wiring (payload→persist, empty→skip, exception→never fails) | `pytest backend/tests/test_agent_heartbeat_geo_security.py -q` | 3 passed | PASS |
| Settings endpoints (admin gate, defaults, persistence, validation) | `pytest backend/tests/test_geo_security_endpoints.py -q` | 5 passed | PASS |
| Full backend suite (regression check) | `pytest backend/tests/ -q --ignore=test_graphql.py` | 1416 passed, 6 failed, 35 skipped | PASS (all 6 failures confirmed pre-existing, unrelated — see below) |
| Frontend typecheck (phase files only) | `npx tsc --noEmit` (filtered to phase-touched files) | 0 errors in `types.ts`/`AgentList.tsx`/`apiService.ts`/`SecuritySettingsDashboard.tsx`/`App.tsx`/`Sidebar.tsx` | PASS (repo-wide `tsc` has pre-existing unrelated errors in vendored `servers/`/`github-mcp-server/` subprojects lacking `node_modules` — confirmed unrelated to any phase-47 file) |
| Production build | `npm run build` | Clean, `SecuritySettingsDashboard-*.js` chunk emitted | PASS |

**Full-suite regression detail:** The 6 failures (`test_agentic_ai.py::test_run_calls_anthropic_with_tool_choice_any`, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`, and 3× `test_support_admin_to_user.py` order-dependent `RuntimeError: no current event loop`) exactly match the pre-existing baseline documented in project memory and in 47-01/47-02/47-03/47-04's own SUMMARY verification sections. `git log` confirms `test_rust_heartbeat_parity.py` was last touched by pre-phase-47 commits (`04789a2`, `3fd1c12`, etc.), and none of the 6 failing test files were modified by this phase. No new failures introduced.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|--------------|----------------|--------------|--------|----------|
| GSEC-01 | 47-05 (primary), 46 (foundation) | Heuristic VPN/hosting flag surfaced, labeled heuristic never "detected" | SATISFIED | `types.ts` typed fields; `AgentList.tsx` + `AgentLocationHistory.tsx` both render amber "likely VPN/hosting" badge, `=== true` guarded, no "detected" wording anywhere in either file. Backend enrichment (`agent_heartbeat_endpoints.py:141-144`) pre-dates this phase (Phase 46) but this phase closes the missing UI surface. |
| GSEC-02 | 47-01, 47-02, 47-03 | Agent-scoped impossible-travel via haversine + time window keyed by agent_id, reusing existing alert fan-out | SATISFIED | Detector core + heartbeat wiring + fan-out reactivation, all behaviorally tested (30 passing tests across the 4 relevant files) |
| GSEC-03 | 47-02, 47-03, 47-04, 47-06 | Per-tenant allowed-region geo-fence, alert-only, no blocking | SATISFIED | Detector logic + heartbeat wiring + admin-gated config endpoints + settings UI panel, all present and tested; no blocking/quarantine logic added (grep confirms only pre-existing, unrelated quarantine/reject code in the file) |

No orphaned requirements — REQUIREMENTS.md maps only GSEC-01/02/03 to Phase 47, all three are claimed and delivered across the 6 plans.

**Minor documentation staleness (not a functional gap):** REQUIREMENTS.md's Traceability table (lines 55-65) still shows "Planned" status for all rows, including GAUD-01/02 which are checked `[x]` complete in the requirements list above (lines 31-32) and GSEC-01/02/03 which are also checked `[x]` (lines 19-21). This is a cosmetic tracking-table lag, not a missing requirement or implementation gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/ueba_service.py` | whole file | 584 lines, exceeds CLAUDE.md's 500-line cap | INFO | Pre-existing (572 lines before Phase 47 touched it per 47-RESEARCH.md and 47-01-SUMMARY.md); this phase added only 12 lines (the alias). Explicitly logged to `deferred-items.md` with a concrete follow-up recommendation (split `_persist_alert`/`persist_security_alert` into a sibling module). Out of scope for 47-01's prohibitions ("MUST NOT rename `_persist_alert`... MUST NOT write a second/parallel alert-insert path"). Does not block phase-goal achievement. |

No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) found in any of the 10 phase-touched files. No stub patterns (empty handlers, static returns, hardcoded-empty props) found.

### Human Verification Required

1 & 2 above (VPN badge visual render, Security settings panel interactive flow) — see frontmatter `human_verification` for full detail. Both are explicitly disclosed as outstanding in 47-05-SUMMARY.md and 47-06-SUMMARY.md, consistent with 47-VALIDATION.md's own "Manual-Only Verifications" table. Neither reflects a coding gap — all automated proxies (tsc, build, unit/endpoint tests, grep wording checks) pass; only live-browser pixel/interaction confirmation is outstanding.

### Gaps Summary

No gaps found. All 3 phase requirements (GSEC-01/02/03) and all 6 roadmap Success Criteria are backed by real, wired, behaviorally-tested code — including the state-transition-sensitive dedup/cooldown logic (D-05/D-07) and the exception-safety invariant (D-04 alert-only), both of which are proven by passing named tests rather than presence alone. The full backend regression suite shows zero new failures. The frontend build is clean and the new UI surfaces are registered and reachable.

The only outstanding items are the two live-browser UAT checks the phase's own plans flagged as Manual-Only from the start (visual badge rendering; interactive settings-panel flow) — these route to human verification per process, which sets phase status to `human_needed` rather than `passed`, but do not indicate any missing or broken implementation.

---

_Verified: 2026-07-29T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
