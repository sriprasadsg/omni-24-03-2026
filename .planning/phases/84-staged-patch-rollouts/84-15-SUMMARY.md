---
phase: 84-staged-patch-rollouts
plan: 15
subsystem: ui
status: complete
tags: [patch-rollout, approval-cards, needs-your-decision, react, typescript, vitest]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-10 GET /api/autonomous-ops/rollout-cards and the rollout line approve/deny routes; 84-02 ApprovalCard / ApprovalLine / LineDecisionResult types"
  - phase: 83-autonomous-response
    provides: "Needs your decision section, incident card anatomy, StateChip, formatExpires, ACCENT/SECONDARY buttons"
provides:
  - "services/patchRollouts/approvals.ts: fetchRolloutCards, approveLine, denyLine over the rollout-lines routes (DEV-1)"
  - "components/patchRollouts/RolloutApprovalCard.tsx: one card per waiting ring with Install, Restart and Revert restart lines, each with its own Approve and Deny"
  - "AutonomousOpsDecisions: incident and rollout cards read on one cadence and merged into one list by soonest deadline"
affects: [84-21]

requirements-completed: [PTCH-06]

actuals:
  tokens: 17000
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 38e022a8dfa1fbcc2777a92a4ecdde6a088063bb
plan_head_after: 68c2b26be02ce8cc6b3450c332a70a364afb0bac

tech-stack:
  added: []
  patterns:
    - "a rollout line patches itself locally after a decision, but only while the server still says pending; the server's settled text wins as soon as it arrives"
    - "two already-ordered card lists are merged by deadline (each source keeps its own order); a read failure of one kind keeps that kind's last cards"

key-files:
  created:
    - services/patchRollouts/approvals.ts
    - components/patchRollouts/RolloutApprovalCard.tsx
    - src/__tests__/RolloutApprovalCard.test.tsx
  modified:
    - components/AutonomousOpsDecisions.tsx
    - src/__tests__/_autonomousOpsDecisionsHarness.tsx
    - src/__tests__/AutonomousOpsActivity.test.tsx

key-decisions:
  - "DEV-1 (UI-SPEC Planning Deviations, pending the user's review, NOT marked accepted): Approve and Deny on a rollout line call POST /api/autonomous-ops/rollout-lines/{rolloutId}/{ring}/{line}/approve and /deny (one request per line) instead of the per-action approve route. Recorded in the approvals.ts header and here."
  - "The Approve button renders when the server says canApprove, or when automatic actions are stopped and the caller can still deny (the server reports canApprove false during a stop), then it is disabled with the Paused helper. Someone who cannot deny never sees an Approve button (T-84-46)."
  - "Reboot and Revert restart Why text is whatever the server sends (messages.py wording), as 84-10 handed over; the card renders text, never rebuilds sentences."
  - "A read failure of one kind (incidents or rollout cards) keeps the other kind's cards and shows the 'Couldn't refresh approvals' notice; a first load where one kind fails and the other is empty is still the full load error."

patterns-established:
  - "RolloutApprovalCard props: card, stopped (boolean), shadow, tenantId, now, onDecided(card), onStale()"

coverage:
  - id: D1
    description: "A rollout card per waiting ring shows the header (LayersIcon, name, Ring i of r subtitle, nearest-expiry chip) and an Install line, a Restart line and a Revert restart line with target, Why, What happens and Show computers (10 then 'Showing 10 of n.')"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "src/__tests__/RolloutApprovalCard.test.tsx#RolloutApprovalCard: lines"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each pending line has its own Approve and Deny (no approve-all) whose aria-labels name the target, ring and rollout; decisions call the rollout line routes; toasts carry patch and computer counts and the window time"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "src/__tests__/RolloutApprovalCard.test.tsx#RolloutApprovalCard: approving and denying"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stop disables Approve but not Deny, shadow mode renders no buttons, a viewer without approval access sees the waiting sentence, denied and expired lines read the server result, an expired deadline disables Approve, failures keep the line with the 83 copy and a 409 shows the server text and refetches"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "src/__tests__/RolloutApprovalCard.test.tsx#RolloutApprovalCard: stop, shadow, access and settled lines"
        status: pass
    human_judgment: false
  - id: D4
    description: "Needs your decision merges incident and rollout cards into one list by soonest deadline with the '{n} incidents · {k} rollout rings' count, Show more, the expiry-only sentence, the combined live region and partial-failure behavior; the incident-only section is unchanged"
    requirement: PTCH-06
    verification:
      - kind: unit
        ref: "src/__tests__/RolloutApprovalCard.test.tsx#Needs your decision: rollout cards beside incident cards"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsDecisions.test.tsx and autonomousOpsDecisionsCards.test.tsx (unchanged assertions)"
        status: pass
    human_judgment: true
    rationale: "How the merged list, the card density and the Approve/Deny consequences read to a person on the real screen is a visual judgment no test asserts; the UI is unpublished, so this belongs to the phase UAT"

duration: 36 min
completed: 2026-11-06
---

# Phase 84 Plan 15: Rollout Approval Card in Needs Your Decision Summary

**A per-ring rollout approval card (Install, Restart and Revert restart lines, each with its own Approve and Deny that name the target) inside the Needs your decision section, merged with the Phase 83 incident cards into one deadline-ordered list and decided through the 84-10 rollout line routes.**

## Accomplishments

- `approvals.ts` reads `GET /api/autonomous-ops/rollout-cards` and posts one approve or deny per line to `/rollout-lines/{rolloutId}/{ring}/{line}/...`, with the optional tenant query and the same error type the incident cards use.
- `RolloutApprovalCard` (305 lines) follows the 83 card anatomy with the section 6 deltas: LayersIcon header, `Ring i of r` subtitle, amber nearest-expiry chip, a `ul` of lines with `divide-y` and two columns at `lg`, the server's label, mono `break-all` target, Why, What happens (with the 5-minute restart warning printed before the click), a `Show computers` disclosure and per-line `Approving...` / `Denying...` states that disable only that line.
- Aria-labels read `Approve: Install 4 patches on 12 computers in Pilot, November security`; the ring name is taken from the server's subtitle.
- Toasts: `Approved. 4 patches will install on 12 computers now.` (or `when your window opens at HH:MM`), `Approved. 3 computers restart now with a 5-minute warning.` (singular forms handled), `Denied. Nothing was sent to 12 computers.`
- `AutonomousOpsDecisions` reads both kinds on one cadence and merges them by deadline; the count line, section sentence, Show more label and live region follow section 6; incident-only behavior is unchanged (the existing Decisions tests pass with their assertions untouched).

## Task Commits

TDD plan, both tasks with RED then GREEN.

1. **Task 1 RED** - `2b1a35ff3` (test): 26 card tests against a skeleton that renders nothing (25 failed on the planned assertions, the shadow-mode emptiness test passes)
2. **Task 1 GREEN** - `5e6a9b4dd` (feat): approvals.ts and the card; one test fixed (see deviations)
3. **Task 2 RED** - `9064185c4` (test): 15 section tests (11 failing on assertions, the rest pin unchanged behavior), plus the harness route
4. **Task 2 GREEN** - `68c2b26be` (feat): the merged list in AutonomousOpsDecisions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two test files routed authFetch without the new rollout read**
- **Found during:** Task 2 (RED)
- **Issue:** `_autonomousOpsDecisionsHarness.tsx` and `AutonomousOpsActivity.test.tsx` throw `unexpected request` for any path they do not know, so the section's new `rollout-cards` read would have failed every existing Decisions and Activity test.
- **Fix:** each routes `/api/autonomous-ops/rollout-cards` to an empty page by default (the harness also gains `rollouts` and `lineDecision` handlers and `rolloutCalls`, `lineCalls`). No assertion in `autonomousOpsDecisions.test.tsx`, `autonomousOpsDecisionsCards.test.tsx` or `AutonomousOpsActivity.test.tsx` changed.
- **Files modified:** src/__tests__/_autonomousOpsDecisionsHarness.tsx, src/__tests__/AutonomousOpsActivity.test.tsx
- **Commit:** 9064185c4

**2. [Rule 1 - Bug, in a test] The approve-all guard matched "Install"**
- **Found during:** Task 1 (GREEN)
- **Issue:** `queryByRole('button', { name: /all/i })` matched the `all` inside `Install`.
- **Fix:** `/\ball\b/i`. **Commit:** 5e6a9b4dd

**3. [Plan text vs server] Approve during a stop**
- The server sets `canApprove` false during a stop, but section 6 wants Approve disabled with the Paused helper. The card shows a disabled Approve when stopped and the caller can still deny. Never shown to a caller who cannot deny.

**4. [Plan text] Props**
- The plan lists props `card, stopped, shadow, onDecided`; the card also takes `now`, `tenantId` and `onStale` (deadline clock, platform staff's organization, and the 409 refetch the plan asks for).

**5. [Plan text] Paging**
- "Page 10 across both" is done per source: the initial and each Show more read up to 10 more of each kind that has more, then the lists are merged. A later Show more can therefore place a newly read card ahead of one already shown.

**6. [Plan text] Exported constants**
- `AutonomousOpsIncidentCard.tsx` is not in this plan's files, so DEADLINE_CHIP / MUTED / TEXT_BUTTON (not exported there) are small local copies; `formatExpires`, `StateChip`, the buttons and `plural`/`plain` are imported.

**Total deviations:** 6 (1 blocking, 1 test bug, 4 plan-text notes). **Impact:** none on the plan's truths.

## Issues Encountered

- Task 1 was written implementation-first in a draft; to keep the RED honest the draft was parked, the tests were run against a render-nothing skeleton (assertion failures, no import or syntax errors), and the RED was committed before the real component went back in. The `check tdd-red-evidence` classifier was not run (plan is `type: execute`).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-84-46: Approve and Deny render only from the server's `canApprove` / `canDeny` (plus the disabled stop case above); the route re-checks control, session and stop. T-84-47: the Why, What happens (window timing, 5-minute warning, unsaved-work loss) and target are printed on the line before the click. There is no approve-all; one click is one line of one ring.

## User Setup Required

None. Nothing was restarted, published or pushed; `dist-new` was rebuilt by `npm run build` only. The merged section shows rollout cards once the UI is published (backend routes of 84-10 load on the next restart).

## Next Phase Readiness

- DEV-1 stays pending the user's review with the other UI-SPEC deviations (84-21 hands them over).
- 84-14's `Review in Needs your decision` link targets `approval-rollout-{rolloutId}-{ring}`, the id this card carries.

## Verification

- `npx vitest run src/__tests__/RolloutApprovalCard.test.tsx` 41 passed; with `autonomousOpsDecisions`, `autonomousOpsDecisionsCards`, `AutonomousOpsActivity`: 125 passed; every `AutonomousOps*`, `autonomousOps*`, `PatchRollout*`, `rolloutCopy` and `autonomousOpsCopy` test file: 19 files, 501 passed.
- `npx tsc --noEmit` clean, `npx eslint` on the changed files `--max-warnings 0` clean, `npm run build` succeeded (dist-new, not published).
- Acceptance: `rollout-lines` in approvals.ts 3; `RolloutApprovalCard` in AutonomousOpsDecisions.tsx 2; RolloutApprovalCard.tsx 305 lines, AutonomousOpsDecisions.tsx 351 lines.

## TDD Gate Compliance

RED `2b1a35ff3` / GREEN `5e6a9b4dd` (Task 1); RED `9064185c4` / GREEN `68c2b26be` (Task 2). No REFACTOR commit.

## Self-Check: PASSED

- Created files exist: approvals.ts, RolloutApprovalCard.tsx, RolloutApprovalCard.test.tsx; commits 2b1a35ff3, 5e6a9b4dd, 9064185c4, 68c2b26be are ancestors of HEAD.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
