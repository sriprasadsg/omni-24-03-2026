# Phase 48: Fleet Observability & Uptime Rollups - Context

**Gathered:** 2026-07-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Give admins a fleet operational view, reusing existing telemetry/detection rather than rebuilding:

- **FOBS-01** — per-agent CPU/memory/disk history rendered as charts in the agent detail view.
- **FOBS-02** — per-agent heartbeat/uptime timeline + an uptime % over a selectable range.
- **FOBS-03** — one fleet-level view: which agents are offline + which run a version older than latest.

Reuse-first: the metrics-history endpoint, `recharts`, `MetricsChartsTab.tsx`, `monitor_agent_status()` offline detection, and `_LATEST_AGENT_VERSION` all already exist. New work = the uptime computation/rollup + the frontend surfaces. Offline-first / air-gapped throughout (no external services).

</domain>

<decisions>
## Implementation Decisions

### Uptime Computation (FOBS-02)
- **D-01:** **Hybrid model.** Implement BOTH: (a) an **on-the-fly gap-detection** path that computes the fine uptime timeline + uptime % by bucketing existing heartbeat/metric timestamps over the requested window (gap = missed heartbeats vs the ~30s cadence); AND (b) a **background daily uptime-rollup sweep** writing a per-agent daily uptime % into a rollup collection (e.g. `agent_uptime_rollups`), so aggregate/long-range uptime is cheap and a future longer-range UI is a switch-on, not a rebuild. Uptime definition = heartbeat-presence ratio (received/expected), not status-transition duration.

### Time Range (FOBS-01/02)
- **D-02:** **UI exposes ≤48h presets only this phase** (e.g. 1h / 6h / 24h / 48h), served by the existing fine `GET /agents/{id}/metrics/history?hours=N` endpoint (2880-point / ~48h cap). Longer ranges (7d/30d) are **deferred** — the D-01 rollup sweep lays the groundwork, but the v3.3 UI does not surface them. No history-collection downsampling or endpoint cap change in this phase.
- **Interaction note (D-01 × D-02):** the rollup sweep is built but only ≤48h ranges are user-visible now. The on-the-fly path backs the exposed presets; the rollup path is scaffolding for the deferred longer-range view. Planner: keep the rollup sweep minimal (write daily %), don't build longer-range UI.

### Fleet View + Version-Drift (FOBS-03)
- **D-03:** **New admin-gated "Fleet Observability" nav page**, cloning the Phase 47 Security-panel pattern (dedicated view, admin-gated, registered in App.tsx + Sidebar.tsx). Backed by a **new aggregate endpoint** returning: offline agents (from the existing `status == "Offline"` set maintained by `monitor_agent_status()`) + version-drift list. **Version-drift = each agent's reported version compared to the single global `_LATEST_AGENT_VERSION`** (currently 2.1.4). Single-version compare — per-OS latest tracking is deferred (only one binary today).

### FOBS-01 Charts (reuse + mount)
- **D-04:** **Reuse `MetricsChartsTab.tsx` as-is** (already renders CPU/mem/disk AreaCharts via recharts, consuming the metrics-history endpoint). Scope = **mount it into the agent detail view** (a new tab in `AgentDetailModal.tsx`, or in `AgentOverviewTab.tsx`) — it is currently only mounted in `AssetDetail.tsx` — and add the shared ≤48h range selector (D-02). No chart rework beyond the mount + range prop.

### Claude's Discretion
- Exact rollup sweep cadence + retention for `agent_uptime_rollups` (suggest daily sweep, retention routed through the existing retention module like Phase 46's location-history — planner/research decide).
- Whether the fleet aggregate is one new endpoint or extends an existing fleet/dashboard endpoint.
- Chart range-selector component (new shared control vs inline preset buttons).
- Exact uptime bucketing granularity for the fine timeline.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` §Fleet Observability (FOBS) — FOBS-01/02/03 + deferrals (native time-series rollups; no external tile/IP APIs; do not rebuild offline detection/version tracking).
- `.planning/ROADMAP.md` §Phase 48 — goal, success criteria, "reuse not rebuild".

### Reuse targets (do NOT rebuild)
- `backend/agent_metrics_endpoints.py:100` — `GET /{agent_id}/metrics/history?hours=N` (fine metrics, ~48h/2880-point cap, returns time-series + summary). Source for FOBS-01 + the on-the-fly uptime path.
- `backend/app_background_tasks.py:41` — `monitor_agent_status()` marks agents Offline after >5 min inactivity (10× missed 30s heartbeat). Source of the FOBS-03 offline set. Pattern for the D-01 rollup sweep (another background task).
- `backend/agent_auto_update_service.py:19` — `_LATEST_AGENT_VERSION` (2.1.4) + `_parse_ver`. Version-drift source for FOBS-03.
- `components/MetricsChartsTab.tsx` — existing CPU/mem/disk recharts AreaCharts (`assetId` prop); mounted in `components/AssetDetail.tsx:395`. Reuse for FOBS-01.
- `components/AgentDetailModal.tsx` / `components/AgentOverviewTab.tsx` — agent detail surface where FOBS-01 charts + FOBS-02 timeline mount.
- Phase 47 `components/SecuritySettingsDashboard.tsx` + its App.tsx/Sidebar.tsx registration — the admin-gated nav-page pattern to clone for the FOBS-03 Fleet Observability page.
- `backend/retention_service.py` — existing retention module; route any `agent_uptime_rollups` retention through it (Phase 46 pattern).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MetricsChartsTab.tsx` — FOBS-01 charts, ready to mount (currently asset-only).
- Metrics-history endpoint — FOBS-01 data + on-the-fly uptime buckets.
- `monitor_agent_status()` — offline set for FOBS-03; template for the uptime-rollup background sweep.
- `_LATEST_AGENT_VERSION` / `_parse_ver` — version-drift compare for FOBS-03.
- recharts — installed, used across many dashboards.

### Established Patterns
- Admin-gated nav page: new view + App.tsx lazy import + ErrorBoundary case + Sidebar entry gated by a `manage:*` permission (Phase 47 Security panel).
- Background sweeps registered in `app_background_tasks.py`.
- Per-tenant/retention config + sweeps routed through `retention_service` (Phase 46).

### Integration Points
- FOBS-01: mount `MetricsChartsTab` into `AgentDetailModal`/`AgentOverviewTab` + range selector.
- FOBS-02: new uptime endpoint (on-the-fly gap detection) + a `agent_uptime_rollups` sweep in `app_background_tasks.py`; timeline UI in the agent detail view.
- FOBS-03: new aggregate endpoint (offline set + version-drift) + new admin-gated Fleet Observability page.

</code_context>

<specifics>
## Specific Ideas

- Uptime = heartbeat-presence ratio (received/expected at ~30s), not online-interval duration.
- Version-drift = reported vs single `_LATEST_AGENT_VERSION` (2.1.4).
- v3.3 keeps observability ranges ≤48h in the UI; rollup sweep built but longer-range UI deferred.

</specifics>

<deferred>
## Deferred Ideas

- **Longer ranges (7d/30d) in the UI** — groundwork (rollup sweep) built this phase, UI surfacing deferred.
- **Native MongoDB time-series collections** — migrate uptime/metrics history if retention outgrows the current cap (REQUIREMENTS.md).
- **Per-OS / per-platform latest-version tracking** — single global version compare for now.
- **Rebuilding offline detection or version tracking** — explicitly out of scope; reuse `monitor_agent_status()` + existing version flow.

None else — discussion stayed within phase scope.

</deferred>

---

*Phase: 48-fleet-observability-uptime-rollups*
*Context gathered: 2026-07-29*
