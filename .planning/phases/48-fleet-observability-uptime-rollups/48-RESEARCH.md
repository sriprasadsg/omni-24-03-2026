# Phase 48: Fleet Observability & Uptime Rollups - Research

**Researched:** 2026-07-29
**Domain:** FastAPI/Motor(MongoDB) backend + React/TypeScript frontend — telemetry reuse, background sweeps, admin dashboards
**Confidence:** HIGH (all core findings verified directly against the running codebase; no external library research was needed — this is a reuse-first phase)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Uptime Computation (FOBS-02)**
- **D-01:** Hybrid model. Implement BOTH: (a) an on-the-fly gap-detection path that computes the fine uptime timeline + uptime % by bucketing existing heartbeat/metric timestamps over the requested window (gap = missed heartbeats vs the ~30s cadence); AND (b) a background daily uptime-rollup sweep writing a per-agent daily uptime % into a rollup collection (e.g. `agent_uptime_rollups`), so aggregate/long-range uptime is cheap and a future longer-range UI is a switch-on, not a rebuild. Uptime definition = heartbeat-presence ratio (received/expected), not status-transition duration.

**Time Range (FOBS-01/02)**
- **D-02:** UI exposes ≤48h presets only this phase (e.g. 1h / 6h / 24h / 48h), served by the existing fine `GET /agents/{id}/metrics/history?hours=N` endpoint (2880-point / ~48h cap). Longer ranges (7d/30d) are deferred — the D-01 rollup sweep lays the groundwork, but the v3.3 UI does not surface them. No history-collection downsampling or endpoint cap change in this phase.
- Interaction note (D-01 × D-02): the rollup sweep is built but only ≤48h ranges are user-visible now. The on-the-fly path backs the exposed presets; the rollup path is scaffolding for the deferred longer-range view. Planner: keep the rollup sweep minimal (write daily %), don't build longer-range UI.

**Fleet View + Version-Drift (FOBS-03)**
- **D-03:** New admin-gated "Fleet Observability" nav page, cloning the Phase 47 Security-panel pattern (dedicated view, admin-gated, registered in App.tsx + Sidebar.tsx). Backed by a new aggregate endpoint returning: offline agents (from the existing `status == "Offline"` set maintained by `monitor_agent_status()`) + version-drift list. Version-drift = each agent's reported version compared to the single global `_LATEST_AGENT_VERSION` (currently 2.1.4). Single-version compare — per-OS latest tracking is deferred (only one binary today).

**FOBS-01 Charts (reuse + mount)**
- **D-04:** Reuse `MetricsChartsTab.tsx` as-is (already renders CPU/mem/disk AreaCharts via recharts, consuming the metrics-history endpoint). Scope = mount it into the agent detail view (a new tab in `AgentDetailModal.tsx`, or in `AgentOverviewTab.tsx`) — it is currently only mounted in `AssetDetail.tsx` — and add the shared ≤48h range selector (D-02). No chart rework beyond the mount + range prop.

  > **Research correction:** `MetricsChartsTab.tsx` does not consume the metrics-history endpoint — it consumes `GET /api/assets/{assetId}/metrics?range=` via `assetId`, not `GET /agents/{id}/metrics/history?hours=N` via `agent_id`. See Summary/Pitfall 1. "As-is" reuse is still the right call; the endpoint it actually hits just isn't the one D-04's parenthetical names.

### Claude's Discretion
- Exact rollup sweep cadence + retention for `agent_uptime_rollups` (suggest daily sweep, retention routed through the existing retention module like Phase 46's location-history — planner/research decide). **Research recommendation:** daily sweep (matches every other daily background loop in this codebase); retention wired into `retention_service.py` exactly like the Phase 46 `agent_location_history` precedent (see Pitfall 4).
- Whether the fleet aggregate is one new endpoint or extends an existing fleet/dashboard endpoint. **Research recommendation:** one new endpoint — no existing endpoint does offline+version-drift aggregation, and `GET /api/agents` (the closest existing surface) is a paginated list, not an aggregate/counts shape.
- Chart range-selector component (new shared control vs inline preset buttons). **Research recommendation:** edit `MetricsChartsTab.tsx`'s own inline preset-button array (`1h/24h/7d/30d` → `1h/6h/24h/48h`) rather than building a new shared control — smallest diff, and the new uptime timeline can reuse the same button styling inline rather than sharing a component (no other consumer of a range selector exists yet to justify extraction).
- Exact uptime bucketing granularity for the fine timeline. **Research recommendation:** 30s buckets (matches the assumed heartbeat cadence used for gap detection — see Pitfall 3), rendered/aggregated to a coarser display granularity (e.g. 5-15 min blocks) for windows near 48h to avoid an unreadably dense timeline.

### Deferred Ideas (OUT OF SCOPE)
- Longer ranges (7d/30d) in the UI — groundwork (rollup sweep) built this phase, UI surfacing deferred.
- Native MongoDB time-series collections — migrate uptime/metrics history if retention outgrows the current cap (REQUIREMENTS.md).
- Per-OS / per-platform latest-version tracking — single global version compare for now.
- Rebuilding offline detection or version tracking — explicitly out of scope; reuse `monitor_agent_status()` + existing version flow.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOBS-01 | An admin can view an agent's CPU / memory / disk history as charts (consuming the existing metrics endpoint via `recharts`) | Mount `MetricsChartsTab.tsx` (edited range presets) as a new `AgentMetricsTab.tsx`, 8th tab in `AgentDetailModal.tsx`; data source is `asset_endpoints.py`'s `get_asset_metrics` (the active, non-shadowed handler) via the same `assetId` derivation already used for the compliance tab — see Pattern 5, Code Examples, Pitfalls 1-2 |
| FOBS-02 | An admin can see a per-agent heartbeat/uptime timeline and an uptime % over a selectable range | New `agent_uptime_service.py` (on-the-fly gap detection over `agent_metrics` rows, 30s bucket assumption) + new `agent_uptime_rollup_loop()` background sweep (daily, writes `agent_uptime_rollups`, raw-db tenant iteration) — see Pattern 1, Pattern 3, Pitfalls 3-4, Code Examples |
| FOBS-03 | An admin can see a fleet-level view of offline agents and agent version-drift | New aggregate endpoint reading `agents.status=="Offline"` + comparing `agents.version` via `agent_auto_update_service._parse_ver()` against `_LATEST_AGENT_VERSION`; new `FleetObservabilityDashboard.tsx` admin-gated nav page cloning `SecuritySettingsDashboard.tsx`'s 4-file registration — see Pattern 4, Pitfall 5, Code Examples |
</phase_requirements>

## Summary

Phase 48 is almost entirely a **wiring and correction phase**, not a build-from-scratch phase. Direct inspection of the code the phase brief cites as reuse targets turned up two load-bearing corrections to the phase brief's own assumptions:

1. **`MetricsChartsTab.tsx` does NOT consume `GET /agents/{id}/metrics/history`.** It takes an `assetId` prop and calls `fetchAssetMetrics(assetId, range)` → `GET /api/assets/{assetId}/metrics?range=`. That route is defined **twice** in this codebase (`asset_endpoints.py` and `asset_metrics_endpoints.py`, identical path/prefix) — `asset_endpoints.py` is registered first in `router_registry.py` and therefore is the one that actually runs; `asset_metrics_endpoints.py`'s handler is silently dead code. FOBS-01 planning must target `asset_endpoints.py`'s handler and `MetricsChartsTab`'s real `assetId` contract, not the agent-scoped endpoint named in the phase brief.
2. **`MetricsChartsTab.tsx`'s time-range buttons are internal, uncontrolled state** (`'1h'|'24h'|'7d'|'30d'`, no prop to override). D-04's "add the shared ≤48h range selector" therefore requires a small, targeted edit to this component's own button array (swap `7d`/`30d` for `6h`/`48h`) — plus a matching edit to `asset_endpoints.py`'s `range_hours` lookup dict, which currently has no `"6h"`/`"48h"` keys and would silently fall back to 24h of data for those selections otherwise. This is not "as-is" reuse in the strictest sense, but it is the minimum viable edit; everything else in the component (fetch logic, chart rendering) stays untouched.

For FOBS-02, the codebase has **no dedicated per-heartbeat-timestamp collection** — `agents.lastSeen` only stores the latest heartbeat time. The best available proxy for heartbeat-presence is the `agent_metrics` collection, which the heartbeat handler (`agent_heartbeat_endpoints.py`) writes on **every** heartbeat that carries `meta.current_cpu`/`current_memory` — true for both the Rust and Python agents. `agent_metrics` has no retention/cleanup at all today (confirmed against `retention_service.py`), so it is safe to read across a 48h window without gaps from an unrelated sweep, but it will need its own retention policy going forward (Claude's Discretion item). The similarly-named `agent_metrics_history` collection is a decoy — it is capped at 100 rows per agent (oldest deleted every heartbeat), giving only ~25–50 minutes of history at typical cadence, and must NOT be used for the uptime timeline.

For FOBS-03, no existing endpoint aggregates offline + version-drift; `GET /api/agents` (paginated, `status`/`tenant_id` filters) is the closest existing surface but doesn't do version comparison. A new, small aggregate endpoint is the right call, consistent with D-03's lock.

The background-sweep pattern for the daily rollup is fully established by four existing loops in `app_background_tasks.py` (especially `snapshot_compliance_scores_loop`), and the fleet-wide-sweep tenant-isolation bug class STATE.md warns about is directly visible in `database.py`: any collection not in the hardcoded `TenantIsolatedDatabase` exemption list gets an automatic `tenantId` filter injected — a cross-tenant background sweep must read tenants via `db._db.tenants.find(...)` and either iterate per-tenant with `set_tenant_id()` or write via `db._db.<collection>` directly, exactly as the existing loops already do.

**Primary recommendation:** Build FOBS-01 as a new `AgentMetricsTab.tsx` (own file, mounted as an 8th tab in `AgentDetailModal.tsx`, following that file's own established one-tab-per-component pattern) wrapping the edited `MetricsChartsTab` with `assetId` derived exactly like the existing compliance-tab derivation (`asset?.id || agent?.assetId || asset-${agent.hostname}`). Build FOBS-02 as a new `agent_uptime_service.py` (on-the-fly gap detection reading `agent_metrics.timestamp` bucketed at a fixed, code-level 30s expected cadence — matching `monitor_agent_status()`'s own existing 30s/5min assumption, since no per-agent interval is ever persisted server-side) plus a new `agent_uptime_rollup_loop()` background task in `app_background_tasks.py` writing daily `%` rows to `agent_uptime_rollups` (native BSON Date timestamps, cloning `agent_location_history`'s append-only/raw-db pattern) registered in `app_startup.py` alongside the other four loops. Build FOBS-03 as one new admin-gated `FleetObservabilityDashboard.tsx` (clone of `SecuritySettingsDashboard.tsx`'s registration in `types.ts`/`App.tsx`/`Sidebar.tsx`) backed by one new aggregate endpoint comparing `agents.version` against `_LATEST_AGENT_VERSION`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CPU/mem/disk history charts (FOBS-01) | Frontend (React tab component) | API/Backend (existing asset-metrics endpoint) | Rendering is pure client-side recharts; backend already serves the time-series, no new backend logic needed beyond a range-key fix |
| On-the-fly uptime gap detection (FOBS-02) | API/Backend | Database (Motor query over `agent_metrics`) | Computed per-request from existing telemetry rows; no new storage, just a new read-path service module |
| Daily uptime rollup sweep (FOBS-02) | API/Backend (background task) | Database (new `agent_uptime_rollups` collection) | Mirrors `snapshot_compliance_scores_loop` — a startup-registered `asyncio.create_task` loop, writes via raw `db._db` |
| Fleet offline + version-drift aggregate (FOBS-03) | API/Backend (new endpoint) | Database (reads `agents` collection, no new storage) | Read-only aggregation over existing `agents.status`/`agents.version`; owned by backend, rendered by a new admin page |
| Fleet Observability nav page (FOBS-03) | Frontend (new admin-gated dashboard) | — | Clones the Phase 47 `SecuritySettingsDashboard` registration pattern exactly |
| Retention of new `agent_uptime_rollups` data | Database / API/Backend (`retention_service.py`) | — | Must be added to `RetentionService.run_cleanup()`, matching the Phase 46 `agent_location_history` precedent |

## Standard Stack

This phase introduces **no new external dependencies**. Everything needed already exists in the installed stack:

### Core (existing, reused)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| recharts | (already installed; see `package.json`) | AreaChart/LineChart rendering in `MetricsChartsTab.tsx` | Already the project's sole charting library across every dashboard |
| FastAPI + Motor (async MongoDB) | (already installed) | New uptime/aggregate endpoints | Matches every other endpoint file in `backend/` |
| pytest (no pytest-asyncio) | (already installed) | New backend unit tests | Confirmed: no `pytest-asyncio` in this env; existing tests use `asyncio.run()` inside sync test functions (see `test_agent_heartbeat_geo_security.py`) |

**Version verification:** Not applicable — no new packages are being added. `npm view`/`pip index versions` checks are skipped per the Package Legitimacy Audit below.

**Installation:** None required.

## Package Legitimacy Audit

**Not applicable.** This phase adds zero new external packages (backend or frontend). All work is new first-party modules/endpoints built from already-installed dependencies (`recharts`, FastAPI, Motor). No `npm install` / `pip install` calls are part of this phase's plan.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────┐
                         │           Rust / Python Agent            │
                         │  heartbeat every 15–30s (cadence varies   │
                         │  by agent build; never persisted server- │
                         │  side)  →  meta.current_cpu/current_memory│
                         └───────────────────┬───────────────────────┘
                                             │ POST /api/agents/{id}/heartbeat
                                             ▼
                         ┌─────────────────────────────────────────┐
                         │      agent_heartbeat_endpoints.py         │
                         │  • updates agents.status/lastSeen/version │
                         │  • INSERT agent_metrics (per-heartbeat)   │
                         │  • INSERT asset_metrics (per-heartbeat)   │
                         │  • INSERT agent_metrics_history (capped   │
                         │    100 rows/agent — NOT for FOBS-02)      │
                         └───────────────────┬───────────────────────┘
                                             │
              ┌──────────────────────────────┼───────────────────────────────┐
              ▼                              ▼                               ▼
  ┌───────────────────────┐   ┌───────────────────────────┐   ┌──────────────────────────┐
  │ GET /assets/{id}/metrics│   │  NEW: agent_uptime_service │   │ monitor_agent_status()   │
  │ (asset_endpoints.py —   │   │  on-the-fly gap detection  │   │ (existing) — flips       │
  │  the ACTIVE handler;    │   │  reads agent_metrics for   │   │ agents.status=Offline    │
  │  asset_metrics_endpoints│   │  the requested agent_id,   │   │ after 5 min no heartbeat │
  │  .py's copy is dead code│   │  buckets vs ~30s expected  │   └───────────┬──────────────┘
  │  — registered 2nd)      │   │  cadence → fine timeline + │               │
  └───────────┬─────────────┘   │  uptime %                  │               │
              │                 └──────────────┬─────────────┘               │
              │                                 │                            │
              ▼                                 ▼                            ▼
  ┌───────────────────────┐   ┌───────────────────────────┐   ┌──────────────────────────┐
  │  AgentMetricsTab.tsx    │   │  Uptime timeline UI (new   │   │  NEW: agent_uptime_rollup │
  │  (NEW — wraps           │   │  component, mounted next   │   │  _loop() — daily sweep,   │
  │  MetricsChartsTab with  │   │  to AgentMetricsTab)        │   │  registered in            │
  │  edited 1h/6h/24h/48h    │   └────────────────────────────┘   │  app_startup.py, writes   │
  │  presets), mounted as   │                                     │  agent_uptime_rollups     │
  │  8th tab in             │                                     │  (per-tenant iteration    │
  │  AgentDetailModal.tsx   │                                     │  via raw db._db.tenants)  │
  └─────────────────────────┘                                     └──────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  NEW: Fleet Observability aggregate endpoint                                  │
  │  reads agents.status=="Offline" (from monitor_agent_status's existing set)    │
  │  + compares agents.version vs agent_auto_update_service._LATEST_AGENT_VERSION │
  │  → NEW FleetObservabilityDashboard.tsx (admin-gated nav page, clones          │
  │    SecuritySettingsDashboard.tsx's App.tsx/Sidebar.tsx/types.ts registration) │
  └─────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── agent_uptime_service.py       # NEW — on-the-fly gap-detection + bucketing (FOBS-02 read path)
├── agent_uptime_endpoints.py     # NEW — GET /api/agents/{id}/uptime?hours=N (fine timeline + %)
├── agent_fleet_observability_endpoints.py  # NEW — GET aggregate: offline set + version-drift
├── app_background_tasks.py       # EDIT — add agent_uptime_rollup_loop()
├── app_startup.py                # EDIT — 2-line import + asyncio.create_task registration
├── retention_service.py          # EDIT — add cleanup_agent_uptime_rollups(), wire into run_cleanup()
├── asset_endpoints.py            # EDIT — add "6h":6 / "48h":48 to range_hours dict (small, targeted)
components/
├── AgentMetricsTab.tsx           # NEW — wraps MetricsChartsTab (assetId) + uptime timeline, 8th tab
├── MetricsChartsTab.tsx          # EDIT — swap ['1h','24h','7d','30d'] for ['1h','6h','24h','48h']
├── AgentDetailModal.tsx          # EDIT — +1 tab button, +1 conditional render line (~4 lines net)
├── FleetObservabilityDashboard.tsx  # NEW — clone of SecuritySettingsDashboard.tsx's shape
services/
├── apiService.ts                 # EDIT — update fetchAssetMetrics range union type; add fetchAgentUptime / fetchFleetObservability
App.tsx                            # EDIT — lazy import + permission map entry + switch case (clone geoSecurity)
components/Sidebar.tsx             # EDIT — +1 nav entry (clone the 'geoSecurity' row)
types.ts                           # EDIT — +1 AppView union member
```

### Pattern 1: Fleet-wide background sweep with raw-db tenant iteration
**What:** Any background task that must touch data across ALL tenants (not just one request's ambient tenant) bypasses `TenantIsolatedDatabase`'s automatic `tenantId` injection by reading tenants through `db._db.tenants.find(...)` directly, then either (a) calling `set_tenant_id(tid)` before each tenant's wrapped-collection calls, or (b) writing directly through `db._db.<collection>` with an explicit `tenantId` field in the document.
**When to use:** The new `agent_uptime_rollup_loop()` — it must compute uptime for every agent across every tenant once a day.
**Example:**
```python
# Source: backend/app_background_tasks.py:129-224 (snapshot_compliance_scores_loop — existing, verified)
async def snapshot_compliance_scores_loop():
    while True:
        await asyncio.sleep(86400)  # run once per day
        _tenant_ctx_token = None
        try:
            db = get_database()
            _tenant_ctx_token = set_tenant_id("platform-admin")
            tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
            for tenant in tenants:
                tid = tenant.get("id")
                if not tid:
                    continue
                try:
                    set_tenant_id(tid)
                    # ... wrapped db.<collection> calls here are now scoped to tid ...
                    await db._db.compliance_score_history.update_one(
                        {"tenant_id": tid, "date": date_key}, {"$set": snapshot}, upsert=True
                    )
                except Exception as _te:
                    logger.error("... error for tenant %s: %s", tid, _te)
        finally:
            if _tenant_ctx_token is not None:
                reset_tenant_id(_tenant_ctx_token)
```
The new `agent_uptime_rollup_loop()` should follow this shape exactly, iterating tenants, then agents within each tenant, computing the daily uptime % from `agent_metrics` rows, and writing to `db._db.agent_uptime_rollups` with an upsert keyed on `{agent_id, date}` (same upsert-by-date-key idiom as `compliance_score_history`).

### Pattern 2: Background task registration (startup wiring)
**What:** Every background loop is imported inline inside `app_startup.py`'s lifespan function and scheduled via `asyncio.create_task(_safe_bg_task(<coro>(), "<name>"))`. `_safe_bg_task` (line 460) logs exceptions instead of crashing the process.
**When to use:** Registering the new `agent_uptime_rollup_loop()`.
**Example:**
```python
# Source: backend/app_startup.py:581-588 (existing, verified)
from app_background_tasks import (
    monitor_agent_status, refresh_mitre_heatmap_loop,
    compliance_evidence_sweep_loop, snapshot_compliance_scores_loop,
)
asyncio.create_task(_safe_bg_task(monitor_agent_status(), "agent_status_monitor"))
asyncio.create_task(_safe_bg_task(refresh_mitre_heatmap_loop(), "mitre_heatmap_refresh"))
# NEW line to add here:
# asyncio.create_task(_safe_bg_task(agent_uptime_rollup_loop(), "agent_uptime_rollup"))
```

### Pattern 3: Native BSON Date timestamps for append-only/retention collections
**What:** New collections that need date-range retention sweeps (`$lt` comparisons) must store `timestamp` as a real `datetime` object, never `.isoformat()`'d — this is the exact opposite convention from `agent_metrics`/`asset_metrics` (which store ISO strings) and is called out explicitly in the Phase 46 code as a hard requirement.
**When to use:** Every row written by `agent_uptime_rollup_loop()` into `agent_uptime_rollups`.
**Example:**
```python
# Source: backend/agent_location_history_service.py (module docstring + retention_service.py:37-51, existing, verified)
# retention_service.py's cleanup_agent_location_history compares timestamp as a datetime object
# directly (no .isoformat()), because the write path never stringifies it:
await raw.agent_location_history.insert_one({..., "timestamp": datetime.now(timezone.utc), ...})
```

### Pattern 4: Admin-gated nav page registration (4-file clone)
**What:** A new dashboard-only view requires edits to exactly 4 files, all following the same shape as the Phase 47 Security Settings panel.
**When to use:** Registering `FleetObservabilityDashboard.tsx`.
**Example:**
```typescript
// Source: types.ts:120, App.tsx:165/367/1912, components/Sidebar.tsx:416 (existing, verified)
// types.ts — add to the AppView union:
| 'fleetObservability'

// App.tsx — lazy import:
const FleetObservabilityDashboard = lazy(() => import('./components/FleetObservabilityDashboard').then(m => ({ default: m.FleetObservabilityDashboard })));
// App.tsx — permission map (see Open Questions for which permission string):
fleetObservability: 'manage:agents',
// App.tsx — render switch:
case 'fleetObservability': return <ErrorBoundary name="FleetObservabilityDashboard"><FleetObservabilityDashboard /></ErrorBoundary>;

// components/Sidebar.tsx — nav entry:
{ view: 'fleetObservability', label: 'Fleet Observability', icon: <ActivityIcon size={20} />, permission: 'manage:agents' },
```

### Pattern 5: Per-tab component extraction to respect the 500-line file cap
**What:** `AgentDetailModal.tsx` is **already at 703 lines** — over the CLAUDE.md 500-line cap before this phase even starts (a pre-existing condition, not introduced by this work). Every existing tab (`RuntimeSecurityTab`, `AgentComplianceTab`, `PredictiveHealthTab`, `AgentOverviewTab`, `AgentSoftwareTab`, `AgentPatchingTab`, `AgentInstructionsTab`) is its own file; the modal itself only holds the tab-button/conditional-render wiring (~4-6 lines per tab).
**When to use:** FOBS-01/02 UI. Do NOT inline chart/timeline JSX into `AgentDetailModal.tsx` — create `AgentMetricsTab.tsx` as a new file (wrapping `MetricsChartsTab` + the new uptime timeline component) and add only a tab button + one conditional render line to the modal, matching every other tab's footprint exactly.

### Anti-Patterns to Avoid
- **Reading `agent_metrics_history` for uptime:** It's capped at 100 rows per agent with oldest-row deletion on every heartbeat (`agent_heartbeat_endpoints.py:191-198`) — at a 15–30s cadence that's only ~25-50 minutes of retained history, nowhere near the 48h window FOBS-02 needs. Use `agent_metrics` instead.
- **Assuming `GET /agents/{id}/metrics/history` is what the frontend renders:** It exists, is correctly implemented, and is a fine data source for a *new* per-agent endpoint (e.g. the uptime endpoint could live alongside it in `agent_metrics_endpoints.py`), but `MetricsChartsTab.tsx` does not call it — don't plan a task that "wires MetricsChartsTab to the metrics-history endpoint," it's already wired to the asset-metrics endpoint.
- **Trusting a per-agent configured `interval_seconds` for uptime math:** It is a client-only config value (Rust default 15s via `DEFAULT_INTERVAL`; Python default 30s) and is **never sent to or stored by the backend** (confirmed: zero occurrences of `interval_seconds` in any heartbeat/registry endpoint). The uptime algorithm has no way to know an individual agent's real cadence and must use a single fixed assumed cadence.
- **Duplicating the `is_super_admin()` role check inconsistently:** `agent_metrics_endpoints.py` uses its own ad-hoc `_METRICS_SUPER_ROLES` set (`{"Super Admin", "super_admin", "platform-admin"}`) instead of the canonical `rbac_utils.is_super_admin()` helper that `agent_core_endpoints.py` and `asset_endpoints.py` use. New FOBS endpoints should use `is_super_admin()` for consistency, not invent a third variant.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Offline-agent detection | A new "is this agent down" heuristic | `agents.status == "Offline"`, already maintained by `monitor_agent_status()` | Explicitly out of scope per REQUIREMENTS.md ("Rebuilding offline-agent detection... `monitor_agent_status()`... already exist") |
| Version comparison | A new semver library or ad-hoc string compare | `agent_auto_update_service._parse_ver()` (already handles `\d+\.\d+\.\d+` parsing and tuple comparison) | Already battle-tested by the auto-update push logic; reusing avoids a second, possibly-inconsistent version-parsing implementation |
| CPU/mem/disk charting | New chart components | `MetricsChartsTab.tsx` (recharts AreaChart/LineChart, already styled/dark-mode-aware) | D-04 lock; also the only charting pattern already proven in this exact modal context |
| Admin nav-page gating | A new permission-check wrapper | The existing `hasPermission()` context + `App.tsx`'s per-view permission map | Same mechanism every other admin dashboard (including the just-shipped Security Settings panel) already uses |
| Retention sweep scheduling | A new cron-like scheduler | `RetentionService.run_cleanup()` + whatever already calls it (daily background loop convention) | Four other collections already retained this way; adding a fifth method is a 10-line diff, not new infrastructure |

**Key insight:** Every piece of FOBS-01/02/03 that looks like "new infrastructure" (charts, background sweeps, admin pages, version parsing, offline detection) has an exact precedent already merged in this repo from the last 1-2 phases. The actual new code surface is small: one uptime-computation module, one rollup-write path, one aggregate-read endpoint, and the UI wiring to expose them.

## Common Pitfalls

### Pitfall 1: Duplicate-route shadowing (`asset_endpoints.py` vs `asset_metrics_endpoints.py`)
**What goes wrong:** Both files define `@router.get("/{asset_id}/metrics")` under the same `/api/assets` prefix. FastAPI/Starlette resolves routes in router-inclusion order; `router_registry.py` loads `asset_endpoints` (line 82) before `asset_metrics_endpoints` (line 280), so the second file's handler is unreachable dead code.
**Why it happens:** Two features were built independently (likely different phases) without noticing the path collision.
**How to avoid:** Any FOBS-01 change to "the asset metrics endpoint" must land in `asset_endpoints.py`'s `get_asset_metrics` (the one with the 3-tier fallback: `asset_metrics` → `agent_metrics_history` → `asset.telemetry` snapshot). Editing `asset_metrics_endpoints.py` instead would have zero effect on the running app.
**Warning signs:** A plan/task that edits `asset_metrics_endpoints.py` and claims it fixes FOBS-01 chart data — verify against `router_registry.py`'s load order before trusting that claim.

### Pitfall 2: Hardcoded `range_hours` dict silently swallows new range keys
**What goes wrong:** `asset_endpoints.py:240` does `{"1h": 1, "24h": 24, "7d": 168, "30d": 720}.get(time_range, 24)`. If the frontend is changed to send `"6h"` or `"48h"` (required by D-02) without adding matching keys here, the backend silently defaults to 24h — the UI will show a "6h" or "48h" label over what is actually a 24h window, corrupting the uptime-adjacent chart data without erroring.
**Why it happens:** The dict's `.get(..., 24)` fallback is silent by design (never raises), so this bug produces no error, no log line, no 4xx — just quietly wrong data.
**How to avoid:** Any task that changes `MetricsChartsTab.tsx`'s preset buttons to include `6h`/`48h` MUST include the matching `asset_endpoints.py` dict edit in the same task/commit.
**Warning signs:** Chart shows identical data for two different range selections.

### Pitfall 3: No server-side record of real per-agent heartbeat cadence
**What goes wrong:** The Rust agent's `DEFAULT_INTERVAL` is 15s (configurable via `cfg.interval_seconds`); the Python agent's default is 30s. Neither value is ever sent to or stored by the backend. `monitor_agent_status()` already hardcodes a 30s-cadence assumption (5 min / 10 = 30s) directly in its docstring/threshold, without it being a real per-agent fact. Any agent configured for a slower-than-assumed cadence will show artificially degraded uptime %; faster-than-assumed just clips at 100%.
**Why it happens:** `interval_seconds` is a purely local agent-config value, never round-tripped in the heartbeat payload.
**How to avoid:** Use the same fixed 30s assumption `monitor_agent_status()` already uses (for internal consistency across the two features, even though it's not perfectly accurate for every agent build) and document the limitation in code comments/UI copy rather than silently presenting the % as exact.
**Warning signs:** A Rust-agent-heavy fleet (15s real cadence) showing suspiciously perfect ~100% uptime across the board is expected and fine; a fleet with a deliberately-slowed custom `interval_seconds` showing degraded uptime despite being fully online is the failure mode to watch for.

### Pitfall 4: `agent_metrics` has no retention today
**What goes wrong:** Unlike `metrics`, `audit_logs`, `notifications`, and (as of Phase 46) `agent_location_history`, the `agent_metrics` collection that both `GET /agents/{id}/metrics/history` and the new uptime gap-detection will read has **no cleanup method in `retention_service.py` at all** — it grows unbounded. This phase doesn't have to fix that (out of scope per D-02: "no history-collection downsampling"), but the NEW `agent_uptime_rollups` collection this phase DOES introduce must not repeat the omission.
**Why it happens:** `agent_metrics` predates the retention-service pattern (Phase 9) and was never retrofitted.
**How to avoid:** Add `cleanup_agent_uptime_rollups()` to `retention_service.py` and wire it into `run_cleanup()`'s report dict, mirroring the Phase 46 `agent_location_history` addition exactly. Do not attempt to also add retention to `agent_metrics` itself — that's out of this phase's scope and could regress the 48h chart/uptime windows other features already depend on.
**Warning signs:** A plan task that scopes retention onto `agent_metrics` (not `agent_uptime_rollups`) has scope-crept beyond D-02's explicit boundary.

### Pitfall 5: Tenant isolation on the new fleet aggregate endpoint
**What goes wrong:** Unlike the background rollup sweep (which legitimately needs cross-tenant raw-db access), the FOBS-03 **request-time** aggregate endpoint must respect the calling admin's tenant scope — a Tenant Admin must only see their own tenant's offline/version-drift agents; only a Super Admin/platform-admin should see the full fleet. Because `agents` is NOT in `TenantIsolatedDatabase`'s exemption list, using the ambient wrapped `db.agents` collection through the normal request-scoped `get_database()` dependency already enforces this correctly by default — the risk is a developer "fixing" a perceived permission gap by switching to `db._db.agents` (raw) inside the endpoint handler, which would leak cross-tenant data.
**Why it happens:** Confusion between the two legitimate raw-db use cases (background sweeps) and the one illegitimate one (request-scoped reads).
**How to avoid:** The new aggregate endpoint should follow `agent_core_endpoints.get_agents()`'s exact shape: `is_super_admin(current_user.role)` gates whether `tenantId` is added to the query filter; never touch `db._db` in a request handler for this endpoint.
**Warning signs:** Any `_db.agents` (raw) access inside an `async def` decorated with `@router.get`/`@router.post` (as opposed to inside a `while True:` background loop) is almost certainly wrong.

### Pitfall 6: `AgentDetailModal.tsx` is already over the 500-line cap
**What goes wrong:** The file is 703 lines today, before any FOBS work lands. Adding tab JSX inline (rather than as a new extracted component) will make an already-CLAUDE.md-noncompliant file worse and could get flagged by code-review as a *new* violation when it's actually a pre-existing one plus a small increment.
**Why it happens:** Incremental tab additions over many phases without ever splitting the file.
**How to avoid:** Follow Pattern 5 above — new tab content goes in its own component file; the modal only gets the button + one conditional-render line, matching the ~4-6 line footprint of every other tab.
**Warning signs:** A diff to `AgentDetailModal.tsx` larger than ~10 added lines for this phase's work.

## Code Examples

### Deriving `assetId` for the new metrics/uptime tab (already-proven pattern in this exact file)
```typescript
// Source: components/AgentDetailModal.tsx:308 (existing, verified — used today for the compliance tab)
const derivedId = asset?.id || agent?.assetId || (agent?.hostname ? `asset-${agent.hostname}` : undefined);
```
Reuse this identical derivation for `AgentMetricsTab`'s `assetId` prop — do not invent a second resolution strategy.

### `_parse_ver` version comparison (FOBS-03 version-drift)
```python
# Source: backend/agent_auto_update_service.py:19-25 (existing, verified)
_LATEST_AGENT_VERSION = "2.1.4"

def _parse_ver(v: str):
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(g) for g in m.groups()) if m else None

# Version-drift check for the new aggregate endpoint:
latest = _parse_ver(_LATEST_AGENT_VERSION)
reported = _parse_ver(agent.get("version", ""))
is_drifted = reported is not None and reported < latest
```

### Reading `agent_metrics` for the on-the-fly uptime gap-detection window
```python
# Source: backend/agent_metrics_endpoints.py:120-128 (existing pattern, verified — the same
# collection/query shape, reused for uptime instead of chart summary)
since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
metrics_filter: dict = {"agent_id": agent_id, "timestamp": {"$gte": since}}
if user_role not in _METRICS_SUPER_ROLES and tenant_id:
    metrics_filter["tenant_id"] = tenant_id
rows = await db.agent_metrics.find(metrics_filter, {"_id": 0, "timestamp": 1}).sort("timestamp", 1).to_list(length=5760)
# Bucket rows into 30s expected slots over [now-hours, now]; uptime % = received_buckets / expected_buckets (clipped to 100%).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Uptime as status-transition duration | Uptime as heartbeat-presence ratio (D-01 lock) | This phase | Simpler to compute from existing telemetry rows; no new "session" tracking needed |
| One-off manual metric-report endpoint (`POST /agents/{id}/metrics`) | Metrics embedded in every heartbeat (`meta.current_cpu`/`current_memory`) | Predates this phase (already the case) | Confirmed the standalone `POST /agents/{id}/metrics` endpoint is not called by either agent build today — it exists but appears unused in production; the heartbeat's inline write is the real data path |

**Deprecated/outdated:**
- `asset_metrics_endpoints.py`'s `get_asset_metrics` handler: unreachable dead code (shadowed by `asset_endpoints.py`). Not this phase's job to delete it, but don't build on it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 30s is the right single fixed "expected heartbeat interval" constant for uptime bucketing | Pitfall 3, Code Examples | If wrong, uptime % will be systematically biased (over- or under-reported) for agent builds/configs that don't match; mitigated by being internally consistent with `monitor_agent_status()`'s existing assumption, not a new invented number |
| A2 | `manage:agents` is the right gating permission for the new Fleet Observability nav page (vs. `manage:settings`, which Security Settings uses, or `view:agents`) | Pattern 4, Open Questions | If wrong, either over-restricts (blocking legitimate Tenant Admins) or under-restricts (exposing fleet-wide offline/version data too broadly) — low risk since both candidate permissions already exist and are easy to swap before merge |
| A3 | Daily cadence + simple per-agent-per-day upsert is sufficient for the `agent_uptime_rollups` shape (no hourly granularity) | Summary, Pattern 3 | If a future longer-range UI (deferred) needs hourly rollups, the collection shape would need a migration; D-01/Claude's-Discretion explicitly leaves this open and this research recommends the simplest shape that satisfies "groundwork, not the UI" |

**If this table is empty:** N/A — see above; all three items are low-risk implementation-detail assumptions, not compliance/security/retention-policy assumptions, and none block planning.

## Open Questions

1. **Which permission string gates the new Fleet Observability nav page?**
   - What we know: `manage:settings` (used by the Phase 47 Security Settings clone target), `manage:agents`, and `view:agents` all already exist as valid `Permission` values in `types.ts`/`rbac_utils.py`.
   - What's unclear: Whether Fleet Observability should be scoped as narrowly as Security Settings (Tenant Admin + Super Admin via `manage:settings`) or should also be visible to any role that can already see agents (`view:agents`, broader).
   - Recommendation: Default to `manage:agents` (semantically closest — it's about agents, not tenant settings) unless the planner/discuss-phase determines a broader read-only audience is wanted; either choice is a one-line change.

2. **Does the daily rollup sweep need a "first ever run" backfill, or does it only start accumulating from the day it's deployed?**
   - What we know: `snapshot_compliance_scores_loop` and `refresh_mitre_heatmap_loop` both just start fresh with no backfill — there's no historical-data-backfill precedent anywhere in this codebase's background-task history.
   - What's unclear: Whether the phase's acceptance criteria expect the rollup collection to have data immediately after deploy, or whether "starts empty, fills in over the following days" is acceptable (matching every other daily sweep's behavior).
   - Recommendation: No backfill — match the existing precedent exactly; document this as expected behavior in the rollup's module docstring so a future reader doesn't mistake an empty rollup collection on day 1 for a bug.

## Environment Availability

Not applicable — this phase has no new external tool/service/runtime dependencies. All work runs inside the existing FastAPI/Motor backend and React frontend already running in this environment (confirmed via direct file reads; no new CLI, database engine, or service is introduced).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no `pytest-asyncio` installed — async test functions call `asyncio.run()` internally, per existing convention) |
| Config file | none — no `pytest.ini`/`[tool.pytest.ini_options]` found; tests run via `backend/venv/bin/python -m pytest` |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_agent_uptime_service.py backend/tests/test_agent_fleet_observability.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend -q` (per project memory: baseline ~1343 pass / 3 pre-existing unrelated fails) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOBS-01 | `asset_endpoints.py`'s `get_asset_metrics` returns correct data for `6h`/`48h` range keys after the dict fix | unit | `pytest backend/tests/test_asset_metrics_endpoint.py -x` | ❌ Wave 0 — no existing test file covers `asset_endpoints.get_asset_metrics`; new file needed |
| FOBS-01 | `AgentMetricsTab` mounts `MetricsChartsTab` with the correctly-derived `assetId` | unit/component | (frontend — no existing RTL/vitest harness found for this component tree; verify via `npx tsc --noEmit` + manual UAT per existing project convention for UI-only changes) | ❌ Wave 0 — no frontend test framework detected for `components/` |
| FOBS-02 | Gap-detection buckets `agent_metrics` rows correctly at 30s expected cadence, computes uptime % | unit | `pytest backend/tests/test_agent_uptime_service.py -x` | ❌ Wave 0 — new file |
| FOBS-02 | `agent_uptime_rollup_loop()` writes one row per agent per day, uses raw `db._db`, native BSON Date timestamp | unit | `pytest backend/tests/test_agent_uptime_rollup_loop.py -x` | ❌ Wave 0 — new file, clone `test_agent_heartbeat_geo_security.py`'s hermetic-mock-db shape |
| FOBS-03 | New aggregate endpoint returns correct offline set + version-drift list, tenant-scoped for non-super-admin | unit | `pytest backend/tests/test_agent_fleet_observability.py -x` | ❌ Wave 0 — new file |
| FOBS-03 | `_parse_ver` comparison correctly flags drifted vs current versions (including malformed version strings) | unit | `pytest backend/tests/test_agent_fleet_observability.py -k version_drift -x` | ❌ Wave 0 — new file (can co-locate with the aggregate-endpoint test) |
| — | `retention_service.cleanup_agent_uptime_rollups()` deletes rows older than retention_days | unit | `pytest backend/tests/test_retention_service.py -k uptime_rollups -x` | Check — `test_retention_service.py` may or may not exist yet; if absent, create alongside the Phase 46 `agent_location_history` retention test pattern |

### Sampling Rate
- **Per task commit:** targeted `-k`/file-scoped pytest run for the file(s) touched
- **Per wave merge:** full backend suite (`backend/venv/bin/python -m pytest backend -q`) + `npx tsc --noEmit` for frontend changes
- **Phase gate:** Full suite green before `/gsd-verify-work`; no frontend automated test harness exists for `components/`, so FOBS-01 UI mount + FOBS-03 nav-page registration require the existing project convention of manual/browser UAT (per `human_verify_mode: "end-of-phase"` in config.json)

### Wave 0 Gaps
- [ ] `backend/tests/test_agent_uptime_service.py` — covers FOBS-02 on-the-fly gap-detection math
- [ ] `backend/tests/test_agent_uptime_rollup_loop.py` — covers FOBS-02 background sweep (hermetic, mocked db, clone `test_agent_heartbeat_geo_security.py`'s TestClient/mock shape or a plain async-mock unit shape depending on whether the loop is tested via direct function call rather than HTTP)
- [ ] `backend/tests/test_agent_fleet_observability.py` — covers FOBS-03 aggregate endpoint + version-drift
- [ ] `backend/tests/test_asset_metrics_endpoint.py` — covers FOBS-01's `range_hours` dict fix (currently zero test coverage found for `asset_endpoints.get_asset_metrics` at all — this is a pre-existing gap, not one this phase created, but the phase's own change to that dict needs a regression test)
- [ ] Confirm whether `backend/tests/test_retention_service.py` exists; if not, create it (currently no dedicated retention-service test file was found in the `backend/tests/` listing check)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | All new endpoints use `Depends(get_current_user)` — same as every existing agent/asset endpoint; no new auth mechanism |
| V3 Session Management | no | No session-management surface touched |
| V4 Access Control | yes | New fleet aggregate endpoint MUST use `is_super_admin(current_user.role)` gating (Pitfall 5) — never raw `db._db` in the request path; new nav page MUST be permission-gated in `App.tsx`'s permission map |
| V5 Input Validation | yes | New `hours`/`range` query params must be validated against an allowlist (`{"1h","6h","24h","48h"}`) rather than trusting arbitrary client strings, matching the existing `.get(time_range, 24)` fallback-to-default pattern (extend it, don't remove the safety net) |
| V6 Cryptography | no | No new cryptographic operations |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant data leak via raw `db._db` access in a request handler | Information Disclosure | Never use `db._db.agents` (raw) inside a `@router` endpoint; only the background sweep may use raw `db._db`, per Pitfall 5 |
| Tampering with reported `version` string to evade version-drift flagging | Tampering | Low severity here — version-drift is an informational fleet-health view, not a security gate; `_parse_ver`'s regex already fails closed (returns `None` → treated as "unknown/not comparable" rather than crashing) for malformed strings |
| Resource exhaustion via unbounded `hours` query param on the new uptime endpoint | Denial of Service | Cap `hours` to the same 48h/2880-point ceiling the existing `GET /agents/{id}/metrics/history` already enforces (D-02 explicitly locks this — no larger windows this phase) |

## Sources

### Primary (HIGH confidence — direct codebase verification this session)
- `backend/agent_metrics_endpoints.py` — full read, confirmed endpoint shape, 2880-point/48h cap, collection distinctions
- `backend/agent_heartbeat_endpoints.py` — full read, confirmed `agent_metrics`/`agent_metrics_history`/`asset_metrics` write paths and their trigger conditions
- `backend/app_background_tasks.py` — full read, confirmed 4 existing background-loop patterns (`monitor_agent_status`, `snapshot_compliance_scores_loop`, `refresh_mitre_heatmap_loop`, `_start_xdr_correlation_scanner`)
- `backend/app_startup.py` (lines 455-590) — confirmed exact background-task registration pattern and `_safe_bg_task` wrapper
- `backend/agent_auto_update_service.py` — full read, confirmed `_LATEST_AGENT_VERSION`/`_parse_ver`
- `backend/retention_service.py` — full read, confirmed existing retention methods and the `agent_metrics` retention gap
- `backend/database.py` (lines 100-153) — confirmed `TenantIsolatedDatabase` exemption list and raw-db-access pattern
- `backend/agent_location_history_service.py` (docstring + `get_track_agent_location`) — confirmed native-BSON-Date convention and raw-db precedent
- `backend/asset_endpoints.py` (lines 200-300) and `backend/asset_metrics_endpoints.py` (full file) — confirmed the duplicate-route shadowing bug via `router_registry.py` load order
- `backend/router_registry.py` (grep for load order) — confirmed `asset_endpoints` registers before `asset_metrics_endpoints`
- `backend/agent_core_endpoints.py` (lines 1-140) — confirmed existing `GET /api/agents` filter/pagination shape and `is_super_admin()` convention
- `components/MetricsChartsTab.tsx` — full read, confirmed `assetId` prop contract, internal uncontrolled range state, `fetchAssetMetrics` call
- `components/AgentDetailModal.tsx` — full read, confirmed 703-line current size, tab-extraction pattern, `assetId` derivation precedent (line 308)
- `components/SecuritySettingsDashboard.tsx` + `App.tsx`/`components/Sidebar.tsx`/`types.ts` grep — confirmed the exact 4-file admin-nav-page registration pattern
- `services/apiService.ts` (line 1587) — confirmed `fetchAssetMetrics`'s real endpoint and range-type union
- `agent-rust/src/agent.rs`, `agent-install/omni-agent-rs/src/heartbeat.rs`, `agent/agent.py` — grepped for heartbeat cadence constants (`DEFAULT_INTERVAL = 15`, Python default 30s) and confirmed `current_cpu`/`current_memory` are always present in every heartbeat's `meta`
- `backend/tests/test_agent_heartbeat_geo_security.py` — read for test-pattern precedent (hermetic TestClient + shared rate-limiter reset fixture)
- `.planning/config.json` — confirmed `nyquist_validation: true`, `security_enforcement: true`, `security_asvs_level: 1`

### Secondary (MEDIUM confidence)
None — no WebSearch/Context7/external documentation lookups were performed; all web-search providers are disabled in `.planning/config.json` (`brave_search`/`exa_search`/`tavily_search`/`ref_search`/`perplexity`/`jina` all `false`), and this phase's scope is entirely internal reuse requiring no external library research.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; every reused piece verified by direct file read
- Architecture: HIGH — every pattern (background sweep, tenant isolation, admin-nav registration, tab extraction) is copied from an already-merged, already-tested precedent in this exact codebase
- Pitfalls: HIGH — all 6 pitfalls are concrete, code-verified findings (duplicate routes, silent range-key fallback, unpersisted interval_seconds, missing retention, raw-db tenant-leak risk, file-size cap), not speculative

**Research date:** 2026-07-29
**Valid until:** 30 days (stable, internal-reuse-only phase; re-verify if `asset_endpoints.py`, `agent_heartbeat_endpoints.py`, or `app_background_tasks.py` are touched by an intervening phase before 48 is planned/executed)
