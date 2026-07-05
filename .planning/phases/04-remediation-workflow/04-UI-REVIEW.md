# Phase 04 — UI Review

**Audited:** 2026-07-05
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured — no dev server detected on localhost:3000 or localhost:5173 (code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Specific error/empty copy, but "Cancel" is the only truly generic label and success actions give zero positive feedback |
| 2. Visuals | 3/4 | Clear hierarchy and no bare icon-only buttons, but modal has no visible close (X) affordance |
| 3. Color | 3/4 | Indigo accent used 16x across 2 files — borderline overuse for a single "10%" accent, though semantically separated from status colors |
| 4. Typography | 3/4 | 3 font weights (medium/semibold/bold) exceed the 2-weight guideline; 4 sizes is acceptable |
| 5. Spacing | 4/4 | 100% Tailwind scale values (p-4/p-6/gap-2-4/space-y-4-6), zero arbitrary bracket values |
| 6. Experience Design | 2/4 | No success feedback on save/resolve (error-only toasts), native `window.confirm()` breaks the app's own modal design language, no focus trap in modal |

**Overall: 18/24**

---

## Top 3 Priority Fixes

1. **No success feedback on save/resolve actions** (`components/RemediationTaskModal.tsx:107-108`, `components/RemediationDashboard.tsx:63-64`) — User impact: after clicking "Save Task" or "Mark Resolved," the modal just closes and the list silently refreshes with zero confirmation; if the WS `remediation_update` broadcast is delayed, the user has no signal the save actually happened, especially destructive/critical operations like marking resolved. Fix: call `showToast('Task saved', 'success')` / `showToast('Task marked resolved', 'success')` in the `try` blocks alongside the existing error-path toasts.

2. **Destructive confirmation uses native `window.confirm()` instead of the app's own modal pattern** (`components/RemediationDashboard.tsx:61`) — User impact: breaks visual consistency (native browser dialog vs. the Tailwind-styled modal used everywhere else in this same file), can't be themed for dark mode, and is inconsistent with the app's `aria-modal` dialog pattern already built in `RemediationTaskModal.tsx`. Fix: replace with a small `ConfirmDialog` component matching the existing modal's `bg-black/50` overlay + `rounded-lg` card style, or reuse an existing app-wide confirm component if one exists.

3. **Modal has no visible close affordance** (`components/RemediationTaskModal.tsx:117-124`) — User impact: the only ways to dismiss are Escape key (not discoverable) or the "Cancel" button at the very bottom of a scrollable form — a user who doesn't want to scroll past 6 fields to find an exit has no quick escape. Fix: add an `X` close icon button in the top-right of the header div (`<h2>` row) wired to `onClose`, matching common modal conventions.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Empty state is specific and actionable: `"No remediation tasks found. Click **Create Task** to add one."` (`RemediationDashboard.tsx:171`) — good.
- Error states are specific, not generic: `"Failed to load tasks — check your connection and retry"` (line 41), `"AI suggestion unavailable — please try again"` (`RemediationTaskModal.tsx:78`) — good, avoids the generic "Something went wrong."
- Destructive-action confirm copy explains consequence: `"Mark this task as resolved? This will be recorded in the audit trail."` (`RemediationDashboard.tsx:61`) — good.
- `Cancel` button (`RemediationTaskModal.tsx:257`) is the one generic label present — acceptable by convention, not penalized further.
- **Gap:** zero success-path copy exists anywhere in either file (`grep showToast` shows only error-path calls) — users get no positive confirmation copy for save/resolve, which is a copywriting gap as much as a UX gap (see Pillar 6, Fix #1).

### Pillar 2: Visuals (3/4)
- Clear focal point: header with icon + "Live" pulse badge (`RemediationDashboard.tsx:95-104`) establishes the screen's primary identity immediately.
- Visual hierarchy present via size/weight differentiation: `text-2xl font-bold` (h1) → `text-lg font-semibold` (modal title) → `text-xs uppercase tracking-wider` (table headers) → `text-sm`/`text-xs` body — genuine hierarchy, not flat.
- No icon-only interactive elements lack labels: `PlusIcon` pairs with "Create Task" text, `SparklesIcon` pairs with "Suggest steps"/"Suggesting..." text, `SaveIcon` pairs with "Save Task" text — all icon+text combos, good for accessibility and scanability.
- **Gap:** Modal (`RemediationTaskModal.tsx:117-124`) has no close (X) icon in the header — relies solely on Escape key or bottom-of-form Cancel button (see Fix #3).
- Stats bar (Open/In Progress/Resolved counts, lines 115-126) is a nice-to-have secondary hierarchy layer but duplicates information already visible via filter chip counts are not shown on the chips themselves — minor inconsistency (stats show counts, filter chips do not), not a blocker.

### Pillar 3: Color (3/4)
- `indigo-*` (primary/brand accent) appears 16 times across the two files — used for: primary CTA button, active filter chip, Edit link, Suggest steps button/spinner, focus/hover accents. For a component this size (479 combined lines), 16 accent-color instances trends toward over-application of the "10%" accent tier rather than reserving it for 1-2 primary actions per view.
- Status colors (`STATUS_COLORS` map: red/yellow/green/gray, `RemediationDashboard.tsx:9-14`) are correctly scoped to badge/status semantics only, not overlapping with the indigo brand accent — this separation is well done.
- Zero hardcoded hex/rgb values found (`grep "#[0-9a-fA-F]\|rgb("` returned nothing) — colors are fully tokenized through Tailwind classes, good discipline.
- No 60/30/10 distribution analysis possible without a rendered screenshot, but static-code accent density (16 uses in ~479 lines, concentrated across only 2 primary buttons + 1 chip group + 1 link + 1 AI button) suggests the accent is doing more visual work than a true "10%" tier should.

### Pillar 4: Typography (3/4)
- Font sizes in use: `text-xs`, `text-sm`, `text-lg`, `text-2xl` — 4 distinct sizes, within the abstract 4-size guideline (pass).
- Font weights in use: `font-medium`, `font-semibold`, `font-bold` — 3 distinct weights, which exceeds the abstract standard's 2-weight guideline. The usage is not arbitrary (bold reserved for the page h1, semibold for modal title + table headers + status badges, medium for labels/buttons/body) but the guideline is nonetheless not met to the letter.
- No arbitrary/bracket font-size or line-height values found.

### Pillar 5: Spacing (4/4)
- All spacing values found (`p-2/4/6/8/10`, `px-2/3/4`, `py-0/1/2`, `gap-1/2/3/4`, `space-y-4/6`) map cleanly onto the standard Tailwind 4px-increment scale — no arbitrary bracket values (`grep "\[.*px\]\|\[.*rem\]"` returned nothing).
- Consistent nested-container pattern: `p-6` for outer page, `p-4` for cards/table cells, `gap-2/3` for inline button groups — this is a coherent, repeatable spacing rhythm across both files, not ad hoc.

### Pillar 6: Experience Design (2/4)
- **Loading state:** present — `"Loading tasks..."` text placeholder (`RemediationDashboard.tsx:148`). Not a skeleton loader, but functional.
- **Error state:** present and good — dedicated error block with retry button (`RemediationDashboard.tsx:149-154`), plus toast on fetch failure.
- **Empty state:** present and actionable (line 170-172).
- **Disabled states:** present and correctly gated — Save button disabled while saving or when title empty (`RemediationTaskModal.tsx:261`), Suggest button disabled without a persisted task ID with an explanatory tooltip (line 164-165), Title field disabled/read-only on edit to preserve audit trail (line 150).
- **Destructive-action confirmation:** present, but implemented via native `window.confirm()` (`RemediationDashboard.tsx:61`) rather than the app's own Tailwind modal pattern — inconsistent visual language, can't be dark-mode styled, blocks in tests/automation differently than the rest of the UI (see Fix #2).
- **Success feedback: MISSING.** `grep showToast` across both files shows toast calls exist only on the error paths (`RemediationDashboard.tsx:41,67`; `RemediationTaskModal.tsx:78,111`) — there is no `showToast(..., 'success')` anywhere. Save and Mark Resolved both silently close/refresh with no positive confirmation (see Fix #1). This is a meaningful experience gap: users performing a save or a compliance-relevant resolve action get no feedback that the action succeeded beyond an implicit list re-render.
- **Focus management:** modal has `role="dialog" aria-modal="true"` and an Escape-key handler, but no focus trap and no initial-focus management (`tabIndex={-1}` is set on the outer div but nothing moves focus into the first field on open) — keyboard users tabbing through the page can tab out of an open modal into the page behind it.

---

## Registry Audit

No `components.json` found at repo root — shadcn is not initialized in this project. Registry safety audit skipped per gating rule.

---

## Files Audited

- `components/RemediationTaskModal.tsx` (276 lines)
- `components/RemediationDashboard.tsx` (230 lines)
- `.planning/phases/04-remediation-workflow/04-00-SUMMARY.md`
- `.planning/phases/04-remediation-workflow/04-01-SUMMARY.md`
- `.planning/phases/04-remediation-workflow/04-02-SUMMARY.md`
