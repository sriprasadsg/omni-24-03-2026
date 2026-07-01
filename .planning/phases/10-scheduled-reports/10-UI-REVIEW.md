# Phase 10 — UI Review

**Audited:** 2026-06-22
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md for this phase)
**Screenshots:** Not captured (no dev server detected)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Labels are mostly clear; empty-state CTA is actionable; generic "Cancel" on modal and silent history fetch failure are minor gaps |
| 2. Visuals | 2/4 | Toggle switch and card grid are functional but icon-only close button (✕) has no aria-label; emoji icons in channel picker lack accessible alternatives; no visual distinction between enabled/disabled schedule cards |
| 3. Color | 3/4 | Semantic colors used correctly (green=success, red=error, amber=urgent); no hardcoded hex values; channel icon "🟦" for Teams bypasses color system entirely |
| 4. Typography | 3/4 | Seven distinct sizes in use including text-5xl on empty-state emoji which is not type hierarchy; weight distribution (bold/semibold/medium) is reasonable; no arbitrary text-[Npx] values found |
| 5. Spacing | 3/4 | Spacing uses Tailwind scale consistently; action row buttons (py-1.5) render at approximately 30px height, below 44px touch target minimum; history table rows have py-1 (8px), too dense for touch |
| 6. Experience Design | 2/4 | runNow has loading state; history fetch has loading state; toggleReport and deleteReport have no loading/optimistic feedback; history fetch errors are silently swallowed; native confirm() used for destructive delete; no error boundary; no keyboard trap on modal |

**Overall: 16/24**

---

## Top 3 Priority Fixes

1. **Silent history fetch failure** — Users who open the history panel on a network error see "No delivery history yet" with no indication that a fetch was attempted and failed. They cannot distinguish "no records" from "failed to load." Fix: add an `historyError` state per card, render "Failed to load history — Retry" with a retry button when the catch block fires (line 169).

2. **Action buttons below 44px touch target** — The Run Now / History / Delete buttons use `py-1.5` (6px top+bottom padding) with `text-xs` (12px line-height ~20px), producing an estimated 32px click target. On mobile this causes mis-taps, particularly on the Delete button adjacent to History. Fix: change `py-1.5` to `py-2.5` on all three action buttons (lines 270, 274, 278) and verify rendered height reaches 44px.

3. **No feedback on toggleReport / deleteReport** — Clicking the toggle switch or Delete triggers a network call but the card shows no in-flight state. On slow connections the user may click repeatedly, causing duplicate requests. Fix: add a per-card `toggling` state similar to the existing `running` state; disable the toggle and delete button during the request; show a brief spinner or opacity reduction.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

**PASS:**
- Empty state (line 201-203): "No scheduled reports yet" + "Set up automated reports delivered to email, Slack, or your SIEM" — specific and actionable.
- CTA copy: "Schedule Report" (line 182), "Schedule First Report" (line 203), "+ Schedule Report" are consistent.
- Run Now label (line 271) changes to "Running..." during flight — appropriate microcopy.
- History toggle text switches between "History" and "Hide" (line 275) — clear.
- Error display uses `d.detail` from the server (line 133) rather than a generic fallback string.

**WARNING:**
- "Cancel" (line 400) is acceptable but not specific. "Discard" or "Close" would signal consequence.
- History loading state text is "Loading..." (line 285) — functional but could be "Loading delivery history..." for context.
- History error is silently caught (line 169 `/* silently leave logs empty */`): the empty-state message "No delivery history yet" (line 287) is displayed for both genuine empty and fetch-failed states — a copywriting lie.
- `confirm('Delete this scheduled report?')` (line 155) uses browser native dialog with no context about consequences (delivery logs lost? reversible?).

### Pillar 2: Visuals (2/4)

**PASS:**
- Stats grid (lines 186-196) provides a quick frequency count overview — useful visual anchor at top of page.
- Report cards use `hover:border-gray-500 transition-colors` — tactile hover feedback.
- Frequency colored with distinct hues per FREQ_COLORS (blue/purple/green/orange).
- Enabled/disabled toggle is visually distinct (green-500 vs gray-600).

**WARNING — BLOCKER CLASS:**
- Close button on modal (line 329): `✕` text character with no `aria-label`. Screen reader announces "times" or nothing useful.
- Channel icons in picker (lines 370-376) are emoji (📧🔗💬🟦) with no `aria-hidden="true"` + adjacent label. Screen readers will announce the emoji descriptions mid-label.
- `🟦` as the Teams icon (line 72) is a colored square emoji — semantically opaque, bypasses icon system. A user with a custom font or Windows older emoji set sees a different color box.
- Disabled schedule cards are visually identical to enabled ones (same bg-gray-800, same border). A `opacity-60` or subtle indicator when `rep.enabled === false` would prevent confusion.
- History table inside a card creates vertical scroll pressure on small viewports; no max-height/overflow-y is set on the history panel, so large history dumps will push card content off screen.

### Pillar 3: Color (3/4)

**PASS:**
- No hardcoded hex values or `rgb()` calls found in the component.
- Semantic mapping is correct: `text-green-400` for success, `text-red-400` for failure, `text-amber-300` for upcoming runs, `text-red-400 font-bold` for imminent runs.
- Blue accent (`bg-blue-600`) is scoped to the primary CTA only — not over-applied.
- Delete button uses `bg-red-900/40` (muted) rather than full red, avoiding alarm fatigue for a common action.

**WARNING:**
- `text-5xl` emoji in empty state (line 200) renders in the OS emoji color palette, which is not controlled by the design system. On dark mode this is fine; on system-forced light mode it may clash.
- `text-blue-300` for daily, `text-purple-300` for weekly, `text-green-300` for monthly, `text-orange-300` for quarterly — all at 300 weight on `bg-gray-800`. Contrast ratio for 300-weight colors on dark gray may fall short of WCAG AA (4.5:1 for small text). Not confirmed without rendering, but flagged.
- `bg-blue-900/20` (20% opacity) for selected frequency/channel tiles could be insufficient contrast difference versus unselected `border-gray-600` on some displays.

### Pillar 4: Typography (3/4)

**PASS:**
- No arbitrary `text-[Npx]` values found.
- Font weight hierarchy is clear: `font-bold` for section headings, `font-semibold` for card titles, `font-medium` for interactive labels, default for body text.
- Body text minimum is `text-xs` (12px) — acceptable for dense data tables inside cards; not used for primary reading content.

**WARNING:**
- Seven distinct text sizes in use: `text-xs`, `text-sm`, `text-base` (implicit default), `text-lg`, `text-2xl`, `text-5xl` — that is five explicit classes plus base. The `text-5xl` on the empty-state emoji (line 200) is a presentational scale, not a typographic scale step. It should use `text-4xl` max or be replaced with an icon component.
- `text-lg` is used only for the modal title (line 328) and the empty-state "No scheduled reports yet" (line 201). Two uses of the same size for very different hierarchy levels weakens the scale's meaning.
- Report card titles (`font-semibold`, implicit `text-base`) and the page `h1` (`text-2xl font-bold`) are the only clear hierarchy anchors; the stats grid numbers (`text-2xl font-bold`) compete with the page heading visually.

### Pillar 5: Spacing (3/4)

**PASS:**
- All spacing uses Tailwind scale (p-4, p-5, p-6, px-3/4/6, py-1/1.5/2, gap-2/3, mb-1/2/3/4/5/6, mt-0.5/1/2/4, space-y-1.5/4). No arbitrary values.
- Modal uses `max-h-[90vh] overflow-y-auto` — one arbitrary value but acceptable for viewport-relative modal constraint.
- Card internal spacing is consistent: `p-5` on cards, `mb-3` between sections, `gap-2` on action row.

**WARNING:**
- Action buttons: `py-1.5` = 6px top + 6px bottom + ~20px line-height = approximately 32px. Touch target minimum is 44px. All three card action buttons fail this standard (lines 270, 274, 278).
- History table cell padding `py-1` (4px top + 4px bottom + 20px = ~28px rows) — too tight for touch targets in the table.
- The stats grid uses `gap-3` (12px) while the card grid uses `gap-4` (16px). Minor inconsistency but within acceptable range.
- Empty state has `py-20` (80px) vertical padding — generous whitespace, not a defect, but note it could feel disconnected on mobile.

### Pillar 6: Experience Design (2/4)

**PASS:**
- `runNow` shows "Running..." and disables the button during flight (lines 269-271).
- History fetch shows "Loading..." during load (line 285).
- History results are cached per card — avoids redundant fetches on toggle.
- `createReport` disables "Schedule Report" during save and shows "Saving..." (lines 396-398).
- Framework picker only appears for relevant report types (conditional render, lines 345-354).
- Recipients field only appears for email channel (lines 379-385); webhook URL only for webhook/slack/teams (lines 387-393).

**WARNING — BLOCKER CLASS:**
- `toggleReport()` (lines 137-143): No loading state, no optimistic update, no error handling. A failed toggle silently reverts on the next `loadReports()` call — but the user sees the toggle visually flip then flip back with no explanation.
- `deleteReport()` (lines 154-158): Uses `window.confirm()` — not a modal, no context about what is lost, cannot be styled, blocked by popup blockers in some enterprise environments.
- History fetch error is explicitly silenced (line 169). The catch block has a comment acknowledging this: `/* silently leave logs empty */`. Users see "No delivery history yet" even when the API returned 500.
- No error boundary wraps the component. A runtime error in `relativeTime()` with malformed date input from the API would crash the entire dashboard.
- Modal (lines 323-406) has no focus trap. Keyboard users can Tab out of the modal into the background content. ESC key is not wired to close the modal.
- `loadReports()` on initial load (line 101-106) catches errors silently — if the endpoint fails, the user sees the empty state with no retry mechanism. There is no way to distinguish "server error" from "no reports yet" on the initial load failure path.

---

## Files Audited

- `/home/user/enterprise-omni-agent-ai-platform/components/ScheduledReportsDashboard.tsx` (409 lines — primary audit target)
- `/home/user/enterprise-omni-agent-ai-platform/.planning/phases/10-scheduled-reports/10-01-SUMMARY.md`
- `/home/user/enterprise-omni-agent-ai-platform/.planning/phases/10-scheduled-reports/10-02-SUMMARY.md`
