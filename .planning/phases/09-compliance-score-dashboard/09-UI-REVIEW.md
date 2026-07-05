# Phase 9 — UI Review

**Audited:** 2026-07-06
**Baseline:** .planning/phases/09-compliance-score-dashboard/09-UI-SPEC.md
**Screenshots:** not captured (no dev server running at localhost:3000/5173)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | All contract strings match exactly, but score numbers aren't formatted to one decimal place, breaking the "87.3%"-style contract example |
| 2. Visuals | 2/4 | Declared "Score Ring" circular display (80px, `w-20 h-20`) is entirely absent — plain text number only |
| 3. Color | 4/4 | All thresholds, accent, and severity legend colors match spec exactly with proper dark: variants |
| 4. Typography | 4/4 | Only the four declared sizes/weights are used, no arbitrary `text-[Npx]` |
| 5. Spacing | 3/4 | Standard spacing matches spec, but the declared 80px score-ring spacing exception is unimplemented |
| 6. Experience Design | 3/4 | Loading/error/empty states solid, but tooltip lacks `role="tooltip"`/`aria-describedby`, and empty-state condition diverges from spec's exact boolean logic |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **Score numbers don't enforce one decimal place** — `components/ComplianceScorePanel.tsx:170` (`{data.overall_score}%`) and `:212` (`{fw.score}%`) render the raw JS number. Backend returns `round(x, 1)` (`backend/compliance_score_endpoints.py:73`), so a score like `80.0` serializes as `80.0` in JSON but JS drops the trailing zero, rendering `"80%"` instead of the contracted `"80.0%"` shown in the spec's own example (`87.3%`). This creates inconsistent formatting across framework rows (e.g., `"87.3%"` next to `"72%"`). Fix: use `data.overall_score.toFixed(1)` and `fw.score.toFixed(1)`.

2. **Score Ring visual element missing entirely** — Spec's Spacing Scale (line 58) explicitly declares an 80px diameter (`w-20 h-20`) circular score ring as "required for legibility of the large percentage number," and the layout diagram (Section 3, line 189) labels the block "Score Ring / Large Number." The implementation (`ComplianceScorePanel.tsx:167-173`) renders only plain stacked text with no ring/circular container of any kind. This is a declared, load-bearing visual affordance that was dropped — the panel currently reads as a plain KPI card rather than the ring-emphasized headline number the contract calls for. Fix: wrap the percentage in a `w-20 h-20 rounded-full` container (e.g., a conic-gradient or SVG ring) as declared.

3. **Tooltip missing required ARIA wiring** — Spec Section 8 (Accessibility, line 403) requires `role="tooltip"` on the tooltip div and `aria-describedby` linking the trigger to it. `SeverityWeightTooltip` (`ComplianceScorePanel.tsx:29-71`) has neither: the tooltip `<div>` (line 47) has no `role` attribute, and the trigger `<span role="button">` (line 33) has no `aria-describedby`. Screen reader users focusing the info icon get no indication that a tooltip exists or what it says. Fix: give the tooltip div a stable `id`, add `role="tooltip"` to it, and add `aria-describedby={that id}` to the trigger span.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- All spec-mandated copy strings verified present and exact: "Compliance Score" (line 100), "Severity-weighted score" (line 172), tooltip title "Severity-Weighted Score" (line 48), formula line (lines 62-64), exclusion note (lines 65-67), error heading/body (lines 137, 139-141), empty state heading/body (lines 154-157), computed-at footer format (line 246), passing/failing/partial count labels (lines 177, 181, 185), drill-down copy (lines 227, 231, 235), all aria-labels (lines 36, 199).
- Deviation: no `.toFixed(1)` applied to `overall_score`/`fw.score` before interpolation (lines 170, 212) — see Fix #1 above. The spec's copywriting contract implicitly assumes consistent one-decimal display via its own example ("87.3%"); a whole-number score silently loses that formatting.

### Pillar 2: Visuals (2/4)
- Panel header, framework rows, progress bars, drill-down rows, and loading/error/empty layouts all structurally match the spec's ASCII diagrams (Sections 3, 5, 7).
- Missing: Score Ring circular container (spec line 58, Section 3 line 189) — see Fix #2. This is the single largest declared visual element in the "Overall Score Display" region and it's absent, not degraded — a full miss, not a minor variance.
- Chevron rotation, hover states, and dot indicators (lines 176, 180, 184) are correctly implemented and match declared visual treatment.

### Pillar 3: Color (4/4)
- `scoreColor()`/`barColor()` (lines 13-22) match the spec's exact threshold rule (≥80 green, 50-79 amber, <50 red) applied consistently to both the overall score and per-framework scores.
- Accent indigo reserved for the ShieldCheckIcon only (line 99), consistent with Section 4's explicit override of the summary table's more general indigo-on-score-number note.
- Severity legend colors in the tooltip (lines 51-54) match spec exactly (red-600/orange-500/yellow-500/blue-500).
- All color utilities have `dark:` counterparts (verified for score text, bar fills, backgrounds, borders) — no bare light-mode-only color found.
- No hardcoded hex/rgb values found in the component (grep clean).

### Pillar 4: Typography (4/4)
- Sizes used: `text-3xl` (line 169), `text-lg` (line 100), `text-sm` (multiple), `text-xs` (multiple) — exactly the four declared sizes, no others.
- Weights used: `font-bold` (line 169), `font-semibold` (lines 100, 137, 48), `font-medium` (multiple) — within the declared two-weight budget (bold/semibold treated as the "Display/Heading" pairing, medium for Label/emphasis; no arbitrary weight found).
- No `text-[Npx]` arbitrary sizing found anywhere in the file.

### Pillar 5: Spacing (3/4)
- Standard scale usage verified: `p-4` section padding (multiple), `mb-4` summary block spacing (line 167), `h-1.5` progress bar height (line 205), `gap`/`space-y-1` for tooltip rows and counts, `min-h-[44px]` touch target on framework rows (line 196) — all match declared tokens.
- Deviation: the declared 80px score-ring exception (`w-20 h-20`, spec line 58) is unused because the ring itself was never built (ties to Visuals Fix #2) — the spacing token exists in the contract specifically to support an element that isn't there.

### Pillar 6: Experience Design (3/4)
- Loading state: `aria-busy="true"` on root (line 115), sr-only label (line 119), skeleton blocks with `aria-hidden="true"` (lines 120, 122) — matches spec exactly.
- Error state: `role="alert"` (line 133), amber container, icon + heading + body — matches spec exactly.
- Accordion: each framework row is a real `<button>` with `aria-expanded`, `aria-controls`, and dynamic `aria-label` (lines 195-199) — matches spec's keyboard accessibility requirement precisely.
- Gap: tooltip lacks `role="tooltip"` + `aria-describedby` (spec line 403) — see Fix #3. This is a named, specific accessibility requirement in the design contract, not an incidental miss.
- Gap: empty-state condition uses `totalEvaluated === 0` (line 148, derived from summed `total_controls`) rather than the spec's literal `data.frameworks.length === 0 AND data.overall_score === 0` (spec lines 380-381). In the common case these coincide, but the implementation's condition is not equivalent to the contract's stated boolean — e.g., a tenant with frameworks defined but zero controls evaluated in any of them would hit the empty state under the implementation even if `overall_score` were non-zero, which cannot happen mathematically, but the divergence from the literal spec means the escape hatch (Section 7's "Zero-score non-empty state") is reachable in ways the spec didn't anticipate testing against. Low risk but a real logic deviation from the written contract.
- Tooltip keyboard handler (line 42) only opens on Enter/Space via `onFocus()`, with no explicit close/toggle behavior on repeat key press or Escape — functional but minimal relative to a typical accessible tooltip pattern.

---

## Registry Safety

No `components.json` found — shadcn not initialized. Registry audit skipped (matches UI-SPEC.md's own Registry Safety section, which declares no third-party registries in use).

---

## Files Audited

- `/home/user/enterprise-omni-agent-ai-platform/components/ComplianceScorePanel.tsx`
- `/home/user/enterprise-omni-agent-ai-platform/components/Dashboard.tsx` (mount point, lines 48-51)
- `/home/user/enterprise-omni-agent-ai-platform/backend/compliance_score_endpoints.py` (score formatting source, lines 60-77)
- `/home/user/enterprise-omni-agent-ai-platform/.planning/phases/09-compliance-score-dashboard/09-UI-SPEC.md`
- `/home/user/enterprise-omni-agent-ai-platform/.planning/phases/09-compliance-score-dashboard/09-01-SUMMARY.md`
- `/home/user/enterprise-omni-agent-ai-platform/.planning/phases/09-compliance-score-dashboard/09-02-SUMMARY.md`
