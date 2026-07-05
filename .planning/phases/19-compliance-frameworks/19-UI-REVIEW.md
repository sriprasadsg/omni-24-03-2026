# Phase 19 — UI Review (Re-audit)

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured (no dev server running on :3000/:5173/:8080; code-only audit)
**Prior audit:** 15/24, BLOCKER on Pillar 6 (frameworks unreachable due to hardcoded 6-ID allowlist + ID mismatch vs backend `_REGISTRY`)

---

## BLOCKER Resolution Status: RESOLVED

The fix (commit `e6ccf90`) replaced the hardcoded `FRAMEWORK_IDS`/`FRAMEWORK_COLORS` allowlist with `const frameworkIds = Object.keys(summary).sort()` (line 144), where `summary` is populated directly from `GET /api/frameworks/summary`. Verified against `backend/compliance_frameworks_endpoints.py:28-73`: `_REGISTRY` now contains 44 entries total (30 original + 14 added by Phase 19), and the `/summary` endpoint iterates this full registry. Since the frontend no longer filters by a static ID list, all 44 frameworks — including the 14 shipped by this phase and the previously-inaccessible pre-existing ones — are now reachable, selectable, and viewable. The ID-mismatch problem (`nist_csf` vs `nistcsf`, etc.) is moot because the component no longer references any hardcoded IDs at all; it consumes whatever keys the backend actually returns, so drift between frontend and backend naming is now structurally impossible for this list.

`colorForFramework()` (lines 52-56) replaces the old 6-entry `FRAMEWORK_COLORS` map with a deterministic hash into a 12-color palette, so all 44 frameworks get a distinct-looking (cycling) accent instead of collapsing to one default indigo.

`selected` now defaults to `frameworkIds[0]` once loaded (lines 151-153), and `fetchDetail` guards against an empty id (line 113: `if (!fid) return;`), fixing the fetch-on-mount race that existed when `selected` started as `''`.

A loading placeholder (`Loading frameworks…`, line 209) covers the initial fetch window before `frameworkIds` is populated.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Subtitle now dynamically reports the live framework count instead of a stale hardcoded list — the copy accuracy issue from the prior audit is fully resolved |
| 2. Visuals | 2/4 | Fixed 3-column grid with no responsive/scroll handling will render ~44 cards in a tall, undifferentiated block with no search/filter/grouping affordance — a new visual-scale problem introduced by fixing the data problem |
| 3. Color | 3/4 | Deterministic 12-color hash palette is a real improvement over the old 6-entry static map, but 12+ other hardcoded hex values remain with no shared token source, and hash collisions mean visually adjacent cards can share identical colors |
| 4. Typography | 3/4 | Unchanged from prior audit: 8 distinct em-based sizes and 4 weights in one file, exceeding the ≤4 sizes / ≤2 weights guideline |
| 5. Spacing | 2/4 | Grid is still fixed at `repeat(3, 1fr)` with no breakpoint/wrap handling; this is now a materially worse problem than at 6 cards since ~44 cards will produce a very long, un-paginated scroll with no responsive collapse on narrow viewports |
| 6. Experience Design | 3/4 | BLOCKER resolved — all frameworks are now reachable and selectable; loading state added; but the fetch-error gap (silent console.error on summary/detail failures) and lack of empty/no-data messaging from the prior audit remain unfixed |

**Overall: 17/24** (prior: 15/24)

---

## Top 3 Priority Fixes

1. **No responsive/overflow handling for ~44 framework cards in a fixed 3-column grid** (`components/ComplianceFrameworksDashboard.tsx:211`, `gridTemplateColumns: 'repeat(3, 1fr)'`) — User impact: on narrow/tablet viewports the grid will overflow or cramp, and even on desktop, scrolling through ~15 rows of cards with no search, filter, or grouping (by category, compliance domain, or score) makes finding a specific framework tedious. Concrete fix: add a `minmax`/`auto-fill` grid (`repeat(auto-fill, minmax(280px, 1fr))`) and a simple text filter/search input above the grid.

2. **No user-facing error state on fetch failure** (lines 107, 119 — `console.error` only, no state update) — User impact: if `/api/frameworks/summary` or `/api/frameworks/{id}` fails, the user sees a stale or perpetually-loading UI with zero indication anything went wrong, this is unchanged from the prior audit and is now more consequential since 44 frameworks depend on that single summary call. Concrete fix: add an `error` state variable set in each `catch` block, rendered as a visible inline banner reusing the existing `scanMessage` failure-styling pattern (line 200).

3. **12+ hardcoded hex values remain with no shared token source** (`components/ComplianceFrameworksDashboard.tsx` — `StatusBadge` cfg object lines 74-79, plus scattered inline colors like `#94a3b8`, `#a5b4fc`, `#6ee7b7`) — User impact: color drift risk persists (e.g., "success" is `#6ee7b7` in `StatusBadge` but a different green in the new hash palette), and this component remains an outlier from any app-wide theme convention. Concrete fix: extract a shared `COLORS` constant (or CSS custom properties) reused across `StatusBadge`, `ScoreRing`, and the header, so semantic colors (pass/fail/partial) aren't redefined ad hoc.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- Header subtitle (line 181) is now fully dynamic: `Automated control evaluation across {frameworkIds.length} configured compliance framework(s)` — correctly pluralizes and reflects the live count rather than a hardcoded, stale 6-framework list. This directly resolves the prior audit's Finding #1 (misrepresentation risk for a compliance-facing product).
- Button labels (`Scan All Agents`, `Re-evaluate`, `Dispatching…`) remain specific and action-oriented.
- Status badges (`Pass`, `Partial`, `Fail`, `N/A`) remain concise and unambiguous.
- Scan failure message (`"Failed to dispatch scan. Check backend connection."`) is still reasonably actionable but generic — minor, unchanged from prior audit, not scored down given the pillar's other strong points.

### Pillar 2: Visuals (2/4)
- Score-ring cards plus expandable grouped control table below remains a reasonable two-level hierarchy in principle.
- Icon-only elements remain always paired with text labels — no bare icon-only affordances.
- **New finding, downgraded from prior 3/4:** now that the BLOCKER is fixed and the dashboard actually renders every framework in `_REGISTRY` (44, versus the 6 previously visible), the fixed `repeat(3, 1fr)` grid (line 211) will produce a long, undifferentiated wall of ~15 rows of cards with no visual grouping (e.g., by domain: security, privacy, financial, government), no search, and no collapse/expand-by-category. What was previously a moot problem (only 6 cards, never noticed) is now a real, user-facing scale problem introduced as a direct consequence of the correct fix.
- Loading placeholder for un-loaded score rings remains a plain grey circle with no skeleton shimmer.

### Pillar 3: Color (3/4)
- **Improvement:** `colorForFramework()` (lines 52-56) replaces the old static 6-entry map with a hash function over a 12-color palette (`FRAMEWORK_COLOR_PALETTE`, lines 47-50), giving every one of the 44 frameworks a defined accent instead of falling back to a single default indigo. This is a genuine, verified fix to the prior audit's Pillar 3 concern about palette exhaustion.
- **Remaining gap:** with 44 frameworks hashed into only 12 colors, color collisions are guaranteed (by pigeonhole, at least 4 frameworks will share each color) — some differentiation value is lost at this frameworks count, though this is a reasonable and pragmatic tradeoff versus 44 unique hand-picked colors.
- 12+ other hardcoded hex values remain scattered throughout the file (`StatusBadge` cfg, header accent `#6366f1`, various `rgba(255,255,255,...)` overlays) with no CSS custom properties or theme tokens — unchanged maintenance/drift risk from the prior audit (e.g., `StatusBadge`'s pass color `#6ee7b7` is a different green than any palette entry).

### Pillar 4: Typography (3/4)
- Unchanged from prior audit: 8 distinct font sizes (`0.72em, 0.75em, 0.78em, 0.82em, 0.85em, 0.88em, 0.95em, 1.8em`) and 4 weights (`600, 700, 800, 900`) in a single file, exceeding the ≤4 sizes / ≤2 weights abstract guideline.
- No regression or improvement introduced by the fix — this pillar was untouched by the change.

### Pillar 5: Spacing (2/4)
- Base spacing values (28px 32px, 20px 24px, 12px 24px, 4-16px gaps) remain consistent 4px multiples — no arbitrary/broken values.
- **Downgraded from prior 3/4:** the fixed 3-column grid (line 211, `gridTemplateColumns: 'repeat(3, 1fr)'`) with no `@media` query, `minmax`, or `auto-fill` pattern was a latent issue at 6 cards but is now materially worse — rendering ~44 cards produces roughly 15 rows with no pagination, virtualization, or responsive column collapse. On narrow viewports (documented gap, still unaddressed) cards will overflow or cramp; on any viewport, the sheer vertical length degrades scannability without a search/filter affordance.
- Component remains 100% inline `style={{}}` objects with no Tailwind/shared spacing tokens, unchanged from prior audit.

### Pillar 6: Experience Design (3/4)
- **BLOCKER RESOLVED:** `frameworkIds = Object.keys(summary).sort()` (line 144) replaces the hardcoded `FRAMEWORK_IDS` allowlist. Verified against `backend/compliance_frameworks_endpoints.py:28-73` (44-entry `_REGISTRY`) that the `/summary` endpoint's response keys map 1:1 to registry entries with no naming mismatch possible, since the frontend no longer hardcodes any IDs to compare against. All 44 frameworks (including the 14 shipped by Phase 19: ENS, MAS TRM, IRAP, ISO 27017/27018, BSI C5, FFIEC, OWASP Top 10, TISAX, AWS Well-Architected, RBI CSF, TIC 3.0, KISA ISMS, FedRAMP High) are now selectable and viewable through the UI.
- **Improvement:** `selected` now defaults to the first loaded framework (`frameworkIds[0]`, lines 151-153) rather than starting empty, and `fetchDetail` guards against an empty `fid` (line 113), removing a previously-latent fetch race.
- **Improvement:** explicit loading state added for the initial framework list (`Loading frameworks…`, line 209), improving on the prior audit's "plain grey circle only" finding for the empty-summary case.
- **Unresolved from prior audit:** `fetchSummary`/`fetchDetail` catch blocks (lines 107, 119) still only `console.error` with no state update or user-visible feedback — if the summary or detail fetch fails, the user sees a stale or stuck-loading UI with no indication of failure. Only the manually-triggered scan action has user-facing error messaging (line 138).
- **Unresolved from prior audit:** no explicit empty-state messaging if `summary` legitimately returns `{}` (distinct from "still loading") — though this is now a narrower edge case than before, since a non-empty `_REGISTRY` should always populate at least one card once the fetch succeeds.
- Role-gating for `Scan All Agents` vs `Re-evaluate` (lines 90, 184-198) remains a reasonable, well-implemented permission-aware pattern.

---

## Files Audited
- `components/ComplianceFrameworksDashboard.tsx` (full file, 309 lines, post-fix version)
- `backend/compliance_frameworks_endpoints.py` (lines 28-73 — verified 44-entry `_REGISTRY`, confirming no ID mismatch is structurally possible with the new dynamic-key approach)
- `.planning/phases/19-compliance-frameworks/19-01-SUMMARY.md`
- `.planning/phases/19-compliance-frameworks/19-01-PLAN.md`
- `.planning/phases/19-compliance-frameworks/19-UI-REVIEW.md` (prior audit, used as comparison baseline)

No `src/` frontend files were relevant (frontend tree lives at repo root under `components/`). No `components.json`/shadcn registry present — registry safety audit skipped. No dev server was running on :3000/:5173/:8080, so this remains a code-only audit; visual claims about grid density/overflow are inferred from the grid CSS and framework count, not observed screenshots.
