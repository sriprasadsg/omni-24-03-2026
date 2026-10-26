---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 07
subsystem: ui
tags: [react, typescript, autonomous-ops, activity-list, polling, vitest, spatial-glass]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-02)
    provides: view:autonomous_ops permission, AppView 'autonomousOps', catalogue entry and sidebar item
provides:
  - "services/autonomousOpsApi.ts: four typed GET functions, AutonomousOpsApiError and the row/status/stop types"
  - "AutonomousOpsStatusProvider + useAutonomousOpsStatus: one shared status poller (mount, 30 s while visible, focus, refresh), scope-aware, no request when disabled"
  - "AutonomousOpsActivity screen shell with data-slot=autonomous-ops-status for the 81-10 status card"
  - "AutonomousOpsActivityList: eight filters, 5-column table at xl and stacked cards below, simulation and control rows, cursor pagination, every list state in 81-UI-SPEC"
  - "App.tsx wiring: lazy import, case 'autonomousOps', provider around the shell column"
affects: [81-09, 81-10]

actuals:
  tokens: 19000
  tasks: 2
  commits: 4

plan_head_before: 4a414b250b3a4f02ae3c17d0f8cf28cc19fa3032
plan_head_after: 4f6fdd74930a853236cd661ab9f551ff5de72f4b
commits: 4

tech-stack:
  added: []
  patterns:
    - "Loud vs silent list loads: filter/scope change shows the skeleton; poll, focus and Refresh reload the first page silently and keep the rows"
    - "resolveAutonomousOpsScope(role, viewingTenantId) is the single place that decides tenant / platform / none; the provider and the screen both use it"
    - "A simulation can never read as carried out: the Result cell prefixes the would-have sentence client-side if the server omitted it, and rows outside the active bucket are dropped"

key-files:
  created:
    - services/autonomousOpsApi.ts
    - contexts/AutonomousOpsStatusContext.tsx
    - components/AutonomousOpsActivity.tsx
    - components/AutonomousOpsActivityList.tsx
    - src/__tests__/AutonomousOpsActivity.test.tsx
  modified:
    - App.tsx

key-decisions:
  - "Scope resolution lives in the context module and is shared with the screen: tenant roles send no tenantId (T-81-29), Super Admin without a tenant reads platform routes, other platform roles without a tenant read nothing"
  - "The client re-applies the bucket rule (state filters drop simulation and control rows; Simulation shows only simulation) even though the server filters, so PROH-81-06 does not depend on the server alone"
  - "The list refreshes itself silently on window focus and on a 30 s visible-tab timer, in addition to the Refresh button; it skips a silent reload while a Load more is open or more than one page is loaded, so loaded pages are never discarded"
  - "Footer shows 'Showing n of total actions' only when total is known and larger than n; a total equal to n reads 'Showing n actions'"

patterns-established:
  - "Tests mock authFetch (apiService) rather than the API module, so the exact URLs and query order are pinned: bucket, limit, cursor, tenantId"

requirements-completed: [ACTV-01, ACTV-03]

coverage:
  - id: D1
    description: "A user with view:autonomous_ops opens Autonomous Ops and sees each decision with what ran, why (reason and rule id), target and result, under eight filters"
    requirement: ACTV-01
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#shows the title, subtitle and both rows with what ran, why, target and result"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#renders eight filter buttons in a labelled group, All pressed by default"
        status: pass
    human_judgment: false
  - id: D2
    description: "Simulation rows carry the Simulation chip, a dashed rule and the would-have result, appear only under All and Simulation, and are never shown as done"
    requirement: ACTV-03
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#a simulation row is absent under each of the six state filters, even if the server leaks one"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#never presents a simulation as carried out, whatever text the server sent"
        status: pass
    human_judgment: false
  - id: D3
    description: "One shared status poller; users without the permission mount no poller and make no request; scope rules for tenant roles, Super Admin and Platform Support"
    requirement: ACTV-01
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#makes no request at all when disabled (a user without view:autonomous_ops)"
        status: pass
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#Platform Support with no tenant sees only the header and Select an organization, and makes no request"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every list state in the UI contract (loading, first-page error, load-more error, empty All live and shadow, empty filtered, populated, partial, overflow, zero-one-many) renders as specified"
    verification:
      - kind: unit
        ref: "src/__tests__/AutonomousOpsActivity.test.tsx#list states"
        status: pass
    human_judgment: false
  - id: D5
    description: "The screen looks right in light and dark themes at 1280 px and below (Spatial Glass tokens, chip contrast, dashed simulation rule)"
    verification: []
    human_judgment: true
    rationale: "Visual fidelity and contrast are not asserted by jsdom tests; the UI has not been published, so it is checked at publish time as an approver and as Platform Support (user's step)."

duration: 10min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 07: Autonomous Ops Activity Screen Summary

**Read-only Autonomous Ops screen: typed client, one shared status poller, and an activity list with eight filters, table/card layouts, unmistakable simulation rows and every list state in the UI contract, wired into App.tsx behind view:autonomous_ops.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-10-26T08:11:07Z
- **Completed:** 2026-10-26T08:21:00Z
- **Tasks:** 2 (Task 1 tracer, Task 2 auto; both TDD)
- **Files modified:** 6 (5 created, App.tsx modified)

## Accomplishments

- Typed client `services/autonomousOpsApi.ts` for `GET /api/autonomous-ops/status|actions` and `GET /api/platform/autonomous-ops/status|actions`, with `AutonomousOpsApiError {status, detail}`.
- `AutonomousOpsStatusProvider` polls once on mount, every 30 s while the tab is visible (paused when hidden, resumed on `visibilitychange`), on window focus and on `refresh()`; a failed poll keeps the last state; `enabled=false` makes no request.
- Activity list: eight filter pills (`aria-pressed`, counts only when the server sends `counts`), 5-column table at `xl`, stacked cards with `dl` below, Simulation and Stop/Resume chips, Load more with the footer variants, five-row skeleton with `aria-busy`, first-page and load-more error alerts with Try again, empty states (live, shadow, filtered, platform), `—` for missing target or result.
- Scope handling: tenant roles read their own tenant and send no `tenantId`; platform staff send the viewing tenant; Super Admin with no tenant reads the platform-scope list; Platform Support with no tenant sees only the header, Read-only chip and the "Select an organization" card, with no request.
- Tracer gate: `Tracer verified end-to-end - expanding` (tests and build green after Task 1, before Task 2).

## Task Commits

1. **Task 1 (tracer): sidebar screen, typed client, shared poller** - `55f23c130` (test, RED), `915bce097` (feat, GREEN)
2. **Task 2: filters, layouts, simulation and control rows, pagination, list states** - `d44e68f0a` (test, RED: 15 of 34 failing), `4f6fdd749` (feat, GREEN: 34 of 34)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

## API contract as consumed (for 81-09)

No deviation from the contract in the plan's interfaces block. What the client relies on that 81-09 must honour:

- `bucket=all` returns every row type including `simulation` and `control`; each state bucket returns only rows of that bucket; `bucket=simulation` only simulation rows. The client drops rows that do not match, but counts and `total` are taken as delivered.
- Query parameter order produced by the client: `bucket`, `limit` (25), `cursor` (only when set), `tenantId` (only for platform staff viewing a tenant). Platform list routes never receive `tenantId`.
- `counts` and `total` are optional and read from the first page only; a missing `counts` hides the numbers.
- Simulation rows should carry `resultText` starting `Nothing was done. This is what would have happened: ...`; if not, the client adds that lead-in.
- Control rows: `controlEvent` in `stop_pressed | platform_stop_pressed | breaker_tripped` show the Stop chip; `stop_cleared | platform_stop_cleared | level_restored` show Resume. `actionLabel`, `reasonText`, `target` and `resultText` are rendered as delivered.
- Errors: non-2xx with `{detail}`; the list shows its fixed copy and does not display the server detail.
- `status.tenantName` supplies the "Viewing {tenant name}" chip; `status.shadow.effective` selects the shadow-mode empty-state copy.

## Files Created/Modified

- `services/autonomousOpsApi.ts` - typed GET client, `AutonomousOpsApiError`, row/status/stop/counts types
- `contexts/AutonomousOpsStatusContext.tsx` - shared poller, `resolveAutonomousOpsScope`, `STATUS_POLL_MS`
- `components/AutonomousOpsActivity.tsx` - screen shell (title, subtitle, scope and Read-only chips, Refresh, status-card slot, Activity section, Select an organization card)
- `components/AutonomousOpsActivityList.tsx` - filters, table/cards, chips, pagination, list states, exported `EmptyStateCard`
- `src/__tests__/AutonomousOpsActivity.test.tsx` - 34 test cases
- `App.tsx` - lazy import, `case 'autonomousOps'` (next to `case 'soar'`), provider around the shell column. Only these 5 added lines were committed.

## Decisions Made

See `key-decisions` above. In short: shared scope resolver; client-side defence for the simulation and bucket rules; silent list refresh on focus and a 30 s timer that never discards extra loaded pages; footer total only when it adds information.

## Deviations from Plan

### Auto-fixed / additive items

**1. [Rule 2 - Missing critical] Client-side guards for PROH-81-06**
- **Found during:** Task 2
- **Issue:** The plan relied on the server alone to keep simulation rows out of state filters and to word the result as "Nothing was done". A server bug would show a simulation as done.
- **Fix:** The list drops rows whose bucket does not match the active filter; the Result cell prefixes the would-have lead-in (or shows `Nothing was done.` when no text) for any simulation row.
- **Files modified:** `components/AutonomousOpsActivityList.tsx`
- **Verification:** two dedicated tests (server leaks a simulation under each state filter; simulation with a plain or null result)
- **Committed in:** `4f6fdd749`

**2. [Copy gap] Platform-scope empty body**
- The copy contract has no text for "no activity" at platform scope. The list uses `Nothing has been recorded at platform level yet. Stop and resume events appear here.` under the same `No activity yet` heading. Please confirm or replace in the UI-SPEC.

**3. [Layout choice] No Refresh button in the "Select an organization" state**
- 81-UI-SPEC 3f says "page header and an empty-state card only"; Refresh would refresh nothing there, so it is omitted. The Read-only chip is kept.

**Total deviations:** 1 auto-fixed (Rule 2), 2 small copy/layout choices. **Impact:** none on scope; all additive.

## Issues Encountered

- A test helper matched the platform status URL when asked for the tenant one (suffix match); fixed to an exact path match in the same commit as Task 1.
- `npm run build` and the full `src/__tests__` run together exceed the 120 s tool limit; they were run in the background and both finished green.

## Known Stubs

- `components/AutonomousOpsActivity.tsx`: the empty `<div data-slot="autonomous-ops-status" />` is an intentional mount point for the status card, Stop and Resume controls built in 81-10. It does not affect this plan's goal (read-only activity list).

## Threat Flags

None. No new endpoint or trust boundary beyond the plan's threat model: T-81-28 (no `dangerouslySetInnerHTML`, no link-ification, covered by a hostile-string test and a source-guard test), T-81-29 (`tenantId` only sent for platform roles, tested), T-81-30 (simulation chip, dashed rule, result sentence, excluded from state filters, tested).

## User Setup Required

None. Steps left for the user (not done here by rule): publish the UI build to `/var/www/omni-agent`, then open Autonomous Ops as an approver and as Platform Support (live integration against 81-09's routes); no restart or migration is needed for this plan.

## Verification Results

- `npx vitest run src/__tests__/AutonomousOpsActivity.test.tsx`: 34 passed (min 15)
- `npx vitest run src/__tests__` (wave gate, includes catalogueAccess and viewAccess): 552 passed
- `npm run build`: built, no TS errors; `tsc --noEmit` reports nothing for the new files
- Acceptance: `case 'autonomousOps'` count 1; `AutonomousOpsStatusProvider` count 3 in App.tsx (import, open, close); `dangerouslySetInnerHTML` 0 in both components; `data-slot="autonomous-ops-status"` 1; `aria-pressed` 1; `Filter activity by state` 1; staged `App.tsx` diff held only the 5 added lines, no reset-password lines
- Only own hunks of App.tsx were committed; the user's `handleResetPassword` / `handleSetUserPassword` / `case 'settings'` edits remain unstaged in the working tree.

## Next Phase Readiness

- 81-10 can mount the status card in the `data-slot="autonomous-ops-status"` element and the banner can read `useAutonomousOpsStatus()` (types `AutonomousOpsStatus`, `PlatformAutonomousOpsStatus`, `StopView` are exported).
- 81-09 must serve the routes above; until then the screen shows the first-page error state against a real backend.

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*

## Self-Check: PASSED

- Files exist: services/autonomousOpsApi.ts, contexts/AutonomousOpsStatusContext.tsx, components/AutonomousOpsActivity.tsx, components/AutonomousOpsActivityList.tsx, src/__tests__/AutonomousOpsActivity.test.tsx
- Commits present: 55f23c130, 915bce097, d44e68f0a, 4f6fdd749
