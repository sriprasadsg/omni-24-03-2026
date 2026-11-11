---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 15
subsystem: partner-ui
tags: [plans, partner-portal, plan-ceiling, trial, screen-picker, react, vitest]
status: complete

requires:
  - phase: 88-03
    provides: customer features view plan + planScreens; screen_outside_plan refusal
  - phase: 88-10
    provides: planCeiling on partners, plan and trialEndsAt on customer rows, PUT /plan, POST /trial, plan_outside_ceiling / not_on_trial / invalid_days codes
provides:
  - "Partner form checklist 'Plans this partner can sell' (Free default) sent as planCeiling"
  - "Partner portal Plan column (open and ended trial), 'Plan and trial' action for admins, PartnerPlanModal (change plan within ceiling, extend Free trial 1..365 days)"
  - "Create customer plan select limited to planCeiling, empty-ceiling state"
  - "PartnerScreenPicker planScreens/planName: screens outside the customer's plan greyed with one shared note; ChooseScreensModal plan line"
affects: [88-16]

actuals:
  tokens: 60000
  tasks: 3
  commits: 6
plan_head_before: 04af72c4b7c84103c8e35775f84bb596d995697b
plan_head_after: ea846584f6a86380ae4ae56bbcce702475c0cb5d

tech-stack:
  added: []
  patterns:
    - "refusal wording by PartnerApiError.code in the modal (plan_outside_ceiling, plan_changed, invalid_days), other refusals through partnerFailureText"
    - "plan limit in the picker is a second predicate (tickable = inside ceiling AND inside plan); kept = held and not tickable"

key-files:
  created:
    - components/PartnerPlanModal.tsx
    - src/__tests__/PartnerPlanModal.test.tsx
  modified:
    - services/partnerApi.ts
    - components/PartnerFormModal.tsx
    - components/PartnerPortal.tsx
    - components/PartnerCustomerModals.tsx
    - components/PartnerScreenPicker.tsx
    - src/__tests__/PartnerAdminModals.test.tsx
    - src/__tests__/PartnerPortal.test.tsx
    - src/__tests__/PartnerPortalModals.test.tsx
    - src/__tests__/PartnerScreenPicker.test.tsx

key-decisions:
  - "UI-SPEC wins over the plan text: dates are Mon D, YYYY via formatDay; one shared visible note + aria-describedby on greyed picker rows (no per-row title); the Plan modal always lists the current plan; column minimums sum to 910px"
  - "unknown_plan is worded once, in partnerFailureText, so every partner modal shows the stale-page sentence"
  - "A Free customer with no running trial (trialEndsAt null) shows 'No free trial is running.' in the Plan modal and keeps Extend offered; the server's not_on_trial sentence is the answer"

requirements-completed: [LIC-02, LIC-03, LIC-04]

coverage:
  - id: D1
    description: "Super Admin's partner form has 'Plans this partner can sell' (Free ticked for a new partner, saved planCeiling shown on edit, Free when absent), sent as planCeiling on appoint and only when changed on edit; amber status when none is ticked; invalid_plan shows the stale-page sentence"
    requirement: LIC-02
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerAdminModals.test.tsx (plan cases, 5 new + appoint payload updated)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Partner portal Plan column shows the plan, an open trial end, an ended trial in amber, a dash with no plan; admins get 'Plan and trial', viewers do not; CSV unchanged; skeleton colSpan 7/6"
    requirement: LIC-02
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerPortal.test.tsx (PartnerPortal plans, 6 cases plus header/viewer updates)"
        status: pass
    human_judgment: true
    rationale: "Whether the table fits 1280px with the sidebar open (910px of column minimums) is a visual check the spec lists as a backstop"
  - id: D3
    description: "PartnerPlanModal changes a customer's plan among the ceiling (current plan always listed), extends a Free trial 1..365 days, and words plan_outside_ceiling, unknown_plan, plan_changed, invalid_days, not_on_trial, trial_changed; refetches on any server answer"
    requirement: LIC-03
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerPlanModal.test.tsx (19 cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Create customer offers the partner's plans with Free selected (first plan when Free is outside the ceiling), sends plan, shows the empty-ceiling message with submit disabled, helper that screens outside the plan are refused"
    requirement: LIC-02
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerPortalModals.test.tsx (CreateCustomerModal plan cases, 5)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Customer screen picker greys screens outside the plan with one shared note and aria-describedby, keeps held screens outside the plan locked, leaves Phase 87 behaviour unchanged for planScreens absent or ['all'], ignores planScreens in ceiling mode (PlansPanel); ChooseScreensModal shows the plan line and screen_outside_plan verbatim"
    requirement: LIC-04
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerScreenPicker.test.tsx (plan limit, 10 cases); PartnerPortalModals.test.tsx (4 Choose screens cases); PlansPanel tests 14 pass"
        status: pass
    human_judgment: true
    rationale: "A Free-plan customer has about 190 greyed rows; whether the shared note and count line stay readable is a visual judgment (spec backstop)"
---

# Phase 88 Plan 15: Plans in the partner screens Summary

**The Super Admin picks the plans each partner can sell, the partner portal shows each customer's plan and trial and lets a partner admin change the plan within that ceiling and extend a Free trial, Create customer picks a plan, and the customer screen picker greys the screens the plan blocks with one shared note.**

## Performance

- **Duration:** about 30 min (2026-11-11, UTC)
- **Tasks:** 3 (all TDD: RED commit then GREEN commit)
- **Files:** 11 (2 created, 9 modified)

## Accomplishments

- `services/partnerApi.ts`: `PLAN_KEYS`/`PlanKey` re-exported from plansApi; `planCeiling`, `plan`, `trialEndsAt`, `planScreens` fields; `changeCustomerPlan` and `extendCustomerTrial`; `planCeiling` on appoint/update, `plan` on create.
- `PartnerFormModal`: "Plans this partner can sell" fieldset above the screens list; sent on appoint and on edit only when changed; amber `role="status"` line when none is ticked; `invalid_plan` worded as the stale-page sentence.
- `PartnerPortal`: Plan column (table and cards) after Agents, column minimums 170/120/100/130/150/120/120 = 910px, ended trial in amber words, a dash when no plan; admin-only "Plan and trial" row action; skeleton/empty `colSpan` 7 (viewer 6).
- `PartnerPlanModal` (184 lines): plan select (current plan first with "(current)" even outside the ceiling), Save plan, Free-trial fieldset with Extend trial (1..365, Enter extends), refusal wording by code, `plan_changed` resets the select to the refetched plan; one request at a time and Esc/backdrop/close ignored while saving.
- `CreateCustomerModal`: Plan select limited to `planCeiling` (default Free; first plan when Free is not in it), helper, empty-ceiling message with submit disabled, "Screens outside the chosen plan are refused." in the screens disclosure; `plan_outside_ceiling` worded; `unknown_plan` worded once in `partnerFailureText`.
- `PartnerScreenPicker`: `planScreens`/`planName`; `tickable = offerable && inPlan`; plan-greyed rows are visible, disabled, described by one shared note (no per-row title); held screens outside the plan are kept and locked; select/clear all skip greyed rows; ceiling mode ignores the plan. `ChooseScreensModal` passes plan and planScreens and shows "Plan: {plan}. Screens outside it can't be added; change the plan under Plan and trial."

## Task Commits

| Step | Commit | Message |
| ---- | ------ | ------- |
| 1 RED | ff03c65e5 | test(88-15): failing tests for the partner form's plans this partner can sell |
| 1 GREEN | 5a09bb5e6 | feat(88-15): the Super Admin chooses the plans each partner can sell |
| 2 RED | ed0bab60f | test(88-15): failing tests for the partner portal plan column, Plan and trial modal and Create customer plan |
| 2 GREEN | fc56f4fda | feat(88-15): partners see each customer's plan and trial, change the plan within their ceiling and extend the trial |
| 3 RED | 2980539f9 | test(88-15): failing tests for the customer screen picker's plan limit |
| 3 GREEN | ea846584f | feat(88-15): the customer screen picker shows the plan's limit beside the partner's ceiling |

## TDD Gate Compliance

- **RED (task 1):** 6 of 46 failed on the planned behavior (no plans fieldset, payload without planCeiling).
- **RED (task 2):** 15 failed across three files (no Plan column or action, no PartnerPlanModal module, no Create customer plan select).
- **RED (task 3):** 7 failed (no greyed rows or note, no plan line in Choose screens). Two of the new tests carried label slips (Asset Management is `view:assets`, Dashboards is `screen:customDashboards`), corrected in the GREEN commit; the behavior assertions did not change.
- **GREEN:** every task's tests pass after its implementation commit. No REFACTOR commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Circular import avoided by keeping the Create customer plan field inline**
- **Found during:** Task 2
- **Issue:** a shared plan field exported from PartnerPlanModal.tsx would make PartnerCustomerModals.tsx and PartnerPlanModal.tsx import each other (the modal needs `ErrorBlock` and `partnerFailureText`).
- **Fix:** the Create customer plan field is written inline in CreateCustomerModal (PartnerCustomerModals.tsx stays at 478 lines, under 500).
- **Commit:** fc56f4fda

**Contract deltas applied (UI-SPEC wins over the plan text, as the spec's delta table directs; not defects):** dates `Mon D, YYYY`; shared note + `aria-describedby` instead of a per-row title in the picker; the Plan modal always lists the current plan; 910px column minimums and the ended trial shown; Create customer helper and empty-ceiling state; no Plan/Trial columns in the CSV (user decision).

**Total deviations:** 1 auto-fixed (Rule 3). **Impact:** none on acceptance criteria.

## Acceptance criteria

- Task 1: `grep -c planCeiling` = 4 (PartnerFormModal.tsx), 5 (partnerApi.ts).
- Task 2: `grep -c PartnerPlanModal components/PartnerPortal.tsx` = 2; `wc -l`: PartnerPortal.tsx 447, PartnerCustomerModals.tsx 478, PartnerPlanModal.tsx 184 (all under 500).
- Task 3: `grep -c planScreens components/PartnerScreenPicker.tsx` = 4; typecheck prints 0 errors mentioning Partner.

## Verification

- Task commands: PartnerAdminModals + PartnersDashboard 69 passed; PartnerPortal + PartnerPlanModal + PartnerPortalModals 108 passed; PartnerScreenPicker + PartnerPortalModals 94 passed; PlansPanel tests (picker `mode="ceiling"`) 14 passed.
- Full suite `npx vitest run src/__tests__`: 126 files, 2063 tests passed (2010 before).
- `npm run build` succeeded (dist-new, git-ignored, not published).

## Notes for later plans and the user

- Nothing was pushed, restarted or published; 88-16 hands those to the user. The UI needs the 88-10 backend live (planCeiling, plan routes) to show anything: an older server shows Free only and no Plan column text.
- A Free customer whose `trialEndsAt` is null (consumed trial, or no trial record) shows "No free trial is running." and keeps Extend offered; the server answers `not_on_trial` verbatim.
- All files this plan touched were clean in the working tree beforehand, so each commit holds only this plan's changes.

## Known Stubs

None.

## Threat Flags

None. T-88-37 accepted: the UI limits are convenience; ownership, planCeiling, the plan screen limit and viewer refusals stay server-side (88-03, 88-10). No new endpoint or trust boundary; two calls added to existing `/api/partner` routes.

## Self-Check: PASSED

Files found: components/PartnerPlanModal.tsx, src/__tests__/PartnerPlanModal.test.tsx and the nine modified files. Commits in HEAD ancestry: ff03c65e5, 5a09bb5e6, ed0bab60f, fc56f4fda, 2980539f9, ea846584f.
