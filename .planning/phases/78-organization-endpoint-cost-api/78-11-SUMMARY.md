---
phase: 78-organization-endpoint-cost-api
plan: 11
subsystem: ui
tags: [itam, reports, react, tenant-isolation, request-sequence, vitest, gap-closure]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: ReportsPanel tenant threading and clear-on-switch (78-06)
provides:
  - ReportsPanel request-sequence guard (runSeq) on every async writer, so a response issued for a previous tenant or a superseded request never renders
  - resultIsCurrent render gate with an exception for the unsaved builder preview
  - Console-level and panel-level stale-response tests (8 new tests)
affects: [phase-78-reverification, phase-78-security-audit]

actuals:
  tokens: 4250
  tasks: 2
  commits: 4
plan_head_before: edbb1bb464ec69b425babde70a043638c3882fb4
plan_head_after: 5278952bd4ccfca1164dae9ec9d2501e1e695c6d

tech-stack:
  added: []
  patterns:
    - "Request-sequence ref (runSeq): every async writer takes ++runSeq.current, a tenant switch bumps it, a response whose seq is stale is dropped without writing state or toasting, and running is cleared only by the current request"
    - "Stale-response tests hold the first call with a deferred promise, rerender with the new tenant, resolve inside act with a 20 ms flush, then assert absence"

key-files:
  created:
    - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
  modified:
    - components/itam/ReportsPanel.tsx
    - src/__tests__/ITAMConsole.test.tsx

key-decisions:
  - "The verifier's literal gate (activeKind && activeKey) would hide every unsaved builder preview, so the gate is resultIsCurrent = Boolean(activeKind && activeKey) || showingPreview, and the preview is guarded by the same runSeq rule (A-78-19)"
  - "A builder preview supersedes any in-flight run: it takes a new seq and clears running itself, since the dropped run would otherwise leave Loading on"
  - "Custom report tenant handling left exactly as is (PROH-78-08): runItamCustomReport, previewItamCustomReport and the custom export carry no tenant argument; WR-02 still awaits the user's call"

patterns-established:
  - "Guard every async state writer in a tenant-scoped panel with a sequence ref, not only the one the review named"

requirements-completed: [COST-07]

coverage:
  - id: D1
    description: "A pre-built run issued for tenant A that resolves after the switch to tenant B renders no title, rows or export buttons under tenant B, and a later run for B shows normally"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMConsole.test.tsx#a pre-built run for the previous tenant that resolves after the switch renders nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "A saved custom run or an unsaved builder preview issued before a tenant switch renders nothing when it resolves after"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#a saved custom run issued before a tenant switch renders nothing when it resolves after"
        status: pass
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#a builder preview that resolves after the tenant switch renders nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "Out-of-order runs in one tenant end on the later-issued run; switching to no tenant clears Loading at once; a superseded failure raises no toast; a same-tenant rerender keeps the result"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx (out of order, switching to no tenant, fails after the switch, same tenant)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The unsaved builder preview still renders its rows and offers no export"
    requirement: COST-07
    verification:
      - kind: unit
        ref: "src/__tests__/ITAMReportsPanelStaleResponse.test.tsx#the unsaved builder preview still renders its rows and offers no export"
        status: pass
    human_judgment: false
  - id: D5
    description: "Frontend suite and production build stay green"
    verification:
      - kind: other
        ref: "npx vitest run src/__tests__ (135 files, 2242 tests passed); npm run build exit 0"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-17
status: complete
---

# Phase 78 Plan 11: ReportsPanel stale-response guard Summary

**A runSeq request-sequence guard on every ReportsPanel async writer, so a report response issued for a previous tenant or a superseded request is dropped instead of rendering under the new tenant; closes the one gap in 78-VERIFICATION.md (WR-01 / UI-SPEC R3 / T-78-15).**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-11-17T05:11:43Z
- **Completed:** 2026-11-17T05:16:01Z
- **Tasks:** 2
- **Files modified:** 3 (1 created)

## Accomplishments
- `runSeq` ref in `components/itam/ReportsPanel.tsx`: `runPrebuilt`, `runSavedCustom` and `handlePreviewCustom` each take `++runSeq.current`; the tenant-change effect bumps it and resets `running`; a response or failure whose seq is stale is dropped with no state write and no toast; `running` is cleared only by the current request.
- `resultIsCurrent` render gate (`(running || result) && resultIsCurrent`) with a `showingPreview` flag so the unsaved builder preview, which renders with `activeKind` and `activeKey` null by design, still shows and still has no export buttons.
- Tenant threading from 78-06 kept verbatim: `runItamPrebuiltReport(key, targetPage, PAGE_SIZE, tenantId)`; custom run, preview and custom export still carry no tenant argument.
- Tests: the verifier's console-level test plus 7 ReportsPanel tests (saved run, switch to no tenant, out-of-order runs, superseded failure, preview renders, stale preview, same-tenant rerender).

## Task Commits

1. **Task 1 RED: tracer test** - `0cebd4d9d` (test)
2. **Task 1 GREEN: runSeq guard on runPrebuilt + tenant-change reset** - `b26ea046e` (fix)
3. **Task 2 RED: ReportsPanel stale-response tests** - `ebdca3fd7` (test)
4. **Task 2 GREEN: guard saved run and preview, resultIsCurrent gate** - `5278952bd` (fix)

**Plan metadata:** docs(78-11) commit follows this file.

## RED evidence (TDD)

- **Task 1:** before the GREEN edit, `npx vitest run src/__tests__/ITAMConsole.test.tsx` gave 1 failed, 27 passed. The failing test was `a pre-built run for the previous tenant that resolves after the switch renders nothing`, failing at the first absence assertion (`expect(screen.queryByText('Laptop 1')).not.toBeInTheDocument()` found the stale `<td title="Laptop 1">`). Not an import, mock or fixture error: the held call was made for `('asset_value', 1, 50, 't-1')`, the console was rerendered with `t-2`, and the 20 ms act flush let the late write land. Semantic assessment: target test executed and failed on the planned assertion for the planned reason. (Vitest default reporter output was used; the TAP-format classifier was not run.)
- **Task 2:** before the GREEN edit, `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx` gave 2 failed, 5 passed. T-a (`a saved custom run issued before a tenant switch renders nothing when it resolves after`) failed on `queryByText('IT-OLD')` finding the stale cell; T-f (`a builder preview that resolves after the tenant switch renders nothing`) failed on `queryByText('IT-PREVIEW')`. The other five (switch to no tenant, out-of-order, superseded failure, preview renders, same-tenant rerender) passed through Task 1 or pin unchanged behaviour, as the plan predicted.

## Verification

- `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx`: 3 files, 62 tests passed.
- `npx vitest run src/__tests__`: 135 files, 2242 tests passed, 0 failed.
- `npm run build`: exit 0 (built in 4.4 s; output goes to the git-ignored `dist-new`, nothing published).
- No pytest run (frontend-only plan); no background process left running.
- All acceptance greps for both tasks print the expected counts (runSeq.current: 1 in the reset block, 4 in runPrebuilt, 4 in runSavedCustom, 2 in preview; `setShowingPreview(true)` once; `resultIsCurrent` twice; custom calls unchanged; ReportsPanel.tsx 427 lines, ITAMConsole.test.tsx 404, new file 207, all under 500).

## User work preserved

Staging used the plan's patch reverse-apply plus `git update-index` for the two user-modified files; `git add` of a whole user file, stash, checkout and restore were never used.
- `HEAD:components/itam/ReportsPanel.tsx` still contains the `eslint-disable-next-line react-hooks/exhaustive-deps` line (1), `git diff` still shows its removal (`0 1` numstat).
- `HEAD:src/__tests__/ITAMConsole.test.tsx` still contains `eslint-disable-next-line no-bitwise` (1), `git diff` still shows its removal (`0 1` numstat).
- `App.tsx`, `services/apiService.ts` and `.planning/ui-reviews/.gitignore` were neither edited nor staged and are still ` M`.
- `git diff --cached --quiet` exits 0 after every commit.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0. **Impact:** none.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. T-78-27 (stale async writers after a tenant switch) is mitigated in code and tests; T-78-28 (user hunks) held. Closing T-78-15 in 78-SECURITY.md and restoring COST requirements belong to the security audit and re-verification that follow; neither file was edited here.

## Not done (by instruction)

No deploy, UI publish, backend restart or git push. 78-REVIEW WR-02 (custom report tenant handling) is untouched and still awaits the user's decision.

## Self-Check: PASSED

- FOUND: src/__tests__/ITAMReportsPanelStaleResponse.test.tsx, components/itam/ReportsPanel.tsx, src/__tests__/ITAMConsole.test.tsx
- FOUND commits: 0cebd4d9d, b26ea046e, ebdca3fd7, 5278952bd (all ancestors of HEAD)
