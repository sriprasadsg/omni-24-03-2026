# Phase 07 — UI Review

**Audited:** 2026-07-06
**Baseline:** 07-UI-SPEC.md (approved design contract)
**Screenshots:** not captured (no dev server detected on :3000/:5173/:8080; code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | All contract strings match exactly (badge, toast, panel, empty/error states) |
| 2. Visuals | 2/4 | Stale badge uses wrong icon (`AlertCircleIcon` instead of spec'd `ClockIcon`); CoC event count is misleading before first expand |
| 3. Color | 4/4 | Amber/blue/green/red palette matches spec exactly, no hardcoded hex found in new files |
| 4. Typography | 4/4 | Only `text-xs`/`text-sm` and `font-medium`/`font-semibold` used, matching the declared two-size/two-weight system |
| 5. Spacing | 4/4 | `px-4 py-2`, `px-1.5 py-0.5`, `w-24`, `px-3 py-2` all match declared spacing scale exactly |
| 6. Experience Design | 3/4 | Loading/error/empty states implemented per spec, but CoC event count desyncs from real data until user expands the panel once |

**Overall: 21/24**

---

## Top 3 Priority Fixes

1. **Stale badge icon mismatch (AssetComplianceList.tsx:201)** — Spec explicitly declares `ClockIcon` at size 10 for the "Stale" badge icon (design rationale: reinforces the time-based/staleness semantics, distinct from the destructive/alert connotation of a circle-exclamation glyph). Implementation uses `AlertCircleIcon` instead. User impact: the badge now visually implies an error/alert condition rather than a passive time-based flag, which contradicts the spec's stated intent that staleness is informational, not alarming. Fix: swap `AlertCircleIcon` for `ClockIcon` in the badge (line 201), matching the icon already used correctly in `ChainOfCustodyPanel.tsx` and `EvidenceSettings.tsx` tab.

2. **CoC panel shows "(0 events)" until first expand (ChainOfCustodyPanel.tsx:32,67)** — `entries` state initializes as `[]` and is only populated on first `handleToggle()` call (lazy-fetch pattern). Because the event count span reads `entries.length` and is rendered in the always-visible header, every CoC panel displays "Chain of Custody (0 events)" on initial render regardless of actual event count, only correcting itself after the user clicks to expand. User impact: users scanning a control row for audit activity will see "(0 events)" even on controls with a rich audit history, potentially concluding there's nothing to inspect and never clicking to expand. Fix: either fetch the count (a lightweight HEAD/count-only call) on mount, or drop the count from the collapsed header state and only show it once `fetched === true`.

3. **Threshold input clamps mid-typing, fighting user input (EvidenceSettings.tsx:44-47)** — `onChange` immediately clamps every keystroke via `Math.min(365, Math.max(1, parseInt(...) || 1))`. Spec calls for inline validation shown only "on blur" with the Save button disabled while out-of-range — not a live clamp that rewrites the input value as the user types. Concretely: backspacing the field to type a new value snaps to `1` mid-edit (parseInt('') is NaN → falls to the `|| 1` default), which can surprise a user trying to enter e.g. "90" by first clearing the field. Fix: store the raw string in local state, validate/clamp only on blur or on Save, matching the spec's stated on-blur validation contract.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
Verified exact string matches against the Copywriting Contract table in 07-UI-SPEC.md:
- `EvidenceSettings.tsx:34` "Staleness Threshold" ✓
- `EvidenceSettings.tsx:37` "Automated evidence older than this many days is flagged as stale." ✓ (exact match)
- `EvidenceSettings.tsx:50` "days" unit label ✓
- `EvidenceSettings.tsx:64` "Save Threshold" / "Saving..." ✓
- `EvidenceSettings.tsx:20,22` toast copy "Staleness threshold updated" / "Failed to save threshold — please try again" ✓ (em-dash preserved)
- `EvidenceSettings.tsx:54` "Must be between 1 and 365 days." ✓
- `ChainOfCustodyPanel.tsx:9-13` action labels "uploaded/updated/deleted evidence" ✓
- `ChainOfCustodyPanel.tsx:62` dynamic aria-labels for expand/collapse ✓ exact wording
- `ChainOfCustodyPanel.tsx:87,92` error/empty state copy ✓ exact match
- `AssetComplianceList.tsx:172` days-old parenthetical format `({N} days old)` ✓
No generic placeholder copy ("Submit", "Click Here", "OK") found in any of the three phase-touched files. No findings; contract fully met.

### Pillar 2: Visuals (2/4)
- **BLOCKER-adjacent WARNING:** Stale badge icon (`AssetComplianceList.tsx:201`) uses `AlertCircleIcon`, not the spec-mandated `ClockIcon`. Confirmed via grep: `ClockIcon` is imported and used correctly in `EvidenceSettings`-adjacent tab nav and `ChainOfCustodyPanel.tsx:2,65`, but not in the stale badge itself. This is a direct violation of the Component Contract §1 visual spec ("Icon: `ClockIcon` at size 10").
- Focal point declared in spec (amber Stale badge as highest-contrast element) is preserved — amber is otherwise unused elsewhere in the touched surface, so visual hierarchy intent holds despite the icon swap.
- Icon-only chevron toggle in `ChainOfCustodyPanel.tsx:69-72` is correctly paired with a dynamic `aria-label` on the parent clickable div (line 62) — meets the icon-only-button-needs-label bar.
- CoC panel entry-count label is visually present but factually wrong pre-expand (see Pillar 6 also) — degrades perceived visual accuracy of the header.

### Pillar 3: Color (4/4)
- Stale badge: `bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300` (line 200) — exact match to spec.
- CoC action icons: create=green-600/400, update=blue-600/400, delete=red-500/400 (ChainOfCustodyPanel.tsx:104,106,108) — exact match to spec's Action-type icon table.
- Save button: `bg-primary-600 hover:bg-primary-700` (EvidenceSettings.tsx:62) — matches accent reservation rule (Save CTA is one of only two declared primary-600 usages).
- No hardcoded hex/`rgb()` values found in any of the three new/modified files (grep returned zero matches).
- 60/30/10 split respected: dominant white/gray-800 backgrounds, secondary gray-50/gray-700 header/section bg, amber+primary accents confined to their declared single-purpose elements. No accent overuse.

### Pillar 4: Typography (4/4)
Grep of the three files shows only `text-xs` and `text-sm` (2 sizes) and only `font-medium`/`font-semibold` (2 weights) — exactly matching the spec's declared "two weights only" contract and font-size table. No `text-lg`/`text-xl`/etc. introduced. Panel heading correctly differentiated by size (`text-sm`) vs badges (`text-xs`), not by a third weight, per spec's explicit instruction.

### Pillar 5: Spacing (4/4)
- Header row: `px-4 py-2` (ChainOfCustodyPanel.tsx:57) — matches spec exactly.
- Log entry: `px-4 py-3` (line 113) — matches spec exactly.
- Badge pill: `px-1.5 py-0.5` (AssetComplianceList.tsx:200) — matches spec's xs token.
- Threshold input: `w-24`, `px-3 py-2` (EvidenceSettings.tsx:48) — matches spec's declared exception value exactly.
- No arbitrary bracket values (`[Npx]`/`[Nrem]`) found in any of the three files.

### Pillar 6: Experience Design (3/4)
Coverage present for all four states in the spec's States/Interactions table:
- Loading: spinner centered, `animate-spin`, `h-4 w-4 text-gray-400` (ChainOfCustodyPanel.tsx:79-83) — matches spec markup near-verbatim.
- Error: exact copy, `text-red-500`, correct padding (line 86-88).
- Empty: exact copy, centered italic gray-400 (line 90-93).
- Permission gate: `canViewCoC = hasPermission('view:audit_log')` in FrameworkDetail.tsx, panel entirely absent from DOM when false — matches spec (though note the permission string is `view:audit_log` not the spec's literal `audit:read`; this was called out and justified in 07-03-SUMMARY.md as a deliberate correction based on research, not a defect).
- Save button disabled state (`disabled:opacity-50 disabled:cursor-not-allowed`) present and correctly gated on `!isValid || saving`.
- **WARNING:** Event count in the CoC header (`entries.length`) is sourced from client state that is empty until the lazy fetch completes, so the always-visible header undercounts (shows 0) prior to first expand — a real state-accuracy defect, not merely cosmetic, since it can cause users to skip panels that actually contain audit history.
- **WARNING:** Threshold input onChange clamps eagerly instead of on blur as specified, degrading input experience during edits (see Fix #3 above).
No destructive-action confirmation regressions found — the existing evidence delete confirmation is untouched, as required by spec.

---

## Files Audited
- `components/ChainOfCustodyPanel.tsx` (134 lines, new)
- `components/EvidenceSettings.tsx` (70 lines, new)
- `components/AssetComplianceList.tsx` (stale badge section, lines 160-210)
- `components/SettingsDashboard.tsx` (evidence tab wiring, grep-verified)
- `components/FrameworkDetail.tsx` (CoC panel mount + permission gate, grep-verified)
- `components/icons.tsx` (ClockIcon/ChevronDownIcon/AlertCircleIcon definitions)
- `.planning/phases/07-evidence-lifecycle-staleness-chain-of-custody/07-UI-SPEC.md` (baseline contract)
- `.planning/phases/07-evidence-lifecycle-staleness-chain-of-custody/07-0{1,2,3}-SUMMARY.md` / `07-0{1,2,3}-PLAN.md` (build record)

Registry audit: `components.json` not present in repo root — shadcn not initialized; registry safety audit skipped per spec ("Design System: none — Tailwind CSS utility classes only").
