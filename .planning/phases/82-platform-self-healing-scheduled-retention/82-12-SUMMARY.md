---
phase: 82-platform-self-healing-scheduled-retention
plan: 12
subsystem: ui
tags: [autonomous-ops, platform-health, watchdog, services, certificates, disk, on-call, test-alert, react, vitest]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-11 typed client (fetchPlatformHealth, requestTestAlert), HealthChip and ladderChip, consumePlatformHealthFocus; 82-08 GET /health document and POST /health/test-alert"
provides:
  - "AutonomousOpsPlatformHealth: the Platform health section (watchdog and services card, certificate, disk and on-call cards) between the status card and Activity for a control:platform_autonomous_ops holder in platform scope"
  - "CertificatesCard, DiskCard, OnCallCard and the useTestAlertNoAnswer hook (Send test alert state machine)"
  - "Shared health parts in AutonomousOpsHealthChips: HealthNotice, InstallChecklistLink, HealthCell, clockOrDash, HEALTH_SKELETON, HealthChip label override"
affects: [82-13 Activity list and retention card, 82-14 retention card and tenant notices]

requirements-completed: [HEAL-01, HEAL-02, HEAL-03, HEAL-04, HEAL-05]

actuals:
  tokens: 23700
  tasks: 3
  commits: 6

key-files:
  created:
    - components/AutonomousOpsPlatformHealth.tsx
    - components/AutonomousOpsHealthCards.tsx
    - src/__tests__/AutonomousOpsPlatformHealth.test.tsx
    - src/__tests__/AutonomousOpsHealthCards.test.tsx
    - src/__tests__/_platformHealthHarness.tsx
  modified:
    - components/AutonomousOpsActivity.tsx
    - components/AutonomousOpsHealthChips.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The section gets its own data hook (usePlatformHealth): one fetch on mount, a 30 s interval gated on tab visibility, window focus, and the page Refresh counter; a failed poll keeps the last document and only the Updated time (the last successful fetch, not the watchdog's report time) stops advancing"
  - "A test alert answer applied from the POST response bumps a generation counter so an older in-flight poll cannot overwrite it; the next 5 s poll then confirms it from the server"
  - "The 90 s no-answer clock starts at the earlier of the server requestedAt and the moment this browser first saw the test (clamps server clock skew, still fires at once on a reload long after the request)"
  - "Shared small parts (notice block, install checklist link, readout cell, clock) live in AutonomousOpsHealthChips so the section and the cards import them without a cycle"
  - "A checklist url becomes a link only when it is https or resolves to this origin; the original string is used as the href after validation"

duration: 55min
completed: 2026-10-30
status: complete
plan_head_before: 09a4cbd6d6a0557fc291238ff6236c461a183470
plan_head_after: 01fb923debe1d8a54e605a8f25a07f2a7ddd229e
commits: 6
---

# Phase 82 Plan 12: Platform health section Summary

**A Super Admin in platform scope now sees the watchdog and its four services first, then the certificate, disk and on-call cards, and can send a test alert and watch it go from requested to delivered, failed or not picked up, all from the existing health API.**

## Accomplishments

- **Section (D-20).** `AutonomousOpsPlatformHealth` renders `section#platform-health` (h2 `platform-health-title`, `tabIndex -1`) with the subtitle and `Updated HH:MM`, only when `AutonomousOpsActivity` is in platform scope and the viewer holds `control:platform_autonomous_ops`. Tenant scope and every other viewer: no render, no fetch, no placeholder.
- **Watchdog and services card (focal block).** Running / Silent / Not installed chips; the Silent block (`role="alert"`, `omni-watchdog.timer` in mono) and the blue Not installed block, each with the install checklist (link only for an https or same-origin url, otherwise label plus mono path, `rel="noopener noreferrer"`). The stop notice for the database, cache and file sources. Four service cells in the fixed order MongoDB, Backend, nginx, Ollama with the chip and two helper lines for each state of the UI-SPEC table (Healthy, Checking, Down with restart k of 3, Restarting, Gave up, paused by a stop, waiting on MongoDB, Expected off, unexpected Ollama in the Notice tone); a silent or never-reporting watchdog turns every cell to Unknown with `Last known: {state} at {HH:MM}.` or `No reading yet.`; a missing field is an em dash.
- **States.** First load: four `.card p-6` skeletons and `aria-busy`. First-load failure: one red `role="alert"` card with `Reload platform health`. Background polls: no skeleton or spinner.
- **Certificates.** Soonest expiry first, path in mono with `break-all`, date, days text (`in N days`, `expires tomorrow`, `expires today`, `expired N days ago`), ladder chip, `Pinned by agents`, worst-rung header chip, the always-visible pinned-certificate note, unreadable file as an amber Warning with `Can't read this file.`, empty text, and Unknown entries while stale.
- **Disk.** One entry per filesystem (a shared filesystem lists both paths once), `{n}% used`, `{free} free of {total}` in GB with one decimal, `role="meter"` bar with decorative ticks at 80, 90 and 95 percent and a rung-coloured fill, ladder chip, forecast line with its own chip or the flat and not-enough-readings text, the free-space note once, and one Unknown entry for `/` when there are no readings.
- **On-call and Send test alert.** The card renders only the channel type and booleans (a test feeds `key`, `routingKey`, `webhookUrl` and `heartbeatUrl` and asserts none reaches the DOM). Button states: Requesting..., Waiting for the watchdog... with a spinning icon, result lines for pending, delivered, failed (`role="alert"`), no answer after 90 s (amber, button re-enabled), request error with the server message or the connection fallback, not installed (disabled, `Install the watchdog first.` plus checklist), silent (disabled, blue line). The result region is `role="status"` and stays the same node across unchanged polls. Repeated clicks send one POST. The section polls every 5 s only while a test is pending and unanswered.

## Props of `AutonomousOpsPlatformHealth` (for 82-13)

```ts
interface PlatformHealthProps {
    /** The page Refresh button's counter (AutonomousOpsActivity); a change refetches the section. */
    refreshSignal?: number;
}
```

It takes no other props and reads no context; `AutonomousOpsActivity` renders `<AutonomousOpsPlatformHealth refreshSignal={refreshSignal} />` after the status card (guard: `scope.kind === 'platform' && hasPermission('control:platform_autonomous_ops')`). The returned tree is `<section id="platform-health" className="space-y-6">` whose last child is the `OnCallCard`; 82-13 adds the retention card as a further child of that section, after `OnCallCard` (UI-SPEC H3 order: watchdog and services, certificate and disk, on-call, retention). Exports from the file: `HEALTH_POLL_MS` (30 000), `TEST_ALERT_POLL_MS` (5 000) and `AutonomousOpsPlatformHealth`. The retention card must be independent of the health document's load state (UI-SPEC section 1: it still renders when the health fetch failed), so it should be placed outside the `{doc && ...}` branch.

Card props, from `AutonomousOpsHealthCards`: `CertificatesCard({certs, stale, updatedAt?})`, `DiskCard({disks, stale, updatedAt?})`, `OnCallCard({oncall, testAlert, watchdogState, installChecklist, noAnswer, onTestRequested})`, `useTestAlertNoAnswer(testAlert): boolean`, `TEST_ALERT_WAIT_MS` (90 000).

## Task Commits

1. **Task 1 RED** `8ddfe9e45` test - tracer: one health request, section placement, four services in order; tenant-scope and tenant-admin guards
2. **Task 1 GREEN** `e563022b4` feat - section with watchdog row and services grid; Activity wiring
3. **Task 2 RED** `853dcf52e` test - services table, silent and not installed, install link rule, stop notice, skeleton, error, cadence, focus, copy-list expectation
4. **Task 2 GREEN** `c1ad55714` feat - full states, shared notice and checklist parts, ACTV-08 list entry
5. **Task 3 RED** `3076c182a` test - certificate, disk, on-call cards and the test alert state machine (cards render nothing yet)
6. **Task 3 GREEN** `01fb923de` feat - the three cards, the 5 s poll, ACTV-08 list entry

## TDD Gate Compliance

RED commit precedes GREEN for every task. RED evidence (vitest, `DEBUG_PRINT_LIMIT=0`):

- Task 1 target "Super Admin in platform scope: one health request, the section between the status card and Activity ...": failed on `Unable to find role="heading" and name "Platform health"`; the two guard tests (no request in tenant scope or for a tenant admin) passed at RED by design. `gsd_run check tdd-red-evidence` returned `INVALID_RED / invalid_record` because the failure message spans several lines in the TAP report (the same limitation recorded in 82-11); semantic assessment: the target ran, nothing failed at import, setup or fixtures, and it failed on the planned assertion for the intended reason (the component did not exist yet).
- Task 2: 26 section tests and the two copy-list tests failed on `TestingLibraryElementError` (missing text, missing `time`, missing alert) or on the list equality; the pytest list test failed on "Right contains one more item". Section placement tests from Task 1 kept passing.
- Task 3: 40 tests failed with `Unable to find ... role "button" and name /Send test alert/`, `Unable to find an element with the text: Channel ... selector 'dt'`, empty `li` lists and the copy-list equality, against a card skeleton that renders null.

## Deviations from Plan

### Auto-fixed Issues

None needed fixing after the fact: every GREEN passed on the first or second run (Task 2: two class-order and href-normalisation findings fixed before commit).

### Plan text interpreted

- **New test helper file.** `src/__tests__/_platformHealthHarness.tsx` (document fixtures and authFetch helpers) is not in the plan's `files_modified`; both new test modules share it, and it follows the existing `_autonomousOpsCardHarness.tsx` naming.
- **`AutonomousOpsHealthChips.tsx` modified** (not in `files_modified`): it gained `HealthNotice`, `InstallChecklistLink`, `HealthCell`, `clockOrDash`, `HEALTH_SKELETON` and an optional `label` on `HealthChip` (the unexpected-Ollama chip reads "Running" in the Notice tone). Putting them there avoids a cycle between the section and the cards file.
- **`SECONDARY_BUTTON` / `OUTLINE_CHIP` are not exported from `AutonomousOpsActivityList.tsx`** (the plan context says they are); the cards file defines the same `SECONDARY_BUTTON` string locally, as `AutonomousOpsStatusCard` already does. `formatWhen` is imported from the list as planned.
- **`OnCallCard` has one prop beyond the plan** (`noAnswer`) and `useTestAlertNoAnswer` is exported, so the section can stop its 5 s polling at the same 90 s moment the card shows the amber line.
- **`Updated {HH:MM}`** is the time of the last successful fetch in this browser (so it advances every poll while the API answers), not the watchdog's `updatedAt`; the UI-SPEC rule "a failed poll only stops the Updated time advancing" implies this.
- **Service cell text for fields the document does not carry.** The document has no per-service "checked" time, so `Checked {relative}.` uses the document's `updatedAt`; the "restart k of 3" number is `restartsInWindow + 1` for a pending restart and `restartsInWindow` for one in progress; `Last known: ... at {HH:MM}` uses `updatedAt`.
- **Status cell when the channel is not set up** shows the `Not tested` chip with no helper (the UI-SPEC table has no row for that combination).
- **`type="tracer"` gate.** Auto mode is off and `human_verify_mode` is the default `end-of-phase` with an automated-only `<verify>`: the tracer verify was re-run (37 tests passed) and execution continued.

**Total deviations:** 0 auto-fixed, 5 interpretations above. **Impact:** none on the contract.

## Verification

- `npx vitest run src/__tests__/AutonomousOpsPlatformHealth.test.tsx src/__tests__/AutonomousOpsHealthCards.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: `Test Files  4 passed (4)`, `Tests  123 passed (123)`.
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider`: `19 passed in 0.27s`.
- `npm run build`: exit 0, `built in 7.51s` (output went to `dist-new`; nothing was copied to /var/www, the UI is not published).
- `npx tsc --noEmit -p .`: no output, zero `error TS` lines for the whole project.
- Acceptance greps: `AutonomousOpsPlatformHealth` in Activity 2, `StatTile` in the section 0, `truncate` 0 in both components, `dangerouslySetInnerHTML` 0, `role="meter"` 1 in the cards file, `AutonomousOpsPlatformHealth.tsx` and `AutonomousOpsHealthCards.tsx` each 1 in the JSON and both copy tests; sizes: section 343, cards 370, chips 145 lines.
- The human check (light and dark at 640, 1024 and 1280 px against UI-SPEC sections 3-5) is for after the user publishes the UI.

## Known Stubs

None. Every value comes from the health document; nothing is hard-coded to empty.

## Threat Flags

None. T-82-40 (server strings rendered as React text, checklist link only for https or same-origin, `rel="noopener noreferrer"`) and T-82-41 (card renders only type and booleans; test asserts no URL-like text and no input) are both covered by tests.

## Self-Check: PASSED

All five created files exist; the six commits are ancestors of HEAD (`git rev-list --count 09a4cbd6d..HEAD` is 6).
