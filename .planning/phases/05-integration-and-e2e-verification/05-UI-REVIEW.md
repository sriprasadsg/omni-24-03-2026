# UI Review: Phase 5 — v1.0 Frontend Audit
**Date:** 2026-06-20
**Scope:** All v1.0 UI components (Phases 2 + 4)
**Phase:** 05-integration-and-e2e-verification
**Screenshots:** Not captured (no dev server detected)
**Audit baseline:** Abstract 6-pillar standards (no UI-SPEC.md)
**Registry audit:** Skipped (no components.json / shadcn not initialized)

---

## Score Summary

| Pillar | Score | Rating |
|--------|-------|--------|
| Copywriting | 2/4 | Needs Work |
| Visuals | 3/4 | Good |
| Color | 3/4 | Good |
| Typography | 3/4 | Good |
| Spacing | 3/4 | Good |
| Experience Design | 2/4 | Needs Work |
| **Overall** | **16/24** | **Needs Work** |

---

## Pillar 1: Copywriting

**Score: 2/4 — Needs Work**

### Findings

**[SEVERITY: HIGH] RemediationTaskModal / RemediationDashboard: Silent failures expose nothing to the user**
- Location: `RemediationTaskModal.tsx:68`, `RemediationTaskModal.tsx:100`, `RemediationDashboard.tsx:36`, `RemediationDashboard.tsx:60`, `AssetComplianceList.tsx:43`, `AssetComplianceList.tsx:58`
- Issue: All six catch blocks send errors to `console.error` only. No toast, no inline message, no banner. When saving a remediation task fails (e.g., network error, 409 conflict), the "Saving..." spinner disappears and the modal stays open with no explanation. The user cannot distinguish "still saving" from "save failed silently."
- Impact: Users will retry actions, create duplicates, or conclude the product is broken. Compliance workflows where task saves are audit-critical need explicit failure copy.
- Fix: Replace each `console.error(...)` in catch blocks with a `showToast(...)` call (already used in FrameworkDetail.tsx for analogous operations). Minimum copy: "Failed to save — please try again" for task save, "AI suggestion unavailable" for suggest, "Could not delete evidence" for delete.

**[SEVERITY: HIGH] AssetComplianceList: "onUpdateStatus" is wired to console.log — action copy misleads users**
- Location: `FrameworkDetail.tsx:770`
- Issue: The "Mark Compliant" (CheckIcon) and "Mark Non-Compliant" (XIcon) buttons in AssetComplianceList call `onUpdateStatus`, but the prop is passed as `(assetId, status) => console.log(...)` — a no-op stub. Users click the buttons and see no feedback and no state change. The buttons carry implicit copy promises (check = compliant) that are silently broken.
- Impact: Operators trust the UI affordance, believe status was recorded, proceed to report generation — with stale data.
- Fix: Wire `onUpdateStatus` to a real API call in FrameworkDetail.tsx (same pattern as `onDeleteEvidence`). Until wired, at minimum surface a toast: "Status update is not yet available."

**[SEVERITY: MEDIUM] RemediationDashboard: Status badge display uses raw underscore string**
- Location: `RemediationDashboard.tsx:180`
- Issue: `task.status.replace('_', ' ')` only replaces the first underscore. A status of `in_progress_review` would render as `in progress_review`. The `.replace('_', ' ')` pattern (no `/g` flag) is fragile. Additionally, "in progress" (lowercase, space-separated) is inconsistent with the filter chips which read "In Progress" (title case). The table badge copy is de-capitalized; the filter chip is title-cased.
- Impact: Minor visual inconsistency that degrades professionalism in a compliance-audit product where label precision matters.
- Fix: Use `task.status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())` or map statuses to explicit display labels in FILTER_LABELS.

**[SEVERITY: MEDIUM] FrameworkDetail toolbar: seven buttons with no grouping and inconsistent action verbs**
- Location: `FrameworkDetail.tsx:507-576`
- Issue: Seven buttons appear in a horizontal row with no visual grouping: "Add Control", "Import Controls", a format selector, "Generate Report", "Collect Evidence", "Evaluate with AI Auditor", "View Reports". Three different verbs ("Generate", "Collect", "Evaluate") are used for AI-triggered actions. The format selector is orphaned from the "Generate Report" button with no visible relationship. A user must read all seven to understand the workflow.
- Impact: Cognitive overload before performing the primary compliance action; the format selector's relationship to report generation is unclear without a label.
- Fix: Group related buttons with a visual separator or dropdown. Rename "Evaluate with AI Auditor" to "Run AI Audit" for brevity and verb consistency.

**[SEVERITY: LOW] ReportsModal: empty state copy is generic**
- Location: `FrameworkDetail.tsx:302`
- Issue: "No reports found." gives no guidance on why or how to generate one.
- Fix: "No reports yet — use Generate Report above to create one."

### Positives
- RemediationDashboard empty state ("No remediation tasks found. Click **Create Task** to add one.") is specific and action-oriented.
- "Save the task first to get AI suggestions" tooltip on the disabled Suggest button is exemplary contextual guidance.
- AI validation feedback in ControlEvidenceUploadModal has graduated copy (Relevant / May not be relevant / Relevance unclear) that guides the user rather than exposing raw verdicts.

---

## Pillar 2: Visuals

**Score: 3/4 — Good**

### Findings

**[SEVERITY: MEDIUM] RemediationDashboard: loading state is text-only, no skeleton**
- Location: `RemediationDashboard.tsx:140-141`
- Issue: The loading state renders `<div className="p-8 text-center text-gray-400">Loading tasks...</div>` inside the table container. The height collapses to a single line, causing layout shift when tasks load. No skeleton rows are shown.
- Impact: Perceptible layout shift on every page load; feels unpolished for a dashboard that positions itself as a real-time operations tool.
- Fix: Render 4-5 skeleton rows with `animate-pulse` grey bars matching the table column widths (same pattern as exists in other dashboards in this codebase).

**[SEVERITY: MEDIUM] AssetComplianceList: icon-only action buttons lack visible labels**
- Location: `AssetComplianceList.tsx:183-189`
- Issue: The CheckIcon, XIcon, and UploadIcon buttons in the Actions column have `title` attributes (visible on hover) but no visible text labels. On touch devices, title tooltips do not fire. A user unfamiliar with the iconography cannot identify which button marks compliant vs. non-compliant without hovering.
- Impact: Accessibility and discoverability failure for the two most consequential status-change actions in the evidence workflow.
- Fix: Add `aria-label` attributes for screen reader support. For touch contexts, consider a brief visible label ("Compliant" / "Non-Compliant") under each icon, or a contextual dropdown.

**[SEVERITY: LOW] FrameworkDetail toolbar: button row overflows at moderate viewport widths**
- Location: `FrameworkDetail.tsx:506-577`
- Issue: Seven inline buttons with no `flex-wrap` guard. On 1024px viewports (common for enterprise laptops), the row will overflow its container and be partially hidden.
- Impact: Operators on standard laptop screens cannot access all framework actions without horizontal scrolling.
- Fix: Wrap in `flex flex-wrap gap-2` or consolidate into a dropdown for secondary actions.

### Positives
- STATUS_COLORS badge map with semantic red/yellow/green is clear and consistent across RemediationDashboard.
- Category icons in FrameworkDetail (BinocularsIcon for Identify, ShieldIcon for Protect, etc.) add scannable visual differentiation across 20+ categories.
- AI validation result in ControlEvidenceUploadModal includes contextual icons (ShieldCheckIcon for RELEVANT, AlertTriangleIcon for IRRELEVANT/UNCLEAR) that reinforce meaning beyond color alone.
- "Live" badge with AnimatedPulse ActivityIcon in RemediationDashboard header communicates real-time status without verbose copy.

---

## Pillar 3: Color

**Score: 3/4 — Good**

### Findings

**[SEVERITY: MEDIUM] FrameworkDetail: `bg-black bg-opacity-50` — legacy utility pattern inconsistent with rest of codebase**
- Location: `FrameworkDetail.tsx:81`, `:207`, `:269`
- Issue: Three modal overlays use the two-class pattern `bg-black bg-opacity-50` while `RemediationTaskModal.tsx:107` uses the modern slash syntax `bg-black/50`. Both are functionally identical but the inconsistency signals the FrameworkDetail modals predate the Tailwind v3 upgrade and were not brought in line.
- Impact: No visual defect, but signals inconsistent standards enforcement; maintainers may copy the old pattern for new code.
- Fix: Globally replace `bg-black bg-opacity-50` with `bg-black/50` in FrameworkDetail.tsx (3 occurrences).

**[SEVERITY: MEDIUM] FrameworkDetail toolbar: indigo-600 and purple-600 primary actions side-by-side**
- Location: `FrameworkDetail.tsx:541`, `:558`
- Issue: "Collect Evidence" uses `bg-indigo-600` and "Evaluate with AI Auditor" uses `bg-purple-600`. Both are high-emphasis filled buttons of equal visual weight but represent different tiers of action. In a dark-mode context, these two colors appear nearly identical (both are deep violet-adjacent). There is no consistent rule for which hue means what.
- Impact: Users cannot infer relative importance or trigger-type of the two AI-action buttons by color alone.
- Fix: Reserve `bg-primary-600` (indigo) for the single highest-priority action per toolbar group. Demote secondary AI action to a bordered/ghost style or consistent secondary color.

**[SEVERITY: LOW] AssetComplianceList: `text-[10px]` badge text may fail WCAG AA contrast**
- Location: `AssetComplianceList.tsx:139-141`
- Issue: "Automated" and "Manual" badges use `text-[10px]` (below the 12px minimum typically required for AA compliance at normal contrast ratios). At `text-blue-700` on `bg-blue-100`, the contrast ratio is approximately 4.5:1 at 12px but may drop below the enhanced threshold at 10px for users with visual impairment.
- Impact: Low-vision users may not be able to read the source badges, which are the only visual differentiator between automated and manual evidence in the table.
- Fix: Increase badge font to `text-xs` (12px) and verify contrast ratios with a WCAG tool.

### Positives
- STATUS_COLORS in RemediationDashboard correctly maps open→red, in_progress→yellow, resolved→green, dismissed→gray — all semantically appropriate.
- VERDICT_STYLES in FrameworkDetail (green/red/amber/gray) follows a consistent semantic color vocabulary for AI validation results.
- Dark mode variants are present on every badge and card in all audited components.

---

## Pillar 4: Typography

**Score: 3/4 — Good**

### Findings

**[SEVERITY: MEDIUM] AssetComplianceList / RemediationDashboard: typography scale compressed to two practical sizes**
- Location: `AssetComplianceList.tsx` throughout, `RemediationDashboard.tsx` throughout
- Issue: Grep analysis shows 27 uses of `text-xs` and 18 of `text-sm` in the three core Phase 4 components, with `text-2xl` appearing only twice (both in stat cards) and `text-lg` once. The effective working scale in the table views is xs/sm, creating a visually flat hierarchy where column headers, data cells, and secondary metadata are all rendered at nearly the same visual weight. Only `font-semibold` / `font-bold` separates header-level text from body text.
- Impact: Dense table views are hard to scan quickly, especially for operators under time pressure during an incident.
- Fix: Introduce at least one explicit `text-base` level for primary row data (task title, asset hostname) to create a 3-level visual rhythm: `text-xs` metadata < `text-sm` labels < `text-base` primary content.

**[SEVERITY: LOW] RemediationTaskModal: h2 heading is text-lg, same size as body labels**
- Location: `RemediationTaskModal.tsx:110`
- Issue: The modal title "Create Remediation Task" / "Edit Remediation Task" uses `text-lg font-semibold`. Form field labels use `text-sm font-medium`. The size gap (lg vs sm) is sufficient but the weight gap (semibold vs medium) is narrow. In dark mode the contrast between title and label text is harder to distinguish.
- Impact: Minor scan friction; modal purpose is not immediately dominant over form field labels.
- Fix: Increase title to `text-xl font-bold` to widen the hierarchy gap.

### Positives
- Three font weights (medium / semibold / bold) are used consistently — bold for numbers/KPIs, semibold for headings and badge text, medium for form labels.
- RemediationDashboard table headers use `text-xs uppercase tracking-wider font-semibold` — the correct Tailwind pattern for scannable data table column headers.
- FrameworkDetail uses `font-mono text-xs` for Control IDs, appropriately distinguishing code-like identifiers from prose text.

---

## Pillar 5: Spacing

**Score: 3/4 — Good**

### Findings

**[SEVERITY: MEDIUM] AssetComplianceList: description text input positioned below icon buttons creates an awkward touch target**
- Location: `AssetComplianceList.tsx:181-200`
- Issue: The Actions cell uses `flex flex-col items-end gap-1`. The description input (`w-44`) sits directly below the three icon buttons with only `gap-1` (4px) separation. The input is 176px wide while the icon row is narrower, causing the column to be wider than necessary. On narrow viewports the `min-w-full` table may force horizontal scroll.
- Impact: The Actions column dominates the right side of what is already a 6-column table. The description field placement is semantically confusing — it belongs with the upload interaction, not in the "actions" column header space.
- Fix: Move the description input into a fly-out or tooltip triggered by the upload button, or place it as a full-width row beneath the asset row rather than inside the actions cell.

**[SEVERITY: LOW] FrameworkDetail toolbar: buttons use `mt-3 flex space-x-2` with no wrapping guard**
- Location: `FrameworkDetail.tsx:506`
- Issue: Seven buttons in `flex space-x-2` with no `flex-wrap`. At typical compliance dashboard viewport widths (1280px) with a sidebar, the effective content width may be 900-1000px. Seven `px-3 py-1.5` buttons at ~90-120px each can total 700-840px, leaving minimal margin.
- Impact: Right-side buttons may be clipped. "View Reports" (last in the row) is the lowest-priority action but will be first to be hidden.
- Fix: Add `flex-wrap gap-2` and replace `space-x-2` (incompatible with wrapping) with `gap-2`.

**[SEVERITY: LOW] RemediationTaskModal: arbitrary `min-[150px]` equivalent not present but `max-w-lg` on 6-field modal may feel cramped**
- Location: `RemediationTaskModal.tsx:108`
- Issue: `max-w-lg` (~512px) is appropriate for a 6-field modal but the `p-6` padding on both the outer div and form content applies 24px on all sides — with the inner `space-y-4` (16px per field gap), the modal content area is approximately 464px wide. This is functional but tight for the textarea + "Suggest steps" button which share a header row.
- Impact: Low — functional, not broken.
- Fix: No immediate action required; note for future form-heavy modals.

### Positives
- RemediationDashboard uses a coherent three-section layout: `space-y-6` at the top level, `grid grid-cols-3 gap-4` for stat cards, `flex gap-2` for filter chips — all on the Tailwind 4-unit scale with no arbitrary values.
- Table cells in both RemediationDashboard and AssetComplianceList use consistent `p-4` / `px-6 py-4` patterns.

---

## Pillar 6: Experience Design

**Score: 2/4 — Needs Work**

### Findings

**[SEVERITY: HIGH] RemediationTaskModal + RemediationDashboard: no user-visible error feedback on any async failure**
- Location: `RemediationTaskModal.tsx:68,100`, `RemediationDashboard.tsx:36,60`
- Issue: Four critical async operations — fetch tasks, mark resolved, AI suggest, save task — all fail silently to the user. When `fetchTasks` fails (e.g., network offline), the table stays empty with the "No remediation tasks found" empty state, which is indistinguishable from a legitimately empty list. A compliance operator cannot tell whether remediation tasks exist but failed to load.
- Impact: BLOCKER for trust in a compliance workflow. A user may declare "no open tasks" when the load simply failed.
- Fix: After fetch failure, show an error state in the table region: "Failed to load tasks — check your connection and retry" with a Retry button. For modal save/suggest failures, show inline error toast (the `showToast` utility is already imported in FrameworkDetail and available project-wide).

**[SEVERITY: HIGH] AssetComplianceList: "Mark Compliant" and "Mark Non-Compliant" buttons are no-ops**
- Location: `FrameworkDetail.tsx:770` (stub `console.log` passed to `onUpdateStatus`)
- Issue: Both status-change buttons call `onUpdateStatus`, which is wired to `console.log` only. No API call, no optimistic update, no error, no success feedback. The action appears to register (no visual rejection) but has zero effect.
- Impact: BLOCKER — operators can mark assets compliant, proceed to generate a report, and submit it — with false compliance state because no data was written.
- Fix: Implement `onUpdateStatus` in FrameworkDetail.tsx as a real API call to `api.updateAssetComplianceStatus(...)` with a success toast and a `refreshAssetCompliance(assetId)` call.

**[SEVERITY: HIGH] No keyboard escape handling on any modal**
- Location: `RemediationTaskModal.tsx`, `FrameworkDetail.tsx` (ControlEvidenceUploadModal, AddControlModal, ReportsModal)
- Issue: None of the modal components listen for `Escape` keydown to close. No `onKeyDown` or `useEffect` keyboard listener exists anywhere in the audited components. Focus is not trapped inside the modal overlay (tab will cycle through background page elements behind the `z-50` overlay).
- Impact: Keyboard-only and screen-reader users cannot dismiss modals via keyboard. Tab focus leaks to obscured background content. Both are WCAG 2.1 Level AA failures (2.1.1 Keyboard, 4.1.3 Focus management).
- Fix: Add `useEffect` in each modal with `document.addEventListener('keydown', e => { if (e.key === 'Escape') onClose(); })`. Add `tabIndex={-1}` and `ref` on the modal container with `focus()` on mount to trap focus.

**[SEVERITY: MEDIUM] RemediationDashboard: "Mark Resolved" has no confirmation guard**
- Location: `RemediationDashboard.tsx:191-197`
- Issue: Clicking "Mark Resolved" immediately calls `updateRemediationTask` with no confirmation dialog. Resolving a compliance remediation task is a meaningful state transition in an audit trail — it should be reversible or at least deliberate. The contrast with `handleDeleteEvidence` (which uses `window.confirm`) is jarring.
- Impact: Accidental resolution of an in-progress task creates an incorrect audit record that must be manually corrected.
- Fix: Add a `window.confirm('Mark this task as resolved? This will be recorded in the audit trail.')` guard, or a visually distinct confirmation step (inline expand to confirm).

**[SEVERITY: MEDIUM] Priority field is hidden on edit — but priority value is editable on save**
- Location: `RemediationTaskModal.tsx:221`, `:83`
- Issue: The Priority field is rendered only when `!task` (creating). When editing, the `priority` state retains its initialized value (from `task.priority`). The `handleSave` for edit mode calls `api.updateRemediationTask(task.id, { description, assignee, due_date })` — `priority` is not included in the update payload, so the omission is harmless. However, the absence of the priority field on edit with no explanation ("Priority cannot be changed after creation") may confuse users who want to escalate a task.
- Impact: Low risk, but no copy communicates why the field is absent.
- Fix: Add a read-only display of the priority value when editing, or a note: "Priority is set at creation and cannot be changed."

### Positives
- WebSocket live-patching in RemediationDashboard correctly guards against event injection: only tasks with matching `t.id === data.task_id` are updated (threat T-04-09 mitigated).
- ControlEvidenceUploadModal has a meaningful post-upload state: after success, the "Upload Evidence" button disappears and only "Close" remains, preventing double-upload.
- Spinner states on async buttons (`saving`, `suggesting`, `uploading`) are correctly implemented with `disabled` attributes, preventing double-submit.
- `ingestingMap` per-asset in AssetComplianceList correctly tracks in-flight state at asset granularity, not globally.

---

## Priority Fix List

| Priority | Pillar | Component | Issue | Effort |
|----------|--------|-----------|-------|--------|
| P1 | Experience Design | AssetComplianceList / FrameworkDetail | `onUpdateStatus` is a no-op `console.log` — status buttons never write data | M |
| P2 | Experience Design | RemediationTaskModal, RemediationDashboard | All async failures are silent — zero user-visible error feedback on 6 catch blocks | S |
| P3 | Experience Design | All modals (5 modal components) | No Escape-key dismiss and no focus trap — WCAG 2.1 AA failures | M |
| P4 | Copywriting | RemediationDashboard | Fetch failure renders as empty state, indistinguishable from "no tasks exist" | S |
| P5 | Visuals | RemediationDashboard | Loading state is text-only with layout shift — replace with skeleton rows | S |
| P6 | Visuals | AssetComplianceList | Icon-only status buttons (Check/X/Upload) have no aria-label — screen reader inaccessible | S |
| P7 | Experience Design | RemediationDashboard | "Mark Resolved" has no confirmation — accidental audit-record mutations | S |
| P8 | Color | AssetComplianceList | `text-[10px]` on source badges likely fails WCAG AA contrast at that size | S |
| P9 | Visuals | FrameworkDetail | Seven-button toolbar has no flex-wrap — overflows at ~1024px viewport | S |
| P10 | Copywriting | FrameworkDetail | `onUpdateStatus` stub aside — seven toolbar buttons with inconsistent verbs and no visual grouping | M |

---

## What's Working Well

- **Semantic status colors are consistent**: red=open/critical, yellow=in-progress, green=resolved/compliant, gray=dismissed — applied uniformly across STATUS_COLORS (RemediationDashboard), statusClasses (FrameworkDetail), and badge pills (AssetComplianceList).
- **Dark mode coverage is thorough**: every card, table, badge, and modal has a `dark:` variant. No component renders white-background-only.
- **WebSocket integration is production-quality**: the `remediation_update` event handler in RemediationDashboard correctly uses teardown (`socketService.off` in effect cleanup) and guards against stale/injected data.
- **AI affordances are well-communicated**: the "Suggest steps" button tooltip ("Save the task first to get AI suggestions") and the ControlEvidenceUploadModal's graduated AI validation feedback (RELEVANT/IRRELEVANT/UNCLEAR with confidence %) are clear, contextual, and non-alarming.
- **Spinner/disabled states on async actions are implemented correctly** throughout — no double-submit paths were found in RemediationTaskModal, ControlEvidenceUploadModal, or the delete handler.

---

## Files Audited

- `components/RemediationDashboard.tsx` (217 lines)
- `components/RemediationTaskModal.tsx` (265 lines)
- `components/AssetComplianceList.tsx` (218 lines)
- `components/FrameworkDetail.tsx` (847 lines — includes ControlEvidenceUploadModal, AddControlModal, ReportsModal sub-components)
- `components/CloudSecurityDashboard.tsx` (partial — header section, CSPM stat cards)
- `.planning/phases/04-remediation-workflow/04-02-SUMMARY.md`
- `.planning/phases/02-manual-evidence-uploads/02-02-SUMMARY.md`
- `.planning/phases/05-integration-and-e2e-verification/05-00-SUMMARY.md`
