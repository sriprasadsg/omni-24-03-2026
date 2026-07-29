---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 07
subsystem: ui
tags: [react, privacy, settings, tailwind, gdpr]

requires:
  - phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
    provides: "getAgentLocationTracking/setAgentLocationTracking apiService clients (46-06) backed by the admin-gated GET/PATCH /api/settings/agent-location-tracking endpoint (46-04)"
provides:
  - "Agent Location Tracking disclosure note (D-03) in the existing PrivacyDashboard settings surface"
  - "Per-tenant track_agent_location toggle (D-02) wired to the 46-04 backend endpoint"
  - "setAgentLocationTracking() now surfaces PATCH failures (e.g. 403 for non-admins) instead of silently swallowing them"
affects: [privacy-dashboard, agent-location-history, settings]

tech-stack:
  added: []
  patterns:
    - "Button-based pill toggle switch (role=switch, translate-x-1/translate-x-5) cloned from NotificationCenter.tsx's existing Slack/email toggle pattern"

key-files:
  created: []
  modified:
    - components/PrivacyDashboard.tsx
    - services/apiService.ts

key-decisions:
  - "Placed the disclosure + toggle as a standalone card between the summary stat grid and the tab bar (always visible regardless of active tab) rather than inside any one tab, since the setting is tenant-wide and not DSR/breach/activity-specific."
  - "Matched PrivacyDashboard.tsx's own existing dark palette (bg-gray-800/gray-700, bg-blue-600) rather than the 46-UI-SPEC.md slate tokens — the UI-SPEC document is explicitly scoped to the AgentLocationHistory timeline panel (46-06), not this file; the plan's own action instructs reusing this file's existing conventions."

requirements-completed: [GAUD-01]

coverage:
  - id: D1
    description: "Disclosure note explaining what agent location data is tracked, why (employee-device IP/geo for security/observability), retention (365 days), and that it can be disabled for works-council/GDPR reasons"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "grep -ciE 'location tracking|agent location' components/PrivacyDashboard.tsx (4 matches) and grep -ciE '365' components/PrivacyDashboard.tsx (1 match)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-tenant track_agent_location toggle reading current state via getAgentLocationTracking() on mount and persisting via setAgentLocationTracking() on change, with success/error toast"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "grep -c getAgentLocationTracking components/PrivacyDashboard.tsx (2) and grep -c setAgentLocationTracking components/PrivacyDashboard.tsx (2)"
        status: pass
      - kind: integration
        ref: "npx tsc --noEmit (0 new errors vs pre-change baseline) and npm run build (succeeds, PrivacyDashboard-G6O93eVo.js emitted)"
        status: pass
    human_judgment: true
    rationale: "Toggle persistence across reload and the admin-403 error-toast path require driving the running app against the live backend endpoint (46-04) — genuine runtime/UAT verification, not something a static grep or build check can confirm."

duration: 20min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 07: Privacy Dashboard Location Tracking Toggle Summary

**Agent Location Tracking disclosure note + per-tenant toggle added to PrivacyDashboard.tsx, wired to the 46-04 backend endpoint, with a fixed setAgentLocationTracking() client that now surfaces PATCH failures instead of swallowing them.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-29T07:55:00Z
- **Completed:** 2026-07-29T08:15:40Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added an "Agent Location Tracking" disclosure card to `PrivacyDashboard.tsx` (D-03): explains that enabled agents' public WAN IP + resolved city/country are recorded to an immutable location-history audit trail for security/observability, that this is employee-device network location data retained 365 days, and that disabling stops new location-history rows and skips ASN/VPN enrichment for the tenant (D-02 OFF semantics).
- Added a per-tenant toggle switch, cloned from the existing `NotificationCenter.tsx` pill-toggle pattern, that reads the setting via `getAgentLocationTracking()` on mount and persists changes via `setAgentLocationTracking()`, disabling itself while the request is in flight and toasting success/error.
- Fixed a latent bug in `setAgentLocationTracking()` (introduced in 46-06): it previously swallowed non-OK PATCH responses and returned the requested value as if it had succeeded, which would have silently defeated this task's own T-46-07-A mitigation ("non-admins receive 403 and the toast surfaces the failure"). It now throws on a non-OK response, matching the `if (!res.ok) throw new Error(...)` convention used throughout the rest of `apiService.ts`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Agent Location Tracking disclosure note + toggle to PrivacyDashboard** - `ef59df4` (feat)

**Plan metadata:** (final docs commit follows this SUMMARY)

## Files Created/Modified
- `components/PrivacyDashboard.tsx` - Added disclosure card + toggle switch, `loadLocationTrackingSetting()`/`toggleLocationTracking()` handlers, wired to `getAgentLocationTracking`/`setAgentLocationTracking`.
- `services/apiService.ts` - `setAgentLocationTracking()` now throws `Error(detail)` on a non-OK PATCH response instead of returning a false-success value.

## Decisions Made
- Card placement: standalone section between the summary stat grid and the tab bar, visible regardless of the active DSR/Breach/Activities tab (the setting is tenant-wide, not tab-scoped).
- Visual language: matched `PrivacyDashboard.tsx`'s own existing dark gray/blue palette and its file-local toggle conventions rather than the 46-UI-SPEC.md tokens, per the plan's explicit instruction (the UI-SPEC is scoped to the `AgentLocationHistory` timeline panel from 46-06, not this settings surface) — no new palette/font/component library introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `setAgentLocationTracking()` silently swallowed PATCH failures**
- **Found during:** Task 1 (wiring the toggle's onChange handler)
- **Issue:** The 46-06-added `setAgentLocationTracking()` client caught all failures (network errors and non-OK HTTP responses alike) and returned `{ enabled }` — the value the caller *requested* — as if the write had succeeded. This meant a 403 from the admin-gated PATCH (or any other failure) would be indistinguishable from success at the call site, directly undermining this task's own threat-model mitigation T-46-07-A ("the UI control simply calls it — non-admins receive 403 and the toast surfaces the failure") and the acceptance criteria's implicit requirement that the toggle actually reflect persisted state.
- **Fix:** Removed the try/catch swallow; the function now throws `new Error(detail)` on a non-OK response, matching the established `if (!res.ok) throw new Error(...)` pattern used elsewhere in `apiService.ts` (e.g. `fetchComponents`, MFA/passkey endpoints). `PrivacyDashboard.tsx`'s `toggleLocationTracking()` catches this and shows an error toast; on success it re-syncs local state from the server's returned `enabled` value.
- **Files modified:** `services/apiService.ts`
- **Verification:** `npx tsc --noEmit` (no new errors vs. a `git stash`-verified pre-change baseline of 144 pre-existing unrelated errors in vendored `servers/` MCP packages) and `npm run build` (succeeds).
- **Committed in:** `ef59df4` (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix was necessary to make this task's own stated threat mitigation (T-46-07-A) actually true at runtime; without it the toggle would appear to succeed even when the backend rejected the write. No scope creep — the change is confined to the one function this task's new UI code calls.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GAUD-01's privacy pre-implementation gate is now met on both the backend (46-04 admin-gated toggle endpoint) and frontend (this disclosure + toggle) sides.
- Manual UAT still recommended: open the Privacy settings surface as an admin, flip the toggle, confirm the toast and that the setting persists across a page reload; separately confirm a non-admin session sees the toggle's PATCH rejected with a visible error toast.
- No blockers for downstream Phase 47 detector work — this plan closes out 46-07, the last plan in phase 46.

---
*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Completed: 2026-07-29*

## Self-Check: PASSED
- FOUND: components/PrivacyDashboard.tsx
- FOUND: services/apiService.ts
- FOUND: .planning/phases/46-public-ip-asn-vpn-enrichment-location-history-audit/46-07-SUMMARY.md
- FOUND: ef59df4
