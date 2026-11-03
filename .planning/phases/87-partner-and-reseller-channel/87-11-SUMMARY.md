---
phase: 87-partner-and-reseller-channel
plan: 11
subsystem: ui
tags: [react, typescript, vitest, partner-channel, super-admin]

requires:
  - phase: 87-07
    provides: services/partnerApi.ts, PartnerStatusChip, PoolExpiryChip, PartnerScreenPicker (ceiling mode)
provides:
  - PartnersDashboard, the Super Admin Partners screen (not yet wired into the shell; 87-14 does that)
  - PartnerFormModal (Appoint and Edit partner)
  - SuspendPartnerDialog, ReinstatePartnerDialog
  - PartnerMoveCustomerModal (move and add modes)
affects: [87-14]

actuals:
  tokens: 24300
  tasks: 3
  commits: 6
plan_head_before: c1850b7bd08ad15fa7705277fd6bb96899b85029
plan_head_after: 30ce9dfbb2e88878bfa8e7abfba453f7f89988a5

tech-stack:
  added: []
  patterns:
    - "A 409 PartnerApiError is a named refusal and its text is shown verbatim; every other server message is wrapped as Couldn't {action}: {message}. Try again."
    - "Wide layout is read from matchMedia and defaults to the table when it cannot be asked, so tests and old browsers get one layout, not two copies of every row"
    - "Modal titles that carry data are a block span with break-words inside Modal's truncating h2, so a long name wraps"

key-files:
  created:
    - components/PartnersDashboard.tsx
    - components/PartnerFormModal.tsx
    - components/PartnerStatusDialogs.tsx
    - components/PartnerMoveCustomerModal.tsx
    - src/__tests__/PartnersDashboard.test.tsx
    - src/__tests__/PartnerAdminModals.test.tsx
  modified: []

key-decisions:
  - "A partner whose stored ceiling contains all is edited as every screen ticked, and the ceiling is sent only when the selection changed; ticking every screen is sent as [all] so it stays unrestricted"
  - "Only 409 refusals are shown verbatim; other failures keep the plan's Couldn't {action} wording with the server text and its trailing full stop removed"
  - "The Overview screen is not counted in the table's N screens figure, matching the picker's N of total"
  - "Expiry is read from the stored string (first ten characters) so no timezone shifts the day in the date field"

patterns-established:
  - "The dashboard owns modal state and passes each dialog an onClose and a single success callback (onSaved, onDone, onMoved) that refetches the table and every open customers panel"

requirements-completed: [PART-01, PART-03, PART-07]

coverage:
  - id: D1
    description: "Partners table: loading skeleton, empty state, error with Try again, ordered rows with pool bar, expiry chips, screen count, status, pluralised counts, search above 10 and paging at 25 from 50"
    requirement: PART-01
    verification:
      - kind: unit
        ref: "src/__tests__/PartnersDashboard.test.tsx"
        status: pass
    human_judgment: false
  - id: D2
    description: "Show customers disclosure with the D-01 columns only, one fetch per partner, empty and error states, Move customer and Add an existing organization buttons"
    requirement: PART-07
    verification:
      - kind: unit
        ref: "src/__tests__/PartnersDashboard.test.tsx#PartnersDashboard customers disclosure"
        status: pass
    human_judgment: false
  - id: D3
    description: "Appoint and Edit partner form: validation messages, request bodies, handed-out floor and verbatim 409, result view when the invite email was not sent, Esc and backdrop blocked in flight"
    requirement: PART-03
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerAdminModals.test.tsx#PartnerFormModal"
        status: pass
    human_judgment: false
  - id: D4
    description: "Suspend, Reinstate and Move dialogs: red and accent confirms, pending labels, consequence line before submit, fit refusal disabling submit, add mode with direct customers only"
    requirement: PART-07
    verification:
      - kind: unit
        ref: "src/__tests__/PartnerAdminModals.test.tsx#Suspend and Reinstate dialogs"
        status: pass
      - kind: unit
        ref: "src/__tests__/PartnerAdminModals.test.tsx#PartnerMoveCustomerModal"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual fit against 87-UI-SPEC: spacing, light and dark theme, stacked cards below lg, 1,008px table scroll below xl, wrapping at 320px"
    verification: []
    human_judgment: true
    rationale: "The screen is not mounted in the shell until 87-14 and the UI is not published; layout, theme and responsive behavior can only be judged in a browser"

duration: 13min
completed: 2026-11-03
status: complete
---

# Phase 87 Plan 11: Super Admin Partners Screen Summary

**The Partners screen with its pool bars, per-partner customers disclosure, Appoint and Edit form with screen ceiling and first administrator, Suspend and Reinstate confirmations, and the Move customer dialog that shows the seat consequence before it submits.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-11-03T16:02:07Z
- **Completed:** 2026-11-03T16:15:11Z
- **Tasks:** 3
- **Files modified:** 6 (6 created)

## Accomplishments

- `PartnersDashboard` (479 lines): header, count, search above 10, six-column table with `min-w` columns, stacked cards below `lg`, four skeleton rows with `aria-busy`, empty state, error block with Try again and no stale table, paging at 25 from 50 partners, and the Show customers disclosure (`aria-expanded`, `aria-controls`) that loads a partner's customers once and shows only name, seats used, seats assigned, agents online and licence expiry.
- `PartnerFormModal` (280 lines): one form, two titles. Appoint sends the name, pool, optional end-of-day expiry, ceiling and first administrator; Edit sends only changed fields, states the handed-out floor, refuses a lower pool inline and shows the server's 409 verbatim. When the invite email was not sent the modal stays open on a result view naming User Management.
- `PartnerStatusDialogs` (139 lines): Suspend is the one red confirm, with the audit line; Reinstate is accent. Both lock in flight.
- `PartnerMoveCustomerModal` (217 lines): move mode lists every other active partner then No partner (direct customer), states the consequence, and disables submit when the target cannot fit the seats; add mode lists direct customers only, with a filter above 20 and the empty line.
- Verification: the three task commands pass (59 and 88 tests across the files), `npx tsc --noEmit` is clean, and the full frontend suite passes: 80 files, 1062 tests, no failures (this plan adds 62 of them).

## Task Commits

1. **Task 1: Partners table and customers disclosure** - RED `b40e66dab` (test), GREEN `6b9e81d0a` (feat)
2. **Task 2: Appoint and Edit partner form** - RED `58eddad4c` (test), GREEN `d30bd128f` (feat)
3. **Task 3: Suspend, Reinstate and Move dialogs** - RED `4d29a0174` (test), GREEN `30ce9dfbb` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## TDD Gate Compliance

Every task has a `test(87-11)` commit before its `feat(87-11)` commit; no refactor commit was needed. `workflow.tdd_mode` is not set, so the machine RED-evidence classifier was not required. Semantic assessment of each RED run: the components were committed as empty stubs, so every new case failed on an assertion (element or text not found), not on an import or syntax error.

- **Task 1 RED:** 18 of 18 failed on assertions.
- **Task 2 RED:** 21 of 21 failed on assertions.
- **Task 3 RED:** 20 new cases failed on assertions; the 21 Task 2 cases still passed.

## Files Created/Modified

- `components/PartnersDashboard.tsx` - the screen, table, cards, disclosure and modal state
- `components/PartnerFormModal.tsx` - Appoint and Edit partner
- `components/PartnerStatusDialogs.tsx` - Suspend and Reinstate confirmations
- `components/PartnerMoveCustomerModal.tsx` - Move customer and Add an existing organization
- `src/__tests__/PartnersDashboard.test.tsx` - 21 tests
- `src/__tests__/PartnerAdminModals.test.tsx` - 41 tests

## Decisions Made

See `key-decisions` above. One to repeat for 87-14: the dashboard has no props and is a default and named export; wire it as the `partners` view.

## Deviations from Plan

None - plan executed exactly as written. The only liberties are copy the UI-SPEC leaves open: the select placeholders (`Choose where to move it`, `Choose an organization`), the add-mode summary (`{name} is a direct customer`, `{n} seats assigned`), the customers-panel load error and the organizations load error. Each follows the Copywriting Contract's error pattern.

## Issues Encountered

- The CLAUDE.md `npm run build && npm test` instruction was met as `npx tsc --noEmit` plus the full vitest run; `npm run build` was not run (it writes `dist-new` only and the plan does not require it).
- Not built here by design: the shell wiring (route, sidebar entry) belongs to 87-14, and nothing was published.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. (The stub components committed in the RED commits were replaced in the GREEN commits.)

## Threat Flags

None. No new endpoint, auth path or schema; T-87-36 is mitigated: every server string renders as React text and `grep -c dangerouslySetInnerHTML` prints 0 on all four components.

## Self-Check: PASSED

- All six files exist; all six commit hashes are ancestors of HEAD.
- Acceptance greps: no `truncate`/`line-clamp` in the dashboard (0), `aria-expanded` present, line counts 479, 280, 139, 217 (all under 500), `closeOnBackdrop={false}` 2, the email-not-sent sentence 1, `No partner (direct customer)` 1, `bg-red-600` in the status dialogs 1 and in the move modal 0.
