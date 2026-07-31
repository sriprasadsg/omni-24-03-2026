---
phase: 16-program-control-grouping
reviewed: 2026-07-04T05:40:04Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - App.tsx
  - components/Sidebar.tsx
  - types.ts
findings:
  critical: 1
  warning: 1
  info: 1
  total: 3
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-07-04T05:40:04Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the actual uncommitted diff (confirmed via `git diff HEAD -- App.tsx components/Sidebar.tsx types.ts`, 4 lines changed total) that wires `ProgramsDashboard` into the app: a lazy import + `case 'programs':` in `App.tsx`, a nav item in `components/Sidebar.tsx`, and the `'programs'` union member in `types.ts`. This follows up on `16-VERIFICATION.md`'s finding that `ProgramsDashboard.tsx` existed but was never reachable.

The lazy-import pattern, `ErrorBoundary` usage, icon reuse (`ClipboardListIcon`, already imported), and the exported component name (`export const ProgramsDashboard`) all match sibling entries correctly. However, the change is incomplete: `App.tsx`'s `viewPermissionMap` (`Record<AppView, Permission>`, App.tsx:211) was not updated to include a `programs` key. This is a real, verified defect — `npx tsc --noEmit` on the working tree fails with `TS2741: Property 'programs' is missing in type ... but required in type 'Record<AppView, Permission>'`, and the project's own CI (`.github/workflows/ci.yml:93`) runs exactly this command, so the change as submitted breaks the frontend CI job. Because `vite build` (the actual `npm run build` script) does not perform type-checking, if this slipped past CI, at runtime `viewPermissionMap['programs']` would be `undefined`, silently blocking non-super-admin, non-"all"-permission users from ever navigating to the view they can see in the sidebar — reintroducing (via a different mechanism) the exact "unreachable feature" bug this change set was supposed to fix.

## Critical Issues

### CR-01: `programs` view missing from `viewPermissionMap`, breaking the type contract and blocking navigation at runtime

**File:** `App.tsx:211-385` (map definition), `App.tsx:1247-1253` (consumer), `types.ts:23` (new union member)

**Issue:**
`types.ts` adds `'programs'` to the `AppView` union, and `App.tsx` adds a `case 'programs':` route and a lazy import, but `viewPermissionMap` — typed as `Record<AppView, Permission>` — has no `programs:` entry. Every other view added in this same "Governance & Compliance" group (`complianceEvidence`, `remediationWorkflow`, `complianceFrameworks`, `customFrameworks`, etc.) does have a corresponding `viewPermissionMap` entry, so this omission breaks an established, load-bearing convention.

Verified impact, not speculative:
1. **Compile break:** Ran `npx tsc --noEmit -p tsconfig.json`, which reports:
   ```
   App.tsx(211,7): error TS2741: Property 'programs' is missing in type '{ dashboard: "view:dashboard"; ... }' but required in type 'Record<AppView, Permission>'.
   ```
2. **CI break:** `.github/workflows/ci.yml` line 93 runs `npx tsc --noEmit` in the `frontend` job before `npm run build` and `eslint`, so this change fails CI as submitted.
3. **Runtime break (if the type error is ever bypassed, e.g. a local `vite build` which skips type-checking):** `handleSetCurrentView` (App.tsx:1240-1254) does:
   ```ts
   const requiredPermission = viewPermissionMap[view]; // undefined for 'programs'
   if (hasPermission(requiredPermission)) { setCurrentView(view); } else { console.warn(...); }
   ```
   `hasPermission(undefined)` (App.tsx:1090-1097) returns `true` only for super-admins or users whose effective permissions include `'all'`; for every other user it evaluates `effectiveFeatures.includes(undefined)` → `false`. Meanwhile the Sidebar nav item is gated on `'view:compliance'` (a real, commonly-granted permission), so the "Programs" link **is visible** to normal compliance users but clicking it silently no-ops (only a `console.warn`, no user-facing feedback) — the feature remains unreachable for the exact audience this phase intended to unblock.
4. As a secondary consequence of the same missing key, the hash-navigation fallback (`App.tsx:571`, `Object.keys(viewPermissionMap).find(key => key.toLowerCase() === hash)`) can never resolve `#programs` to the `programs` view either, since `'programs'` isn't a key of the map.

**Fix:**
Add the missing entry to `viewPermissionMap` (consistent with the sibling `compliance`/`complianceEvidence`/`remediationWorkflow` entries which all use `'view:compliance'`):
```ts
// App.tsx, inside viewPermissionMap
compliance: 'view:compliance',
programs: 'view:compliance',   // <-- add this line
complianceEvidence: 'view:compliance',
```

## Warnings

### WR-01: No local safeguard against this class of "new AppView added without updating dependent maps" regression

**File:** `App.tsx:211`

**Issue:** `viewPermissionMap`'s `Record<AppView, Permission>` typing is the *only* thing that would have caught this (and did, via `tsc`), but there is no `npm run typecheck` script and no pre-commit/local hook wired to it — the omission was only catchable by CI, and would not have been caught by a developer running `npm run build` locally (since `vite build` does not type-check). This is exactly the kind of gap that let phase 16's original defect (`ProgramsDashboard` existing but never wired in) go undetected in the first place, and it nearly reintroduced a variant of the same class of bug.

**Fix:** Add a `"typecheck": "tsc --noEmit"` script to `package.json` and document (e.g. in CLAUDE.md or CONTRIBUTING) that it must be run before committing changes that add/remove an `AppView` member, so the omission surfaces locally instead of only in CI.

## Info

### IN-01: New `programs` view has no explicit hash-navigation shortcut

**File:** `components/Sidebar.tsx` (nav item), `App.tsx:560-569` (`hashToView` map)

**Issue:** Other governance/compliance-adjacent views in the friendly-URL `hashToView` map (e.g. `'compliance'`, `'aigovernance'`) have explicit short-hash entries. `'programs'` relies solely on the `Object.keys(viewPermissionMap).find(...)` case-insensitive fallback (which, per CR-01, doesn't work until `programs` is added to `viewPermissionMap` anyway). Once CR-01 is fixed, `#programs` will resolve via the fallback path, but for consistency with sibling views an explicit entry could be added.

**Fix (optional, cosmetic):**
```ts
const hashToView: Record<string, AppView> = {
  ...
  'programs': 'programs',
};
```

---

_Reviewed: 2026-07-04T05:40:04Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
