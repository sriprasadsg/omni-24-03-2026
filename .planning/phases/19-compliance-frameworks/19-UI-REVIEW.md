# Phase 19 — UI Review (Re-audit #2)

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured (no dev server running on :3000/:5173/:8080; code-only audit)
**History:** 15/24 (original, BLOCKER: frameworks unreachable) → 17/24 (BLOCKER fixed, grid/scale regression introduced) → this audit (grid/scale fix verified)

---

## Fix Verification: Grid/Scale Issue — RESOLVED

Commit `d1c7eb3` addresses the prior audit's top priority fix directly:

- **Grid:** `gridTemplateColumns` changed from `repeat(3, 1fr)` (line 211 in the prior version) to `repeat(auto-fill, minmax(260px, 1fr))` (line 237 in the current file). This means the card grid now wraps responsively at any viewport width and at any framework count — 6 cards or 44 cards both render correctly, with no fixed column count forcing overflow or cramped columns on narrow screens.
- **Search/filter:** A new `search` state and input (lines 101, 213-228) filters `frameworkIds` into `visibleFrameworkIds` (lines 146-149) by matching the query case-insensitively against either the raw `fid` or the summary's display `name`. This gives users a way to jump directly to a framework instead of scanning ~15 rows of cards.
- **Empty state:** A new "No frameworks match "{search}"." message (line 235) covers the zero-result search case, and the pre-existing "Loading frameworks…" state (line 232) is preserved and correctly gated on `loading && frameworkIds.length === 0`.
- **Verified no regression:** the loading-state logic, framework-count subtitle (line 186), and role-gated scan/re-evaluate buttons are all unchanged from the prior fix and still function correctly.

This is a complete, verified resolution of the Pillar 2/Pillar 5 regression flagged in the last audit. Both pillars are restored to their pre-regression scores this round.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Dynamic framework count subtitle and new empty-state/search-placeholder copy remain accurate and specific |
| 2. Visuals | 3/4 | Grid/scale regression resolved via auto-fill + search; loading placeholder for un-loaded score rings is still a plain grey circle with no skeleton shimmer |
| 3. Color | 3/4 | Unchanged: 12-color hash palette is a real improvement, but 12+ hardcoded hex values (StatusBadge, header accent, overlays) remain with no shared token source — **still open** |
| 4. Typography | 3/4 | Unchanged: 8 distinct em-based sizes and 4 weights in one file, exceeding the ≤4 sizes / ≤2 weights guideline |
| 5. Spacing | 3/4 | Grid/scale regression resolved via `auto-fill, minmax(260px, 1fr)`; component remains 100% inline `style={{}}` with no shared spacing tokens |
| 6. Experience Design | 3/4 | Search/empty-state improves usability, but fetch-error gap (silent `console.error` on summary/detail failures, no visible banner) remains unfixed — **still open** |

**Overall: 19/24** (prior: 17/24, original: 15/24)

---

## Top 3 Priority Fixes

1. **No user-facing error state on fetch failure** (`components/ComplianceFrameworksDashboard.tsx:108, 120` — `console.error` only, no state update) — User impact: if `GET /api/frameworks/summary` or `GET /api/frameworks/{id}` fails, the user sees a stale or perpetually-loading UI with zero indication anything went wrong; unchanged across two audits despite the app depending entirely on these two endpoints for a compliance-facing feature. Concrete fix: add an `error` state set in each `catch` block (mirroring the existing `AbortError` guard), rendered as a visible inline banner reusing the `scanMessage` failure-styling pattern already used at line 205 (`color: '#fca5a5'`).

2. **12+ hardcoded hex values remain with no shared token source** (`StatusBadge` cfg object lines 74-79; header accent `#6366f1` line 184; scattered `#94a3b8`, `#a5b4fc`, `#6ee7b7`, `#fcd34d`, `#fca5a5` throughout) — User impact: color drift risk persists — e.g., `StatusBadge`'s pass color `#6ee7b7` is a different green than any entry in the new `FRAMEWORK_COLOR_PALETTE`, and the same green/amber/red trio is redefined by hand in at least 4 separate places in the file. Concrete fix: extract one shared `SEMANTIC_COLORS` constant (pass/partial/fail/na) reused by `StatusBadge`, the pass/partial/fail counts on each card (lines 254-256), and the panel filter buttons.

3. **Loading placeholder for score rings has no skeleton/shimmer** (line 249 — plain static grey circle, `background: 'rgba(255,255,255,.05)'`) — User impact: minor but noticeable at scale; when many cards are mid-fetch there's no visual indication of "in progress" vs. "this framework has no score," which reads as inert rather than loading. Concrete fix: add a CSS shimmer/pulse animation to the placeholder circle (the file already defines a `@keyframes spin` at line 180, so a `@keyframes pulse` sibling is a low-cost, consistent addition).

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- Header subtitle (line 186) remains fully dynamic and correctly pluralized.
- New copy introduced by this fix is equally precise: `Search {frameworkIds.length} frameworks…` (line 220) tells the user exactly what's being searched, and `No frameworks match "{search}".` (line 235) echoes the query back so the user can immediately see what didn't match — both are specific, non-generic empty-state patterns.
- Button labels, status badges, and scan messaging remain unchanged and still appropriately specific.

### Pillar 2: Visuals (3/4)
- **Regression resolved:** the fixed 3-column grid flagged in the last audit is gone; `repeat(auto-fill, minmax(260px, 1fr))` (line 237) lets the grid collapse to fewer columns on narrow viewports and expand on wide ones, with no overflow risk at any framework count.
- **Regression resolved:** the search input (lines 213-228) gives users a direct way to locate a specific framework among ~44, addressing the "wall of undifferentiated cards" concern from last audit.
- Score-ring cards plus expandable grouped control table below remains a reasonable two-level information hierarchy.
- Icon-only elements remain always paired with text labels.
- **Unchanged minor gap:** the un-loaded score-ring placeholder (line 249) is a static grey circle with no shimmer/pulse, giving no visual cue that it's a loading state rather than a permanently-empty one.

### Pillar 3: Color (3/4)
- Unchanged from last audit. `colorForFramework()` hash-palette approach (lines 47-56) remains a genuine improvement over the original 6-entry static map.
- **Still open:** 12+ hardcoded hex values remain scattered through `StatusBadge` (lines 75-78), the header accent (line 184, `#6366f1`), and various `rgba(255,255,255,...)` overlays, with no CSS custom properties or shared constant. This fix was not in scope for commit `d1c7eb3` and remains exactly as flagged previously.
- Hash collisions (44 frameworks into 12 colors) remain a reasonable, acknowledged tradeoff, not a new issue.

### Pillar 4: Typography (3/4)
- Untouched by this fix. Still 8 distinct font sizes (`0.72em` through `1.8em`) and 4 weights (`600, 700, 800, 900`) in one file.

### Pillar 5: Spacing (3/4)
- **Regression resolved:** `gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))'` (line 237) replaces the fixed 3-column layout that broke down at 44 cards. This restores the score to its pre-regression level.
- Base spacing values (28px/32px, 20px/24px, 12px/24px, 4-16px gaps) remain consistent 4px multiples throughout, including in the new search-bar markup (`padding: '8px 12px 8px 34px'`, `marginBottom: 16`).
- Component remains 100% inline `style={{}}` objects with no Tailwind/shared spacing tokens — unchanged, not a new finding, capping the score at 3 rather than 4.

### Pillar 6: Experience Design (3/4)
- **Improvement:** search/filter (lines 213-228) plus the "no results" empty state (line 235) meaningfully improve findability now that all 44 frameworks are reachable — a genuine UX upgrade layered on top of the prior BLOCKER fix.
- **Unresolved from two prior audits:** `fetchSummary`/`fetchDetail` catch blocks (lines 108, 120) still only `console.error` with no state update or user-visible feedback. If `/summary` or `/{id}` fails, the user sees a stale or stuck-loading UI with no indication of failure. Only the manually-triggered scan action has user-facing error messaging (line 139). This is the single most consequential remaining gap in the component.
- Role-gating for `Scan All Agents` vs `Re-evaluate` (lines 90, 189-203) remains a reasonable, well-implemented permission-aware pattern.
- Loading state for the initial framework list (line 232) and the detail panel (line 268) both remain correctly gated and functional.

---

## Files Audited
- `components/ComplianceFrameworksDashboard.tsx` (full file, 335 lines, post-grid-fix version, commit `d1c7eb3`)
- `.planning/phases/19-compliance-frameworks/19-UI-REVIEW.md` (prior audit, used as comparison baseline — content superseded by this file)
- `.planning/phases/19-compliance-frameworks/19-01-SUMMARY.md`
- `.planning/phases/19-compliance-frameworks/19-01-PLAN.md`
- `backend/compliance_frameworks_endpoints.py` (re-confirmed 44-entry `_REGISTRY`, no change since last audit)

No `src/` frontend files were relevant (frontend tree lives at repo root under `components/`). No `components.json`/shadcn registry present — registry safety audit skipped. No dev server was running on :3000/:5173/:8080, so this remains a code-only audit; the grid-wrap and search-filter claims are verified by reading the CSS/logic directly, not by observed screenshots.
