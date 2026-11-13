---
phase: 86-activity-reporting-hardening-live-validation
plan: 15
subsystem: autonomous-ops-golive-ui
tags: [go-live, shadow-mode, test-organization, dialogs, copy-gate, vitest, react, autonomous-ops]
status: complete

requires:
  - phase: 86-12
    provides: the Going live card, its organizations table, the Lift and Turn-back-on dialogs and the goLiveCopy.ts source of strings
  - phase: 86-14
    provides: POST and DELETE /golive/test-organization, testOrganization on GET /golive and on each row, the 409 and 422 sentences
provides:
  - markTestOrganization and clearTestOrganization in services/autonomousOpsGoLive.ts, plus the testOrganization payload types
  - MarkTestOrgDialog (typed exact name) and ClearTestOrgDialog in components/autonomousOpsGoLive/TestOrgDialogs.tsx
  - Test organization label, Use as test organization and Clear test mark actions on the organization rows
  - Lift dialog note for the test organization, replacing the evidence line that claims five recorded checks
affects: [86-13]

actuals:
  tokens: 16000
  tasks: 2
  commits: 4
plan_head_before: 43be0af1511063da1f31f48145cee4490147773a
plan_head_after: 6da9c5219fcc374eab8b265e1a09aaeda820521f

tech-stack:
  added: []
  patterns:
    - the card renders the server's testOrganization, per-row flag and canLift; it never decides who may be marked or lifted
    - a 4xx from mark or clear is shown as the server's own sentence in a role=alert block; 403 and 5xx use fixed sentences
    - a 409 on mark or clear also refetches, because the server's state (another organization marked, shadow flag) may differ from the screen
    - the typed-name dialog shell (title wrapper, ErrorBlock, FIELD classes, one request per click, Esc ignored while pending) copied from ShadowDialogs.tsx

key-files:
  created:
    - components/autonomousOpsGoLive/TestOrgDialogs.tsx
    - src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx
  modified:
    - services/autonomousOpsGoLive.ts
    - components/autonomousOpsGoLive/goLiveCopy.ts
    - components/autonomousOpsGoLive/GoLiveOrganizations.tsx
    - components/autonomousOpsGoLive/GoLiveCard.tsx
    - components/autonomousOpsGoLive/ShadowDialogs.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "For the test organization the Lift dialog shows the exemption note in place of the evidence line, because that line says 'All 5 go-live checks are recorded' and a day count, which would be false for an organization lifted without them; every other organization keeps the unchanged evidence line."
  - "Use as test organization is offered on every listed row while nothing is marked (the platform organization is never listed by the server), regardless of the row's shadow flag; the marked row is the top-level testOrganization id or the per-row flag, so either signal alone shows the label."
  - "The typed name is sent trimmed; the server compares after trimming too."

requirements-completed: [GATE-09]

coverage:
  - id: D1
    description: "With no test organization marked, every organization row offers Use as test organization; with one marked only that row shows the Test organization text label and Clear test mark, and no row offers marking; the server's canLift still drives Lift shadow mode"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx#marking offers, with no test organization marked"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx#a marked test organization"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Mark dialog explains the exemption, keeps the confirm disabled until the exact name is typed, marks once with Marking..., closes and reloads on success, and shows the server's 409, 422 and 404 sentences in an alert; hostile names and sentences render as text"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx#the Mark dialog"
        status: pass
    human_judgment: false
  - id: D3
    description: "Clear test mark is disabled with the visible reason 'Turn shadow mode back on first.' (aria-describedby) while the row's shadow flag is off; when enabled its dialog clears once, reloads on success and shows the server's 409 sentence"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx#a marked test organization"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx#the Clear test mark dialog"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Lift dialog for the test organization states the checks and the seven days are not required and the lift is recorded as a test-organization lift, above the unchanged typed-name confirmation; other organizations see no note"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx#the Lift dialog for the test organization"
        status: pass
    human_judgment: false
  - id: D5
    description: "TestOrgDialogs.tsx and all new strings pass the ACTV-08 copy gate on both sides"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "The marked-row layout (label beside a wrapping name, two stacked actions with the amber reason line) reads well at 320px and in light and dark, and the flow works against the live server"
    requirement: GATE-09
    verification: []
    human_judgment: true
    rationale: "Layout and the live walk (mark, lift, turn shadow back on, clear) are visual and operator judgments; nothing was published, restarted or run against the live server, and no real tenant was marked or lifted."

duration: ~15min
completed: 2026-11-13
---

# Phase 86 Plan 15: Going live card, test organization Summary

**A Super Admin can mark one organization as the go-live test organization by typing its exact name, see it labelled as text on the Going live card, lift it early as the server allows with a Lift dialog that states the exemption, and clear the mark once shadow mode is back on, with the server deciding every outcome.**

## What was built

- **`services/autonomousOpsGoLive.ts`:** `markTestOrganization(tenantId, confirmName)` (POST) and `clearTestOrganization(tenantId)` (DELETE with `?tenantId=`), both through the module's `authFetch` and `failure()` so status and the server's detail are kept. `GoLiveOverview.testOrganization` and `GoLiveOrganization.testOrganization` are optional so older payloads still parse.
- **`TestOrgDialogs.tsx` (160 lines):** `MarkTestOrgDialog` (typed name focused first, exact match after trimming, `Marking...`, Esc and Cancel ignored while pending, one request per click) and `ClearTestOrgDialog` (one confirm, `Keep test mark` focused first, `Clearing...`). A 4xx shows the server sentence verbatim; 403 and 5xx use fixed sentences; a 409 also refetches. All text is React text.
- **`GoLiveOrganizations.tsx` (243 lines):** `OrganizationName` carries the `Test organization` chip (text plus icon, never colour alone); the action cell now stacks `ShadowAction` (the 86-12 Lift or Turn-back-on logic, unchanged) and `TestOrgAction` (Use as test organization, or Clear test mark with its disabled reason referenced by `aria-describedby`). No row offers marking while any row or the top-level field is marked.
- **`ShadowDialogs.tsx`:** for a row with `testOrganization` the evidence block is replaced by the note `Test organization: the five checks and the seven days are not required. The lift is recorded as a test-organization lift.` above the unchanged typed-name field.
- **`goLiveCopy.ts` (187 lines):** every new string; the copy-gate lists name `TestOrgDialogs.tsx` and the frontend file-count pin is 25.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | RED | bef74ed75 | test(86-15): add failing tests for the go-live test organization mark, label and clear |
| 1 | GREEN | c28996228 | feat(86-15): mark, label and clear the go-live test organization on the Going live card |
| 2 | RED | 9d20a3cbd | test(86-15): add failing tests for the Lift dialog note of the test organization |
| 2 | GREEN | 6da9c5219 | feat(86-15): Lift dialog states the test-organization exemption; copy gate lists TestOrgDialogs |

## TDD Gate Compliance

RED then GREEN commits exist for both tasks, in order; no REFACTOR commit.

- **Task 1 RED:** 17 failed, 1 passed. Every failure was at the first assertion for the planned behavior (no `Use as test organization` button, no label, no dialog). The one pass pins existing behavior (the server's `canLift` still enables Lift on the marked row) and must stay true in GREEN. The service module is mocked in the test, so no stub was needed to avoid import errors.
- **Task 2 RED:** 2 failed, 3 passed. The failures are the note being absent and the false "All 5 go-live checks are recorded" line still shown; the 3 passes pin behavior GREEN must keep (typed-name confirmation, refused lift sentence, other organizations unchanged).
- **Semantic assessment:** both REDs failed on the planned assertions for the intended reason, not on import, syntax or fixture faults. `gsd_run check tdd-red-evidence` was not run (vitest output was not captured as a TAP report), the same process gap noted in 86-07 and 86-12.

## Verification

- `npx vitest run src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx src/__tests__/autonomousOpsGoLive.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: 87 passed, 0 skipped. The 86-12 test file passes unchanged.
- `backend/venv/bin/python -m pytest -q -rs tests/test_autonomous_ops_copy.py` (private mongod 27998 env set): 33 passed, 0 skipped.
- Full `npx vitest run src/__tests__`: 130 files, 2180 tests passed (neither known flake fired).
- `npm run build`: built (dist-new only; nothing published). `npx tsc --noEmit` and `npx eslint` on the touched files: clean.
- Acceptance greps: `test-organization` in the service 4 (at least 2); `dangerouslySetInnerHTML` 0 in every component; every file under 500 lines (largest 243); `TestOrgDialogs` listed once in the JSON list, the pytest list and the vitest list; no user-visible literal in `TestOrgDialogs.tsx` outside `goLiveCopy.ts` imports.

## Deviations from Plan

**1. [Rule 1 - Bug] Lift dialog evidence line replaced for the test organization**
- **Found during:** Task 2
- **Issue:** the 86-12 evidence block reads `{n} days of shadow records. {m} actions would have been done. All 5 go-live checks are recorded.` For the test organization the checks may not be recorded and there may be no shadow records, so the line would state something untrue directly beside the note.
- **Fix:** for `testOrganization: true` the note takes the evidence block's place (same position, above the typed name); other organizations render the unchanged evidence line (test pinned).
- **Files modified:** components/autonomousOpsGoLive/ShadowDialogs.tsx
- **Commit:** 6da9c5219

**2. [Rule 3 - Blocking] GoLiveCard.tsx edited (not in the plan's files_modified)**
- **Issue:** the card must pass the server's top-level `testOrganization` to the organizations section.
- **Fix:** one prop added (`testOrganization={data.testOrganization ?? null}`).
- **Commit:** c28996228

**3. [Plan adaptation] Copy-gate registration of a file inside an already-listed directory**
- `components/autonomousOpsGoLive` was already a gate directory (86-12), so `TestOrgDialogs.tsx` was scanned the moment it existed. As in 86-14, it is also listed explicitly once in each of the three lists because the acceptance criterion asks for it; the vitest file-count pin moved 24 to 25.
- **Commit:** 6da9c5219

**4. [Rule 2 - Missing critical] Strings the plan did not give**
- Cancel and Keep test mark buttons, Marking... and Clearing..., a success toast for mark and for clear, and fixed 403 and network-failure sentences (a failed write must always say something). All in `goLiveCopy.ts`, covered by the copy gate.
- **Commit:** c28996228

**Total deviations:** 1 bug fix (Rule 1), 1 blocking edit (Rule 3), 1 adaptation, 1 added copy (Rule 2). **Impact:** none on D-23 behavior.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model: T-86-15-01 mitigated (the card renders `testOrganization`, the per-row flag, `canLift` and the server's refusal sentences; no client-side gate logic), T-86-15-02 mitigated (typed exact-name confirmation, warning text, visible label; the audit event is 86-14's), T-86-15-03 mitigated (React text only, hostile name and sentence asserted to render as text, `dangerouslySetInnerHTML` count 0). No new endpoint, auth path or file access.

## Issues Encountered

None. Nothing was run against 127.0.0.1:27017; the UI was not published, no service was restarted, nothing was pushed, and no real tenant was marked or lifted.

## Next Phase Readiness

The Going live card now shows and sets the D-23 mark, so the runbook's "set through the API route" note from 86-14 is out of date once the UI is published (publishing stays the user's step). Ready for 86-13.

## Self-Check: PASSED

Created files exist (`components/autonomousOpsGoLive/TestOrgDialogs.tsx`, `src/__tests__/autonomousOpsGoLiveTestOrg.test.tsx`); commits bef74ed75, c28996228, 9d20a3cbd and 6da9c5219 are on HEAD; `git rev-list --count 43be0af15..HEAD` is 4.
