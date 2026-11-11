---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 12
subsystem: ui
tags: [plans, super-admin, tenant-management, react, vitest, plan-ceiling]
status: complete

requires:
  - phase: 88-04
    provides: server refusal of screens outside a plan (422) on POST/PATCH /api/tenants
  - phase: 88-08
    provides: GET /api/platform/plans and PUT /api/platform/plans/{key}
provides:
  - services/plansApi.ts (PlanKey, PLAN_KEYS, Plan, fetchPlans, savePlan, allowedScreens)
  - components/PlansPanel.tsx, the Super Admin Plans dialog, opened by a Plans button in Tenant Management
  - Manage Tenant treats the plan as a ceiling (D-27, D-28)
  - Add Tenant defaults to Free; Custom asks for seats and sends maxAgents (D-24)
  - apiService.addTenant defaults to Free and forwards maxAgents
affects: [88-13, 88-16]

tech-stack:
  added: []
  patterns:
    - "plan ceiling in the UI: a switch outside the plan's list is disabled unless the tenant already has it; the server still refuses"

key-files:
  created:
    - services/plansApi.ts
    - components/PlansPanel.tsx
    - src/__tests__/PlansPanel.test.tsx
    - src/__tests__/AddNewTenantModal.test.tsx
  modified:
    - components/TenantManagementDashboard.tsx
    - components/ManageTenantModal.tsx
    - components/AddNewTenantModal.tsx
    - services/apiService.ts
    - src/__tests__/ManageTenantModal.test.tsx

key-decisions:
  - "Choosing a plan in Manage Tenant changes no checkbox; the old SUBSCRIPTION_TIERS preset and the dead tier-sync effect that read it were removed from ManageTenantModal"
  - "A switch is disabled when it is outside the chosen plan and not currently ticked; that one rule covers 'kept' screens (ticked, marked 'outside plan', can be unticked, then stay off), so no separate keptOutside set is stored"
  - "Select all adds the plan's allowed switches to what is already ticked (it no longer drops service: ticks, which the old code did)"
  - "If the plan table cannot be loaded every box stays enabled; the server still refuses"
  - "Plans dialog shows each plan's screen list inside a collapsed details element (about 200 checkboxes per plan)"

requirements-completed: [LIC-07, LIC-04, LIC-02]

duration: 25 min
completed: 2026-11-11

actuals:
  tokens: 40000
  tasks: 2
  commits: 4
plan_head_before: 1186f69b50eba61da8fc382d3e4cd7c1d765cd94
plan_head_after: 33a1da60750bb947bfd24d8b47fd8213f84c7590

coverage:
  - id: D1
    description: "Plans dialog from Tenant Management lists Free, Pro, Enterprise and Custom with seats and tenant counts; saving sends PUT /api/platform/plans/{key} with only the changed fields and shows 'Saved. N tenants updated.'"
    requirement: LIC-07
    verification:
      - kind: unit
        ref: "src/__tests__/PlansPanel.test.tsx (lists Free, Pro..., saving Pro seats..., unticking a screen...)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Trial days editable on Free only; Custom read-only 'Set per tenant by contract'; effect-timing note (seats at once, screens future only, trial days new trials only); 422 text shown and edits kept; non-whole seats not sent"
    requirement: LIC-07
    verification:
      - kind: unit
        ref: "src/__tests__/PlansPanel.test.tsx (trial days exist on Free only, explains when each kind of change, shows a 422 answer, does not send a seat count)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Manage Tenant: choosing a plan ticks nothing; boxes outside the plan are disabled with 'Not part of the <plan> plan'; kept screens stay ticked, marked 'outside plan', untickable; select all ticks only allowed switches; save still sends features and tier"
    requirement: LIC-04
    verification:
      - kind: unit
        ref: "src/__tests__/ManageTenantModal.test.tsx (D-27 choosing a plan..., plan ceiling describe, 5 cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Add Tenant opens on Free; Custom shows a required seats input and sends maxAgents; apiService.addTenant posts Free by default and forwards maxAgents"
    requirement: LIC-02
    verification:
      - kind: unit
        ref: "src/__tests__/AddNewTenantModal.test.tsx (6 cases)"
        status: pass
    human_judgment: false
  - id: D5
    description: "How the Plans dialog, the disabled/marked boxes and the Custom seats field look and read in the live Spatial Glass UI"
    requirement: LIC-07
    human_judgment: true
    rationale: "Visual adequacy and wording in the real UI are not asserted by any test; the UI is not published until 88-16"
---

# Phase 88 Plan 12: Plans screen, plan ceiling in Manage Tenant, Free default in Add Tenant

**Super Admin Plans dialog (seats, Free trial days, per-plan screen lists) plus plan-as-ceiling boxes in Manage Tenant and a Free default with Custom seats in Add Tenant**

## Accomplishments

- `services/plansApi.ts` wraps GET/PUT `/api/platform/plans` and exposes `allowedScreens(plan)` (a Set, or `'all'` for Custom or an all-screens plan).
- `components/PlansPanel.tsx` (177 lines): one region per plan with seats, Free-only trial days, a collapsible screen checklist grouped like Manage Tenant with per-group counts, per-plan Save sending only changed fields, inline success/error text, and the effect-timing note. Custom is read-only. Opened from a new "Plans" button beside "Add New Tenant".
- Manage Tenant: the tier select lists Free, Pro, Enterprise, Custom and no longer ticks anything. Boxes outside the chosen plan are disabled with the reason; ones the tenant already has stay ticked with an "outside plan" marker until unticked. Select all ticks only what the plan allows. File is 413 lines.
- Add Tenant: defaults to Free, plan options from `PLAN_KEYS`, Custom shows a required seats field validated 0..1,000,000 and sends `maxAgents`; `addTenant` defaults to Free and forwards `maxAgents`. App.tsx forwards the object unchanged and was not edited.

## Task Commits

1. Task 1 RED `6d66c95e0` test, GREEN `7c1d787f8` feat (Plans screen)
2. Task 2 RED `fb1a371d5` test, GREEN `33a1da607` feat (plan ceiling, Free default)

## Verification

- `npx vitest run src/__tests__/ManageTenantModal.test.tsx src/__tests__/AddNewTenantModal.test.tsx src/__tests__/PlansPanel.test.tsx`: 28 passed.
- `npx vitest run src/__tests__`: 1948 passed (1929 before plus 19 new).
- `npm run build`: built in 3.23s. `npm run typecheck` shows nothing for the touched files. eslint on the touched files is clean.
- Acceptance greps: Enterprise default gone from AddNewTenantModal and apiService, `allowedScreens` used in ManageTenantModal, all files under 500 lines.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed the no-op tier-sync effect in ManageTenantModal**
- **Found during:** Task 2
- **Issue:** an effect read `SUBSCRIPTION_TIERS` to detect a matching tier but its only action was commented out; keeping it would have kept the preset import the plan asked to drop.
- **Fix:** removed the effect and the import. Select labels are now the plain plan keys ("Free", not "Free Tier").
- **Files modified:** components/ManageTenantModal.tsx
- **Commit:** 33a1da607

**2. [Plan simplification] No separate keptOutside set**
- The plan described a `keptOutside` set computed at load. The rule "disabled when outside the plan and not currently ticked" gives the same behavior (kept screens stay enabled while ticked, disabled after unticking) and also covers switching to a smaller plan, so no extra state was added.

**3. [Rule 1 - Bug] Select all no longer drops service ticks**
- The old handler replaced the set with only the switch list, silently clearing `service:` selections. The new handler adds the allowed switches to what is ticked.

**Total deviations:** 3 (1 bug cleanup, 1 simplification, 1 bug fix). **Impact:** none on the plan's behaviors.

## Notes for later plans

- `services/apiService.ts` still carries the user's uncommitted `setUserPassword` hunk; only the two `addTenant` hunks were committed (via `git apply --cached`).
- 88-13 runs `ManageTenantModal.test.tsx`; it is green. The tests mock `authFetch` per URL, so a plans fetch that is not mocked simply leaves all boxes enabled.
- The UI is not published; 88-16 hands that to the user. `npm run build` wrote to the git-ignored `dist-new`.

## Known Stubs

None.

## Threat Flags

None. No new endpoint or trust boundary; the UI only shapes input and the server refuses (T-88-34 accepted).

## Self-Check: PASSED

Files exist (plansApi.ts, PlansPanel.tsx, PlansPanel.test.tsx, AddNewTenantModal.test.tsx); commits 6d66c95e0, 7c1d787f8, fb1a371d5, 33a1da607 are on HEAD's history; full suite and build green.
