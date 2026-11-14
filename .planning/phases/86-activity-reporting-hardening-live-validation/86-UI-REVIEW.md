# Phase 86 — UI Review (re-audit after gap plan 86-16)

**Audited:** 2026-11-14 (HEAD, after 86-16 commits 2a4e2ea4e, ad556c174, 1b7b2857e)
**Baseline:** 86-UI-SPEC.md (approved 2026-11-11, corrected by 86-16). Plans 86-14/86-15 (D-23 test organization) have no UI-SPEC section and are judged against the spec's card, dialog, chip and label patterns.
**Screenshots:** not captured. No dev server on localhost:3000, 5173 or 8080. The live site still serves the pre-86-16 bundle (`index-BwnVKpDW.js`); the fix is in `dist-new` (`index-BeV-nK0J.js`) and is unpublished. Every Phase 86 surface needs a signed-in admin, so this is a code-only audit. The 86-16 fix was not re-measured in a browser.
**Interaction captures:** off (workflow.ui_interaction_capture is false). All interaction findings come from reading code.
**Carried-forward evidence:** the earlier static layout probe (884 px Organizations table, 946 px per-rule table, content column = viewport minus about 358 px with sidebar open) is the width basis for the scroll-region assessment. Per 86-16, the five Phase 86 suites pass (124 tests, including 8 new structural tests in `autonomousOpsTableScroll.test.tsx`).

---

## Blocker status

**G-86-5 (clipped tables): RESOLVED in code, pending a browser check on the published build.**
- `GoLiveOrganizations.tsx:137` and `StatsRuleTable.tsx:51` each wrap the table in `<div role="region" aria-label=... tabIndex={0} className="min-w-0 overflow-x-auto">`. `main`'s `overflow-x-hidden` (App.tsx:2023) no longer swallows content, because the overflow now scrolls inside the card, and the region is Tab-reachable. A global `:focus-visible` rule (index.css:131) supplies the ring.
- The card `dl` is `grid-cols-1 sm:grid-cols-2` with the simulation cell `col-span-full` (GoLiveOrganizations.tsx:171, 180), which fixes the chip overlap below sm.
- Not yet verified on the real build: scroll behaviour at 1024 to 1300 px, light and dark, sidebar open and collapsed, and the visible focus ring. That is UAT test 5 and cannot be settled here.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Matches the contract. Still open: "12 of 7 days" (`goLiveCopy.ts:113`), "checks 1, 2 and 5" with no visible numbers (`goLiveCopy.ts:177`), no wording for the test-organization exemption in the summary |
| 2. Visuals | 3/4 | Focal point and chips hold. Still open: a second secondary button per organization row, Time saved drawn twice, nested card in the empty state |
| 3. Color | 4/4 | No hard-coded colours, accent only on dialog and form confirms and the selected pill, simulation never green, every colour has a `dark:` pair |
| 4. Typography | 4/4 | 12/14/18 and weights 400/600 only in new code |
| 5. Spacing | 3/4 | Blocker fixed by scroll regions. Residual: the per-rule table (946 px) still scrolls up to about 1314 px viewport with the sidebar open, with the `Refused` and simulation columns off-screen and no cue. Off-scale `gap-3`, `mt-0.5` half-steps |
| 6. Experience Design | 3/4 | States are thorough and the tables are now reachable. Still open: Export vanishes silently when Statistics fails; a failed refetch after a write leaves stale rows with no notice |

**Overall: 20/24** (previous 19/24; Spacing 2 to 3, nothing else changed)

---

## Top 3 Priority Fixes

1. **Test-organization exemption and "12 of 7 days" copy (WARNING, carried forward).** At `goLiveCopy.ts:113`, an organization observed longer than seven days reads "12 of 7 days" (a test pins it at `autonomousOpsGoLive.test.tsx:460`), and an organization with no records shows the dash the spec reserves for "couldn't be read". At `goLiveCopy.ts:177`, MARK_BODY says "checks 1, 2 and 5" while the checklist shows no numbers. `goLiveSummary` (`goLiveCopy.ts:20-27`) reads as if the gate was bypassed when only the test organization is lifted. Fix: render `{d} days (7 needed)` or cap at `7 of 7 days`, name the three checks in MARK_BODY, and append "(the test organization)" in the summary.
2. **Export disappears with no reason, and stale rows after a failed refetch (WARNING, carried forward).** `showExport` (`AutonomousOpsActivity.tsx:82`) depends on a successful Statistics load, so a user with the right sees `Export activity` vanish when Statistics errors. `GoLiveCard.tsx:61` (`showError = failed && !data`) shows nothing when a reload after a lift or mark fails, so the toast says success while the row may be stale. Fix: show a disabled Export with a reason, and show a small amber "Couldn't refresh. The list may be out of date. Try again." line when `failed && data`.
3. **Per-rule table scrolls with no cue, and the Action button crowding (WARNING).** Between 1024 and about 1314 px with the sidebar open, `Refused` and `Would have done (simulation)` sit beyond the fold of a scroll region with no shadow, fade or hint, so a user may never learn the simulation column exists. Add an edge fade or a one-line "Scroll sideways for more columns" hint below the wide breakpoint cases, or let the header words wrap inside 72 px to shrink the table. Also demote `Use as test organization` (`GoLiveOrganizations.tsx:123`, same secondary style as `Lift shadow mode` on every row) to a text button.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
Contract rows (titles, summary, readout labels, simulation line, Estimate method, glossary, export dialog, checklist titles, toasts, errors) match `reportingCopy.ts` and `goLiveCopy.ts`. The 86-16 change adds no copy: the region `aria-label` reuses `ORG_CAPTION` and `rulesCaption(days)`. All of these still hold, unchanged (the files were not touched by 86-16 for copy):
- WARNING: `daysLabel` (`goLiveCopy.ts:113`) renders `12 of 7 days`; null days shows `—` for both "no records" and "unreadable".
- WARNING: `MARK_BODY` (`goLiveCopy.ts:177`) refers to checks by number the list does not show.
- WARNING: no summary wording for a lifted test organization (`goLiveCopy.ts:20-27`).
- Minor: the Mark dialog says "Type {name}" twice and its secondary is the generic `Cancel` (TestOrgDialogs.tsx:86, 99-100). `CLEAR_BODY` uses the undefined term "Customer rules".

### Pillar 2: Visuals (3/4)
- Focal point holds: `Needs your decision` in tenant scope, the status card in platform scope, with `Statistics` and `Going live` as collapsed rows. No icon-only buttons; icons are `aria-hidden`.
- New and good: the scroll regions are labelled landmarks, so assistive tech announces "Shadow mode by organization, region", and the card layout adds no extra tab stop (pinned by test).
- WARNING: `Use as test organization` competes with `Lift shadow mode` in every row (GoLiveOrganizations.tsx:123, 127).
- Minor: Time saved appears twice (StatsCard.tsx:154, TimeSavedBlock.tsx:39); nested `.card` in the Organizations empty state (GoLiveOrganizations.tsx:225); hand-rolled note in the Lift dialog (ShadowDialogs.tsx:92-94) instead of `HealthNotice`; flat h3 outline in the empty state.

### Pillar 3: Color (4/4)
- 0 hex or rgb values in the 12 Phase 86 component files and in the 86-16 changes.
- Accent in 7 places (Download CSV/PDF, Record check, Lift and Turn-on confirms, selected pill, two D-23 confirms), at most one visible at a time. Simulation figures are `MUTED`, never green. Every `text-gray-*`, `bg-*`, `border-*` has a `dark:` pair.
- Informational: the two D-23 accent confirms are not in the UI-SPEC accent register ("exactly three"); record them as items 22 and 23.

### Pillar 4: Typography (4/4)
- New code uses `text-xs`, `text-sm`, `text-lg` only; weights `font-semibold` and `font-normal` plus one inherited `font-medium` in `ReportExportCard` (contract says copy `ExportCard`). Number cells are `tabular-nums`. 86-16 added no type classes.
- Minor: `Close form`, `Discard note` and `Keep editing` use the 12/600 `TEXT_BUTTON` beside the 14/600 `Record check`.

### Pillar 5: Spacing (3/4)
- Resolved: the Organizations table (884 px) and per-rule table (946 px) no longer lose columns, since both scroll in their own `overflow-x-auto` region. The card `dl` stacks to one column below sm, fixing the 25 px chip overlap at 320 px. 86-UI-SPEC.md now records the measured widths (884, 946) and the scroll-region rule; the false "888 px inside the 900 px budget" claim is gone.
- WARNING (residual): the layout switch is still the viewport (`WIDE_QUERY = '(min-width: 1024px)'` at both files, line 15 and 16), so from 1024 up to about 1252 px (Organizations) and 1314 px (per-rule) with the sidebar open the user gets a table that needs a sideways scroll, where cards would have needed none. This is acceptable by the 86-16 decision, but the `Refused` and simulation columns are the least visible content in exactly that range, and nothing signals it.
- Minor: `gap-3` (12 px, off the 4/8/16/24 scale) at GoLiveOrganizations.tsx:127; `mt-0.5` half-steps at GoLiveOrganizations.tsx:89, 115, StatsCard.tsx:168, ExportDialog.tsx:125, GoLiveChecklist.tsx:96, ShadowDialogs.tsx:31, TestOrgDialogs.tsx:31 (inherited from `HealthNotice`).
- Good: `p-6` cards, `gap-6` sections, `p-4` cells, `min-h-10` consequential buttons, `min-h-8` pills.

### Pillar 6: Experience Design (3/4)
- State coverage is thorough: loading skeletons under `aria-busy`, empty, error with Try again, partial, disabled reasons via `aria-describedby`, single in-flight export, focus return, typed-name confirmations, the server's 409 sentence plus refetch. No `dangerouslySetInnerHTML`. No `components.json`, so the registry audit was skipped.
- Resolved: the Action controls (`Lift shadow mode`, `Turn shadow mode back on`, `Use as test organization`, `Clear test mark`) are reachable by scroll or keyboard at every width; the task-breaking behaviour from the previous review is gone. A keyboard user lands on the region first and can scroll with the arrow keys.
- WARNING: Export hidden without reason when Statistics fails (AutonomousOpsActivity.tsx:82, 164).
- WARNING: failed refetch after a write leaves stale data with no notice (GoLiveCard.tsx:42-46, 61). StatsCard discards its data on the same failure (StatsCard.tsx:79-83), so the two cards disagree.
- Minor: copied `FIELD` classes lose `disabled:opacity-60`; `RestoreShadowDialog` trusts server `detail` on 5xx; the Reporting spinner lacks `aria-hidden`; duplicated constants and hooks (`useWideLayout`, `OUTLINE_CHIP`, `TEXT_BUTTON`, `FIELD`) invite drift.
- Verification gap: the 86-16 tests assert structure only (jsdom has no layout). Real behaviour needs the published build.

---

## Files Audited

- components/autonomousOpsGoLive/GoLiveOrganizations.tsx, GoLiveCard.tsx, GoLiveChecklist.tsx, ShadowDialogs.tsx, TestOrgDialogs.tsx, goLiveCopy.ts
- components/autonomousOpsStats/StatsRuleTable.tsx, StatsCard.tsx, TimeSavedBlock.tsx, ExportDialog.tsx, ReportExportCard.tsx, reportingCopy.ts
- components/AutonomousOpsActivity.tsx, App.tsx (shell 2023), index.css (focus-visible rules)
- Context: 86-UI-SPEC.md, 86-CONTEXT.md, 86-16-SUMMARY.md, .planning/debug/golive-tables-clipped.md, the previous 86-UI-REVIEW.md
