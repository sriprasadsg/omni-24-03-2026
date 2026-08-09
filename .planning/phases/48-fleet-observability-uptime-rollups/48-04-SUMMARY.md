---
phase: 48-fleet-observability-uptime-rollups
plan: 04
subsystem: ui
tags: [react, typescript, recharts, agent-detail, fleet-observability]

# Dependency graph
requires:
  - phase: 48-fleet-observability-uptime-rollups (48-01)
    provides: "GET /agents/{id}/metrics/history?hours=N and GET /agents/{id}/uptime?hours=N endpoints"
provides:
  - "Agent-scoped Metrics tab in AgentDetailModal with CPU/mem/disk AreaCharts + uptime timeline"
  - "fetchAgentMetricsHistory / fetchAgentUptime apiService clients"
affects: [49-fleet-geo-map]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Agent-scoped tab component (AgentMetricsTab) mirrors MetricsChartsTab's recharts chart layout but consumes a different, agent-scoped endpoint — chart structure reused, data source parametrized per D-04 CORRECTION"
    - "Shared range-selector state lifted into the tab component, passed down to an embedded sub-component (AgentUptimeTimeline) so both react to one control"

key-files:
  created:
    - components/AgentMetricsTab.tsx
    - components/AgentUptimeTimeline.tsx
  modified:
    - services/apiService.ts
    - components/AgentDetailModal.tsx

key-decisions:
  - "AgentMetricsTab is a new file (not a MetricsChartsTab prop change) since the asset-scoped and agent-scoped endpoints have different shapes/tenancy — cleanest to keep the two chart tabs fully independent per D-04 CORRECTION"
  - "AgentDetailModal.tsx grew by its per-tab footprint only (+14/-1 lines: import, type union entry, tab button, conditional render) — matches every other tab, no chart/timeline JSX inlined (Pitfall 6)"

patterns-established:
  - "Range-selector state owned by the parent tab component and passed as props to child components (AgentUptimeTimeline) rather than each component independently managing its own hours state"

requirements-completed: [FOBS-01, FOBS-02]

coverage:
  - id: D1
    description: "Agent detail Metrics tab renders CPU/memory/disk history as recharts AreaCharts, driven by a 1h/6h/24h/48h range selector, consuming GET /agents/{id}/metrics/history"
    requirement: "FOBS-01"
    verification:
      - kind: automated_ui
        ref: "npx tsc --noEmit && npm run build (both clean, no new errors)"
        status: pass
    human_judgment: true
    rationale: "Chart rendering correctness and visual behavior across live data require a human to open the app, view an agent, and confirm the charts actually render — automated typecheck/build cannot confirm the runtime data-binding and UI look."
  - id: D2
    description: "Same tab renders a per-agent uptime timeline + uptime % over the shared range selector, consuming GET /agents/{id}/uptime"
    requirement: "FOBS-02"
    verification:
      - kind: automated_ui
        ref: "npx tsc --noEmit && npm run build (both clean, no new errors)"
        status: pass
    human_judgment: true
    rationale: "Uptime timeline/percent correctness against live heartbeat data and its reaction to range-selector changes requires human UAT in a running app, matching the plan's own manual <human-check> step."

# Metrics
duration: 20min
completed: 2026-07-29
status: complete
---

# Phase 48 Plan 04: Agent Metrics + Uptime Tab Summary

**New agent-scoped Metrics tab in AgentDetailModal rendering CPU/mem/disk recharts AreaCharts and a heartbeat-presence uptime timeline, both driven by a shared 1h/6h/24h/48h range selector.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-29
- **Tasks:** 3/3
- **Files modified:** 3 (1 created new pair of components, 1 apiService edit, 1 modal edit)

## Accomplishments
- Two new `apiService.ts` functions — `fetchAgentMetricsHistory(agentId, hours)` and `fetchAgentUptime(agentId, hours)` — mirroring `fetchAssetMetrics`'s auth/error-handling shape, both restricted to the D-02 `1 | 6 | 24 | 48` hour union type (no 7d/30d)
- New `components/AgentMetricsTab.tsx`: CPU/memory/disk recharts AreaCharts adapted from `MetricsChartsTab.tsx`'s layout, consuming the agent-scoped metrics-history endpoint (not the asset endpoint), with a 1h/6h/24h/48h range selector and graceful empty-data handling
- New `components/AgentUptimeTimeline.tsx`: uptime % (color-coded), a compact horizontal up/down bucket strip, and an explicit honesty note that the % is a heartbeat-presence estimate at an assumed 30s cadence (T-48-12)
- `AgentDetailModal.tsx` gained exactly one new tab button + one conditional render line (+14/-1 net), matching every other tab's footprint — no chart/timeline JSX inlined into the 700+-line file

## Task Commits

Each task was committed atomically:

1. **Task 1: apiService fetchers for agent metrics-history + uptime** - `8a4085a` (feat)
2. **Task 2: AgentMetricsTab + AgentUptimeTimeline components** - `7f35cd1` (feat)
3. **Task 3: Mount the Metrics tab in AgentDetailModal** - `b5d6c10` (feat)

_No TDD tasks in this plan — all three are `type="auto"` implementation tasks._

## Files Created/Modified
- `services/apiService.ts` - Added `fetchAgentMetricsHistory` and `fetchAgentUptime` plus their response-shape interfaces
- `components/AgentMetricsTab.tsx` - New: CPU/mem/disk AreaCharts + range selector, embeds `AgentUptimeTimeline`
- `components/AgentUptimeTimeline.tsx` - New: uptime % + bucketed timeline strip sub-component
- `components/AgentDetailModal.tsx` - Added Metrics tab button + conditional render (per-tab footprint only)

## Decisions Made
- Kept `AgentMetricsTab.tsx` and `MetricsChartsTab.tsx` as two fully separate components (not a shared-with-prop-toggle component) since their data sources, tenancy scoping, and range presets (1/6/24/48 vs 1h/24h/7d/30d) genuinely differ — matches the plan's D-04 CORRECTION guidance to adapt the chart *structure*, not reuse the component itself
- Uptime timeline rendered as equal-width flex divs (not a chart library) — simplest correct rendering of a boolean up/down sequence, avoids pulling in another recharts chart type for a binary strip
- `AgentUptimeTimeline` receives `agentId`/`hours` as props rather than deriving its own agent-id, so `AgentMetricsTab` is the single source of truth for the shared range selector

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FOBS-01 and FOBS-02 UI surfaces are complete and wired; Phase 48's remaining work (FOBS-03 fleet-level offline/version-drift view) is independent of this plan's files.
- Manual UAT (open an agent, click Metrics tab, confirm charts + uptime render and react to the range selector) is outstanding per this plan's own `<human-check>` step — deferred to end-of-phase per `human_verify_mode`, consistent with prior 48-0x plans in this phase.
- `npx tsc --noEmit` and `npm run build` both clean for all files this plan touched (pre-existing vendored `servers/` TypeScript errors are unrelated and out of scope, confirmed no new errors introduced).

---
*Phase: 48-fleet-observability-uptime-rollups*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files exist on disk; all 3 task commit hashes (8a4085a, 7f35cd1, b5d6c10) found in git log.
