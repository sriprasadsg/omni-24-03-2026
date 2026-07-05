# Phase 19 — UI Review (Re-audit #3)

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured (no dev server running on :3000/:5173/:8080; code-only audit)
**History:** 15/24 (original, BLOCKER: frameworks unreachable) → 17/24 (BLOCKER fixed, grid/scale regression introduced) → 19/24 (grid/scale fix verified, error-state gap still open) → this audit (error-state gap verified fixed)

---

## Fix Verification: Fetch-Error Banner — RESOLVED

Commit `006b301` directly addresses the last audit's #1 priority fix:

- **Summary error path:** `fetchSummary` (lines 105-121) now checks `res.ok` and sets `summaryError` to a specific `Failed to load frameworks (HTTP {status}).` message on non-2xx responses, and to `Failed to load frameworks. Check backend connection.` in the `catch` block for network/other failures (with the pre-existing `AbortError` guard preserved so aborted requests during unmount/re-fetch don't flash an error). Success clears `summaryError` back to `null` (line 110).
- **Detail error path:** `fetchDetail` (lines 123-141) mirrors the identical pattern for the per-framework detail fetch — `detailError` set on non-ok or catch, cleared on success.
- **Visible banners:** Two banner blocks render conditionally — one above the search/grid gated on `summaryError` (lines 231-243), one above the detail panel gated on `detailError && !detailLoading` (lines 300-312) so a fresh in-flight fetch doesn't show a stale error underneath its own loading spinner. Both use a consistent red-tinted style (`rgba(239,68,68,.1)` background, `#fca5a5` text, `AlertTriangle` icon) that visually matches the existing failed-scan message styling already in the file, so this isn't an ad hoc new pattern.
- **Retry affordance:** Each banner includes a `Retry` button that re-invokes the exact failed fetch (`fetchSummary()` / `fetchDetail(selected)`) — the user isn't just informed of failure, they have an immediate one-click recovery path, which exceeds the bare minimum ask (a banner alone) from the prior audit.
- **No regression:** `console.error` calls are retained alongside the new state (useful for engineering/devtools debugging) rather than replaced, and the pre-existing loading/empty-state gating logic is untouched.

This is a complete, verified resolution of the Pillar 6 finding that persisted across the prior two audits. Experience Design is restored to a full 4/4 this round — this was the single most consequential gap in the component and it is now closed.

---

## Confirmation: Two Other Open Findings — STILL PRESENT, NOT ADDRESSED

Per the phase brief, commit `006b301` was scoped only to the error-banner fix. Verified directly against the current file:

1. **Hardcoded hex color duplication (still open).** `FRAMEWORK_COLOR_PALETTE` (lines 47-50) is a real shared constant for framework-identity color, but it is a separate, disconnected system from the semantic pass/partial/fail colors, which remain hand-duplicated in at least four places: `StatusBadge`'s `cfg` object (lines 75-78: `#6ee7b7`/`#fcd34d`/`#fca5a5`/`#94a3b8`), the card pass/partial/fail counts (lines 287-289, same three hex values re-typed rather than referencing `StatusBadge`'s config), the scan-message success/fail color branch (line 223), and the group "N failing" pill (line 352, `#fca5a5` again). The header accent `#6366f1` (line 202) is also hardcoded separately from `FRAMEWORK_COLOR_PALETTE[0]`, which happens to be the same value — an accident of no shared source, not intentional reuse. No CSS custom properties or a single `SEMANTIC_COLORS` constant exists. Unchanged from the last audit.

2. **No shimmer/pulse on un-loaded score-ring placeholder (still open).** Line 282: `s ? <ScoreRing ... /> : <div style={{ width: 70, height: 70, background: 'rgba(255,255,255,.05)', borderRadius: '50%' }} />` — this placeholder circle has no animation of any kind. The file already defines `@keyframes spin` (line 198) and uses it conditionally on the scan-refresh icon, so the pattern for adding a second keyframe (e.g., `pulse`) and applying it conditionally is established elsewhere in the same file but was not extended to this element. Unchanged from the last audit.

Both findings are confirmed present verbatim and are re-flagged below.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Dynamic framework count subtitle, search/empty-state copy, and the two new error banner messages are all specific and non-generic |
| 2. Visuals | 3/4 | Grid/search improvements hold; loading placeholder for un-loaded score rings remains a static grey circle with no shimmer — **still open** |
| 3. Color | 3/4 | Unchanged: 12-color identity palette is fine, but 4+ separate hand-duplicated copies of the semantic pass/partial/fail/na hex values with no shared constant — **still open** |
| 4. Typography | 3/4 | Unchanged: 8 distinct em-based sizes and 4 weights in one file, exceeding the ≤4 sizes / ≤2 weights guideline |
| 5. Spacing | 3/4 | Unchanged: consistent 4px-multiple spacing values, but 100% inline `style={{}}` with no shared spacing tokens |
| 6. Experience Design | 4/4 | **RESOLVED THIS ROUND** — fetch failures on both summary and detail now surface a visible, retry-capable error banner instead of a silent `console.error` |

**Overall: 20/24** (prior: 19/24, before that: 17/24, original: 15/24)

---

## Top 3 Priority Fixes

1. **Semantic status colors are hand-duplicated in 4+ places with no shared constant** (`StatusBadge` cfg lines 75-78; card counts lines 287-289; scan-message branch line 223; failing-count pill line 352) — User impact: color drift risk is real, not theoretical — a future edit to "what pass-green looks like" in `StatusBadge` silently diverges from the identical-looking green used on the card counts, since they're three independent literals. Concrete fix: extract one `SEMANTIC_COLORS = { pass: '#6ee7b7', partial: '#fcd34d', fail: '#fca5a5', na: '#94a3b8' }` constant near `FRAMEWORK_COLOR_PALETTE` and reference it from all four call sites.

2. **Loading placeholder for score rings has no skeleton/shimmer** (line 282 — plain static grey circle) — User impact: minor but noticeable at scale; when several cards are mid-fetch there's no visual cue distinguishing "in progress" from "this framework permanently has no score." Concrete fix: add a `@keyframes pulse` sibling to the existing `@keyframes spin` (line 198) and apply `animation: 'pulse 1.5s ease-in-out infinite'` to the placeholder div.

3. **8 font sizes / 4 font weights in one component file** (sizes from `0.72em` to `1.8em`; weights `600/700/800/900` throughout) — User impact: subtle but real inconsistency in visual rhythm — e.g. badge text (`0.72em`/700), card names (`0.95em`/800), and group headers (`0.88em`/700) are three near-identical-but-not-quite type treatments doing the same structural job (a label), which reads as unintentional drift rather than a deliberate type scale. Concrete fix: consolidate to a 4-size scale (e.g., `0.75em` caption / `0.85em` body / `1em` emphasis / `1.5em` heading) and 2 weights (600 regular-emphasis, 800 heading), remapping each existing literal to the nearest tier.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- Header subtitle, search placeholder, and empty-state copy remain accurate and specific (unchanged from last audit).
- New error-banner copy is equally precise: `Failed to load frameworks (HTTP {status}).` and `Failed to load control detail (HTTP {status}).` distinguish the two failure surfaces rather than sharing one generic "Something went wrong," and the catch-block fallback (`Check backend connection.`) gives the user an actionable hint rather than a dead end.
- `Retry` button label is short, obvious, and consistent between both banners.

### Pillar 2: Visuals (3/4)
- Grid auto-fill and search from the prior fix remain intact and correctly verified again in this file (`repeat(auto-fill, minmax(260px, 1fr))`, line 270; search input, lines 246-261).
- New error banners are visually consistent with each other and with the existing failed-scan-message color treatment — no new one-off visual pattern introduced.
- **Unchanged minor gap:** un-loaded score-ring placeholder (line 282) remains a static grey circle with no shimmer/pulse, still reading as inert rather than loading.

### Pillar 3: Color (3/4)
- `colorForFramework()` hash-palette (lines 52-56) remains a genuine, single-source approach for framework identity color — no regression there.
- **Still open:** semantic pass/partial/fail/na colors are copy-pasted as literals in `StatusBadge` (75-78), card summary counts (287-289), scan-message coloring (223), and the group failing-count pill (352) — four independent sources of truth for what should be one shared constant. The new error banners (lines 231-243, 300-312) additionally introduce a fifth hardcoded instance of the fail-red (`#fca5a5`, `rgba(239,68,68,...)`), consistent in appearance with the existing pattern but adding to, not reducing, the duplication count. This fix was out of scope for commit `006b301` and remains exactly as previously flagged.

### Pillar 4: Typography (3/4)
- Untouched by this fix. Still 8 distinct font sizes (`0.72em` through `1.8em`) and 4 weights (`600, 700, 800, 900`) in one file. New banner text uses `0.85em`/`0.9em`, adding no new tier but not reducing the existing spread either.

### Pillar 5: Spacing (3/4)
- Untouched by this fix. Base spacing values remain consistent 4px multiples (new banner uses `padding: '10px 16px'`, `marginBottom: 16`, `gap: 12` — all on-scale).
- Component remains 100% inline `style={{}}` objects with no Tailwind/shared spacing tokens — unchanged, capping the score at 3.

### Pillar 6: Experience Design (4/4)
- **Resolved this round:** `fetchSummary`/`fetchDetail` failures (HTTP non-ok or thrown error) now set `summaryError`/`detailError` state, rendered as a visible banner with an icon and specific message, positioned directly above the affected section (summary banner above the search/grid, detail banner above the detail panel) so the user knows exactly which fetch failed.
- **Retry affordance exceeds the minimum ask:** each banner's `Retry` button re-invokes the exact failed request rather than requiring a full page reload or unrelated action.
- **Correctly scoped, no over-triggering:** the detail banner is gated on `!detailLoading` so it doesn't flash a stale error underneath an in-flight retry's own loading spinner (line 300); the `AbortError` guard prevents an error banner from firing when a fetch is intentionally cancelled by rapid framework-switching (lines 115, 135).
- Search/empty-state (from the prior fix), role-gated scan/re-evaluate buttons, and loading states for both the framework list and the detail panel all remain correctly implemented with no regression.
- No remaining BLOCKER or unaddressed WARNING-level gap in this pillar.

---

## Files Audited
- `components/ComplianceFrameworksDashboard.tsx` (full file, 381 lines, post-error-banner-fix version, commit `006b301`)
- `.planning/phases/19-compliance-frameworks/19-UI-REVIEW.md` (prior audit, used as comparison baseline — content superseded by this file)
- `.planning/phases/19-compliance-frameworks/19-01-SUMMARY.md`
- `.planning/phases/19-compliance-frameworks/19-01-PLAN.md`

No `src/` frontend files were relevant (frontend tree lives at repo root under `components/`). No `components.json`/shadcn registry present — registry safety audit skipped. No dev server was running on :3000/:5173/:8080, so this remains a code-only audit; the error-banner claims are verified by reading the state/render logic directly, not by observed screenshots or simulated network failures.
