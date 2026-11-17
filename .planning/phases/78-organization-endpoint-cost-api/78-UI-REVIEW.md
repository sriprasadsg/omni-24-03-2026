# Phase 78 — UI Review (re-audit after gap plan 78-11)

**Audited:** 2026-11-17
**Baseline:** 78-UI-SPEC.md (approved 2026-11-16)
**Screenshots:** not captured (code-only audit; no dev server was started, and the surface needs a tenant-selected Super Admin session that a bare `/` capture cannot reach)
**Interaction captures:** off (workflow.ui_interaction_capture is false). All interaction findings are code-derived, plus the 78-11 test evidence in its SUMMARY (not re-run here).

Audited committed code only (`git show HEAD:components/itam/ReportsPanel.tsx`, `HEAD:components/itam/ItamKpiPanel.tsx`). The two uncommitted one-line lint-comment removals were ignored. This review replaces the earlier 19/24 review (commit 9a85e37d3).

---

## Changes since the previous review

**Resolved by 78-11**
- Previous fix 1, no stale-response guard in ReportsPanel (WARNING): resolved. `runSeq` (ReportsPanel.tsx L88) is taken by `runPrebuilt` (L107), `runSavedCustom` (L133) and `handlePreviewCustom` (L159). The tenant-change effect bumps it (L93). Stale success and failure paths return before any state write or toast (L110, L114, L136, L140, L163). `running` is cleared only by the current request (L117, L143).
- The `running` flag no longer sticks on a tenant change: the reset effect calls `setRunning(false)` (L94), and it also clears `showingPreview`, `result`, `activeKind`, `activeKey` and `page`.
- `resultIsCurrent` (L223) gates the result block (L322). The unsaved builder preview, which renders with `activeKind` and `activeKey` null, is kept visible through `showingPreview`, and export stays off because `canExport` (L220) still needs both values.

**Remain unchanged**
- Select-a-tenant body copy for Platform Support (ItamKpiPanel.tsx L23, not touched by 78-11).
- Custom and saved reports not tenant-aware or disabled under `needsTenant` (the spec leaves them untouched, PROH-78-08, WR-02 still awaits the user).
- All pre-existing color, spacing and 320px-overflow notes.

**New**
- See Pillar 6 findings N1 to N3. None is a blocker.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | All contract strings match verbatim; Select body tells Platform Support to "Open a tenant from Tenants", which they cannot do |
| 2. Visuals | 3/4 | Tile hierarchy and a11y wiring match the spec; unverified without screenshots (320px overflow, loading/disabled look) |
| 3. Color | 3/4 | Not-tracked is neutral gray as specified; hardcoded chart hexes (pre-existing); `text-gray-500` without a dark variant on report descriptions |
| 4. Typography | 4/4 | Only 12/14/24px and 400/600 on new elements, as declared |
| 5. Spacing | 3/4 | Mixed `mb-1`/`mt-1` stacking in the summary block; `p-8` Select block heavier than its `p-4` neighbors |
| 6. Experience Design | 3/4 | Stale-response gap closed and tested; custom reports still run and export with no tenant; superseded runs vanish silently in two edge cases |

**Overall: 19/24** (same total as before). Pillar 6 stays at 3 because the headline defect was fixed but the remaining gaps (custom-report tenant handling, the silent-supersede edge cases) keep it below 4. The fix removes a cross-tenant data leak risk rather than lifting a pillar from a lower score, so the arithmetic does not move.

---

## Top 3 Priority Fixes

1. **Custom/saved reports stay runnable and exportable with no tenant (WARNING, carried over)** — With `needsTenant`, only the pre-built Run buttons are disabled (ReportsPanel.tsx L246). `runSavedCustom` (L135), `previewItamCustomReport` (L162) and the custom export (L211) carry no tenant, so a Super Admin with no tenant selected can still run them and gets the raw server 400 toast, or an unscoped result. Fix: settle WR-02 (confirm the server rule for custom reports), then disable or annotate the saved-report Run buttons and the builder under `needsTenant`, or thread `tenantId` through them.
2. **Select-a-tenant body is wrong for Platform Support (WARNING, carried over)** — `selectTenantBody` says "Open a tenant from Tenants, then come back to Reports" (ItamKpiPanel.tsx L23), but `Go to Tenants` is hidden for Platform Support. Fix: a variant used when `onGoToTenants` is absent, for example "Ask a platform administrator to select an organization."
3. **A superseding builder preview silently kills an in-flight run (WARNING, new)** — `handlePreviewCustom` bumps `runSeq` and sets `running` false (L159-160) before the preview returns. If the preview then throws, the earlier run's result is dropped, no Loading state is shown, and the user sees the older result or nothing with no explanation. Fix: only supersede after the preview succeeds, or surface the preview failure inline.

Minor (not in the top 3): the delete path (L192-196) clears the active custom result but does not bump `runSeq`, so an in-flight run of the report just deleted can still land. Add `runSeq.current += 1` there.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- `ITAM_KPI_COPY` (ItamKpiPanel.tsx L16-26) matches the Copywriting Contract: `Not tracked`, hint, `No active assets`, `Valued x of y asset(s)` with correct singular, excluded line, Select heading, `Go to Tenants`, and the Reports note. 78-11 changed no copy.
- WARNING: L23 body assumes the viewer can open Tenants (fix 2).
- ReportsPanel copy is unchanged and consistent: `Run Report`, `No matching assets`, `Adjust your filters and run the report again.`, and the specific export error string (L24).
- The suppressed stale-failure path raises no toast, which is the right behavior: no copy leaks from a request the user already moved past.

### Pillar 2: Visuals (3/4)
- The figure is the focal point (`text-2xl font-semibold`) with Valued and excluded lines beneath. Not-tracked keeps the same size, so no layout shift.
- `aria-describedby` on the tile is applied only when the summary exists. The Select block is `role="status"` and replaces the four-tile grid, as specified.
- 78-11 adds no visuals. Behaviorally the result region now disappears on a tenant switch instead of showing the old tenant's table, which is the correct focal-point behavior.
- Not verified visually: 320px overflow of a large book value in a `sm:grid-cols-2` tile (no `break-words`), and the disabled Run button look.
- Icon-only buttons: none introduced; the export and Run buttons carry text.

### Pillar 3: Color (3/4)
- Not-tracked uses `text-gray-500 dark:text-gray-400`, no red or amber. Cyan is limited to `Go to Tenants`, Run Report, Create Custom Report, Export buttons and the existing tile accent, which stays inside the declared accent list. The repeated `bg-cyan-600` on five button kinds is the existing screen pattern.
- `CHART_COLORS` in ItamKpiPanel are hardcoded hex values (pre-existing).
- ReportsPanel L241 `text-gray-500` (report description) and several `text-gray-500` empty-state strings (L279, L361) have no dark variant. Pre-existing, contrast on the dark card is borderline.

### Pillar 4: Typography (4/4)
- ReportsPanel: `text-lg` headings, `text-sm` and `text-xs` body, weights `font-semibold`/`font-medium` only. New KPI elements use 12/14/24px and 400/600 as declared. 78-11 added no classes.

### Pillar 5: Spacing (3/4)
- Summary block mixes `mb-1` and `mt-1`, giving 4px steps by accident of margin direction (pre-existing from 78-02).
- Select block `p-8 mb-6` against `p-4` neighbors: spec-compliant but heavier.
- ReportsPanel uses `mb-3`, `mb-6`, `gap-4`, `p-4`, `p-8`, `py-1.5`; `py-1.5` and `mt-0.5` are half-step values outside a strict 4/8/16/24 scale (pre-existing). No arbitrary `[..px]` values introduced.

### Pillar 6: Experience Design (3/4)
- Resolved (R3, T-78-27): a late response from tenant A cannot render under tenant B for pre-built runs, saved runs or builder previews; out-of-order runs in one tenant end on the later-issued request; switching to no tenant clears Loading at once. Backed by 8 new tests (`ITAMReportsPanelStaleResponse.test.tsx` and one console-level test); the SUMMARY records a full-suite pass and a build, which I did not re-run.
- Still good: KpiPanel effect resets state per request with a `cancelled` flag; `needsTenant` makes no request; the 400 text is pattern-matched and never rendered; Run buttons carry `aria-describedby` to a visible note; the delete action goes through a confirm Modal.
- WARNING (carried): custom reports have no tenant handling (fix 1). The 78-11 SUMMARY states this was left as is by design.
- WARNING N1 (new): preview supersede with a failed preview drops the in-flight run silently (fix 3).
- N2 (new, minor): `handleDeleteConfirm` does not bump `runSeq` (see above).
- N3 (new, minor): the `focusReportKey` effect (L121-126) calls `onFocusHandled` in `.finally`, so a drill-down run dropped by a quick tenant switch is still marked handled and is not retried under the new tenant. Acceptable, since R3 says reports clear on switch, but it means a drill-down tile click followed by a tenant change ends on an empty Reports tab with no hint. A `Select a report to run` empty state would help; none exists.
- Pagination Previous/Next are disabled only at the bounds, not while `running`; a double click can queue two page requests, now safely resolved by `runSeq`.
- No destructive action added by this phase.

---

## Files Audited
- components/itam/ReportsPanel.tsx (HEAD, 427 lines)
- components/itam/ItamKpiPanel.tsx (HEAD, copy block L14-26)
- .planning/phases/78-organization-endpoint-cost-api/78-UI-SPEC.md, 78-CONTEXT.md, 78-01 to 78-11 SUMMARY and PLAN files, previous 78-UI-REVIEW.md
- Not re-read this round: ITAMConsole.tsx, apiService.ts, App.tsx (unchanged by 78-11; earlier review findings stand)
