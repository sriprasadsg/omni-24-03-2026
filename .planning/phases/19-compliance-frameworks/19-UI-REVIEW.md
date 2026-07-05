# Phase 19 — UI Review

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** Not captured (no dev server running on :3000/:5173/:8080; code-only audit)

**Scope note:** Phase 19 (`19-01-PLAN.md`) is a backend-only plan — it shipped 14 Python framework modules (`backend/frameworks/*.py`) and a schema/contract test suite. It declares no frontend deliverable of its own, but its `affects:` field names `compliance-score-dashboard`, and the plan's stated purpose ("reach feature parity with Probo and Comp AI") is a user-facing claim. This audit therefore evaluates the actual consumer of this backend work: `components/ComplianceFrameworksDashboard.tsx`, wired into `App.tsx` at the `complianceFrameworks` route (confirmed lines 181, 1791).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Labels are clear and specific, but the hardcoded subtitle lists only 6 legacy frameworks, actively misrepresenting what the platform now supports |
| 2. Visuals | 3/4 | Clean hierarchy (score rings, grouped controls) but zero visual differentiation exists for any of the 14 new frameworks because they are absent |
| 3. Color | 2/4 | 12+ hardcoded hex values with no shared token/theme source; accent color reused inconsistently across per-framework "brand" colors |
| 4. Typography | 3/4 | 8 distinct `em`-based font sizes and 4 weights in one file — exceeds the ≤4 sizes / ≤2 weights guideline, though visually restrained |
| 5. Spacing | 3/4 | Consistent inline spacing scale (multiples of 4), no arbitrary/broken values, but 100% inline styles with no shared spacing tokens |
| 6. Experience Design | 1/4 | **BLOCKER:** the dashboard's `FRAMEWORK_IDS` list is hardcoded to 6 legacy frameworks; all 14 frameworks delivered by Phase 19 (and 37 total beyond the original 6) are completely inaccessible in the UI — no way to select, view, or evaluate them |

**Overall: 15/24**

---

## Top 3 Priority Fixes

1. **Phase 19's entire deliverable is invisible to users** — User impact: none of the 14 new frameworks (FedRAMP High, ISO 27017/27018, OWASP Top 10, BSI C5, TISAX, MAS TRM, FFIEC, ENS, IRAP, RBI CSF, KISA ISMS, TIC 3.0, AWS Well-Architected) can be selected, viewed, or scanned — the backend work is fully dead weight from a user's perspective. Concrete fix: replace the hardcoded `FRAMEWORK_IDS` array in `components/ComplianceFrameworksDashboard.tsx:47` with a dynamic fetch from `GET /api/frameworks/summary` (which the component already calls) and render every key present in the response, rather than filtering to a fixed allowlist of 6.

2. **Framework ID mismatch between frontend allowlist and backend registry** — User impact: even the intended 6 "legacy" frameworks reference IDs (`nist_csf`, `iso27001_2022`) that don't match the backend `_REGISTRY` keys (`nistcsf`, `iso27001` — see `backend/compliance_frameworks_endpoints.py:29-31`), meaning some of the original 6 cards may silently render as empty/placeholder rings rather than real data. Concrete fix: audit `FRAMEWORK_IDS` and `FRAMEWORK_COLORS` against the actual `_REGISTRY` keys and correct the mismatches, then remove the hardcoded list per fix #1.

3. **No user-facing error state on fetch failure** — User impact: if `/api/frameworks/summary` or `/api/frameworks/{id}` fails (network error, 500, auth expiry), the component only does `console.error(...)` (lines 106, 117) and silently leaves `summary`/`detail` in their prior state — the user sees stale or empty data with zero indication anything went wrong. Concrete fix: add an `error` state variable, set it in the `catch` blocks, and render a visible inline banner (matching the existing `scanMessage` failure-styling pattern already used for scan-dispatch failures at line 191-195).

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Button labels (`Scan All Agents`, `Re-evaluate`, `Dispatching…`) are specific and action-oriented — no generic "Submit"/"OK"/"Click Here" patterns found.
- Status badges (`Pass`, `Partial`, `Fail`, `N/A`) are concise and unambiguous (`components/ComplianceFrameworksDashboard.tsx:73-79`).
- **Finding:** The header subtitle at line 173 hardcodes: `"Automated control evaluation — NIST CSF · CIS v8 · ISO 27001 · HIPAA · PCI-DSS · SOC 2"`. After Phase 19 (and the 37 total frameworks now in the backend registry), this copy is factually stale and undersells/misrepresents the product to users and auditors — a compliance-facing product describing its own coverage inaccurately is a real credibility risk, not just cosmetic.
- Scan failure message (`"Failed to dispatch scan. Check backend connection."`) is reasonably actionable but generic; no error code or retry guidance.

### Pillar 2: Visuals (3/4)
- Clear focal point: score-ring cards up top, expandable grouped control table below — reasonable hierarchy for a compliance dashboard.
- Icon-only elements (`ChevronDown`/`ChevronRight` toggles, `RefreshCw` scan icon) are always paired with adjacent text labels or accompany a labeled button, so no bare icon-only affordances.
- **Finding:** Visual hierarchy is undermined by the missing-frameworks issue (Pillar 6) — with only 6 of 43 possible frameworks ever rendered, the "grid" layout (`repeat(3, 1fr)`, line 200) will never show the scale the backend actually supports; there's no "show more"/pagination affordance for when the full list is wired up, which will need rework anyway.
- Loading placeholder for un-loaded score rings is a plain grey circle (line 212) with no skeleton shimmer — acceptable but minimal.

### Pillar 3: Color (2/4)
- 13 distinct hardcoded hex values in a single file (`#94a3b8` x12, `#fca5a5` x4, `#a5b4fc` x3, `#6ee7b7` x3, `#6366f1` x3, plus 7 more single-use hexes) — no CSS custom properties, theme tokens, or Tailwind classes are used anywhere; this is a 100% inline-style component.
- `FRAMEWORK_COLORS` (line 48-55) hand-assigns a unique accent color per framework — reasonable for differentiating cards, but with only 6 colors defined and no fallback strategy beyond a single default (`|| '#6366f1'`), extending to 43 frameworks (once fix #1 lands) will require either a generated palette or all frameworks collapsing to the same indigo accent, which defeats the differentiation purpose.
- No accent-color overuse in the traditional 60/30/10 sense since this is a dark, mostly-monochrome dashboard, but the total absence of a shared token source means color consistency depends entirely on developers copy-pasting hex strings correctly across files — a maintenance and drift risk already evident in the file (e.g., success uses `#6ee7b7` in `StatusBadge` but `#10b981` in `FRAMEWORK_COLORS.cis_v8` for what's conceptually the same "success" concept).

### Pillar 4: Typography (3/4)
- 8 distinct font sizes in use: `0.72em, 0.75em, 0.78em, 0.82em, 0.85em, 0.88em, 0.95em, 1.8em` — exceeds the abstract-standard guideline of ≤4 sizes.
- 4 font weights in use: `600, 700, 800, 900` — exceeds the ≤2 weight guideline, though the gradation (700/800/900 for headers, 600 for body-emphasis) is used with some intent rather than randomly.
- All sizes are relative (`em`) and scale with parent context, which is reasonable practice, but the sheer number of distinct values (8) for what is functionally a 3-level hierarchy (page title / section header / body text) suggests values were tuned ad hoc per element rather than drawn from a defined type scale.

### Pillar 5: Spacing (3/4)
- Spacing values observed (`28px 32px`, `20px 24px`, `12px 24px`, `16px 24px`, `4-16px` gaps) are consistent multiples of 4px — no arbitrary/broken fractional values found.
- No Tailwind classes exist in this file to audit via the standard grep patterns (`p-`, `px-`, etc.) since the entire component uses inline `style={{}}` objects — this itself is a finding: the component sits outside whatever design-system/Tailwind convention the rest of the app may use, making it harder to audit or enforce consistency at scale.
- Grid layout (`gridTemplateColumns: 'repeat(3, 1fr)'`, line 200) is fixed at 3 columns with no responsive breakpoint handling — on narrow viewports this will overflow or cramp; no `@media` query or clamp/minmax pattern present anywhere in the file.

### Pillar 6: Experience Design (1/4)
- **BLOCKER:** `FRAMEWORK_IDS` (line 47) is a hardcoded array of exactly 6 IDs. The component never queries which frameworks actually exist server-side beyond filtering the `/summary` response down to this allowlist. This means Phase 19's entire shipped scope — 14 new frameworks, plus the other ~23 frameworks already in `_REGISTRY` beyond the original 6 (confirmed via `backend/compliance_frameworks_endpoints.py:28-73`, 43 total entries) — is unreachable through any UI affordance. A user or auditor has no way to know these frameworks exist or to run/view an evaluation against them, despite the backend fully supporting it (per `19-01-SUMMARY.md`: "All 14 registered in `_REGISTRY` and reachable via the API").
- Loading state exists (`detailLoading` → "Running control checks…", line 231) and a scan-in-progress state exists (`isScanning` → spinning icon + "Dispatching…" text) — this part of state coverage is solid.
- Error state does not exist for the primary data-fetch path: `fetchSummary`/`fetchDetail` catch blocks only `console.error` (lines 106, 117) with no state update or user-visible feedback; only the manually-triggered scan action has a user-facing failure message (line 136).
- No empty-state handling: if `summary` returns `{}` (e.g., first load before seeding), cards render with an empty grey ring and no framework name — no explicit "no data yet" messaging distinguishing this from a slow load.
- No destructive-action confirmation needed here (no delete/destroy actions present) — not a gap.
- Role-gating for `Scan All Agents` vs `Re-evaluate` (lines 89, 176-190) is a reasonable, well-implemented permission-aware UX pattern.

---

## Files Audited
- `components/ComplianceFrameworksDashboard.tsx` (full file, 298 lines)
- `App.tsx` (lines 181, 1791 — routing/wiring confirmation)
- `backend/compliance_frameworks_endpoints.py` (lines 28-90 — `_REGISTRY` contents)
- `.planning/phases/19-compliance-frameworks/19-01-SUMMARY.md`
- `.planning/phases/19-compliance-frameworks/19-01-PLAN.md`

No `src/` frontend files were relevant (the actual frontend tree lives at repo root under `components/`, not `src/`). No `components.json`/shadcn registry present — registry safety audit skipped.
