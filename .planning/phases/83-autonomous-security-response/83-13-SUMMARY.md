---
phase: 83-autonomous-security-response
plan: 13
subsystem: autonomous-ops-ui
tags: [autonomous-ops, settings, two-signal, block-length, watched-services, bulk, react, vitest]
status: complete

requires:
  - phase: 83-autonomous-security-response
    provides: "83-07 response-settings routes (tenant GET/PUT, platform GET and bulk PUT); 83-10 Activity screen pieces"
provides:
  - "AutonomousOpsResponseSettings (tenant panel), PlatformResponseSettings (Super Admin card), TurnOffRuleDialog, ApplyAllDialog"
  - "fetchResponseSettings, saveResponseSettings, fetchResponseSettingsDistribution, applyResponseSettingsToAll and their types"
  - "Panel rendered by AutonomousOpsActivity for manage holders in an organization, and the every-organization card in platform scope"
affects: [83-18, 83-19, 83-20]

actuals:
  tokens: 23700
  tasks: 2
  commits: 2
plan_head_before: a73ee1e529c69c5627aa0b9cf98f676e82e2a8ec
plan_head_after: a7ea408e155bf82a436d8d986c8b2793380d6a82

tech-stack:
  added: []
  patterns:
    - "Staged form: nothing is written until Save; the server's answer (or a refetch) resets the staged values"
    - "Loosening a safeguard asks first: single dialog for one organization, dialog plus required acknowledgement for all"
    - "Bulk retry: the dialog keeps the failed organization ids and the next click sends only those (onlyTenants)"

key-files:
  created:
    - components/AutonomousOpsResponseSettings.tsx
    - components/AutonomousOpsResponseSettingsDialogs.tsx
    - components/AutonomousOpsResponseSettingsPlatform.tsx
    - src/__tests__/autonomousOpsSettings.test.tsx
    - src/__tests__/autonomousOpsSettingsPlatform.test.tsx
  modified:
    - components/AutonomousOpsActivity.tsx
    - services/autonomousOpsApi.ts
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts
    - src/__tests__/AutonomousOpsActivity.test.tsx

key-decisions:
  - "The every-organization form lives in its own file (AutonomousOpsResponseSettingsPlatform.tsx): with it the settings file would pass 500 lines, and the plan's acceptance count of one role switch line in the settings file needs the platform form elsewhere."
  - "A block length of exactly 24 hours stays '24 hours'; a whole number of days above one day shows as days (48 -> 2 days). The UI-SPEC says 'days when a whole number of days' but also 'shows 24 hours' for the default, so the two are reconciled this way."
  - "The invalid block-length alert shows as soon as the value is invalid, not only on blur; Save is disabled either way."

requirements-completed: []

coverage:
  - id: D1
    description: "Collapsed card between status card and Activity for manage holders: summary line keeps the dormant-restart fact, no form in the DOM; hidden for no-manage, Platform Support and the platform organization"
    requirement: "ACTV-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettings.test.tsx#Response settings: collapsed summary and loading"
        status: pass
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettings.test.tsx#Response settings: who sees the panel"
        status: pass
  - id: D2
    description: "Staged form: switch with On/Off, block length number and unit (48 hours reads 2 days), watched services chips with the four validations and the 50 limit; nothing written until Save; Discard restores"
    requirement: "RESP-04"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettings.test.tsx#Response settings: the form"
        status: pass
  - id: D3
    description: "Turning the two-source rule off opens the confirmation (tenant name, record notice, Also saving line) before any write; Cancel writes nothing; Esc and Cancel ignored while pending; failure keeps it open; turning it on needs no dialog"
    requirement: "RESP-08"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettings.test.tsx#Response settings: turning the two-source rule off"
        status: pass
  - id: D4
    description: "States: load skeleton, load error with Try again, save error with fallback, 403 toast and close, restartAvailable false and unreadable blue blocks"
    requirement: "ACTV-02"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettings.test.tsx#Response settings: the form"
        status: pass
  - id: D5
    description: "Super Admin platform card: summary from the distribution, two groups behind checkboxes with No change, Apply disabled until a valid box is ticked, no watched services"
    requirement: "RESP-08"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettingsPlatform.test.tsx#Response settings for every organization: summary and form"
        status: pass
  - id: D6
    description: "Apply to every organization dialog: required acknowledgement only when the rule is turned off (first in focus, gates confirm); partial failure keeps it open and the retry sends only the failed ids; a second click with none failed closes with the cumulative toast; Esc blocked while pending; 403 closes"
    requirement: "RESP-08"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsSettingsPlatform.test.tsx#Apply to every organization? dialog"
        status: pass
  - id: D7
    description: "Both new component files and the platform form are on the three copy lists and pass the banned-terms gate"
    requirement: "ACTV-08"
    verification:
      - kind: unit
        ref: "src/__tests__/autonomousOpsCopy.test.ts"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_copy.py"
        status: pass
---

# Phase 83 Plan 13: Response settings panel Summary

**A tenant admin reads and stages the two-source switch, the block length and up to 50 watched services behind one Save, a loosening asks first, and a Super Admin applies the first two to every organization through a dialog that retries only the organizations that failed.**

## What was built

- `components/AutonomousOpsResponseSettings.tsx` (411 lines): the collapsed Response settings card (summary line, skeleton, load error with Try again), the staged form, the single role switch, the block length number and unit, the services list with chips, the footer (Save settings accent when dirty, Discard changes), and shared helpers the platform form reuses (`OnOffSwitch`, `BlockLengthControl`, `Group`, `splitHours`, `toHours`, `convertUnit`, `durationText`).
- `components/AutonomousOpsResponseSettingsDialogs.tsx` (150 lines): `TurnOffRuleDialog`, `ApplyAllDialog`, and the shared `plain`, `plural`, `ACCENT_BUTTON`.
- `components/AutonomousOpsResponseSettingsPlatform.tsx` (250 lines): `PlatformResponseSettings` (summary from the distribution, two checkbox-gated groups, retry state).
- `services/autonomousOpsApi.ts`: `ResponseSettings`, `fetchResponseSettings`, `saveResponseSettings`, `ResponseSettingsDistribution`, `fetchResponseSettingsDistribution`, `applyResponseSettingsToAll` (body carries `onlyTenants`).
- `components/AutonomousOpsActivity.tsx`: renders the tenant panel after the status card and before Activity when scope is a tenant, the viewer is not Platform Support, the status says the organization is not the platform one, and `hasPermission('manage:autonomous_ops')`; renders the platform card after Platform health when `control:platform_autonomous_ops` is held. The panel is keyed by organization so entering another one starts clean.

## Verification

- `npx vitest run src/__tests__/autonomousOpsSettings.test.tsx src/__tests__/autonomousOpsSettingsPlatform.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: 103 passed, exit 0.
- Whole `src/__tests__` directory: 74 files, 895 tests passed (run before the Task 2 commit and again with its files in place).
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py`: 27 passed.
- `npm run build`: built in 5.7 s, nothing printed as an error; output goes to git-ignored `dist-new`. `tsc --noEmit` printed no error for any file this plan touched.
- Acceptance greps: `role="switch"` count 1, `truncate` count 0 in all three components, `wc -l` 411 (below 500), `AutonomousOpsResponseSettings` count in the banned-terms JSON is 2 after Task 1 (3 after Task 2, which adds the platform file), `I understand this changes every organization.` count 1, `onlyTenants` count 2.
- Two mutation checks, both caught and restored: forcing `ruleOff = false` failed 7 settings tests; forcing the acknowledgement gate off failed the bulk loosening test.
- No cargo, no database, no live service was used. This plan is frontend only, so the cargo recipe and the private mongod were not needed.

## Honesty notes

- **RED runs were import errors only.** For both tasks I wrote the tests first and ran them: the only failure was `Failed to resolve import` for the component module that did not exist yet. After the code existed, all tests passed on the first run, so the mutation checks above are the evidence that the tests can fail.
- **Read in full:** 83-13-PLAN.md, 83-CONTEXT.md, 83-07-SUMMARY.md, 83-UI-SPEC.md lines 12-140 (design system, spacing, type, colour, placement, section 1) and 260-528 (sections 6-9, copywriting, UI considerations, accessibility, assumptions R1-R14, open items). **Not read:** UI-SPEC lines 141-259 (sections 2-5: incident cards, Activity Undo, row copy, suggestions in volume), 83-RESEARCH.md, 83-PATTERNS.md, 83-VALIDATION.md, 81-UI-SPEC.md and 82-UI-SPEC.md (relied on 83-UI-SPEC's statement that tokens and chip anatomy are inherited, and on the existing retention dialog and health chips as the code reference). `NotificationPreferencesDashboard.tsx` was read for the switch pattern at lines 110-140 only.
- **The human check was not run.** Light and dark at 640, 1024 and 1280 px, the real save of each setting and the control row appearing in Activity need the UI published, which is the user's step.

## Deviations from Plan

**1. [Rule 3 - size limit and acceptance count] Platform form in its own file.** The plan said to move it only if the settings file passed 450 lines; it was 406 before the platform form existed. With the platform form in the same file it would have been about 650 lines (over the 500 limit in CLAUDE.md) and would have carried a second `role="switch"` line, breaking the Task 1 acceptance count of 1. `PlatformResponseSettings` is therefore exported from `AutonomousOpsResponseSettingsPlatform.tsx`, not the settings file; the file is on all three copy lists. Commit a7ea408e1.

**2. [Rule 3 - size limit] New test file for Task 2.** `autonomousOpsSettings.test.tsx` reached 463 lines with Task 1 alone, so the Task 2 tests are in `src/__tests__/autonomousOpsSettingsPlatform.test.tsx` (344 lines).

**3. [Rule 1 - broke existing tests] `AutonomousOpsActivity.test.tsx` edited.** Its fixtures use `hasPermission: () => true` and throw on an unknown URL, so the new panel's settings request turned into a red alert that two existing tests (`Load more` failure and first-page error) tripped over. Its `routeFetch` now answers the tenant and platform response-settings routes (7 lines). `autonomousOpsCopy.test.ts` also had a hard-coded count of scanned frontend files (15), now 18. Neither file was in the plan's file list.

**4. Markup and wording choices inside the contract.**
- The header is `h2 > button` (the accordion pattern) instead of a button containing the h2: same accessible names, valid HTML.
- The block-length input is `type="number"` with `inputMode="numeric"`, as the UI-SPEC says; a non-whole value is rejected by the same rule as the server.
- Changing the unit converts the value where it can be exact (48 hours becomes 2 days and back).
- The inline block-length alert appears while the value is invalid, not only on blur.
- The summary line writes the length as "Blocks last 2 days" / "Blocks last 1 hour".

## User-visible sentences the UI-SPEC does not word

Please read these:

- Bulk dialog, every organization failed: `Couldn't change {k} of {n} organization(s): {server messages}. Try again.` (the spec words only the partial case, which ends `The others were changed. Try again to retry the rest.`). Several different server messages are joined with `; `.
- Bulk dialog request-level failure (the whole call refused): `Couldn't save response settings: {server message}. Try again.` with the connection fallback, reusing the settings-save sentences.
- Singular forms: `Settings applied to 1 organization.`, `1 organization will be changed.`, `Block length: 1 hour`, `on in 1 organization`.
- Dialog lines `Two-source rule: on` (the spec shows only the `off` line).
- Turn-off dialog when the status has no organization name: `... on its own for this organization.`
- Platform summary when there are no organizations: only `Two-source rule on in 0 organizations, off in 0`, with no block-length part.
- The platform checkboxes all read `Change this setting for every organization` (as the spec words them); each is tied to its group with `aria-describedby`.
- The services list has `aria-label="Watched services"` (not visible).

## Known Stubs

None. The Activity screen has no placeholder where `Needs your decision` goes (83-19): the panel is rendered directly before the Activity section, so 83-19 inserts its section between the status card and the panel (platform scope: no decision section).

## Cross-plan facts for the orchestrator

- `AutonomousOpsActivity.tsx` renders, tenant scope: status card, [83-19 decisions go here], Response settings, Activity; platform scope: status card, Platform health, Response settings for every organization, Activity.
- `AutonomousOpsActivity.test.tsx`'s `routeFetch` now answers `/api/autonomous-ops/response-settings` and `/api/platform/autonomous-ops/response-settings`; any further request the screen starts to make needs a handler there too, or the tests see an alert.
- `autonomousOpsCopy.test.ts` hard-codes the frontend file count (now 18): a plan adding a copy-list file must bump it.
- Exports other plans may reuse: from the dialogs file `ACCENT_BUTTON`, `plain`, `plural`; from the settings file `OnOffSwitch`, `Group`, `durationText`.
- The platform form never sends `watchedServices`; the server already refuses it (83-07).
- Requirements: RESP-04, RESP-08 and ACTV-02 stay unticked (`requirements-completed: []`): the agent side, the sweep and the decision cards finish them in later plans.

## Threat model

T-83-54 (loosening by accident): the tenant dialog opens before any write and the bulk dialog adds a required acknowledgement; both tested including the disabled confirm. T-83-55 (panel shown to a non-holder): hidden in the UI for no-manage, Platform Support, the platform organization and tenant roles on the platform card (tested); the server refuses regardless (83-07). No new endpoint, auth path or schema; no threat flags.

## Self-Check: PASSED

Files exist (the three components, both new test files, this summary), commits 4c9cf54b4 and a7ea408e1 are ancestors of HEAD, `commits: 2` was measured from the ledger file with base a73ee1e52. Neither commit contained a file with someone else's uncommitted hunks (all modified files were clean before the plan; checked with `git diff --stat` before staging and `git show --stat` after).
