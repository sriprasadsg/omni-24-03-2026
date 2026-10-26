# Phase 81 — UI Review

**Audited:** 2026-10-26
**Baseline:** 81-UI-SPEC.md (approved 2026-10-25)
**Screenshots:** not captured. The live UI at /var/www/omni-agent is an older build without this phase and the backend routes are not live. No local vite server was started, because the screen needs an authenticated session and live API payloads. This is a code-only audit; every visual finding is derived from class names and structure, not from rendered output.
**Interaction captures:** off (workflow.ui_interaction_capture is false). Interaction findings are code-derived.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Nearly every contract string is present verbatim. Gaps are one unconfirmed platform empty-state string, a duplicated "Try again", and a Stop cell that can hide a platform stop. |
| 2. Visuals | 3/4 | Hierarchy, chips and icons follow the contract. The sidebar icon is shared by 8 other entries, and nothing has been rendered. |
| 3. Color | 3/4 | Accent, red and amber roles are correct and no hex is hardcoded. Bare "Try again" text buttons carry no declared colour or hover state. |
| 4. Typography | 4/4 | Only 12/14/18/30px and 400/600 weights in the new files. No font-medium, font-bold or truncate. |
| 5. Spacing | 3/4 | Two `mt-0.5` half-steps, which the spec forbids. The textarea uses `p-3`, which is outside the declared scale. |
| 6. Experience Design | 3/4 | Loading, error, empty and partial states are all covered. Weaknesses are the ambiguous Resume controls for Super Admin and a stale status that cannot be seen. |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **Ambiguous or mis-scoped Resume control when a platform stop is active (WARNING).** `AutonomousOpsStatusCard.tsx:172-176` treats `tenantStop ?? platform` as `anyStop` and draws "Resume automatic actions" whenever `canResume` is true. That opens a *tenant* resume dialog. In that case `dialogCurrent` is null (line 231), so the dialog shows no "Stopped by..." context. A Super Admin inside a tenant, with a platform stop active, would also see "Resume all organizations" (line 208) beside it. Two similarly named Resume buttons, one of which may act on the wrong scope or show no context, is a risk on a safety control. Fix: draw the tenant Resume only when `tenantStop` is non-null, and leave a platform stop to the platform row or the "Only a platform administrator can resume this." line. Add a test for Super Admin in tenant scope with a platform-only stop.
2. **A stuck status looks fresh (WARNING).** The banner and card keep the last known state when a poll fails, as the spec requires. Nothing shows that the data is stale. After a network loss, the banner could keep saying "stopped" (or not appear) indefinitely. The spec forbids the banner from showing its own fetch error, so put the staleness cue on the screen. Show a muted "Last updated {time}" beside Refresh, or an `aria-live="polite"` notice in the status card after N failed polls, without changing the banner.
3. **Half-step spacing and the shared sidebar icon (WARNING).** Replace `mt-0.5` at `AutonomousOpsStatusCard.tsx:55` and `AutonomousOpsStopDialog.tsx:224` with `mt-1`, or align the icon with `items-center`. The spec bans half-steps in new elements. Give `autonomousOps` a glyph used by no other entry in `sidebarPresentation.tsx:166`. It currently shares ShieldZapIcon with security, edr, yaraRules, mdr, siem, runtimeSecurity and nativeSecurity, and the spec wants it distinguishable at a glance.

Minor:
- Stop dialog Cancel stays enabled while a request is in flight (`AutonomousOpsStopDialog.tsx:179`). This matches the spec. It lets the user dismiss the dialog before the outcome is known, though, and the later toast is the only feedback. Consider disabling Esc and Cancel while `pending`.
- The textarea has no placeholder and no explicit text colour in light mode (`AutonomousOpsStopDialog.tsx:210`). Add `placeholder:text-gray-400` and `resize-y`, and confirm the border contrast against the Modal surface.
- The Stop cell shows only `stop.tenant ?? stop.platform` (`AutonomousOpsStatusCard.tsx:263`). When both are active, the card hides the platform stop that the banner shows. Show both, or add a helper line.
- The platform-scope empty-state body is not in the UI-SPEC. 81-07 already flagged it for confirmation, and it should be added to the copywriting contract.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Verified verbatim against the contract:
  - Page title and subtitle (`AutonomousOpsActivity.tsx:45-47`).
  - Banner titles and detail (`AutonomousOpsStopBanner.tsx:78,86`).
  - Level labels and helpers (`AutonomousOpsStatusCard.tsx:26-33`).
  - All four notices (lines 285-302).
  - Stop and Resume titles, bodies, confirms, pending labels, toasts and failure text including the fallbacks (`AutonomousOpsStopDialog.tsx:39-83`).
  - The 409 and 403 toasts, `Enter a reason to resume.`, and all empty-state strings (`AutonomousOpsActivityList.tsx:204-226`).
- No banned terms found by grep in these files, and ACTV-08 has a rules file with tests.
- Findings:
  - `AutonomousOpsActivityList.tsx:222` platform empty body is invented copy, not in the contract.
  - `AutonomousOpsActivityList.tsx:397-398` reads "Couldn't load more activity. Try again." and then shows a "Try again" button. This matches the spec but is redundant.
  - Generic labels (Cancel, Refresh, Load more, Try again) were flagged as non-blocking at spec sign-off.
  - `AutonomousOpsStatusCard.tsx:263` hides a platform stop when a tenant stop is also active (see fixes).

### Pillar 2: Visuals (3/4)
- Focal point: the status card sits directly under the h1, and the amber banner outranks it when active, as the spec intends.
- Every chip carries a 12px `aria-hidden` icon plus text. Simulation is distinguishable through its dashed chip, its dashed left rule and its result sentence.
- Icon-only buttons: none. All controls have text.
- Findings:
  - Sidebar icon is non-distinct (`sidebarPresentation.tsx:166`).
  - The empty-state card, banner and table could not be rendered, so wrapping, clamp and overflow behaviour are unverified.
  - `SIM_RULE` is applied to the first `td` and not the `tr`. The dashed rule only spans the first cell's height, which is fine while cells align top, but verify visually.

### Pillar 3: Color (3/4)
- No hardcoded hex or rgb in any of the 7 files. Chip, notice, error and banner class sets match the spec tables.
- Accent is used only for Resume (`bg-primary-600`) and the selected filter pill (`bg-primary-500/10`), as the spec reserves. Stop is red and the banner is amber.
- Findings:
  - Active pills use `border-transparent` plus a ring, which is fine.
  - The "Try again" text buttons in the status error block (`AutonomousOpsStatusCard.tsx:22,150`) have no declared colour or hover. They inherit red-700, which is acceptable, but they have no hover state.
  - Dialog and card contrast pairs are unverified without rendering.

### Pillar 4: Typography (4/4)
- Sizes found in the new files are only `text-xs`, `text-sm`, `text-lg` and `text-[30px]`.
- Weights are only 400 (default) and `font-semibold`. grep found no `font-medium`, `font-bold` or `truncate`.
- `font-mono` is used only for rule ids and targets. `tabular-nums` is applied on counts and times.
- Caveat: the `Modal` title typography belongs to the shared component and was not audited.

### Pillar 5: Spacing (3/4)
- Cell padding `px-4 py-4`, card `p-6`, gaps 4/6, `py-12 px-8` empty state, `min-h-10` buttons and `min-h-8` pills all match the contract.
- Deviations:
  - `mt-0.5` at `AutonomousOpsStatusCard.tsx:55` and `AutonomousOpsStopDialog.tsx:224` (half-steps).
  - Textarea `p-3` (12px) at `AutonomousOpsStopDialog.tsx:210`, not in the declared scale.
  - `mt-1` and `mt-2` on dt/dd and the subtitle are not listed in the spec but are on-grid.

### Pillar 6: Experience Design (3/4)
- Covered:
  - Skeleton and `aria-busy` on the card and list.
  - First-page and load-more errors, with Stop still available when status fails.
  - Empty states (live, shadow, filtered, platform, no tenant).
  - Pending labels with an `inFlight` ref, so a double click sends one request.
  - Resume requires a trimmed reason with no keyboard shortcut. Ctrl/Cmd+Enter submits Stop.
  - Backdrop close is disabled and `showClose` is false, so focus lands in the textarea.
  - 409 and 403 handling.
  - Silent background refresh that is paused when the tab is hidden and respects pagination.
  - The server's `canResume` is authoritative for the Resume button.
- Weaknesses:
  - The Resume scope ambiguity (fix 1).
  - No stale-data indicator (fix 2).
  - Cancel and Esc stay live during a pending request.
  - The error block does not move focus.
  - No automated visual or live check exists. 81-07 and 81-10 both list the light/dark, contrast and live-API checks as human_judgment and unperformed. The UI is unpublished and the backend has not been restarted.
- Registry audit: shadcn is not initialised and no third-party registries are used, so the audit was skipped.

---

## Files Audited
- /home/azureuser/enterprise-omni-agent-ai-platform/components/AutonomousOpsActivity.tsx
- /home/azureuser/enterprise-omni-agent-ai-platform/components/AutonomousOpsActivityList.tsx
- /home/azureuser/enterprise-omni-agent-ai-platform/components/AutonomousOpsStatusCard.tsx
- /home/azureuser/enterprise-omni-agent-ai-platform/components/AutonomousOpsStopDialog.tsx
- /home/azureuser/enterprise-omni-agent-ai-platform/components/AutonomousOpsStopBanner.tsx
- App.tsx (banner and provider wiring at lines 1962-1984, route case at line 1738), components/sidebarPresentation.tsx (line 166)
- Not read in full: services/autonomousOpsApi.ts and contexts/AutonomousOpsStatusContext.tsx (only through the summaries), components/Modal.tsx (focus handling only)
