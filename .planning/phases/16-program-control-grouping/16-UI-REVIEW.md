# Phase 16 — UI Review

**Audited:** 2026-07-06
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server running on :3000/:5173)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Generic "Save"/"Cancel"/"Delete" labels; delete confirm is a raw `window.confirm` browser dialog, not a styled destructive-action pattern |
| 2. Visuals | 2/4 | No focal point — form, card grid, and modal all compete at equal weight; icon-only close button (✕) has no aria-label |
| 3. Color | 3/4 | Status colors (green/red/amber) correctly scoped to badges/progress bar only; no hardcoded hex/rgb found |
| 4. Typography | 2/4 | Entire component uses only `text-xs`/`text-sm` (2 sizes) with a single `font-semibold`/`font-medium` bump — flat hierarchy, headings barely differentiated from body |
| 5. Spacing | 3/4 | Consistent Tailwind spacing scale (p-1/p-2/p-3/p-4, gap-1/2/3), no arbitrary bracket values found |
| 6. Experience Design | 2/4 | Loading and empty states present; but no error state beyond toast, no disabled-state on "New Program" while submitting, no loading skeleton on control picker fetch |

**Overall: 14/24**

---

## Top 3 Priority Fixes

1. **Icon-only close button has no accessible name (line 140)** — screen-reader users cannot identify the "✕" modal-close control, breaking task completion for assistive-tech users — add `aria-label="Close"` to the button.
2. **No focal point / flat visual hierarchy across the whole file (lines 87-133)** — with only `text-xs`/`text-sm` and one weight bump, users scanning the dashboard get no visual cue for what matters most (compliance status vs. metadata) — promote the status badge and program name to a larger/bolder treatment (e.g., `text-base font-semibold` for name, keep badge prominent) and demote secondary metadata (owner, framework) to `text-[11px] text-gray-400`.
3. **Native `window.confirm` for destructive delete (line 40) and no submit-in-flight guard on "Create" (line 96)** — the browser-native confirm dialog is inconsistent with the rest of the styled UI and can't be visually branded or tested reliably; the Create button has no disabled/loading state so a double-click can fire duplicate POST requests — replace `window.confirm` with an in-app confirmation modal matching the existing "Manage Controls" modal pattern, and add a `submitting` state disabling the Create button during the request (mirroring the existing `savingControls` pattern already used for the controls modal).

---

## Detailed Findings

### Pillar 1: Copywriting (2/4)
- Line 88: `+ New Program` / `Cancel` toggle button — acceptable but generic; no distinct empty-form vs. edit-form copy.
- Line 96: `Create` — passable, though other phases in this codebase (per CLAUDE.md conventions) favor action+object labels (e.g., "Create Program") for clarity when multiple entities exist on a page.
- Line 40: `Delete this program? This cannot be undone.` is a decent confirm message, but delivered via native `window.confirm`, not the app's own modal/toast system — inconsistent voice with the rest of the UI (see Fix #3).
- Line 133: `No programs yet.` — reasonable empty state, but no CTA hint (e.g., "No programs yet — create one above.") to guide the user to the action that resolves the empty state.
- Line 157: `No controls found.` — same issue, no guidance on whether this is a search-filter miss or genuinely empty catalog.
- No distinct error copy: all failure branches (lines 25, 36, 45, 57, 81) reduce to generic toasts ("Failed to load", "Failed", "Delete failed", "Failed to load controls", "Update failed") with no specific recovery guidance.

### Pillar 2: Visuals (2/4)
- No single focal point: the header row (line 87), inline create-form (lines 90-98), and 2-col card grid (line 102) are all rendered with equal `text-xs`/`text-sm` weight — nothing draws the eye to the primary action or the most important program.
- Icon-only button at line 140 (`✕`) has zero `aria-label` or `title` — grep confirmed no `aria-label` or `title=` attributes exist anywhere in the file.
- Status badge (line 111) is the only real hierarchy signal in the card, but it's the same visual weight (`px-1.5 py-0.5`, `rounded`) as the plain "Controls"/"Delete" action buttons below it (line 126-127), diluting its role as the primary status indicator.
- Progress bar (lines 116-119) is a good visual affordance, correctly color-matched to status — one bright spot.

### Pillar 3: Color (3/4)
- Accent/status colors are scoped correctly: `STATUS_STYLES` (line 6) only touches badge backgrounds and the progress-bar fill (line 118) — no bleed into unrelated chrome.
- `grep` for hardcoded hex/rgb values returned none — all color via Tailwind utility classes.
- Minor: red is reused for both "at_risk" status (line 6) and the "Delete" button (line 127) — same hue for two different semantic meanings (danger-state vs. destructive-action) risks user confusion at a glance, though this is a common and generally acceptable pattern.

### Pillar 4: Typography (2/4)
- Only two font sizes used in the entire file: `text-sm` (2 instances: lines 87, 139) and `text-xs` (used pervasively — 8+ instances). This is within the "≤4 sizes" abstract guideline, but the near-total dominance of `text-xs` for both body copy, progress-bar stats, and empty states means there's effectively only one working size doing all the work — no differentiation between primary content (program name) and tertiary metadata (owner/framework).
- Only two weights used: `font-semibold` (headings, 2 instances) and `font-medium` (program name + badge, 2 instances) — technically within the "≤2 weights" guideline, but the program name (arguably the most important scannable text in each card) shares `font-medium` with the status badge, giving no size/weight lift over surrounding metadata like owner/framework which use no weight class at all (regular default).

### Pillar 5: Spacing (3/4)
- Consistent use of standard Tailwind spacing scale throughout: `p-1`, `p-2`, `p-3`, `p-4`, `gap-1`, `gap-2`, `gap-3`, `space-y-1`, `space-y-2`, `space-y-4` — no arbitrary bracket values (`grep` for `\[.*px\]|\[.*rem\]` returned no matches).
- Card grid gap (`gap-3`, line 102) vs. form grid gap (`gap-2`, line 91) is a minor inconsistency but within reasonable design-system tolerance, not flagged as a defect.

### Pillar 6: Experience Design (2/4)
- Loading state: present for initial program list (line 100, `loading && <p>Loading...</p>`) — plain text, no skeleton/spinner despite the codebase using `Spinner`-pattern conventions elsewhere per the audit method grep list.
- Loading state for controls picker (`openControlsModal`, lines 48-58): none — if `/api/compliance` is slow, the modal opens with an empty picker and no loading indicator, indistinguishable from a genuinely empty control catalog (compounds the copywriting issue at line 157).
- Empty state: present for programs (line 133) and for filtered controls (line 157) — good coverage.
- Error state: all failures collapse to a generic toast with no retry affordance or inline error text — acceptable minimum but not robust.
- Disabled/in-flight state: present for "Save" in the controls modal (`disabled={savingControls}`, line 161) but conspicuously absent for "Create" (line 96) and "Delete" (line 127) — a user can double-click Create to fire duplicate POST requests, or double-click Delete before the first request resolves.
- Destructive-action confirmation: present (line 40) but implemented via native `window.confirm`, not the app's own modal system, and untestable via the same UI-automation path used for the rest of the component (see Fix #3).

---

## Files Audited
- `/home/user/enterprise-omni-agent-ai-platform/components/ProgramsDashboard.tsx` (170 lines, only frontend file in this phase's SUMMARY.md file list)

No `backend/*.py` files audited (out of scope for a UI/visual review — this phase's other 4 modified files are backend-only per `16-01-SUMMARY.md`).
