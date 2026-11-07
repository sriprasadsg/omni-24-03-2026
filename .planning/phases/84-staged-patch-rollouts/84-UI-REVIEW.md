# Phase 84 — UI Review

**Audited:** 2026-11-07
**Baseline:** 84-UI-SPEC.md (approved body). DEV-1..DEV-4 are not accepted by the user, so they are reported below as open deviations.
**Screenshots:** not captured (code-only audit; no build or preview was run, nothing published)
**Interaction captures:** off (workflow.ui_interaction_capture is false)

Scope: static class and string audit of `components/patchRollouts/*` (14 files). Spot checks of `AgentGroupsDashboard.tsx`, `AutonomousOpsDecisions.tsx` and `PatchManagementDashboard.tsx`. Visual and interaction claims are code-derived, not observed. I did not run the tests. Edits in `AgentGroupsDashboard.tsx` and `App.tsx` that belong to the user's work in progress were not scored against Phase 84.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | The chip and copy module is centralised and gated. One lowercase chip label (`not reached`) and an unverified `Loading...` string. |
| 2. Visuals | 3/4 | Chips always carry an icon and text, and icon buttons carry aria-labels. The Rollouts tab and card use no tabular numerals. Visual hierarchy was not observed. |
| 3. Color | 3/4 | Chip tones are the declared ones. The accent buttons are scoped. Some colour constants are redefined in many files, so drift is likely. |
| 4. Typography | 3/4 | Only text-xs, text-sm and text-lg are used, with semibold plus one font-normal (400). That fits the 4-size, 2-weight rule. `tabular-nums` is applied inconsistently. |
| 5. Spacing | 2/4 | Many off-scale `3` steps (12px) and `0.5` half-steps, against the contract's "No half-steps" and the 4/8/16/24 scale. |
| 6. Experience Design | 3/4 | Loading, error, empty and retry states exist. Button sizing relies on a per-file constant and sometimes on an appended `min-h-10`. The unaccepted DEVs change contract behaviour. |

**Overall: 17/24**

---

## Top 3 Priority Fixes

1. **Off-scale spacing across the new UI (WARNING)** — The visual rhythm departs from the contract's 4/8/16/24/32/48 scale, and half-steps appear in new elements. Replace `py-3`, `gap-3`, `space-y-3`, `px-3` and `p-3` with `py-2`/`py-4`, `gap-2`/`gap-4` and so on. Replace `mt-0.5` with an `items-start` and `pt-1` pattern or a documented exemption (see Pillar 5 for lines).
2. **DEV-1..DEV-4 are not yet accepted (WARNING)** — The built UI already implements all four, but the user has not signed off.
   - DEV-2 adds a `Not checked` services chip.
   - DEV-3 adds two preflight blockers.
   - DEV-1 uses line-level approve/deny routes.
   - DEV-4 moves the files into `components/patchRollouts/`.
   Get explicit acceptance, or rework before shipping.
3. **Inconsistent numerals and button sizing (WARNING)** — The contract requires `tabular-nums` on counts, countdowns and percentages. Only 6 of 14 files use it, and `RolloutCard.tsx`, `RolloutsTab.tsx`, `ChangeManagementWindows.tsx` and `StartDialog.tsx` do not. Primary controls inherit `min-h-10` from per-file constants, and the Deny and Cancel buttons append it ad hoc (`RolloutApprovalCard.tsx:217`, `RolloutDialogs.tsx:29`). Move the button constants to one shared module so the 40px rule cannot be missed.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Chip labels, tones and icons live in `components/patchRollouts/rolloutCopy.ts` (131 lines). The copy gate covers the whole folder. This is a strong control, and I found no generic `Submit` or `OK` labels in the new files.
- WARNING: `RolloutCard.tsx:25` defines `NOT_REACHED_CHIP` with the lowercase label `not reached`. The contract's chip is `Not reached`. Check this against the spec's copy table, because the other chips are capitalised.
- WARNING: `RolloutsTab.tsx:365` shows a `Loading...` string with three ASCII dots, and `RolloutApprovalCard.tsx` shows `Approving...` and `Denying...`. Confirm that the copy contract allows these progress strings.
- Error text is specific: `Couldn't load maintenance windows.` (`ChangeManagementWindows.tsx:78`).
- DEV-2 and DEV-3 add copy that the approved contract does not contain. See Fix 2.

### Pillar 2: Visuals (3/4)
- Chips use an icon at `size={12}` with `aria-hidden` plus visible text. Icon-only ring buttons have aria-labels (`RingsSettings.tsx:100-106`).
- The Agent Groups ring chip is rendered at `AgentGroupsDashboard.tsx:164-167` as `Ring: {name}`. That file also carries the user's own uncommitted work.
- WARNING: With no screenshots, the focal point and hierarchy of the Rollouts tab were not verified. The card layout (`RolloutCard.tsx:57`, `min-w-[200px] flex-1`) matches the contract's ring strip.
- RingDetail's 800px table minimum (200+150+300+150) matches the spec's budget (`RingDetail.tsx:69-72`). A stacked layout exists below `lg` (`RingDetail.tsx:90`).

### Pillar 3: Color (3/4)
- No hardcoded hex or rgb values were found in `components/patchRollouts`. Colours come from Tailwind classes.
- `RolloutChip.tsx:16-19` maps amber, blue, green and red. That agrees with the declared meaning table.
- `bg-primary-600` is used only on the ACCENT_BUTTON constants (`MaintenanceWindowDialog.tsx:32`, `RolloutApprovalCard`, `RolloutDialogs.tsx`). `bg-red-600` is on `DANGER_BUTTON` (`RolloutDialogs.tsx:27`, `MaintenanceWindowDialog.tsx:35`).
- WARNING: `RolloutDialogs.tsx:119` gives the `Resume rollout` confirm the accent button. This matches section 12 of the accent list. It sits right beside `Keep halted`, so check the pairing visually.
- WARNING: Chip and tone strings are copied in `ChangeManagementWindows.tsx:17-18` (`GREEN_CHIP`) and `RolloutApprovalCard.tsx:26` (amber), apart from `RolloutChip.tsx`. They can drift from the spec's tone table.

### Pillar 4: Typography (3/4)
- Counts over `components/patchRollouts/*.tsx`: `text-sm` 62, `text-xs` 38, `text-lg` 3. `font-semibold` 42 and `font-normal` 1 (`StartPreflight.tsx:133`). No `font-medium` or `font-bold`. This matches the two-weight rule.
- WARNING: `tabular-nums` appears in only 6 files: `RingDetail`, `RolloutApprovalCard`, `RolloutDialogs` and `StartPatchPicker` (2). Soak and countdown lines on `RolloutCard`, and the counts in `RolloutsTab` and `StartDialog`, do not use it.
- Heading and display roles: I did not check whether any new element uses a 30px display size. `text-lg` for section titles fits the 18px rule.

### Pillar 5: Spacing (2/4)
The contract says: "No half-steps in new elements." It names the 4/8/16/24/32/48 scale. Counts in `components/patchRollouts`:
- `py-3`, `px-3`, `p-3`, `gap-3`, `space-y-3` (12px) are off-scale. Locations:
  - `RingDetail.tsx:78-81` (table cells, `py-3`)
  - `RingDetail.tsx:90, 125, 127, 141`
  - `ChangeManagementWindows.tsx:60, 77, 93, 105`
  - `StartDialog.tsx:191, 193`
  - `StartPatchPicker.tsx:134` (`px-3 py-2`, `gap-x-3`)
  - `MaintenanceWindowDialog.tsx:20` (`px-3`)
  - `RolloutDialogs.tsx:140` (`p-3`)
- `mt-0.5` half-steps (7 uses): `RolloutCard.tsx:108`, `RolloutApprovalCard.tsx:176`, `RolloutsTab.tsx:241`, `MaintenanceWindowDialog.tsx:370`, `StartPreflight.tsx:43, 45, 47`.
- The arbitrary values `min-w-[200px]`, `[150px]` and `[300px]` are contract-sanctioned.
- `gap-2` (28), `gap-4` (16) and `px-4` (16) dominate, so the base rhythm is right.
- The contract's own line padding is `px-6 py-4`. Only 7 uses of `px-6` appear, so card interiors may be narrower than specified in places.
- The bulk of the deviations repeat in at least five files, so the fix is mechanical.

### Pillar 6: Experience Design (3/4)
- Loading: `RolloutsTab.tsx:269` renders three skeleton `.card` blocks with `animate-pulse`, and `loadMore` has a pending label (`:364-365`).
- Error and retry: `role="alert"` blocks with Try again at `RingsSettings.tsx:278`, `ChangeManagementWindows.tsx:79`, `StartPatchPicker.tsx:122-123`, `StartPreflight.tsx:104`.
- Destructive confirms are red and separate: `Cancel rollout` and `Delete window` (`RolloutDialogs.tsx:203`, `MaintenanceWindowDialog.tsx:358`). The safe button gets autoFocus (`MaintenanceWindowDialog.tsx:355`).
- Resume needs a typed confirmation (`RolloutDialogs.tsx:119`, `disabled={pending || !typed}`).
- Unsaved-change handling: `RingsSettings.tsx:317` shows the accent button only when `dirty`, and Discard changes is available (`:321`).
- WARNING: `RolloutCard.tsx:80` and `RolloutApprovalCard.tsx:182` set `aria-expanded` and `aria-controls`. They conditionally drop `aria-controls` when closed. That is acceptable, but I did not verify focus management after the dialogs close.
- WARNING: The size of primary controls is not centrally enforced (see Fix 3). `ICON_BUTTON` is `h-8 w-8`, as the contract says.
- DEV-1 (rollout-line approve and deny routes), DEV-2 (`Not checked` chip) and DEV-3 (two extra blockers) are implemented but not accepted by the user. DEV-4 is a file move (implemented as mapped).
- Not verified: the stop-rule behaviour (Approve refused while stopped). The code disables Approve with `disabled || stopped` (`RolloutApprovalCard.tsx`, in the Approve button).

---

## Registry Safety
Skipped. `components.json` is absent (`shadcn_initialized: false`).

## Files Audited
- `.planning/phases/84-staged-patch-rollouts/84-UI-SPEC.md` (Spacing, Typography, Color, Planning Deviations)
- `components/patchRollouts/*.tsx` and `rolloutCopy.ts` (grep audit of classes, colours, buttons, states)
- `components/AgentGroupsDashboard.tsx`, `components/AutonomousOpsDecisions.tsx`, `components/PatchManagementDashboard.tsx` (spot checks)
- Not read in full: `OsPatchesTab.tsx`, `MaintenanceWindowConfig.tsx`, `ChangeManagementDashboard.tsx`, `AutonomousOpsActivity.tsx`, `AutonomousOpsRowActions.tsx` and the tests in `src/__tests__/`.
