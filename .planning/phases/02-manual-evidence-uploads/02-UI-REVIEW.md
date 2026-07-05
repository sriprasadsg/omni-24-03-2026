# Phase 02 — UI Review

**Audited:** 2026-07-05
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server detected on :3000 or :5173)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Toast/error copy is specific and actionable; description field relies on placeholder-only labeling |
| 2. Visuals | 2/4 | Evidence/Actions cells are overcrowded — up to 5 stacked badges/buttons compete for attention with no clear hierarchy |
| 3. Color | 2/4 | Six semantic colors (blue/green/red/yellow/purple/amber) fire simultaneously in the same cell — no dominant accent |
| 4. Typography | 3/4 | Only 2 font sizes (good) but 3 weights (semibold/medium/bold) in a single table row |
| 5. Spacing | 4/4 | All spacing values are standard Tailwind scale; no arbitrary bracket values found |
| 6. Experience Design | 3/4 | Loading/error/empty/disabled states all present, but destructive delete uses a native `window.confirm` instead of the app's own dialog pattern |

**Overall: 17/24**

---

## Top 3 Priority Fixes

1. **Evidence cell overcrowding (Visuals, 2/4)** — In a single evidence row a user may see: markdown/download link, a "PS" badge, an "Automated"/"Manual" badge, a "Stale" badge, and a delete button, all same-size pills with no size/weight differentiation (`components/AssetComplianceList.tsx:188-215`). User impact: hard to scan which control is the actual delete action vs. informational metadata, especially on narrow viewports where this `flex items-center gap-1` row will wrap. Fix: move secondary badges (PS/Stale) into a single "info" affordance (icon + tooltip) and keep only the primary status badge + delete action inline.

2. **Color pillar dilution (Color, 2/4)** — Six distinct semantic hues (blue/green/red/yellow/purple/amber) render concurrently in the same evidence cell (`AssetComplianceList.tsx:145-148` status pill, `:190` purple PS badge, `:195-197` blue/green source badge, `:200` amber stale badge, `:264-265` green/red action icons). No single "primary accent" pillar test can pass here — everything is emphasized, so nothing is. Fix: consolidate to one accent color for interactive controls (e.g., blue for actions only) and restrict the remaining hues to a single unified "status chip" component with a documented color-to-meaning legend.

3. **Native `window.confirm` for destructive action (Experience Design, 3/4)** — `handleDeleteEvidence` (`AssetComplianceList.tsx:104`) uses the browser's blocking `window.confirm` dialog for evidence deletion, while the rest of the app's feedback loop (`FrameworkDetail.tsx`, same file) is built entirely on `showToast`. User impact: the confirm dialog cannot be styled, is inconsistent with the app's visual language, and blocks the JS thread (no async cancel path, no keyboard-accessible custom copy). Fix: replace with the app's existing modal/dialog primitive (if one exists elsewhere in the codebase) for a consistent, on-brand confirmation experience.

**Additional issues found (not in top 3):**
- Description `<input>` (`AssetComplianceList.tsx:277-282`) has no `<label>` or `aria-label` — relies solely on `placeholder="Description (optional)"`, which disappears once text is entered and is not reliably exposed to all assistive tech. Add a visually-hidden `<label htmlFor>` or `aria-label="Evidence description"`.
- No `maxLength` attribute on the description `<input>` in the frontend, even though the backend enforces `max_length=1000` via `Form("", max_length=1000)` (per 02-01-SUMMARY.md) — a user can type past the limit with no feedback until submission fails/truncates server-side. Add `maxLength={1000}` client-side for immediate feedback.
- Delete button has no loading spinner, only `disabled` + `opacity-40` — visually easy to miss mid-flight state versus the upload button's `animate-pulse` treatment; inconsistent affordance for "in progress" across two similar async actions in the same row.
- `handleFileChange` (`AssetComplianceList.tsx:64-101`) silently no-ops when `!file || !selectedAssetId` with no user-facing message — acceptable for a cancelled file picker, but worth confirming this is the only path that hits it.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Toast copy is specific and actionable: `'Failed to upload evidence — please try again'` (`AssetComplianceList.tsx:78`), `'Could not delete evidence — please try again'` (`:110`), `'Evidence deleted.'` / `'Failed to delete evidence.'` (`FrameworkDetail.tsx:424,428`) — none of the generic "Submit/OK/Cancel/error occurred" anti-patterns were found via grep.
- Confirm-dialog copy is clear: `'Delete this evidence? This action cannot be undone.'` (`:104`) correctly signals irreversibility.
- Gap: `placeholder="Description (optional)"` (`:278`) is the only copy carrying field intent — no persistent label. Minor deduction, not a blocker since the field is optional and low-stakes.

### Pillar 2: Visuals (2/4)
- Icon-only buttons are consistently paired with both `title` and `aria-label` (`:264-274`, `:209-210`) — good baseline accessibility practice.
- No single focal point in the Evidence column: markdown viewer/download link, PS badge, source badge, stale badge, and delete button all render at the same visual weight (`text-xs`, `px-1.5 py-0.5` pill styling) in one `flex items-center gap-1` row (`:188-215`). A user scanning for "can I delete this" has to parse through 3-4 pills of similar size and saturation first.
- The Actions column (`:261-284`) stacks 3 icon buttons + a text input in a `flex-col` — functional but cramped at `w-44` for the input, and provides no visual grouping/separator between "status" actions (Check/X) and "evidence" actions (Upload).

### Pillar 3: Color (2/4)
- Grep confirms 6 distinct hue families active in the same component: green (`text-green-600`, `bg-green-100`), red (`text-red-600`, `bg-red-100`), yellow (`bg-yellow-100`), blue (`text-blue-600`, `bg-blue-100` — 8 occurrences), purple (`bg-purple-100`, PS badge), amber (`bg-amber-100`, stale badge).
- No hardcoded hex/rgb colors found (`grep -n "#[0-9a-fA-F]..." ` returned nothing) — all colors route through Tailwind tokens, which is good practice.
- With 6 hues live in a single cell, no color reads as "the" accent — this fails the abstract 60/30/10 guideline outright since there is no dominant color and no restraint on secondary/tertiary hues.

### Pillar 4: Typography (3/4)
- Font sizes: only `text-xs` and `text-sm` in use across the file (21 total occurrences, all one of these two values) — well within the 4-size ceiling.
- Font weights: `font-semibold` (5x), `font-medium` (8x), `font-bold` (1x) — 3 distinct weights, one over the abstract "≤2 weights" guideline. The `font-bold` on the AI Auditor label (`:243`) versus `font-semibold` on badges creates a subtle, likely-unintentional weight ladder.

### Pillar 5: Spacing (4/4)
- All spacing utilities found (`px-6 py-3`, `px-6 py-4`, `gap-1`, `gap-2`, `space-y-3`, `px-2 py-0.5`, `px-1.5 py-0.5`) are standard Tailwind scale values.
- Zero arbitrary bracket values (`grep -n "\[.*px\]\|\[.*rem\]"` returned nothing) — spacing discipline is clean and consistent between table cells and inline badges.

### Pillar 6: Experience Design (3/4)
- Loading states: `ingestingMap` drives `animate-pulse` + disabled on the upload button (`:268-271`); `deletingMap` drives `disabled` + `opacity-40` on delete (`:207-208`) — both async actions are guarded against double-fire.
- Error states: every async path (`onUploadEvidence`, `onIngestEvidence`, `onDeleteEvidence`) is wrapped in try/catch with a `showToast(..., 'error')` fallback (`:74-114`, and mirrored in `FrameworkDetail.tsx:396-429`).
- Empty state: `"No evidence attached"` italic muted text renders when `statusRecord?.evidence?.length` is falsy (`:258`).
- Destructive-action confirmation: present via `window.confirm` (`:104`) but implemented as a native browser dialog rather than the app's own UI language — a WARNING-level inconsistency rather than a missing-state failure, hence 3/4 rather than lower.
- Backend disposition (02-01-SUMMARY.md) confirms the destructive path is further guarded server-side (owner/admin/tenant/systemGenerated checks before `$pull`), so the client-side confirm is a UX affordance layered on top of a real authorization boundary — acceptable per the plan's own accepted threat disposition (T-02-08).

---

## Files Audited
- `/home/user/enterprise-omni-agent-ai-platform/components/AssetComplianceList.tsx`
- `/home/user/enterprise-omni-agent-ai-platform/components/FrameworkDetail.tsx` (delete/upload wiring only, lines ~380-430)
- `/home/user/enterprise-omni-agent-ai-platform/services/apiService.ts` (`uploadComplianceEvidence`, `deleteComplianceEvidence`, ~lines 633-660)
- `.planning/phases/02-manual-evidence-uploads/02-01-SUMMARY.md`
- `.planning/phases/02-manual-evidence-uploads/02-02-SUMMARY.md`
- `.planning/phases/02-manual-evidence-uploads/02-01-PLAN.md`
- `.planning/phases/02-manual-evidence-uploads/02-02-PLAN.md`

Registry audit: no `components.json` found — shadcn not initialized, registry safety audit skipped.
