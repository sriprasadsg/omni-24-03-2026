---
phase: 48-fleet-observability-uptime-rollups
verified: 2026-07-30T00:00:00Z
status: human_needed
score: 10/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - test: "Open an agent detail view and click the new 'Metrics' tab. Confirm CPU/memory/disk AreaCharts render with real data and switch the 1h/6h/24h/48h range selector; confirm both the charts and the uptime timeline/percent update to match the selected range."
    expected: "Three recharts AreaCharts (CPU, memory, disk) render with data points; the uptime timeline strip and uptime % update in sync with the charts on every range change; empty-data agents show the friendly empty-state message instead of a blank/broken chart."
    why_human: "Automated typecheck/build and unit tests confirm the components are wired to the right endpoints and typecheck cleanly, but actual chart rendering, visual layout, and live reactive behavior against real heartbeat/metrics data can only be confirmed by opening the running app (per the plan's own <human-check> step, deferred to end-of-phase)."

  - test: "As an admin holding manage:agents, confirm the 'Fleet Observability' sidebar entry appears and opens a page listing real offline agents and version-drifted agents. As a user without manage:agents, confirm the entry is hidden and the view is unreachable."
    expected: "manage:agents holders see the nav entry and a working page with live offline/drift data (or friendly empty states); users without the permission never see the entry and cannot navigate to it."
    why_human: "Code review confirms the permission string ('manage:agents') is wired identically to the Sidebar/App.tsx/types.ts pattern for the pre-existing geoSecurity page, and the build emits a separate lazy-loaded chunk, but confirming the gate actually hides/blocks the view for a live non-admin session requires logging in as both roles (per the plan's own <human-check> step, deferred to end-of-phase)."
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  status: human_needed
---

# Phase 48: Fleet Observability & Uptime Rollups Verification Report

**Phase Goal:** Give admins a fleet operational view — per-agent metrics/uptime history + an aggregate offline/version-drift view — reusing existing telemetry, not rebuilding it.
**Verified:** 2026-07-30
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/agents/{id}/uptime?hours=N` returns a tenant-isolated `uptime_percent` + bucketed `timeline` (FOBS-02 on-the-fly path) | VERIFIED | `backend/agent_uptime_endpoints.py:32-67` clones `agent_metrics_endpoints` tenant-gating verbatim (404 cross-tenant, `tenantId`/`tenant_id` filter added for non-super roles); reads `db.agents`/`db.agent_metrics` via the request-scoped wrapped `db` (no `db._db`). 9/9 tests pass in `test_agent_uptime_service.py`. |
| 2 | Uptime % = heartbeat-presence gap-detection at a fixed 30s cadence, clipped ≤100%, 0% (no crash) on an empty window | VERIFIED | `backend/agent_uptime_service.py:46-109` `compute_uptime()` — bucket-index-set construction bounds the ratio ≤1.0 by design; `expected_buckets==0` guard prevents div-by-zero. Unit tests cover 100%/50%/0%/clip-at-100%/timeline-shape (5 cases, all pass). |
| 3 | `hours` is clamped to 1..48 server-side before querying (D-02 ceiling, DoS mitigation) | VERIFIED | `backend/agent_uptime_endpoints.py:43` — `hours = max(1, min(hours, 48))`. Endpoint tests assert both the 48h ceiling and 1h floor clamp. |
| 4 | Daily rollup sweep (`agent_uptime_rollup_loop`) upserts one row per agent per day into `agent_uptime_rollups`, keyed on `{agent_id, date}`, via raw `db._db` tenant iteration, storing a native BSON Date `timestamp`, with no historical backfill | VERIFIED | `backend/app_background_tasks.py:226-324` — `_run_agent_uptime_rollup_once` iterates `db._db.tenants`/`db._db.agents` raw, reuses `compute_uptime(rows, 24)` (no duplicated math), upserts via `update_one(..., upsert=True)` with `timestamp: datetime.now(timezone.utc)` (never `.isoformat()`), docstring documents no-backfill. Registered in `app_startup.py:584,590`. 11/11 rollup tests pass. |
| 5 | `retention_service.run_cleanup()` deletes `agent_uptime_rollups` rows older than the configured retention (default 90d) by native-datetime `$lt` cutoff, and does not touch `agent_metrics` retention | VERIFIED | `backend/retention_service.py:53-65,79-87` — `cleanup_agent_uptime_rollups` + wired into `run_cleanup`'s report dict as `agent_uptime_rollups_deleted`. Tests confirm 90-day-old row deleted / 1-day-old retained, and that `run_cleanup` doesn't add `agent_metrics` retention. |
| 6 | `GET /api/fleet/observability` returns `offline_agents` + `version_drift` + `latest_version`, tenant-scoped for non-super-admins, full fleet for super-admins (FOBS-03 backend) | VERIFIED | `backend/agent_fleet_observability_endpoints.py:44-79` — `is_super_admin()` gate adds `tenantId` filter only for non-super roles; reads via wrapped `db.agents` (never `db._db`). Registered in `router_registry.py:281`. 5/5 tests pass, covering super-admin fleet-wide vs tenant-admin scoping. |
| 7 | Version-drift reuses `agent_auto_update_service._parse_ver`/`_LATEST_AGENT_VERSION` (no new parser); malformed/missing version excluded from drift without raising | VERIFIED | `backend/agent_fleet_observability_endpoints.py:23,63-71` imports and reuses `_parse_ver`/`_LATEST_AGENT_VERSION` unchanged; `parsed is not None and latest_parsed is not None and parsed < latest_parsed` guard fails closed. Test `test_malformed_or_missing_version_excluded_without_crash` passes. |
| 8 | Offline set sourced from `agents.status == "Offline"` (the field `monitor_agent_status()` maintains) — not a new heuristic | VERIFIED | `backend/agent_fleet_observability_endpoints.py:65` filters on the existing `status` field; `app_background_tasks.py:60,66,75` confirms `monitor_agent_status()` is the sole writer of `"Offline"`. Test `test_offline_set_read_from_status_field_not_new_heuristic` passes. |
| 9 | Agent detail view has a Metrics tab wired to render CPU/mem/disk history as recharts AreaCharts + a per-agent uptime timeline/%, both driven by a shared ≤48h (1h/6h/24h/48h) range selector, calling the correct endpoints (FOBS-01/02 UI) | ? UNCERTAIN (wired, not visually confirmed) | `components/AgentMetricsTab.tsx` renders 3 `<AreaChart>` (CPU/mem/disk) from `fetchAgentMetricsHistory(agentId, hours)`, embeds `<AgentUptimeTimeline agentId hours />` sharing the same `hours` state; `components/AgentUptimeTimeline.tsx` calls `fetchAgentUptime(agentId, hours)` and renders `uptime_percent` + bucket strip. `npx tsc --noEmit` and `npm run build` both clean. Actual chart rendering + live range-switch reactivity requires a human to open the app (see Human Verification). |
| 10 | `AgentDetailModal.tsx` gains only its per-tab footprint (button + one conditional render), no chart/timeline JSX inlined | VERIFIED | `components/AgentDetailModal.tsx:584-593` (button) and `:649-650` (`activeTab === 'metrics' ? <AgentMetricsTab agent={agent} /> : ...`) — matches the footprint of every sibling tab; no chart/timeline markup added to this file. |
| 11 | New admin-gated "Fleet Observability" nav page, registered across `types.ts`/`App.tsx`/`Sidebar.tsx`, gated by `manage:agents`, renders `offline_agents`/`version_drift` from the aggregate endpoint with no client-side recomputation (FOBS-03 UI) | ? UNCERTAIN (wired, not live-session confirmed) | `types.ts:201` (`'fleetObservability'` in `AppView`), `App.tsx:166` (lazy import), `:369` (`fleetObservability: 'manage:agents'`), `:1915` (switch case), `components/Sidebar.tsx:417` (`permission: 'manage:agents'`). `components/FleetObservabilityDashboard.tsx` renders `data.offline_agents`/`data.version_drift` verbatim from `fetchFleetObservability()` — no client-side offline/version logic. Build emits a separate `FleetObservabilityDashboard-*.js` chunk (lazy-loaded, confirmed via `npm run build`). Live reachability for a `manage:agents` holder and hiddenness for a non-holder requires a human session test (see Human Verification). |
| 12 | Requirements coverage: FOBS-01, FOBS-02, FOBS-03 are each mapped to a plan in this phase, and REQUIREMENTS.md shows no orphaned Phase-48 requirement IDs | VERIFIED | `REQUIREMENTS.md:25-27,61-63` lists FOBS-01/02/03 all `[x]` and mapped to Phase 48; plan frontmatter `requirements:` fields across 48-01..48-05 cover `[FOBS-02]` (48-01, 48-02), `[FOBS-03]` (48-03, 48-05), and `[FOBS-01, FOBS-02]` (48-04) — all 3 IDs accounted for, no orphans. |

**Score:** 10/12 truths verified (2 present + wired, visual/live-session confirmation pending human check)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agent_uptime_service.py` | `compute_uptime` gap-detection engine | VERIFIED | 138 lines, substantive, exports `compute_uptime`; imported by both the endpoint and the rollup sweep. |
| `backend/agent_uptime_endpoints.py` | `GET /{agent_id}/uptime` endpoint | VERIFIED | 67 lines; registered in `router_registry.py:280`. |
| `backend/tests/test_agent_uptime_service.py` | Bucketing + endpoint unit coverage | VERIFIED | 9 tests, all pass. |
| `backend/app_background_tasks.py` (edit) | `agent_uptime_rollup_loop` daily sweep | VERIFIED | Function + factored `_run_agent_uptime_rollup_once` present, registered in `app_startup.py`. |
| `backend/retention_service.py` (edit) | `cleanup_agent_uptime_rollups` + `run_cleanup` wiring | VERIFIED | Method present, wired into report dict. |
| `backend/tests/test_agent_uptime_rollup_loop.py` | Sweep + retention hermetic coverage | VERIFIED | 11 tests, all pass. |
| `backend/agent_fleet_observability_endpoints.py` | `GET /api/fleet/observability` aggregate | VERIFIED | 79 lines; registered in `router_registry.py:281`. |
| `backend/tests/test_agent_fleet_observability.py` | Offline/drift/tenant-scope coverage | VERIFIED | 5 tests, all pass. |
| `components/AgentMetricsTab.tsx` | Agent-scoped metrics + uptime tab | VERIFIED (wired) | 181 lines, 3 AreaCharts + range selector + embedded uptime timeline; TS-clean, builds. |
| `components/AgentUptimeTimeline.tsx` | Uptime timeline + % sub-component | VERIFIED (wired) | 83 lines, renders % + bucket strip; TS-clean, builds. |
| `services/apiService.ts` (edit) | `fetchAgentMetricsHistory` + `fetchAgentUptime` + `fetchFleetObservability` | VERIFIED | All three functions present with correctly-typed request/response shapes (lines ~1618, ~1648, ~5033). |
| `components/FleetObservabilityDashboard.tsx` | Admin-gated fleet page | VERIFIED (wired) | 119 lines, pure renderer over the endpoint, no client-side compute; builds as its own lazy chunk. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `agent_uptime_endpoints.py` | `agent_uptime_service.py` | `compute_uptime(rows, hours)` | WIRED | `agent_uptime_endpoints.py:66` |
| `agent_uptime_service.py` | `agent_metrics` collection | reads `timestamp` over the window | WIRED | Endpoint queries `db.agent_metrics`, never `agent_metrics_history` (grepped, absent). |
| `app_startup.py` | `app_background_tasks.py` | `asyncio.create_task(_safe_bg_task(agent_uptime_rollup_loop(), ...))` | WIRED | `app_startup.py:590` |
| `app_background_tasks.py` | `agent_uptime_service.py` | reuses `compute_uptime` for daily % | WIRED | `app_background_tasks.py:241,273` |
| `retention_service.py run_cleanup` | `cleanup_agent_uptime_rollups` | count reported | WIRED | `retention_service.py:79-87` |
| `agent_fleet_observability_endpoints.py` | `agent_auto_update_service.py` | imports `_parse_ver`/`_LATEST_AGENT_VERSION` | WIRED | `agent_fleet_observability_endpoints.py:23` |
| `agent_fleet_observability_endpoints.py` | `agents` collection | wrapped `db.agents` (never `db._db`) | WIRED | `agent_fleet_observability_endpoints.py:55,61` — confirmed no `db._db` reference in this file. |
| `AgentMetricsTab.tsx` | `apiService.ts` | `fetchAgentMetricsHistory`/`fetchAgentUptime` | WIRED | `AgentMetricsTab.tsx:5,38`; `AgentUptimeTimeline.tsx:2,23` |
| `AgentDetailModal.tsx` | `AgentMetricsTab.tsx` | conditional render for `metrics` tab | WIRED | `AgentDetailModal.tsx:650` |
| `FleetObservabilityDashboard.tsx` | `apiService.ts` | `fetchFleetObservability()` | WIRED | `FleetObservabilityDashboard.tsx:2,21` |
| `App.tsx` | `FleetObservabilityDashboard.tsx` | lazy import + permission map + switch case | WIRED | `App.tsx:166,369,1915` |
| `Sidebar.tsx` nav entry | `manage:agents` permission | gate | WIRED | `Sidebar.tsx:417` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Uptime/rollup/fleet unit tests pass (single named-module run, not full suite) | `backend/venv/bin/python -m pytest tests/test_agent_uptime_service.py tests/test_agent_uptime_rollup_loop.py tests/test_agent_fleet_observability.py -q` | 25 passed | PASS |
| New/edited backend modules import cleanly | `python -c "import agent_uptime_endpoints, agent_fleet_observability_endpoints, router_registry, app_background_tasks, app_startup"` | exit 0 | PASS |
| Frontend typecheck clean (project files only, excluding pre-existing vendored `servers/` errors) | `npx tsc --noEmit` | no output (clean) | PASS |
| Frontend build succeeds, Fleet page code-splits | `npm run build` | `✓ built in 4.17s`; `FleetObservabilityDashboard-DB81CzWa.js` chunk emitted | PASS |
| Full backend suite shows no new regressions vs documented pre-existing failures | `python -m pytest -q --continue-on-collection-errors` | 1451 passed / 34 skipped / 8 failed / 4 errors — all 8 failures + 4 errors match the documented pre-existing set exactly (webhook jira/zoho, agentic tool_choice, e2e golden-path, rust_heartbeat_parity, support_admin_to_user ×3, 4 collection errors) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|-------------|--------|----------|
| FOBS-01 | 48-04 | CPU/mem/disk history charts via recharts off metrics/history endpoint | SATISFIED | `AgentMetricsTab.tsx` renders 3 AreaCharts from `fetchAgentMetricsHistory`; wiring + build verified; visual render pending human check. |
| FOBS-02 | 48-01, 48-02, 48-04 | Per-agent heartbeat/uptime timeline + selectable-range uptime % | SATISFIED | Backend on-the-fly path (48-01) + rollup groundwork (48-02) + UI (48-04) all verified; UI visual/reactive confirmation pending human check. |
| FOBS-03 | 48-03, 48-05 | Fleet-level offline + version-drift view | SATISFIED | Backend aggregate (48-03) + admin-gated nav page (48-05) verified; live nav reachability/permission-gating pending human check. |

No orphaned requirements found — REQUIREMENTS.md maps exactly FOBS-01/02/03 to Phase 48, and all three appear in at least one plan's `requirements:` frontmatter.

### Anti-Patterns Found

None. Scanned all phase-modified files (`agent_uptime_service.py`, `agent_uptime_endpoints.py`, `agent_fleet_observability_endpoints.py`, `app_background_tasks.py`, `retention_service.py`, `AgentMetricsTab.tsx`, `AgentUptimeTimeline.tsx`, `FleetObservabilityDashboard.tsx`, `AgentDetailModal.tsx`, `apiService.ts`) for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/stub-language — no matches. No stub-shaped empty returns (`return null`/`return {}`/`return []`) found in the new production code paths; empty states (`data.length === 0`) are legitimate loading/no-data UI states, not stubs.

### Human Verification Required

### 1. Agent Detail Metrics Tab — Live Rendering + Range Reactivity

**Test:** Open an agent detail view and click the new "Metrics" tab. Confirm CPU/memory/disk AreaCharts render with real data, and switch the 1h/6h/24h/48h range selector to confirm both the charts and the uptime timeline/percent update together.
**Expected:** Three AreaCharts render with real data points; the uptime timeline strip and uptime % update in sync with the charts on every range change; an agent with no metrics shows the friendly empty-state message instead of a blank/broken chart.
**Why human:** Automated typecheck/build and unit tests confirm correct wiring to the right endpoints, but actual chart rendering, visual layout, and live reactive behavior against real heartbeat/metrics data require opening the running app — this is the plan's own deferred `<human-check>` step (48-04 Task 3).

### 2. Fleet Observability Nav Page — Reachability + Permission Gate

**Test:** As an admin holding `manage:agents`, confirm the "Fleet Observability" sidebar entry appears and opens a page listing real offline agents and version-drifted agents. As a user without `manage:agents`, confirm the entry is hidden and the view is unreachable.
**Expected:** `manage:agents` holders see the nav entry and a working page with live offline/drift data (or friendly empty states); users without the permission never see the entry and cannot navigate to the view.
**Why human:** Code review confirms the permission string is wired identically to the pre-existing `geoSecurity` page pattern, and the build emits a separate lazy-loaded chunk, but confirming the gate actually hides/blocks the view for a live non-admin session requires logging in as both roles — this is the plan's own deferred `<human-check>` step (48-05 Task 2).

### Gaps Summary

No gaps found. All 12 must-have truths derived from the ROADMAP success criteria and the 5 plans' `must_haves` frontmatter are either fully VERIFIED by code inspection, passing unit tests (25/25 phase-specific tests), clean typecheck/build, and a full-suite regression check (no new failures beyond the documented pre-existing set), or are wired-and-present pending only a human visual/live-session confirmation that the plans themselves deliberately deferred to end-of-phase (`human_verify_mode`). Both deferred items were explicitly flagged by the executing plans' own `<human-check>` steps, not discovered as gaps by this verification — the underlying code, tests, and wiring for both are sound.

---

_Verified: 2026-07-30_
_Verifier: Claude (gsd-verifier)_
