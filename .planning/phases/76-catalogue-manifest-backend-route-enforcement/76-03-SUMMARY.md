---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 03
subsystem: ui
tags: [rbac, catalogue-manifest, sidebar, vitest, react]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: shared/catalogue-access.json (202 catalogues, 188 nav) and utils/catalogueAccess.ts reader (plans 01, 02)
provides:
  - NAV_GROUPS, viewForHash, findNavDrift in utils/catalogueAccess.ts
  - components/sidebarPresentation.tsx (SIDEBAR_PRESENTATION: icon, minTier, featureKey for 188 views)
  - Sidebar.tsx built from the manifest; App.tsx permission and hash lookups from the manifest
  - D-06 drift test with negative controls; D-11 single-permission checks
affects: [76-11]

actuals:
  tokens: 28000
  tasks: 3
  commits: 5
plan_head_before: df584f789bdf1e0a0db03d182d9bb544cf918056
plan_head_after: 88c8d0c202216b39606452ece58aff6670365eac

tech-stack:
  added: []
  patterns:
    - "Sidebar = NAV_GROUPS (manifest order) joined with SIDEBAR_PRESENTATION by view; only presentation is local"
    - "findNavDrift(navViews, presentationViews) names drift in both directions"

key-files:
  created:
    - components/sidebarPresentation.tsx
  modified:
    - utils/catalogueAccess.ts
    - src/__tests__/catalogueAccess.test.ts
    - components/Sidebar.tsx
    - App.tsx

key-decisions:
  - "CatalogueEntry.read/write typed string[] (backend-only lists); only .permission is typed Permission, because 8 read/write strings are not members of the frontend Permission union"
  - "App.tsx keeps the old undefined-permission flow (hasPermission(viewPermission(view) as Permission)); fail-closed is Phase 77"
  - "The Sidebar local variable is menuGroups, not navGroups, so the 76-02 two-state check sees the manifest-backed state"

requirements-completed: [ACC-03, ACC-05]

coverage:
  - id: D1
    description: "Sidebar groups/items come from the manifest in manifest order; no item-level permission literal remains"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts#NAV_GROUPS and #sidebar presentation vs manifest (D-06)"
        status: pass
      - kind: unit
        ref: "src/__tests__/SidebarAuditFixes.test.tsx"
        status: pass
    human_judgment: false
  - id: D2
    description: "App.tsx resolves permission and hash route from the manifest; its Record<AppView,Permission> table is gone"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts#App.tsx lookups (ACC-03)"
        status: pass
      - kind: command
        ref: "npm run build"
        status: pass
    human_judgment: false
  - id: D3
    description: "Nine mismatched views each resolve to the single Sidebar string (D-11)"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts#single permission per view (D-11)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Drift test fails on a nav entry with no presentation entry and the reverse (D-06)"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts#findNavDrift (D-06)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual check that the super-admin sidebar looks and orders exactly as before (EDGE-ACC-03-ordering)"
    verification: []
    human_judgment: true
    rationale: "Order equals manifest array order, which 76-02 asserts equals the old Sidebar order; no screenshot comparison was run."

duration: 9min
completed: 2026-10-13
status: complete
---

# Phase 76 Plan 03: Frontend on the Manifest Summary

**Sidebar.tsx and App.tsx now read one manifest through utils/catalogueAccess.ts; the inline navGroups table and App's 206-line viewPermissionMap are deleted, icons/tier/feature keys live in a separate presentation map, and a vitest drift test fails on mismatch in either direction.**

## Accomplishments
- `utils/catalogueAccess.ts` gained `NAV_GROUPS` (8 groups, 188 nav items, manifest order, no sort), `viewForHash` (case-insensitive over all 202 views) and `findNavDrift`.
- `components/sidebarPresentation.tsx` (206 lines) holds one line per nav view: icon, `minTier`, `featureKey`, generated mechanically from the old literal. `Sidebar.tsx` went from 544 to 325 lines; `visibleGroups`, tier locking, feature keys and the badge logic are untouched.
- `App.tsx` lost the `viewPermissionMap` block (4 insertions, 209 deletions); hash fallback uses `viewForHash`, `handleSetCurrentView` uses `viewPermission`.
- The nine D-11 views resolve to exactly the Sidebar string in both the reader and `NAV_GROUPS`.

## Task Commits
1. RED `c55d6589a` (test): 18 of 22 tests failed ("findNavDrift is not a function", NAV_GROUPS undefined)
2. GREEN `1feace133` (feat): reader extended, 21 of 22 pass
3. `1ad57db83` (fix): typed read/write as string[] and scoped the union check, 23 of 23 pass
4. `d74a64a49` (feat): Sidebar rewired + presentation map + drift test
5. `88c8d0c20` (feat): App.tsx rewired + source check

## TDD Gate Compliance
RED `c55d6589a` precedes GREEN `1feace133`. RED assessment: the target describes (`NAV_GROUPS`, `viewForHash`, `findNavDrift`) failed on missing exports (TypeError / undefined), the planned behaviour, not on a fixture or syntax error; the 4 already-passing tests are characterisation of existing exports (viewPermission, unions). No REFACTOR commit. Note: `1feace133` was committed with one failing test (the Permission-union test, a plan assumption error); `1ad57db83` fixed it immediately.

## Numbers
- vitest before: 209 baseline (plan) ; after `npx vitest run src/__tests__`: 28 files, 235 passed. catalogueAccess.test.ts: 2 -> 26 tests (+SidebarAuditFixes still green).
- `npm run build`: exit 0, writes dist-new/ (not deployed). Sidebar.tsx 325 lines, sidebarPresentation.tsx 206.
- `backend/tests/test_catalogue_manifest.py`: 15 passed; its Sidebar/App check moved to the "reads the manifest" state.
- `tsc --noEmit` shows no error in Sidebar, sidebarPresentation or catalogueAccess.

## Deviations from Plan

**1. [Rule 1 - Bug] Plan assumption: every manifest read/write string is a Permission member**
- **Found during:** Task 1 (GREEN run)
- **Issue:** 8 strings in read/write lists (`manage:approvals`, `manage:assets`, `manage:compliance`, `manage:procurement`, `manage:secrets`, `manage:users`, `request:assets`, `view:secrets`) are not in the frontend `Permission` union, though the backend grants them.
- **Fix:** `CatalogueEntry.read/write` typed `string[]`; the union test covers `.permission` (all members), and a second test pins the 8 backend-only strings. `types.ts` and the manifest were not edited (outside this plan's files; wave-3 must not edit the manifest).
- **Files modified:** utils/catalogueAccess.ts, src/__tests__/catalogueAccess.test.ts
- **Commit:** 1ad57db83

**Total deviations:** 1 auto-fixed (Rule 1). **Impact:** none on scope.

## Behaviour changes worth knowing (not regressions)
- D-08 from 76-02: Subscription Plan, Invoices and Knowledge Base used `view:dashboard` in the old Sidebar literal and now need `manage:settings` (manifest decision). Roles holding view:dashboard but not manage:settings lose those three sidebar entries and their App route.
- The nine D-11 views previously used weaker strings in App (for example swarm via `view:dashboard`); App now requires the Sidebar string (T-76-09).
- Group/item order equals manifest order; 76-02 asserts that equals the old order (EDGE-ACC-03-ordering unconfirmed visually).

## For 76-11 (manifest/type corrections found, not applied)
- Add the 8 backend-only strings above to `Permission` in types.ts if the frontend should ever type them, or leave as is.
- No manifest label/permission/order differences from the old Sidebar literal other than the D-08 trio (checked mechanically for all 188 items).

## Issues Encountered
- The post-tool context hook reported 92% usage repeatedly; the token budget was ample and nothing was truncated.
- Files outside this plan with uncommitted changes (src/__tests__/ITAMConsole.test.tsx, ITAMReportsPanel.test.tsx, remoteControl.test.ts, setup.ts and untracked tests) were not touched. App.tsx, Sidebar.tsx and the reader carried no unrelated hunks.

## Known Stubs
None.

## Threat Flags
None. No endpoints or auth paths added; T-76-09 mitigated (single lookup, nine views pinned); T-76-10 accepted (sidebar is cosmetic, backend guards enforce).

## Self-Check: PASSED
- components/sidebarPresentation.tsx, utils/catalogueAccess.ts, src/__tests__/catalogueAccess.test.ts exist; commits c55d6589a, 1feace133, 1ad57db83, d74a64a49, 88c8d0c20 are on HEAD.
- Plan verification: vitest src/__tests__ 235 passed, npm run build exit 0, manifest pytest 15 passed.

---
*Phase: 76-catalogue-manifest-backend-route-enforcement*
*Completed: 2026-10-13*
