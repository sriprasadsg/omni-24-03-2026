# Phase 86 — UI Review

**Audited:** 2026-11-14
**Baseline:** 86-UI-SPEC.md (approved 2026-11-11). Plans 86-14/86-15 (D-23 test organization) have no UI-SPEC section and are judged against the spec's existing card, dialog, chip and label patterns.
**Screenshots:** not captured. No dev server answered on localhost:3000, 5173 or 8080. The live site (https://127.0.0.1, bundle `index-BwnVKpDW.js`, whose lazy chunk `AutonomousOpsActivity-DvA1idXW.js` contains the 86-15 strings) serves the Phase 86 build, but every Phase 86 surface needs a signed-in tenant admin or Super Admin. No audit credentials were available and signing in with a real account was not allowed, so this is a code-only audit. One finding (the table overflow) was checked with a **static layout probe**: a local HTML page using the same shell, card and table classes, styled with the live CSS (`index-BRVoEUxD.css`) and measured in headless Chromium at 1024 to 1440 px. The probe is not a screenshot of the app.
**Interaction captures:** off (workflow.ui_interaction_capture is false). Every interaction finding below comes from reading the code.
**Unit evidence:** `npx vitest run` on the five Phase 86 UI suites (stats, export, goLive, goLiveTestOrg, copy): 140/140 passed.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Close to the contract word for word. Defects: "12 of 7 days" (a test pins it), "checks 1, 2 and 5" refers to numbers the list never shows, and the summary hides the test-organization exemption |
| 2. Visuals | 3/4 | The focal point survives (quiet collapsed cards). But every row shows a second secondary button, "Use as test organization", and the Time saved figure appears twice |
| 3. Color | 4/4 | No hex or rgba values. Accent appears only on dialog and form confirms and the selected pill. Simulation figures are never green. Every colour has a `dark:` pair |
| 4. Typography | 4/4 | Exactly 12/14/18 and weights 400/600 in new code. The only exception (`font-medium`, a 16px h4) is in the Reporting card, which the contract told to copy |
| 5. Spacing | 2/4 | Both tables switch to the wide layout at 1024 px but only fit from about 1280 px with the sidebar open. They have no `overflow-x-auto`, so the Lift shadow mode button is cut off. The per-rule table's real minimum is about 946 px, not the spec's 888 |
| 6. Experience Design | 3/4 | States are thorough (loading, empty, error, partial, disabled reasons, one request per click, focus). But Export disappears without a reason when Statistics fails, and a failed refetch after a write leaves stale rows |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **Wide tables are cut off between 1024 and about 1280 px with the sidebar open (BLOCKER for the Organizations table, WARNING for the per-rule table).** Users lose the go-live task: at 1024 to about 1175 px the `Lift shadow mode`, `Turn shadow mode back on` and `Use as test organization` buttons in the Action column are clipped by `main`'s `overflow-x-hidden` (App.tsx:2023), and the per-rule table loses `Refused` and the whole `Would have done (simulation)` column up to about 1240 px. **Fix:** in `GoLiveOrganizations.tsx:231-233` and `StatsRuleTable.tsx:150-151`, wrap each table in `overflow-x-auto`, as Phase 84 does in `patchRollouts/RingDetail.tsx:64`. Also move the switch to the wide layout (`WIDE_QUERY`, GoLiveOrganizations.tsx:15 and StatsRuleTable.tsx:16) from `lg` (1024) to `xl` (1280), or base it on the card's width (ResizeObserver) rather than the viewport. Correct the UI-SPEC budget arithmetic too: `min-w-[72px]` includes the 32 px of padding, so `Approved`, `Refused` and `Undone` overflow it, and the table measures about 946 px.
2. **"12 of 7 days" and an ambiguous dash in Days observed (WARNING).** An organization observed longer than the minimum reads as nonsense, and the test pins that string (`src/__tests__/autonomousOpsGoLive.test.tsx:460`). An organization with no shadow records shows `—`, which the spec reserves for "couldn't be read". **Fix:** in `goLiveCopy.ts:113`, render `{d} days (7 needed)` (or cap the figure at `7 of 7 days`), and show `0 of 7 days` when daysObserved is null only because there are no records. The server's `observation()` returns None in both cases, so the payload needs a flag that tells them apart, or the UI can key off the `no_shadow_records` reason.
3. **The test-organization exemption is hard to read (WARNING).** (a) The collapsed summary can read `2 of 5 checks recorded · 1 organization out of shadow mode` (goLiveCopy.ts:20-27, GoLiveCard.tsx:58/74). To anyone glancing at the card, that looks like the gate was bypassed. Say `(the test organization)` when the only lifted organization is the test one. (b) MARK_BODY (goLiveCopy.ts:176-177) says "so you can walk checks 1, 2 and 5", but the checklist `<ol>` (GoLiveChecklist.tsx:194) shows no numbers, because preflight removes list markers. Name the checks instead: "Firewall round-trip, Reboot gate and Live stop drill". (c) While nothing is marked, every organization row carries a second secondary button, `Use as test organization` (GoLiveOrganizations.tsx:123). It competes with `Lift shadow mode` and invites marking a customer organization. Demote it to the text-button style, or offer it from one place above the table.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

Contract match: every Copywriting Contract row was checked against `reportingCopy.ts` and `goLiveCopy.ts`. Titles, summary lines, readout labels, the simulation line, the Estimate method (character for character), the glossary, the Export dialog lines, the cap note, the Reporting card note and reasons, the checklist titles, the record form, both shadow dialogs, the toasts and the errors all match. Documented, justified deviations (not counted against the score): the `Refused` glossary line was widened to "blocked by a limit, a never-touch entry or a stop, or nobody answered the approval in time" (reportingCopy.ts:101, which matches the server column); check descriptions 2 and 3 follow the runbook ("on its card", "watchdog timer"), as R15 allows; and the note helper has no address from a documentation range (goLiveCopy.ts:78). Added fallback sentences for 5xx and network failures (goLiveCopy.ts:149, 160, 181, 187) close gaps the spec left.

Findings:
- WARNING: `daysLabel` renders `{d} of 7 days` with no cap (goLiveCopy.ts:113), so a lifted organization reads `12 of 7 days`. A test pins this (autonomousOpsGoLive.test.tsx:460). See Top fix 2.
- WARNING: an organization with no shadow records shows `—` (goLiveCopy.ts:113 with server `observation()` returning None, golive.py:96). The spec reserves `—` for "can't be read" (UI-SPEC section 6, Partial). The reason line below it does tell the two apart, but the cell itself does not.
- WARNING: `MARK_BODY` (goLiveCopy.ts:176-177) refers to "checks 1, 2 and 5", numbers the list never shows (GoLiveChecklist.tsx:194 has no `list-decimal`). Name the checks.
- WARNING: `goLiveSummary` (goLiveCopy.ts:20-27) has no wording for a lifted test organization, so the collapsed card seems to contradict its own gate. Spec gap from 86-15 (no UI-SPEC section).
- Minor: the Mark dialog says "Type {name}" twice, once as the label `Type {name} to confirm` and again as the helper `Type {name} exactly as shown.` (TestOrgDialogs.tsx:99-100). The Lift dialog uses the neutral label `Type the organization name to confirm` (goLiveCopy.ts:143), so the two typed-name dialogs read differently. Reuse `TYPE_NAME_LABEL`.
- Minor: the Mark dialog's secondary is the generic `Cancel` (goLiveCopy.ts:170, TestOrgDialogs.tsx:86). Every other Phase 86 dialog names what staying means (`Keep shadow mode on`, `Keep it lifted`, `Keep test mark`). `Cancel` exists in Phase 81 to 83 dialogs, so this is consistency, not a contract breach. Suggest `Don't mark it`.
- Minor: `CLEAR_BODY` (goLiveCopy.ts:184) introduces "Customer rules", a term the card never defines. "The full go-live gate applies to it again" reuses wording the card already shows.

### Pillar 2: Visuals (3/4)

Focal point: tenant scope keeps `Needs your decision` as the anchor. `Statistics` is a single collapsed `.card` row whose summary carries the headline (StatsCard.tsx:97-109). Platform scope keeps the status card as the anchor, and `Going live` is a collapsed row (GoLiveCard.tsx:64-76). Placement matches section 1 (AutonomousOpsActivity.tsx:143, 157-166, 171-176). There are no icon-only buttons; every icon is `aria-hidden`, and every chip pairs icon and text (HealthChip, the outline Estimate chip, the dashed Shadow chip at GoLiveOrganizations.tsx:20-21/50).

Findings:
- WARNING: with no test organization marked, every row offers `Use as test organization` in the same secondary style as `Lift shadow mode` (GoLiveOrganizations.tsx:123, 126-131). N organizations means 2N competing secondary buttons in the Action column, and the less frequent, riskier control looks as important as the main one. See Top fix 3(c).
- Minor: the Time saved figure is drawn twice in the expanded card, once in the readout cell (StatsCard.tsx:154-157) and again in the TimeSavedBlock (TimeSavedBlock.tsx:39), both at 18/600 with an Estimate chip. The spec mandates both (sections 2b and 2d), but the repeat dilutes the readout. Consider using the block's heading row as the only figure, or dropping the figure from the block and keeping the method.
- Minor: the Organizations empty state is a `.card` nested inside the Going live `.card` (GoLiveOrganizations.tsx:225), a card inside a card with a double border and shadow. The Statistics empty state puts `EmptyStateCard` straight on the card (StatsCard.tsx:161). Drop the inner `card overflow-hidden` wrapper.
- Minor: the Lift dialog's test-organization note is a hand-rolled blue block with no icon (ShadowDialogs.tsx:92-94). Every other notice in the phase uses `HealthNotice`, which always carries its 16px icon. Use `<HealthNotice tone="blue">`.
- Minor: the `EmptyStateCard` heading under the `Organizations` h3 is also an h3 (default `headingLevel`, AutonomousOpsEmptyStateCard.tsx:9), so the outline is flat. It should be h4. Allowing `'h4'` needs a one-line type change.

### Pillar 3: Color (4/4)

- Hard-coded colours: 0 hex or rgb/rgba values in all 12 Phase 86 component files.
- Accent (`ACCENT_BUTTON` / `primary-*`): 7 uses. These are Download CSV/PDF (ExportDialog.tsx:75, item 21), Record check (GoLiveChecklist.tsx:109, item 20), Lift shadow mode and Turn shadow mode on (ShadowDialogs.tsx:81/152, item 19), the selected period pill (StatsCard.tsx:29, item 2), and the two D-23 confirms (TestOrgDialogs.tsx:88/148). At most one accent is visible at a time, because each sits in a modal or the single open form. The cards, tables and readouts are `.card` surfaces with neutral text, so the 60/30/10 split holds.
- Simulation marks: the dashed neutral border plus the words appear on the per-rule column (StatsRuleTable.tsx:12, 57, 72, 82), the stacked card (StatsRuleTable.tsx:101), the simulation line (StatsCard.tsx:40), the Organizations column and card (GoLiveOrganizations.tsx:18, 144, 154, 178) and the Shadow chip. Simulation values are always `MUTED`, never green and never in a real cell.
- Dark mode: every `text-gray-*`, `bg-*` and `border-*` class in the new files has a `dark:` pair. The three unpaired `hover:bg-*` cases carry `dark:hover:` as well.
- Informational (spec bookkeeping, no code change): the two D-23 accent confirms are not in the UI-SPEC accent register, which says Phase 86 adds "exactly three". They follow the "one affirmative action of a dialog" rule, so the next spec revision should record them as items 22 and 23.
- Informational: the Reporting card's PDF button is red-tinted (ReportExportCard.tsx:15). Section 4 requires it ("keep the Reporting screen's own styles"), but it sits awkwardly against "Destructive red: none in this phase".

### Pillar 4: Typography (4/4)

- Sizes in new code: `text-xs` 39, `text-sm` 49, `text-lg` 5, and nothing else. No 30 px size was added; the page title is unchanged.
- Weights: `font-semibold` 38, `font-normal` 4 (resetting `th` boldness on row headers, which is correct), `font-medium` 1.
- Contract roles hold. Card titles are 18/600 (StatsCard.tsx:99, GoLiveCard.tsx:66). Headline numbers are 18/600 `tabular-nums` (StatsCard.tsx:36, R13). Column headers are 12/600 muted (StatsRuleTable.tsx:15, GoLiveOrganizations.tsx:17). Rule ids are 12/400 mono (StatsRuleTable.tsx:46). Notes are 14/400 `whitespace-pre-wrap break-words` (GoLiveChecklist.tsx:144). Every number cell is `tabular-nums`.
- Inherited by contract, not counted: ReportExportCard has `font-medium` buttons (ReportExportCard.tsx:13) and an unsized `h4` that renders at 16px (ReportExportCard.tsx:54), because section 4 says to use the same classes as `ExportCard` (ReportingDashboard.tsx:160-182).
- Minor: text-button sizes split across the phase. Statistics disclosures are 14/600 (StatsRuleTable.tsx:13, TimeSavedBlock.tsx:11). The checklist's single `TEXT_BUTTON` (GoLiveChecklist.tsx:16, 12/600) is correct for `Record again` (spec 12/600), but it is also used for `Close form`, `Discard note` and `Keep editing`. So `Close form` sits at 12px next to the 14/600 `Record check`. Give the form's text buttons the 14/600 class.

### Pillar 5: Spacing (2/4)

Static layout probe (headless Chromium, live CSS, the same classes as App.tsx:1989/2006/2023, GoLiveOrganizations.tsx:137-161 and StatsRuleTable.tsx:51-86; sidebar open, which is the default at 768 px and above):

| Viewport | main right edge | Organizations table | Lift button right edge | Per-rule table | Simulation column right edge |
|----------|-----------------|---------------------|------------------------|----------------|------------------------------|
| 1024 | 1012 | 884 px | 1166 (clipped) | 946 px | 1259 (column gone) |
| 1100 | 1088 | 884 px | 1166 (clipped, reads "Lift shad") | 946 px | 1259 (column gone) |
| 1180 | 1168 | 884 px | 1166 (fits main, spills 37 px past the card) | 946 px | 1259 (column gone) |
| 1240 | 1228 | 884 px | fits | 946 px | 1259 (clipped) |
| 1280 | 1268 | 922 px | fits | 946 px | 1259 (fits, 1 px to spare) |

Findings:
- BLOCKER (Organizations) / WARNING (per-rule): the viewport switch (`WIDE_QUERY = '(min-width: 1024px)'`, GoLiveOrganizations.tsx:15, StatsRuleTable.tsx:16) does not match the width the tables need. The content column is the viewport minus about 356 px (shell padding 24, sidebar 256, gap 12, main padding 16, card padding 48). Neither table has an `overflow-x-auto` wrapper (GoLiveOrganizations.tsx:231, StatsRuleTable.tsx:150), and `main` hides horizontal overflow, so the overflowing columns cannot be reached at all. See Top fix 1.
- WARNING: the per-rule table's budget arithmetic is wrong. Seven count columns at `min-w-[72px]` include the 32px `px-4` padding (border-box), so headers such as `Approved` need about 82px. The measured minimum is about 946px, above the spec's 888px and the 900px budget. Either let the header words wrap inside 72px, or budget 72px of content plus padding and record the real total in the UI-SPEC.
- Minor: `gap-3` (12px, off the 4/8/16/24 scale) between the shadow action and the test-organization action (GoLiveOrganizations.tsx:127). Use `gap-4`, or `gap-2` to match the reason-line rhythm.
- Minor: half-step `mt-0.5` icon nudges in new elements (StatsCard.tsx:168, ExportDialog.tsx:125, GoLiveChecklist.tsx:96, GoLiveOrganizations.tsx:89/115, ShadowDialogs.tsx:31, TestOrgDialogs.tsx:31). The spec says "No half-steps in new elements". The idiom is inherited from `HealthNotice` (AutonomousOpsHealthChips.tsx:109), so fix it there once, for example with `items-center` on single-line rows, rather than per file.
- Accepted per the spec's exceptions: the pill `px-3` (StatsCard.tsx:27), the `FIELD` `px-3` (inherited from AutonomousOpsResponseSettings.tsx:25-26), and the ReportExportCard `px-3 py-1` (copied ExportCard). The arbitrary `min-w-[…px]` values are the spec's declared column minimums.
- Good: card padding `p-6`, section gaps `gap-6`, readout cells `p-4`, check rows `p-4` with `gap-4`, consequential buttons `min-h-10`, pills `min-h-8`, the textarea `min-h-24` and the typed-name input `min-h-10` all match the spec.

### Pillar 6: Experience Design (3/4)

State coverage, from code:
- Statistics (E1 to E3): collapsed `h-4 w-64` and expanded skeletons under `aria-busy` (StatsCard.tsx:106, 139-146). Empty state in place of sections c to e (160-163), red `HealthNotice` with Try again (130-137), shadow-only sentence (TimeSavedBlock.tsx:41), `—` for missing counts (StatsRuleTable.tsx:33-35), show-all past 15 (153-159), glossary disclosure with `aria-expanded`.
- Export (E4, E5): opens filled (ExportDialog.tsx:38-39), Close takes first focus (73), one in-flight ref (43, 50), Esc off while pending (83), the result block takes focus (47, 85), cut, empty, error and 403 states (86-90, 123-128).
- Going live (E8 to E12): a single inline form at a time, focus to the textarea and back to the row button (GoLiveChecklist.tsx:52, 185-191), disabled reasons through `aria-describedby` (GoLiveChecklist.tsx:110; GoLiveOrganizations.tsx:83, 109), discard prompt, the server's 409 sentence plus refetch (ShadowDialogs.tsx:62-64), typed exact-name confirmations (ShadowDialogs.tsx:47, TestOrgDialogs.tsx:58).
- Server strings render as React text only; there is no `dangerouslySetInnerHTML` in any file. Registry audit: no `components.json`, so it was skipped.

Findings:
- BLOCKER (cross-reference, Pillar 5): at 1024 to about 1175 px the Organizations Action column is clipped, so the go-live task cannot be completed at those widths without collapsing the sidebar.
- WARNING: the Export button depends on the statistics payload. `showExport` needs `exportRight.can`, which only a successful Statistics load sets (AutonomousOpsActivity.tsx:82, 164). If Statistics fails, `Export activity` vanishes with no reason, even for a user who holds both rights. Show the button with a disabled reason ("Export is unavailable until Statistics loads. Try again.") or read `canExport` from the status payload.
- WARNING: a refetch after a write that fails leaves stale data on screen without saying so. GoLiveCard keeps the old payload when a reload fails (GoLiveCard.tsx:42-46) and shows nothing, because `showError` needs `!data`. After a successful lift or mark, the toast says it worked while the row may still show the old shadow state. Show a small amber "Couldn't refresh. The list may be out of date. Try again." line when `failed && data`.
- Minor: refetch failures behave inconsistently. StatsCard throws away the numbers it was showing when a Refresh or period refetch fails (StatsCard.tsx:79-83), while GoLiveCard keeps its data. Pick one behaviour; keeping the data with a notice is the better one.
- Minor: the record form's textarea and the dialogs' typed-name inputs are `disabled` while pending, but their copied `FIELD` classes (GoLiveChecklist.tsx:17-18, ShadowDialogs.tsx:23-24, TestOrgDialogs.tsx:23-24) drop the shared `disabled:opacity-60` (AutonomousOpsResponseSettings.tsx:26), so nothing looks disabled. Import the shared `FIELD` and add `w-full py-2`.
- Minor: `RestoreShadowDialog` shows the server's detail for any status (ShadowDialogs.tsx:139), including a 5xx. The record form and the D-23 dialogs only trust `detail` below 500 (GoLiveChecklist.tsx:24, TestOrgDialogs.tsx:44). Align them.
- Minor: the Reporting card spinner (ReportExportCard.tsx:60, 64) has no `aria-hidden` and the button no `aria-busy`. This is copied from ExportCard.
- Maintainability, which feeds visual drift: the spec asked for file-local constants to be exported rather than copied. `PILL_BASE/IDLE/ACTIVE` are copied from AutonomousOpsActivityList.tsx:259-261 into StatsCard.tsx:27-29. `OUTLINE_CHIP` is copied 3 times. `TEXT_BUTTON` differs between files. `SECONDARY_BUTTON` was copied into ExportDialog.tsx:25-27 without the shared `gap-2 py-2`. `useWideLayout`, `ErrorBlock`, `WrappedTitle` and `FIELD` are each duplicated across 2 or 3 files. Export each once.

---

## Files Audited

- components/autonomousOpsStats/StatsCard.tsx, StatsRuleTable.tsx, TimeSavedBlock.tsx, ExportDialog.tsx, ReportExportCard.tsx, reportingCopy.ts
- components/autonomousOpsGoLive/GoLiveCard.tsx, GoLiveChecklist.tsx, GoLiveOrganizations.tsx, ShadowDialogs.tsx, TestOrgDialogs.tsx, goLiveCopy.ts
- components/AutonomousOpsActivity.tsx, components/AutonomousOpsActivityList.tsx (onBucketChange, EmptyStateCard re-export), components/AutonomousOpsEmptyStateCard.tsx
- components/ReportingDashboard.tsx (ExportCard 160-182, mount 558-562)
- Shared primitives compared against: components/AutonomousOpsHealthChips.tsx, AutonomousOpsHealthCards.tsx, AutonomousOpsResponseSettingsDialogs.tsx, AutonomousOpsResponseSettings.tsx, index.css (`.card`), App.tsx (shell 1989-2023), tailwind.config (darkMode class)
- Server shape checked for copy: backend/autonomous_ops/reporting/golive.py (observation, _reasons)
- Context: 86-UI-SPEC.md, 86-CONTEXT.md (D-01..D-23), 86-01..86-15 SUMMARY.md, 86-15-PLAN.md
