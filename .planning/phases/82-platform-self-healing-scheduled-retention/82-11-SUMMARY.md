---
phase: 82-platform-self-healing-scheduled-retention
plan: 11
subsystem: ui
tags: [autonomous-ops, platform-health, banners, chips, react, vitest, status-poller]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-08 status.health summary and GET /health document; 82-10 retention review and confirm routes"
provides:
  - "Red role=alert watchdog-silent banner and amber role=status no-working-channel banner for a control:platform_autonomous_ops holder in any scope, fed by the one existing poller"
  - "Typed client surface for every later Phase 82 UI plan (types and calls listed below)"
  - "HealthChip, HealthChipKind, ladderChip: the 25 UI-SPEC chips"
  - "requestPlatformHealthFocus / consumePlatformHealthFocus: one-shot focus flag the Platform health section reads on mount (82-12)"
affects: [82-12 Platform health section, 82-13 Activity list, 82-14 retention card and tenant notices]

requirements-completed: [HEAL-05]

actuals:
  tokens: 11400
  tasks: 3
  commits: 7

key-files:
  created:
    - components/AutonomousOpsHealthBanners.tsx
    - components/AutonomousOpsHealthChips.tsx
    - src/__tests__/AutonomousOpsHealthBanners.test.tsx
  modified:
    - services/autonomousOpsApi.ts
    - contexts/AutonomousOpsStatusContext.tsx
    - components/AutonomousOpsStopBanner.tsx
    - components/AutonomousOpsActivityList.tsx
    - App.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "The health banner's visibility is decided by one exported hook (useHealthBannerKind) used by both the stop banner wrapper and the health banner, so the wrapper renders nothing (no empty flex slot in the shell) when there is neither a stop nor a health banner"
  - "In tenant scope the provider reads the platform status as a side read: a failed side read keeps the last known health and never sets the provider's error flag, so the tenant status card is unaffected"
  - "The permission gate is a boolean (holdsPlatformControl) in the poller's callback dependencies, not the hasPermission function, so the interval is not restarted on every render"
  - "The failing-channel detail falls back to 'no reason was given' when the server sends no error text"

duration: 20min
completed: 2026-10-30
status: complete
plan_head_before: 4dae2bdeb73c93b2abfb24fc4a32ad34d438b33f
plan_head_after: 991b799dae4e2dd1a56fb646d4325210aebefa1e
commits: 7
---

# Phase 82 Plan 11: Platform health banners, typed client and health chips Summary

**The Super Admin now sees the watchdog-silent alarm and the no-working-channel warning on every screen and in every scope through the one 30-second status poller; the typed client calls and the 25 shared health chips every later Phase 82 screen needs are in place.**

## Accomplishments

- `AutonomousOpsStatusProvider` also fetches `/api/platform/autonomous-ops/status` for a holder of `control:platform_autonomous_ops` while inside a tenant (same load, same interval, one `setInterval` at 30,000 ms). Other users make no platform request.
- `AutonomousOpsHealthBanners` renders at most one banner beneath the stop banners: silent (red, `role="alert"`, `Last seen HH:MM` in the viewer's 24-hour clock) outranks channel `none` / `failing` (amber, `role="status"`); `untested`, `working`, `null`, watchdog `not_installed` and `health: null` render nothing. Not dismissible. Detail text uses `break-words`, `line-clamp-2` and the full text in `title`; `View details` wraps below the text under 640px (`basis-full sm:basis-auto`).
- `View details` is hidden only on `autonomousOps` in platform scope; elsewhere it calls `requestPlatformHealthFocus()` then `onViewPlatformHealth()`.
- `HealthChip` renders all 25 UI-SPEC chips with the 81 anatomy, a 12px `aria-hidden` icon, visible text and the Phase 81 tone classes (no new tone), light and dark.

## Exported API (services/autonomousOpsApi.ts)

Types: `WatchdogState`, `OnCallChannelStatus`, `PlatformHealthSummary` (`{watchdog, lastSeenAt, channel, channelError}`), `ServiceId`, `ServiceState`, `PlatformHealthService`, `PlatformHealthCert`, `PlatformHealthDisk`, `PlatformHealthOnCall`, `PlatformHealthTestAlert`, `PlatformHealthDocument` (`watchdog, services, certs, disks, oncall, testAlert, installChecklist, stop, updatedAt, host`), `RetentionReviewItem`, `RetentionLastRun`, `RetentionReview`, `ConfirmRetentionResult` (`{confirmed: {rows, records, tenants}}`), `AutonomousOpsHealthRowChip`.

Extended: `AutonomousOpsBucket` and `AutonomousOpsRowBucket` include `'platform_health'`; `AutonomousOpsRow.healthChip` and `source` (optional); `AutonomousOpsCounts.platform_health` (optional); `PlatformAutonomousOpsStatus.health` (optional, nullable).

Calls: `fetchPlatformHealth()`, `requestTestAlert()` (answers `{testAlert}`), `fetchRetentionReview(offset = 0)` (limit 25), `confirmRetention(reviewToken)`. Errors are `AutonomousOpsApiError` (status 409 and 403 readable).

Components: `AutonomousOpsHealthBanners`, `useHealthBannerKind`, `formatClock`, `requestPlatformHealthFocus`, `consumePlatformHealthFocus`; `HealthChip`, `HealthChipKind`, `ladderChip(rung)` (0 OK, 1 Notice, 2 Warning, 3+ Critical, unreadable Unknown). `AutonomousOpsStopBanner` gained optional props `inPlatformScope` and `onViewPlatformHealth`.

## App.tsx hunk staged

Only the `AutonomousOpsStopBanner` element's props (6 insertions, 1 deletion, hunk `@@ -1955,7 +1955,12 @@`): `inPlatformScope={viewingTenantId === null}` and `onViewPlatformHealth={() => { setViewingTenantId(null); handleSetCurrentView('autonomousOps'); }}`. It was staged with `git apply --cached` from a patch built against `git show HEAD:App.tsx` (interactive `git add -p` is unavailable), committed in `c046979de`. The user's two uncommitted hunks (`@@ -1404,22 +1404,28 @@` handleResetPassword/handleSetUserPassword and `@@ -1717,7 +1723,7 @@` the settings case) were untouched and remain unstaged in the working tree.

## Task Commits

1. **Task 1 RED** `4fb48f94a` test - silent banner for a Super Admin inside a tenant; tenant admin guard
2. **Task 1 GREEN** `e83e18961` feat - API types and calls, provider platform side read, silent banner, stop banner wiring
3. **Task 2 RED** `a1bfa1f9c` test - priority, arming, failing channel, View details focus, 25 chips, ladder (plus a render-nothing chip skeleton so the tests fail on assertions)
4. **Task 2 GREEN** `c046979de` feat - channel banners, focus flag, HealthChip and ladderChip, App.tsx props hunk
5. **Task 3 RED** `ddf26a040` test - vitest and pytest expect the two new components in the agreed file list
6. **Task 3 GREEN** `e916bed49` feat - banned-terms JSON lists both components; frontend scan count 7 to 9
7. **Fix** `991b799da` fix - Activity chip map accepts the new `platform_health` bucket (type error)

## TDD Gate Compliance

RED commits precede GREEN commits for all three tasks. RED evidence (vitest `tap-flat`, `DEBUG_PRINT_LIMIT=0`, run through `gsd_run check tdd-red-evidence`):

- Task 1 target "fetches the platform status in tenant scope and shows the red silent banner with the last seen time": `RED_EVIDENCE_OK`. Semantic assessment: the target ran and failed on the planned `waitFor(queryByRole alert not null)` assertion ("no alert region was rendered"); no import or fixture fault. The companion tenant-admin test passed at RED (a guard that must hold, it is not the target).
- Task 2 targets "running with no channel shows the amber status banner...", "in tenant scope ... requests focus once" (fails on `toBeTypeOf('function')` for the missing exports) and "healthy renders ..." (chip skeleton renders null): each `RED_EVIDENCE_OK`. 31 tests failed at RED; guard tests (silent suppression, null/untested/working, platform-scope absence of View details, wrap classes) already held.
- Task 3 target "lists the agreed files ..." (vitest deep-equal of the file list, 15 vs 17 entries) and pytest `test_file_list_is_the_agreed_list_and_the_scope_excludes_other_screens`: genuine assertion failures, but the vitest TAP for this one contains a multi-line array that the classifier rejected as `invalid_record` (report format), and pytest has no supported report adapter. Semantic assessment: the target executed and failed on the planned equality for the intended reason (the JSON lacked the two new entries).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Type error from the new bucket** - Found during: plan verification (`tsc --noEmit`, outside `npm run build`, which does not type-check). Adding `'platform_health'` to `AutonomousOpsRowBucket` made `chipKeyFor` in `components/AutonomousOpsActivityList.tsx` return a value not in `ChipKey`. Fix: one line maps that bucket to the informational (`suggested`) chip until the Phase 82 Activity plan renders `HealthChip`. File not in the plan's `files_modified`. 34 Activity tests pass. Commit `991b799da`.

**2. [Rule 3 - Blocking] Hard-coded scan count** - `autonomousOpsCopy.test.ts` asserted `FRONTEND_FILES` length 7; adding the two components makes it 9. Updated in the Task 3 GREEN commit `e916bed49`.

### Plan text interpreted

- **Task 2 RED needed a skeleton.** `AutonomousOpsHealthChips.tsx` was committed in the RED commit as a component that renders nothing, so the chip tests fail on assertions rather than on a missing module. GREEN replaces it entirely.
- **`git add -p` replaced** by a cached patch of exactly my hunk, as the run rules direct.
- **`useHealthBannerKind` hook** (not in the plan) so the stop banner wrapper can return `null` when nothing is showing, instead of leaving an empty flex child in the shell's `gap-3` column.
- **Test helper `findRegion`** uses `waitFor` with a one-line `onTimeout` error instead of `findByRole`, so RED failures produce a TAP report the evidence classifier can parse.

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking). **Impact:** none on the contract.

## Verification

- `npx vitest run src/__tests__/AutonomousOpsHealthBanners.test.tsx src/__tests__/AutonomousOpsStopBanner.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: `Test Files  4 passed (4)`, `Tests  109 passed (109)`.
- `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_copy.py -q -p no:cacheprovider`: `19 passed in 0.24s`.
- `npm run build`: exit 0, `built in 7.12s`. Nothing was copied to /var/www; the UI is not published.
- `npx tsc --noEmit -p .` filtered to AutonomousOps files: no errors after `991b799da`.
- Acceptance greps: API calls 4, `'platform_health'` 1, `AutonomousOpsHealthBanners` in the stop banner 2, `onViewPlatformHealth` in App.tsx 1, `dangerouslySetInnerHTML` 0 in both new components, `AutonomousOpsHealthBanners.tsx` 1 in each of the three lists, `AutonomousOpsHealthChips.tsx` 1 in the JSON.

## Known Stubs

None. `requestPlatformHealthFocus` has no reader yet by design: the Platform health section that consumes it is 82-12.

## Threat Flags

None beyond the register. T-82-38: the platform status is fetched and the banner rendered only when `hasPermission('control:platform_autonomous_ops')` is true (a tenant admin test asserts zero platform requests); T-82-39: every server string is React text, no `dangerouslySetInnerHTML`.

## Issues Encountered

- Nothing is live: the UI is built into `dist-new` but not published (the user's step). The banners need the 82-08 backend restart to receive `health`.
- The working tree still carries the user's other uncommitted work (including the two App.tsx hunks above).

## Next Phase Readiness

82-12 can import the types and calls above, `HealthChip`/`ladderChip`, and call `consumePlatformHealthFocus()` on mount to move focus to `#platform-health-title`.

## Self-Check: PASSED

All created and modified files exist; commits `4fb48f94a`, `e83e18961`, `a1bfa1f9c`, `c046979de`, `ddf26a040`, `e916bed49`, `991b799da` are ancestors of HEAD; all plan acceptance criteria and verification commands pass.
