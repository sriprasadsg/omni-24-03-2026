# Phase 18 — UI Review

**Audited:** 2026-07-06
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server detected on :3000/:5173/:8080)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Contextual empty states and CTAs are good, but "Create" button label is repeated generically across all 4 forms with no field-specific confirmation |
| 2. Visuals | 2/4 | Zero `<label>` elements for any form field across all 4 tabs — all 16 inputs rely on placeholder text only, a WCAG 3.3.2 failure |
| 3. Color | 3/4 | Single blue-600 accent is well-scoped to primary actions/active tab, but semantic risk/expiry badges lack `dark:` variants while every other element in the file does |
| 4. Typography | 4/4 | Only 2 font sizes (text-xs, text-sm) and 2 weights (font-medium, font-semibold) used — disciplined and consistent |
| 5. Spacing | 4/4 | All spacing values (p-1/2/3, px-2/3/4, py-0.5/1/2, gap-1/2, space-y-2/4) are on the standard Tailwind scale, no arbitrary values found |
| 6. Experience Design | 2/4 | Submit buttons have no `disabled` state during in-flight requests (double-submit risk) and no client-side required-field validation despite backend enforcing required fields |

**Overall: 18/24**

---

## Top 3 Priority Fixes

1. **No `<label>` elements on any of the 16 form inputs (TIA, LIA, Notices, Contracts forms)** — screen reader users cannot determine what a field is for once text is entered (placeholder disappears on input, and placeholders are not programmatically associated labels) — add `<label htmlFor>` or `aria-label` to every `<input>`, `<select>`, and `<textarea>` in `components/PrivacyLegalDashboard.tsx` (lines 87-95, 118-121, 143-146, 174-182).

2. **Submit buttons stay enabled during in-flight requests** — a user double-clicking "Create" on any of the 4 forms (lines 96, 122, 147, 183) can fire duplicate POST requests, creating duplicate TIA/LIA/notice/contract records — add a `submitting` state per form, disable the button and swap label to "Creating…" while the request is in flight.

3. **Risk/expiry status badges omit `dark:` variants while the rest of the component is fully dark-mode aware** — `bg-red-100 text-red-700` / `bg-amber-100 text-amber-700` / `bg-green-100 text-green-700` (line 102) and `bg-amber-50 ... text-amber-800` (line 164) render as light pastel badges with poor contrast against the dark `bg-gray-800` container in dark mode — add `dark:bg-red-900/30 dark:text-red-300` style variants matching the pattern already used elsewhere in the file (e.g., line 164's border already has a `dark:border-amber-800`, but the fill/text colors do not follow the same dark treatment for the risk badges in the TIA list).

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Empty states are specific and appropriately worded per tab: "No TIAs yet.", "No LIAs yet.", "No notices yet.", "No contracts yet." (lines 105, 130, 156, 192) — good, avoids generic "No data" pattern.
- CTA labels are contextual: "+ New TIA", "+ New LIA", "+ New Notice", "+ New Contract" (lines 83, 114, 139, 170) rather than a generic "Add".
- Weakness: every form's submit button is the bare word "Create" (lines 96, 122, 147, 183) with no confirmation of which record type was created beyond the toast text — acceptable but not best-in-class; toasts ("TIA created", "LIA created", etc., lines 56-59) do carry the specific noun so this is a minor deduction only.
- Error handling copy is generic: `catch { showToast('Failed', 'error'); }` (lines 56-59) discards the actual error detail on the catch path (only the non-catch `!res.ok` branch surfaces `body?.detail`), meaning network-level failures show a bare "Failed" with no actionable next step.

### Pillar 2: Visuals (2/4)
- No `<label>` tags anywhere in the file (confirmed via grep — zero matches). All 16 inputs (4 in TIA form, 4 in LIA form, 4 in Notices form, 5 in Contracts form) rely solely on `placeholder` attributes for field identification (lines 87-95, 118-121, 143-146, 174-182). This is a BLOCKER-adjacent accessibility gap: placeholder-only labeling fails WCAG 2.1 SC 3.3.2 (Labels or Instructions).
- No icon-only buttons in this component (all buttons carry text labels), so aria-label omission for icon buttons is not applicable here — that's a genuine positive.
- Visual hierarchy exists through color-coded risk/status badges (line 102: red/amber/green for high/medium/low risk) and semibold section headers (lines 82, 113, 138, 169), giving the dashboard a clear focal point per tab.
- Active tab indication uses `text-blue-600` + border to differentiate from inactive `text-gray-500` tabs (line 72) — adequate but relies on color alone with no underline/icon reinforcement, a minor concern for color-blind users distinguishing active vs. inactive tabs (mitigated somewhat by the border/background change, which is not color-only).

### Pillar 3: Color (3/4)
- Accent color (`blue-600`) usage: 8 occurrences, all on primary actions (active tab text, all 4 "Create" buttons, all 4 "+ New X" toggle buttons) — properly scoped, no overuse into decorative elements.
- No hardcoded hex/rgb colors found via grep — all colors go through Tailwind's semantic scale.
- Inconsistency: dark-mode support is applied thoroughly elsewhere (borders, backgrounds, inputs all have `dark:` variants — e.g. lines 69, 86, 117, 142, 173), but the risk-level badges (line 102: `bg-red-100 text-red-700`, `bg-amber-100 text-amber-700`, `bg-green-100 text-green-700`) and the expiring-contracts banner text/background (line 164, only the border gets `dark:border-amber-800` — the amber fill/text do get `dark:bg-amber-900/20 dark:text-amber-300`, so line 164 is actually compliant, but line 102's three risk badges are not). This creates a genuine dark-mode readability defect specifically for TIA risk badges.

### Pillar 4: Typography (4/4)
- Only 2 distinct font sizes used across the whole file: `text-xs` (16 occurrences) and `text-sm` (7 occurrences) — well under the 4-size ceiling.
- Only 2 distinct font weights used: `font-medium` (3) and `font-semibold` (5) — well under the 2-weight ceiling, appropriately reserved for headers and emphasis.
- Consistent sizing pattern: form labels/inputs at `text-xs`, section headers at `text-sm font-semibold`, matching a coherent micro-hierarchy for a dense data-entry dashboard.

### Pillar 5: Spacing (4/4)
- Spacing values found are exclusively standard Tailwind scale steps: `p-1/2/3`, `px-2/3/4`, `py-0.5/1/2`, `gap-1/2`, `space-y-2/4` — no arbitrary bracket values (`grep "\[.*px\]"` returned no matches).
- Pattern is consistent across all 4 tabs: each form uses `grid grid-cols-2 gap-2 p-3`, each list item uses `p-2`, each tab header row uses `px-3 py-1` for the action button — good structural repetition rather than ad-hoc spacing per tab.

### Pillar 6: Experience Design (2/4)
- Loading state exists but is minimal: a single text line "Loading..." (line 76) with no skeleton/placeholder rows — acceptable but not polished for a dashboard with 4 distinct list types.
- Error handling: `fetchData`'s catch block shows a single generic toast ("Failed to load data", line 50) regardless of which tab/request failed, losing the more specific `body?.detail` that submit handlers do surface — inconsistent error-detail handling between read and write paths.
- Empty states are present and specific per tab (see Pillar 1), a genuine strength.
- BLOCKER-adjacent: no `disabled` attribute anywhere in the file (confirmed via grep — zero matches). All 4 submit buttons (lines 96, 122, 147, 183) and both toggle buttons remain clickable during their own async request, so a user can double-click "Create" and fire duplicate POST requests, creating duplicate TIA/LIA/notice/contract records server-side (nothing in `privacy_service.py`'s create paths was audited for idempotency here, but the UI provides no protection).
- No client-side required-field validation before submit — forms POST whatever partial state exists (e.g., `tiaForm` could be `{}` if the user clicks Create immediately), pushing all validation errors to the backend round-trip with only a generic toast surfaced back.
- No destructive actions (delete/archive) exist in this component, so confirmation-dialog coverage is not applicable — not scored against.

---

## Files Audited
- `/home/user/enterprise-omni-agent-ai-platform/components/PrivacyLegalDashboard.tsx` (197 lines, full file read)
- `/home/user/enterprise-omni-agent-ai-platform/App.tsx` (grep-verified wiring at lines 41, 1860 — confirms lazy-loaded route registration with ErrorBoundary wrapper)
- `.planning/phases/18-privacy-legal-modules/18-01-SUMMARY.md` (context)
- `.planning/phases/18-privacy-legal-modules/18-01-PLAN.md` (context / must-haves)

Registry audit: `components.json` not present in repo root — shadcn not initialized, registry safety audit skipped.
