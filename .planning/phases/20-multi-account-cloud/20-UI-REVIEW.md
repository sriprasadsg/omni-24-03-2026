# Phase 20 — UI Review

**Audited:** 2026-07-06
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md exists for this phase)
**Screenshots:** not captured (no dev server detected on :3000 or :5173)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Every error path collapses to a generic toast string ("Failed to load", "Failed", "Scan failed") with no cause or next step; "Cancel" used for form toggle |
| 2. Visuals | 2/4 | No page/section title; entire component renders at a single `text-xs` size with no size-based hierarchy between account name, status, and metadata |
| 3. Color | 3/4 | Semantic red/green/blue/gray usage is reasonable and no hardcoded hex/rgb found, but no design-system `-primary` token is used anywhere — raw Tailwind palette classes only |
| 4. Typography | 2/4 | Only one Tailwind scale size (`text-xs`) is used across the whole component, plus 3 arbitrary `text-[10px]` values that fall outside any declared scale |
| 5. Spacing | 3/4 | Consistent standard Tailwind spacing scale, no arbitrary px/rem spacing values, but uniformly cramped (`p-1`, `py-0.5`) throughout with no breathing room |
| 6. Experience Design | 2/4 | Loading state is a plain "Loading..." string (no skeleton); fetch failures show a toast only with no retry affordance; results list is silently sliced to 5 with no "view more" |

**Overall: 14/24**

---

## Top 3 Priority Fixes

1. **No visual hierarchy — single font size for everything** (`components/CloudAccountsDashboard.tsx:118-186`) — user impact: account names, statuses, and metadata are visually indistinguishable, making it hard to scan the dashboard quickly during an incident — concrete fix: bump account name to `text-sm font-semibold`, keep `text-xs` for secondary metadata, and add a `text-base font-semibold` section title ("Cloud Accounts") at the top of the component.
2. **Fetch/scan failures are dead-ends** (`components/CloudAccountsDashboard.tsx:70, 81, 93, 105` — all four catch blocks call `showToast(...)` and stop) — user impact: a toast disappears in a few seconds; if the initial `fetchData()` fails, the user is left staring at an empty dashboard with no way to retry without a full page reload — concrete fix: track an `error` state and render an inline banner with a "Retry" button when `fetchData` fails, in addition to (or instead of) the toast.
3. **Results silently truncated to 5 with no indication** (`components/CloudAccountsDashboard.tsx:172` — `.slice(0, 5)` with no count/affordance) — user impact: an account with 20 failing checks shows only 5 and gives no signal that 15 more exist, so a user could believe an environment is nearly clean when it isn't — concrete fix: render `Showing 5 of {results[a.id].length}` and a "View all" link/expand toggle when the array exceeds 5.

---

## Detailed Findings

### Pillar 1: Copywriting (2/4)
- Generic error copy repeated four times with no differentiation: `showToast('Failed to load', 'error')` (line 70), `showToast(e.message || 'Failed', 'error')` (line 81), `showToast(e.message || 'Scan failed', 'error')` (line 93), `showToast('Failed to load results', 'error')` (line 105). None tell the user why (network vs. auth vs. server) or what to do next.
- "Cancel" (line 131, conditional label on the Add Account toggle button) is a flagged generic label per UX best-practice grep patterns — acceptable for a toggle but worth a more specific label like "Close form".
- Empty state copy is a positive example: "No cloud accounts registered." (line 186) is specific and matches the pattern elsewhere in the codebase — not generic "No data".
- Register/Scan success toasts are reasonably specific (`Account registered`, `Scan complete: ${r.ran || 0} checks`).

### Pillar 2: Visuals (2/4)
- No `<h2>`/`<h3>` section title anywhere in the component (confirmed by reading the full 190-line file) and no wrapping title is supplied by the caller in `App.tsx:1700` (`case 'cloudAccounts': return <ErrorBoundary name="CloudAccountsDashboard"><CloudAccountsDashboard /></ErrorBoundary>;` — no page header passed in). A user landing on this view has no on-screen confirmation of where they are.
- Uniform `text-xs` across summary bar, account names, badges, and results (lines 118, 131, 135, 148, 156, 158, 186 — 7 of the file's ~10 text-size declarations) means there is no size-based differentiation between primary content (account name) and secondary content (metadata).
- Font weight is used minimally and correctly for the little hierarchy that exists (`font-semibold` for env group headers line 156, `font-medium` for account name line 160, summary label line 119) — this is the one hierarchy signal present, but it's undermined by everything sharing the same size.
- No icon-only buttons in this component — all buttons are text-labeled ("+ Add Account", "Scan Now", "Results", "Register", "Cancel") so no missing aria-label issue here.

### Pillar 3: Color (3/4)
- No hardcoded hex/rgb values found in the file.
- Color usage is semantic and scoped: green/red for pass/fail (lines 120-121, 174), blue for primary actions (lines 131, 144, 165), gray/neutral for secondary chrome (badges, borders, muted text) — roughly 22 total color-class occurrences in a 190-line file, not excessive for a data-dense dashboard.
- No use of `text-primary`/`bg-primary`/`border-primary` design tokens anywhere — the component bypasses the design system's semantic color layer entirely in favor of raw Tailwind palette classes (`bg-blue-600`, `text-green-600`, etc.), which means a future rebrand or theme change would require touching this file directly rather than a token update.

### Pillar 4: Typography (2/4)
- Only one standard Tailwind size class appears in the whole file: `text-xs` (7 occurrences: lines 118, 131, 135, 148, 156, 158, 186).
- Three arbitrary-value sizes outside the standard scale: `text-[10px]` at lines 165, 168, 173 (button labels and result-row text) — these fall below `text-xs` (12px) and are not part of any declared type scale, violating the "no arbitrary spacing/typography values" standard.
- Only 2 font weights used (`font-medium`, `font-semibold`) — within the acceptable ≤2-weight guidance, but combined with the single-size issue above, there is effectively zero typographic hierarchy in the component.

### Pillar 5: Spacing (3/4)
- No arbitrary px/rem spacing values found — all spacing uses the standard Tailwind scale (`p-1`, `p-3`, `px-2`, `py-0.5`, `py-1`, `gap-1`, `gap-2`, `gap-4`, `space-y-1/2/4`).
- Spacing is internally consistent (card padding `p-3` throughout, button padding `px-2 py-0.5` throughout) — no mixed patterns for the same element type.
- However every value sits at the low end of the scale (`p-1`, `py-0.5`) which, combined with `text-[10px]`/`text-xs` everywhere, produces a visually dense, cramped card layout with little breathing room between account rows and their action buttons.

### Pillar 6: Experience Design (2/4)
- Loading state exists but is minimal: a plain `<p>` "Loading..." string (line 148) rather than a skeleton — acceptable but not polished for a dashboard that fetches two endpoints in parallel.
- Error handling covers all four async paths (fetch, register, scan, loadResults) but every path terminates in a toast with no retry affordance — if the initial `fetchData()` call fails, the entire dashboard body renders empty (`accounts` and `summary` stay at their initial falsy/empty values) with only a transient toast as evidence something went wrong.
- Empty state for zero accounts is handled correctly (line 186: `!loading && accounts.length === 0`).
- Disabled state for in-flight scans is handled correctly (`disabled={scanning[a.id]}` line 165, with button label swapping to "Scanning...").
- No destructive actions exist in this component (no delete/deregister account action), so the "confirmation for destructive actions" criterion doesn't apply — but this also means there's no way to remove a misregistered account without a backend call, a functional gap worth flagging even if outside pure UI scope.
- Results are silently truncated to 5 (`.slice(0, 5)`, line 172) with no count or "view more" indicator — a user cannot tell if 5 results is the whole set or a subset.
- Component is wrapped in an `ErrorBoundary` at the router level (`App.tsx:1700`), which is a positive safety net for render-time crashes.
- Registry audit: `components.json` not found — shadcn not initialized, registry safety audit skipped per protocol.

---

## Files Audited
- `components/CloudAccountsDashboard.tsx` (190 lines, full read)
- `App.tsx` (route wiring at line 1700, confirmed ErrorBoundary wrapping and absence of a page-level title)
- `.planning/phases/20-multi-account-cloud/20-01-SUMMARY.md`
- `.planning/phases/20-multi-account-cloud/20-01-PLAN.md`
