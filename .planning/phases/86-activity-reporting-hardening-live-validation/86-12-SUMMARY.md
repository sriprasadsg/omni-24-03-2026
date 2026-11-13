---
phase: 86-activity-reporting-hardening-live-validation
plan: 12
subsystem: autonomous-ops-golive-ui
tags: [go-live, shadow-mode, platform-scope, dialogs, copy-gate, vitest, react, autonomous-ops]
status: complete

requires:
  - phase: 86-07
    provides: GET /api/platform/autonomous-ops/golive, POST /golive/checks/{id}, the server lift gate (409 {detail, reasons}) on PUT /tenants/{id}/shadow
  - phase: 86-10
    provides: docs/autonomous-ops-go-live.md, whose five Summary lines are the check descriptions
  - phase: 86-11
    provides: EmptyStateCard in its own file, the screen's platform-scope mount points
provides:
  - services/autonomousOpsGoLive.ts (GoLiveCheck, GoLiveReason, GoLiveOrganization, GoLiveOverview, fetchGoLive, recordGoLiveCheck, setOrganizationShadow)
  - Going live card for a Super Admin in platform scope (collapsed summary, intro, five checks with an inline note form)
  - Organizations table (stacked cards below lg) with the server's gate reasons, Lift shadow mode and Turn shadow mode back on dialogs
  - copy gate (ACTV-08) coverage of components/autonomousOpsGoLive and services/autonomousOpsGoLive.ts on both sides
affects: [86-13]

actuals:
  tokens: 21590
  tasks: 2
  commits: 4
plan_head_before: adff7ea17dfa5b5049b500204bd1672a68d4014f
plan_head_after: e3a3f14b32ad033d0762dcccdeeb5fdd745ddc36

tech-stack:
  added: []
  patterns:
    - the lift-allowed decision is read from the server's canLift and reasons, never recomputed in the browser
    - a refused lift (409) shows the server sentence, keeps the typed name and refetches the table
    - one button element for Record this check and Record again so focus survives the row changing after a record
    - organization name drawn in one small component (OrganizationName) so a later test-organization label has one place to go

key-files:
  created:
    - services/autonomousOpsGoLive.ts
    - components/autonomousOpsGoLive/goLiveCopy.ts
    - components/autonomousOpsGoLive/GoLiveCard.tsx
    - components/autonomousOpsGoLive/GoLiveChecklist.tsx
    - components/autonomousOpsGoLive/GoLiveOrganizations.tsx
    - components/autonomousOpsGoLive/ShadowDialogs.tsx
    - src/__tests__/autonomousOpsGoLive.test.tsx
  modified:
    - components/AutonomousOpsActivity.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The card and every button take their gate from the server: Lift shadow mode is disabled exactly when canLift is false, and the dialog still shows a 409 refusal and refetches."
  - "A 4xx record error shows the server message in the planned sentence; a 5xx or a network failure shows the fallback sentence, so a generic server text never reads as the cause."
  - "The Modal title row truncates, so both dialogs pass a block span with whitespace-normal break-words to let a long organization name wrap."
  - "A refetch that fails keeps the data already on screen; only a first load shows the red notice."

requirements-completed: [GATE-09]

coverage:
  - id: D1
    description: "A Super Admin in platform scope sees a collapsed Going live card between Response settings and Activity; tenant admins, a Super Admin viewing an organization and holders without the platform permission do not"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#where the Going live card appears"
        status: pass
    human_judgment: false
  - id: D2
    description: "The summary reads k of 5 checks recorded with the organizations out of shadow mode, All 5 checks recorded, or Go-live checks couldn't be loaded; loading shows skeletons"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#the collapsed summary"
        status: pass
    human_judgment: false
  - id: D3
    description: "Five checks show the document's Summary sentences; Record this check opens an inline form gated on 10 trimmed characters, posts once, shows Recording..., toasts and updates the row; 403, 4xx and 5xx errors keep the note; Esc asks before discarding"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#the expanded checklist"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#the inline record form"
        status: pass
    human_judgment: false
  - id: D4
    description: "The organizations table lists organizations sorted by name with the shadow chip, days observed, the dashed simulation count and the action; every unmet reason is an amber status line the disabled Lift button points to; stacked cards below lg; empty state; deployment-wide notice never blocks"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#the organizations table"
        status: pass
    human_judgment: false
  - id: D5
    description: "Lift shadow mode needs the exact organization name, writes once, ignores Esc while pending and shows the server's 409 reasons with a refetch; Turn shadow mode back on is never gated"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#the Lift shadow mode dialog"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsGoLive.test.tsx#the Turn shadow mode back on dialog"
        status: pass
    human_judgment: false
  - id: D6
    description: "components/autonomousOpsGoLive and services/autonomousOpsGoLive.ts are scanned by the copy gate on both sides"
    requirement: GATE-09
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py"
        status: pass
    human_judgment: false
  - id: D7
    description: "A 100-character organization name and a long dialog title wrap without overflowing at 320px (E11 and E12 long-text backstops), and the card looks right in light and dark"
    requirement: GATE-09
    verification: []
    human_judgment: true
    rationale: "Layout at 320px is a visual judgment; the code uses break-words and a wrapping title span, and nothing asserts the rendered width."

duration: ~21min
completed: 2026-11-13
---

# Phase 86 Plan 12: Going live card Summary

**A Super Admin records each of the five live go-live checks with a note, sees every organization's observation days, simulation count and the server's unmet lift reasons, and lifts or restores shadow mode through typed-name and one-confirm dialogs, with the gate itself still enforced only by the server.**

## What was built

- **`services/autonomousOpsGoLive.ts`:** types for the 86-07 payloads and three calls: `fetchGoLive`, `recordGoLiveCheck(id, note)` and `setOrganizationShadow(tenantId, shadow)`. Failures reuse `failure()` so the thrown error keeps the status and the server's plain detail (a 409 detail is the reason sentence).
- **`goLiveCopy.ts` (162 lines):** every fixed string, including the five check descriptions copied word for word from the `Summary:` lines of `docs/autonomous-ops-go-live.md` (check 3 says "timer", the document's wording, which corrects UI-SPEC R15's "service"), the reason sentences by code with singular and plural days, and the note helper reworded without a documentation-range address.
- **`GoLiveCard.tsx` (108 lines):** collapsed `.card p-6` with ClipboardCheckIcon, summary loaded on mount and refetched on expand and after every write, no polling; skeletons, red `HealthNotice` with Try again; a failed refetch keeps what is on screen. Renders the intro, the checklist and the organizations section.
- **`GoLiveChecklist.tsx` (206 lines):** the labelled `ol` of five rows with Recorded / Not recorded chips, the latest record in full (whitespace-pre-wrap break-words), and one inline form at a time: focus to the textarea, `{n}/500` counter, disabled Record check with its reason referenced by `aria-describedby`, one request per click, discard prompt on Esc or Close form, focus back to the row's button.
- **`GoLiveOrganizations.tsx` (184 lines):** table at lg and wider (caption, scoped headers, dashed simulation column), stacked cards with a `dl` below, blue deployment-wide notice, EmptyStateCard, and `OrganizationAction` which disables Lift exactly when the server says `canLift` is false and lists every reason as an amber `role="status"` line.
- **`ShadowDialogs.tsx` (158 lines):** `LiftShadowDialog` (evidence block, typed name with first focus, exact match after trimming, 409 sentence plus refetch, 403 sentence) and `RestoreShadowDialog` (Keep it lifted first focus, no gate). Both: `showClose={false}`, `closeOnBackdrop={false}`, Esc and cancel ignored while pending, one request per click, success toast and card refetch.
- **Wiring:** `AutonomousOpsActivity.tsx` renders `GoLiveCard` for platform scope plus `control:platform_autonomous_ops` right after `PlatformResponseSettings` (198 lines). The copy gate JSON and both EXPECTED lists gained the new file and directory, and the frontend file-count pin moved from 23 to 24.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | RED | d74c91e90 | test(86-12): add failing tests for the Going live card and the inline check form |
| 1 | GREEN | f77a1a017 | feat(86-12): Going live card with the five checks and the inline record form |
| 2 | RED | 0b146ca8d | test(86-12): add failing tests for the organizations table and the shadow dialogs |
| 2 | GREEN | e3a3f14b3 | feat(86-12): organizations table with gate reasons and the Lift and Turn-back-on dialogs |

## TDD Gate Compliance

RED then GREEN commits exist for both tasks, in order; no REFACTOR commit (nothing to clean up).

- **Task 1 RED:** the service and `GoLiveCard` were committed as stubs with the tests, so the target tests failed on their planned assertions (`Unable to find role="button" and name /Going live/`): 20 failed, 3 passed. The 3 that passed are the "not rendered" guards (tenant admin, Super Admin viewing an organization, no permission), which are true of a stub that renders nothing; they pin behaviour that GREEN must keep.
- **Task 2 RED:** 18 failed, 23 passed; every new test failed at its first assertion because no `Organizations` heading existed yet.
- **Semantic assessment:** both REDs failed on the planned assertions for the intended reason, not on import, syntax or fixture faults. `gsd_run check tdd-red-evidence` was not run: the vitest console output was not captured as a TAP report. This is a process gap, noted rather than hidden (same as 86-07).

## Verification

- `npx vitest run src/__tests__/autonomousOpsGoLive.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/autonomousOpsCopy.test.ts` (plus the export and stats suites): 136 passed after Task 1; goLive plus copy 64 passed after Task 2.
- Full `npx vitest run src/__tests__`: 129 files, 2157 tests passed (the Phase 85 `ServiceDeskKnowledgeGaps` flake did not fire).
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider` (private mongod env set): 33 passed.
- `npm run build`: built (writes dist-new only; nothing published).
- `npx eslint components/autonomousOpsGoLive services/autonomousOpsGoLive.ts`: clean.
- Acceptance greps: documentation-range addresses 0; all five Summary lines found in `goLiveCopy.ts` (1 each); copy-gate JSON 2; `GoLiveCard` in the screen 2; `dangerouslySetInnerHTML` 0 in all four components; `Type the organization name to confirm` 1; `aria-describedby` 1 and 2; `showClose={false}` 2; every file under 500 lines (largest 206; the screen 198).

## Deviations from Plan

**1. [Rule 1 - Bug] Copy-gate file-count pin updated**
- **Found during:** Task 1
- **Issue:** `src/__tests__/autonomousOpsCopy.test.ts` pins `FRONTEND_FILES` at 23; registering `services/autonomousOpsGoLive.ts` made it 24, failing the existing pin.
- **Fix:** the pin now reads 24 (the file was already in this plan's `files_modified`).
- **Commit:** f77a1a017

**2. [Rule 2 - Missing critical] Fallback sentences for unspecified failures**
- **Issue:** the UI-SPEC gives a lift error only for 409 and 403 and a turn-on error only with a server message. A network failure or a 5xx on the lift would otherwise show nothing.
- **Fix:** added `Couldn't lift shadow mode. Check your connection and try again.` and `Couldn't turn shadow mode back on. Check your connection and try again.`, and a neutral `Not ready to lift yet.` for a reason code the card does not know, so a disabled Lift never has no explanation.
- **Files modified:** components/autonomousOpsGoLive/goLiveCopy.ts, ShadowDialogs.tsx
- **Commit:** e3a3f14b3

**3. [Design addition] Local `useWideLayout` hook**
- The same hook lives privately in `StatsRuleTable.tsx` (86-11); this plan did not touch that file, so a small copy sits in `GoLiveOrganizations.tsx`. A later cleanup could export one.

**Total deviations:** 1 auto-fixed (Rule 1), 1 added (Rule 2), 1 design clarification. **Impact:** none on scope.

## Known Stubs

None.

## Threat Flags

None: T-86-29 is mitigated (React text only, `whitespace-pre-wrap break-words`, no `dangerouslySetInnerHTML`, hostile note, recorder and organization names are asserted to render as text) and T-86-30 is accepted as planned (the UI gate is advisory; the 409 path shows the server's reasons and refetches). No new endpoint, auth path or file access was added.

## Issues Encountered

- A first commit attempt that carried a `Co-Authored-By` trailer was refused by the harness; the project CLAUDE.md and the dispatch both forbid the trailer, so the commit was redone without it. Nothing was committed with a trailer.

## Next Phase Readiness

The follow-up that adds a Super Admin "test organization" exemption can hang its label on `OrganizationName` and its mark or clear action on `OrganizationAction`; both are small and the lift-allowed decision is already the server's. Nothing was restarted, published or pushed, and no tenant's shadow mode was lifted. Ready for 86-13.

## Self-Check: PASSED
