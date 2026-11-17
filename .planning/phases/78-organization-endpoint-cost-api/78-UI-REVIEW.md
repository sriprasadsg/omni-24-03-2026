# Phase 78 — UI Review (re-audit after gap round 2, plans 78-12..78-15)

**Audited:** 2026-11-17
**Baseline:** 78-UI-SPEC.md (approved 2026-11-16), plus the D-13/D-14 amendments in 78-CONTEXT.md
**Screenshots:** not captured (code-only audit; no dev server was started, and the surface needs a tenant-selected Super Admin session that a bare `/` capture cannot reach)
**Interaction captures:** off (workflow.ui_interaction_capture is false). All interaction findings are code-derived, plus the SUMMARY test evidence for 78-12..78-15 (not re-run here).

Audited the working tree: `components/itam/ReportsPanel.tsx` (367 lines, carries the user's uncommitted edits), `components/itam/ReportResultView.tsx` (129 lines, committed), `ItamKpiPanel.tsx` copy block, `ITAMConsole.tsx` wiring. This review replaces the 19/24 review written after 78-11.

---

## Changes since the previous review

**Resolved by gap round 2**
- WR-04 (export target and rows could drift): one `shown` object (`ShownReport`, ReportResultView.tsx L10-15) holds kind, key, page and data together, written only by the current request (ReportsPanel L129, L151, L178). The failed-run case leaves the shown report intact because the in-flight run is held in `pending` (L47). Export reads its target from `shown` at click time (L221).
- IN-05 (export crossing tenants): `tenantEpoch` (L107) moves only on a tenant switch, and export, save and delete all compare it after each await (L190, L206, L226).
- WR-02 (custom reports ignoring the tenant, previous top fix 1): resolved. `listItamCustomReports`, `runItamCustomReport`, `previewItamCustomReport`, `saveItamCustomReport` and `deleteItamCustomReport` all take `tenantId` (L86, L149, L176, L189, L205). With `blocked`, the section shows a note (L297-301, `customReportsSelectTenantNote`), the Create Custom Report button is disabled with `aria-describedby` (L280-285), the builder is not rendered (L290) and the saved table and Run buttons are not rendered (L302-309). No saved-list request is sent without a tenant (L78-83).
- No-tenant state for every platform tier (78-15): `needsTenant` is `(isSuperAdminView || isPlatformView) && !tenantId` (ITAMConsole L85). A server "Select a tenant" rejection now sets `tenantRejected` (L58-67) from list, run, saved run and export, and blocks the same controls instead of toasting. The tenant-switch effect clears it (L120).
- Saved list stale-response guard (`listSeq`, L75) and the delete modal closing on a tenant switch (L119): both new and correct.
- Previous minor, delete path not bumping `runSeq`: still open but now mostly moot, see Pillar 6.

**Unchanged from the previous review**
- Select-a-tenant body copy tells Platform Support to "Open a tenant from Tenants" (ItamKpiPanel L23).
- Hardcoded chart hexes, `text-gray-500` without a dark variant, half-step spacing values.
- No screenshots, so 320px overflow of a large book value is still unverified.

**New findings**
- See Pillar 6 N1 to N4. None is a blocker.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | All contract strings verbatim; new custom-reports note is clear; Select body still wrong for Platform Support |
| 2. Visuals | 3/4 | Result block now extracted and coherent (title, export, rows always one report); unverified without screenshots |
| 3. Color | 3/4 | Neutral gray notes with dark variants; `text-gray-500` without dark variant on result-view empty state and table header |
| 4. Typography | 4/4 | Only 12/14/18/24px and 400/500/600 across the touched files; nothing outside the declared set on new elements |
| 5. Spacing | 3/4 | Consistent `mb-3`/`mb-6`/`p-4`/`p-8`; half-step `py-1.5`/`mt-0.5` and `mb-1` stacking remain |
| 6. Experience Design | 3/4 | Cross-tenant and export drift gaps closed and no-tenant state is complete; four small edge cases remain |

**Overall: 19/24** (same total as the previous review). Pillars are unchanged because the round fixed data-integrity and consistency defects (WR-02, WR-04, IN-05) that the previous review had scored as warnings inside a 3, and the remaining defects are new small edge cases, not leftovers. I am not raising Pillar 6 to 4: a plausible superseded-run path and the unrouted preview rejection (N1, N2) are real, user-visible gaps.

---

## Top 3 Priority Fixes

1. **Select-a-tenant body is wrong for Platform Support (WARNING, carried over)** — `selectTenantBody` says "Open a tenant from Tenants, then come back to Reports" (ItamKpiPanel.tsx L23), but `Go to Tenants` is hidden for Platform Support and the new `isPlatformView` path makes this user class land in `needsTenant` more often. They are told to do something they cannot do. Fix: a second body used when `onGoToTenants` is absent, for example "Ask a platform administrator to select an organization."
2. **A builder preview silently kills an in-flight run (WARNING)** — `handlePreviewCustom` bumps `runSeq` and clears `pending` (L173-174) before the preview returns. If the preview then fails, the builder form toasts, but the run the user started is already dropped: its Loading line disappears and it never lands, and the old `shown` report stays with no hint. Fix: bump `runSeq` and clear `pending` only after the preview succeeds, or keep the pending run until then.
3. **A preview rejected with "Select a tenant" is not routed to the no-tenant state (WARNING)** — `runPrebuilt`, `runSavedCustom`, list and export call `takeTenantRejection`; `handlePreviewCustom` (L170-182) has no catch and rethrows to `ReportBuilderForm`, which toasts the raw server message. This is the one path that still shows the raw 400 for a Platform Support user, contradicting the 78-15 intent and R5. Fix: catch in `handlePreviewCustom`, call `takeTenantRejection(e)` and only rethrow when it returns false.

Minor (not in the top 3):
- `builderOpen` (L50) is not reset when `blocked` becomes true or the tenant switches, so the builder reappears already open, with the previous tenant's unsaved form state kept by the child, once a tenant is selected again. Reset it in the tenant-switch effect.
- `handleDeleteConfirm` clears `shown` for the deleted report (L208) but does not bump `runSeq`, so an in-flight run of that report can still land and re-show a deleted report.
- `focusReportKey` effect (L139-143) has `[focusReportKey]` as its only dependency and marks the focus handled in `.finally` even when the run was dropped by a tenant switch; the user lands on an empty Reports tab with no "Select a report to run" hint.
- Pagination Previous/Next stay enabled while a run is in flight; however, `canExport` is false and the rows are replaced by Loading during `pending`, so the controls vanish with the rows (ReportResultView L45, L52). This is acceptable and noted only because it changed since the last review.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- `ITAM_KPI_COPY` (ItamKpiPanel.tsx L16-28) matches the Copywriting Contract for every string in the spec: `Not tracked`, hint, `No active assets`, singular/plural Valued and excluded lines, `Select a tenant`, `Go to Tenants`, and the reports note.
- New string `customReportsSelectTenantNote` (L27): "Select a tenant to see, build and run its custom reports. They cover one organization at a time." Specific, states the next step, and uses "tenant" and "organization" the way the contract prescribes. It is not in the approved contract (the contract left custom reports untouched) but follows the declared pattern; it is a legitimate consequence of the D-13 amendment.
- WARNING: L23 body assumes the viewer can open Tenants (fix 1).
- Result view copy is unchanged and specific: `No matching assets`, `Adjust your filters and run the report again.`, `Exporting…`, the export error string (ReportsPanel L24). Toasts for list failure (`Failed to load saved reports`) are generic but give the server message first.
- No generic "Submit/OK/Cancel" labels in the touched files. The delete modal uses `Delete` with a title and consequence sentence.

### Pillar 2: Visuals (3/4)
- `ReportResultView` is a clean extraction: the title, export buttons, Loading line, empty state and table all derive from `shown` and `pendingTitle`, so the focal point is always the one report on screen. While a run is in flight the title switches to the pending report and the old rows give way to `Loading…` (L40-45, L68), which removes the earlier mismatch where a title could describe a different report than the rows.
- The unsaved builder preview renders rows with no export and no page controls (`kind` and `key` null, L44, L108), as intended (D-02).
- Disabled Create Custom Report plus the muted note inside the saved-reports card gives a coherent explanation in the same place the table would be.
- Not verified visually: 320px overflow of the Select block and large book values; the disabled button contrast; truncation (`truncate max-w-xs` with a `title` tooltip) on long cells. Icon-only buttons: none; Download icon buttons carry text labels.
- Table cell truncation hides content at `max-w-xs` and relies on a `title` tooltip, which does not work on touch devices (minor).

### Pillar 3: Color (3/4)
- Accent use stays inside the declared list: cyan on Run Report, Create Custom Report, Export buttons, the saved-report `Run` text button and the tile accent. The `Delete` text button is red, which is the destructive convention and is backed by a confirm Modal.
- New notes use `text-gray-500 dark:text-gray-400` (ReportsPanel L250, L298), as the contract requires.
- Remaining: `text-gray-500` without a dark variant on report descriptions (L261), the empty-state strings (L306, ReportResultView L77), and table header cells (L313, ReportResultView L87). Contrast on the dark card is borderline. `CHART_COLORS` hardcoded hex values are pre-existing in ItamKpiPanel.
- Counts (`grep` of the two files): `bg-cyan-600` appears on 4 button kinds; no accent on non-interactive text.

### Pillar 4: Typography (4/4)
- Heading `text-lg font-semibold` for section titles and the result title, `text-sm` for body and table, `text-xs` for notes, hints and buttons; weights `font-semibold` and `font-medium` only. No arbitrary sizes. The 18px section heading and the `font-medium` weight are pre-existing screen conventions outside the Phase 78 elements, whose three sizes and two weights remain as declared.

### Pillar 5: Spacing (3/4)
- Consistent rhythm: `mb-6` between sections, `mb-3` title-to-content, `gap-4` grid, `p-4` card, `p-8` empty and Select block. No arbitrary `[..px]` values.
- Remaining: `py-1.5`, `mt-0.5` and the `mb-1` summary stacking (pre-existing) sit outside a strict 4/8/16/24 scale. The `Create Custom Report` button uses `px-4 py-2` while sibling Run buttons use `px-3 py-1.5`, a minor size inconsistency within one screen (pre-existing).

### Pillar 6: Experience Design (3/4)
- Loading: pending run shows `Loading…` with the pending title; saved list shows `Loading…`; no stale rows are visible during a run. Tenant switch clears `shown`, `pending`, saved list, delete target, export state and rejection (L109-121).
- Error: tenant rejections become the no-tenant state; other failures toast the server text. A stale failure raises nothing (L131, L153).
- Empty: `No matching assets`, `No custom reports yet`, and the no-tenant notes. Disabled: every Run button and Create Custom Report, with `aria-describedby` to a visible reason; export buttons disable while exporting.
- Destructive: delete goes through a Modal with a consequence sentence; closes on tenant switch.
- Tenant isolation behaviour (the phase's purpose) is well covered: `runSeq` for runs, `listSeq` for the list, `tenantEpoch` for export, save and delete. The SUMMARY records the added tests (`ITAMReportsPanelStaleResponse`, `ITAMReportsPanelTenantRule`); not re-run here.
- WARNING N1: preview supersedes an in-flight run before it succeeds (fix 2).
- WARNING N2: preview does not route a "Select a tenant" rejection (fix 3).
- N3 (minor): `builderOpen` persists across tenant switches and the blocked state.
- N4 (minor): delete does not bump `runSeq`; `focusReportKey` is marked handled even for a dropped run.
- Accessibility: both notes are `role="status"` with ids referenced by `aria-describedby`; native `disabled`; no keyboard traps added.

---

## Files Audited
- components/itam/ReportsPanel.tsx (working tree, 367 lines)
- components/itam/ReportResultView.tsx (129 lines)
- components/itam/ItamKpiPanel.tsx (copy block L14-28, props)
- components/itam/ITAMConsole.tsx (needsTenant and prop wiring, L59-85, L148-149, L163-196)
- components/itam/ReportBuilderForm.tsx (preview call and catch, L141-154)
- .planning/phases/78-organization-endpoint-cost-api/78-UI-SPEC.md, 78-CONTEXT.md, 78-12..78-15 SUMMARY and PLAN files, previous 78-UI-REVIEW.md
- Not re-read this round: services/apiService.ts and App.tsx (user's uncommitted edits; their tenant parameters were inferred from the ReportsPanel call sites)
