# Phase 19 — UI Review (Re-audit #4)

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured (no dev server running on :3000/:5173/:8080; code-only audit)
**History:** 15/24 (original, BLOCKER: frameworks unreachable) → 17/24 (BLOCKER fixed, grid/scale regression introduced) → 19/24 (grid/scale fix verified, error-state gap still open) → 20/24 (error-state gap verified fixed) → this audit (color-consolidation fix verified)

---

## Fix Verification: Semantic Color Consolidation — RESOLVED

Commit `fe04a4e` directly addresses the last audit's #1 priority fix.

- **Single source of truth added.** Lines 61-66 define `SEMANTIC = { primary, pass, partial, fail }`, each with `hex` (solid fill), `rgb` (comma-joined triplet for building rgba strings), and `text` (the lighter tint previously hardcoded as e.g. `#6ee7b7`). A `semanticBg(key, alpha)` helper (lines 70-72) builds `rgba(r,g,b,alpha)` from the triplet, replacing every hand-typed `rgba(16,185,129,.12)`-style literal.
- **Verified fully migrated, not partially.** Grepping the file for the four semantic hex values (`#10b981`, `#f59e0b`, `#ef4444`, `#6366f1`) and their rgb triplets turns up exactly one hit each — the `SEMANTIC` object's own declaration (lines 62-65). `FRAMEWORK_COLOR_PALETTE` (lines 47-50) still contains 12 raw hex literals, but that is a *different*, legitimately-standalone system (per-framework identity hashing via `colorForFramework`) that was never in scope for this fix and correctly remains untouched.
- **Every previously-flagged call site now references the constant:** `StatusBadge` cfg (91-93), header GRC label (218), scan/re-evaluate buttons (227, 234), scan-message branch (239), both error banners — summary (250, 255) and detail (319, 324) — plus their Retry buttons, score-card pass/partial/fail counts (303-305), filter-tab active state (343-344), and the group "N failing" pill (368). All nine sites previously flagged (the four original plus the fifth the last audit noted the new error banners had added) are now single-sourced.
- **No visual regression.** Every `SEMANTIC.<key>.hex/text` and `semanticBg(key, alpha)` call resolves to the exact same hex/rgba value that was previously hardcoded at that site — this was confirmed by inspecting each call site's resolved value against the pre-fix literals recorded in the prior audit (e.g. `StatusBadge`'s pass color was `#6ee7b7` and `SEMANTIC.pass.text` is `#6ee7b7`; the fail banner background was `rgba(239,68,68,.1)` and `semanticBg('fail', .1)` resolves to the same). This is a pure declaration-site refactor as claimed, not a visual change.

This is a complete, verified resolution of the Pillar 3 finding that persisted across the prior three audits.

---

## Confirmation: Two Other Open Findings — STILL PRESENT, NOT ADDRESSED

1. **No shimmer/pulse on un-loaded score-ring placeholder (still open).** Line 298: `s ? <ScoreRing ... /> : <div style={{ width: 70, height: 70, background: 'rgba(255,255,255,.05)', borderRadius: '50%' }} />`. Only one keyframe (`spin`, line 214) exists in the file, applied solely to the scan-refresh icon (line 228). No `pulse`/`shimmer` keyframe or `animation` property was added to the placeholder. Unchanged from the last audit.
2. **8-9 font sizes / 4 font weights in one file (still open).** Current distinct sizes: `0.72em, 0.75em, 0.78em, 0.82em, 0.85em, 0.88em, 0.9em, 0.95em, 1.8em` (9 values, one more than the prior audit's count of 8 — new banner text added `0.9em` alongside existing `0.85em`, both used for near-identical structural purposes). Weights unchanged at 4: `600, 700, 800, 900`. Not addressed by this fix, and not in scope for it.

Both findings are confirmed present verbatim and are re-flagged below.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Unchanged — dynamic subtitle, search/empty-state, and error-banner copy remain specific and non-generic |
| 2. Visuals | 3/4 | Unchanged — loading placeholder for un-loaded score rings remains a static grey circle with no shimmer — **still open** |
| 3. Color | 4/4 | **RESOLVED THIS ROUND** — single `SEMANTIC` constant + `semanticBg()` helper now back every one of the 9 previously-duplicated call sites; grep confirms zero remaining stray literals for these four colors outside the one declaration site |
| 4. Typography | 3/4 | Unchanged — 9 distinct em-based sizes (one more than last audit) and 4 weights in one file, exceeding the ≤4 sizes / ≤2 weights guideline |
| 5. Spacing | 3/4 | Unchanged — consistent 4px-multiple spacing values, but 100% inline `style={{}}` with no shared spacing tokens |
| 6. Experience Design | 4/4 | Unchanged from last audit — fetch failures on both summary and detail surface a visible, retry-capable error banner; no regression introduced by the color refactor |

**Overall: 21/24** (prior: 20/24, before that: 19/24, 17/24, original: 15/24)

---

## Top 3 Priority Fixes

1. **Loading placeholder for score rings has no skeleton/shimmer** (line 298 — plain static grey circle) — User impact: minor but noticeable at scale; when several cards are mid-fetch there's no visual cue distinguishing "in progress" from "this framework permanently has no score." Concrete fix: add a `@keyframes pulse` sibling to the existing `@keyframes spin` (line 214) and apply `animation: 'pulse 1.5s ease-in-out infinite'` to the placeholder div.

2. **9 font sizes / 4 font weights in one component file** (sizes `0.72em` through `1.8em`; weights `600/700/800/900`) — User impact: subtle but real inconsistency in visual rhythm — badge text (`0.72em`/700), card names (`0.95em`/800), and group headers (`0.88em`/700) are near-identical-but-not-quite type treatments doing the same structural job, reading as unintentional drift. The new detail-error banner text (`0.9em`) added yet another near-duplicate of the existing `0.85em` banner size rather than reusing it. Concrete fix: consolidate to a 4-size scale (e.g., `0.75em` caption / `0.85em` body / `1em` emphasis / `1.5em` heading) and 2 weights (600, 800), remapping each literal to the nearest tier — and while doing so, fold the summary/detail banner sizes onto the same tier.

3. **100% inline `style={{}}` with no shared spacing tokens** — User impact: low today (values are consistently on a 4px scale), but every new element requires re-deriving spacing by eye rather than picking from a defined scale, which is how the font-size sprawl above originated. Concrete fix: extract a small `SPACING = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 }` constant (mirroring the `SEMANTIC` pattern just established for color) and reference it from padding/margin/gap props.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- Unchanged from last audit — header subtitle, search placeholder, empty-state copy, and the two error-banner messages remain accurate, specific, and distinct per failure surface. `Retry` label is short and consistent.

### Pillar 2: Visuals (3/4)
- Grid auto-fill, search, and error banners from prior fixes remain intact.
- **Unchanged gap:** un-loaded score-ring placeholder (line 298) remains a static grey circle with no shimmer/pulse.

### Pillar 3: Color (4/4)
- **Resolved this round.** `SEMANTIC` constant (lines 61-66) plus `semanticBg()` helper (70-72) is now the single declaration site for `primary`/`pass`/`partial`/`fail` colors. Verified via targeted grep: `#6ee7b7`, `#fcd34d`, `#fca5a5`, `#10b981`, `#f59e0b`, `#ef4444`, `#6366f1`, and their rgb triplets each appear exactly once in the file (within the `SEMANTIC` object itself) — no stray re-typed copies remain in `StatusBadge`, the score-card counts, filter tabs, scan-message branch, error banners, or the failing-count pill, all of which now call `SEMANTIC.<key>.hex/text` or `semanticBg(key, alpha)`.
- `FRAMEWORK_COLOR_PALETTE` (12 raw hex values, lines 47-50) is correctly left as-is — a distinct, legitimate identity-hashing palette that was never part of this finding.
- No visual regression: every migrated call site resolves to the identical value it held before the refactor.

### Pillar 4: Typography (3/4)
- Untouched by this fix. 9 distinct font sizes (`0.72em` through `1.8em`, one more than the previous audit due to the detail-error banner's `0.9em` sitting alongside the summary-error banner's pre-existing `0.85em`) and 4 weights (`600, 700, 800, 900`) remain in one file.

### Pillar 5: Spacing (3/4)
- Untouched by this fix. Spacing values remain consistent 4px multiples; component remains 100% inline styles with no shared spacing tokens.

### Pillar 6: Experience Design (4/4)
- Unchanged from last audit and unaffected by the color refactor: `summaryError`/`detailError` banners with Retry affordance, proper loading/empty-state gating, and `AbortError` guards all remain intact and correctly scoped.
- Confirmed no regression: the refactor is purely a color-declaration change and touches no state, fetch, or gating logic.

---

## Files Audited
- `components/ComplianceFrameworksDashboard.tsx` (full file, 397 lines, post-color-consolidation-fix version, commit `fe04a4e`)
- `.planning/phases/19-compliance-frameworks/19-UI-REVIEW.md` (prior audit, used as comparison baseline — content superseded by this file)
- `.planning/phases/19-compliance-frameworks/19-01-SUMMARY.md`
- `.planning/phases/19-compliance-frameworks/19-01-PLAN.md`

No `src/` frontend files were relevant (frontend tree lives at repo root under `components/`). No `components.json`/shadcn registry present — registry safety audit skipped. No dev server was running on :3000/:5173/:8080, so this remains a code-only audit; the color-consolidation claims are verified via direct grep and line-by-line call-site inspection, not observed screenshots.
