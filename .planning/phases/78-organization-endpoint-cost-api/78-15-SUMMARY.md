---
phase: 78-organization-endpoint-cost-api
plan: 15
subsystem: ui
tags: [itam, reports, platform-tiers, tenant-rule, react, vitest, gap-closure]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: ReportsPanel needsTenant gating and the custom report tenant rule (78-13, 78-14), D-14 amended 2026-11-17 and D-15
provides:
  - ITAMConsole isPlatformView prop; needsTenant = (isSuperAdminView || isPlatformView) && !tenantId, so every platform tier without a tenant gets the Select-a-tenant block and disabled Reports controls with no request and no toast
  - App.tsx passes isPlatformView={isPlatformRoleName(currentUser.role)} to the ITAM console
  - ReportsPanel tenantRejected state, takeTenantRejection helper and blocked = needsTenant || tenantRejected gating every Reports control (R5 on the Reports tab)
  - SELECT_TENANT_RE exported from ItamKpiPanel as the one R5 pattern
  - Tests pinning Support (no tenant, selected tenant), Billing refusal by the view gate, and the select-tenant rejection paths
affects: [phase-78-reverification, phase-78-security-audit, 78-UAT-test-1]

actuals:
  tokens: 9500
  tasks: 2
  commits: 4
plan_head_before: 301ce5dbd534eadcef5e4f81a14494a61e22387d
plan_head_after: 747b2b972f97b60c325e31482aede610a6316124
commits: 4

tech-stack:
  added: []
  patterns:
    - "A server 400 whose detail starts 'Select a tenant' is matched (never rendered) and turns into the no-tenant state instead of a toast, in both the KPI tile and the Reports tab"
    - "Client gating is presentation only; the resolver's 400 and the guards' 403 are unchanged (PROH-78-16)"

key-files:
  created: []
  modified:
    - App.tsx
    - components/itam/ITAMConsole.tsx
    - components/itam/ItamKpiPanel.tsx
    - components/itam/ReportsPanel.tsx
    - src/__tests__/ITAMConsole.test.tsx
    - src/__tests__/ITAMReportsPanelTenantRule.test.tsx

key-decisions:
  - "isPlatformView is an optional prop defaulting to false, so every other caller of ITAMConsole behaves as before; LifecyclePanel and FinancePanel keep isSuperAdminView only"
  - "blocked (not needsTenant) also gates the saved-list rows, the Loading line and the empty state, so a rejected list shows the custom note alone rather than the note beside 'No custom reports yet'"
  - "A tenant change is the only thing that clears tenantRejected; loadSavedReports still skips on needsTenant only, so choosing another tenant reloads the list"

requirements-completed: [COST-07]
gap_ids: [G-78-IN04]

coverage:
  - id: D1
    description: "A Platform Support user with no tenant gets the Select a tenant block, disabled Run Report buttons with the pre-built note, the custom note, no KPI/report/saved-list request and no toast"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#a Platform Support user with no tenant gets the Select a tenant state with no request or toast"
        status: pass
    human_judgment: false
  - id: D2
    description: "A platform user with a selected tenant still sends the KPI request; Platform Billing is refused the ITAM screen by the view gate and Platform Support is allowed"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#a platform user with a selected tenant still sends the KPI request"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#Platform Billing is refused the ITAM screen by the view gate while Platform Support is allowed"
        status: pass
    human_judgment: false
  - id: D3
    description: "A saved-list, pre-built run or export rejection starting 'Select a tenant' puts the Reports tab into the no-tenant state with no toast; other rejections still toast; a tenant change clears the state"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#a Select a tenant rejection on the Reports tab (Phase 78 plan 15)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Support with a selected tenant and Support with no tenant read acceptably in the live UI (the Select block copy still says 'Open a tenant from Tenants', A-78-39)"
    verification: []
    human_judgment: true
    rationale: "Wording and look of the explained state for a role that can never choose a tenant is a judgment call; UAT test 1 in 78-UAT.md stays pending for the post-deploy live check"

duration: 18min
completed: 2026-11-17
status: complete
---

# Phase 78 Plan 15: Platform tiers without a tenant get the no-tenant ITAM state Summary

**Every platform tier (Owner, Support, Billing) without a selected tenant now gets the Select-a-tenant block and disabled Reports controls with no request and no toast, and a server "Select a tenant" 400 puts the Reports tab into that same state instead of raising a toast.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-11-17T07:48:56Z
- **Completed:** 2026-11-17T08:07:04Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- G-78-IN04 closed: `needsTenant = (isSuperAdminView || isPlatformView) && !tenantId`, with App.tsx passing `isPlatformView={isPlatformRoleName(currentUser.role)}` (a four-line diff in App.tsx: the import and the itam case, each removed and added).
- R5 applied to the Reports tab: `takeTenantRejection` matches the server detail with the shared `SELECT_TENANT_RE` (never rendered, T-78-07) in the saved-list, pre-built run, saved run and export catches; `blocked` gates the notes, Run buttons, Create Custom Report, builder, and the saved-list body.
- Billing pinned behind the Phase 77 view gate by a test (no gate code changed); Owner and tenant-user behaviour unchanged.

## Task Commits

1. **Task 1 (tracer), RED: platform tiers on the ITAM console** - `5bf03c54f` (test)
2. **Task 1 (tracer), GREEN: isPlatformView and needsTenant rule** - `2017d7cf0` (fix; ITAMConsole.tsx and App.tsx)
3. **Task 2, RED: select-tenant rejection on the Reports tab** - `65236cf54` (test)
4. **Task 2, GREEN: tenantRejected state and takeTenantRejection** - `747b2b972` (fix; ItamKpiPanel.tsx and ReportsPanel.tsx)

**Plan metadata:** recorded in the docs(78-15) commit that follows this file.

## RED evidence

- **Task 1:** `npx vitest run src/__tests__/ITAMConsole.test.tsx -t "platform tiers"` on HEAD before the GREEN edit: 1 failed, 2 passed. The Support test failed at `getByRole('heading', { name: 'Select a tenant' })` (the console rendered the KPI grid, so the request was sent and the tile never showed the block). The selected-tenant test and the Billing gate test passed, as the plan expected (the gate test pins existing behaviour). Semantic assessment: the target test failed on the planned assertion for the intended reason, not on setup or import.
- **Task 2:** `npx vitest run src/__tests__/ITAMReportsPanelTenantRule.test.tsx` before the GREEN edit: 4 failed, 22 passed. The four select-tenant behaviours (saved-list rejection, run rejection, export rejection, tenant-change clears) failed on `findByText(<pre-built note>)` because a toast was raised and the controls stayed enabled; the 'boom' test passed and pins the unchanged path. Semantic assessment: failures are the planned assertions, not setup faults. (The `gsd_run check tdd-red-evidence` classifier was not run; the plan is `type: execute` with TDD tasks, and the RED runs above are the plan's recorded evidence.)

## Verification results

- `npx vitest run` of ITAMReportsPanelTenantRule, ITAMReportsPanelStaleResponse, ITAMReportsPanel, ITAMConsole and ITAMKpiPanel tests: 5 files, 121 tests passed.
- `npx vitest run src/__tests__`: 136 files, 2278 tests passed (no pre-existing failure to record).
- `npm run typecheck`: no errors. `npm run build`: built in 4.71s.
- Task 1 verify run (ITAMConsole, ITAMReportsPanelTenantRule, ITAMKpiPanel): 3 files, 75 tests passed.
- Acceptance greps: `(isSuperAdminView || isPlatformView) && !tenantId` 1; `isPlatformView` in ITAMConsole.tsx 6; the App.tsx prop and import lines 1 each; `git diff PLAN_HEAD_BEFORE HEAD -- App.tsx` changed-line count 4; `export const SELECT_TENANT_RE` 1; `const blocked = needsTenant || tenantRejected` 1; `takeTenantRejection(e)` 4; `SELECT_TENANT_RE` in ReportsPanel.tsx 2; `setTenantRejected(false)` inside the tenant-change effect 1; `builderOpen && !blocked` 1. Line counts: ITAMConsole.test.tsx 455, ITAMReportsPanelTenantRule.test.tsx 340, ReportsPanel.tsx 367 (all under 500).

## User hunks (PROH-78-17, T-78-41)

Staged with the patch rule (App.tsx) and the insertion rule (ReportsPanel.tsx, ITAMConsole.test.tsx); `git diff --cached --quiet` held after every commit. After the last commit the numstat is identical to the start: App.tsx 21/15, components/itam/ReportsPanel.tsx 0/1, services/apiService.ts 10/0, src/__tests__/ITAMConsole.test.tsx 0/1, src/__tests__/ITAMReportsPanel.test.tsx 4/3. HEAD's App.tsx lacks `const handleSetUserPassword` (0) while the working tree has it (1); the HEAD captures of ReportsPanel.tsx and ITAMConsole.test.tsx still carry their lint lines once. services/apiService.ts and src/__tests__/ITAMReportsPanel.test.tsx were neither edited nor staged (both still ` M`). No stash, checkout, restore or reformat was used.

## Deviations from Plan

None - plan executed exactly as written. One placement note: the plan asked only for the pre-built note, Run buttons, custom note, Create button and builder to switch to `blocked`; the saved-list Loading line, empty state and table were switched as well (listed under key-decisions) so a rejected list never shows 'No custom reports yet' beside the custom note.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; the server's 400/403 are untouched (PROH-78-16, T-78-40 accepted). T-78-39 mitigated: no request and no toast for any platform tier without a tenant, and the server detail is pattern-matched only.

## User Setup Required

None - no external service configuration required. The UI is not published and nothing was restarted or pushed (the user's). UAT test 1 in 78-UAT.md stays pending for the user's post-deploy check.

## Next Phase Readiness

Round-2 fix plans 78-12..78-15 are all executed; Phase 78 is ready for re-verification and the post-deploy live check. Open observation (A-78-39, unchanged by this plan): the Select block copy ("Open a tenant from Tenants...") reads slightly off for Platform Support, who can never choose a tenant.

---
*Phase: 78-organization-endpoint-cost-api*
*Completed: 2026-11-17*

## Self-Check: PASSED

- Files exist: App.tsx, components/itam/ITAMConsole.tsx, ItamKpiPanel.tsx, ReportsPanel.tsx, src/__tests__/ITAMConsole.test.tsx, src/__tests__/ITAMReportsPanelTenantRule.test.tsx.
- Commits are ancestors of HEAD: 5bf03c54f, 2017d7cf0, 65236cf54, 747b2b972.
