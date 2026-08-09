# Phase 06 — UI Review

**Audited:** 2026-07-06
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server detected on :3000 or :5173 — code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Toast and HTTP error copy are specific and actionable; no generic labels found |
| 2. Visuals | 3/4 | Icon-only Mark Compliant/Non-Compliant buttons have aria-label+title, but give only a subtle opacity change as feedback, no distinct "active/updating" visual state |
| 3. Color | 4/4 | Green/red/blue used semantically (compliant/non-compliant/automated); no hardcoded hex/rgb in touched files |
| 4. Typography | 3/4 | 4 distinct font sizes (xs/sm/lg/xl) and 3 weights (medium/semibold/bold) in the touched files — weight count exceeds the 2-weight abstract guideline |
| 5. Spacing | 3/4 | Consistent px-1.5/py-0.5 badge scale, but one pre-existing arbitrary value `min-w-[150px]` remains in FrameworkDetail.tsx (same file this phase edited) |
| 6. Experience Design | 3/4 | Per-row disabled/loading map (`updatingMap`) and try/catch+toast on failure are solid, but there's no `aria-busy`/spinner/visible loading indicator during the PATCH, only `disabled:opacity-40` |

**Overall: 20/24**

---

## Top 3 Priority Fixes

1. **No visible loading indicator on status-override buttons** — `components/AssetComplianceList.tsx:264-265` — user impact: during the async PATCH round-trip a user has no positive confirmation the click registered beyond a faint opacity drop; on a slow network they may click again or assume the app is frozen — concrete fix: swap the `CheckIcon`/`XIcon` for a small spinner (or add `aria-busy={!!updatingMap[asset.id]}`) while `updatingMap[asset.id]` is true.
2. **Font-weight sprawl (3 weights: medium/semibold/bold) in touched component tree** — `components/AssetComplianceList.tsx` (lines 123, 145, 149, 238, 243, etc.) — user impact: inconsistent visual weight across badges/headers/labels weakens hierarchy signaling for what's actually important (status vs. metadata) — concrete fix: standardize on `font-medium` for body/labels and `font-semibold` for headers only; drop `font-bold` usage in this component.
3. **Stray arbitrary spacing value left in an edited file** — `components/FrameworkDetail.tsx:235` (`min-w-[150px]`) — user impact: none directly visible, but it's technical debt in a file this phase touched and signals the spacing scale isn't being enforced as changes land — concrete fix: replace with a Tailwind scale class (e.g. `min-w-[9.375rem]` → `min-w-40` or nearest scale token) during the next pass through this file.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- `components/FrameworkDetail.tsx:387` — `showToast('Failed to update compliance status — please try again', 'error')` is specific, tells the user what failed and what to do next.
- `backend/compliance_status_endpoints.py:52,61,67` — HTTP error details are specific: "Insufficient permissions to override compliance status", "Asset not found", "Asset not found in your tenant" — no generic "Error" or "Something went wrong" strings.
- Button titles/aria-labels are task-specific: "Mark Compliant" / "Mark Non-Compliant" (`AssetComplianceList.tsx:264-265`), not generic "Submit"/"OK".
- No occurrences of `Submit|Click Here|Cancel` (grepped, none found) or generic empty/error placeholder patterns in the touched files.

### Pillar 2: Visuals (3/4)
- Icon-only buttons for Mark Compliant/Non-Compliant, Delete evidence, Upload/Ingest all carry both `title` and `aria-label` (`AssetComplianceList.tsx:209-210, 264-265, 269-270`) — accessibility pass.
- Visual hierarchy exists via color-coded badges (green=Compliant, red=Non-Compliant, blue=Automated) and size differentiation (`text-xl` control header vs `text-xs` metadata badges).
- Gap: the only feedback for an in-flight status update is `disabled:opacity-40` on the button itself (`AssetComplianceList.tsx:264-265`) — no spinner, no row-level "saving…" indicator, no toast-on-start. A user clicking on a slow connection gets weak affordance that the action is processing.

### Pillar 3: Color (4/4)
- Color usage is semantically anchored, not decorative: green (compliant/automated-positive), red (non-compliant/error), blue (automated source badge) — this is a reasonable domain-driven use of a 3-hue accent set rather than a single-brand-color overuse pattern.
- No hardcoded hex or `rgb()` values found in `AssetComplianceList.tsx` or `FrameworkDetail.tsx` (grepped, zero matches) — all color via Tailwind semantic utility classes.
- The WCAG fix itself (`text-[10px]` → `text-xs`, `AssetComplianceList.tsx:195,197`) was correctly and completely applied — verified zero remaining `text-[10px]` instances.

### Pillar 4: Typography (3/4)
- Font sizes in use across the two touched files: `text-xs`, `text-sm`, `text-lg`, `text-xl` — 4 distinct sizes, at the edge of the abstract 4-size guideline (acceptable but no headroom).
- Font weights in use: `font-medium`, `font-semibold`, `font-bold` — 3 distinct weights, exceeding the abstract 2-weight guideline (`AssetComplianceList.tsx:123,145,149,195,197,200,238,243,249,254,260,316,337`). `font-bold` appears only twice (lines 149, 238, 243) and could likely collapse into `font-semibold` without loss of hierarchy.

### Pillar 5: Spacing (3/4)
- Badge padding is consistent: `px-1.5 py-0.5` reused across every badge in `AssetComplianceList.tsx` (lines 128-133, 145, 195, 197) — good internal consistency.
- One arbitrary spacing value remains: `min-w-[150px]` at `FrameworkDetail.tsx:235`, inside a file this phase directly modified. Not part of the phase's stated diff but present in the surrounding code the plan touched — flagged since arbitrary-value spacing is an explicit anti-pattern this same phase's plan (06-02) called out and fixed elsewhere (`text-[10px]` → `text-xs`) but didn't fully sweep.
- No other arbitrary `[…px]`/`[…rem]` spacing found in either touched file.

### Pillar 6: Experience Design (3/4)
- Loading/in-flight state: `updatingMap` per-asset boolean disables the button during the PATCH (`AssetComplianceList.tsx:47-53`), preventing double-submit — good defensive UX.
- Error handling: try/catch around the async PATCH with a specific toast message and `console.error` for diagnostics (`FrameworkDetail.tsx:381-388`).
- Backend hardening beyond the original plan scope: atomic `find_one_and_update` (TOCTOU fix, WR-03) and a dedicated `_WRITE_ROLES` guard so read-only roles get 403 (`compliance_status_endpoints.py:47-52,76-89`) — strong defense-in-depth for a status-mutation endpoint.
- Gap: no destructive-action confirmation before overriding a compliance status (arguably acceptable since it's reversible and audit-tracked via `status_history`), but also no `aria-busy` or spinner during the async call — screen reader users get no announcement that a mutation is in progress.
- Cache invalidation on write (`invalidate_cache(...)` x4, lines 110-113) ensures compliance-score views don't show stale data after an override — good end-to-end state consistency.

---

## Files Audited
- `backend/compliance_status_endpoints.py`
- `backend/router_registry.py` (reference only, no UI surface)
- `backend/tests/test_compliance_status.py` (reference only, no UI surface)
- `services/apiService.ts` (reference only, no UI surface)
- `components/FrameworkDetail.tsx`
- `components/AssetComplianceList.tsx`
