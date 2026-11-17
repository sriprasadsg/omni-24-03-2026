# Phase 78 — UI Review

**Audited:** 2026-11-17
**Baseline:** 78-UI-SPEC.md (approved 2026-11-16)
**Screenshots:** not captured (code-only audit; no dev-server probe was run, and the surface needs a tenant-selected Super Admin session that a bare `/` capture cannot reach)
**Interaction captures:** off (workflow.ui_interaction_capture is false). All interaction findings are code-derived.

Audited committed code only (`git show HEAD:components/itam/ItamKpiPanel.tsx`; `git diff fd4e00f24 HEAD` for ReportsPanel, ITAMConsole, apiService, App.tsx). The user's uncommitted hunks were ignored.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | All contract strings match verbatim; Select block tells Platform Support to "Open a tenant from Tenants", which they cannot do |
| 2. Visuals | 3/4 | Tile hierarchy and a11y wiring match the spec; no loading/disabled visual verification possible without screenshots |
| 3. Color | 3/4 | Not-tracked is neutral gray as specified; chart hexes hardcoded (pre-existing), one pre-existing `text-gray-500` lacks a dark variant |
| 4. Typography | 4/4 | Only 12/14/24px and 400/600 used on new elements, as declared |
| 5. Spacing | 3/4 | Mixed `mb-1`/`mt-1` stacking inside the summary block; `p-8` Select block is an unlisted spacing token if the scale is 4/8/16/24 |
| 6. Experience Design | 3/4 | Tenant reset and `needsTenant` handled, but ReportsPanel has no stale-response guard, so a late result from tenant A can land under tenant B |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **ReportsPanel has no stale-response guard (WARNING)** — A prebuilt report started for tenant A and still in flight when the Super Admin switches to tenant B resolves into `setResult` and shows A's rows under B. This is the exact cross-tenant failure the phase exists to prevent (UI-SPEC section 4 and R3 demand an ignored late response). Fix: a request-id ref or an AbortController keyed on `tenantId` in `runPrebuilt`, and also reset `running` in the tenant-change effect (it is not reset at ReportsPanel.tsx ~L82-90).
2. **Select-a-tenant body is wrong for Platform Support (WARNING)** — The block can show for Platform Support after a server 400 (R5), but the copy says "Open a tenant from Tenants, then come back to Reports", and `Go to Tenants` is hidden for them. They are left with an instruction they cannot follow. Fix: when `onGoToTenants` is absent, use body copy such as "Ask a platform administrator to select an organization", or add a variant to `ITAM_KPI_COPY`.
3. **Custom/saved reports stay runnable and exportable with no tenant (WARNING)** — With `needsTenant`, only the pre-built Run buttons are disabled; saved report runs and the builder still fire and will toast the raw server 400. The spec explicitly leaves them untouched, so this is a contract gap rather than a deviation. Fix: confirm the server rule covers custom reports and, if so, disable or note them too.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- `ITAM_KPI_COPY` (ItamKpiPanel.tsx L16-26) matches the Copywriting Contract exactly: `Not tracked`, hint, `No active assets`, `Valued x of y asset(s)` with the singular handled by `plural(y)`, `{n} disposed or retired asset(s) not counted`, Select heading/body, `Go to Tenants`, and the Reports note. The old `{n} assets` line is gone.
- WARNING: L23 body copy assumes the viewer can open Tenants (see fix 2).
- The Reports note says "These reports", which is correct per R10 and does not name Costs.
- The tile's `hasData` false state still reads "No data yet / Add an asset from the Catalog tab", per spec.

### Pillar 2: Visuals (3/4)
- The figure is the focal point (`text-2xl font-semibold`), with the Valued line beneath and the pie below. The `Not tracked` figure keeps the same size (R9), so there is no layout shift.
- `aria-describedby="itam-kpi-asset-value-summary"` is set only when `!loading && !failed && hasData` (L163), and the target id exists in the same state. Correct.
- The Select block is `role="status"` with no icon, as specified. It replaces the whole four-tile grid, which is the spec'd behavior.
- The nested summary sits inside a `<button>`, so the hint line is read as part of the button, which is acceptable here.
- Not verified visually: 320px overflow for a large book value (spec backstop); the summary has no `break-words`, so a very long figure could overflow `text-2xl` in a `sm:grid-cols-2` tile.

### Pillar 3: Color (3/4)
- The Not-tracked figure uses `text-gray-500 dark:text-gray-400`, with no red or amber. Cyan is used only on `Go to Tenants` and the existing Run Report buttons and tile accents, so accent use stays within the declared elements.
- `CHART_COLORS` (L40) are 7 hardcoded hex values (pre-existing, not introduced by this phase); the legend font is a fixed 10px.
- Run-button disabled state uses `disabled:opacity-50` only; `hover:bg-cyan-500` still applies when enabled, and disabled buttons do not show hover. Fine.

### Pillar 4: Typography (4/4)
- New elements use only `text-xs` (12), `text-sm` (14) and `text-2xl` (24), with weights 400/600. Matches the declared type table with no extra sizes or weights.

### Pillar 5: Spacing (3/4)
- The summary block mixes `mb-1` on the figure and `mt-1` on the excluded and hint lines, so it adds up to 8px on those gaps; consistent enough, but the figure-to-Valued gap (4px) differs from Valued-to-excluded (4px) only by accident of margin direction.
- The Select block uses `p-8 mb-6`; the surrounding ITAM panels use `p-4` and `mb-6`. Spec-compliant (specified), but heavier than its neighbors.
- No arbitrary `[..px]` values were introduced.

### Pillar 6: Experience Design (3/4)
- Good: the effect resets `data`, `failed` and `tenantRejected` before each request and uses a `cancelled` flag (L99-122), so KpiPanel is race-safe. `needsTenant` makes no request (D-17). The 400 message is pattern-matched only and never rendered (T-78-07). The `tenantId || undefined` handling in apiService is correct.
- WARNING: ReportsPanel (see fix 1). `runPrebuilt` depends on `tenantId` but ignores late responses, and the reset effect leaves `running` true if a request was in flight.
- WARNING: the reset effect skips first mount via a ref, which is right for drill-down, but the `focusReportKey` run effect re-creates `runPrebuilt` on a tenant change and can re-trigger the run for the new tenant if `focusReportKey` is still set (it is cleared by `onFocusHandled`, so low risk).
- `generateItamReport` passes `tenantId` for prebuilt reports only. Custom report exports go without it (see fix 3).
- `Disabled` Run buttons carry `aria-describedby` to a visible note. Good.
- No destructive actions in this phase.

---

## Files Audited
- components/itam/ItamKpiPanel.tsx (HEAD)
- components/itam/ReportsPanel.tsx (phase diff)
- components/itam/ITAMConsole.tsx (phase diff)
- services/apiService.ts (phase diff)
- App.tsx (phase diff, ITAM case only)
- .planning/phases/78-organization-endpoint-cost-api/78-UI-SPEC.md
