---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 10
subsystem: ui
tags: [react, typescript, autonomous-ops, stop-switch, banner, status-card, copy-check, vitest, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-07)
    provides: typed client, shared status poller, screen shell with the status-card slot
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-09)
    provides: POST stop/resume routes (tenant and platform), canResume/canResumePlatform flags, masked by values
provides:
  - "pressStop, resumeStop, pressPlatformStop, resumePlatformStop in services/autonomousOpsApi.ts; AutonomousOpsApiError now carries `by` (409 body)"
  - "AutonomousOpsStopBanner: app-wide amber role=status banner above the Header, non-dismissible, platform first"
  - "AutonomousOpsStatusCard: four-cell readout, four notices, platform-scope readout, Stop / Resume / Stop all organizations / Resume all organizations, loading and error states"
  - "AutonomousOpsStopDialog: Stop and Resume dialogs for tenant and platform scope"
  - "shared/autonomous-ops-banned-terms.json plus pytest and vitest copy checks (ACTV-08)"
affects: [81-verification, 82, 83, 86]

actuals:
  tokens: 26000
  tasks: 3
  commits: 5

plan_head_before: d32bf0bb5d9ad8da56c04500547405733f0b53ae
plan_head_after: af6ade2bcd80d528424b4ebc0b35de6da528593d
commits: 5

tech-stack:
  added: []
  patterns:
    - "Authority from the server: Resume is drawn only from status.canResume / canResumePlatform and every stop name is the server's `by`; permission checks only decide which controls to draw"
    - "One rules file (shared/autonomous-ops-banned-terms.json) applied line by line by Python re and JavaScript RegExp, with an explicit scanned-file list that must exist and negative controls per rule"
    - "Dialogs mount only while open (state resets on open); an inFlight ref makes repeated clicks send one request"

key-files:
  created:
    - components/AutonomousOpsStopBanner.tsx
    - components/AutonomousOpsStatusCard.tsx
    - components/AutonomousOpsStopDialog.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts
    - src/__tests__/AutonomousOpsStopBanner.test.tsx
    - src/__tests__/AutonomousOpsStatusCard.test.tsx
    - src/__tests__/AutonomousOpsStatusCardStates.test.tsx
    - src/__tests__/_autonomousOpsCardHarness.tsx
  modified:
    - services/autonomousOpsApi.ts
    - components/AutonomousOpsActivity.tsx
    - App.tsx
    - backend/autonomous_ops/messages.py
    - src/__tests__/AutonomousOpsActivity.test.tsx

key-decisions:
  - "Any active stop (organization or platform) counts as stopped for the controls row: Stop is hidden, Resume shows only when the server says canResume, otherwise one helper line says who can resume"
  - "The helper line is chosen from the stop's tier and the viewer's manage permission, for wording only: a tenant stop and no manage access reads 'administrator with manage access'; a tenant stop with manage access that the server still refuses, or a platform stop, reads 'platform administrator'"
  - "Stop is drawn when the viewer holds control:autonomous_ops, is not Platform Support and the server's canStop is true; the platform row needs control:platform_autonomous_ops and canStopPlatform; Resume all organizations needs canResumePlatform"
  - "On a status load failure the card keeps Stop available to holders and shows a disabled Resume to manage holders (UI-SPEC S2); with older data in hand a failed poll is silent and the last status stays"
  - "The ACTV-08 pytest side scans the backend files and the autonomousOps catalogue label, the vitest side the frontend files; both hard-code the same expected file list and fail on any drift from the JSON"

patterns-established:
  - "Test harness module with an underscore prefix (src/__tests__/_autonomousOpsCardHarness.tsx) shared by two test files; each test file registers the vi.mock calls"

requirements-completed: [ACTV-08, GATE-06, ACTV-01]

coverage:
  - id: D1
    description: "Pressing Stop takes one confirmation (optional reason, Ctrl/Cmd+Enter, pending label, one request); afterwards the banner shows for every viewer on every screen"
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStopBanner.test.tsx#one confirmation presses Stop, closes the dialog, toasts, and the banner appears"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStatusCard.test.tsx#keeps the dialog open with the typed reason and the server message on failure"
        status: pass
    human_judgment: false
  - id: D2
    description: "The stop banner is non-dismissible, amber role=status, platform above organization, hidden on the Autonomous Ops screen's View details, absent for users without the permission, silent on poll failures"
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStopBanner.test.tsx#cannot be dismissed: the only button inside the banner is View details"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStopBanner.test.tsx#renders no banner when the first load fails, and keeps the last banner when a later poll fails"
        status: pass
    human_judgment: false
  - id: D3
    description: "Resume needs a typed reason (whitespace is empty, no keyboard shortcut), is drawn only from the server's canResume, and a 403 or other failure is handled as specified; Platform Support and the platform organization get no controls"
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStatusCard.test.tsx#shows who stopped it, requires a typed reason and never submits from the keyboard"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStatusCard.test.tsx#gives Platform Support no controls even if the permission list names them"
        status: pass
    human_judgment: false
  - id: D4
    description: "Status card readout, the breaker / unreadable / platform-organization / not-ticked notices, platform-scope readout, loading skeleton and error block"
    requirement: ACTV-01
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStatusCard.test.tsx#status card readout"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStatusCardStates.test.tsx#card states"
        status: pass
    human_judgment: false
  - id: D5
    description: "Super Admin platform-wide Stop all organizations / Resume all organizations with typed reason, in tenant scope and platform scope"
    requirement: GATE-06
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsStatusCardStates.test.tsx#platform-wide stop (Super Admin)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Banned terms (ACTV-08) fail both test suites; every listed file must exist; each rule has negative controls"
    requirement: ACTV-08
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py (19 tests)"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts (18 tests)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The banner, card and dialogs look right in light and dark themes, and Stop / Resume work against the live backend after a UI publish"
    verification: []
    human_judgment: true
    rationale: "jsdom tests do not assert contrast, layout or the live :5000 API; publishing the UI and restarting the backend are the user's steps"

duration: 14min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 10: Autonomous Ops status card, stop banner and copy check Summary

**Status card with Stop / Resume dialogs (tenant and Super Admin platform-wide), a non-dismissible app-wide stop banner fed by the shared poller, and one banned-terms rules file enforced by both pytest and vitest**

## Performance

- **Duration:** 14 min
- **Started:** 2026-10-26T13:14:45Z
- **Completed:** 2026-10-26T13:29Z
- **Tasks:** 3 (Task 1 tracer, Tasks 2-3 auto; all TDD)
- **Files modified:** 15 (10 created, 5 modified)

## Accomplishments

- Tracer: an approver presses Stop on the card (one confirmation, optional reason, Ctrl/Cmd+Enter), the dialog closes, a toast shows and the shared poller refetches so the amber banner appears above the Header on every screen. Tracer verified end to end (46 tests and build green) before expansion.
- Full card: four-cell readout (level, maximum, shadow with deployment/organization source, stop), the four conditional notices, a platform-scope readout (platform stop and "{n} organizations stopped"), skeleton and error states, Resume with a typed reason, and the Super Admin platform-wide row.
- ACTV-08: `shared/autonomous-ops-banned-terms.json` (five rules, eleven-file list, catalogue view) read by `backend/tests/test_autonomous_ops_copy.py` (19 tests) and `src/__tests__/autonomousOpsCopy.test.ts` (18 tests), each with negative controls per rule and a missing-file failure.

## Task Commits

1. **Task 1 (tracer): Stop on the card + app-wide banner** - `128b41367` (test, red), `c0400e71f` (feat)
2. **Task 2: full status card, Resume, platform-wide controls, states** - `1e25ae824` (test, red: 25 of 31 failing), `02b190b68` (feat)
3. **Task 3: ACTV-08 copy check** - `af6ade2bc` (test + rules file + one copy fix; the rules were exercised red by scanning the previous messages.py, which flagged five lines)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

## Scanned file list (ACTV-08)

`backend/autonomous_ops/messages.py`, `backend/autonomous_ops/views.py`, `backend/autonomous_ops_endpoints.py`, `backend/autonomous_ops_platform_endpoints.py` (pytest side, plus the `autonomousOps` label in `shared/catalogue-access.json`); `services/autonomousOpsApi.ts`, `contexts/AutonomousOpsStatusContext.tsx`, `components/AutonomousOpsActivity.tsx`, `components/AutonomousOpsActivityList.tsx`, `components/AutonomousOpsStatusCard.tsx`, `components/AutonomousOpsStopDialog.tsx`, `components/AutonomousOpsStopBanner.tsx` (vitest side). Never `.planning/**`, the Windows Autopilot screen, `backend/autopilot_service.py` or `components/AutonomousOpsLog.tsx`.

## Files Created/Modified

- `services/autonomousOpsApi.ts` - four POST functions; error class gains `by`
- `components/AutonomousOpsStopBanner.tsx` - banner plus shared date and stop-sentence helpers
- `components/AutonomousOpsStatusCard.tsx` - readout, notices, controls, platform row, states (307 lines)
- `components/AutonomousOpsStopDialog.tsx` - Stop and Resume dialogs, tenant and platform (233 lines)
- `components/AutonomousOpsActivity.tsx` - mounts the card in the status slot
- `App.tsx` - banner directly above `<Header>` (2 added lines only; the user's reset-password and settings hunks stay unstaged)
- `shared/autonomous-ops-banned-terms.json`, `backend/tests/test_autonomous_ops_copy.py`, `src/__tests__/autonomousOpsCopy.test.ts` - the copy check
- `src/__tests__/AutonomousOpsStopBanner.test.tsx` (12), `AutonomousOpsStatusCard.test.tsx` (20), `AutonomousOpsStatusCardStates.test.tsx` (11, same card), `_autonomousOpsCardHarness.tsx` - fixtures shared by the two card modules

## Decisions Made

See `key-decisions` above. In short: any active stop counts as stopped for the controls row; wording of the "who can resume" line follows the stop's tier and the viewer's manage permission while authority stays with the server flags; platform row and platform Resume come from `canStopPlatform` / `canResumePlatform`; the pytest and vitest sides hard-code the same file list so neither can drift from the JSON.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Banned terms spelled out in the messages.py docstring**
- **Found during:** Task 3
- **Issue:** The `messages.py` module docstring listed the banned terms to explain ACTV-08, so the line-based scan flagged it (five hits, confirmed against `HEAD`). The plan says to fix the copy, not the rule.
- **Fix:** Reworded the docstring to point at the rules file without naming the terms.
- **Files modified:** `backend/autonomous_ops/messages.py`
- **Verification:** `test_backend_files_pass_every_rule`; endpoints, registry and structural suites still pass (57 passed)
- **Committed in:** `af6ade2bc`

**2. [Rule 1 - Bug] 81-07 list-loading test picked up the card's aria-busy**
- **Found during:** Task 2
- **Issue:** `AutonomousOpsActivity.test.tsx` selected the first `[aria-busy="true"]`; the status card (required by the plan to be `aria-busy` while loading) now comes first.
- **Fix:** The test finds the busy container that holds the skeleton rows (`closest`).
- **Files modified:** `src/__tests__/AutonomousOpsActivity.test.tsx`
- **Committed in:** `02b190b68`

### CLAUDE.md / plan-shape adjustments

**3. [CLAUDE.md: files under 500 lines] Card tests split**
- The plan names one `AutonomousOpsStatusCard.test.tsx`; it reached 535 lines. Split into `AutonomousOpsStatusCard.test.tsx` (readout, controls, dialogs), `AutonomousOpsStatusCardStates.test.tsx` (platform-wide controls, card states) and an underscore-prefixed fixtures module. Each file registers its own `vi.mock` calls. (`AutonomousOpsActivity.test.tsx` from 81-07 is 669 lines and was left as is.)

**4. [Plan wording] Catalogue label is scanned on the pytest side only**
- The plan's truths say both sides scan the same file list; its behavior section says pytest also scans the label. Both sides hard-code and compare the full list, but only pytest can read the label alongside the backend files. The label is "Autonomous Ops" and passes.

**Total deviations:** 2 auto-fixed (Rule 1), 2 plan-shape adjustments. **Impact:** none on scope.

## Issues Encountered

- `npm run build` is vite build and runs no tests (A-81-BUILD-GATE): the ACTV-08 gate is `npx vitest run src/__tests__` plus the backend pytest suite.
- Known pre-existing reds not touched: `test_catalogue_manifest.py::test_sidebar_and_app_agree_with_manifest` and `test_catalogue_route_parity.py::test_ledger_ratchets` (not run in full here; only this plan's pytest modules and the autonomous ops suites above).
- The full backend phase gate (about 11 minutes, `backend/tests`) was not run here; it is the phase-level step before `/gsd-verify-work`.

## Known Stubs

None. The 81-07 empty status slot is now filled by the card.

## Threat Flags

None. No new endpoint or trust boundary: T-81-42 (Resume drawn from server flags, tested), T-81-43 (no dismiss control, tested), T-81-44 (React text only; `dangerouslySetInnerHTML` count is 0 in the three new components; `maxLength` 500), T-81-45 (server `by` rendered as delivered).

## User Setup Required

None for configuration. Steps left for the user (not done here by rule):

1. Restart `omni-backend.service` so the 81-09 routers are live (the backend runs from this checkout without reload).
2. Publish the UI build to `/var/www/omni-agent` (this plan did not touch `/var/www`).
3. Manual checks after publish: as a Tenant Admin press Stop with and without a reason, confirm the amber banner on another screen and that it cannot be dismissed, then resume with a reason; as a Security Analyst confirm Stop works and the "manage access" line replaces Resume; as a Super Admin use Stop all organizations / Resume all organizations and confirm a tenant user sees "Platform administrator" as the name; as Platform Support confirm the screen is read-only; check the banner, card and dialogs in light and dark themes at 1280 px and below (contrast, wrapping under 640 px).

## Next Phase Readiness

- Plan 81-10 is the last plan of Phase 81. Remaining phase steps: the full backend gate, then `/gsd-verify-work 81`.
- Level, maximum level, shadow lift and never-touch editing stay API-only (D-22); Phase 83 adds approve / deny / undo row actions.

## Verification Results

- `npx vitest run src/__tests__`: 63 files, 613 passed (was 552 before this plan)
- `npm run build`: built, no `error TS`; `tsc --noEmit` reports nothing for the new or changed files
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider`: 19 passed
- Related backend modules (copy, endpoints, registry, structural): 57 passed
- Acceptance: banner usage line 1964 before `<Header` line 1965 in `App.tsx`; staged `App.tsx` diff held only the import and the banner line; 4 POST functions exported; `Stop all organizations` / `Resume all organizations` present in the card; `canResume` count 6; no `truncate`, `font-medium`, `font-bold` or `dangerouslySetInnerHTML` in the three components; rules file passes the plan's python check; both copy tests reference the JSON path

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*

## Self-Check: PASSED

- Files exist: components/AutonomousOpsStopBanner.tsx, components/AutonomousOpsStatusCard.tsx, components/AutonomousOpsStopDialog.tsx, shared/autonomous-ops-banned-terms.json, backend/tests/test_autonomous_ops_copy.py, src/__tests__/autonomousOpsCopy.test.ts, src/__tests__/AutonomousOpsStopBanner.test.tsx, src/__tests__/AutonomousOpsStatusCard.test.tsx
- Commits present: 128b41367, c0400e71f, 1e25ae824, 02b190b68, af6ade2bc
