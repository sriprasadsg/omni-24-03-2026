---
phase: 78-organization-endpoint-cost-api
plan: 14
subsystem: ui
tags: [itam, reports, custom-reports, react, tenant-isolation, x-tenant-id, vitest, gap-closure]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: server-side custom report tenant resolution (78-12), ReportsPanel shown/pending split and tenantEpoch (78-13), D-13 and D-14 amended 2026-11-17
provides:
  - listItamCustomReports, saveItamCustomReport, deleteItamCustomReport, previewItamCustomReport and runItamCustomReport send X-Tenant-ID (optional trailing tenantId); the custom export does too
  - ReportsPanel saved list that follows tenant switches (listSeq guard, cleared at the switch) and save/delete guarded by tenantEpoch
  - custom section no-tenant state: no list request, role-status note, Create Custom Report disabled, builder hidden
  - ITAM_KPI_COPY.customReportsSelectTenantNote
  - src/__tests__/ITAMReportsPanelTenantRule.test.tsx (21 tests)
affects: [78-15, phase-78-reverification, phase-78-security-audit]

actuals:
  tokens: 7400
  tasks: 3
  commits: 6
plan_head_before: 57eb1e98d9beca73abe5d04fe948c037b38e59c8
plan_head_after: fd11ee3175ccca835f0e8a44f680ee1af55c975c
commits: 6

tech-stack:
  added: []
  patterns:
    - "Every tenant-scoped client call takes a trailing tenantId and passes tenantId: tenantId || undefined to authFetch (same shape as runItamPrebuiltReport)"
    - "listSeq ref: only the latest saved-list load writes state; a no-tenant state bumps it so a load in flight is dropped"
    - "tenantEpoch captured before an await in save and delete; a moved epoch returns without side effects"

key-files:
  created:
    - src/__tests__/ITAMReportsPanelTenantRule.test.tsx
  modified:
    - services/apiService.ts
    - components/itam/ReportsPanel.tsx
    - components/itam/ItamKpiPanel.tsx
    - src/__tests__/ITAMConsole.test.tsx
    - src/__tests__/ITAMReportsPanel.test.tsx
    - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx

key-decisions:
  - "Every custom call passes the tenant as the trailing argument even when undefined (A-78-34), so tenant-user assertions in ITAMReportsPanel.test.tsx expect a trailing undefined"
  - "Under needsTenant the builder is hidden by the render condition (builderOpen && !needsTenant), not closed: builderOpen survives, but ReportBuilderForm unmounts, so its field entries (name, columns, filters) are reset when a tenant is chosen again"
  - "handleSaveCustom checks the epoch twice (after the save and after the list reload) so a switch during the reload also suppresses the toast and the run"

requirements-completed: [COST-07]
gap_ids: [G-78-WR02]

coverage:
  - id: D1
    description: "A Platform Owner's saved custom report runs, exports and deletes for the selected tenant; a tenant user's calls carry an explicit undefined tenant"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#runs and exports a saved custom report for the selected tenant"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanel.test.tsx#clicking delete opens the shared Modal and only calls deleteItamCustomReport after the confirm control is used"
        status: pass
    human_judgment: false
  - id: D2
    description: "All five custom report API functions send X-Tenant-ID with a tenant and none without"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#custom report transport carries the tenant"
        status: pass
    human_judgment: false
  - id: D3
    description: "The saved list reloads per tenant, is cleared at a switch, and a late list response for the previous tenant is dropped"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#hides the previous tenant's saved list at once and shows the new tenant's when it loads"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#drops a saved-list response for the previous tenant that resolves after the switch"
        status: pass
    human_judgment: false
  - id: D4
    description: "A save or confirmed delete that completes after a tenant switch does not reload, run or toast in the new tenant"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#a save that completes after a tenant switch neither reloads the list, runs the report nor toasts"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#a confirmed delete that completes after a tenant switch raises no toast"
        status: pass
    human_judgment: false
  - id: D5
    description: "With no tenant selected the custom section sends no request, shows the described note, disables Create Custom Report and hides the builder; choosing a tenant restores it; tenant users are unchanged"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelTenantRule.test.tsx#custom section with no tenant"
        status: pass
    human_judgment: false
  - id: D6
    description: "Visual look of the disabled Create Custom Report button and the note inside the saved-reports box in the live Reports tab (A-78-35 planner wording)"
    verification: []
    human_judgment: true
    rationale: "Copy wording was flagged in the plan (A-78-35) and the disabled styling is a visible change that tests do not judge; a post-deploy look decides it"

duration: 9 min
completed: 2026-11-17
status: complete
---

# Phase 78 Plan 14: Custom reports follow the one-tenant rule on the client Summary

**All five custom report API functions and the custom export now send the selected tenant as X-Tenant-ID, the saved-reports list follows tenant switches without ever showing the previous tenant's definitions, save and delete are bound to the tenant they started in, and a platform user with no tenant sees the custom section disabled with a note and sends no custom request.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-11-17T07:37:52Z
- **Completed:** 2026-11-17T07:46:38Z
- **Tasks:** 3 (6 commits: RED then GREEN per task)
- **Files modified:** 7 (1 created)

## Accomplishments

- G-78-WR02 closed on the client: a Platform Owner with a tenant selected lists, saves, previews, runs, exports and deletes custom reports for that tenant; the server (78-12) answers 400 without one, so the client no longer sends such calls.
- The saved list is reloaded for each tenant (`loadSavedReports` depends on `[tenantId, needsTenant]`), cleared in the tenant-switch effect, and written only by the latest load (`listSeq`), so a held list response for the previous tenant is dropped.
- `handleSaveCustom` and `handleDeleteConfirm` capture `tenantEpoch` and return without reloading, running, toasting or clearing when the Owner switched tenant meanwhile.
- No-tenant state: `listItamCustomReports` is never called, the note `ITAM_KPI_COPY.customReportsSelectTenantNote` (role status) replaces Loading / empty state / table, Create Custom Report is disabled with `aria-describedby` pointing at the note, the builder is hidden.
- Tenant users are unchanged (calls carry an undefined tenant, no note, Create enabled); pre-built runs and exports are unchanged.

## Task Commits

1. **Task 1 (tracer): run, export and delete carry the selected tenant**
   - RED `388af39c5` (test)
   - GREEN `b70ee6345` (fix)
2. **Task 2: list, save and preview carry the tenant; list follows switches; save/delete guarded**
   - RED `8e78e0695` (test)
   - GREEN `2a724b19a` (fix)
3. **Task 3: no-tenant state of the custom section**
   - RED `ee8cc7bff` (test)
   - GREEN `fd11ee317` (fix)

**Plan metadata:** the docs(78-14) commit that carries this SUMMARY, STATE.md and ROADMAP.md.

## RED evidence

- **Task 1:** before the GREEN edit 4 tests failed on their argument assertions and 65 passed: ITAMConsole "runs and exports a saved custom report for the selected tenant" (`runItamCustomReport` expected `['c-1', 1, 50, 't-1']`, received no tenant), ITAMReportsPanelStaleResponse "a saved custom run issued before a tenant switch renders nothing when it resolves after" (same call), ITAMReportsPanel "clicking delete ... confirm control" (expected `['rpt-abc123', undefined]`, received one argument) and "clicking an export button ..." (expected `['custom', 'rpt-abc123', 'csv', undefined]`, received three). No import, mock or fixture error. Semantic assessment: the target tests executed and failed on the planned assertions.
- **Task 2:** new file, 17 tests, 10 failed and 7 passed before the GREEN edit. Failed: transport `list`, `save` and `preview` sending X-Tenant-ID (header undefined), and every panel behaviour: list called with 't-1', save with `(object, 't-1')`, preview with `(object, 1, 50, 't-1')`, previous list hidden at a switch, late previous-tenant list dropped (new tenant's list never loaded, as no reload happened), save across a switch (list not reloaded for 't-2'), delete across a switch. Passed: transport `delete` and `run` (Task 1 made them tenant-aware) and the five "no X-Tenant-ID without a tenant" cases. The first draft of two of the panel mocks keyed on the tenant argument and so passed vacuously; they were changed to call-order mocks before the RED commit so they fail on the behaviour.
- **Task 3:** all four tests failed on the missing copy key (`getByText(undefined)`, as the plan predicted). To get evidence on the behaviour as well, a scratch run with the literal note text in place of the constant failed the three needsTenant behaviours on the missing note (no note element) and passed the tenant-user test (already true); the file was restored before the commit.
- The `gsd_run check tdd-red-evidence` classifier was not run: the plan is `type: execute`, the RED outcomes above come from real vitest runs.

## Verification

- `npx vitest run src/__tests__/ITAMReportsPanelTenantRule.test.tsx src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx src/__tests__/ITAMKpiPanel.test.tsx`: 5 files, 113 passed, 0 failed.
- `npx vitest run src/__tests__`: 136 files, 2270 passed, 0 failed.
- `npm run typecheck`: exit 0. `npm run build`: built in 4.16 s.
- Task 1 verify (3 suites): 69 passed; Task 2 verify (4 suites): 86 passed.
- Acceptance greps all met: `runItamCustomReport(reportId, targetPage, PAGE_SIZE, tenantId)` 1, `generateItamReport(kind, key, format, tenantId)` 1, `deleteItamCustomReport(target.id, tenantId)` 1, both signature greps 1, "without any tenant argument" 0, ITAMReportsPanel.test.tsx plan diff 4 changed lines, `tenantId: tenantId || undefined` 8, `listItamCustomReports(tenantId)` / `saveItamCustomReport(definition, tenantId)` / preview 1 each, `listSeq.current` in loadSavedReports 4, `tenantEpoch.current` in save 3 and in delete 3, copy constant line 1, `CUSTOM_SELECT_TENANT_NOTE_ID` 3, `ITAM_KPI_COPY.customReportsSelectTenantNote` 1, `builderOpen && !needsTenant` 1, `[tenantId, needsTenant]` 1. Line counts: ReportsPanel.tsx 347, ItamKpiPanel.tsx 296, TenantRule test 278 (below the 400, 480 and 500 limits).

## User hunks and user-modified files

- After every one of the six commits: `git diff --cached --quiet` exits 0; `git diff --numstat` is App.tsx 21/15, components/itam/ReportsPanel.tsx 0/1, services/apiService.ts 10/0, src/__tests__/ITAMConsole.test.tsx 0/1, src/__tests__/ITAMReportsPanel.test.tsx 4/3 (identical to the start); HEAD lacks `export const setUserPassword` (0) and the `ComponentProps` type import (0) and keeps both removed lint lines (`react-hooks/exhaustive-deps` 1, `no-bitwise` 1).
- Staging used the insertion rule (ReportsPanel.tsx, ITAMConsole.test.tsx) and the patch rule (apiService.ts, ITAMReportsPanel.test.tsx) with `git update-index --cacheinfo`; ItamKpiPanel.tsx, the stale-response test and the new test file were staged with `git add` of that one path. No stash, checkout, restore, clean or reformat was run.
- App.tsx was neither edited nor staged (`git status --short -- App.tsx` prints ` M App.tsx`).

## Decisions Made

See key-decisions. Assumptions A-78-33..A-78-37 were implemented as written; the one nuance is A-78-37: hiding the builder with `builderOpen && !needsTenant` keeps `builderOpen` true, but `ReportBuilderForm` unmounts, so its own field state (name, selected columns, filters) is lost and the builder reappears empty after a tenant is chosen again. This follows the plan's explicit render condition and is the safer behaviour for tenant-scoped content; recorded here because A-78-37 describes it as "the state it had".

## Deviations from Plan

None - plan executed exactly as written. Two notes that are not deviations: (1) commit messages carry no Co-Authored-By trailer because the project CLAUDE.md forbids one unless `.claude/settings.json` sets `attribution.commit` (it does not) and CLAUDE.md takes precedence over the harness attribution reminder, as in 78-12; (2) tracer feedback gate: `end-of-phase` mode with an automated-only verify, so the three suites and typecheck were re-run after the Task 1 GREEN edit and passed ("Tracer verified end-to-end - expanding").

## Issues Encountered

None. The RED commits for Tasks 2 and 3 reference new arguments and a new copy key, so `tsc` would flag them between the RED and GREEN commits; the GREEN commits restore a clean typecheck (verified after each GREEN edit).

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; the client now sends an existing header on more calls. T-78-36 (stale list, tenant-less custom calls) and T-78-37 (save or delete completing after a switch) are mitigated and tested; T-78-38 (user hunks) held as recorded above. PROH-78-14 and PROH-78-15 held.

## User Setup Required

None - no external service configuration required. The UI is not published, no service was restarted and nothing was pushed (the user's). Until the UI is published, the live Reports tab still sends no tenant on custom calls; once 78-12's backend is restarted, an Owner without a chosen tenant gets 400 there, which this plan's client handles by not sending the call.

## Next Phase Readiness

- 78-15 (IN-04 rejection tests) can add its cases to `ITAMReportsPanelTenantRule.test.tsx` (278 lines, room under 500).
- Phase re-verification and the security audit own 78-VERIFICATION.md, 78-SECURITY.md, 78-UAT.md and REQUIREMENTS.md statuses (not edited here). A post-deploy look at the disabled Create Custom Report button and the note wording (A-78-35) is the one human-judgment item (coverage D6).

## Self-Check: PASSED

- `src/__tests__/ITAMReportsPanelTenantRule.test.tsx`, `components/itam/ReportsPanel.tsx`, `components/itam/ItamKpiPanel.tsx`, `services/apiService.ts` exist.
- Commits `388af39c5`, `b70ee6345`, `8e78e0695`, `2a724b19a`, `ee8cc7bff`, `fd11ee317` are ancestors of HEAD; `git rev-list --count 57eb1e98d..HEAD` is 6.

---
*Phase: 78-organization-endpoint-cost-api*
*Completed: 2026-11-17*
