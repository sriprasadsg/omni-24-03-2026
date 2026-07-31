---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 06
subsystem: ui
tags: [react, typescript, tailwind, apiService, geoip]

# Dependency graph
requires:
  - phase: 46-04
    provides: "GET /api/agents/{agent_id}/location-history and GET/PATCH /api/settings/agent-location-tracking read/toggle endpoints"
provides:
  - "utils/geo.ts — shared flagEmoji/formatGeo helpers (extracted from AgentList.tsx, no behavior change)"
  - "services/apiService.ts — LocationHistoryEntry type, fetchAgentLocationHistory (typed), getAgentLocationTracking, setAgentLocationTracking"
  - "components/AgentLocationHistory.tsx — read-only lazy-expand Location History timeline panel (GAUD-02)"
  - "AgentLocationHistory mounted in AgentOverviewTab.tsx Overview tab"
affects: ["46-07 (remaining frontend work, if any references this panel or the toggle clients)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared formatting helper extraction into utils/ (utils/geo.ts) to avoid duplicating module-private consts across two components"
    - "Client-side-only derived value, backend value deliberately ignored: dwell computed at render time from adjacent entries' timestamps, never from the backend's dwell_seconds field"
    - "Heuristic-caution badge convention: muted amber (never red), lowercase-led non-authoritative copy for unlicensed enrichment signals (GSEC-01)"

key-files:
  created:
    - utils/geo.ts
    - components/AgentLocationHistory.tsx
  modified:
    - components/AgentList.tsx
    - services/apiService.ts
    - components/AgentOverviewTab.tsx

key-decisions:
  - "Resolved the D-08/UI-SPEC dwell conflict in favor of 46-UI-SPEC.md: AgentLocationHistory.tsx computes dwell client-side from adjacent entries' timestamps and deliberately ignores the backend's dwell_seconds field (documented inline in both apiService.ts's LocationHistoryEntry type and the component's formatDwell comment)."
  - "components/AgentLocationHistory.tsx and the fetchAgentLocationHistory apiService function already existed on disk as untracked, stale drafts from a prior uncommitted session (mirroring the same pattern seen in 46-04's backend endpoints file). The stale drafts diverged from 46-UI-SPEC.md in several ways (badge missing WifiIcon/rounded-full/uppercase styling, header count said '(N events)' instead of '(N locations)', dwell read from a stored dwellTime field instead of computed client-side, geo/flag helpers imported directly from AgentList.tsx instead of a shared util) — repaired in place per the plan's own instructions rather than left as-is."
  - "Header bar radius classes (rounded-t-md, unconditional) follow the Layout/Structure section's literal class string and the EscalationHistoryPanel analog verbatim, rather than the States table's more general 'rounded-md when collapsed' description — the literal class list is the more specific, load-bearing spec."

requirements-completed: [GAUD-02]

coverage:
  - id: D1
    description: "Read-only, lazy-expand Location History panel mounted in the Agent Overview tab, fetching only on first expand and never refetching on subsequent toggles"
    requirement: "GAUD-02"
    verification:
      - kind: other
        ref: "npx tsc --noEmit && npm run build — both succeed with zero errors referencing components/AgentLocationHistory.tsx, components/AgentOverviewTab.tsx, utils/geo.ts, or services/apiService.ts"
        status: pass
      - kind: other
        ref: "grep -c 'AgentLocationHistory' components/AgentOverviewTab.tsx >= 1 (mounted after Tenant DetailRow, before Performance Metrics)"
        status: pass
    human_judgment: true
    rationale: "Visual rendering (flag emoji, badge placement, row layout) and the lazy-fetch-on-first-expand behavior against a live agent are best confirmed by opening the Overview tab in the running app — grep/typecheck confirm structure and copy but not visual correctness."
  - id: D2
    description: "VPN/hosting heuristic badge is muted amber, never red, and never phrased as an authoritative detection"
    requirement: "GAUD-02"
    verification:
      - kind: other
        ref: "grep -c 'amber' components/AgentLocationHistory.tsx >= 1; grep -niE 'bg-red-|text-red-500' components/AgentLocationHistory.tsx matches only the fetch-error state text; grep -niE 'vpn detected|detected vpn|proxy detected|vpn/proxy detected' components/AgentLocationHistory.tsx returns nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "Panel and every row are read-only — no edit/delete/mutation affordance anywhere"
    requirement: "GAUD-02"
    verification:
      - kind: other
        ref: "grep -niE 'onDelete|onEdit|deleteLocation|editLocation' components/AgentLocationHistory.tsx returns nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "Dwell time computed client-side at render time from adjacent entries' timestamps (never from the backend's dwell_seconds field)"
    requirement: "GAUD-02"
    verification:
      - kind: other
        ref: "components/AgentLocationHistory.tsx formatDwell()/sortedEntries dwell calculation reads only entry.timestamp values; services/apiService.ts LocationHistoryEntry.dwell_seconds is typed but never read by the component"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 06: Location-History Timeline Panel Summary

**Read-only lazy-expand AgentLocationHistory.tsx panel (cloned from EscalationHistoryPanel) mounted in the Agent Overview tab, with client-side dwell computation and a muted-amber "likely VPN/hosting" heuristic badge — shared flagEmoji/formatGeo extracted to utils/geo.ts.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-29T07:42:00Z (approx, continuing directly after 46-04/46-05)
- **Completed:** 2026-07-29T08:06:34Z
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- Extracted `flagEmoji`/`formatGeo` from `AgentList.tsx` into `utils/geo.ts`, updated `AgentList.tsx` to import them (verbatim logic, no behavior change to the card view).
- Added a typed `LocationHistoryEntry` interface to `services/apiService.ts`, retyped `fetchAgentLocationHistory`'s return value with it, and added `getAgentLocationTracking`/`setAgentLocationTracking` clients for the GAUD-02 tracking toggle.
- Built `components/AgentLocationHistory.tsx`: collapsible header (`HistoryIcon` + "Location History" + `(N locations)` count + rotating `ChevronDownIcon`), lazy-fetch-on-first-expand body with mutually-exclusive loading/error/empty/row-list states, each row showing flag + city/country + conditional amber "likely VPN/hosting" badge (`WifiIcon`) + monospace public IP + UTC timestamp + client-side-computed dwell (with `(ongoing)` suffix on the most recent row).
- Mounted `<AgentLocationHistory agentId={agent.id} />` in `AgentOverviewTab.tsx`, wrapped in the standard `pt-4 border-t` section spacing, directly after the Tenant `DetailRow` and before Performance Metrics.
- `npx tsc --noEmit` and `npm run build` both succeed with zero errors touching any of this plan's files.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract geo helpers to utils/geo.ts + add apiService client functions** - `634614c` (feat)
2. **Task 2: Build AgentLocationHistory.tsx and mount it in the Overview tab** - `1d1814f` (feat)

## Files Created/Modified
- `utils/geo.ts` - Shared `flagEmoji`/`formatGeo` helpers, exported
- `components/AgentList.tsx` - Imports `flagEmoji`/`formatGeo` from `utils/geo.ts` instead of local module-private consts
- `services/apiService.ts` - `LocationHistoryEntry` type; typed `fetchAgentLocationHistory`; new `getAgentLocationTracking`/`setAgentLocationTracking`
- `components/AgentLocationHistory.tsx` - Read-only lazy-expand Location History timeline panel (GAUD-02)
- `components/AgentOverviewTab.tsx` - Mounts `AgentLocationHistory` after the Tenant `DetailRow`

## Decisions Made
- Reconciled the dwell-computation conflict flagged by 46-04's SUMMARY.md in favor of 46-UI-SPEC.md: dwell is computed client-side from adjacent entries' `timestamp` values; the backend's `dwell_seconds` field is typed (for completeness/documentation) but deliberately never read.
- Repaired two pre-existing, untracked stale drafts (`components/AgentLocationHistory.tsx` and the `fetchAgentLocationHistory` addition to `services/apiService.ts`) found already on disk at plan start, rather than leaving them as-is — they diverged from the UI-SPEC's locked copy/color/behavior contract (see Deviations).
- Kept the header bar's `rounded-t-md` class unconditional (matching the `EscalationHistoryPanel` analog and the UI-SPEC's own literal "Layout / Structure" class list) rather than implementing a conditional `rounded-md`/`rounded-t-md` swap suggested more loosely by the States table — the more specific spec section wins.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Repaired a stale, untracked draft of `components/AgentLocationHistory.tsx` that diverged from the UI-SPEC**
- **Found during:** Task 2
- **Issue:** An untracked `components/AgentLocationHistory.tsx` already existed on disk (not from this session), presumably scaffolded in a prior interrupted run. It used `ShieldIcon` instead of the locked `GlobeIcon`, labelled the header count `(N events)` instead of `(N locations)`, read dwell from a stored `entry.dwellTime` field instead of computing it client-side from adjacent timestamps (violating the D-09/Behavior Contract anti-pattern guard), rendered the IP with `<code>` instead of a `font-mono` span, used compact `px-1.5 py-0.5 text-[10px]` badge styling instead of the locked `px-2 py-1 text-[11px] rounded-full uppercase tracking-wide` pill with a `WifiIcon`, and imported `flagEmoji`/`formatGeo` directly from `AgentList.tsx` instead of the newly-shared `utils/geo.ts`.
- **Fix:** Rewrote the component to match 46-UI-SPEC.md's Copywriting/Color/Layout contracts exactly, sourcing `flagEmoji`/`formatGeo` from `utils/geo.ts` and computing dwell purely from `entry.timestamp` values (never from any stored dwell field).
- **Files modified:** `components/AgentLocationHistory.tsx`
- **Verification:** `grep` acceptance-criteria gates for copy/color/read-only all pass; `npx tsc --noEmit` and `npm run build` succeed.
- **Committed in:** `1d1814f` (Task 2 commit)

**2. [Rule 1 - Bug] `fetchAgentLocationHistory` in `services/apiService.ts` was already present, untyped (`entries: any[]`)**
- **Found during:** Task 1
- **Issue:** An uncommitted, working-tree-only version of `fetchAgentLocationHistory` already existed with an `any[]` entries type, providing no compile-time guarantee for the panel's field access (`entry.geo`, `entry.vpn_heuristic`, `entry.publicIp`, `entry.timestamp`).
- **Fix:** Added an exported `LocationHistoryEntry` interface and retyped `fetchAgentLocationHistory`'s return value to use it.
- **Files modified:** `services/apiService.ts`
- **Verification:** `npx tsc --noEmit` succeeds; `AgentLocationHistory.tsx` consumes the typed entries with no `any` casts.
- **Committed in:** `634614c` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — repairing pre-existing, untracked, stale/incorrect drafts found on disk at plan start)
**Impact on plan:** Both fixes were necessary to meet the plan's own must_haves and the UI-SPEC's locked contract. No scope creep — no new files beyond the plan's own file list, no architectural changes.

## Issues Encountered
- `components/AgentLocationHistory.tsx` and part of `services/apiService.ts`'s `fetchAgentLocationHistory` were already present on disk as untracked changes before this plan began executing (mirroring the same "stale untracked draft" pattern 46-04 encountered with its backend endpoints file). Both were repaired in place rather than treated as already-complete, since they diverged from this plan's must_haves and the UI-SPEC's locked contract.
- `npx tsc --noEmit` reports pre-existing, unrelated errors in vendored `github-mcp-server/` and `servers/` subdirectories (missing `@modelcontextprotocol/sdk`, `@primer/react`, `zod`, etc. type declarations) — confirmed out of scope (Scope Boundary rule) and unrelated to any file this plan touches; `npm run build` (the actual app bundle via Vite) succeeds cleanly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The GAUD-02 Location History panel is fully wired: backend read/toggle endpoints (46-04) + heartbeat/register write path (46-05, if completed) + this frontend panel together satisfy the phase's UI-visible deliverable.
- Manual verification recommended per the plan's own `<verification>` section: open an agent detail view after a public-IP change and confirm the timeline rows render with flag/city/IP/VPN-badge/timestamp/dwell (flagged as human-judgment in the coverage block above).
- Remaining phase work (if any) is tracked in `46-07-PLAN.md`.

---
*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Completed: 2026-07-29*

## Self-Check: PASSED
