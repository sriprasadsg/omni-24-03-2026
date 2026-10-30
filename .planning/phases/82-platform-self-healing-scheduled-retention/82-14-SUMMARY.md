---
phase: 82-platform-self-healing-scheduled-retention
plan: 14
subsystem: ui
tags: [autonomous-ops, platform-health, activity-list, retention, react, vitest]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-10 /policies gate flags, managedBy, editable and countOnlyUntilConfirmed; 82-11 HealthChip and the typed healthChip/source row fields"
provides:
  - "platform_health rows in the platform Activity list (five-column table and stacked cards) with HealthChip, source, rule id, host/target and result"
  - "Platform health filter pill (ninth, platform scope only) with counts.platform_health and two empty-state variants"
  - "Client-side drop of platform_health rows outside platform scope (T-82-44)"
  - "Tenant Retention Policy notices: audit_logs card without Edit, 02:00 UTC schedule line, D-26 confirmation, shortened and waiting notices"
affects: [82 verification, 82 operator install checklist]

requirements-completed: [HEAL-07, HEAL-06]

actuals:
  tokens: 9400
  tasks: 3
  commits: 6

key-files:
  created:
    - src/__tests__/AutonomousOpsActivityPlatformHealth.test.tsx
    - src/__tests__/RetentionPolicyDashboard.test.tsx
  modified:
    - components/AutonomousOpsActivityList.tsx
    - components/RetentionPolicyDashboard.tsx

key-decisions:
  - "A platform_health row with a host but no target shows the host and a dash line under it; a row with neither shows a single dash"
  - "The Platform health pick is derived: outside platform scope a leftover platform_health selection reads as All and requests bucket=all, so the filter cannot leak across a scope change"
  - "The not-installed empty variant keys on platformStatus.health.watchdog === 'not_installed'; unknown or missing health uses the 'afterwards' variant with Show all activity"
  - "The shortened-period block shows only when the save was OK, the server answered countOnlyUntilConfirmed true AND the new retention_days is lower than the card's previous value; lengthening never shows it even if the server is still counting"
  - "The Edit button is hidden when the server sends editable false or the collection is audit_logs (the audit_logs note renders for that collection regardless of the server flag)"

duration: 35min
completed: 2026-10-30
status: complete
plan_head_before: 6f1def0e24a78bcf0cf9c057901dcb248ba01002
plan_head_after: b3dd0674c6de9838087f50c72de4bc57bc558e62
commits: 6
---

# Phase 82 Plan 14: Platform-health Activity rows and tenant Retention Policy notices Summary

**The Super Admin reads watchdog and retention events in the same platform Activity list as every other decision, filterable with a Platform health pill and counts, and invisible in every other scope; the tenant Retention Policy screen now says audit logs are not cleaned here, cleanup runs at 02:00 UTC, the manual run only counts types awaiting confirmation, and a shortened period waits for a platform administrator.**

## Accomplishments

- `components/AutonomousOpsActivityList.tsx` (439 lines, under 500): the 82-11 stopgap that mapped `platform_health` to the informational chip is gone. A `RowChip` renders `HealthChip` from `row.healthChip` (Healthy, Notice, Warning, Critical, Paged, Skipped; Unknown if the server omits it) for those rows and the Phase 81 chip for all others. Under the event label the muted line is `row.source` (Watchdog, Super Admin) instead of the class line. Reason and rule id (font-mono), host and target (font-mono, break-all) and result use the existing cells, so the layout, no-row-actions rule and Phase 81 stop-control presentation are unchanged.
- The `visible` filter drops any `bucket === 'platform_health'` row unless `scope.kind` is platform, whatever the server sent (T-82-44).
- A ninth pill `Platform health` is appended after Simulation in platform scope only, with the same pill classes (accent when selected), a number only when `counts.platform_health` is returned, and a request for `bucket=platform_health` from the platform actions call. Tenant scope renders eight pills.
- Empty under the pill: watchdog `not_installed` gives `No platform health events yet.` with `Events appear here once the watchdog is installed and reporting.`; otherwise `No platform health events.` with `Show all activity` (selects All).
- `components/RetentionPolicyDashboard.tsx`: `audit_logs` keeps its row, loses Edit and shows `Audit logs are kept by the audit ledger's own schedule, not by this cleanup.`; the guideline reads `Cleanup runs automatically every night at 02:00 UTC.` (no other bullet touched); the Run Cleanup Now confirmation uses the D-26 text exactly; a lower saved value that the server holds for confirmation shows the D-19 yellow block (existing yellow classes) on that card only; a card with `gate.waiting` shows the 12px waiting line, no counts. Existing emoji and styling untouched.

## Task Commits

1. **Task 1 RED** `2f579363f` test - platform-health row, six chips, tenant-scope drop
2. **Task 1 GREEN** `d08ea3738` feat - RowChip, source line, client-side drop
3. **Task 2 RED** `c1c6b6433` test - pill, counts, empty states, dashes, wrapping, loading
4. **Task 2 GREEN** `ab594ee99` feat - platform-only filter, count, empty-state variants, dash for missing target
5. **Task 3 RED** `2cc622bbb` test - tenant notices
6. **Task 3 GREEN** `b3dd0674c` feat - the five text and small-block changes

## TDD Gate Compliance

RED commit precedes GREEN for every task. The repo's vitest reporter was run with `--reporter=json` and read directly; `gsd_run check tdd-red-evidence` was not run (the JSON reporter is not one of its supported formats). Semantic assessment of each RED, per test:

- Task 1: all 3 tests executed and failed on the planned assertions (no `Critical` chip text because the row rendered the informational chip; tenant-scope row found because it was not dropped). No import or fixture fault.
- Task 2: 7 of 15 tests failed on the planned assertions (pill list missing the ninth entry, `Platform health` button not found, the host-without-target row showing no dash). The remaining 8 (Task 1 tests, tenant eight-pill guard, All-includes, break-words, footer and no-target-no-result dash) held already; the tenant eight-pill and footer tests are guards, not targets.
- Task 3: 8 of 12 failed on the planned assertions (Edit present on audit_logs, missing note, missing 02:00 line, old confirm text, missing D-19 block and waiting line). The four passing tests are guards (decline runs nothing; longer value, non-held lower value, refused save show no block).

## Deviations from Plan

### Test fix during GREEN

**1. [Rule 1 - Bug in my own test] Suggested pill matched as a chip** - The Task 1 test asserted `queryByText('Suggested')` was null, but the Suggested filter pill carries that text. Changed to filter out matches inside a button (the chip is a span). Included in the Task 1 GREEN commit `d08ea3738`. No product-code impact.

### Interpretations

- `chipKeyFor` keeps its `ChipKey` return type with a cast (`row.bucket as ChipKey`) for the one bucket it never receives, rather than widening `ChipKey` and `CHIPS`; `RowChip` is the single place that decides.
- `Target` shows a dash line under the host for a platform_health row with host but no target (UI-SPEC: "Missing target or result renders —"); Phase 81 rows are unchanged.
- No new helper file was needed: additions to the Activity list total 24 lines net, well inside the 500-line limit, so nothing moved into `AutonomousOpsHealthChips.tsx`.
- `App.tsx`, `AutonomousOpsHealthChips.tsx` and the backend were not touched.

**Total deviations:** 1 auto-fixed (own test), 0 contract changes.

## Verification

- `npx vitest run src/__tests__/AutonomousOpsActivityPlatformHealth.test.tsx src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/RetentionPolicyDashboard.test.tsx src/__tests__/autonomousOpsCopy.test.ts`: `Test Files  4 passed (4)`, `Tests  79 passed (79)`.
- `npm run build`: exit 0, `built in 7.87s` (output in dist-new; nothing copied to /var/www, UI not published).
- `npx tsc --noEmit -p .`: 0 `error TS` lines.
- Acceptance: `grep -c platform_health components/AutonomousOpsActivityList.tsx` 8 (>= 2); `wc -l` 439 (< 500); `No platform health events` appears 2 times in the Activity list; `3:00 AM` 0 and `02:00 UTC` 1 in RetentionPolicyDashboard; `audit ledger's own schedule` 1.

## Known Stubs

None.

## Threat Flags

None beyond the register. T-82-44 mitigated by the client-side drop plus a test that feeds a platform_health row into tenant scope; T-82-45 mitigated because the screen renders only the caller's own `gate.waiting` flag and never a count.

## Issues Encountered

- Nothing is live: the UI is built but not published (the user's step). The platform-health rows need the 82-01/82-08 backend (restart) and the notices need the 82-10 backend routes.
- The waiting line and D-19 block can both show for a freshly shortened card after the refetch (the first is the saved notice, the second the standing state). This follows the spec literally.

## Next Phase Readiness

Phase 82 UI plans are complete; remaining work is phase verification and the user's deploy (backend restart, watchdog install, UI publish).

## Self-Check: PASSED

All four files exist; commits `2f579363f`, `d08ea3738`, `c1c6b6433`, `ab594ee99`, `2cc622bbb`, `b3dd0674c` are ancestors of HEAD; the verification commands above pass.
