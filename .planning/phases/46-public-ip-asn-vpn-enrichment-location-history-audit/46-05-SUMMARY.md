---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 05
subsystem: api
tags: [fastapi, mongodb, tenant-isolation, geoip, asn]

# Dependency graph
requires:
  - phase: 46-01
    provides: agent_asn_service.lookup(public_ip) -> {"asn": {...}, "vpn_heuristic": bool}
  - phase: 46-02
    provides: agent_location_history_service.py (record_location_change, get_track_agent_location), the append-only agent_location_history collection
provides:
  - "Heartbeat and registration handlers now run agent_asn_service.lookup + record_location_change inline, gated on the per-tenant track_agent_location toggle (D-02)"
  - "agents.geo.asn / agents.geo.vpn_heuristic persist on every enriched heartbeat/registration (D-13)"
  - "First-ever registration with a public IP writes an initial agent_location_history row"
affects: ["46-06 (any downstream consumer of geo.asn/vpn_heuristic)", "46-07 (frontend location-history panel now has real data flowing in)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Toggle-gate resolved once per request (get_track_agent_location), reused to gate both the ASN lookup and the record_location_change call — avoids a second toggle read and keeps the two behaviors atomic per request"
    - "Merge ASN/VPN fields into the same 'geo' dict rather than separate dotted $set keys ('geo.asn') to avoid a MongoDB path-conflict between a top-level 'geo' key and a 'geo.asn' subpath in the same update document"
    - "Self-contained, unrelated blocks extracted to standalone service modules purely to satisfy the CLAUDE.md 500-line file cap, preserving behavior 1:1"

key-files:
  created:
    - backend/tests/test_agent_location_history_wiring.py
    - backend/agent_auto_update_service.py
    - backend/agent_heartbeat_alerts_service.py
  modified:
    - backend/agent_heartbeat_endpoints.py
    - backend/agent_registry_endpoints.py

key-decisions:
  - "Repaired a pre-existing, uncommitted, broken partial-wiring attempt already present in the working tree rather than rewriting from scratch — its overall shape (imports, block placement) already matched this plan's design; two real bugs needed fixing (see Deviations)."
  - "geo.asn/geo.vpn_heuristic written via a merged 'geo' dict, not separate dotted $set keys, to avoid a MongoDB update-path conflict."
  - "agent_heartbeat_endpoints.py was already at 517 lines (over the CLAUDE.md 500-line cap) before this plan touched it, from an unrelated prior commit (757595a). Extracted three self-contained, unrelated blocks (auto-update push, persistence_detection handling, pii_scanner handling) into two new service modules to bring it to 480 lines and satisfy both CLAUDE.md and this plan's own acceptance criterion."

requirements-completed: [GAUD-01]

coverage:
  - id: D1
    description: "Heartbeat with a public IP and the toggle ON invokes agent_asn_service.lookup and record_location_change; geo.asn/geo.vpn_heuristic persist in the agents.update_one $set"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_wiring.py::TestToggleOn::test_heartbeat_toggle_on_invokes_asn_and_history_and_persists_geo_asn"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_location_history_wiring.py::TestToggleOn::test_register_toggle_on_invokes_asn_and_history"
        status: pass
    human_judgment: false
  - id: D2
    description: "Toggle OFF skips agent_asn_service.lookup and record_location_change, but geoip_service.lookup (city/country) still runs and geo still persists (scope boundary, T-46-05-B)"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_wiring.py::TestToggleOff::test_heartbeat_toggle_off_skips_asn_and_history_but_keeps_geoip"
        status: pass
    human_judgment: false
  - id: D3
    description: "First-ever registration (no existing_agent) with a public IP and toggle ON calls record_location_change with existing_agent=None so its first-ever branch writes an initial history row"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_wiring.py::TestRegisterFirstSeen::test_first_ever_registration_writes_initial_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "No public IP in the heartbeat payload performs no geoip/ASN lookup and no record_location_change call"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history_wiring.py::TestPrivateIp::test_heartbeat_no_public_ip_skips_everything"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both handler files stay under the CLAUDE.md 500-line cap and the full backend suite shows no new failures vs the pre-existing baseline"
    verification:
      - kind: unit
        ref: "wc -l backend/agent_heartbeat_endpoints.py (480) / backend/agent_registry_endpoints.py (386); full suite 1387 passed / 34 skipped / 8 pre-existing failures"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 05: Heartbeat/Registration ASN + Location-History Wiring Summary

**agent_heartbeat_endpoints.py and agent_registry_endpoints.py now call agent_asn_service.lookup + record_location_change inline in the existing geo block, gated on the per-tenant track_agent_location toggle, with geoip_service's city/country enrichment staying unconditional.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-29T07:47:00Z (approx)
- **Completed:** 2026-07-29T07:56:36Z
- **Tasks:** 2
- **Files modified:** 4 (2 endpoint files modified, 2 new small extraction modules created, 1 test file created)

## Accomplishments
- `agent_heartbeat_endpoints.py`'s heartbeat handler and `agent_registry_endpoints.py`'s registration handler both resolve `get_track_agent_location(db, tenant_id)` once per request and use it to gate both `agent_asn_service.lookup` and `record_location_change` — when OFF, neither runs, but `geoip_service.lookup` (city/country) is untouched.
- `geo.asn`/`geo.vpn_heuristic` persist on the agent doc via a merged `geo` dict (not separate dotted `$set` keys), avoiding a MongoDB update-path conflict.
- `record_location_change` is called with the `existing_agent` doc already fetched earlier in each handler (D-05, zero extra reads); passing `None` on first-ever registration lets the service's first-ever branch write an initial `agent_location_history` row.
- `agent_heartbeat_endpoints.py` brought from 517 lines (already over the CLAUDE.md 500-line cap before this plan touched it) down to 480 lines by extracting three self-contained, unrelated blocks into two new modules.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write wiring tests (toggle gating, geo.asn persistence, record invocation)** - `37b8caf` (test)
2. **Task 2: Wire ASN enrichment + location-history into heartbeat and registration** - `dc77536` (feat)

_Note: 5 wiring tests were written; 4 failed against the working tree's pre-existing (uncommitted) partial-wiring attempt for real bugs (see Deviations), 1 passed incidentally — functionally equivalent RED-phase evidence to a clean absence, per the same precedent documented in 46-04-SUMMARY.md._

## Files Created/Modified
- `backend/tests/test_agent_location_history_wiring.py` - toggle_on/toggle_off/register_first_seen/private_ip wiring tests for both handlers
- `backend/agent_heartbeat_endpoints.py` - toggle-gated ASN enrichment + record_location_change call in the heartbeat geo block; auto-update-push/persistence-detection/pii-scanner blocks extracted out
- `backend/agent_registry_endpoints.py` - toggle-gated ASN enrichment + record_location_change call in the registration geo block
- `backend/agent_auto_update_service.py` - new: `maybe_push_update_instruction(db, agent_id, payload)`, extracted verbatim from the heartbeat handler
- `backend/agent_heartbeat_alerts_service.py` - new: `persist_persistence_detection` / `persist_pii_scanner`, extracted verbatim from the heartbeat handler

## Decisions Made
- Repaired the pre-existing (uncommitted) draft wiring in place rather than rewriting from scratch — its import placement and block location already matched this plan's design.
- Single toggle read per request (not one for the ASN gate and a second implicit one inside `record_location_change`, though the service function does still internally re-check the toggle as defense-in-depth — see `agent_location_history_service.record_location_change`'s own `get_track_agent_location` call). The endpoint-level gate is what determines whether `record_location_change` is invoked at all, which is what the wiring tests assert.
- Extracted three unrelated, self-contained blocks out of `agent_heartbeat_endpoints.py` into two new small modules to satisfy the CLAUDE.md 500-line cap (see Deviations #3).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `record_location_change` called with the wrong argument signature**
- **Found during:** Task 1 (writing the wiring tests) / confirmed running them against the working tree
- **Issue:** The working tree already had an uncommitted, broken partial-wiring attempt (from an earlier, interrupted session) that called `record_location_change(db, merged_agent)` — a 2-argument call — against a function that requires `(db, existing_agent, agent_id, tenant_id, public_ip, geo, asn_enrichment, now=None)`. This was silently swallowed by the surrounding `try/except Exception` in both files, so it would have run in production but never actually written a history row or updated the shadow fields — a fully silent no-op.
- **Fix:** Rewrote both call sites to pass the full 7-argument signature using the `existing_agent`/`agent_id`/`tenant_id`/`public_ip`/`geo`/`asn_enrichment` locals already in scope in each handler.
- **Files modified:** `backend/agent_heartbeat_endpoints.py`, `backend/agent_registry_endpoints.py`
- **Verification:** `TestToggleOn`/`TestRegisterFirstSeen` assert `record_location_change`'s actual call args (e.g. `call_args.args[1] is None` for first-ever registration).
- **Committed in:** `dc77536` (Task 2 commit)

**2. [Rule 1 - Bug] ASN enrichment was not gated on the `track_agent_location` toggle, and used a dotted-key `$set` that conflicts with the existing `geo` key**
- **Found during:** Task 1 (writing the toggle_off test) / confirmed in Task 2
- **Issue:** The same pre-existing draft called `agent_asn_service.lookup(public_ip)` unconditionally (never checking the toggle at all — `get_track_agent_location` was imported in the registration file but never called, and not imported at all in the heartbeat file), and wrote `update_data["geo.asn"]`/`update_data["geo.vpn_heuristic"]` as separate dotted keys in the same `$set` document that also contains a top-level `"geo"` key whenever `geoip_service.lookup` returned a truthy result — a real MongoDB update conflict ("Updating the path 'geo.asn' would create a conflict at 'geo'") that would have raised on every heartbeat/registration where both city/country and ASN data were present.
- **Fix:** Added `get_track_agent_location` to the heartbeat file's imports; resolved the toggle once per request and used it to gate the ASN lookup in both files; merged `asn`/`vpn_heuristic` into the same `geo` dict (`geo = {**(geo or {}), "asn": ..., "vpn_heuristic": ...}`) instead of separate dotted keys.
- **Files modified:** `backend/agent_heartbeat_endpoints.py`, `backend/agent_registry_endpoints.py`
- **Verification:** `TestToggleOn` asserts `set_doc["geo"]["asn"]`/`set_doc["geo"]["city"]` coexist in the same `$set` payload without error; `TestToggleOff` asserts `agent_asn_service.lookup` is never called and `"asn"` is absent from `set_doc["geo"]` when the toggle is OFF.
- **Committed in:** `dc77536` (Task 2 commit)

**3. [Rule 2 - CLAUDE.md compliance] `agent_heartbeat_endpoints.py` exceeded the CLAUDE.md 500-line cap**
- **Found during:** Task 2 acceptance-criteria check (`wc -l < backend/agent_heartbeat_endpoints.py`)
- **Issue:** The file was already at 517 lines at `HEAD` — before this plan's changes — due to an earlier, unrelated commit (`757595a feat(agent-geo): ...`). This plan's own acceptance criteria (and CLAUDE.md's hard "keep files under 500 lines" rule) require the file be under 500 after this plan's wiring lands; adding the toggle-gated ASN/history calls on top of the existing overage pushed it to 543 lines.
- **Fix:** Extracted three self-contained, behaviorally-unrelated blocks verbatim into two new modules: the Windows auto-update-instruction push (`agent_auto_update_service.maybe_push_update_instruction`) and the `persistence_detection`/`pii_scanner` telemetry handlers (`agent_heartbeat_alerts_service.persist_persistence_detection` / `persist_pii_scanner`). Each call site in the endpoint file was replaced with a single `await` call. No behavior change — same inputs (`db`, `agent_id`, `payload`/`meta` sub-dict, `background_tasks`), same outputs.
- **Files modified:** `backend/agent_heartbeat_endpoints.py` (new imports + call-site replacement); new files `backend/agent_auto_update_service.py`, `backend/agent_heartbeat_alerts_service.py`
- **Verification:** `wc -l < backend/agent_heartbeat_endpoints.py` now returns 480; full backend suite re-run confirmed no new failures (see Issues Encountered).
- **Committed in:** `dc77536` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 real bugs in a pre-existing uncommitted draft, 1 Rule 2 CLAUDE.md line-cap compliance fix)
**Impact on plan:** All three were necessary for correctness (a silently-broken history write and a MongoDB update-conflict crash) or for satisfying this plan's own acceptance criteria and CLAUDE.md. No architectural changes, no scope creep — the extracted modules preserve identical behavior for code paths outside this plan's stated scope.

## Issues Encountered
- The working tree had an uncommitted, partially-wired draft of this exact plan's scope already present (imports for `agent_asn_service`/`record_location_change` added, ASN enrichment block present, but broken as documented above) — presumably from a prior, interrupted execution attempt. Repaired in place per the same precedent set by 46-04's summary (`agent_location_history_endpoints.py` was also found pre-existing and broken, and was repaired rather than rewritten).
- Full backend suite (excluding pre-existing broken-collection files unrelated to this plan: `test_rebac.py`, `test_ai_service_config.py`, `test_network_endpoint.py`, `test_sbom_api.py`, `tests/test_graphql.py`) showed **1387 passed / 34 skipped / 8 failed**. All 8 failures are pre-existing and unrelated to this plan's files, matching 46-04-SUMMARY.md's documented baseline exactly: `test_webhook_logic.py` x2, `tests/test_agentic_ai.py` tool_choice test, `tests/test_e2e_integration.py` golden path, `tests/test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`, `tests/test_support_admin_to_user.py` x3 (event-loop/asyncio environment issue). None reference `agent_heartbeat_endpoints.py`, `agent_registry_endpoints.py`, `agent_asn_service.py`, `agent_location_history_service.py`, `agent_auto_update_service.py`, or `agent_heartbeat_alerts_service.py`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both handlers now produce live `geo.asn`/`geo.vpn_heuristic` and append-only `agent_location_history` rows in real traffic (subject to the per-tenant toggle, default ON). 46-04's read surface (`GET /api/agents/{agent_id}/location-history`, `GET/PATCH /api/settings/agent-location-tracking`) can now serve real data instead of an empty collection.
- 46-07 (frontend `AgentLocationHistory` panel) can proceed with confidence that heartbeats/registrations are actually populating the collection it reads from.
- No new blockers.

---
*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files confirmed present on disk; both task commits (`37b8caf`, `dc77536`) confirmed in git log.
