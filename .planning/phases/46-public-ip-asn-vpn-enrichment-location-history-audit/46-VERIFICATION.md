---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
verified: 2026-07-29T14:10:00Z
status: human_needed
score: 4/4 must-haves verified (roadmap success criteria); 0 behavior_unverified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Open an agent's detail view (Overview tab) after a real public-IP/geo change and expand the Location History panel"
    expected: "Panel lazy-fetches on first expand and renders one row per recorded change: country flag + city/country, optional amber 'likely VPN/hosting' badge, monospace public IP, UTC timestamp, and dwell time; last row suffixed '(ongoing)'"
    why_human: "Visual rendering/appearance in a live browser cannot be confirmed by static code inspection alone (component code, wiring, and unit-level behavior were verified; live render was not)"
  - test: "Supply a real (licensed) GeoLite2-ASN.mmdb via GEOIP_ASN_DB_PATH and confirm geo.asn / geo.vpn_heuristic populate on a live agent heartbeat"
    expected: "agent_asn_service.lookup() returns a populated asn sub-object (number/org) for a real public IP, in addition to the vpn_heuristic flag already exercised by the hermetic test suite"
    why_human: "Requires a licensed MaxMind database supplied out-of-band; graceful degrade without it is unit-tested, but real-DB enrichment is not (the phase's own 46-VALIDATION.md flags this as Manual-Only)"
---

# Phase 46: Public-IP ASN/VPN Enrichment + Location-History Audit Verification Report

**Phase Goal:** Give every agent's public-IP/geo change an immutable, queryable audit trail, and lay the ASN/VPN-enrichment foundation (heuristic GeoLite2-ASN + X4BNet lookup) that Phase 47's security detectors depend on — front-loading the false-positive and privacy/legal risks research flagged as this milestone's two biggest.
**Verified:** 2026-07-29T14:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An admin opening an agent's detail view can see a chronological timeline of every public-IP/geo change, with timestamps (GAUD-02) | ✓ VERIFIED | `components/AgentLocationHistory.tsx` mounted in `components/AgentOverviewTab.tsx:215`; renders `sortedEntries` ascending with `formatLocationTimestamp`; fetches via `fetchAgentLocationHistory` → `GET /api/agents/{agent_id}/location-history` which returns tenant-scoped rows sorted ascending. `npx tsc --noEmit` clean on this file, `npm run build` succeeds. Live visual render not observed (see Human Verification). |
| 2 | Location-history entries are append-only — no update or delete path anywhere in the API (GAUD-01) | ✓ VERIFIED | `grep -nE 'agent_location_history\.(update\|delete\|replace\|find_one_and)' backend/agent_location_history_service.py` → no matches; `grep -nE '@router\.(patch\|put\|delete)' backend/agent_location_history_endpoints.py` → only match is `@router.patch("/api/settings/agent-location-tracking")` (the toggle, not the history resource — no path contains "location-history"). Service only ever calls `raw.agent_location_history.insert_one` (`_promote()`). |
| 3 | A given agent's public IP changing during heartbeat writes exactly one new location-history row for that change, not one per heartbeat (GAUD-01) | ✓ VERIFIED | `backend/agent_location_history_service.py::record_location_change` implements the 4-branch de-noise state machine with a `DEBOUNCE_WINDOW = timedelta(minutes=10)`. Behavioral tests with an injected clock pass: `test_denoise_flip_flop_a_b_a_never_writes`, `test_denoise_promotes_after_window_elapses`, `test_denoise_two_genuine_changes_each_write_one_row`, `test_change_detection_no_row_when_unchanged` — all green (`pytest tests/test_agent_location_history.py -q` → 11 passed). |
| 4 | Retention for location-history is a deliberate decision routed through the existing retention module, not silently inherited from the 30-day convention (GAUD-01; privacy/legal gate) | ✓ VERIFIED | `backend/retention_service.py::cleanup_agent_location_history(retention_days=365)` compares a native `datetime` cutoff (`{"timestamp": {"$lt": cutoff}}`, no `.isoformat()`); wired into `run_cleanup()` (`location_history_deleted = await self.cleanup_agent_location_history(p.get("agent_location_history", 365))`) and surfaced in the returned report dict as `agent_location_history_deleted`. `backend/retention_endpoints.py` `_POLICY_DEFAULTS["agent_location_history"] = {"retention_days": 365, ...}`. Real-cutoff test `pytest tests/test_retention_agent_location_history.py -q` → 4 passed (366-day row deleted, 1-day row retained). |

**Score:** 4/4 roadmap success criteria verified. 0 behavior-unverified (all behavior-dependent truths — de-noise state machine, retention cutoff — were exercised by passing behavioral tests with injected/controllable clocks, not merely presence-checked).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agent_asn_service.py` | ASN + X4BNet VPN heuristic lookup, graceful degrade, no network | ✓ VERIFIED | 197 lines; `lookup()`, `_get_reader()`, `_load_vpn_ranges()`, `_is_known_vpn_range()` all present; `grep -nE 'requests\.\|httpx\|urllib\|aiohttp\|socket\.'` → no matches (no network calls) |
| `backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt` | Bundled X4BNet VPN CIDR snapshot | ✓ VERIFIED | 185KB, vendored with source-commit comment header; committed to git (`git log` shows it in commit `2343849`) |
| `backend/tests/test_agent_asn_service.py` | Graceful-degrade + VPN membership + private-IP-skip coverage | ✓ VERIFIED | 10 tests, all pass |
| `backend/agent_location_history_service.py` | Change-detection + de-noise + toggle + append-only write | ✓ VERIFIED | 204 lines; `record_location_change`, `get_track_agent_location` exported; insert_one only, no mutation |
| `backend/migrations/003_agent_location_history_indexes.py` | Compound (agent_id, tenantId, timestamp) + standalone timestamp index, no TTL | ✓ VERIFIED | Parses clean; `grep -nE 'expireAfterSeconds\|TTL'` → no matches; both indexes present |
| `backend/tests/test_agent_location_history.py` | Change-detection/de-noise/toggle/BSON-date coverage | ✓ VERIFIED | 11 tests, all pass |
| `backend/retention_service.py` (modified) | `cleanup_agent_location_history` + `run_cleanup` wiring | ✓ VERIFIED | Method present, wired, report key present |
| `backend/retention_endpoints.py` (modified) | `agent_location_history` in `_POLICY_DEFAULTS` | ✓ VERIFIED | Entry present, 365-day default |
| `backend/tests/test_retention_agent_location_history.py` | 365-day cutoff sweep coverage | ✓ VERIFIED | 4 tests, all pass |
| `backend/agent_location_history_endpoints.py` | Tenant-scoped GET-only timeline + read-time dwell + admin-gated toggle | ✓ VERIFIED | 129 lines; router exported; registered in `router_registry.py:172` |
| `backend/tests/test_agent_location_history_endpoints.py` | Tenant-scope, sort, dwell, admin PATCH, immutability coverage | ✓ VERIFIED | 9 tests, all pass |
| `backend/agent_heartbeat_endpoints.py` / `backend/agent_registry_endpoints.py` (modified) | Inline ASN + location-history hook | ✓ VERIFIED | Both import `agent_asn_service`, call `agent_asn_service.lookup`, `record_location_change`; both under 500 lines (480 / 386) |
| `backend/tests/test_agent_location_history_wiring.py` | Toggle-gating + geo.asn persistence + invocation coverage | ✓ VERIFIED | 5 tests, all pass |
| `utils/geo.ts` | Shared `flagEmoji`/`formatGeo` helpers | ✓ VERIFIED | Exported, used by `AgentList.tsx` and `AgentLocationHistory.tsx` |
| `services/apiService.ts` (modified) | `fetchAgentLocationHistory`, `getAgentLocationTracking`, `setAgentLocationTracking`, `LocationHistoryEntry` type | ✓ VERIFIED | All 4 symbols present |
| `components/AgentLocationHistory.tsx` | Read-only lazy-expand timeline panel | ✓ VERIFIED | 155 lines; no edit/delete/mutation affordance; amber (not red) heuristic badge; client-side dwell computation ignoring backend `dwell_seconds` |
| `components/AgentOverviewTab.tsx` (modified) | Panel mount point | ✓ VERIFIED | Mounted at line 215, after Tenant DetailRow, before Performance Metrics |
| `components/PrivacyDashboard.tsx` (modified) | Disclosure note + per-tenant toggle | ✓ VERIFIED | "Agent Location Tracking" section present; wired to `getAgentLocationTracking`/`setAgentLocationTracking`; retention window (365) disclosed in copy |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `agent_asn_service.py` | `geoip_service.py` | reuses `_is_public` | ✓ WIRED | `from geoip_service import _is_public` at line 24 |
| `agent_location_history_service.py` | `system_settings` collection | `get_track_agent_location` tenant→global→default | ✓ WIRED | Confirmed by passing toggle tests |
| `agent_location_history_endpoints.py` | `agent_location_history` collection | tenant-scoped find + belt-and-braces re-filter | ✓ WIRED | Query + re-filter both present (lines 55-66) |
| `router_registry.py` | `agent_location_history_endpoints.py` | `_load` registration | ✓ WIRED | `router_registry.py:172` |
| `agent_heartbeat_endpoints.py` / `agent_registry_endpoints.py` | `agent_asn_service.py` | `lookup(public_ip)` inline after `geoip_service.lookup` | ✓ WIRED | Confirmed via grep + passing wiring tests (toggle-off scope-boundary test confirms `geoip_service.lookup` still fires when toggle is OFF) |
| `agent_heartbeat_endpoints.py` / `agent_registry_endpoints.py` | `agent_location_history_service.py` | `record_location_change(existing_agent, ...)` gated on toggle | ✓ WIRED | Confirmed via grep + passing wiring tests |
| `components/AgentLocationHistory.tsx` | `services/apiService.ts` | `fetchAgentLocationHistory(agentId)` on first expand | ✓ WIRED | `handleToggle` calls `api.fetchAgentLocationHistory`, guarded by `fetched` flag (no refetch on re-expand) |
| `components/AgentOverviewTab.tsx` | `components/AgentLocationHistory.tsx` | mounted after Tenant DetailRow | ✓ WIRED | Confirmed at line 215 |
| `components/PrivacyDashboard.tsx` | `services/apiService.ts` | `getAgentLocationTracking` on mount + `setAgentLocationTracking` on toggle | ✓ WIRED | Both calls present |

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 5 phase-46 backend test modules | `pytest tests/test_agent_asn_service.py tests/test_agent_location_history.py tests/test_retention_agent_location_history.py tests/test_agent_location_history_endpoints.py tests/test_agent_location_history_wiring.py -q` | 39 passed | ✓ PASS |
| Full backend suite (regression check) | `pytest tests/ -q --ignore=tests/test_graphql.py --ignore=tests/test_ai_service_config.py --ignore=tests/test_network_endpoint.py --ignore=tests/test_sbom_api.py` | 1381 passed, 35 skipped, 6 failed | ✓ PASS — all 6 failures match the documented pre-existing baseline exactly (test_e2e_integration golden-path, test_rust_heartbeat_parity, test_agentic_ai tool_choice_any, test_support_admin_to_user x3 order-dependent). No new failures attributable to phase 46. |
| Frontend typecheck | `npx tsc --noEmit` | 0 errors in any phase-46 file (pre-existing unrelated errors only in `servers/src/*` MCP-server workspace, untouched by this phase) | ✓ PASS |
| Frontend build | `npm run build` | built in 4.07s, no errors | ✓ PASS |
| No network calls in ASN service | `grep -nE 'requests\.\|httpx\|urllib\|aiohttp\|socket\.' backend/agent_asn_service.py` | no matches | ✓ PASS |
| Append-only guarantee (service) | `grep -nE 'agent_location_history\.(update\|delete\|replace\|find_one_and)' backend/agent_location_history_service.py` | no matches | ✓ PASS |
| No mutation route on location-history resource | `grep -nE '@router\.(patch\|put\|delete)' backend/agent_location_history_endpoints.py` | only `/api/settings/agent-location-tracking` PATCH (not location-history) | ✓ PASS |
| No TTL index on agent_location_history | `grep -nE 'expireAfterSeconds\|TTL' backend/migrations/003_agent_location_history_indexes.py` | no matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|-------------|--------|----------|
| GAUD-01 | 46-01, 46-02, 46-03, 46-04, 46-05, 46-07 | Append-only `agent_location_history`, change-detected off already-fetched agent doc, cloned from `remediation_escalations` | ✓ SATISFIED | Service, endpoints, retention, and wiring all verified above; append-only + de-noise + retention all confirmed |
| GAUD-02 | 46-04, 46-06 | Per-agent location-history timeline view | ✓ SATISFIED | GET endpoint + `AgentLocationHistory.tsx` panel verified above; live visual render deferred to human verification |

No orphaned requirements — REQUIREMENTS.md maps only GAUD-01/GAUD-02 to Phase 46, and both are claimed by at least one plan's frontmatter. Both are also already marked `[x]` in REQUIREMENTS.md.

### Anti-Patterns Found

None. Scanned all 16 phase-modified/created files for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` and stub patterns — no matches.

**Housekeeping note (not a gap):** `backend/tests/test_agent_location_history_endpoints.py` has an uncommitted working-tree diff that *strengthens* an existing dwell assertion (adds `insert_one.assert_not_called()` / `update_one.assert_not_called()` checks in place of a weaker `"dwell_seconds" not in rows[0]` check). The test suite passes with this diff applied. This is not a regression — flagging only so it doesn't get lost if the working tree is reset.

### Human Verification Required

Two items were pre-identified as Manual-Only in the phase's own `46-VALIDATION.md` and could not be closed by static/automated verification:

1. **Location-history timeline visual render**
   **Test:** Open an agent's detail view (Overview tab) for an agent with recorded location changes and expand the Location History panel.
   **Expected:** Rows render with flag emoji, city/country, optional amber "likely VPN/hosting" badge, monospace public IP, UTC timestamp, and dwell time; panel is read-only with no mutation controls.
   **Why human:** Live visual rendering in a browser cannot be confirmed from source code alone — component logic, prop wiring, and API contract were all verified, but the rendered DOM/visual output was not observed in this verification pass.

2. **Real GeoLite2-ASN.mmdb enrichment**
   **Test:** Supply a real, licensed `GeoLite2-ASN.mmdb` via `GEOIP_ASN_DB_PATH` and trigger a heartbeat/registration for an agent with a real public IP.
   **Expected:** `geo.asn` populates with a real `{number, org}` object on the agent doc, in addition to the already-tested `vpn_heuristic` flag.
   **Why human:** Requires a licensed MaxMind database supplied out-of-band per the phase's own design (D-11); graceful degrade without it is unit-tested and confirmed, but enrichment against a real database was not exercised in this environment.

### Gaps Summary

No gaps found. All 4 roadmap success criteria are verified against the actual codebase (not merely SUMMARY.md claims): append-only integrity confirmed by grep + passing tests, one-row-per-confirmed-change confirmed by a deterministic-clock behavioral test suite (not just code presence), retention routed through the real cleanup-and-wire pattern (avoiding the `security_events`/`alerts` seed-only gap the plans explicitly called out), and the GAUD-02 timeline is built, wired, and mounted at the correct location. The full backend test suite shows no regressions beyond the pre-documented baseline failures. Frontend typecheck and build are clean. The only outstanding items are the two Manual-Only checks the phase's own validation plan flagged from the start — routing this verification to `human_needed` rather than `passed`, per the decision tree (human verification items present, even though zero automated gaps exist).

---

_Verified: 2026-07-29T14:10:00Z_
_Verifier: Claude (gsd-verifier)_
