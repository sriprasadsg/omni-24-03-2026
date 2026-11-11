---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 13
subsystem: ui
tags: [licence, plans, trial, tenant-admin, super-admin, react, vitest]
status: complete

requires:
  - phase: 88-01
    provides: GET /api/tenants/{id}/license licence view (plan, planSeats, seatOverride, partnerManaged, exempt, trial, allowedNetworks)
  - phase: 88-06
    provides: licence PATCH answers the licence view and accepts clearSeatOverride and trialExtendDays
  - phase: 88-12
    provides: the Manage Tenant plan-ceiling changes this panel sits beside
provides:
  - services/licenceApi.ts (LicenceView, LicenceTrial, LicenceNetwork, LicenceChanges, fetchLicenceView, updateLicence, networkLabel)
  - components/TenantPlanCard.tsx, the tenant admin's read-only licence card on the Agents screen
  - TenantLicensePanel plan row, Use plan number, Free trial extension and read-only allowed networks
affects: [88-16]

tech-stack:
  added: []
  patterns:
    - "licence client in its own module (services/licenceApi.ts) so apiService.ts, already over 500 lines and carrying user hunks, is not edited"
    - "a body that is not a licence view renders nothing in the card (refused or malformed read)"

key-files:
  created:
    - services/licenceApi.ts
    - components/TenantPlanCard.tsx
    - src/__tests__/TenantPlanCard.test.tsx
    - src/__tests__/TenantLicensePanel.test.tsx
  modified:
    - components/TenantLicensePanel.tsx
    - components/AgentsDashboard.tsx
    - src/__tests__/EnrollmentControlsPanels.test.tsx
    - src/__tests__/ManageTenantModal.test.tsx

key-decisions:
  - "Use plan number shows only for a direct tenant with a seat override on a plan other than Custom; a partner customer instead reads that the partner's allotment sets the seats"
  - "Extend and Use plan number are their own PATCH calls: Use plan number re-adopts the whole view (the Max agents field returns to the plan number), Extend only refreshes the trial so unsaved edits in the other fields are kept"
  - "The tenant card shows the networks as written by people (a /32 or /128 drops its suffix); the Super Admin panel shows the full CIDR"
  - "The old licence client in apiService.ts (fetchTenantLicense, updateTenantLicense) is left in place, now unused by the panel"

requirements-completed: [LIC-07, LIC-01, LIC-03]

duration: 12 min
completed: 2026-11-11

actuals:
  tokens: 7500
  tasks: 2
  commits: 4
plan_head_before: 462677d280b5d273cf3cdf906e9788533389755e
plan_head_after: 353b9887bfba01251452e4e644363925c0781067

coverage:
  - id: D1
    description: "Tenant admin's Agents screen shows a read-only 'Your plan' card: plan, seats used of the limit with 'override' or 'set by your partner', days left on an open Free trial, the allowed networks with their source and an empty-state line; no input or button"
    requirement: LIC-07
    verification:
      - kind: unit
        ref: "src/__tests__/TenantPlanCard.test.tsx (shows the plan..., marks an override and a partner-set limit, explains an empty network list, offers no control)"
        status: pass
    human_judgment: false
  - id: D2
    description: "After a Free trial ends the card says the trial has ended, new computers wait for approval and running agents and screens keep working"
    requirement: LIC-03
    verification:
      - kind: unit
        ref: "src/__tests__/TenantPlanCard.test.tsx (says the trial has ended and that running agents keep working)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The card renders nothing for the platform organization (exempt) or when the licence read is refused"
    requirement: LIC-07
    verification:
      - kind: unit
        ref: "src/__tests__/TenantPlanCard.test.tsx (renders nothing for an exempt organization, renders nothing when the licence read is refused)"
      - kind: unit
        ref: "src/__tests__/AgentsDashboard.test.tsx (the card is rendered there and a non-licence body shows nothing)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Manage Tenant licence panel shows 'Plan X: N seats' beside 'Limit N (override)', and 'Use plan number' sends PATCH {clearSeatOverride: true} for a direct tenant with an override and then shows the plan number; absent for a partner customer"
    requirement: LIC-01
    verification:
      - kind: unit
        ref: "src/__tests__/TenantLicensePanel.test.tsx (shows the plan number beside the limit..., has no Use plan number without an override...)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The licence panel shows the Free trial end and days left and extends by a whole number of days 1..365 through PATCH {trialExtendDays}; 0, 366, 2.5 and empty disable Extend; a server refusal is shown"
    requirement: LIC-03
    verification:
      - kind: unit
        ref: "src/__tests__/TenantLicensePanel.test.tsx (shows the trial end and days left on Free and extends it, shows a refusal from the server...)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both panels list the allowed networks with their source, read-only; the existing save fields still send the same PATCH body"
    requirement: LIC-05
    verification:
      - kind: unit
        ref: "src/__tests__/TenantLicensePanel.test.tsx (lists the allowed networks..., still saves the existing fields with the same PATCH body)"
      - kind: unit
        ref: "src/__tests__/EnrollmentControlsPanels.test.tsx (TenantLicensePanel controls)"
        status: pass
    human_judgment: false
  - id: D7
    description: "How the card and panel look and read in the real Spatial Glass UI (spacing, wording on dark and light themes)"
    requirement: LIC-07
    human_judgment: true
    rationale: "No test asserts layout or visual fit; the UI publish is the user's (88-16)"
---

# Phase 88 Plan 13: Licence card and Super Admin licence panel Summary

**Tenant admins now see their plan, seats, trial and allowed networks on the Agents screen, and the Super Admin's Manage Tenant licence panel shows the plan number, clears a seat override and extends a Free trial.**

## Accomplishments

- `services/licenceApi.ts`: typed `LicenceView` (plan, planSeats, seatOverride, partnerManaged, exempt, trial, allowedNetworks), `fetchLicenceView` and `updateLicence` with the same `{error}` / `{detail}` error handling as before.
- `TenantPlanCard` (68 lines): read-only "Your plan" card above the pending agents panel for a tenant context. Seats line with `(override)` or `(set by your partner)`, "N days left in your free trial", the trial-ended wording (D-21), the networks with source and an empty-state line. Renders nothing for exempt, refused or malformed reads. It contains no input, button or select.
- `TenantLicensePanel` (228 lines): plan row, "Limit N (override)", "Use plan number" (PATCH `clearSeatOverride`), a Free trial row with end date, days left and an "Extend trial by (days)" control (PATCH `trialExtendDays`, 1..365), and a read-only "Allowed networks" list. Every existing control and its PATCH body are unchanged.
- One import and one JSX line added to `AgentsDashboard.tsx`; `apiService.ts` is not touched.

## Task Commits

| Task | Phase | Commit | Description |
| ---- | ----- | ------ | ----------- |
| 1 | RED | 80b9725e4 | failing TenantPlanCard tests |
| 1 | GREEN | 222d75ceb | licenceApi, TenantPlanCard, AgentsDashboard line |
| 2 | RED | 0cc8d2ddb | failing TenantLicensePanel tests |
| 2 | GREEN | 353b9887b | plan row, Use plan number, trial extension, networks; older tests mock the new client |

## Verification

- `npx vitest run src/__tests__/TenantPlanCard.test.tsx src/__tests__/AgentsDashboard.test.tsx`: 16 passed.
- `npx vitest run src/__tests__/TenantLicensePanel.test.tsx src/__tests__/ManageTenantModal.test.tsx` (plus EnrollmentControlsPanels): 26 passed.
- `npx vitest run src/__tests__`: 123 files, 1962 tests passed (1948 before, 14 new).
- `npm run typecheck`: 0 lines mentioning TenantLicensePanel, TenantPlanCard, licenceApi or the edited tests.
- `npm run build`: built (dist-new, git-ignored, not published).
- Acceptance: `grep -c TenantPlanCard components/AgentsDashboard.tsx` = 2; `<input|<button` in TenantPlanCard.tsx = 0; `clearSeatOverride|trialExtendDays` in TenantLicensePanel.tsx = 2; TenantLicensePanel.tsx = 228 lines.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Older tests mocked the old licence client**
- **Found during:** Task 2
- **Issue:** `EnrollmentControlsPanels.test.tsx` and `ManageTenantModal.test.tsx` mock `fetchTenantLicense` / `updateTenantLicense` from apiService; the panel now uses `services/licenceApi`, so their mocks no longer reached it.
- **Fix:** mock `services/licenceApi` (`fetchLicenceView`, `updateLicence`) instead; the licence fixture gained the new view fields. Assertions unchanged.
- **Files modified:** src/__tests__/EnrollmentControlsPanels.test.tsx, src/__tests__/ManageTenantModal.test.tsx
- **Commit:** 353b9887b

**2. [Rule 1 - Bug] Card crashed on a body that is not a licence view**
- **Found during:** Task 1
- **Issue:** AgentsDashboard tests answer every fetch with a generic body; the card read `allowedNetworks.length` of `undefined` and 4 dashboard tests failed.
- **Fix:** the card renders nothing unless the body has a string `plan` and an `allowedNetworks` array.
- **Files modified:** components/TenantPlanCard.tsx
- **Commit:** 222d75ceb

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug). **Impact:** none on scope.

## Known Stubs

None.

## Threat Flags

None. The card has no edit control and the PATCH route keeps its platform permission check (T-88-35).

## Next Phase Readiness

Ready for the rest of wave 5/6. 88-16 hands the push, restart and UI publish to the user: this plan's UI is built (dist-new) but not published.

## Self-Check: PASSED

- FOUND: services/licenceApi.ts, components/TenantPlanCard.tsx, src/__tests__/TenantPlanCard.test.tsx, src/__tests__/TenantLicensePanel.test.tsx
- FOUND commits: 80b9725e4, 222d75ceb, 0cc8d2ddb, 353b9887b
