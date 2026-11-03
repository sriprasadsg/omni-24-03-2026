---
phase: "87"
slug: "partner-and-reseller-channel"
audited: "2026-11-03"
mode: code-only
baseline: 87-UI-SPEC.md
overall_score: 17
max_score: 24
---

# Phase 87: UI Review

**Audited:** 2026-11-03, after execution (all 15 plans committed).
**Mode:** code-only.
- The Phase 87 UI is not published, and no dev server served it, so no screenshots were taken. Interaction capture is off.
- The auditor read 432 of the 549 UI-SPEC lines.
- Checks were targeted greps plus a read of the `PartnersDashboard` row actions. The `App.tsx` shell edits were not audited, because the auditor missed the file at the project root.
- Treat the scores as provisional until the browser pass. The orchestrator re-checked findings 1 and 2 against the current files.

## Scores

| Pillar | Score | Key finding |
|---|---|---|
| Copywriting | 3/4 | The spec strings that were checked match: Export CSV, Exporting..., the export-failure toast, Try again, Clear search, Show more customers, Refresh customers, the empty-state headings and the viewer read-only line. No full copy-contract pass was made. |
| Visuals | 2/4 | Row-action `aria-label`s replace the visible button text, so the accessible name does not contain the words on screen. |
| Color | 3/4 | Accent use stays within the six reserved items. The bar fills use `bg-primary-600`. No hard-coded hex or rgba. Chip and button colour classes were not checked in full. |
| Typography | 3/4 | One size outside the spec's four, on the accept-invite brand line. No `font-medium` or `font-bold`. |
| Spacing | 3/4 | Controls use `min-h-10`, row actions `min-h-8`, and the pool bar `h-2`, which the spec allows. A few 12px gaps sit off the scale. |
| Experience Design | 3/4 | State coverage is thorough in code: `aria-busy`, `role="alert"`, `aria-describedby` on the disabled Create customer, the viewer line, the token stripped by `replaceState`, and focus on the heading. None of it has been seen at runtime. |

**Overall: 17/24**

## Priority Fixes

1. **Label in Name (WCAG 2.5.3) on Partners row actions.**
   - In `components/PartnersDashboard.tsx`, the row-action `aria-label`s replace the visible text. `Edit partner` is announced as `Edit {name}`. `Suspend partner` and `Reinstate partner` are announced as `Suspend {name}` and `Reinstate {name}`.
   - A voice-control user saying "click Edit partner" will not match.
   - Fix: keep the visible words at the start, as in `Edit partner {name}`, `Suspend partner {name}` and `Reinstate partner {name}`. The alternative is an `sr-only` suffix in place of the `aria-label`.
   - `Show customers of {name}`, `Move {name}` (spec-given) and the portal's `Change seats for {name}` already keep the visible words.
2. **A fifth font size.**
   - `components/AcceptInvitePage.tsx:390` uses `text-2xl` (24px) for the brand line. The spec allows 12, 14, 18 and 30px.
   - Fix: use `text-lg` or `text-3xl`, or record it in the spec as the inherited sign-in brand treatment.
3. **No browser pass yet.**
   - All responsive, theme and state behaviour comes from reading code. That includes the stacked cards below `lg`, horizontal scroll below `xl`, dark mode, and the three backstop layout checks.
   - Fix: run a local dev server, or publish when ready. Capture Partners, the Partner portal as admin and as viewer, and Accept invite at 1440, 768 and 375px in light and dark. This is already a 87-14 human check.

## Minor Recommendations

- **12px gaps.** `gap-3` and `space-y-3` (12px) are off the 4/8/16/24/32/48 scale. Use `gap-2`/`gap-4` and `space-y-2`/`space-y-4`. They appear in:
  - `components/PartnerPortal.tsx:300`
  - `components/PartnerCustomerModals.tsx:442`
  - `components/PartnersDashboard.tsx:178,406`
  - `components/PartnerTeamPanel.tsx:266,311`
  - `components/PartnerScreenPicker.tsx:153`
- **Remaining audit work.**
  - A full copy-contract pass against the UI-SPEC Copywriting Contract.
  - An audit of the `App.tsx` shell edits (the lazy views, the `/accept-invite` branch and the Tenants filter).

## Spec-Compliant Checks Passed

- **Typography:**
  - Page titles use `text-3xl font-semibold leading-tight` (PartnersDashboard.tsx:394, PartnerPortal.tsx:282).
  - Stat values use `text-3xl`, and the date tile `text-lg`.
  - The accept-invite heading is `text-lg`.
  - Chips use `text-xs font-semibold`.
- **Pool bar:** `role="img"` with `aria-label="{n} of {m} seats handed out"`.
- **Customers disclosure:** carries `aria-expanded` and `aria-controls`.
- **Export CSV:** a secondary button, disabled while loading, on load error and while exporting.
- **Accept invite:** the password toggle uses `aria-pressed`, and the rule list labels each rule as met or not met.
- **No markup injection:** no `dangerouslySetInnerHTML` in any Phase 87 component.
- **Shell:** the partner header and the headerless single sidebar entry are present, and partners get no support-unread polling (Header.tsx, Sidebar.tsx).

Registry audit: skipped (no components.json).
