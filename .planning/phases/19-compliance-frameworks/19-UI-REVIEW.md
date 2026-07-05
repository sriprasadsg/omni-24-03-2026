# Phase 19 — UI Review (Re-audit #5, final)

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured (no dev server running on :3000/:5173/:8080; code-only audit)
**History:** 15/24 (original, BLOCKER: frameworks unreachable) → 17/24 (BLOCKER fixed, grid/scale regression introduced) → 19/24 (grid/scale fix verified, error-state gap still open) → 20/24 (error-state gap verified fixed) → 21/24 (color-consolidation fix verified, 2 findings remained) → **this audit (both remaining findings verified fixed)**

---

## Fix Verification: Both Remaining Findings — RESOLVED

Commit `7b1f1de` addresses both open items from the 21/24 audit.

**1. Score-ring loading placeholder shimmer — RESOLVED.**
- Line 221: a second keyframe rule was added alongside the pre-existing `spin`: `@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`.
- Line 306: the un-loaded placeholder div (`s ? <ScoreRing .../> : <div ... />`) now carries `animation: 'pulse 1.5s ease-in-out infinite'` in addition to its existing static styles. Verified by direct read — this is the exact element flagged in the prior three audits.
- No competing/duplicate animation was introduced; `spin` remains scoped to the scan-refresh icon (line 236) only.

**2. Font-scale fragmentation — RESOLVED.**
- Lines 76-77 introduce `FONT = { xs: '0.72em', sm: '0.78em', md: '0.88em', lg: '1.8em' }` and `WEIGHT = { medium: 600, bold: 700 }`.
- Grepped every `em` literal in the file: only `0.72em`, `0.78em`, `0.88em`, `1.8em` remain as font sizes (four, matching the guideline exactly). The two other `em` hits in the file — `0.03em` and `0.12em` — are `letterSpacing` tracking values, not font sizes, and are out of scope for this pillar.
- Grepped every `fontWeight:` usage: only `WEIGHT.bold` and `WEIGHT.medium` appear (two, matching the guideline). No stray numeric weight (600/700/800/900) literals remain anywhere in the file.
- Every previously-flagged call site — `StatusBadge`, header GRC label, h1 title, subtitle, scan/re-evaluate buttons, scan-message, both error banners + Retry buttons, search input, score cards + framework name + evaluating label, panel header (framework name, control count, filter tabs), group headers + control count + failing pill, and per-control id/title/description/evidence/badge — now references `FONT.*`/`WEIGHT.*` exclusively. No un-migrated literal em/weight values found.
- One deliberate, disclosed exception: the SVG score-ring's `fontSize={13}` (line 89, px not em) is untouched, correctly left alone since it's dimensioned to the fixed 70px ring geometry rather than the page type scale — its `fontWeight` was migrated to `WEIGHT.bold` as claimed.
- Cosmetic side-effect (disclosed, not a regression): h1 title and framework-card names moved from weight 900/800 down to 700 (`WEIGHT.bold`), producing visibly lighter headings. This is an intentional, reasonable design simplification that comes packaged with the consolidation — not a defect. No layout shift, truncation, or contrast issue results from it.

**No new issues surfaced during this pass.** Reviewed the full diff area (StatusBadge, header, both error banners, search, score cards, detail panel, grouped controls) for regressions in state handling, color, spacing, and copy — all untouched and intact. `SEMANTIC`/`semanticBg` color system from the prior fix remains fully intact and unaffected by this commit.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Unchanged — dynamic subtitle, search/empty-state, and error-banner copy remain specific and non-generic |
| 2. Visuals | 4/4 | **RESOLVED THIS ROUND** — score-ring placeholder now pulses via a dedicated `pulse` keyframe, clearly signaling "loading" instead of reading as static/broken |
| 3. Color | 4/4 | Unchanged from last audit — `SEMANTIC`/`semanticBg()` remains the single source of truth for accent/status colors, no regression |
| 4. Typography | 4/4 | **RESOLVED THIS ROUND** — exactly 4 font sizes (`0.72em/0.78em/0.88em/1.8em`) and 2 weights (`600/700`) confirmed via grep across the whole file; only exception is the ring's geometry-bound `13px` label, correctly out of scope |
| 5. Spacing | 3/4 | Unchanged — consistent 4px-multiple spacing values, but still 100% inline `style={{}}` with no shared spacing tokens (not in scope for this fix) |
| 6. Experience Design | 4/4 | Unchanged — fetch-failure error banners with Retry, loading/empty-state gating, and `AbortError` guards all remain intact; no regression from this commit |

**Overall: 23/24** (prior: 21/24, 20/24, 19/24, 17/24, original: 15/24)

---

## Final Assessment — Phase 19 Fix Sequence (15/24 → 23/24)

Phase 19 went through five fix rounds, each verified by a fresh adversarial re-audit rather than trusted on the implementer's word:

1. **15/24 → 17/24**: BLOCKER (unreachable frameworks due to hardcoded/mismatched IDs) fixed by deriving the framework list from the backend registry — but this fix introduced a visual regression (non-responsive grid, no search).
2. **17/24 → 19/24**: Grid/search regression fixed with a responsive `auto-fill` grid and a search input — but exposed that fetch failures had no visible error state (silent failure).
3. **19/24 → 20/24**: Error-state gap closed with `summaryError`/`detailError` banners + Retry affordance, scoped correctly with `AbortError` guards.
4. **20/24 → 21/24**: Nine hand-duplicated semantic color literals consolidated into a single `SEMANTIC`/`semanticBg()` source of truth, verified with zero stray literals remaining.
5. **21/24 → 23/24 (this round)**: The last two lingering polish items — a static (non-shimmering) loading placeholder and a fragmented 9-size/4-weight type scale — were both fixed in one commit and both verified resolved with no regressions.

The one remaining deduction (Spacing, 3/4) is a low-severity, disclosed-as-out-of-scope item: the component is 100% inline styles with no shared `SPACING` token object (unlike the now-established `SEMANTIC`/`FONT`/`WEIGHT` patterns). Values are consistently 4px-multiples, so this is a maintainability/consistency nit rather than a user-facing defect — reasonable to leave as a backlog item rather than a blocking fix.

**Verdict: Phase 19 is now shippable.** All four originally-identified defects (unreachable frameworks, layout regression, silent fetch failures, color duplication) plus both follow-on polish items (loading affordance, type-scale sprawl) are confirmed resolved through direct code inspection across five independent audit passes, with no BLOCKER or unresolved WARNING remaining except the minor, non-blocking spacing-token gap.

---

## Top Remaining Recommendation (non-blocking)

1. **No shared spacing token constant** — Low user impact (spacing is already consistent on a 4px scale) but a maintainability gap: extract `SPACING = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 }` (mirroring the `SEMANTIC`/`FONT` pattern) and route padding/margin/gap through it, to prevent the same fragmentation that previously happened to font sizes.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- Unchanged from prior audits — header subtitle, search placeholder, empty-state copy, and both error-banner messages remain accurate, specific, and distinct per failure surface.

### Pillar 2: Visuals (4/4)
- **Resolved this round.** Line 221 adds `@keyframes pulse`; line 306 applies `animation: 'pulse 1.5s ease-in-out infinite'` to the un-loaded score-ring placeholder, replacing the previously-flagged static grey circle. Grid, search, and error banners from prior fixes remain intact and unaffected.

### Pillar 3: Color (4/4)
- Unchanged — `SEMANTIC` (lines 61-66) + `semanticBg()` (70-72) remain the single declaration site for accent/pass/partial/fail colors; this commit touches no color literal.

### Pillar 4: Typography (4/4)
- **Resolved this round.** `FONT = { xs: '0.72em', sm: '0.78em', md: '0.88em', lg: '1.8em' }` and `WEIGHT = { medium: 600, bold: 700 }` (lines 76-77) are now referenced by every text element in the file. Grep confirms exactly 4 distinct font-size em values and 2 distinct fontWeight values file-wide (excluding the two `letterSpacing` tracking values `0.03em`/`0.12em`, which are not font sizes, and the SVG ring's geometry-bound `fontSize={13}` px value, disclosed and out of scope).
- Minor disclosed side-effect: h1 and framework-card names now render at weight 700 instead of 900/800 — a lighter, intentional heading treatment, not a defect.

### Pillar 5: Spacing (3/4)
- Untouched by this fix and not in scope for it. Spacing values remain consistent 4px multiples; component remains 100% inline styles with no shared spacing tokens (see recommendation above).

### Pillar 6: Experience Design (4/4)
- Unchanged and unaffected by this commit: `summaryError`/`detailError` banners with Retry, proper loading/empty-state gating, and `AbortError` guards all remain intact and correctly scoped.

---

## Files Audited
- `components/ComplianceFrameworksDashboard.tsx` (full file, 405 lines, post-shimmer/type-scale fix, commit `7b1f1de`)
- `.planning/phases/19-compliance-frameworks/19-UI-REVIEW.md` (prior audit, used as comparison baseline — content superseded by this file)
- `.planning/phases/19-compliance-frameworks/19-01-SUMMARY.md`
- `.planning/phases/19-compliance-frameworks/19-01-PLAN.md`
- `git log`/`git show 7b1f1de` (commit diff verification)

No `src/` frontend files were relevant (frontend tree lives at repo root under `components/`). No `components.json`/shadcn registry present — registry safety audit skipped. No dev server was running on :3000/:5173/:8080, so this remains a code-only audit; both fix claims were verified via direct grep across the whole file plus line-by-line inspection of every flagged call site, not observed screenshots.
