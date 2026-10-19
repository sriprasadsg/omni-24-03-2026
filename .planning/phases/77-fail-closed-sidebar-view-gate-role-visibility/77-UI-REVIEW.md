# Phase 77 - UI Review

**Audited:** 2026-10-19
**Baseline:** 77-UI-SPEC.md (design contract)
**Screenshots:** not captured (code-only audit; no dev server listening on 3000/5173/8080 and the phase is not deployed)
**Interaction captures:** off

Scope: the phase's new and rewritten UI: `components/NoAccessPanel.tsx`, `components/ZeroAccessScreen.tsx`, `components/Sidebar.tsx`, `components/RoleVisibilityPanel.tsx`, `components/RoleEditorModal.tsx`, `components/SettingsRolesTab.tsx` (Roles tab and delete flow), `components/Dashboard.tsx` / `components/NotificationCenter.tsx` (hidden widgets), with `utils/viewAccess.ts`, `utils/rolePermissions.ts` and `utils/permissionRefresh.ts` behind them. Audit run by gsd-ui-auditor; file written by the orchestrator from the auditor's report. Findings 1 and 2 were spot-checked against the source by the orchestrator.

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Every contract string matches verbatim in the audited files |
| 2. Visuals | 3/4 | Good hierarchy, icon+text markers and aria; unspecified numeric badge on role rows; two editor icons lack `aria-hidden` |
| 3. Color | 2/4 | Accent used outside the reserved list (permission-count badge); editor footer buttons have no focus ring |
| 4. Typography | 2/4 | `font-medium` (500) on new/rewritten elements; contract allows 400 and 600 only |
| 5. Spacing | 3/4 | Mostly on the 4px scale; half-step utilities (`py-1.5`, `gap-1.5`, `mr-1.5`) copied into new elements |
| 6. Experience Design | 4/4 | Full state coverage: skeletons, deny-by-default, retry in-flight guard, delete pending/confirm/refusal, editor locked/implied rows |

**Overall: 18/24**

## Top Fixes (priority order)

1. **WARNING - Color: accent on the permission-count badge.** `components/SettingsRolesTab.tsx:108-109` renders `bg-primary-100 text-primary-800` on a bare `role.permissions.length`. The contract reserves the accent for an exhaustive list, and the badge sits on every row with no label, so the number's meaning is not conveyed. Fix: neutral gray plus `aria-label`/`title` "N permissions", or remove it.
2. **WARNING - Accessibility/Color: no focus ring on the editor footer.** `components/RoleEditorModal.tsx:149,154` (Cancel, Save) use `focus:outline-none` with no ring; the contract requires a visible focus ring on every new interactive control. Fix: `focus:ring-2 focus:ring-primary-500 focus:ring-offset-2`. (Permission checkboxes already use `focus:ring-primary-500`.)
3. **WARNING - Typography: `font-medium` on rewritten elements.** `RoleEditorModal.tsx` (lines ~149, 154, 166, 177, 183) and `SettingsRolesTab.tsx` (New Custom Role button, row name cell, "What it can see" button). Both files were rewritten this phase, so the legacy exemption does not apply. Fix: `font-semibold` for buttons; `font-normal` or `font-semibold` for labels.
4. **WARNING - Spacing: half-step utilities in new elements.** "What it can see" button `px-1.5 py-1`; New Custom Role button `px-3 py-1.5` and icon `mr-1.5`; RoleVisibilityPanel legend `gap-1.5`; some 12px padding. Fix: `py-2`/`gap-2` or `py-1`/`gap-1`, `px-2` or `px-4`.
5. **WARNING - Visuals/a11y: decorative icons without `aria-hidden`.** `RoleEditorModal` `ShieldLockIcon` (~line 187) and the `AlertTriangleIcon` in the save-error block. `LockIcon` is correct.
6. **WARNING - Visuals: editor group header style.** Editor group headers use `text-sm font-semibold` instead of the contract's 12px uppercase tracking-wider group style; the ceiling banner uses `ShieldLockIcon` where the contract describes the plain blue info banner. Minor.
7. **Minor:** `Custom` chip has no icon (not required; `Built-in` has one); RoleVisibilityPanel legend glosses inherit text color instead of explicit muted classes; "Try again" (RoleVisibilityPanel) and "Expand all" buttons have no focus ring; ZeroAccessScreen `min-h-[20px]` is an arbitrary value, but the contract specifies it.

## Evidence by Pillar

### 1. Copywriting (4/4)

Checked against the contract and matching: in-place heading, the three reason variants, "Required permission", "Your access was updated by an administrator.", "Nothing on this screen is available to your role yet."; full-page title, body, identity labels, "Checking...", "Still no screens...", the retry error; role panel summary, basis variants, "Switched off for this tenant", empty state, error with "Try again"; editor ceiling banner, locked text, "Included with Manage", name-collision message, name-locked helper, save-error variants, success toast; delete flow "Keep role", "Delete role", "Can't delete ... yet", "Sign-in mappings"; the "No custom roles yet..." helper; the "Retry permission check" aria-label.

### 2. Visuals (3/4)

NoAccessPanel and ZeroAccessScreen follow the anatomy: icon circle, `tabIndex=-1` heading focused on mount, `max-w-lg` / `max-w-md` cards, brand tile, identity `dl` with `truncate` and `title`. Markers always carry icon plus text. Group expanders are real buttons with `aria-expanded` / `aria-controls`. The role panel has `role="region"`, `aria-label` and `aria-busy`. Deductions: fixes 5 and 6, and the unlabeled numeric badge (fix 1).

### 3. Color (2/4)

Hardcoded hex only in the contract-specified `#f8fafc` / `#0b1220` backgrounds. Primary buttons and amber/blue/red usage otherwise follow the contract; markers and chips are neutral; amber is limited to switched-off. Deductions: fixes 1 and 2. The editor's disabled primary state (`disabled:bg-primary-400/50`) is faint and may be low contrast; not measured.

### 4. Typography (2/4)

Sizes stay within `text-xs`, `text-sm`, `text-lg`, `text-2xl`; no `text-base`, `text-xl` or `text-3xl` in the audited files. Permission strings use `font-mono text-xs` as specified. Deduction: fix 3.

### 5. Spacing (3/4)

`p-8`, `gap-4`, `gap-6`, `pt-12`, `p-6` and `gap-2` match the contract; the 32px hit target is met through `min-w-8 min-h-8`. Deduction: fix 4.

### 6. Experience Design (4/4)

- Gate and screens: ViewGate shows `SkeletonDashboard` while permissions are unknown, then the allowed screen or NoAccessPanel. The sidebar uses `permissionsKnown`, `hasPermission` defaults to deny (`Sidebar.tsx:182`), and it renders skeleton rows. Retry is guarded by an `inFlight` ref with a `motion-safe:` spin, an `aria-live` status line and a `role="alert"` error; Sign out is never disabled. `AllPartsHiddenNotice` exists and is wired in Dashboard.
- Role list and panel: delete has an in-flight state (`opacity-60`, spinner, `aria-busy`), a confirmation modal and a refusal modal. The role panel handles loading, error, empty and populated states and refetches on its dependencies. Built-in rows have Edit `aria-disabled` and no Delete.
- Editor: name locked on edit; implied and locked permissions handled; submit sends exactly what is visibly checked; server errors keep the modal open; Save guarded while the catalogue loads.
- Not verified (needs a runtime check): the "all parts hidden" flow beyond Dashboard, and whether the sidebar's active group stays open after a permission refresh. `RoleDeleteRefusalModal` and `Dashboard` were read only by grep.

## Recommendation Count

- Priority fixes: 3 (items 1-3)
- Minor recommendations: 4 (items 4-7)
- Blockers: 0

Registry audit: skipped (shadcn not initialized; the UI-SPEC lists no third-party registries).

## Files Audited

- components/NoAccessPanel.tsx
- components/ZeroAccessScreen.tsx
- components/Sidebar.tsx
- components/RoleVisibilityPanel.tsx
- components/RoleEditorModal.tsx
- components/SettingsRolesTab.tsx
- components/Dashboard.tsx (grep)
- components/NotificationCenter.tsx
- utils/viewAccess.ts, utils/rolePermissions.ts, utils/permissionRefresh.ts
