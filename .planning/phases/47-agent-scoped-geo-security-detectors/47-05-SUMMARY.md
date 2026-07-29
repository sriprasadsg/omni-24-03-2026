---
phase: 47-agent-scoped-geo-security-detectors
plan: 05
subsystem: ui
tags: [typescript, react, tailwind, geo, vpn-heuristic]

# Dependency graph
requires:
  - phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
    provides: "agent_asn_service.lookup() vpn_heuristic flag stored on agent.geo; amber badge convention set in AgentLocationHistory.tsx"
provides:
  - "GeoLocation TS interface with vpn_heuristic?/asn? fields"
  - "Amber 'likely VPN/hosting' heuristic badge on the live agent card (AgentList.tsx)"
affects: [47-agent-scoped-geo-security-detectors, gsec-02-impossible-travel-suppression-explainability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Heuristic-only security labeling convention (never 'detected') reused verbatim across AgentLocationHistory.tsx and AgentList.tsx"

key-files:
  created: []
  modified:
    - types.ts
    - components/AgentList.tsx

key-decisions:
  - "GeoLocation.asn typed as { number?: number | string; org?: string } to match agent_asn_service.lookup()'s stored shape, kept fully optional since the flag is 3-valued (true/false/absent)"
  - "Badge markup, Tailwind classes, and WifiIcon cloned identically from AgentLocationHistory.tsx (Phase 46) rather than extracted into a shared component — plan scope was a direct clone, not a refactor"

patterns-established:
  - "Amber heuristic badge (bg-amber-100/dark:bg-amber-900/50, WifiIcon, uppercase tracking) is now the standard 'likely VPN/hosting' UI treatment across both the location-history panel and the agent card"

requirements-completed: [GSEC-01]

coverage:
  - id: D1
    description: "GeoLocation interface exposes vpn_heuristic?: boolean and asn (optional) fields, type-checking without any"
    requirement: "GSEC-01"
    verification:
      - kind: unit
        ref: "npx tsc --noEmit (no new errors in types.ts or components/AgentList.tsx)"
        status: pass
    human_judgment: false
  - id: D2
    description: "AgentList.tsx renders the amber 'likely VPN/hosting' badge in the agent-card Location row only when agent.geo.vpn_heuristic === true, and never uses authoritative 'detected' wording"
    requirement: "GSEC-01"
    verification:
      - kind: unit
        ref: "grep -c 'likely VPN/hosting' components/AgentList.tsx == 1; grep 'detected' components/AgentList.tsx == no matches"
        status: pass
      - kind: integration
        ref: "npm run build (Vite production build, clean)"
        status: pass
    human_judgment: true
    rationale: "Visual rendering (badge only appears for a VPN-flagged agent, absent otherwise) requires a live browser check against a real agent card per 47-VALIDATION.md's Manual-Only gate — not exercised in a live browser this session."

# Metrics
duration: 8min
completed: 2026-07-29
status: complete
---

# Phase 47 Plan 05: Agent-Card VPN/Hosting Heuristic Badge Summary

**Extended `GeoLocation` with `vpn_heuristic`/`asn` and cloned Phase 46's amber heuristic badge onto the live `AgentList.tsx` agent card, closing the GSEC-01 visibility gap.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-29T13:16:00Z (approx, session start)
- **Completed:** 2026-07-29T13:24:00Z (approx, per commit timestamps)
- **Tasks:** 2/2 completed
- **Files modified:** 2

## Accomplishments
- `GeoLocation` interface in `types.ts` now exposes `vpn_heuristic?: boolean` and `asn?: { number?: number | string; org?: string }`, matching the shape `agent_asn_service.lookup()` already stores on `agent.geo` (confirmed against `backend/agent_heartbeat_endpoints.py:141` and `backend/agent_registry_endpoints.py:102`).
- `AgentList.tsx`'s agent-card Location row now renders the identical amber "likely VPN/hosting" badge from `AgentLocationHistory.tsx` (same Tailwind classes, `WifiIcon`, uppercase tracking), guarded strictly by `agent.geo?.vpn_heuristic === true` — absent for `false`/`undefined`.
- No new backend calls added; the badge reads the already-computed flag directly from `agent.geo`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend the GeoLocation interface** - `c2d91d1` (feat)
2. **Task 2: Render the amber 'likely VPN/hosting' heuristic badge on the agent card** - `1fb1979` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `types.ts` - `GeoLocation` interface gains optional `vpn_heuristic` and `asn` fields
- `components/AgentList.tsx` - imports `WifiIcon`; renders the amber heuristic badge in the Location row when `agent.geo?.vpn_heuristic === true`

## Decisions Made
- `asn` typed as `{ number?: number | string; org?: string }` — matches the backend's stored shape without over-constraining the number type (backend `agent_asn_service.py` doesn't guarantee a strict int).
- Badge cloned verbatim (markup + classes + wording) rather than extracted into a shared component, per the plan's explicit "clone the existing amber badge" instruction — no premature abstraction.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

GSEC-01 is now fully satisfied: the heuristic VPN/hosting flag is typed and visible on the live agent card, not just the location-history panel. This closes the load-bearing UI link for GSEC-02's impossible-travel suppression (D-02) — admins can now see *why* an impossible-travel alert was suppressed for a given agent by looking at its card. Manual/UAT browser verification remains outstanding per 47-VALIDATION.md's Manual-Only gate (badge visual rendering on a real VPN-flagged agent vs. a non-flagged agent was not exercised in a live browser this session — automated `tsc`/`build`/grep checks all pass).

## Self-Check: PASSED

- FOUND: types.ts
- FOUND: components/AgentList.tsx
- FOUND: c2d91d1 (commit exists)
- FOUND: 1fb1979 (commit exists)
