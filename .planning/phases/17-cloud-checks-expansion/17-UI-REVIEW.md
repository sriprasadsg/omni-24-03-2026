# Phase 17 — UI Review

**Audited:** 2026-07-06
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server running on :3000, :5173, or :8080)

**Scope note:** Phase 17's plan/summary describe a backend-only change (`backend/cloud_checks_aws.py`, `cloud_checks_azure.py`, `cloud_checks_gcp.py`, `cloud_checks_k8s.py`, `cloud_checks_service.py` — expanding CLOUD_CHECKS from 67 to 300+). No frontend files were listed as modified in `17-01-SUMMARY.md`. The only frontend surface that renders this data is `components/CloudChecksScanner.tsx` (consumes `GET /api/cloud-checks`, `/results`, `/summary`). This audit evaluates that consumer component against abstract 6-pillar standards, since it is the sole UI affected by the expanded check library (300+ checks now flow through its Check Library and Results tables/filters).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Empty state copy is specific and actionable; no user-facing error copy exists anywhere in the component |
| 2. Visuals | 2/4 | Icon-only refresh button has no aria-label/tooltip; otherwise good hierarchy via stat cards and badges |
| 3. Color | 4/4 | Accent (`primary-*`) restrained to 4 usages; severity colors are semantic and consistent, no hardcoded hex/rgb |
| 4. Typography | 2/4 | 5 distinct font sizes and 4 distinct weights in one component, exceeding the >4 size / >2 weight flag threshold |
| 5. Spacing | 4/4 | All spacing uses standard Tailwind scale (p-2/3/4, gap-1/2/3/4); zero arbitrary bracket values |
| 6. Experience Design | 2/4 | Loading and empty states present; fetch failures are silently swallowed with no error state or message |

**Overall: 17/24**

---

## Top 3 Priority Fixes

1. **Silent fetch failures** (`components/CloudChecksScanner.tsx:64-90`) — When `GET /api/cloud-checks`, `/results`, `/summary`, or `/cloud-accounts` fail (network error, 401, 500), the `try/finally` blocks have no `catch`, so the promise rejection is unhandled and the user sees a blank or stale screen with zero explanation, with 300+ checks now depending on 4 separate endpoints resolving successfully. Add a `catch` that sets an `error` state and render an inline banner (e.g. "Couldn't load cloud checks — retry") above the tab bar.
2. **Icon-only button with no accessible name** (`components/CloudChecksScanner.tsx:126-128`) — The `RefreshCw` refresh button has no `aria-label`, `title`, or visible text, so screen reader users cannot determine its purpose. Add `aria-label="Refresh cloud checks"`.
3. **Typography sprawl** (`components/CloudChecksScanner.tsx:112-269`) — 5 distinct font sizes (`text-xs`, `text-sm`, `text-xl`, `text-2xl`, `text-3xl`) and 4 distinct weights (`font-normal`, `font-medium`, `font-semibold`, `font-bold`) are in play in a single component, more than the abstract-standard thresholds of 4 sizes / 2 weights. Consolidate: use `text-3xl font-bold` for all stat-card numbers (currently split between `text-3xl`/`text-2xl`) and drop `font-normal`/`font-semibold` in favor of `font-medium`/`font-bold` only.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Empty state at line 198 is specific and instructional: `'Select a cloud account and click "Run Checks" to evaluate your cloud security posture.'` — good, avoids generic "No data" pattern.
- Secondary empty state ("No results match your filters.") is also clear.
- No `grep` hits for generic labels (`Submit`, `Click Here`, `OK`) — button copy is task-specific ("Run Checks", "Running…").
- **Gap:** No error copy exists in the file at all — `grep -n "went wrong\|try again\|error occurred"` returns nothing. If the phase's 300+ new checks cause a slower or failing `/api/cloud-checks` response, there is no user-facing message to explain it.

### Pillar 2: Visuals (2/4)
- Clear focal point: pass-rate stat card is visually first and largest (`text-3xl font-bold`, line 136).
- Good hierarchy: stat cards → tab bar → filter row → table, consistent card treatment (`rounded-xl border p-4`).
- **Defect:** `RefreshCw` icon button (line 126-128) has no `aria-label` or `title` — the only icon-only, unlabeled interactive element in the component. The `Play`/"Run Checks" button by contrast pairs icon + text correctly.
- Severity badges (`SEV_COLORS`, lines 37-43) provide clear differentiation across 5 severity levels using both color and text — good.

### Pillar 3: Color (4/4)
- `text-primary`/`bg-primary`/`border-primary` (as `primary-*` variants) used exactly 4 times: heading icon, active tab underline/text, and the primary action button — correctly scoped to the single most important CTA and current-state indicator, consistent with 60/30/10 accent restraint.
- No hardcoded hex or `rgb()` values (`grep` returns empty) — all color via Tailwind semantic classes.
- Severity color map (lines 37-43) is applied consistently across both the Results and Check Library tabs — no divergence in how `critical`/`high`/etc. render between views.

### Pillar 4: Typography (2/4)
- Font sizes in use: `text-xs`, `text-sm`, `text-xl`, `text-2xl`, `text-3xl` — 5 distinct sizes, one over the abstract 4-size guideline.
- Font weights in use: `font-normal`, `font-medium`, `font-semibold`, `font-bold` — 4 distinct weights, double the 2-weight guideline.
- Specific overlap issue: stat-card numbers split between `text-3xl` (Pass Rate, line 136) and `text-2xl` (per-provider %, line 147; Critical Fails, line 154) with no visual justification for the size difference — these are peers in the same stat-card row and should share one size.

### Pillar 5: Spacing (4/4)
- All spacing values found (`p-2`, `p-4`, `px-3/4`, `py-0/1/2/3`, `gap-1/2/3/4`, `space-y-6`) are standard Tailwind scale values — no arbitrary bracket values (`grep "\[.*px\]\|\[.*rem\]"` returns empty).
- Consistent card padding (`p-4`) and table cell padding (`px-4 py-3`) applied uniformly across both tabs.

### Pillar 6: Experience Design (2/4)
- Loading state: present and clear (spinner, line 194).
- Empty states: present and specific (lines 197-199) for both "no results yet" and "no results match filters" cases.
- **Gap — Error state:** `fetchAll` (lines 64-80) and `runChecks` (lines 84-90) both use `try { ... } finally { ... }` with no `catch`. Any rejected fetch or non-JSON response throws unhandled and leaves `loading`/`running` cleared with no indication to the user that the operation failed — this is a genuine break in task completion, not just cosmetic.
- **Gap — Disabled/confirmation states:** "Run Checks" correctly disables while `running`, but there's no confirmation before running potentially long/costly checks against a live cloud account, and no per-row loading indicator if multiple accounts could run concurrently (single global `running` flag).
- No destructive actions exist in this component, so confirmation-dialog absence isn't a blocker.

---

## Files Audited
- `components/CloudChecksScanner.tsx` (frontend consumer of Phase 17's expanded check library)
- `.planning/phases/17-cloud-checks-expansion/17-01-SUMMARY.md`
- `.planning/phases/17-cloud-checks-expansion/17-01-PLAN.md`

**Registry audit:** `components.json` not found — shadcn not initialized in this project. Registry safety audit skipped.

**Backend files** (`backend/cloud_checks_*.py`) were reviewed for context only; they are non-UI Python modules and out of scope for this visual audit.
